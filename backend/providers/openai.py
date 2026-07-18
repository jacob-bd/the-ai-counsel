"""OpenAI provider implementation."""

import httpx
from typing import List, Dict, Any
from .base import LLMProvider
from .temperature import add_temperature_if_supported
from ..settings import get_settings

class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""
    
    BASE_URL = "https://api.openai.com/v1"
    
    def _get_api_key(self) -> str:
        from ..credentials import get_api_key
        return get_api_key("openai")


    async def query(self, model_id: str, messages: List[Dict[str, str]], timeout: float = 120.0, temperature: float = 0.7) -> Dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return {"error": True, "error_message": "OpenAI API key not configured"}
            
        # Strip prefix if present
        model = model_id.removeprefix("openai:")
        
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                payload = add_temperature_if_supported(
                    {
                        "model": model,
                        "messages": messages,
                    },
                    model,
                    "openai",
                    temperature,
                )
                response = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json=payload
                )
                
                if response.status_code != 200:
                    return {
                        "error": True, 
                        "error_message": f"OpenAI API error: {response.status_code} - {response.text}"
                    }
                    
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return {"content": content, "usage": data.get("usage"), "error": False}
                
        except Exception as e:
            return {"error": True, "error_message": str(e)}

    async def get_models(self) -> List[Dict[str, Any]]:
        api_key = self._get_api_key()
        if not api_key:
            return []
            
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/models",
                    headers={"Authorization": f"Bearer {api_key}"}
                )
                
                if response.status_code != 200:
                    return []
                    
                data = response.json()
                models = []
                # Filter for chat models
                for model in data.get("data", []):
                    mid = model["id"].lower()
                    # Filter out non-chat models
                    if any(x in mid for x in ["audio", "realtime", "voice", "tts", "dall-e", "whisper", "embed", "transcribe", "sora"]):
                        continue
                        
                    if "gpt" in mid or "o1" in mid or "o3" in mid:
                        models.append({
                            "id": f"openai:{model['id']}",
                            "name": f"{model['id']} [OpenAI]",
                            "provider": "OpenAI"
                        })
                return sorted(models, key=lambda x: x["name"])
                
        except Exception:
            return []

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
