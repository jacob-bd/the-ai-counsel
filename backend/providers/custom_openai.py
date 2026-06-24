"""Custom OpenAI-compatible endpoint provider."""

import asyncio
import logging
import time
import httpx
from typing import List, Dict, Any, Optional
from .base import LLMProvider
from .temperature import add_temperature_if_supported
from ..settings import get_settings

logger = logging.getLogger(__name__)


def _is_rate_limited(status_code: int, response_text: str) -> bool:
    """Check if the status code or response text indicates a rate limit."""
    if status_code == 429:
        return True
    body = (response_text or "").lower()
    if status_code == 503 and any(
        m in body for m in ("notion_429", "rate_limit", "rate limit", "fileimporterror", "congest", "unavail")
    ):
        return True
    if status_code not in {200, 0} and any(
        m in body for m in ("notion rate limit", "rate_limit", "too many requests", "throttl", "quota", "temporary congestion", "temporarily unavailable")
    ):
        return True
    if status_code == 0 and any(
        m in body for m in (
            "notion rate limit", "rate limit", "rate_limit",
            "429", "too many requests", "quota", "throttl", "temporary congestion", "temporarily unavailable"
        )
    ):
        return True
    return False


class CustomOpenAIProvider(LLMProvider):
    """Provider for any OpenAI-compatible API endpoint."""

    def _get_config(self) -> tuple[str, str, str]:
        """Get custom endpoint configuration."""
        settings = get_settings()
        name = settings.custom_endpoint_name or "Custom"
        url = settings.custom_endpoint_url or ""
        api_key = settings.custom_endpoint_api_key or ""
        return name, url, api_key

    def _supports_attachments(self) -> bool:
        """True when the custom endpoint is configured to accept attachment payloads."""
        settings = get_settings()
        return bool(getattr(settings, "custom_endpoint_supports_attachments", False))

    async def query(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        timeout: float = 120.0,
        temperature: float = 0.7,
        max_output_tokens: Optional[int] = None,
        conversation_id: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
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

            payload = add_temperature_if_supported(
                {
                    "model": model,
                    "messages": messages,
                },
                model,
                "custom",
                temperature,
            )

            # Pass attachments if enabled and present
            if attachments and self._supports_attachments():
                payload["attachments"] = attachments

            max_attempts = getattr(settings, "attachment_max_attempts", 3)
            base_delay = getattr(settings, "attachment_retry_delay_seconds", 35.0)

            # Standard constraints
            if not isinstance(max_attempts, int) or max_attempts <= 0:
                max_attempts = 3
            if not isinstance(base_delay, (int, float)) or base_delay <= 0:
                base_delay = 35.0

            response = None
            last_status = 0
            last_response_text = ""
            attempts_info = []
            start_time = time.monotonic()

            for attempt in range(max_attempts):
                attempt_idx = attempt + 1
                status_code = 0
                response_text = ""
                retry_after = None
                is_transient_failure = False

                try:
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        response = await client.post(
                            f"{base_url}/chat/completions",
                            headers=headers,
                            json=payload
                        )
                        status_code = response.status_code
                        response_text = response.text

                        # Check Retry-After header
                        if "retry-after" in response.headers:
                            try:
                                retry_after = float(response.headers["retry-after"])
                            except (TypeError, ValueError):
                                pass
                except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError) as exc:
                    response_text = str(exc)
                    is_transient_failure = True

                is_rl = _is_rate_limited(status_code, response_text)
                is_retryable_503 = (status_code == 503) and (is_rl or retry_after is not None)

                attempts_info.append({
                    "attempt": attempt_idx,
                    "status": status_code,
                    "is_rate_limit": is_rl or is_transient_failure or is_retryable_503,
                    "error_excerpt": response_text[:120] if response_text else "No response body",
                })

                last_status = status_code
                last_response_text = response_text

                if status_code == 200:
                    break

                # Fail fast on auth or not found errors
                if status_code in {401, 403, 404}:
                    break

                # Check if we should retry
                should_retry = (
                    is_rl or
                    is_transient_failure or
                    is_retryable_503 or
                    (retry_after is not None)
                )

                if not should_retry or attempt_idx >= max_attempts:
                    break

                sleep_time = retry_after if retry_after is not None else (base_delay * (2 ** attempt))
                logger.warning(
                    "custom_openai: transient failure/rate-limited on %s (attempt %d/%d, HTTP %s) "
                    "-- retrying in %.2fs",
                    model_id,
                    attempt_idx,
                    max_attempts,
                    status_code or "exception",
                    sleep_time,
                )
                await asyncio.sleep(sleep_time)

            if response is None or last_status != 200:
                err_msg = last_response_text or "No response from custom endpoint"
                if last_status == 401 or last_status == 403:
                    err_msg = "authentication failed -- check the API key."
                elif last_status == 404:
                    err_msg = "model not found or endpoint does not exist."
                elif _is_rate_limited(last_status, last_response_text):
                    err_msg = "due to Rate Limit."
                return {
                    "error": True,
                    "error_message": f"{name} API error ({last_status or 'no response'}): {err_msg}",
                    "rate_limited": _is_rate_limited(last_status, last_response_text),
                    "debug_timeline": attempts_info,
                    "total_elapsed_seconds": f"{time.monotonic() - start_time:.2f}s",
                }

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return {
                "content": content,
                "usage": data.get("usage"),
                "error": False,
                "debug_timeline": attempts_info,
                "total_elapsed_seconds": f"{time.monotonic() - start_time:.2f}s",
            }
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
