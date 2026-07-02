"""The AI Counsel backend package."""

import os
from collections.abc import MutableMapping


def sanitize_no_proxy_environment(
    environment: MutableMapping[str, str] | None = None,
) -> None:
    """Remove only IPv6 loopback entries that trigger httpx proxy parsing errors."""
    target = os.environ if environment is None else environment
    for name in ("no_proxy", "NO_PROXY"):
        raw_value = target.get(name)
        if not raw_value:
            continue
        entries = [entry.strip() for entry in raw_value.split(",") if entry.strip()]
        cleaned = [
            entry
            for entry in entries
            if entry.casefold() not in {"::1", "[::1]"}
            and not entry.casefold().startswith("[::1]:")
        ]
        target[name] = ",".join(cleaned)


sanitize_no_proxy_environment()
