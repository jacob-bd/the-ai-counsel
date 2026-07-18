"""In-memory OAuth device-code sessions (single-worker)."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, Optional

from ..credentials import set_oauth_credential
from ..settings import get_settings, update_settings
from . import github_copilot, openai_chatgpt, xai
from .types import tokens_to_stored_credential

logger = logging.getLogger(__name__)

OAUTH_PROVIDER_IDS = ("xai-oauth", "openai-oauth", "github-copilot")

_sessions: Dict[str, Dict[str, Any]] = {}


def _enable_provider(provider_id: str) -> None:
    settings = get_settings()
    enabled = dict(settings.enabled_providers or {})
    enabled[provider_id] = True
    update_settings(enabled_providers=enabled)


async def start_oauth_session(provider_id: str) -> Dict[str, Any]:
    if provider_id not in OAUTH_PROVIDER_IDS:
        raise ValueError(f"Unsupported OAuth provider: {provider_id}")

    session_id = str(uuid.uuid4())
    if provider_id == "xai-oauth":
        device = await xai.request_xai_device_code()
        info = {
            "user_code": device["user_code"],
            "verification_uri": device["verification_uri"],
            "verification_uri_complete": device.get("verification_uri_complete"),
            "expires_in": device.get("expires_in", 300),
            "device": device,
        }
    elif provider_id == "openai-oauth":
        device = await openai_chatgpt.request_openai_device_code()
        info = {
            "user_code": device["user_code"],
            "verification_uri": openai_chatgpt.open_ai_device_code_url(),
            "verification_uri_complete": None,
            "expires_in": device.get("expires_in", 300),
            "device": device,
        }
    else:
        device = await github_copilot.request_github_device_code()
        info = {
            "user_code": device["user_code"],
            "verification_uri": device["verification_uri"],
            "verification_uri_complete": device.get("verification_uri_complete"),
            "expires_in": device.get("expires_in", 900),
            "device": device,
        }

    session = {
        "provider_id": provider_id,
        "status": "pending",
        "error": None,
        "created_at": time.time(),
        "expires_in": info["expires_in"],
        **info,
    }
    _sessions[session_id] = session

    async def _poll() -> None:
        try:
            if provider_id == "xai-oauth":
                tokens = await xai.poll_xai_device_code_token(device)
                cred = tokens_to_stored_credential(tokens)
            elif provider_id == "openai-oauth":
                tokens, account_id = await openai_chatgpt.poll_openai_device_code_token(device)
                cred = tokens_to_stored_credential(tokens, account_id=account_id)
            else:
                tokens = await github_copilot.poll_github_device_code_token(device)
                provider_data = None
                if isinstance(tokens.get("account"), dict) and tokens["account"]:
                    provider_data = {"copilot": tokens["account"]}
                cred = tokens_to_stored_credential(tokens, provider_data=provider_data)
            set_oauth_credential(provider_id, cred)
            _enable_provider(provider_id)
            session["status"] = "complete"
        except Exception as exc:  # noqa: BLE001
            logger.exception("OAuth session %s failed", session_id)
            msg = str(exc)
            session["status"] = "expired" if "timed out" in msg.lower() else "error"
            session["error"] = msg

    session["task"] = asyncio.create_task(_poll())
    return {
        "session_id": session_id,
        "provider_id": provider_id,
        "user_code": info["user_code"],
        "verification_uri": info["verification_uri"],
        "verification_uri_complete": info.get("verification_uri_complete"),
        "expires_in": info["expires_in"],
        "status": "pending",
    }


def get_oauth_session_status(provider_id: str, session_id: str) -> Dict[str, Any]:
    session = _sessions.get(session_id)
    if not session or session.get("provider_id") != provider_id:
        return {"status": "error", "error": "Unknown or expired session"}
    return {
        "status": session["status"],
        "error": session.get("error"),
        "provider_id": provider_id,
        "session_id": session_id,
    }


def disconnect_oauth(provider_id: str) -> None:
    from ..credentials import delete_secret
    from ..credentials.ids import OAUTH_SECRET_IDS

    sid = OAUTH_SECRET_IDS.get(provider_id)
    if sid:
        delete_secret(sid)
    settings = get_settings()
    enabled = dict(settings.enabled_providers or {})
    enabled[provider_id] = False
    update_settings(enabled_providers=enabled)
