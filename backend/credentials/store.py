"""Unified credential store facade (file vs OS keyring)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from . import file_backend, keyring_backend
from .availability import (
    get_availability as probe_availability,
    is_container_environment,
    probe_keyring,
)
from .ids import (
    ENV_OVERRIDES,
    KNOWN_SECRET_IDS,
    OAUTH_SECRET_IDS,
    SETTINGS_FIELD_TO_SECRET_ID,
)

logger = logging.getLogger(__name__)

_lock = asyncio.Lock()


def _preferred_mode() -> str:
    from ..settings import get_settings

    mode = getattr(get_settings(), "credential_storage", "file") or "file"
    return mode if mode in ("file", "keyring") else "file"


def get_effective_mode() -> str:
    """Mode used for reads/writes. Containers always use file."""
    if is_container_environment():
        return "file"
    preferred = _preferred_mode()
    if preferred == "keyring":
        ok, _ = probe_keyring()
        if not ok:
            # Fail closed for keyring preference without backend:
            # still try file for recovery reads.
            return "file"
    return preferred


def get_availability() -> Dict[str, Any]:
    avail = probe_availability()
    preferred = _preferred_mode()
    effective = get_effective_mode()
    reason = avail.get("unavailable_reason")
    if preferred == "keyring" and effective == "file" and is_container_environment():
        reason = (
            "OS keystore isn’t available in containers. "
            "Use file storage on the data volume."
        )
    elif preferred == "keyring" and effective == "file" and not avail.get("keyring"):
        reason = avail.get("unavailable_reason")
    show_reason = None
    if not avail.get("keyring") or (preferred == "keyring" and preferred != effective):
        show_reason = reason
    return {
        "file": True,
        "keyring": bool(avail.get("keyring")),
        "unavailable_reason": show_reason,
        "in_container": is_container_environment(),
        "preferred": preferred,
        "effective": effective,
    }


def _backend_for(mode: str):
    return keyring_backend if mode == "keyring" else file_backend


def _disabled_secret_ids() -> set:
    try:
        from ..settings import get_settings

        raw = getattr(get_settings(), "disabled_secret_ids", None) or []
        return {str(x) for x in raw if str(x).strip()}
    except Exception:
        return set()


def is_secret_disabled(secret_id: str) -> bool:
    return secret_id in _disabled_secret_ids()


def _set_secret_disabled(secret_id: str, disabled: bool) -> None:
    """Persist Disconnect/reconnect override (so env vars cannot revive a cleared key)."""
    try:
        from ..settings import get_settings, update_settings

        current = list(getattr(get_settings(), "disabled_secret_ids", None) or [])
        if disabled:
            if secret_id in current:
                return
            update_settings(disabled_secret_ids=[*current, secret_id])
            return
        if secret_id not in current:
            return
        update_settings(disabled_secret_ids=[x for x in current if x != secret_id])
    except Exception:
        logger.exception("Failed to update disabled_secret_ids for %s", secret_id)


def get_secret(secret_id: str) -> Optional[str]:
    if is_secret_disabled(secret_id):
        return None

    # Prefer stored credentials (Settings UI / credentials.json / keyring) so
    # Disconnect + save-new-key works even when a shell env var is still set.
    mode = get_effective_mode()
    value = _backend_for(mode).get_secret(secret_id)
    if value:
        return value
    # Recovery: if preferred keyring but empty, try file once.
    if _preferred_mode() == "keyring" and mode == "file":
        value = file_backend.get_secret(secret_id)
        if value:
            return value
    if mode == "keyring":
        value = file_backend.get_secret(secret_id)
        if value:
            return value

    env_name = ENV_OVERRIDES.get(secret_id)
    if env_name:
        env_val = os.getenv(env_name, "").strip()
        if env_val:
            return env_val
    return None


def has_secret(secret_id: str) -> bool:
    return bool(get_secret(secret_id))


def set_secret(secret_id: str, value: str) -> None:
    if not value:
        delete_secret(secret_id)
        return
    # Re-enable if user saved a new key after Disconnect.
    _set_secret_disabled(secret_id, False)
    # Always write to effective backend (file in containers even if preference is keyring).
    mode = get_effective_mode()
    _backend_for(mode).set_secret(secret_id, value)


def delete_secret(secret_id: str) -> None:
    # Delete from both backends to avoid dual-home leftovers after migrate.
    file_backend.delete_secret(secret_id)
    try:
        keyring_backend.delete_secret(secret_id)
    except Exception:
        pass
    # Also ignore env overrides until a new key is saved (Disconnect UX).
    _set_secret_disabled(secret_id, True)


def get_api_key(provider: str) -> str:
    """Convenience: api:{provider} or settings field name without prefix."""
    secret_id = provider if provider.startswith("api:") else f"api:{provider}"
    return get_secret(secret_id) or ""


# UI / PROVIDERS ids that share a single credential-store secret.
_PROVIDER_ID_TO_STORE: Dict[str, str] = {
    "opencode-zen": "opencode",
    "opencode-go": "opencode",
}


def resolve_api_key(provider_id: str, provided: Optional[str] = None) -> str:
    """Resolve an API key for settings Retest endpoints.

    Preference: non-empty request value → credential store → legacy settings.json field.
    """
    if provided is not None and str(provided).strip():
        return str(provided).strip()

    store_id = _PROVIDER_ID_TO_STORE.get(provider_id, provider_id)
    stored = get_api_key(store_id)
    if stored:
        return stored

    # Legacy inline settings (pre-credential-store installs).
    try:
        from ..settings import get_settings

        field = {
            "opencode-zen": "opencode_api_key",
            "opencode-go": "opencode_api_key",
        }.get(provider_id, f"{provider_id}_api_key")
        legacy = getattr(get_settings(), field, None)
        if legacy and str(legacy).strip():
            return str(legacy).strip()
    except Exception:
        pass
    return ""


def get_oauth_credential(provider_id: str) -> Optional[Dict[str, Any]]:
    sid = OAUTH_SECRET_IDS.get(provider_id)
    if not sid:
        return None
    raw = get_secret(sid)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("type") != "oauth":
        return None
    return data


def set_oauth_credential(provider_id: str, credential: Dict[str, Any]) -> None:
    sid = OAUTH_SECRET_IDS.get(provider_id)
    if not sid:
        raise ValueError(f"Unknown OAuth provider: {provider_id}")
    set_secret(sid, json.dumps(credential))


def export_all_secrets() -> Dict[str, str]:
    mode = get_effective_mode()
    return _backend_for(mode).list_present(KNOWN_SECRET_IDS)


def import_secrets(secrets: Dict[str, str], *, replace_existing: bool = True) -> List[str]:
    imported: List[str] = []
    for sid, value in secrets.items():
        if sid not in KNOWN_SECRET_IDS:
            continue
        if not value:
            continue
        if not replace_existing and has_secret(sid):
            continue
        set_secret(sid, value)
        imported.append(sid)
    return imported


def wipe_all_secrets() -> None:
    file_backend.wipe(KNOWN_SECRET_IDS)
    try:
        keyring_backend.wipe(KNOWN_SECRET_IDS)
    except Exception:
        logger.exception("Failed wiping keyring secrets")


def disconnect_all_credentials() -> Dict[str, Any]:
    """Remove every stored API key / OAuth token and disable provider sources.

    Also marks all known secret IDs as disabled so process env vars cannot
    revive them until the user saves a new key. Used by Settings → Backup & Reset.
    """
    from ..settings import DEFAULT_DIRECT_PROVIDER_TOGGLES, get_settings, update_settings

    before = 0
    for sid in KNOWN_SECRET_IDS:
        # Count while disabled list may still allow reads.
        if file_backend.get_secret(sid):
            before += 1
            continue
        try:
            if keyring_backend.get_secret(sid):
                before += 1
        except Exception:
            pass

    wipe_all_secrets()

    settings = get_settings()
    enabled = {
        "openrouter": False,
        "ollama": False,
        "groq": False,
        "direct": False,
        "custom": False,
        "xai-oauth": False,
        "openai-oauth": False,
        "github-copilot": False,
    }
    # Preserve any extra keys with False.
    for key in (settings.enabled_providers or {}):
        enabled.setdefault(key, False)
        enabled[key] = False

    toggles = {**DEFAULT_DIRECT_PROVIDER_TOGGLES}
    for key in (settings.direct_provider_toggles or {}):
        toggles[key] = False

    update_settings(
        disabled_secret_ids=list(KNOWN_SECRET_IDS),
        enabled_providers=enabled,
        direct_provider_toggles=toggles,
        custom_endpoint_name="",
        custom_endpoint_url="",
    )
    return {"cleared": before, "disabled_secret_ids": list(KNOWN_SECRET_IDS)}


async def migrate_storage_mode(target: str) -> Dict[str, Any]:
    """Move all secrets to target backend. Atomic enough: verify then delete source."""
    if target not in ("file", "keyring"):
        raise ValueError("mode must be 'file' or 'keyring'")

    avail = probe_availability()
    if target == "keyring" and not avail.get("keyring"):
        raise RuntimeError(
            avail.get("unavailable_reason") or "OS keystore is not available"
        )
    if is_container_environment() and target == "keyring":
        raise RuntimeError(
            "OS keystore isn’t available in containers. Use file storage on the data volume."
        )

    async with _lock:
        from ..settings import get_settings, update_settings

        source = get_effective_mode()
        # When preferred is keyring but effective is file, still load from file.
        source_backend = _backend_for(source)
        if _preferred_mode() == "keyring" and source == "file":
            secrets = file_backend.list_present(KNOWN_SECRET_IDS)
        else:
            secrets = source_backend.list_present(KNOWN_SECRET_IDS)

        # Also pull from the other backend if dual-homed.
        other = file_backend if source == "keyring" else keyring_backend
        for sid, val in other.list_present(KNOWN_SECRET_IDS).items():
            secrets.setdefault(sid, val)

        if not secrets:
            update_settings(credential_storage=target)
            return {"mode": target, "moved": 0, "ids": []}

        target_backend = _backend_for(target)
        written: List[str] = []
        try:
            for sid, value in secrets.items():
                target_backend.set_secret(sid, value)
                read_back = target_backend.get_secret(sid)
                if read_back != value:
                    raise RuntimeError(f"Verify failed for {sid}")
                written.append(sid)
        except Exception:
            # Leave source intact; best-effort cleanup of partial target writes.
            for sid in written:
                try:
                    target_backend.delete_secret(sid)
                except Exception:
                    pass
            raise

        # Delete from every backend except the migration target.
        for sid in written:
            if source != target:
                try:
                    source_backend.delete_secret(sid)
                except Exception:
                    logger.exception("Failed deleting %s from source after migrate", sid)
            if other is not _backend_for(target):
                try:
                    if other.get_secret(sid):
                        other.delete_secret(sid)
                except Exception:
                    pass

        update_settings(credential_storage=target)
        return {"mode": target, "moved": len(written), "ids": written}


def secret_id_for_settings_field(field: str) -> Optional[str]:
    return SETTINGS_FIELD_TO_SECRET_ID.get(field)


def apply_settings_secret_updates(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Route API key fields from a settings update into the credential store.

    Returns a copy of updates with secret fields removed (so they are not
    re-inlined into settings.json). Empty string clears the secret.
    """
    cleaned = dict(updates)
    for field, secret_id in SETTINGS_FIELD_TO_SECRET_ID.items():
        if field not in cleaned:
            continue
        value = cleaned.pop(field)
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            # Clears store + disables env override for this secret id.
            delete_secret(secret_id)
        elif isinstance(value, str):
            set_secret(secret_id, value.strip())
    return cleaned
