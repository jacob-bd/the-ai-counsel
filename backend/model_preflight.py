"""Lightweight model availability checks before expensive runs."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Iterable

from .council import query_model

logger = logging.getLogger(__name__)

PREFLIGHT_PROMPT = "Reply with OK."
DEFAULT_PREFLIGHT_TIMEOUT = 5.0

# ---------------------------------------------------------------------------
# Rate-limit retry configuration
# ---------------------------------------------------------------------------

# Maximum number of retry attempts for transient rate-limit errors.
PREFLIGHT_RATE_LIMIT_RETRIES = 2
# Base backoff delay (seconds) between retries; doubles each attempt.
PREFLIGHT_RATE_LIMIT_BACKOFF = 1.5
# Hard ceiling on total wall-clock time spent on a single model's preflight.
# Prevents a sustained congestion event from stalling the entire pass.
PREFLIGHT_MAX_WALL_SECONDS = 12.0


def _is_transient_rate_limit(status_code: int, message: str) -> bool:
    """Classify an error as a transient rate-limit.

    Match priority (most stable -> least stable):
      1. HTTP status code 429  (canonical rate-limit signal)
      2. HTTP status code 503  combined with Notion-specific body markers
      3. Substring match on the error message as a last-resort fallback

    Fallback substring set: "notion rate limit", "rate limit", "rate_limit",
    "429", "too many requests", "quota", "throttl".
    """
    if status_code == 429:
        return True
    body = (message or "").lower()
    if status_code == 503 and any(
        m in body for m in ("notion_429", "rate_limit", "rate limit", "fileimporterror")
    ):
        return True
    if status_code not in {200, 0} and any(
        m in body for m in ("notion rate limit", "rate_limit", "too many requests", "throttl", "quota")
    ):
        return True
    # Pure text match when there is no status code at all
    if status_code == 0 and any(
        m in body for m in (
            "notion rate limit", "rate limit", "rate_limit",
            "429", "too many requests", "quota", "throttl",
        )
    ):
        return True
    return False


def _extract_status_code(result: dict | None) -> int:
    """Pull the last HTTP status code out of a query_model result dict."""
    if not result:
        return 0
    timeline = result.get("debug_timeline") or []
    if timeline:
        return int(timeline[-1].get("status") or 0)
    return 0


@dataclass
class ModelPreflightResult:
    """Result of a preflight pass over selected models."""

    failures: list[dict[str, str]] = field(default_factory=list)
    timeouts: list[str] = field(default_factory=list)
    # Models that were rate-limited for the full retry budget but were not
    # counted as hard failures -- the run is allowed to proceed.
    rate_limited: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


def _dedupe_models(models: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for model in models:
        normalized = (model or "").strip()
        if not normalized:
            continue
        comp = normalized.lower()
        if comp in seen:
            continue
        seen.add(comp)
        unique.append(normalized)
    return unique


def _is_timeout_error(message: str) -> bool:
    text = (message or "").lower()
    return any(marker in text for marker in ("timeout", "timed out", "readtimeout", "connecttimeout"))


async def _preflight_one(model: str, timeout: float) -> tuple[str, str | None, bool, bool, int]:
    """Ping a single model once.

    Returns (model, error_message, timed_out, rate_limited, http_status_code).
    error_message is None on success.
    """
    messages = [{"role": "user", "content": PREFLIGHT_PROMPT}]
    try:
        result = await query_model(model, messages, timeout=timeout, temperature=0.0)
    except asyncio.TimeoutError:
        return model, None, True, False, 0
    except Exception as exc:
        message = str(exc) or repr(exc)
        if _is_timeout_error(message):
            return model, None, True, False, 0
        return model, message, False, _is_transient_rate_limit(0, message), 0

    if not result:
        return model, "Model returned empty or null response", False, False, 0

    status_code = _extract_status_code(result)

    if not result.get("error"):
        return model, None, False, False, status_code

    message = result.get("error_message", "Unknown model error")
    if _is_timeout_error(message):
        return model, None, True, False, status_code
    rate_limited = result.get("rate_limited", False) or _is_transient_rate_limit(status_code, message)
    return model, message, False, rate_limited, status_code


async def _preflight_one_with_retry(
    model: str,
    timeout: float,
) -> tuple[str, str | None, bool, bool]:
    """Ping a single model, retrying transient rate-limit errors with backoff.

    Returns (model, error_message, timed_out, still_rate_limited_after_retries).
    """
    wall_start = time.monotonic()
    delay = PREFLIGHT_RATE_LIMIT_BACKOFF
    last_error: str | None = None
    last_status: int = 0

    for attempt in range(PREFLIGHT_RATE_LIMIT_RETRIES + 1):
        elapsed = time.monotonic() - wall_start
        if elapsed >= PREFLIGHT_MAX_WALL_SECONDS:
            logger.warning(
                "preflight: wall-clock budget (%.1fs) exhausted for %s after %d attempt(s) "
                "-- treating as soft rate-limit",
                PREFLIGHT_MAX_WALL_SECONDS,
                model,
                attempt,
            )
            return model, last_error, False, True

        model_out, error, timed_out, rate_limited, status_code = await _preflight_one(model, timeout)
        last_error = error
        last_status = status_code

        if timed_out or not rate_limited:
            return model_out, error, timed_out, False

        if attempt < PREFLIGHT_RATE_LIMIT_RETRIES:
            remaining = PREFLIGHT_MAX_WALL_SECONDS - (time.monotonic() - wall_start)
            actual_delay = min(delay, max(0.0, remaining - timeout))
            if actual_delay > 0:
                logger.warning(
                    "preflight.rate_limited: model=%s attempt=%d/%d http_status=%s "
                    "-- retrying in %.2fs",
                    model,
                    attempt + 1,
                    PREFLIGHT_RATE_LIMIT_RETRIES + 1,
                    status_code or "unknown",
                    actual_delay,
                )
                await asyncio.sleep(actual_delay)
            delay *= 2

    elapsed_ms = int((time.monotonic() - wall_start) * 1000)
    logger.warning(
        "preflight.soft_fail.rate_limited: model=%s attempts=%d elapsed_ms=%d "
        "http_status=%s last_error_class=NotionRateLimit -- "
        "allowing run to proceed; Notion may throttle the actual request",
        model,
        PREFLIGHT_RATE_LIMIT_RETRIES + 1,
        elapsed_ms,
        last_status or "unknown",
    )
    return model, last_error, False, True


async def preflight_models(
    models: Iterable[str],
    timeout: float = DEFAULT_PREFLIGHT_TIMEOUT,
) -> ModelPreflightResult:
    """Ping selected models and report immediate non-timeout failures.

    Rate-limit errors are retried with exponential backoff up to
    PREFLIGHT_RATE_LIMIT_RETRIES times, bounded by PREFLIGHT_MAX_WALL_SECONDS.
    Persistent rate-limited models are soft-failed (run proceeds).
    Hard failures (auth, model-not-found, unreachable) remain blocking.
    """

    result = ModelPreflightResult()
    unique_models = _dedupe_models(models)
    if not unique_models:
        return result

    sem = asyncio.Semaphore(5)

    async def _preflight_with_sem(m: str):
        async with sem:
            return await _preflight_one_with_retry(m, timeout)

    checks = [_preflight_with_sem(model) for model in unique_models]
    for model, error, timed_out, still_rate_limited in await asyncio.gather(*checks):
        if timed_out:
            result.timeouts.append(model)
            logger.warning(
                "preflight.timeout: model=%s timeout=%.1fs -- will retry under full run timeout",
                model,
                timeout,
            )
        elif still_rate_limited:
            result.rate_limited.append(model)
        elif error:
            result.failures.append({"model": model, "error": error})

    return result


def build_preflight_error_message(result: ModelPreflightResult) -> str:
    """Build a user-facing error message for failed model preflight checks."""

    if result.ok:
        return ""

    details = "; ".join(
        f"{failure['model']}: {failure['error']}"
        for failure in result.failures
    )
    return (
        "Model preflight failed before starting. "
        "One or more selected models are not currently available: "
        f"{details}"
    )
