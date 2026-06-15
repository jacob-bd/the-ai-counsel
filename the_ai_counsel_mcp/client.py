"""HTTP client for The AI Counsel backend."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


class CouncilClient:
    """Async HTTP client for The AI Counsel REST API."""

    def __init__(self, base_url: str = "http://localhost:8001", timeout: float = 180.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> CouncilClient:
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("CouncilClient must be used as an async context manager")
        return self._client

    # ── Health ──────────────────────────────────────────────────────────────

    async def health(self) -> dict:
        resp = await self.client.get(f"{self.base_url}/api/health")
        resp.raise_for_status()
        return resp.json()

    # ── Settings ─────────────────────────────────────────────────────────────

    async def get_settings(self) -> dict:
        resp = await self.client.get(f"{self.base_url}/api/settings")
        resp.raise_for_status()
        return resp.json()

    async def update_settings(self, **kwargs: Any) -> dict:
        resp = await self.client.put(
            f"{self.base_url}/api/settings",
            json=kwargs,
        )
        resp.raise_for_status()
        return resp.json()

    async def export_settings(self) -> dict:
        resp = await self.client.get(f"{self.base_url}/api/settings/export")
        resp.raise_for_status()
        return resp.json()

    async def import_settings(self, data: dict) -> dict:
        resp = await self.client.post(
            f"{self.base_url}/api/settings/import",
            json=data,
        )
        resp.raise_for_status()
        return resp.json()

    async def reset_settings(self) -> dict:
        resp = await self.client.post(f"{self.base_url}/api/settings/reset")
        resp.raise_for_status()
        return resp.json()

    # ── Models ───────────────────────────────────────────────────────────────

    async def get_openrouter_models(self) -> list[dict]:
        try:
            resp = await self.client.get(f"{self.base_url}/api/models")
            resp.raise_for_status()
            return resp.json().get("models", [])
        except (httpx.HTTPStatusError, httpx.RequestError):
            return []

    async def get_direct_models(self) -> list[dict]:
        try:
            resp = await self.client.get(f"{self.base_url}/api/models/direct")
            resp.raise_for_status()
            return resp.json().get("models", [])
        except (httpx.HTTPStatusError, httpx.RequestError):
            return []

    async def get_ollama_models(self) -> list[dict]:
        try:
            resp = await self.client.get(f"{self.base_url}/api/ollama/tags")
            resp.raise_for_status()
            return resp.json().get("models", [])
        except (httpx.HTTPStatusError, httpx.RequestError):
            return []

    async def get_custom_models(self) -> list[dict]:
        try:
            resp = await self.client.get(f"{self.base_url}/api/custom-endpoint/models")
            resp.raise_for_status()
            return resp.json().get("models", [])
        except (httpx.HTTPStatusError, httpx.RequestError):
            return []

    async def get_all_models(self) -> list[dict]:
        """Aggregate models from all providers."""
        results = []
        for models in await asyncio.gather(
            self.get_openrouter_models(),
            self.get_direct_models(),
            self.get_ollama_models(),
            self.get_custom_models(),
            return_exceptions=True,
        ):
            if isinstance(models, list):
                results.extend(models)
        return results

    # ── Conversations ─────────────────────────────────────────────────────────

    async def list_conversations(self) -> list[dict]:
        resp = await self.client.get(f"{self.base_url}/api/conversations")
        resp.raise_for_status()
        return resp.json()

    async def create_conversation(self) -> dict:
        resp = await self.client.post(
            f"{self.base_url}/api/conversations",
            json={},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_conversation(self, conversation_id: str) -> dict:
        resp = await self.client.get(
            f"{self.base_url}/api/conversations/{conversation_id}"
        )
        resp.raise_for_status()
        return resp.json()

    async def get_conversation_progress(self, conversation_id: str) -> dict:
        """Poll live progress of an active streaming run."""
        resp = await self.client.get(
            f"{self.base_url}/api/conversations/{conversation_id}/progress"
        )
        resp.raise_for_status()
        return resp.json()

    # ── One-Shot ───────────────────────────────────────────────────────────────

    async def ask(
        self,
        content: str,
        models: list[str] | None = None,
        chairman_model: str | None = None,
        web_search: bool = False,
        execution_mode: str = "chat_only",
        documents: list[dict] | None = None,
    ) -> dict:
        """One-shot query via POST /api/ask. No conversation state."""
        payload: dict[str, Any] = {
            "content": content,
            "web_search": web_search,
            "execution_mode": execution_mode,
        }
        if models:
            payload["models"] = models
        if chairman_model:
            payload["chairman_model"] = chairman_model
        if documents:
            payload["documents"] = documents
        resp = await self.client.post(f"{self.base_url}/api/ask", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def extract_documents(self, documents: list[dict]) -> dict:
        resp = await self.client.post(
            f"{self.base_url}/api/documents/extract-json",
            json={"documents": documents},
        )
        resp.raise_for_status()
        return resp.json()

    async def prepare_documents(self, documents: list[dict] | None) -> list[dict] | None:
        if not documents:
            return None
        if any(doc.get("data_base64") for doc in documents if isinstance(doc, dict)):
            extracted = await self.extract_documents(documents)
            return extracted.get("documents", [])
        return documents

    # ── Streaming ─────────────────────────────────────────────────────────────

    async def stream_message(
        self,
        conversation_id: str,
        content: str,
        web_search: bool = False,
        execution_mode: str = "full",
        council_models: list[str] | None = None,
        chairman_model: str | None = None,
        documents: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """Stream SSE events from the backend.

        Yields parsed event dicts (each has a 'type' field).
        Execution modes: 'full', 'chat_ranking', 'chat_only'
        Per-request model overrides avoid mutating global config.
        """
        url = f"{self.base_url}/api/conversations/{conversation_id}/message/stream"
        payload: dict[str, Any] = {
            "content": content,
            "web_search": web_search,
            "execution_mode": execution_mode,
        }
        if council_models:
            payload["council_models"] = council_models
        if chairman_model:
            payload["chairman_model"] = chairman_model
        if documents:
            payload["documents"] = documents
        async with self.client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    raw = line[len("data: "):]
                    try:
                        yield json.loads(raw)
                    except json.JSONDecodeError:
                        continue

    async def stream_debate_message(
        self,
        conversation_id: str,
        content: str,
        web_search: bool = False,
        execution_mode: str = "full",
        council_models: list[str] | None = None,
        chairman_model: str | None = None,
        debate_rounds: int | None = None,
        documents: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """Stream SSE events from the multi-round iterative debate endpoint.

        Yields parsed event dicts.
        """
        url = f"{self.base_url}/api/conversations/{conversation_id}/message/debate"
        payload: dict[str, Any] = {
            "content": content,
            "web_search": web_search,
            "execution_mode": execution_mode,
        }
        if council_models:
            payload["council_models"] = council_models
        if chairman_model:
            payload["chairman_model"] = chairman_model
        if debate_rounds is not None:
            payload["debate_rounds"] = debate_rounds
        if documents:
            payload["documents"] = documents
        async with self.client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    raw = line[len("data: "):]
                    try:
                        yield json.loads(raw)
                    except json.JSONDecodeError:
                        continue

    # ── Personas ──────────────────────────────────────────────────────────────

    async def get_personas(self) -> list[dict]:
        resp = await self.client.get(f"{self.base_url}/api/personas")
        resp.raise_for_status()
        return resp.json()

    async def update_persona(self, persona_id: str, **fields: Any) -> dict:
        resp = await self.client.patch(
            f"{self.base_url}/api/personas/{persona_id}",
            json=fields,
        )
        resp.raise_for_status()
        return resp.json()

    async def reset_persona(self, persona_id: str) -> dict:
        resp = await self.client.delete(
            f"{self.base_url}/api/personas/{persona_id}/override"
        )
        resp.raise_for_status()
        return resp.json()

    # ── Advisor Debate ────────────────────────────────────────────────────────

    async def stream_debate(
        self,
        conversation_id: str,
        question: str,
        persona_ids: list[str],
        default_model: str | None = None,
        model_assignments: dict | None = None,
        max_rounds: int = 3,
        search_provider: str | None = None,
        documents: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """Stream SSE events from an advisor debate.

        Yields parsed event dicts. Events include advisor_debate_start,
        advisor_round_start, advisor_response, advisor_round_complete,
        advisor_verdict, advisor_complete, and optionally advisor_search_*.
        """
        url = f"{self.base_url}/api/conversations/{conversation_id}/debate/stream"
        payload: dict[str, Any] = {
            "question": question,
            "persona_ids": persona_ids,
            "max_rounds": max_rounds,
            "web_search": search_provider is not None,
            "search_provider": search_provider,
            "default_model": default_model,
            "model_assignments": model_assignments,
        }
        if documents:
            payload["documents"] = documents
        async with self.client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    raw = line[len("data: "):]
                    try:
                        yield json.loads(raw)
                    except json.JSONDecodeError:
                        continue

    # ── Provider Testing ──────────────────────────────────────────────────────

    async def test_provider(self, provider: str, api_key: str | None = None) -> dict:
        resp = await self.client.post(
            f"{self.base_url}/api/settings/test-provider",
            json={"provider": provider, "api_key": api_key},
        )
        resp.raise_for_status()
        return resp.json()
