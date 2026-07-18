"""OpenRouter provider wrapper."""

from typing import List, Dict, Any
from .base import LLMProvider
from .. import openrouter
from ..credentials import get_api_key

class OpenRouterProvider(LLMProvider):
    """OpenRouter API provider."""
    
    async def query(self, model_id: str, messages: List[Dict[str, str]], timeout: float = 120.0, temperature: float = 0.7) -> Dict[str, Any]:
        # Strip internal prefix if present
        if model_id.startswith("openrouter:"):
            model_id = model_id.replace("openrouter:", "", 1)
            
        # OpenRouter module handles key retrieval internally
        return await openrouter.query_model(model_id, messages, timeout, temperature)

    async def get_models(self) -> List[Dict[str, Any]]:
        # We can reuse the existing endpoint logic or implement a direct fetch here
        # For now, let's implement a direct fetch to match the interface pattern
        import httpx
        api_key = get_api_key("openrouter")
        
        if not api_key:
            return []
            
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"}
                )
                
                if response.status_code != 200:
                    return []
                    
                data = response.json()
                models = []
                for model in data.get("data", []):
                    # Filter out non-chat models based on ID and Name
                    mid = model.get("id", "").lower()
                    name = model.get("name", "").lower()
                    
                    # Comprehensive exclusion list for non-text/chat models
                    excluded_terms = [
                        "embed", "audio", "whisper", "tts", "dall-e", "realtime", 
                        "vision-only", "voxtral", "speech", "transcribe", "sora"
                    ]
                    
                    if any(term in mid for term in excluded_terms) or any(term in name for term in excluded_terms):
                        continue
                        
                    # Extract pricing
                    pricing = model.get("pricing", {})
                    prompt_price = float(pricing.get("prompt", "0") or "0")
                    completion_price = float(pricing.get("completion", "0") or "0")
                    is_free = prompt_price == 0 and completion_price == 0
                    
                    models.append({
                        "id": f"openrouter:{model.get('id')}",
                        "name": f"{model.get('name', model.get('id'))} [OpenRouter]",
                        "provider": "OpenRouter",
                        "is_free": is_free
                    })
                return sorted(models, key=lambda x: x["name"])
        except Exception:
            return []

    async def validate_key(self, api_key: str) -> Dict[str, Any]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"}
                )
                
                if response.status_code == 200:
                    return {"success": True, "message": "API key is valid"}
                elif response.status_code == 401:
                    return {"success": False, "message": "Invalid API key"}
                else:
                    return {"success": False, "message": f"API error: {response.status_code}"}
        except Exception as e:
            return {"success": False, "message": str(e)}
