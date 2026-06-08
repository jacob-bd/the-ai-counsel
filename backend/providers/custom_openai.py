"""Custom OpenAI-compatible endpoint provider."""

import asyncio
import logging
import os
import random
import time
import httpx
from typing import List, Dict, Any
from .base import LLMProvider
from .temperature import add_temperature_if_supported
from ..settings import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Runtime 429 retry configuration (text-only and attachment calls)
# ---------------------------------------------------------------------------

# Maximum retries for transient 429/rate-limit responses during any query.
_DEFAULT_RATE_LIMIT_MAX_RETRIES = 2
# Base backoff delay (seconds); each retry doubles this (plus jitter).
_DEFAULT_RATE_LIMIT_BASE_DELAY = 1.0
# Jitter ceiling added to each backoff interval (seconds).
_DEFAULT_RATE_LIMIT_JITTER = 0.5

# Semaphore to serialize attachment uploads across provider instances
_ATTACHMENT_UPLOAD_SEMAPHORE = asyncio.Semaphore(1)

def _is_rate_limited(status_code: int, response_text: str) -> bool:
    """Return True when the response indicates a transient rate-limit.

    Priority order:
      1. HTTP status code 429 (canonical rate-limit status)
      2. HTTP status code 503 combined with Notion-specific markers
      3. Substring match on the response body as a last-resort fallback

    This ordering ensures upstream wording changes do not silently break
    detection -- the status code is the stable signal.
    """
    if status_code == 429:
        return True
    body = (response_text or "").lower()
    if status_code == 503 and any(
        m in body for m in ("notion_429", "rate_limit", "rate limit", "fileimporterror")
    ):
        return True
    # Last-resort substring match for error messages surfaced as HTTP 200
    # (e.g. Notion2API wraps some errors inside a 200 payload).
    if status_code not in {200, 0} and any(
        m in body for m in ("notion rate limit", "rate_limit", "too many requests", "throttl", "quota")
    ):
        return True
    # Pure text match when there is no status code at all (e.g. raw exception text fallback)
    if status_code == 0 and any(
        m in body for m in (
            "notion rate limit", "rate limit", "rate_limit",
            "429", "too many requests", "quota", "throttl",
        )
    ):
        return True
    return False


def _is_auth_error(status_code: int) -> bool:
    return status_code in {401, 403}


def _is_not_found(status_code: int) -> bool:
    return status_code == 404


class CustomOpenAIProvider(LLMProvider):
    """Provider for any OpenAI-compatible API endpoint."""

    def _get_config(self) -> tuple[str, str, str]:
        """Get custom endpoint configuration."""
        settings = get_settings()
        name = settings.custom_endpoint_name or "Custom"
        url = settings.custom_endpoint_url or ""
        api_key = settings.custom_endpoint_api_key or ""
        return name, url, api_key

    def _is_attachment_rate_limit(self, status_code: int, response_text: str) -> bool:
        """Legacy attachment-specific rate-limit check (delegates to shared helper)."""
        return _is_rate_limited(status_code, response_text)

    def _rate_limit_retry_config(self) -> tuple[int, float, float]:
        """Return (max_retries, base_delay_s, jitter_s) for text-only rate-limit backoff."""
        settings = get_settings()
        try:
            max_retries = max(0, int(getattr(
                settings, "rate_limit_max_retries",
                os.getenv("LLM_COUNCIL_RATE_LIMIT_MAX_RETRIES", str(_DEFAULT_RATE_LIMIT_MAX_RETRIES))
            )))
        except (TypeError, ValueError):
            max_retries = _DEFAULT_RATE_LIMIT_MAX_RETRIES
        try:
            base_delay = max(0.0, float(getattr(
                settings, "rate_limit_base_delay_seconds",
                os.getenv("LLM_COUNCIL_RATE_LIMIT_BASE_DELAY_SECONDS", str(_DEFAULT_RATE_LIMIT_BASE_DELAY))
            )))
        except (TypeError, ValueError):
            base_delay = _DEFAULT_RATE_LIMIT_BASE_DELAY
        return max_retries, base_delay, _DEFAULT_RATE_LIMIT_JITTER

    def _is_notion_attachment_endpoint(self, name: str, base_url: str) -> bool:
        """True when the custom endpoint is Notion2API and needs upload throttling."""
        name_marker = (name or "").lower()
        url_marker = (base_url or "").lower()
        if "notion" in name_marker or "notion2api" in name_marker:
            return True
        return "notion" in url_marker or "notion2api" in url_marker

    def _supports_attachments(self, name: str | None = None, base_url: str | None = None) -> bool:
        """True when the custom endpoint is configured to accept attachment payloads."""
        if name is None or base_url is None:
            name, base_url, _ = self._get_config()
        settings = get_settings()
        return bool(getattr(settings, "custom_endpoint_supports_attachments", False))

    def _attachment_retry_config(self) -> tuple[int, float]:
        """Return (max_retries, base_delay) for attachment rate-limit backoff."""
        settings = get_settings()
        try:
            max_attempts = max(1, int(getattr(
                settings, "attachment_max_attempts",
                os.getenv("LLM_COUNCIL_ATTACHMENT_MAX_ATTEMPTS", "3")
            )))
            max_retries = max_attempts - 1
        except (TypeError, ValueError):
            max_retries = 2
        try:
            base_delay = max(0.0, float(getattr(
                settings, "attachment_retry_delay_seconds",
                os.getenv("LLM_COUNCIL_ATTACHMENT_RETRY_DELAY_SECONDS", "35.0")
            )))
        except (TypeError, ValueError):
            base_delay = 35.0
        return max_retries, base_delay

    def _attachment_delay_seconds(self) -> float:
        """Delay between attachment-bearing custom endpoint calls to avoid rate limits."""
        settings = get_settings()
        try:
            return max(0.0, float(getattr(settings, "attachment_delay_seconds", 20.0)))
        except (TypeError, ValueError):
            pass
        raw = os.getenv("LLM_COUNCIL_ATTACHMENT_DELAY_SECONDS", "20")
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            return 20.0

    async def _maybe_pause_after_attachment_call(self) -> None:
        delay = self._attachment_delay_seconds()
        if delay > 0:
            await asyncio.sleep(delay)

    async def query(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        timeout: float = 120.0,
        temperature: float = 0.7,
        attachments: List[Dict[str, Any]] | None = None
    ) -> Dict[str, Any]:
        name, base_url, _ = self._get_config()
        payload_attachments = (
            attachments if attachments and self._supports_attachments(name, base_url) else None
        )
        notion_upload = bool(
            payload_attachments and self._is_notion_attachment_endpoint(name, base_url)
        )

        if notion_upload:
            async with _ATTACHMENT_UPLOAD_SEMAPHORE:
                res = await self._query_execute(
                    model_id,
                    messages,
                    timeout,
                    temperature,
                    payload_attachments,
                    notion_upload=True,
                )
                if not res.get("error"):
                    await self._maybe_pause_after_attachment_call()
                return res

        return await self._query_execute(
            model_id,
            messages,
            timeout,
            temperature,
            payload_attachments,
            notion_upload=False,
        )

    async def _query_execute(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        timeout: float = 120.0,
        temperature: float = 0.7,
        attachments: List[Dict[str, Any]] | None = None,
        *,
        notion_upload: bool = False,
    ) -> Dict[str, Any]:
        name, base_url, api_key = self._get_config()

        if not base_url:
            return {"error": True, "error_message": f"{name} endpoint URL not configured"}

        # Strip prefix if present
        model = model_id.removeprefix("custom:")

        # Normalize URL
        if base_url.endswith('/'):
            base_url = base_url[:-1]

        try:
            settings = get_settings()
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            # Pass the custom poll configuration in request headers if supported
            poll_interval = getattr(settings, "attachment_poll_interval_seconds", 2.0)
            poll_timeout = getattr(settings, "attachment_poll_timeout_seconds", 60.0)
            headers["X-Attachment-Poll-Interval"] = str(poll_interval)
            headers["X-Attachment-Poll-Timeout"] = str(poll_timeout)
            headers["X-Notion-Poll-Interval"] = str(poll_interval)
            headers["X-Notion-Poll-Timeout"] = str(poll_timeout)

            payload = add_temperature_if_supported(
                {
                    "model": model,
                    "messages": messages,
                },
                model,
                "custom",
                temperature,
            )

            # Attachment payloads use the Notion2API wire format. Generic custom
            # endpoints only receive them when custom_endpoint_supports_attachments
            # is enabled; Notion-specific throttling/retry applies separately.
            if attachments:
                payload["attachments"] = attachments

            start_time = time.monotonic()
            attempts_info = []

            use_notion_attachment_retry = notion_upload and bool(payload.get("attachments"))
            if use_notion_attachment_retry:
                rate_limit_retries, rate_limit_base = self._attachment_retry_config()
                rate_limit_jitter = 0.0
            else:
                rate_limit_retries, rate_limit_base, rate_limit_jitter = self._rate_limit_retry_config()

            max_attempts = 1 + rate_limit_retries

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = None
                last_status = 0
                last_response_text = ""

                for attempt in range(max_attempts):
                    attempt_start = time.monotonic()
                    attempt_idx = attempt + 1
                    status_code = 0
                    response_text = ""
                    try:
                        response = await client.post(
                            f"{base_url}/chat/completions",
                            headers=headers,
                            json=payload
                        )
                        status_code = response.status_code
                        response_text = response.text

                        # Fast-path: auth errors don't benefit from retrying
                        if _is_auth_error(status_code):
                            attempt_duration = time.monotonic() - attempt_start
                            attempts_info.append({
                                "attempt": attempt_idx,
                                "duration": f"{attempt_duration:.2f}s",
                                "status": status_code,
                                "is_rate_limit": False,
                                "error_excerpt": response_text[:120] or "No response body",
                            })
                            last_status = status_code
                            last_response_text = response_text
                            break

                    except Exception as e:
                        response_text = str(e)

                    attempt_duration = time.monotonic() - attempt_start
                    is_rl = _is_rate_limited(status_code, response_text)

                    attempts_info.append({
                        "attempt": attempt_idx,
                        "start_offset": f"{(time.monotonic() - start_time - attempt_duration):.2f}s",
                        "duration": f"{attempt_duration:.2f}s",
                        "status": status_code,
                        "is_rate_limit": is_rl,
                        "error_excerpt": response_text[:120] if response_text else "No response body",
                    })

                    last_status = status_code
                    last_response_text = response_text

                    if status_code == 200:
                        break

                    # Only retry on rate-limit responses
                    if not is_rl:
                        break

                    if attempt >= max_attempts - 1:
                        logger.warning(
                            "custom_openai: rate-limited on %s after %d attempt(s) "
                            "(%.1fs elapsed) -- rate-limit persists",
                            model_id,
                            attempt_idx,
                            time.monotonic() - start_time,
                        )
                        break

                    if use_notion_attachment_retry:
                        # Linear/progressive backoff for Notion2API file-import limits
                        sleep_time = rate_limit_base * attempt_idx
                    else:
                        sleep_time = rate_limit_base * (2 ** attempt) + random.uniform(0, rate_limit_jitter)

                    logger.warning(
                        "custom_openai: rate-limited on %s (attempt %d/%d, HTTP %s) "
                        "-- retrying in %.2fs",
                        model_id,
                        attempt_idx,
                        max_attempts,
                        status_code or "no-response",
                        sleep_time,
                    )
                    await asyncio.sleep(sleep_time)

                if response is None:
                    return {
                        "error": True,
                        "error_message": (
                            f"{name} API error (no response) after {len(attempts_info)} attempt(s)."
                        ),
                        "rate_limited": False,
                        "debug_timeline": attempts_info,
                        "total_elapsed_seconds": f"{time.monotonic() - start_time:.2f}s",
                    }

                # Evaluate final outcome
                if last_status != 200:
                    status_str = f"status: {last_status}" if last_status else "no response"
                    if _is_auth_error(last_status):
                        err_msg = (
                            f"{name} API error ({status_str}) after {len(attempts_info)} attempt(s): "
                            "authentication failed -- check the API key."
                        )
                    elif _is_not_found(last_status):
                        err_msg = (
                            f"{name} API error ({status_str}) after {len(attempts_info)} attempt(s): "
                            "model not found or endpoint does not exist."
                        )
                    elif _is_rate_limited(last_status, last_response_text):
                        err_msg = (
                            f"{name} API error ({status_str}) after {len(attempts_info)} attempt(s) "
                            "due to Rate Limit."
                        )
                    else:
                        err_msg = (
                            f"{name} API error ({status_str}) after {len(attempts_info)} attempt(s)."
                        )

                    return {
                        "error": True,
                        "error_message": err_msg,
                        "rate_limited": _is_rate_limited(last_status, last_response_text),
                        "debug_timeline": attempts_info,
                        "total_elapsed_seconds": f"{time.monotonic() - start_time:.2f}s",
                    }

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return {"content": content, "usage": data.get("usage"), "error": False}

        except httpx.TimeoutException:
            return {"error": True, "error_message": f"Request timed out after {int(timeout)}s — {name} did not respond"}
        except httpx.ConnectError:
            return {"error": True, "error_message": f"Connection failed — check the {name} endpoint URL"}
        except Exception as e:
            return {"error": True, "error_message": str(e) or repr(e)}


    async def get_models(self) -> List[Dict[str, Any]]:
        name, base_url, api_key = self._get_config()

        if not base_url:
            return []

        # Normalize URL
        if base_url.endswith('/'):
            base_url = base_url[:-1]

        try:
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{base_url}/models",
                    headers=headers
                )

                if response.status_code != 200:
                    return []

                data = response.json()
                models = []

                for model in data.get("data", []):
                    model_id = model.get("id", "")
                    if not model_id:
                        continue

                    mid = model_id.lower()
                    # Filter out non-chat models
                    if any(x in mid for x in ["embed", "whisper", "tts", "dall-e", "audio", "transcribe"]):
                        continue

                    models.append({
                        "id": f"custom:{model_id}",
                        "name": f"{model_id} [{name}]",
                        "provider": name
                    })

                return sorted(models, key=lambda x: x["name"])

        except Exception:
            return []

    async def validate_connection(self, url: str, api_key: str = "") -> Dict[str, Any]:
        """Validate connection to a custom endpoint."""
        if not url:
            return {"success": False, "message": "URL is required"}

        # Normalize URL
        if url.endswith('/'):
            url = url[:-1]

        try:
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{url}/models",
                    headers=headers
                )

                if response.status_code == 200:
                    data = response.json()
                    model_count = len(data.get("data", []))
                    return {
                        "success": True,
                        "message": f"Connected successfully. Found {model_count} models."
                    }
                elif response.status_code == 401:
                    return {"success": False, "message": "Authentication failed. Check your API key."}
                else:
                    return {"success": False, "message": f"API error: {response.status_code}"}

        except httpx.ConnectError:
            return {"success": False, "message": "Connection failed. Check the URL."}
        except httpx.TimeoutException:
            return {"success": False, "message": "Connection timed out."}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def validate_key(self, api_key: str) -> Dict[str, Any]:
        """Validate using stored URL."""
        _, base_url, _ = self._get_config()
        return await self.validate_connection(base_url, api_key)
