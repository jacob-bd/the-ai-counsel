"""Shared OAuth helpers (intervals, User-Agent)."""

from __future__ import annotations

import asyncio
from typing import Optional

USER_AGENT = "the-ai-counsel/0.10.5"


def positive_seconds_to_ms(value: Optional[object], default_ms: int) -> int:
    try:
        sec = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default_ms
    if sec <= 0:
        return default_ms
    return int(sec * 1000)


async def sleep_ms(ms: int) -> None:
    await asyncio.sleep(max(0, ms) / 1000.0)
