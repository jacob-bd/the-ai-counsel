"""OAuth credential blob shape (compatible with relay-ai / OpenCode)."""

from __future__ import annotations

import base64
import json
import time
from typing import Any, Dict, Optional

OAUTH_REFRESH_SKEW_MS = 120_000


def tokens_to_stored_credential(
    tokens: Dict[str, Any],
    existing_refresh: Optional[str] = None,
    account_id: Optional[str] = None,
    provider_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    expires_in = tokens.get("expires_in")
    try:
        expires_sec = int(expires_in) if expires_in is not None else 3600
    except (TypeError, ValueError):
        expires_sec = 3600
    cred: Dict[str, Any] = {
        "type": "oauth",
        "access": tokens.get("access_token") or "",
        "refresh": tokens.get("refresh_token") or existing_refresh or "",
        "expires": int(time.time() * 1000) + expires_sec * 1000,
    }
    if account_id:
        cred["accountId"] = account_id
    if provider_data:
        cred["providerData"] = provider_data
    return cred


def oauth_credential_needs_refresh(
    cred: Dict[str, Any], skew_ms: int = OAUTH_REFRESH_SKEW_MS
) -> bool:
    try:
        expires = int(cred.get("expires") or 0)
    except (TypeError, ValueError):
        return True
    return expires <= int(time.time() * 1000) + max(0, skew_ms)


def access_token_is_expiring(token: Optional[str], skew_ms: int = OAUTH_REFRESH_SKEW_MS) -> bool:
    if not token:
        return False
    parts = token.split(".")
    if len(parts) < 2:
        return False
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = payload.replace("-", "+").replace("_", "/")
        claims = json.loads(base64.b64decode(payload).decode("utf-8"))
        exp = claims.get("exp")
        if not isinstance(exp, (int, float)):
            return False
        return exp * 1000 <= time.time() * 1000 + max(0, skew_ms)
    except Exception:
        return False


def parse_stored_oauth_credential(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw or not raw.strip().startswith("{"):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if (
        isinstance(parsed, dict)
        and parsed.get("type") == "oauth"
        and isinstance(parsed.get("access"), str)
        and isinstance(parsed.get("refresh"), str)
        and isinstance(parsed.get("expires"), (int, float))
    ):
        return parsed
    return None
