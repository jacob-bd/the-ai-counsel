"""OAuth token refresh with in-flight deduplication."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from ..credentials import get_oauth_credential, set_oauth_credential
from . import github_copilot, openai_chatgpt, xai
from .types import (
    access_token_is_expiring,
    oauth_credential_needs_refresh,
    tokens_to_stored_credential,
)

logger = logging.getLogger(__name__)

_inflight: Dict[str, asyncio.Task] = {}
_lock = asyncio.Lock()


async def _do_refresh(provider_id: str, cred: Dict[str, Any]) -> Dict[str, Any]:
    refresh_token = cred.get("refresh") or ""
    if not refresh_token:
        raise RuntimeError(f"{provider_id}: missing refresh token — reconnect required")

    if provider_id == "xai-oauth":
        tokens = await xai.refresh_xai_access_token(refresh_token)
    elif provider_id == "openai-oauth":
        tokens = await openai_chatgpt.refresh_openai_access_token(refresh_token)
    elif provider_id == "github-copilot":
        tokens = await github_copilot.refresh_github_copilot_token(refresh_token)
    else:
        raise ValueError(f"Unknown OAuth provider: {provider_id}")

    provider_data = dict(cred.get("providerData") or {})
    account = tokens.get("account")
    if isinstance(account, dict) and account:
        provider_data["copilot"] = account
    updated = tokens_to_stored_credential(
        tokens,
        existing_refresh=refresh_token,
        account_id=cred.get("accountId"),
        provider_data=provider_data or None,
    )
    # Preserve accountId if refresh didn't yield a new one.
    if not updated.get("accountId") and cred.get("accountId"):
        updated["accountId"] = cred["accountId"]
    set_oauth_credential(provider_id, updated)
    return updated


async def get_valid_access_token(provider_id: str) -> str:
    """Return a fresh access token, refreshing if needed (single-flight)."""
    cred = get_oauth_credential(provider_id)
    if not cred:
        raise RuntimeError(f"{provider_id} is not connected")

    needs = oauth_credential_needs_refresh(cred) or access_token_is_expiring(
        cred.get("access")
    )
    if not needs:
        return cred["access"]

    async with _lock:
        existing = _inflight.get(provider_id)
        if existing is None:
            existing = asyncio.create_task(_do_refresh(provider_id, cred))
            _inflight[provider_id] = existing

    try:
        updated = await existing
        return updated["access"]
    except Exception:
        # Fall back to unexpired access if still valid.
        cred = get_oauth_credential(provider_id) or cred
        if cred.get("access") and not oauth_credential_needs_refresh(cred):
            logger.warning("%s refresh failed; using still-valid access token", provider_id)
            return cred["access"]
        raise
    finally:
        async with _lock:
            if _inflight.get(provider_id) is existing:
                _inflight.pop(provider_id, None)
