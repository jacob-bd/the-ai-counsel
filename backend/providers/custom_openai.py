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

    async def query(self, model_id: str, messages: List[Dict[str, str]], timeout: float = 120.0, temperature: float = 0.7, attachments: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
        name, base_url, api_key = self._get_config()

        if not base_url:
            return {"error": True, "error_message": f"{name} endpoint URL not configured"}

        # Strip prefix if present
        model = model_id.removeprefix("custom:")

        # Normalize URL
        if base_url.endswith('/'):
            base_url = base_url[:-1]

        try:
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            async with httpx.AsyncClient(timeout=timeout) as client:
                payload = add_temperature_if_supported(
                    {
                        "model": model,
                        "messages": messages,
                    },
                    model,
                    "custom",
                    temperature,
                )
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )

                if response.status_code != 200:
                    return {
                        "error": True,
                        "error_message": f"{name} API error: {response.status_code} - {response.text}"
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
