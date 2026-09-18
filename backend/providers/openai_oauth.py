"""ChatGPT Plus/Pro OAuth provider (Codex Responses API)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from .errors import describe_exception

from ..credentials import get_oauth_credential
from ..oauth.refresh import get_valid_access_token
from ..oauth.responses_websocket import query_codex_responses_websocket
from .base import LLMProvider

logger = logging.getLogger(__name__)

CODEX_BASE = "https://chatgpt.com/backend-api/codex"
CHATGPT_CODEX_MODELS_URL = f"{CODEX_BASE}/models"
# Codex /models requires this query param (relay-ai uses the installed Claude
# Code version; a recent known-good fallback is enough for Counsel).
CODEX_MODELS_CLIENT_VERSION = "2.1.183"

# Models the Codex backend rejects for ChatGPT OAuth accounts (HTTP 400).
# Luna is supported via Responses-Lite WebSocket — do not list it here.
CHATGPT_CODEX_UNSUPPORTED = frozenset({"gpt-5.5-fast"})

# Runtime transport flags discovered from live Codex /models (plus seed defaults).
_MODEL_TRANSPORT: Dict[str, Dict[str, bool]] = {
    "gpt-5.6-luna": {"prefer_websockets": True, "use_responses_lite": True},
}

OPENAI_OAUTH_MODEL_SEEDS = [
    {"id": "gpt-5.6-sol", "name": "GPT-5.6 Sol", "prefer_websockets": True, "use_responses_lite": True},
    {"id": "gpt-5.6-terra", "name": "GPT-5.6 Terra", "prefer_websockets": True, "use_responses_lite": True},
    {
        "id": "gpt-5.6-luna",
        "name": "GPT-5.6 Luna",
        "prefer_websockets": True,
        "use_responses_lite": True,
    },
    {"id": "gpt-5.5", "name": "GPT-5.5", "prefer_websockets": True},
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


def _humanize_model_id(model_id: str) -> str:
    return model_id.replace("-", " ").replace(".", " ").title()


def _seed_models() -> List[Dict[str, Any]]:
    models = []
    for s in OPENAI_OAUTH_MODEL_SEEDS:
        if s["id"] in CHATGPT_CODEX_UNSUPPORTED:
            continue
        prefer_ws = bool(s.get("prefer_websockets"))
        use_lite = bool(s.get("use_responses_lite"))
        _MODEL_TRANSPORT[s["id"]] = {
            "prefer_websockets": prefer_ws,
            "use_responses_lite": use_lite,
        }
        models.append(
            {
                "id": f"openai-oauth:{s['id']}",
                "name": f"{s['name']} [ChatGPT]",
                "provider": "ChatGPT",
                "source": "openai-oauth",
                "prefer_websockets": prefer_ws,
                "use_responses_lite": use_lite,
            }
        )
    return models


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
            title = raw.get("title") or raw.get("name")
            entries.append(
                {
                    "id": str(mid),
                    "name": str(title) if title else str(mid),
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
    for entry in entries:
        mid = entry["id"]
        if mid in CHATGPT_CODEX_UNSUPPORTED:
            continue
        seed = seed_by_id.get(mid, {})
        prefer_ws = bool(entry.get("prefer_websockets") or seed.get("prefer_websockets"))
        use_lite = bool(entry.get("use_responses_lite") or seed.get("use_responses_lite"))
        _MODEL_TRANSPORT[mid] = {
            "prefer_websockets": prefer_ws,
            "use_responses_lite": use_lite,
        }
        raw_name = entry.get("name") or ""
        if not raw_name or raw_name == mid:
            name = seed.get("name") or _humanize_model_id(mid)
        else:
            name = raw_name
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
    return models


def model_transport_flags(model: str) -> Dict[str, bool]:
    """Return prefer_websockets / use_responses_lite for a bare Codex model id."""
    cached = _MODEL_TRANSPORT.get(model)
    if cached:
        return dict(cached)
    seed = next((s for s in OPENAI_OAUTH_MODEL_SEEDS if s["id"] == model), None)
    if seed:
        return {
            "prefer_websockets": bool(seed.get("prefer_websockets")),
            "use_responses_lite": bool(seed.get("use_responses_lite")),
        }
    # Luna variants always need Responses-Lite over WebSocket.
    if "luna" in model.lower():
        return {"prefer_websockets": True, "use_responses_lite": True}
    return {"prefer_websockets": False, "use_responses_lite": False}


def model_needs_responses_lite(model: str) -> bool:
    """True when inference must use the Codex WebSocket transport."""
    flags = model_transport_flags(model)
    return bool(flags.get("prefer_websockets") or flags.get("use_responses_lite"))


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

        flags = model_transport_flags(model)
        if flags.get("prefer_websockets") or flags.get("use_responses_lite"):
            try:
                return await query_codex_responses_websocket(
                    payload=payload,
                    headers=headers,
                    timeout=timeout,
                    use_responses_lite=bool(flags.get("use_responses_lite")),
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
                # Codex-specific listing — requires client_version or returns 400.
                # Do NOT fall back to chatgpt.com/backend-api/models: that catalog
                # includes ChatGPT-web (-wm) slugs that Codex rejects at inference.
                codex_resp = await client.get(
                    CHATGPT_CODEX_MODELS_URL,
                    headers=headers,
                    params={"client_version": CODEX_MODELS_CLIENT_VERSION},
                )
                if codex_resp.status_code == 200:
                    entries = _parse_chatgpt_model_entries(codex_resp.json())
                    models = _entries_to_models(entries)
                    if models:
                        return models
                else:
                    logger.warning(
                        "ChatGPT Codex model list failed (%s); using seeds",
                        codex_resp.status_code,
                    )
        except Exception:
            logger.debug("ChatGPT OAuth live model fetch failed; using seeds", exc_info=True)

        return _seed_models()

    async def validate_key(self, api_key: str) -> Dict[str, Any]:
        if get_oauth_credential("openai-oauth"):
            return {"success": True, "message": "ChatGPT OAuth connected"}
        return {"success": False, "message": "ChatGPT OAuth not connected"}
