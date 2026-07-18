"""OS keyring backend with Windows credential chunking (relay-ai compatible)."""

from __future__ import annotations

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

SERVICE = "the-ai-counsel"
KEYRING_CHUNK_PREFIX = "__relay_chunked__:"
KEYRING_CHUNK_SIZE = 1200


def _entry(account: str):
    import keyring

    return keyring


def get_secret(secret_id: str) -> Optional[str]:
    import keyring

    try:
        value = keyring.get_password(SERVICE, secret_id)
    except Exception:
        logger.exception("keyring get failed for %s", secret_id)
        return None
    if value is None:
        return None
    if value.startswith(KEYRING_CHUNK_PREFIX):
        try:
            count = int(value[len(KEYRING_CHUNK_PREFIX) :])
        except ValueError:
            return value
        parts = []
        for i in range(count):
            chunk = keyring.get_password(SERVICE, f"{secret_id}::chunk::{i}")
            if chunk is None:
                return None
            parts.append(chunk)
        return "".join(parts)
    return value


def set_secret(secret_id: str, value: str) -> None:
    import keyring

    # Clear previous chunks first.
    delete_secret(secret_id)
    if len(value) <= KEYRING_CHUNK_SIZE:
        keyring.set_password(SERVICE, secret_id, value)
        return
    chunks = [
        value[i : i + KEYRING_CHUNK_SIZE]
        for i in range(0, len(value), KEYRING_CHUNK_SIZE)
    ]
    for i, chunk in enumerate(chunks):
        keyring.set_password(SERVICE, f"{secret_id}::chunk::{i}", chunk)
    keyring.set_password(SERVICE, secret_id, f"{KEYRING_CHUNK_PREFIX}{len(chunks)}")


def delete_secret(secret_id: str) -> None:
    import keyring
    from keyring.errors import PasswordDeleteError

    try:
        existing = keyring.get_password(SERVICE, secret_id)
    except Exception:
        existing = None
    if existing and existing.startswith(KEYRING_CHUNK_PREFIX):
        try:
            count = int(existing[len(KEYRING_CHUNK_PREFIX) :])
        except ValueError:
            count = 0
        for i in range(count):
            try:
                keyring.delete_password(SERVICE, f"{secret_id}::chunk::{i}")
            except PasswordDeleteError:
                pass
            except Exception:
                pass
    try:
        keyring.delete_password(SERVICE, secret_id)
    except PasswordDeleteError:
        pass
    except Exception:
        pass


def list_present(secret_ids: list[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for sid in secret_ids:
        val = get_secret(sid)
        if val:
            out[sid] = val
    return out


def wipe(secret_ids: list[str]) -> None:
    for sid in secret_ids:
        delete_secret(sid)
