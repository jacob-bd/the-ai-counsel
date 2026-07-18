"""GitHub Copilot OAuth (device code → ghu_ → session token) — ported from relay-ai."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict

import httpx

from .helpers import USER_AGENT, positive_seconds_to_ms, sleep_ms

CLIENT_ID = "Iv1.b507a08c87ecfe98"
DEVICE_CODE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"
COPILOT_USER_URL = "https://api.github.com/copilot_internal/user"
SCOPE = "copilot"

DEVICE_CODE_DEFAULT_INTERVAL_MS = 5_000
DEVICE_CODE_DEFAULT_EXPIRES_MS = 15 * 60 * 1000
OAUTH_POLLING_SAFETY_MARGIN_MS = 1_000

# VS Code / Copilot SKUs treated as Free or Student (manual model pick restricted).
FREE_COPILOT_SKUS = frozenset(
    {
        "free_limited_copilot",
        "free_educational_quota",
        "no_auth_limited_copilot",
    }
)


def _common_headers() -> Dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": USER_AGENT,
    }


def classify_copilot_account(user: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize /copilot_internal/user into a small non-secret plan summary."""
    sku = str(user.get("access_type_sku") or "").strip()
    plan = str(user.get("copilot_plan") or "").strip()
    sku_l = sku.lower()
    plan_l = plan.lower()
    is_free = sku_l in FREE_COPILOT_SKUS or plan_l == "free"
    return {
        "login": user.get("login"),
        "access_type_sku": sku or None,
        "copilot_plan": plan or None,
        "is_free_plan": bool(is_free),
    }


async def fetch_copilot_account(ghu_token: str) -> Dict[str, Any]:
    """GET plan/SKU for the GitHub user (Bearer = ghu_ refresh token)."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            COPILOT_USER_URL,
            headers={
                "Authorization": f"Bearer {ghu_token}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
                "Editor-Version": "vscode/1.85.1",
                "X-Github-Api-Version": "2025-04-01",
            },
        )
    if response.status_code >= 400:
        raise RuntimeError(
            f"GitHub Copilot account lookup failed ({response.status_code}): {response.text}"
        )
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("GitHub Copilot account lookup returned invalid JSON")
    return classify_copilot_account(data)


async def request_github_device_code() -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            DEVICE_CODE_URL,
            headers=_common_headers(),
            data={"client_id": CLIENT_ID, "scope": SCOPE},
        )
    if response.status_code >= 400:
        raise RuntimeError(
            f"GitHub device code request failed ({response.status_code}): {response.text}"
        )
    data = response.json()
    if not data.get("device_code") or not data.get("user_code") or not data.get("verification_uri"):
        raise RuntimeError("GitHub device code response is missing required fields")
    return data


async def exchange_for_copilot_token(ghu_token: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            COPILOT_TOKEN_URL,
            headers={
                "Authorization": f"Bearer {ghu_token}",
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
        )
    if response.status_code >= 400:
        raise RuntimeError(
            f"GitHub Copilot token exchange failed ({response.status_code}): {response.text}"
        )
    data = response.json()
    if not data.get("token"):
        raise RuntimeError(
            "GitHub Copilot token exchange response missing token — is Copilot subscription active?"
        )
    expires_in = 1800
    if data.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(
                str(data["expires_at"]).replace("Z", "+00:00")
            )
            expires_ms = expires_at.timestamp() * 1000 - time.time() * 1000
            if expires_ms > 0:
                expires_in = int(expires_ms / 1000)
        except Exception:
            pass
    account: Dict[str, Any] = {}
    try:
        account = await fetch_copilot_account(ghu_token)
    except Exception:
        # Session token still usable even if plan lookup fails.
        pass
    result = {"access_token": data["token"], "expires_in": expires_in}
    if account:
        result["account"] = account
    return result


async def refresh_github_copilot_token(ghu_token: str) -> Dict[str, Any]:
    copilot = await exchange_for_copilot_token(ghu_token)
    return {**copilot, "refresh_token": ghu_token}


async def poll_github_device_code_token(
    device: Dict[str, Any],
    *,
    sleep: Callable[[int], Any] = sleep_ms,
    now: Callable[[], float] = time.time,
) -> Dict[str, Any]:
    deadline = now() * 1000 + positive_seconds_to_ms(
        device.get("expires_in"), DEVICE_CODE_DEFAULT_EXPIRES_MS
    )
    interval_ms = max(
        positive_seconds_to_ms(device.get("interval"), DEVICE_CODE_DEFAULT_INTERVAL_MS),
        1_000,
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        while now() * 1000 < deadline:
            response = await client.post(
                TOKEN_URL,
                headers=_common_headers(),
                data={
                    "client_id": CLIENT_ID,
                    "device_code": device["device_code"],
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )
            body = response.json() if response.content else {}
            error = body.get("error")
            if not error and body.get("access_token"):
                ghu_token = body["access_token"]
                copilot = await exchange_for_copilot_token(ghu_token)
                return {
                    "access_token": copilot["access_token"],
                    "refresh_token": ghu_token,
                    "expires_in": copilot.get("expires_in"),
                }
            remaining = max(0, deadline - now() * 1000)
            if error == "authorization_pending":
                await sleep(min(interval_ms + OAUTH_POLLING_SAFETY_MARGIN_MS, remaining))
                continue
            if error == "slow_down":
                interval_ms += 5_000
                await sleep(min(interval_ms + OAUTH_POLLING_SAFETY_MARGIN_MS, remaining))
                continue
            if error == "expired_token":
                raise RuntimeError("GitHub device code expired — please Connect again")
            raise RuntimeError(
                f"GitHub device authorization failed{f': {error}' if error else ''}"
            )
    raise RuntimeError("GitHub device authorization timed out")
