"""OpenCode Zen / Go direct provider (OpenAI-compatible chat/completions only).

OpenCode Zen is a multi-protocol gateway: GPT-family models use /v1/responses,
Claude-family use /v1/messages, Gemini use per-model Google endpoints, and the
rest use the OpenAI-compatible /v1/chat/completions endpoint. This provider
only supports the chat/completions subset in v1. Models that need a different
protocol are not listed by ``get_models`` and will surface as a backend error
if requested directly.

OpenCode Go is a subscription endpoint that also exposes /v1/chat/completions
for a subset of models (GLM, Kimi, DeepSeek, MiMo). Models on the /v1/messages
path (MiniMax, Qwen) are not supported in v1.

Both products share the same OpenCode auth — one key unlocks Zen balance
(per-token) and/or Go subscription ($5 first month, $10/month after).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx

from ..settings import get_settings
from .base import LLMProvider

logger = logging.getLogger(__name__)


class OpenCodeProvider(LLMProvider):
    """Provider for OpenCode Zen and OpenCode Go (chat/completions only)."""

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

    # Substring markers for chat/completions-capable models. Anything not
    # matching is filtered out of get_models(). Keep this list aligned with the
    # v1 scope; the per-model hardcoded pricing in costs.py mirrors it.
    _CHAT_COMPLETIONS_MARKERS: Dict[str, tuple[str, ...]] = {
        "zen": (
            "deepseek",
            "glm",
            "kimi",
            "minimax",
            "qwen3.5",
            "qwen3.6",
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

        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.config['base_url']}/chat/completions",
                    headers=headers,
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                    },
                )

            if response.status_code != 200:
                return {
                    "error": True,
                    "error_message": f"{self.name} API error: {response.status_code} - {response.text[:300]}",
                }

            data = response.json()
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as e:
                return {"error": True, "error_message": f"Unexpected {self.name} response shape: {e}"}
            return {"content": content, "usage": data.get("usage"), "error": False}

        except httpx.TimeoutException:
            return {"error": True, "error_message": f"Request timed out after {int(timeout)}s — {self.name} did not respond"}
        except httpx.ConnectError:
            return {"error": True, "error_message": f"Connection failed — could not reach {self.name}"}
        except Exception as e:
            return {"error": True, "error_message": str(e) or repr(e)}

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
                if not self._supports_chat_completions(model_id):
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
