"""DeepSeek provider implementation."""

import httpx
from typing import List, Dict, Any
from .base import LLMProvider
from ..settings import get_settings

class DeepSeekProvider(LLMProvider):
    """DeepSeek API provider."""
    
    BASE_URL = "https://api.deepseek.com"
    
    def _get_api_key(self) -> str:
        settings = get_settings()
        return settings.deepseek_api_key or ""

    async def query(self, model_id: str, messages: List[Dict[str, str]], timeout: float = 120.0, temperature: float = 0.7) -> Dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return {"error": True, "error_message": "DeepSeek API key not configured"}
            
        model = model_id.removeprefix("deepseek:")
        
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature
                    }
                )
                
                if response.status_code != 200:
                    return {
                        "error": True, 
                        "error_message": f"DeepSeek API error: {response.status_code} - {response.text}"
                    }
                    
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return {"content": content, "usage": data.get("usage"), "error": False}
                
        except Exception as e:
            return {"error": True, "error_message": str(e)}

    async def get_models(self) -> List[Dict[str, Any]]:
        """Fetch available models from DeepSeek API with hardcoded fallback."""
        api_key = self._get_api_key()

        # Terms to exclude non-chat models
        excluded_terms = [
            "embed", "audio", "whisper", "tts", "dall-e", "realtime",
            "vision-only", "voxtral", "speech", "transcribe", "sora"
        ]

        # Try dynamic fetch if API key is available
        if api_key:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        f"{self.BASE_URL}/models",
                        headers={"Authorization": f"Bearer {api_key}"}
                    )

                    if response.status_code == 200:
                        data = response.json()
                        models = []

                        for model in data.get("data", []):
                            model_id = model.get("id", "")
                            model_id_lower = model_id.lower()

                            # Skip non-chat models
                            if any(term in model_id_lower for term in excluded_terms):
                                continue

                            models.append({
                                "id": f"deepseek:{model_id}",
                                "name": f"{model_id} [DeepSeek]",
                                "provider": "DeepSeek"
                            })

                        if models:
                            return models
            except Exception:
                pass  # Fall through to hardcoded fallback

        # Fallback to known models if API fails or no key
        return [
            {"id": "deepseek:deepseek-chat", "name": "DeepSeek Chat (V3) [DeepSeek]", "provider": "DeepSeek"},
            {"id": "deepseek:deepseek-reasoner", "name": "DeepSeek Reasoner (R1) [DeepSeek]", "provider": "DeepSeek"},
        ]

    async def validate_key(self, api_key: str) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/models",
                    headers={"Authorization": f"Bearer {api_key}"}
                )
                
                if response.status_code == 200:
                    return {"success": True, "message": "API key is valid"}
                else:
                    return {"success": False, "message": "Invalid API key"}
        except Exception as e:
            return {"success": False, "message": str(e)}
