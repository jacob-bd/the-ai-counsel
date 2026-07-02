"""Anthropic provider implementation."""

import httpx
from typing import List, Dict, Any
from .base import LLMProvider
from .temperature import add_temperature_if_supported
from ..settings import get_settings

class AnthropicProvider(LLMProvider):
    """Anthropic API provider."""
    
    BASE_URL = "https://api.anthropic.com/v1"
    
    def _get_api_key(self) -> str:
        settings = get_settings()
        return settings.anthropic_api_key or ""

    async def query(self, model_id: str, messages: List[Dict[str, str]], timeout: float = 120.0, temperature: float = 0.7) -> Dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return {"error": True, "error_message": "Anthropic API key not configured"}
            
        model = model_id.removeprefix("anthropic:")
        
        # Convert messages to Anthropic format (system message is separate)
        system_message = ""
        filtered_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                filtered_messages.append(msg)
        
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                payload = {
                    "model": model,
                    "messages": filtered_messages,
                    "max_tokens": 4096,
                }
                add_temperature_if_supported(payload, model, "anthropic", temperature)
                if system_message:
                    payload["system"] = system_message
                    
                response = await client.post(
                    f"{self.BASE_URL}/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json=payload
                )
                
                if response.status_code != 200:
                    return {
                        "error": True, 
                        "error_message": f"Anthropic API error: {response.status_code} - {response.text}"
                    }
                    
                data = response.json()
                content = data["content"][0]["text"]
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
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    }
                )
                
                if response.status_code != 200:
                    # Fallback to hardcoded list if API fails (e.g. older keys or API not enabled)
                    return [
                        {"id": "anthropic:claude-fable-5", "name": "Claude Fable 5 [Anthropic]", "provider": "Anthropic"},
                        {"id": "anthropic:claude-opus-4-7", "name": "Claude Opus 4.7 [Anthropic]", "provider": "Anthropic"},
                        {"id": "anthropic:claude-opus-4-6", "name": "Claude Opus 4.6 [Anthropic]", "provider": "Anthropic"},
                        {"id": "anthropic:claude-sonnet-5", "name": "Claude Sonnet 5 [Anthropic]", "provider": "Anthropic"},
                        {"id": "anthropic:claude-sonnet-4-6", "name": "Claude Sonnet 4.6 [Anthropic]", "provider": "Anthropic"},
                        {"id": "anthropic:claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5 [Anthropic]", "provider": "Anthropic"},
                        {"id": "anthropic:claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet [Anthropic]", "provider": "Anthropic"},
                    ]
                    
                data = response.json()
                models = []
                
                for model in data.get("data", []):
                    if model.get("type") == "model":
                        models.append({
                            "id": f"anthropic:{model['id']}",
                            "name": f"{model.get('display_name', model['id'])} [Anthropic]",
                            "provider": "Anthropic"
                        })
                
                return sorted(models, key=lambda x: x["name"])
                
        except Exception:
            return []

    async def validate_key(self, api_key: str) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": "claude-haiku-4-5-20251001",
                        "messages": [{"role": "user", "content": "Hi"}],
                        "max_tokens": 1
                    }
                )

                if response.status_code == 200:
                    return {"success": True, "message": "API key is valid"}

                error_body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                error_detail = error_body.get("error", {}).get("message", response.text)

                if response.status_code == 401:
                    return {"success": False, "message": f"Invalid API key: {error_detail}"}
                return {"success": False, "message": f"Anthropic API error ({response.status_code}): {error_detail}"}
        except Exception as e:
            return {"success": False, "message": str(e)}
