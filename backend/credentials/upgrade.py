"""One-time migration of plaintext settings.json secrets into the credential store."""

from __future__ import annotations

import logging
from typing import Any, Dict

from .ids import SETTINGS_FIELD_TO_SECRET_ID
from .store import get_secret, set_secret

logger = logging.getLogger(__name__)


def ensure_credentials_upgraded() -> bool:
    """Move inline settings secrets into the active credential store.

    Returns True if a migration ran.
    """
    from ..settings import get_settings, update_settings

    settings = get_settings()
    if getattr(settings, "credentials_migrated", False):
        return False

    data = settings.model_dump()
    moved: Dict[str, str] = {}
    for field, secret_id in SETTINGS_FIELD_TO_SECRET_ID.items():
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            # Prefer existing store value if already present.
            if not get_secret(secret_id):
                set_secret(secret_id, value.strip())
            moved[field] = None  # type: ignore[assignment]

    clears: Dict[str, Any] = {field: None for field in moved}
    clears["credentials_migrated"] = True
    if "credential_storage" not in data or not data.get("credential_storage"):
        clears["credential_storage"] = "file"
    update_settings(**clears)
    if moved:
        logger.info("Migrated %d secrets from settings.json into credential store", len(moved))
    return True
