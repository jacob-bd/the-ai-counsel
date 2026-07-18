"""Plaintext credentials.json backend (mode 0o600 on Unix)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

CREDENTIALS_FILE = Path(__file__).parent.parent.parent / "data" / "credentials.json"


def _read_all() -> Dict[str, str]:
    if not CREDENTIALS_FILE.exists():
        return {}
    try:
        with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items() if v is not None and str(v)}
    except Exception:
        logger.exception("Failed to read %s", CREDENTIALS_FILE)
        return {}


def _write_all(data: Dict[str, str]) -> None:
    CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write via temp file in same directory.
    fd, tmp_path = tempfile.mkstemp(
        dir=str(CREDENTIALS_FILE.parent),
        prefix=".credentials-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, CREDENTIALS_FILE)
        try:
            os.chmod(CREDENTIALS_FILE, 0o600)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def get_secret(secret_id: str) -> Optional[str]:
    return _read_all().get(secret_id)


def set_secret(secret_id: str, value: str) -> None:
    data = _read_all()
    data[secret_id] = value
    _write_all(data)


def delete_secret(secret_id: str) -> None:
    data = _read_all()
    if secret_id in data:
        del data[secret_id]
        _write_all(data)


def list_present(secret_ids: list[str]) -> Dict[str, str]:
    data = _read_all()
    return {sid: data[sid] for sid in secret_ids if sid in data}


def wipe(secret_ids: list[str]) -> None:
    data = _read_all()
    changed = False
    for sid in secret_ids:
        if sid in data:
            del data[sid]
            changed = True
    if changed:
        _write_all(data)
