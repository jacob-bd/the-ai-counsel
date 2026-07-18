"""GitHub Copilot OAuth provider."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from ..credentials import get_oauth_credential, set_oauth_credential
from ..oauth.github_copilot import fetch_copilot_account
from ..oauth.refresh import get_valid_access_token
from .base import LLMProvider
from .temperature import add_temperature_if_supported

logger = logging.getLogger(__name__)

COPILOT_BASE = "https://api.githubcopilot.com"
EDITOR_VERSION = "vscode/1.85.1"

COPILOT_MODEL_SEEDS = [
    {"id": "gpt-4.1", "name": "GPT-4.1", "is_free": True},
    {"id": "gpt-4o", "name": "GPT-4o", "is_free": True},
]

# Strict Free/Student allowlist for chat/completions (catalog often over-lists).
_COPILOT_FREE_ALLOWLIST = frozenset(
    {
        "gpt-4.1",
        "gpt-4o",
        "gpt-4o-mini",
        "raptor-mini",
        "goldeneye",
    }
)

# Included / 0× labels when API omits billing.multiplier (paid + free).
_COPILOT_KNOWN_FREE_IDS = frozenset(_COPILOT_FREE_ALLOWLIST)

# Catalog often marks these Free-capable; chat/completions rejects on Free.
_COPILOT_FREE_CHAT_BLOCKLIST = frozenset(
    {
        "gpt-5-mini",
    }
)


def _copilot_supports_chat(entry: Dict[str, Any]) -> bool:
    """True if the model can be called via chat/completions."""
    mid = str(entry.get("id") or "").lower()
    # *-auto / *-free-auto are Copilot Auto router aliases — not callable model IDs.
    if mid.endswith("-auto") or mid.endswith("-free-auto") or mid == "auto":
        return False
    if "embedding" in mid:
        return False

    caps = entry.get("capabilities")
    if isinstance(caps, dict):
        family = str(caps.get("family") or "").lower()
        if "embedding" in family:
            return False

    endpoints = entry.get("supported_endpoints")
    if isinstance(endpoints, list) and endpoints:
        normalized = {str(e).lower().rstrip("/") for e in endpoints}
        chat_ok = any(
            e.endswith("chat/completions") or e == "/chat/completions" for e in normalized
        )
        if not chat_ok:
            return False
    return True


def _copilot_model_allowed(entry: Dict[str, Any], *, is_free_plan: bool) -> bool:
    """Return True if this account may manually select the model for chat."""
    if not _copilot_supports_chat(entry):
        return False
    mid = str(entry.get("id") or "").lower()
    if is_free_plan and mid in _COPILOT_FREE_CHAT_BLOCKLIST:
        return False
    if entry.get("model_picker_enabled") is False:
        return False
    policy = entry.get("policy")
    if isinstance(policy, dict) and str(policy.get("state", "")).lower() == "disabled":
        return False
    if is_free_plan and mid not in _COPILOT_FREE_ALLOWLIST:
        return False
    return True


def _friendly_copilot_error(status_code: int, body: str) -> str:
    code = None
    message = None
    try:
        parsed = json.loads(body)
        err = parsed.get("error") if isinstance(parsed, dict) else None
        if isinstance(err, dict):
            code = err.get("code")
            message = err.get("message")
    except Exception:
        pass
    if code == "model_not_supported" or (
        isinstance(message, str) and "not supported" in message.lower()
    ):
        return (
            "Copilot rejected this model "
            f"(HTTP {status_code}). Auto/router IDs (names ending in -auto) and "
            "premium models outside your plan cannot be called via the API — "
            "pick a concrete model such as gpt-4.1 or gpt-4o "
            "(labeled · Free when included). Premium models need Copilot Pro+."
        )
    return f"Copilot API error: {status_code} - {body}"


def _is_copilot_free_model(entry: Dict[str, Any]) -> bool:
    """True for included/0× models (safe for Free plan; no premium multiplier)."""
    mid = str(entry.get("id") or "").lower()
    if mid.endswith("-auto") or mid.endswith("-free-auto") or mid == "auto":
        return False
    if mid in _COPILOT_FREE_CHAT_BLOCKLIST:
        return False
    billing = entry.get("billing")
    if isinstance(billing, dict) and billing.get("multiplier") is not None:
        try:
            return float(billing["multiplier"]) == 0.0
        except (TypeError, ValueError):
            pass
    return mid in _COPILOT_KNOWN_FREE_IDS


def _copilot_display_name(mid: str, *, is_free: bool) -> str:
    base = f"{mid} [Copilot]"
    return f"{base} · Free" if is_free else base


def _normalize_copilot_models(
    rows: List[Any], *, is_free_plan: bool = False
) -> List[Dict[str, Any]]:
    models: List[Dict[str, Any]] = []
    for m in rows:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        if not mid or not _copilot_model_allowed(m, is_free_plan=is_free_plan):
            continue
        is_free = _is_copilot_free_model(m) or is_free_plan
        models.append(
            {
                "id": f"github-copilot:{mid}",
                "name": _copilot_display_name(str(mid), is_free=is_free),
                "provider": "GitHub Copilot",
                "source": "github-copilot",
                "is_free": is_free,
            }
        )
    return models


def get_cached_copilot_account() -> Optional[Dict[str, Any]]:
    cred = get_oauth_credential("github-copilot")
    if not cred:
        return None
    data = cred.get("providerData")
    if not isinstance(data, dict):
        return None
    account = data.get("copilot")
    return account if isinstance(account, dict) else None


async def ensure_copilot_account() -> Optional[Dict[str, Any]]:
    """Return plan summary, refreshing from GitHub when missing."""
    cached = get_cached_copilot_account()
    if cached and "is_free_plan" in cached:
        return cached
    cred = get_oauth_credential("github-copilot")
    if not cred:
        return None
    ghu = cred.get("refresh") or ""
    if not ghu:
        return cached
    try:
        account = await fetch_copilot_account(ghu)
    except Exception:
        logger.exception("Failed to refresh Copilot account plan")
        return cached
    provider_data = dict(cred.get("providerData") or {})
    provider_data["copilot"] = account
    cred = dict(cred)
    cred["providerData"] = provider_data
    set_oauth_credential("github-copilot", cred)
    return account


class GitHubCopilotProvider(LLMProvider):
    async def query(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        timeout: float = 120.0,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        try:
            token = await get_valid_access_token("github-copilot")
        except Exception as exc:
            return {"error": True, "error_message": str(exc)}

        model = model_id.removeprefix("github-copilot:")
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                payload = add_temperature_if_supported(
                    {"model": model, "messages": messages},
                    model,
                    "github-copilot",
                    temperature,
                )
                response = await client.post(
                    f"{COPILOT_BASE}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "Editor-Version": EDITOR_VERSION,
                    },
                    json=payload,
                )
                if response.status_code != 200:
                    return {
                        "error": True,
                        "error_message": _friendly_copilot_error(
                            response.status_code, response.text
                        ),
                    }
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return {"content": content, "usage": data.get("usage"), "error": False}
        except Exception as e:
            return {"error": True, "error_message": str(e)}

    async def get_models(self) -> List[Dict[str, Any]]:
        if not get_oauth_credential("github-copilot"):
            return []
        account = await ensure_copilot_account()
        is_free_plan = bool(account and account.get("is_free_plan"))
        try:
            token = await get_valid_access_token("github-copilot")
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{COPILOT_BASE}/models",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Editor-Version": EDITOR_VERSION,
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    rows = data.get("data") if isinstance(data, dict) else data
                    if isinstance(rows, list):
                        models = _normalize_copilot_models(rows, is_free_plan=is_free_plan)
                        if models:
                            return models
        except Exception:
            logger.exception("Failed to list Copilot models")
        # Free fallback seeds; paid keeps seeds too if catalog empty.
        return [
            {
                "id": f"github-copilot:{s['id']}",
                "name": _copilot_display_name(s["id"], is_free=True),
                "provider": "GitHub Copilot",
                "source": "github-copilot",
                "is_free": True,
            }
            for s in COPILOT_MODEL_SEEDS
        ]

    async def validate_key(self, api_key: str) -> Dict[str, Any]:
        if get_oauth_credential("github-copilot"):
            account = await ensure_copilot_account()
            plan = (account or {}).get("copilot_plan") or "connected"
            sku = (account or {}).get("access_type_sku")
            tier = "Free" if (account or {}).get("is_free_plan") else "Paid"
            detail = f"{tier}"
            if plan:
                detail += f" ({plan})"
            if sku:
                detail += f" · {sku}"
            return {"success": True, "message": f"GitHub Copilot OAuth connected — {detail}"}
        return {"success": False, "message": "GitHub Copilot OAuth not connected"}
