"""ChatGPT Plus/Pro OAuth (deviceauth + PKCE) — ported from relay-ai."""

from __future__ import annotations

import base64
import json
import time
from typing import Any, Callable, Dict, Optional, Tuple

import httpx

from .helpers import USER_AGENT, positive_seconds_to_ms, sleep_ms

CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
ISSUER = "https://auth.openai.com"
DEVICE_CODE_DEFAULT_EXPIRES_MS = 5 * 60 * 1000
OAUTH_POLLING_SAFETY_MARGIN_MS = 3_000


def open_ai_device_code_url() -> str:
    return f"{ISSUER}/codex/device"


def extract_openai_account_id(tokens: Dict[str, Any]) -> Optional[str]:
    token = tokens.get("id_token") or tokens.get("access_token")
    if not token:
        return None
    parts = str(token).split(".")
    if len(parts) != 3:
        return None
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = payload.replace("-", "+").replace("_", "/")
        claims = json.loads(base64.b64decode(payload).decode("utf-8"))
        return (
            claims.get("chatgpt_account_id")
            or (claims.get("https://api.openai.com/auth") or {}).get("chatgpt_account_id")
            or ((claims.get("organizations") or [{}])[0] or {}).get("id")
        )
    except Exception:
        return None


async def request_openai_device_code() -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{ISSUER}/api/accounts/deviceauth/usercode",
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            json={"client_id": CLIENT_ID},
        )
    if response.status_code >= 400:
        raise RuntimeError("Failed to initiate OpenAI device authorization")
    return response.json()


async def poll_openai_device_code_token(
    device_data: Dict[str, Any],
    *,
    sleep: Callable[[int], Any] = sleep_ms,
    now: Callable[[], float] = time.time,
) -> Tuple[Dict[str, Any], Optional[str]]:
    interval_ms = max((int(device_data.get("interval") or 5) or 5), 1) * 1000
    deadline = now() * 1000 + positive_seconds_to_ms(
        device_data.get("expires_in"), DEVICE_CODE_DEFAULT_EXPIRES_MS
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        while now() * 1000 < deadline:
            response = await client.post(
                f"{ISSUER}/api/accounts/deviceauth/token",
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": USER_AGENT,
                },
                json={
                    "device_auth_id": device_data["device_auth_id"],
                    "user_code": device_data["user_code"],
                },
            )
            if response.status_code < 400:
                data = response.json()
                token_response = await client.post(
                    f"{ISSUER}/oauth/token",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    data={
                        "grant_type": "authorization_code",
                        "code": data["authorization_code"],
                        "redirect_uri": f"{ISSUER}/deviceauth/callback",
                        "client_id": CLIENT_ID,
                        "code_verifier": data["code_verifier"],
                    },
                )
                if token_response.status_code >= 400:
                    raise RuntimeError(
                        f"OpenAI token exchange failed ({token_response.status_code})"
                    )
                tokens = token_response.json()
                return tokens, extract_openai_account_id(tokens)

            if response.status_code not in (403, 404):
                raise RuntimeError(
                    f"OpenAI device authorization failed ({response.status_code})"
                )

            remaining = max(0, deadline - now() * 1000)
            await sleep(min(interval_ms + OAUTH_POLLING_SAFETY_MARGIN_MS, remaining))

    raise RuntimeError("OpenAI device authorization timed out")


async def refresh_openai_access_token(refresh_token: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{ISSUER}/oauth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
            },
        )
    if response.status_code >= 400:
        raise RuntimeError(
            f"OpenAI token refresh failed ({response.status_code}): {response.text}"
        )
    return response.json()
