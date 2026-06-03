"""OpenCode Zen / Go direct provider (chat/completions + messages protocols).

OpenCode Zen is a multi-protocol gateway: GPT-family models use /v1/responses,
Claude-family use /v1/messages, Gemini use per-model Google endpoints, and the
rest use the OpenAI-compatible /v1/chat/completions endpoint.

OpenCode Go is a subscription endpoint exposing /v1/chat/completions for some
models (GLM, Kimi, DeepSeek, MiMo) and /v1/messages (Anthropic-compatible)
for others (MiniMax, Qwen).

This provider supports the chat/completions and messages subsets. Models that
need /v1/responses (GPT) or per-model Google endpoints (Gemini) are not listed
by ``get_models`` and will surface as a backend error if requested directly.

Both products share the same OpenCode auth — one key unlocks Zen balance
(per-token) and/or Go subscription ($5 first month, $10/month after).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

import httpx

from ..settings import get_settings
from .base import LLMProvider

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
INITIAL_RETRY_DELAY = 1.0


class OpenCodeProvider(LLMProvider):
    """Provider for OpenCode Zen and OpenCode Go (chat/completions + messages)."""

    PRODUCT_CONFIG: Dict[str, Dict[str, str]] = {
        "zen": {
            "name": "OpenCode Zen",
            "base_url": "https://opencode.ai/zen/v1",
            "prefix": "opencode-zen",
        },
        "go": {
            "name": "OpenCode Go",
            "base_url": "https://opencode.ai/zen/go/v1",
            "prefix": "opencode-go",
        },
    }

    # Substring markers for chat/completions-capable models.
    _CHAT_COMPLETIONS_MARKERS: Dict[str, tuple[str, ...]] = {
        "zen": (
            "deepseek",
            "glm",
            "kimi",
            "minimax",
            "grok",
            "big-pickle",
            "mimo",
            "nemotron",
        ),
        "go": (
            "glm",
            "kimi",
            "deepseek",
            "mimo",
        ),
    }

    # Substring markers for Anthropic-compatible /v1/messages models.
    _MESSAGES_MARKERS: Dict[str, tuple[str, ...]] = {
        "zen": ("qwen",),
        "go": ("minimax", "qwen"),
    }

    def __init__(self, product: str = "zen") -> None:
        if product not in self.PRODUCT_CONFIG:
            raise ValueError(f"Unknown OpenCode product: {product}")
        self.product = product
        self.config = self.PRODUCT_CONFIG[product]

    @property
    def name(self) -> str:
        return self.config["name"]

    def _get_api_key(self) -> str:
        return get_settings().opencode_api_key or ""

    def _strip_prefix(self, model_id: str) -> str:
        prefix = f"{self.config['prefix']}:"
        if model_id.startswith(prefix):
            return model_id[len(prefix):]
        if model_id.startswith(self.config["prefix"]):
            return model_id[len(self.config["prefix"]):].lstrip(":")
        return model_id

    def _supports_chat_completions(self, model_id: str) -> bool:
        """Return True when the model uses /v1/chat/completions on this product."""
        markers = self._CHAT_COMPLETIONS_MARKERS[self.product]
        lowered = model_id.lower()
        return any(marker in lowered for marker in markers)

    def _supports_messages(self, model_id: str) -> bool:
        """Return True when the model uses /v1/messages on this product."""
        markers = self._MESSAGES_MARKERS[self.product]
        lowered = model_id.lower()
        return any(marker in lowered for marker in markers)

    async def query(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        timeout: float = 120.0,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return {
                "error": True,
                "error_message": f"{self.name} API key not configured. Add it in Settings → LLM API Keys.",
            }

        model = self._strip_prefix(model_id)
        if not model:
            return {"error": True, "error_message": f"Missing model id after {self.config['prefix']}: prefix"}

        if self._supports_chat_completions(model):
            return await self._query_chat_completions(api_key, model, messages, timeout, temperature)
        if self._supports_messages(model):
            return await self._query_messages(api_key, model, messages, timeout, temperature)

        return {
            "error": True,
            "error_message": (
                f"{model} is not supported on {self.name}. "
                f"Only chat/completions and messages-protocol models are available."
            ),
        }

    async def _query_chat_completions(
        self, api_key: str, model: str, messages: List[Dict[str, str]],
        timeout: float, temperature: float,
    ) -> Dict[str, Any]:
        return await self._request_with_retries(
            api_key=api_key,
            model=model,
            url=f"{self.config['base_url']}/chat/completions",
            payload={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "stream": False,
            },
            parse_response=self._parse_chat_completions,
            timeout=timeout,
        )

    async def _query_messages(
        self, api_key: str, model: str, messages: List[Dict[str, str]],
        timeout: float, temperature: float,
    ) -> Dict[str, Any]:
        system_message = ""
        filtered_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                filtered_messages.append(msg)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": filtered_messages,
            "max_tokens": 4096,
            "temperature": temperature,
        }
        if system_message:
            payload["system"] = system_message

        return await self._request_with_retries(
            api_key=api_key,
            model=model,
            url=f"{self.config['base_url']}/messages",
            payload=payload,
            parse_response=self._parse_messages,
            timeout=timeout,
        )

    @staticmethod
    def _parse_chat_completions(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            return {"error": True, "error_message": f"Unexpected response shape: {e}"}
        return {"content": content, "usage": data.get("usage"), "error": False}

    @staticmethod
    def _parse_messages(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            content = data["content"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            return {"error": True, "error_message": f"Unexpected response shape: {e}"}
        return {"content": content, "usage": data.get("usage"), "error": False}

    async def _request_with_retries(
        self, *, api_key: str, model: str, url: str,
        payload: Dict[str, Any],
        parse_response,
        timeout: float,
    ) -> Dict[str, Any]:
        last_error: Dict[str, str] = {}
        for attempt in range(MAX_RETRIES):
            try:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                }
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(url, headers=headers, json=payload)

                if response.status_code == 429:
                    retry_delay = INITIAL_RETRY_DELAY * (2 ** attempt)
                    logger.info(
                        "Rate limited on %s, retrying in %.1fs (attempt %d/%d)",
                        model, retry_delay, attempt + 1, MAX_RETRIES,
                    )
                    last_error = {"code": "rate_limited"}
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(retry_delay)
                        continue

                if response.status_code != 200:
                    return {
                        "error": True,
                        "error_message": f"{self.name} API error: {response.status_code} - {response.text[:300]}",
                    }

                content_type = response.headers.get("content-type", "")
                if not content_type.startswith("application/json"):
                    return {
                        "error": True,
                        "error_message": (
                            f"Unexpected {self.name} response content-type: {content_type!r}. "
                            f"Expected application/json."
                        ),
                    }

                return parse_response(response.json())

            except httpx.TimeoutException:
                last_error = {"code": "timeout"}
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(INITIAL_RETRY_DELAY * (2 ** attempt))
                    continue
            except httpx.RemoteProtocolError as e:
                logger.info("Remote protocol error on %s: %s. Retrying...", model, e)
                last_error = {"code": "protocol_error"}
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(INITIAL_RETRY_DELAY * (2 ** attempt))
                    continue
            except httpx.ConnectError:
                return {"error": True, "error_message": f"Connection failed — could not reach {self.name}"}

        code = last_error.get("code", "unknown")
        if code == "rate_limited":
            return {"error": True, "error_message": f"{self.name} rate-limited after {MAX_RETRIES} attempts"}
        if code == "timeout":
            return {"error": True, "error_message": f"Request timed out after {int(timeout)}s — {self.name} did not respond"}
        if code == "protocol_error":
            return {"error": True, "error_message": f"{self.name} closed connection mid-response after {MAX_RETRIES} attempts"}
        return {"error": True, "error_message": f"{self.name} request failed after {MAX_RETRIES} attempts"}

    async def get_models(self) -> List[Dict[str, Any]]:
        api_key = self._get_api_key()
        if not api_key:
            return []

        try:
            headers = {"Authorization": f"Bearer {api_key}"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.config['base_url']}/models",
                    headers=headers,
                )

            if response.status_code != 200:
                logger.warning("%s /models returned %s", self.name, response.status_code)
                return []

            data = response.json()
            models: List[Dict[str, Any]] = []
            for model in data.get("data", []):
                model_id = model.get("id", "")
                if not model_id:
                    continue
                mid = model_id.lower()
                if any(x in mid for x in ("embed", "whisper", "tts", "audio", "transcribe", "image", "vision")):
                    continue
                if not self._supports_chat_completions(model_id) and not self._supports_messages(model_id):
                    continue
                models.append({
                    "id": f"{self.config['prefix']}:{model_id}",
                    "name": f"{model_id} [{self.name}]",
                    "provider": self.name,
                    "is_free": bool(model.get("is_free", False)),
                })
            return sorted(models, key=lambda m: m["name"])

        except Exception as e:
            logger.warning("Failed to list %s models: %s", self.name, e)
            return []

    async def _validate_with_key(self, api_key: str) -> Dict[str, Any]:
        if not api_key:
            return {"success": False, "message": f"{self.name} API key not configured"}
        try:
            headers = {"Authorization": f"Bearer {api_key}"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.config['base_url']}/models",
                    headers=headers,
                )
            if response.status_code == 200:
                data = response.json()
                count = len(data.get("data", []))
                return {
                    "success": True,
                    "message": f"Connected to {self.name}. Found {count} models.",
                }
            if response.status_code == 401:
                return {"success": False, "message": "Authentication failed. Check your API key."}
            return {"success": False, "message": f"{self.name} API error: {response.status_code}"}
        except httpx.ConnectError:
            return {"success": False, "message": f"Connection failed. Could not reach {self.name}."}
        except httpx.TimeoutException:
            return {"success": False, "message": f"Connection to {self.name} timed out."}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def validate_key(self, api_key: str) -> Dict[str, Any]:
        key = api_key or self._get_api_key()
        return await self._validate_with_key(key)
