"""ChatGPT Plus/Pro OAuth provider (Codex Responses API)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Set

import httpx

from .errors import describe_exception

from ..credentials import get_oauth_credential
from ..oauth.refresh import get_valid_access_token
from ..oauth.responses_websocket import query_responses_lite_websocket
from .base import LLMProvider

logger = logging.getLogger(__name__)

CODEX_BASE = "https://chatgpt.com/backend-api/codex"
CHATGPT_MODELS_URL = "https://chatgpt.com/backend-api/models"
CHATGPT_CODEX_MODELS_URL = f"{CODEX_BASE}/models"

# Models the Codex backend rejects for ChatGPT OAuth accounts (HTTP 400).
# Luna is supported via Responses-Lite WebSocket — do not list it here.
CHATGPT_CODEX_UNSUPPORTED = frozenset({"gpt-5.5-fast"})

# Seed + runtime models that require Responses-Lite WebSocket transport.
_RESPONSES_LITE_MODELS: Set[str] = {"gpt-5.6-luna"}

OPENAI_OAUTH_MODEL_SEEDS = [
    {"id": "gpt-5.6-sol", "name": "GPT-5.6 Sol"},
    {"id": "gpt-5.6-terra", "name": "GPT-5.6 Terra"},
    {
        "id": "gpt-5.6-luna",
        "name": "GPT-5.6 Luna",
        "prefer_websockets": True,
        "use_responses_lite": True,
    },
    {"id": "gpt-5.5", "name": "GPT-5.5"},
    {"id": "gpt-5.4", "name": "GPT-5.4"},
    {"id": "gpt-5.4-mini", "name": "GPT-5.4 Mini"},
    {"id": "gpt-5", "name": "GPT-5"},
    {"id": "o4-mini", "name": "o4 Mini"},
    {"id": "o3", "name": "o3"},
    {"id": "o3-mini", "name": "o3 Mini"},
    {"id": "o1", "name": "o1"},
    {"id": "o1-mini", "name": "o1 Mini"},
]


def _messages_to_responses_input(messages: List[Dict[str, str]]) -> tuple[Optional[str], List[Dict[str, Any]]]:
    instructions_parts: List[str] = []
    input_items: List[Dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role") or "user"
        content = msg.get("content") or ""
        if role == "system":
            instructions_parts.append(content)
            continue
        mapped_role = "assistant" if role == "assistant" else "user"
        input_items.append(
            {
                "type": "message",
                "role": mapped_role,
                "content": [{"type": "input_text", "text": content}],
            }
        )
    instructions = "\n\n".join(instructions_parts) if instructions_parts else None
    return instructions, input_items


def _extract_responses_text(data: Dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str) and data["output_text"]:
        return data["output_text"]
    chunks: List[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                continue
            text = part.get("text") or part.get("output_text")
            if text:
                chunks.append(str(text))
    if chunks:
        return "".join(chunks)
    # Fallback: chat-completions-like
    try:
        return data["choices"][0]["message"]["content"]
    except Exception:
        return json.dumps(data)[:2000]


def _seed_models() -> List[Dict[str, Any]]:
    return [
        {
            "id": f"openai-oauth:{s['id']}",
            "name": f"{s['name']} [ChatGPT]",
            "provider": "ChatGPT",
            "source": "openai-oauth",
            "prefer_websockets": bool(s.get("prefer_websockets")),
            "use_responses_lite": bool(s.get("use_responses_lite")),
        }
        for s in OPENAI_OAUTH_MODEL_SEEDS
        if s["id"] not in CHATGPT_CODEX_UNSUPPORTED
    ]


def _parse_chatgpt_model_entries(body: Any) -> List[Dict[str, Any]]:
    """Parse ChatGPT-internal `{models:[{slug,title}]}` or OpenAI `{data:[{id}]}`."""
    if not isinstance(body, dict):
        return []
    entries: List[Dict[str, Any]] = []
    if isinstance(body.get("models"), list):
        for raw in body["models"]:
            if not isinstance(raw, dict):
                continue
            mid = raw.get("slug") or raw.get("id")
            if not mid:
                continue
            entries.append(
                {
                    "id": str(mid),
                    "name": str(raw.get("title") or raw.get("name") or mid),
                    "prefer_websockets": bool(raw.get("prefer_websockets")),
                    "use_responses_lite": bool(raw.get("use_responses_lite")),
                }
            )
        return entries
    if isinstance(body.get("data"), list):
        for raw in body["data"]:
            if not isinstance(raw, dict):
                continue
            mid = raw.get("id")
            if not mid:
                continue
            entries.append(
                {
                    "id": str(mid),
                    "name": str(raw.get("name") or mid),
                    "prefer_websockets": bool(raw.get("prefer_websockets")),
                    "use_responses_lite": bool(raw.get("use_responses_lite")),
                }
            )
    return entries


def _entries_to_models(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seed_by_id = {s["id"]: s for s in OPENAI_OAUTH_MODEL_SEEDS}
    models: List[Dict[str, Any]] = []
    lite: Set[str] = set()
    for entry in entries:
        mid = entry["id"]
        if mid in CHATGPT_CODEX_UNSUPPORTED:
            continue
        seed = seed_by_id.get(mid, {})
        prefer_ws = bool(entry.get("prefer_websockets") or seed.get("prefer_websockets"))
        use_lite = bool(entry.get("use_responses_lite") or seed.get("use_responses_lite"))
        if prefer_ws or use_lite:
            lite.add(mid)
        name = entry.get("name") or seed.get("name") or mid
        models.append(
            {
                "id": f"openai-oauth:{mid}",
                "name": f"{name} [ChatGPT]",
                "provider": "ChatGPT",
                "source": "openai-oauth",
                "prefer_websockets": prefer_ws,
                "use_responses_lite": use_lite,
            }
        )
    if lite:
        _RESPONSES_LITE_MODELS.update(lite)
    return models


def model_needs_responses_lite(model: str) -> bool:
    """True when inference must use the Responses-Lite WebSocket transport."""
    return model in _RESPONSES_LITE_MODELS


class OpenAIOauthProvider(LLMProvider):
    async def query(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        timeout: float = 120.0,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        cred = get_oauth_credential("openai-oauth")
        if not cred:
            return {"error": True, "error_message": "ChatGPT OAuth not connected"}
        try:
            token = await get_valid_access_token("openai-oauth")
        except Exception as exc:
            return {"error": True, "error_message": str(exc)}

        model = model_id.removeprefix("openai-oauth:")
        if model in CHATGPT_CODEX_UNSUPPORTED:
            return {
                "error": True,
                "error_message": f"Model '{model}' is not supported via ChatGPT OAuth",
            }

        instructions, input_items = _messages_to_responses_input(messages)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "originator": "the-ai-counsel",
        }
        account_id = cred.get("accountId")
        if account_id:
            headers["ChatGPT-Account-Id"] = account_id

        payload: Dict[str, Any] = {
            "model": model,
            "input": input_items,
            "store": False,
            "stream": True,
        }
        if instructions:
            payload["instructions"] = instructions

        if model_needs_responses_lite(model):
            try:
                return await query_responses_lite_websocket(
                    payload=payload,
                    headers=headers,
                    timeout=timeout,
                )
            except Exception as e:
                return {"error": True, "error_message": describe_exception(e, timeout)}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{CODEX_BASE}/responses",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        return {
                            "error": True,
                            "error_message": (
                                f"ChatGPT OAuth API error: {response.status_code} - "
                                f"{body.decode('utf-8', errors='replace')}"
                            ),
                        }
                    content_type = response.headers.get("content-type", "")
                    if "text/event-stream" in content_type or payload.get("stream"):
                        text_parts: List[str] = []
                        usage = None
                        async for line in response.aiter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                event = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
                            etype = event.get("type") or ""
                            if etype in (
                                "response.output_text.delta",
                                "response.text.delta",
                            ):
                                delta = event.get("delta") or ""
                                if delta:
                                    text_parts.append(str(delta))
                            elif etype == "response.completed":
                                resp = event.get("response") or {}
                                if not text_parts:
                                    text_parts.append(_extract_responses_text(resp))
                                usage = resp.get("usage") or event.get("usage")
                        content = "".join(text_parts)
                        if not content:
                            return {
                                "error": True,
                                "error_message": "ChatGPT OAuth returned empty response",
                            }
                        return {"content": content, "usage": usage, "error": False}

                    data = await response.aread()
                    parsed = json.loads(data)
                    return {
                        "content": _extract_responses_text(parsed),
                        "usage": parsed.get("usage"),
                        "error": False,
                    }
        except Exception as e:
            return {"error": True, "error_message": describe_exception(e, timeout)}

    async def get_models(self) -> List[Dict[str, Any]]:
        if not get_oauth_credential("openai-oauth"):
            return []

        try:
            token = await get_valid_access_token("openai-oauth")
        except Exception:
            logger.debug("ChatGPT OAuth token unavailable for model list; using seeds", exc_info=True)
            return _seed_models()

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "originator": "the-ai-counsel",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Tier 1: Codex-specific listing (models the Codex API supports).
                codex_resp = await client.get(CHATGPT_CODEX_MODELS_URL, headers=headers)
                if codex_resp.status_code == 200:
                    entries = _parse_chatgpt_model_entries(codex_resp.json())
                    models = _entries_to_models(entries)
                    if models:
                        return models

                # Tier 2: General ChatGPT catalog, filtered by known restrictions.
                chat_resp = await client.get(CHATGPT_MODELS_URL, headers=headers)
                if chat_resp.status_code == 200:
                    entries = [
                        e
                        for e in _parse_chatgpt_model_entries(chat_resp.json())
                        if e["id"] not in CHATGPT_CODEX_UNSUPPORTED
                    ]
                    models = _entries_to_models(entries)
                    if models:
                        return models
        except Exception:
            logger.debug("ChatGPT OAuth live model fetch failed; using seeds", exc_info=True)

        return _seed_models()

    async def validate_key(self, api_key: str) -> Dict[str, Any]:
        if get_oauth_credential("openai-oauth"):
            return {"success": True, "message": "ChatGPT OAuth connected"}
        return {"success": False, "message": "ChatGPT OAuth not connected"}
