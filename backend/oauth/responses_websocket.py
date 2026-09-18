"""Codex Responses WebSocket transport (ChatGPT OAuth).

Some ChatGPT Codex models are only served over
wss://chatgpt.com/backend-api/codex/responses (prefer_websockets).
Models also flagged use_responses_lite (e.g. gpt-5.6-luna) need the
Responses-Lite headers and request shape. Mirrors relay-ai's
responses-websocket transport, scoped to text completion.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import websockets
from websockets.exceptions import WebSocketException

logger = logging.getLogger(__name__)

CODEX_RESPONSES_WS_URL = "wss://chatgpt.com/backend-api/codex/responses"
CODEX_RESPONSES_LITE_VERSION = "0.153.4"
CODEX_RESPONSES_WEBSOCKETS_BETA = "responses_websockets=2026-02-06"
RESPONSES_LITE_HEADER = "x-openai-internal-codex-responses-lite"

# Back-compat aliases used by older imports/tests.
CODEX_RESPONSES_LITE_WS_URL = CODEX_RESPONSES_WS_URL

TERMINAL_EVENT_TYPES = frozenset(
    {"response.completed", "response.failed", "response.incomplete", "error"}
)


def apply_responses_lite_shape(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Fold Responses-Lite request fields into the outgoing payload."""
    reasoning = payload.get("reasoning")
    if isinstance(reasoning, dict):
        reasoning = {**reasoning, "context": "all_turns"}
    else:
        reasoning = {"context": "all_turns"}
    return {
        **payload,
        "reasoning": reasoning,
        "parallel_tool_calls": False,
        "store": False,
    }


def _extract_text_from_event(event: Dict[str, Any], text_parts: List[str]) -> Optional[Any]:
    """Append text deltas; return usage when present on a completed response."""
    etype = event.get("type") or ""
    usage = None
    if etype in ("response.output_text.delta", "response.text.delta"):
        delta = event.get("delta") or ""
        if delta:
            text_parts.append(str(delta))
    elif etype == "response.completed":
        resp = event.get("response") or {}
        if isinstance(resp, dict):
            usage = resp.get("usage") or event.get("usage")
            if not text_parts:
                output_text = resp.get("output_text")
                if isinstance(output_text, str) and output_text:
                    text_parts.append(output_text)
                else:
                    for item in resp.get("output") or []:
                        if not isinstance(item, dict):
                            continue
                        for part in item.get("content") or []:
                            if not isinstance(part, dict):
                                continue
                            text = part.get("text") or part.get("output_text")
                            if text:
                                text_parts.append(str(text))
    return usage


async def query_codex_responses_websocket(
    *,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    timeout: float = 120.0,
    use_responses_lite: bool = False,
    ws_url: str = CODEX_RESPONSES_WS_URL,
) -> Dict[str, Any]:
    """Run one Responses request over the Codex WebSocket transport.

    Returns the same shape as HTTP ChatGPT OAuth queries:
    ``{content, usage, error}`` or ``{error: True, error_message}``.
    """
    ws_headers = {
        **headers,
        "OpenAI-Beta": CODEX_RESPONSES_WEBSOCKETS_BETA,
    }
    if use_responses_lite:
        ws_headers["version"] = CODEX_RESPONSES_LITE_VERSION
        ws_headers[RESPONSES_LITE_HEADER] = "true"
    # Content-Type is HTTP-only; strip before WS handshake.
    ws_headers.pop("Content-Type", None)
    ws_headers.pop("content-type", None)

    body = dict(payload)
    if use_responses_lite:
        body = apply_responses_lite_shape(body)
    # WS protocol is event-tagged; stream is implied by the transport.
    body.pop("stream", None)
    outgoing = json.dumps({"type": "response.create", **body})

    text_parts: List[str] = []
    usage = None
    try:
        async with websockets.connect(
            ws_url,
            additional_headers=ws_headers,
            open_timeout=min(30.0, timeout),
            close_timeout=10.0,
            max_size=8 * 1024 * 1024,
        ) as ws:
            await ws.send(outgoing)
            while True:
                try:
                    raw = await asyncio_wait_for_recv(ws, timeout)
                except TimeoutError:
                    return {
                        "error": True,
                        "error_message": f"ChatGPT OAuth WebSocket timed out after {timeout}s",
                    }
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    logger.debug("Non-JSON Codex WS frame (%s chars)", len(raw))
                    continue
                if not isinstance(event, dict):
                    continue

                event_usage = _extract_text_from_event(event, text_parts)
                if event_usage is not None:
                    usage = event_usage

                etype = event.get("type") or ""
                if etype == "error" or etype == "response.failed":
                    err = event.get("error") or {}
                    msg = (
                        err.get("message")
                        if isinstance(err, dict)
                        else None
                    ) or event.get("message") or "ChatGPT OAuth WebSocket error"
                    return {"error": True, "error_message": str(msg)}
                if etype in TERMINAL_EVENT_TYPES:
                    break
    except WebSocketException as exc:
        return {"error": True, "error_message": f"ChatGPT OAuth WebSocket error: {exc}"}
    except OSError as exc:
        return {"error": True, "error_message": f"ChatGPT OAuth WebSocket connection failed: {exc}"}

    content = "".join(text_parts)
    if not content:
        return {"error": True, "error_message": "ChatGPT OAuth WebSocket returned empty response"}
    return {"content": content, "usage": usage, "error": False}


# Back-compat name used by earlier tests/imports.
async def query_responses_lite_websocket(
    *,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    timeout: float = 120.0,
    ws_url: str = CODEX_RESPONSES_WS_URL,
) -> Dict[str, Any]:
    return await query_codex_responses_websocket(
        payload=payload,
        headers=headers,
        timeout=timeout,
        use_responses_lite=True,
        ws_url=ws_url,
    )


async def asyncio_wait_for_recv(ws: Any, timeout: float) -> str:
    """Receive one WS message with a timeout (isolated for easy mocking)."""
    return await asyncio.wait_for(ws.recv(), timeout=timeout)
