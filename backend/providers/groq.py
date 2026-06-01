"""Groq provider implementation."""

import httpx
from typing import List, Dict, Any
from .base import LLMProvider
from ..settings import get_settings

class GroqProvider(LLMProvider):
    """Groq API provider."""
    
    BASE_URL = "https://api.groq.com/openai/v1"
    
    def _get_api_key(self) -> str:
        settings = get_settings()
        return settings.groq_api_key or ""

    async def query(self, model_id: str, messages: List[Dict[str, str]], timeout: float = 120.0, temperature: float = 0.7) -> Dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return {"error": True, "error_message": "Groq API key not configured"}
            
        # Strip prefix if present
        model = model_id.removeprefix("groq:")
        
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
                        "error_message": f"Groq API error: {response.status_code} - {response.text}"
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
                for model in data.get("data", []):
                    model_id = model["id"]
                    # Filter out non-chat models (Audio, TTS, etc.)
                    if "whisper" in model_id.lower() or "tts" in model_id.lower():
                        continue
                        
                    # Groq models usually have clean IDs like "llama3-70b-8192"
                    models.append({
                        "id": f"groq:{model['id']}",
                        "name": f"{model['id']} [Groq]",
                        "provider": "Groq",
                        "context_length": model.get("context_window", 8192) # Fallback if missing
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
                elif response.status_code == 401:
                    return {"success": False, "message": "Invalid API key"}
                else:
                    return {"success": False, "message": f"Groq API error: {response.status_code}"}
        except Exception as e:
            return {"success": False, "message": str(e)}
