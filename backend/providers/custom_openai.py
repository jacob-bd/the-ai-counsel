"""Custom OpenAI-compatible endpoint provider."""

import httpx
from typing import List, Dict, Any
from .base import LLMProvider
from ..settings import get_settings


class CustomOpenAIProvider(LLMProvider):
    """Provider for any OpenAI-compatible API endpoint."""

    def _get_config(self) -> tuple[str, str, str]:
        """Get custom endpoint configuration."""
        settings = get_settings()
        name = settings.custom_endpoint_name or "Custom"
        url = settings.custom_endpoint_url or ""
        api_key = settings.custom_endpoint_api_key or ""
        return name, url, api_key

    async def query(self, model_id: str, messages: List[Dict[str, str]], timeout: float = 120.0, temperature: float = 0.7) -> Dict[str, Any]:
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
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature
                    }
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
