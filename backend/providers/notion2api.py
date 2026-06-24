from __future__ import annotations

import asyncio
import json
import os
import random
import time
import logging
from typing import Any, Dict, List, Optional

import httpx

from .base import LLMProvider
from .temperature import add_temperature_if_supported


DEFAULT_NOTION2API_BASE_URL = "http://127.0.0.1:8120/v1"
NOTION2API_QUERY_ATTEMPTS = 3
NOTION2API_RETRY_BASE_DELAY = 1.5
NOTION2API_RETRY_MAX_DELAY = 20.0
NOTION2API_QUERY_TIMEOUT = 600.0

# 502 circuit breaker constants
NOTION2API_502_PAUSE_SECONDS = 30.0
NOTION2API_STAGGER_MIN = 5.0
NOTION2API_STAGGER_MAX = 13.0
# Fable5 pre-fire delay constants
NOTION2API_FABLE5_DELAY_MIN = 10.0
NOTION2API_FABLE5_DELAY_MAX = 15.0

logger = logging.getLogger(__name__)


class Notion2APICircuitBreaker:
    """Process-level circuit breaker for notion2api 502 errors.

    When a 502 is detected, all notion2api calls pause for 30 seconds.
    After the pause, each subsequent request waits a random 5-13s stagger
    slot before firing (sequential slot ordering).
    """

    def __init__(self) -> None:
        self._paused: bool = False
        self._pause_until: float = 0.0
        self._pause_lock: asyncio.Lock = asyncio.Lock()
        self._stagger_lock: asyncio.Lock = asyncio.Lock()
        self._semaphores: Dict[int, asyncio.Semaphore] = {}
        self._force_fire_models: set = set()

    @property
    def is_paused(self) -> bool:
        return self._paused and time.monotonic() < self._pause_until

    def get_semaphore(self, max_concurrent: int) -> asyncio.Semaphore:
        if max_concurrent not in self._semaphores:
            self._semaphores[max_concurrent] = asyncio.Semaphore(max_concurrent)
        return self._semaphores[max_concurrent]

    def force_fire(self, model_id: str) -> None:
        self._force_fire_models.add(model_id)

    def reset(self) -> None:
        """Reset circuit breaker state for testing."""
        self._paused = False
        self._pause_until = 0.0
        self._force_fire_models.clear()

    def trigger_502_pause(self, model_id: str) -> None:
        """Trigger or extend the 30-second 502 pause."""
        now = time.monotonic()
        new_until = now + NOTION2API_502_PAUSE_SECONDS
        if self._paused and self._pause_until > now:
            # Already paused — extend the window
            logger.warning(
                "[Notion2API] 502 pause extended — new 30s window started (%s)", model_id
            )
        else:
            logger.warning(
                "[Notion2API] 502 pause triggered — waiting %.0fs before retrying (%s)",
                NOTION2API_502_PAUSE_SECONDS,
                model_id,
            )
        self._paused = True
        self._pause_until = new_until

    async def wait_if_paused(self, model_id: str, firing_mode: str = "sequential") -> None:
        """Wait for the 502 pause to expire, then take a sequential stagger slot."""
        if model_id in self._force_fire_models:
            self._force_fire_models.remove(model_id)
            logger.info("[Notion2API] Bypassing circuit breaker and stagger for %s (forced manually)", model_id)
            return

        was_paused = self._paused
        # Only stagger if we were paused OR if we are explicitly in random_delay mode
        if not was_paused and firing_mode != "random_delay":
            return

        # Wait for the pause window to expire
        while True:
            now = time.monotonic()
            if not self._paused or now >= self._pause_until:
                if self._paused and now >= self._pause_until:
                    self._paused = False
                    logger.info(
                        "[Notion2API] 502 pause ended after %.1fs",
                        NOTION2API_502_PAUSE_SECONDS,
                    )
                break
            remaining = self._pause_until - now
            await asyncio.sleep(min(remaining, 0.5))

        # Sequential stagger slot: each caller waits for the previous one
        # to finish its random delay before starting its own
        async with self._stagger_lock:
            delay = random.uniform(NOTION2API_STAGGER_MIN, NOTION2API_STAGGER_MAX)
            logger.info(
                "[Notion2API] Stagger delay: %.1fs before firing %s", delay, model_id
            )
            await asyncio.sleep(delay)
            logger.info("[Notion2API] Request fired: %s (stagger=%.1fs)", model_id, delay)


# Module-level singleton
_circuit_breaker = Notion2APICircuitBreaker()


class Notion2APIProvider(LLMProvider):
    """Provider for a user-managed Notion2API endpoint."""

    provider_name = "Notion2API"
    provider_prefix = "notion2api"

    def _get_config(self) -> tuple[str, str]:
        try:
            from ..settings import get_settings
            settings = get_settings()
            stored_url = settings.notion2api_base_url
            stored_token = settings.notion2api_api_key or ""
        except Exception:
            stored_url = DEFAULT_NOTION2API_BASE_URL
            stored_token = ""

        base_url = (os.getenv("NOTION2API_BASE_URL") or stored_url or DEFAULT_NOTION2API_BASE_URL).strip()
        token = (os.getenv("NOTION2API_API_KEY") or stored_token or "").strip()
        return base_url.rstrip("/"), token

    def _headers(self, token: str) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _strip_prefix(self, model_id: str) -> str:
        return model_id.removeprefix(f"{self.provider_prefix}:")

    def _persistent_conversation_id(self, conversation_id: str | None, model: str) -> str | None:
        clean_conversation = str(conversation_id or "").strip()
        if not clean_conversation:
            return None

        def _safe(value: str) -> str:
            return "".join(
                ch if ch.isalnum() or ch in {"-", "_", "."} else "-"
                for ch in value.strip()
            ).strip("-._")

        safe_conversation = _safe(clean_conversation)
        safe_model = _safe(model)
        if not safe_conversation or not safe_model:
            return None
        return f"ai-counsel-{safe_conversation}-{safe_model}"[:200]

    def _effective_timeout(self, timeout: float | None) -> float:
        try:
            requested = float(timeout or 0)
        except (TypeError, ValueError):
            requested = 0.0
        return max(requested, NOTION2API_QUERY_TIMEOUT)

    def _retry_delay(self, attempt: int) -> float:
        return min(
            NOTION2API_RETRY_MAX_DELAY,
            NOTION2API_RETRY_BASE_DELAY * (2 ** max(attempt - 1, 0)),
        )

    def _is_retryable_response(self, status_code: int, body_text: str) -> bool:
        lowered = (body_text or "").lower()
        retryable_terms = (
            "notion_empty",
            "upstream_empty_response",
            "notion returned empty content",
            "rate limit",
            "rate_limit",
            "ratelimit",
            "too many requests",
            "quota",
            "throttle",
            "temporarily unavailable",
            "temporary congestion",
            "timeout",
        )
        if any(term in lowered for term in retryable_terms):
            return True

        if status_code in {408, 409, 425, 429, 500, 502, 503, 504}:
            return True

        try:
            body = json.loads(body_text)
        except Exception:
            return False

        error = body.get("error") if isinstance(body, dict) else None
        if not isinstance(error, dict):
            return False

        code = str(error.get("code", "")).lower()
        error_type = str(error.get("type", "")).lower()
        message = str(error.get("message", "")).lower()
        combined = " ".join([code, error_type, message])
        return any(term in combined for term in retryable_terms)

    def _coerce_stream_text(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts: List[str] = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)
        return ""

    def _extract_stream_content(self, event: Any) -> str:
        if not isinstance(event, dict):
            return ""

        parts: List[str] = []
        choices = event.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue

                delta = choice.get("delta")
                if isinstance(delta, dict):
                    parts.append(self._coerce_stream_text(delta.get("content")))
                    parts.append(self._coerce_stream_text(delta.get("text")))

                message = choice.get("message")
                if isinstance(message, dict):
                    parts.append(self._coerce_stream_text(message.get("content")))

                parts.append(self._coerce_stream_text(choice.get("text")))

        parts.append(self._coerce_stream_text(event.get("content")))
        return "".join(part for part in parts if part)

    @staticmethod
    def _is_fable5_model(model_id: str) -> bool:
        """Return True if this model should have the fable5 pre-fire delay applied."""
        return "fable5" in (model_id or "").lower()

    @staticmethod
    async def _fable5_preflight_delay(model_id: str) -> None:
        """Apply the 10-15s pre-fire delay for fable5 models."""
        delay = random.uniform(NOTION2API_FABLE5_DELAY_MIN, NOTION2API_FABLE5_DELAY_MAX)
        logger.info(
            "[Notion2API] Fable5 pre-fire delay: %.1fs for %s", delay, model_id
        )
        await asyncio.sleep(delay)
        logger.info(
            "[Notion2API] Fable5 delay complete — firing %s", model_id
        )

    def _get_firing_mode(self) -> tuple[str, int]:
        """Read firing mode and sequential max_concurrent from settings."""
        try:
            from ..settings import get_settings
            s = get_settings()
            mode = getattr(s, "notion2api_firing_mode", "rapid_fire") or "rapid_fire"
            max_concurrent = int(getattr(s, "notion2api_sequential_max_concurrent", 3) or 3)
        except Exception:
            mode = "rapid_fire"
            max_concurrent = 3
        return mode, max_concurrent

    async def query(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        *,
        timeout: float = 120.0,
        temperature: float = 0.7,
        max_output_tokens: Optional[int] = None,
        conversation_id: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        base_url, token = self._get_config()
        if not base_url:
            return {"error": True, "error_message": "Notion2API endpoint URL not configured"}

        model = self._strip_prefix(model_id)
        payload = add_temperature_if_supported(
            {"model": model, "messages": messages},
            model,
            self.provider_prefix,
            temperature,
        )
        if attachments:
            payload["attachments"] = attachments
        if max_output_tokens is not None:
            payload["max_tokens"] = max_output_tokens

        persist_threads = False
        try:
            from ..settings import get_settings
            persist_threads = getattr(get_settings(), "notion2api_persist_chats", False)
        except Exception:
            pass

        persistent_conversation_id = self._persistent_conversation_id(conversation_id, model) if persist_threads else None
        if persistent_conversation_id:
            payload["conversation_id"] = persistent_conversation_id
            payload["metadata"] = {
                "persist_remote_chat": True,
                "source": "ai-counsel",
            }
        else:
            payload["metadata"] = {
                "persist_remote_chat": False,
                "source": "ai-counsel",
            }

        payload["stream"] = True
        effective_timeout = self._effective_timeout(timeout)

        _mode, _max_conc = self._get_firing_mode()
        sem = None
        if _mode == "sequential":
            sem = _circuit_breaker.get_semaphore(_max_conc)

        if sem:
            async with sem:
                return await self._execute_query_loop(
                    model_id, base_url, token, payload, effective_timeout, _mode
                )
        else:
            return await self._execute_query_loop(
                model_id, base_url, token, payload, effective_timeout, _mode
            )

    async def _execute_query_loop(
        self,
        model_id: str,
        base_url: str,
        token: str,
        payload: Dict[str, Any],
        effective_timeout: float,
        firing_mode: str,
    ) -> Dict[str, Any]:
        self._strip_prefix(model_id)
        last_response_text = ""
        last_status_code = 0

        for attempt in range(1, NOTION2API_QUERY_ATTEMPTS + 1):
            content_parts: List[str] = []
            usage: Any = None

            try:
                # --- Firing mode gate ---
                if firing_mode in ("random_delay", "sequential"):
                    await _circuit_breaker.wait_if_paused(model_id, firing_mode)
                    if self._is_fable5_model(model_id):
                        await self._fable5_preflight_delay(model_id)
                # --- End firing mode gate ---

                async with httpx.AsyncClient(timeout=effective_timeout) as client:
                    async with client.stream(
                        "POST",
                        f"{base_url}/chat/completions",
                        headers=self._headers(token),
                        json=payload,
                    ) as response:
                        last_status_code = response.status_code

                        if response.status_code != 200:
                            raw_body = await response.aread()
                            last_response_text = raw_body.decode("utf-8", errors="replace")

                            # Trigger 502 circuit breaker if needed
                            if response.status_code == 502 and firing_mode in ("random_delay", "sequential"):
                                _circuit_breaker.trigger_502_pause(model_id)

                            if (
                                attempt < NOTION2API_QUERY_ATTEMPTS
                                and self._is_retryable_response(response.status_code, last_response_text)
                            ):
                                await asyncio.sleep(self._retry_delay(attempt))
                                continue

                            suffix = ""
                            if attempt > 1:
                                suffix = f" after {attempt} attempts"
                            return {
                                "error": True,
                                "error_message": f"Notion2API error{suffix}: {response.status_code} - {last_response_text}",
                            }

                        async for line in response.aiter_lines():
                            stripped = line.strip()
                            if not stripped or stripped.startswith(":"):
                                continue

                            if stripped.startswith("data:"):
                                data_text = stripped.removeprefix("data:").strip()
                            elif stripped.startswith("{"):
                                data_text = stripped
                            else:
                                continue

                            if data_text == "[DONE]":
                                break

                            try:
                                event = json.loads(data_text)
                            except json.JSONDecodeError:
                                last_response_text = data_text
                                continue

                            if isinstance(event, dict) and event.get("usage") is not None:
                                usage = event.get("usage")

                            piece = self._extract_stream_content(event)
                            if piece:
                                content_parts.append(piece)

                            if isinstance(event, dict) and event.get("error") is not None:
                                last_response_text = json.dumps(event.get("error"), ensure_ascii=False)

                content = "".join(content_parts)
                if str(content or "").strip():
                    return {"content": content, "usage": usage, "error": False}

                if not last_response_text:
                    last_response_text = "stream completed without assistant content"

                if (
                    attempt < NOTION2API_QUERY_ATTEMPTS
                    and self._is_retryable_response(502, last_response_text)
                ):
                    await asyncio.sleep(self._retry_delay(attempt))
                    continue

            except (httpx.ReadError, httpx.RemoteProtocolError, httpx.StreamError) as exc:
                content = "".join(content_parts)
                if str(content or "").strip():
                    return {"content": content, "usage": usage, "error": False}
                last_response_text = str(exc) or repr(exc)
                last_status_code = 0
                if attempt < NOTION2API_QUERY_ATTEMPTS:
                    await asyncio.sleep(self._retry_delay(attempt))
                    continue

            except httpx.TimeoutException:
                content = "".join(content_parts)
                if str(content or "").strip():
                    return {"content": content, "usage": usage, "error": False}
                return {"error": True, "error_message": f"Notion2API request timed out after {int(effective_timeout)}s"}
            except httpx.ConnectError:
                return {"error": True, "error_message": f"Could not connect to Notion2API at {base_url}"}
            except Exception as exc:
                content = "".join(content_parts)
                if str(content or "").strip():
                    return {"content": content, "usage": usage, "error": False}
                return {"error": True, "error_message": str(exc) or repr(exc)}

        return {
            "error": True,
            "error_message": f"Notion2API error after {NOTION2API_QUERY_ATTEMPTS} attempts: {last_status_code} - {last_response_text}",
        }

    async def get_models(self) -> List[Dict[str, Any]]:
        base_url, token = self._get_config()
        if not base_url:
            return []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{base_url}/models", headers=self._headers(token))

            if response.status_code != 200:
                return []

            models: List[Dict[str, Any]] = []
            for model in response.json().get("data", []):
                model_id = str(model.get("id") or "").strip()
                if not model_id:
                    continue

                lowered = model_id.lower()
                if any(term in lowered for term in ["embed", "whisper", "tts", "dall-e", "audio", "transcribe"]):
                    continue

                models.append({
                    "id": f"{self.provider_prefix}:{model_id}",
                    "name": f"{model_id} [Notion2API]",
                    "provider": self.provider_name,
                    "source": self.provider_prefix,
                })

            return sorted(models, key=lambda item: item["name"])

        except Exception:
            return []

    async def validate_connection(self, url: str | None = None, token: str | None = None) -> Dict[str, Any]:
        stored_url, stored_token = self._get_config()
        base_url = (url or stored_url).rstrip("/")
        request_token = token if token is not None else stored_token
        if not base_url:
            return {"success": False, "message": "URL is required"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{base_url}/models", headers=self._headers(request_token))

            if response.status_code == 200:
                count = len(response.json().get("data", []))
                return {"success": True, "message": f"Connected to Notion2API. Found {count} models."}
            if response.status_code == 401:
                return {"success": False, "message": "Authentication failed."}
            return {"success": False, "message": f"Notion2API error: {response.status_code}"}

        except httpx.ConnectError:
            return {"success": False, "message": f"Could not connect to Notion2API at {base_url}"}
        except httpx.TimeoutException:
            return {"success": False, "message": "Connection timed out."}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    async def validate_key(self, api_key: str) -> Dict[str, Any]:
        return await self.validate_connection(token=api_key)
