"""Discover and import credentials from relay-ai (opt-in copy)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .availability import is_container_environment, probe_keyring
from .ids import KNOWN_SECRET_IDS, OAUTH_SECRET_IDS
from .store import has_secret, set_secret

logger = logging.getLogger(__name__)

RELAY_KEYRING_SERVICE = "relay-ai"
RELAY_CHUNK_PREFIX = "__relay_chunked__:"

# Never import these (account-ban risk).
BLOCKED_RELAY_IDS = frozenset({"claude-code", "antigravity"})

# relay provider id / account → counsel secret id + label
RELAY_API_MAP = {
    "openai": ("api:openai", "OpenAI API key"),
    "anthropic": ("api:anthropic", "Anthropic API key"),
    "google": ("api:google", "Google API key"),
    "mistral": ("api:mistral", "Mistral API key"),
    "deepseek": ("api:deepseek", "DeepSeek API key"),
    "groq": ("api:groq", "Groq API key"),
    "nvidia": ("api:nvidia", "NVIDIA API key"),
    "openrouter": ("api:openrouter", "OpenRouter API key"),
}

RELAY_OAUTH_MAP = {
    "xai-oauth": ("oauth:xai-oauth", "xAI SuperGrok (OAuth)"),
    "openai-oauth": ("oauth:openai-oauth", "ChatGPT Plus/Pro (OAuth)"),
    "github-copilot": ("oauth:github-copilot", "GitHub Copilot (OAuth)"),
}

RELAY_GLOBAL_OPENCODE = ("global:opencode", "api:opencode", "OpenCode API key")

# In-process cache so Settings re-renders don't re-trigger macOS Keychain ACL prompts.
_DISCOVER_CACHE: Optional[Tuple[float, Dict[str, Any]]] = None
_DISCOVER_CACHE_TTL_SEC = 300.0


def _relay_providers_path() -> Path:
    return Path.home() / ".relay-ai" / "providers.json"


def _read_relay_keyring_raw(account: str) -> Optional[str]:
    """Single getPassword for an account (does not reassemble chunks)."""
    try:
        import keyring
    except Exception:
        return None
    try:
        return keyring.get_password(RELAY_KEYRING_SERVICE, account)
    except Exception:
        return None


def _read_relay_keyring(account: str) -> Optional[str]:
    """Full secret including chunk reassembly (use for import only)."""
    value = _read_relay_keyring_raw(account)
    if value is None:
        return None
    if not value.startswith(RELAY_CHUNK_PREFIX):
        return value
    try:
        import keyring

        count = int(value[len(RELAY_CHUNK_PREFIX) :])
    except Exception:
        return value
    parts = []
    for i in range(count):
        try:
            chunk = keyring.get_password(RELAY_KEYRING_SERVICE, f"{account}::chunk::{i}")
        except Exception:
            return None
        if chunk is None:
            return None
        parts.append(chunk)
    return "".join(parts)


def _load_registry() -> Tuple[List[str], Dict[str, str]]:
    """Return (provider_ids, auth_type_by_id) from ~/.relay-ai/providers.json."""
    registry_path = _relay_providers_path()
    ids: List[str] = []
    auth_types: Dict[str, str] = {}
    if not registry_path.exists():
        return ids, auth_types
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        providers = data.get("providers") if isinstance(data, dict) else data
        if isinstance(providers, list):
            for p in providers:
                if not isinstance(p, dict) or not p.get("id"):
                    continue
                pid = str(p["id"])
                if pid in BLOCKED_RELAY_IDS:
                    continue
                ids.append(pid)
                auth = str(p.get("authType") or p.get("auth_type") or "").lower()
                auth_types[pid] = auth
    except Exception:
        logger.exception("Failed reading %s", registry_path)
    return ids, auth_types


def _accounts_to_probe(registry_ids: List[str], auth_types: Dict[str, str]) -> List[Tuple[str, str, str, str]]:
    """Build (relay_id, keyring_account, counsel_secret_id, label) list.

    Prefer registry-driven probes so we don't hit macOS Keychain for every
    possible provider (each getPassword can show a separate ACL dialog).
    """
    probes: List[Tuple[str, str, str, str]] = []

    if registry_ids:
        for rid in registry_ids:
            if rid in BLOCKED_RELAY_IDS:
                continue
            auth = auth_types.get(rid, "")
            if rid in RELAY_OAUTH_MAP or auth == "oauth":
                if rid in RELAY_OAUTH_MAP:
                    secret_id, label = RELAY_OAUTH_MAP[rid]
                    probes.append((rid, f"oauth:provider:{rid}", secret_id, label))
                continue
            if rid in RELAY_API_MAP:
                secret_id, label = RELAY_API_MAP[rid]
                probes.append((rid, f"provider:{rid}", secret_id, label))
        # OpenCode global key is often shared across zen/go.
        if any(x in registry_ids for x in ("opencode-zen", "opencode-go", "opencode", "zen", "go")):
            g_account, g_secret, g_label = RELAY_GLOBAL_OPENCODE
            probes.append(("opencode", g_account, g_secret, g_label))
        return probes

    # No registry: only probe the three OAuth accounts we care about (not every API key).
    for rid, (secret_id, label) in RELAY_OAUTH_MAP.items():
        probes.append((rid, f"oauth:provider:{rid}", secret_id, label))
    g_account, g_secret, g_label = RELAY_GLOBAL_OPENCODE
    probes.append(("opencode", g_account, g_secret, g_label))
    return probes


def discover_relay_ai_credentials(*, force: bool = False) -> Dict[str, Any]:
    global _DISCOVER_CACHE

    if is_container_environment():
        return {
            "items": [],
            "reason": "relay-ai OS keystore import isn’t available in containers (native desktop only).",
        }

    now = time.time()
    if (
        not force
        and _DISCOVER_CACHE is not None
        and now - _DISCOVER_CACHE[0] < _DISCOVER_CACHE_TTL_SEC
    ):
        return _DISCOVER_CACHE[1]

    # Do NOT call probe_keyring() here — that hits a separate ACL entry and
    # adds another macOS dialog. Fail soft when individual gets fail.

    registry_ids, auth_types = _load_registry()
    if not registry_ids and not _relay_providers_path().exists():
        result = {
            "items": [],
            "reason": (
                "No ~/.relay-ai/providers.json found. Install/configure relay-ai first, "
                "then click Discover. (We avoid scanning the whole keychain to prevent "
                "repeated macOS password prompts.)"
            ),
        }
        _DISCOVER_CACHE = (now, result)
        return result

    candidates: List[Dict[str, Any]] = []
    for relay_id, account, secret_id, label in _accounts_to_probe(registry_ids, auth_types):
        # Presence check only — one getPassword. Do not reassemble chunks here
        # (each chunk is another macOS Keychain ACL prompt).
        raw = _read_relay_keyring_raw(account)
        if not raw:
            continue
        candidates.append(
            {
                "relay_id": relay_id,
                "counsel_secret_id": secret_id,
                "kind": "oauth" if secret_id.startswith("oauth:") else "api",
                "label": label,
                "already_configured_in_counsel": has_secret(secret_id),
            }
        )

    seen = set()
    items = []
    for c in candidates:
        sid = c["counsel_secret_id"]
        if sid in seen:
            continue
        seen.add(sid)
        items.append(c)

    result = {
        "items": items,
        "reason": None if items else "No importable relay-ai credentials found.",
        "hint": (
            "On macOS, Keychain may ask once per credential — choose Always Allow. "
            "Results are cached for a few minutes."
        ),
    }
    _DISCOVER_CACHE = (now, result)
    return result


def clear_discover_cache() -> None:
    global _DISCOVER_CACHE
    _DISCOVER_CACHE = None


def import_relay_ai_credentials(
    relay_ids: List[str], *, replace_existing: bool = False
) -> Dict[str, Any]:
    if is_container_environment():
        raise RuntimeError("relay-ai import isn’t available in containers")

    imported: List[str] = []
    skipped: List[str] = []
    errors: Dict[str, str] = {}

    id_to_account = {}
    for rid, (sid, _) in RELAY_OAUTH_MAP.items():
        id_to_account[rid] = (f"oauth:provider:{rid}", sid, "oauth")
    for rid, (sid, _) in RELAY_API_MAP.items():
        id_to_account[rid] = (f"provider:{rid}", sid, "api")
    id_to_account["opencode"] = (RELAY_GLOBAL_OPENCODE[0], RELAY_GLOBAL_OPENCODE[1], "api")

    for rid in relay_ids:
        if rid in BLOCKED_RELAY_IDS:
            skipped.append(rid)
            continue
        mapping = id_to_account.get(rid)
        if not mapping:
            errors[rid] = "unknown id"
            continue
        account, secret_id, kind = mapping
        if secret_id not in KNOWN_SECRET_IDS:
            errors[rid] = "unsupported secret"
            continue
        if has_secret(secret_id) and not replace_existing:
            skipped.append(rid)
            continue
        # Full read (may prompt once per chunk on first authorize).
        raw = _read_relay_keyring(account)
        if not raw:
            errors[rid] = "not found in relay-ai keystore"
            continue
        if kind == "oauth":
            try:
                blob = json.loads(raw)
                if not isinstance(blob, dict) or blob.get("type") != "oauth":
                    errors[rid] = "invalid oauth blob"
                    continue
            except json.JSONDecodeError:
                errors[rid] = "invalid oauth json"
                continue
        set_secret(secret_id, raw)
        imported.append(rid)

    if imported:
        _enable_providers_for_imported(imported)

    clear_discover_cache()
    return {"imported": imported, "skipped": skipped, "errors": errors}


def _enable_providers_for_imported(relay_ids: List[str]) -> None:
    """Turn on council toggles for imported secrets.

    Keys live in the credential store (file or OS keystore); settings.json stays
    without API key fields. Enabling toggles makes Retest / model pickers usable
    immediately after import without re-pasting keys.
    """
    from ..settings import get_settings, update_settings

    settings = get_settings()
    enabled = dict(settings.enabled_providers or {})
    toggles = dict(settings.direct_provider_toggles or {})
    changed = False

    for rid in relay_ids:
        if rid in OAUTH_SECRET_IDS:
            if not enabled.get(rid):
                enabled[rid] = True
                changed = True
            continue
        if rid == "openrouter":
            if not enabled.get("openrouter"):
                enabled["openrouter"] = True
                changed = True
            continue
        if rid == "groq":
            if not enabled.get("groq"):
                enabled["groq"] = True
                changed = True
            continue
        if rid == "opencode":
            if not enabled.get("direct"):
                enabled["direct"] = True
                changed = True
            for product in ("opencode-zen", "opencode-go"):
                if not toggles.get(product):
                    toggles[product] = True
                    changed = True
            continue
        if rid in RELAY_API_MAP:
            if not enabled.get("direct"):
                enabled["direct"] = True
                changed = True
            if not toggles.get(rid):
                toggles[rid] = True
                changed = True

    if changed:
        update_settings(
            enabled_providers=enabled,
            direct_provider_toggles=toggles,
        )
