"""Optional Notion2API OpenAI-compatible provider."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List

import httpx

from .base import LLMProvider
from .temperature import add_temperature_if_supported


DEFAULT_NOTION2API_BASE_URL = "http://127.0.0.1:8120/v1"
NOTION2API_QUERY_ATTEMPTS = 3
NOTION2API_RETRY_BASE_DELAY = 0.75



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

    def _is_retryable_empty_response(self, status_code: int, body_text: str) -> bool:
        if status_code not in {502, 503, 504}:
            return False

        lowered = (body_text or "").lower()
        if "notion_empty" in lowered or "upstream_empty_response" in lowered:
            return True
        if "notion returned empty content" in lowered:
            return True

        try:
            body = json.loads(body_text)
        except Exception:
            return False

        error = body.get("error") if isinstance(body, dict) else None
        if not isinstance(error, dict):
            return False

        return (
            error.get("code") == "NOTION_EMPTY"
            or error.get("type") == "upstream_empty_response"
            or "empty content" in str(error.get("message", "")).lower()
        )

    async def query(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        timeout: float = 120.0,
        temperature: float = 0.7,
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

        try:
            last_response_text = ""
            last_status_code = 0

            for attempt in range(1, NOTION2API_QUERY_ATTEMPTS + 1):
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        f"{base_url}/chat/completions",
                        headers=self._headers(token),
                        json=payload,
                    )

                last_status_code = response.status_code
                last_response_text = response.text

                if response.status_code != 200:
                    if (
                        attempt < NOTION2API_QUERY_ATTEMPTS
                        and self._is_retryable_empty_response(response.status_code, response.text)
                    ):
                        await asyncio.sleep(NOTION2API_RETRY_BASE_DELAY * attempt)
                        continue

                    suffix = ""
                    if attempt > 1:
                        suffix = f" after {attempt} attempts"
                    return {
                        "error": True,
                        "error_message": f"Notion2API error{suffix}: {response.status_code} - {response.text}",
                    }

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                if not str(content or "").strip() and attempt < NOTION2API_QUERY_ATTEMPTS:
                    await asyncio.sleep(NOTION2API_RETRY_BASE_DELAY * attempt)
                    continue

                return {"content": content, "usage": data.get("usage"), "error": False}

            return {
                "error": True,
                "error_message": f"Notion2API error after {NOTION2API_QUERY_ATTEMPTS} attempts: {last_status_code} - {last_response_text}",
            }

        except httpx.TimeoutException:
            return {"error": True, "error_message": f"Notion2API request timed out after {int(timeout)}s"}
        except httpx.ConnectError:
            return {"error": True, "error_message": f"Could not connect to Notion2API at {base_url}"}
        except Exception as exc:
            return {"error": True, "error_message": str(exc) or repr(exc)}

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
