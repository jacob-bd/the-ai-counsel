"""NVIDIA Build (NIM) provider — OpenAI-compatible at integrate.api.nvidia.com."""

import httpx
from typing import List, Dict, Any
from .base import LLMProvider
from ..settings import get_settings


class NvidiaProvider(LLMProvider):
    """NVIDIA Build (NIM) API provider."""

    BASE_URL = "https://integrate.api.nvidia.com/v1"

    def _get_api_key(self) -> str:
        from ..credentials import get_api_key
        return get_api_key("nvidia")


    async def query(self, model_id: str, messages: List[Dict[str, str]], timeout: float = 120.0, temperature: float = 0.7) -> Dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return {"error": True, "error_message": "NVIDIA API key not configured"}

        model = model_id.removeprefix("nvidia:")

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                    },
                )

                if response.status_code != 200:
                    return {
                        "error": True,
                        "error_message": f"NVIDIA API error: {response.status_code} - {response.text}",
                    }

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return {"content": content, "usage": data.get("usage"), "error": False}

        except Exception as e:
            return {"error": True, "error_message": str(e)}

    async def get_models(self) -> List[Dict[str, Any]]:
        """Fetch available chat models from the NVIDIA NIM catalog."""
        api_key = self._get_api_key()

        excluded_terms = [
            "embed", "rerank", "vlm", "vision", "audio", "whisper",
            "tts", "dall-e", "speech", "transcribe",
        ]

        if api_key:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        f"{self.BASE_URL}/models",
                        headers={"Authorization": f"Bearer {api_key}"},
                    )

                    if response.status_code == 200:
                        data = response.json()
                        models = []

                        for model in data.get("data", []):
                            model_id = model.get("id", "")
                            model_id_lower = model_id.lower()

                            if any(term in model_id_lower for term in excluded_terms):
                                continue

                            models.append({
                                "id": f"nvidia:{model_id}",
                                "name": f"{model_id} [NVIDIA]",
                                "provider": "NVIDIA",
                            })

                        if models:
                            return models
            except Exception:
                pass

        # Fallback to commonly used models
        return [
            {"id": "nvidia:nvidia/llama-3.1-nemotron-ultra-253b-v1", "name": "Nemotron Ultra 253B [NVIDIA]", "provider": "NVIDIA"},
            {"id": "nvidia:nvidia/llama-3.3-nemotron-super-49b-v1", "name": "Nemotron Super 49B [NVIDIA]", "provider": "NVIDIA"},
            {"id": "nvidia:meta/llama-3.3-70b-instruct", "name": "Llama 3.3 70B Instruct [NVIDIA]", "provider": "NVIDIA"},
            {"id": "nvidia:meta/llama-3.1-70b-instruct", "name": "Llama 3.1 70B Instruct [NVIDIA]", "provider": "NVIDIA"},
            {"id": "nvidia:mistralai/mistral-nemotron", "name": "Mistral Nemotron [NVIDIA]", "provider": "NVIDIA"},
            {"id": "nvidia:qwen/qwq-32b", "name": "QwQ 32B [NVIDIA]", "provider": "NVIDIA"},
        ]

    async def validate_key(self, api_key: str) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if response.status_code == 200:
                    return {"success": True, "message": "API key is valid"}
                return {"success": False, "message": f"Invalid API key (HTTP {response.status_code})"}
        except Exception as e:
            return {"success": False, "message": str(e)}
