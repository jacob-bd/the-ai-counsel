"""xAI SuperGrok OAuth provider."""

from __future__ import annotations

from typing import Any, Dict, List

import httpx

from ..credentials import get_oauth_credential
from ..oauth.refresh import get_valid_access_token
from .base import LLMProvider
from .temperature import add_temperature_if_supported

XAI_BASE = "https://api.x.ai/v1"

XAI_OAUTH_MODEL_SEEDS = [
    {"id": "grok-4", "name": "Grok 4"},
    {"id": "grok-4-fast", "name": "Grok 4 Fast"},
    {"id": "grok-3", "name": "Grok 3"},
    {"id": "grok-3-fast", "name": "Grok 3 Fast"},
    {"id": "grok-3-mini", "name": "Grok 3 Mini"},
    {"id": "grok-3-mini-fast", "name": "Grok 3 Mini Fast"},
]


class XaiOAuthProvider(LLMProvider):
    async def query(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        timeout: float = 120.0,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        try:
            token = await get_valid_access_token("xai-oauth")
        except Exception as exc:
            return {"error": True, "error_message": str(exc)}

        model = model_id.removeprefix("xai-oauth:")
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                payload = add_temperature_if_supported(
                    {"model": model, "messages": messages},
                    model,
                    "xai-oauth",
                    temperature,
                )
                response = await client.post(
                    f"{XAI_BASE}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if response.status_code != 200:
                    return {
                        "error": True,
                        "error_message": f"xAI OAuth API error: {response.status_code} - {response.text}",
                    }
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return {"content": content, "usage": data.get("usage"), "error": False}
        except Exception as e:
            return {"error": True, "error_message": str(e)}

    async def get_models(self) -> List[Dict[str, Any]]:
        if not get_oauth_credential("xai-oauth"):
            return []
        try:
            token = await get_valid_access_token("xai-oauth")
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{XAI_BASE}/models",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if response.status_code == 200:
                    models = []
                    for m in response.json().get("data", []):
                        mid = m.get("id")
                        if not mid:
                            continue
                        models.append(
                            {
                                "id": f"xai-oauth:{mid}",
                                "name": f"{mid} [SuperGrok]",
                                "provider": "xAI SuperGrok",
                                "source": "xai-oauth",
                            }
                        )
                    if models:
                        return models
        except Exception:
            pass
        return [
            {
                "id": f"xai-oauth:{s['id']}",
                "name": f"{s['name']} [SuperGrok]",
                "provider": "xAI SuperGrok",
                "source": "xai-oauth",
            }
            for s in XAI_OAUTH_MODEL_SEEDS
        ]

    async def validate_key(self, api_key: str) -> Dict[str, Any]:
        if get_oauth_credential("xai-oauth"):
            return {"success": True, "message": "xAI SuperGrok OAuth connected"}
        return {"success": False, "message": "xAI SuperGrok OAuth not connected"}
