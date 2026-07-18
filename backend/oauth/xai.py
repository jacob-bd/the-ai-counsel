"""xAI SuperGrok OAuth (RFC 8628 device code) — ported from relay-ai."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

import httpx

from .helpers import USER_AGENT, positive_seconds_to_ms, sleep_ms

CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
TOKEN_URL = "https://auth.x.ai/oauth2/token"
DEVICE_AUTHORIZATION_URL = "https://auth.x.ai/oauth2/device/code"
DEVICE_CODE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
SCOPE = "openid profile email offline_access grok-cli:access api:access"

DEVICE_CODE_DEFAULT_INTERVAL_MS = 5_000
DEVICE_CODE_MIN_INTERVAL_MS = 1_000
DEVICE_CODE_SLOW_DOWN_INCREMENT_MS = 5_000
DEVICE_CODE_DEFAULT_EXPIRES_MS = 5 * 60 * 1000
OAUTH_POLLING_SAFETY_MARGIN_MS = 3_000


def _auth_headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }


async def request_xai_device_code() -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            DEVICE_AUTHORIZATION_URL,
            headers=_auth_headers(),
            data={"client_id": CLIENT_ID, "scope": SCOPE},
        )
    if response.status_code >= 400:
        raise RuntimeError(
            f"xAI device code request failed ({response.status_code}): {response.text}"
        )
    data = response.json()
    if not data.get("device_code") or not data.get("user_code") or not data.get("verification_uri"):
        raise RuntimeError("xAI device code response is missing required fields")
    return data


async def poll_xai_device_code_token(
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
        DEVICE_CODE_MIN_INTERVAL_MS,
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        while now() * 1000 < deadline:
            response = await client.post(
                TOKEN_URL,
                headers=_auth_headers(),
                data={
                    "grant_type": DEVICE_CODE_GRANT_TYPE,
                    "client_id": CLIENT_ID,
                    "device_code": device["device_code"],
                },
            )
            if response.status_code < 400:
                return response.json()

            body: Dict[str, Any] = {}
            try:
                body = response.json()
            except Exception:
                pass
            error = body.get("error")
            remaining = max(0, deadline - now() * 1000)
            if error == "authorization_pending":
                await sleep(min(interval_ms + OAUTH_POLLING_SAFETY_MARGIN_MS, remaining))
                continue
            if error == "slow_down":
                interval_ms += DEVICE_CODE_SLOW_DOWN_INCREMENT_MS
                await sleep(min(interval_ms + OAUTH_POLLING_SAFETY_MARGIN_MS, remaining))
                continue
            raise RuntimeError(
                f"xAI device authorization failed{f': {error}' if error else ''}"
            )
    raise RuntimeError("xAI device authorization timed out")


async def refresh_xai_access_token(refresh_token: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            TOKEN_URL,
            headers=_auth_headers(),
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
            },
        )
    if response.status_code >= 400:
        raise RuntimeError(
            f"xAI token refresh failed ({response.status_code}): {response.text}"
        )
    return response.json()
