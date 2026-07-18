"""Detect whether OS keyring is usable (never in containers)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def is_container_environment() -> bool:
    if os.environ.get("LLM_COUNCIL_IN_CONTAINER", "").strip() in ("1", "true", "yes"):
        return True
    if Path("/.dockerenv").exists():
        return True
    try:
        cgroup = Path("/proc/1/cgroup")
        if cgroup.exists():
            text = cgroup.read_text(encoding="utf-8", errors="ignore")
            if "docker" in text or "containerd" in text or "kubepods" in text:
                return True
    except OSError:
        pass
    return False


def probe_keyring() -> Tuple[bool, Optional[str]]:
    """Return (available, reason_if_not). Never raises."""
    if is_container_environment():
        return False, (
            "OS keystore isn’t available in containers. "
            "Use file storage on the data volume."
        )
    try:
        import keyring
        from keyring.errors import KeyringError

        # Probe without persisting secrets.
        kr = keyring.get_keyring()
        name = type(kr).__name__.lower()
        if "fail" in name or "null" in name or "chainer" in name:
            # Chainer may still work; try a get.
            pass
        try:
            keyring.get_password("the-ai-counsel-probe", "probe")
        except KeyringError as exc:
            return False, f"OS keystore unavailable: {exc}"
        except Exception as exc:  # noqa: BLE001 — probe must never crash
            msg = str(exc).lower()
            if "secret service" in msg or "dbus" in msg or "daemon" in msg:
                return False, "Linux Secret Service is not available (no session agent)."
            if "denied" in msg or "locked" in msg or "cancelled" in msg:
                return False, "Keychain access was denied or the keychain is locked."
            return False, f"OS keystore unavailable: {exc}"
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, f"OS keystore module error: {exc}"


def get_availability() -> Dict[str, Any]:
    keyring_ok, reason = probe_keyring()
    return {
        "file": True,
        "keyring": keyring_ok,
        "unavailable_reason": None if keyring_ok else reason,
        "in_container": is_container_environment(),
    }
