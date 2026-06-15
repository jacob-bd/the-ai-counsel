"""Tests for advisor and persona MCP tools."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from the_ai_counsel_mcp.server import create_server
from the_ai_counsel_mcp.tests.conftest import get_json, get_text


@pytest.fixture
def server():
    return create_server(base_url="http://test:8001")


PERSONAS = [
    {"id": "skeptic", "name": "The Skeptic", "role": "Critical Thinker",
     "description": "Challenges assumptions.", "system_prompt": "You are The Skeptic.",
     "avatar_emoji": "🔍", "color": "#ef4444", "is_customized": False},
    {"id": "pragmatist", "name": "The Pragmatist", "role": "Practical Thinker",
     "description": "Focuses on what works.", "system_prompt": "You are The Pragmatist.",
     "avatar_emoji": "🔧", "color": "#f59e0b", "is_customized": False},
]

ADVISOR_SETTINGS = {
    "advisor_default_model": "openai:gpt-4.1",
    "advisor_tiebreaker_model": "",
    "advisor_temperature": 0.7,
    "advisor_default_rounds": 3,
    "advisor_presets": [],
    "council_models": ["openai:gpt-4.1"],
}


# ── list_personas ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_personas_success(server):
    with respx.mock:
        respx.get("http://test:8001/api/personas").mock(
            return_value=httpx.Response(200, json=PERSONAS)
        )
        result = await server.call_tool("personas", {"action": "list"})
        data = get_json(result)
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["id"] == "skeptic"
    assert data[1]["id"] == "pragmatist"


@pytest.mark.asyncio
async def test_list_personas_backend_error(server):
    with respx.mock:
        respx.get("http://test:8001/api/personas").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        result = await server.call_tool("personas", {"action": "list"})
        text = get_text(result)
    assert "Error" in text


# ── get_persona ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_persona_found(server):
    with respx.mock:
        respx.get("http://test:8001/api/personas").mock(
            return_value=httpx.Response(200, json=PERSONAS)
        )
        result = await server.call_tool("personas", {"action": "get", "persona_id": "skeptic"})
        data = get_json(result)
    assert data["id"] == "skeptic"
    assert data["name"] == "The Skeptic"
    assert "system_prompt" in data


@pytest.mark.asyncio
async def test_get_persona_not_found(server):
    with respx.mock:
        respx.get("http://test:8001/api/personas").mock(
            return_value=httpx.Response(200, json=PERSONAS)
        )
        result = await server.call_tool("personas", {"action": "get", "persona_id": "nonexistent"})
        text = get_text(result)
    assert "not found" in text.lower()


# ── update_persona ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_persona_name_only(server):
    updated = {**PERSONAS[0], "name": "Super Skeptic", "is_customized": True}
    with respx.mock:
        respx.patch("http://test:8001/api/personas/skeptic").mock(
            return_value=httpx.Response(200, json=updated)
        )
        result = await server.call_tool("personas", {"action": "update", 
            "persona_id": "skeptic",
            "name": "Super Skeptic",
        })
        data = get_json(result)
    assert data["name"] == "Super Skeptic"
    assert data["is_customized"] is True


@pytest.mark.asyncio
async def test_update_persona_system_prompt(server):
    updated = {**PERSONAS[0], "system_prompt": "New prompt", "is_customized": True}
    with respx.mock:
        respx.patch("http://test:8001/api/personas/skeptic").mock(
            return_value=httpx.Response(200, json=updated)
        )
        result = await server.call_tool("personas", {"action": "update", 
            "persona_id": "skeptic",
            "system_prompt": "New prompt",
        })
        data = get_json(result)
    assert data["system_prompt"] == "New prompt"


@pytest.mark.asyncio
async def test_update_persona_no_fields_provided(server):
    result = await server.call_tool("personas", {"action": "update", "persona_id": "skeptic"})
    text = get_text(result)
    assert "provide at least one field" in text


@pytest.mark.asyncio
async def test_update_persona_not_found(server):
    with respx.mock:
        respx.patch("http://test:8001/api/personas/ghost").mock(
            return_value=httpx.Response(404, json={"detail": "Persona not found"})
        )
        result = await server.call_tool("personas", {"action": "update", 
            "persona_id": "ghost",
            "name": "Ghost",
        })
        data = get_json(result)
    assert data["status"] == "error"


# ── reset_persona ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reset_persona_success(server):
    restored = {**PERSONAS[0], "is_customized": False}
    with respx.mock:
        respx.delete("http://test:8001/api/personas/skeptic/override").mock(
            return_value=httpx.Response(200, json=restored)
        )
        result = await server.call_tool("personas", {"action": "reset", "persona_id": "skeptic"})
        data = get_json(result)
    assert data["is_customized"] is False
    assert data["id"] == "skeptic"


@pytest.mark.asyncio
async def test_reset_persona_not_found(server):
    with respx.mock:
        respx.delete("http://test:8001/api/personas/ghost/override").mock(
            return_value=httpx.Response(404, json={"detail": "Persona not found"})
        )
        result = await server.call_tool("personas", {"action": "reset", "persona_id": "ghost"})
        data = get_json(result)
    assert data["status"] == "error"


# ── get_advisor_config ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_advisor_config_returns_only_advisor_fields(server):
    with respx.mock:
        respx.get("http://test:8001/api/settings").mock(
            return_value=httpx.Response(200, json=ADVISOR_SETTINGS)
        )
        result = await server.call_tool("advisor_settings", {"action": "get"})
        data = get_json(result)
    assert "advisor_default_model" in data
    assert "advisor_tiebreaker_model" in data
    assert "advisor_temperature" in data
    assert "advisor_default_rounds" in data
    assert "advisor_presets" in data
    # Council fields should NOT be included
    assert "council_models" not in data


@pytest.mark.asyncio
async def test_get_advisor_config_values(server):
    with respx.mock:
        respx.get("http://test:8001/api/settings").mock(
            return_value=httpx.Response(200, json=ADVISOR_SETTINGS)
        )
        result = await server.call_tool("advisor_settings", {"action": "get"})
        data = get_json(result)
    assert data["advisor_default_model"] == "openai:gpt-4.1"
    assert data["advisor_temperature"] == 0.7
    assert data["advisor_default_rounds"] == 3


# ── configure_advisors ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_configure_advisors_single_field(server):
    with respx.mock:
        respx.get("http://test:8001/api/settings").mock(
            return_value=httpx.Response(200, json=ADVISOR_SETTINGS)
        )
        respx.put("http://test:8001/api/settings").mock(
            return_value=httpx.Response(200, json={**ADVISOR_SETTINGS, "advisor_default_rounds": 3})
        )
        result = await server.call_tool("advisor_settings", {"action": "update", "default_rounds": 3})
        text = get_text(result)
    assert "updated" in text.lower()
    assert "advisor_default_rounds" in text


@pytest.mark.asyncio
async def test_configure_advisors_rejects_default_rounds_below_three(server):
    result = await server.call_tool("advisor_settings", {"action": "update", "default_rounds": 2})
    text = get_text(result)
    assert "default_rounds must be between 3 and 10" in text


@pytest.mark.asyncio
async def test_configure_advisors_multiple_fields(server):
    with respx.mock:
        respx.get("http://test:8001/api/settings").mock(
            return_value=httpx.Response(200, json=ADVISOR_SETTINGS)
        )
        respx.put("http://test:8001/api/settings").mock(
            return_value=httpx.Response(200, json=ADVISOR_SETTINGS)
        )
        result = await server.call_tool("advisor_settings", {"action": "update", 
            "default_model": "anthropic:claude-sonnet-4-6",
            "temperature": 0.5,
        })
        text = get_text(result)
    assert "updated" in text.lower()


@pytest.mark.asyncio
async def test_configure_advisors_no_fields_provided(server):
    result = await server.call_tool("advisor_settings", {"action": "update"})
    text = get_text(result)
    assert "no update fields" in text


# ── run_advisor_debate ────────────────────────────────────────────────────────

def _make_debate_sse(question: str = "Test?", consensus: bool = True) -> str:
    """Build a minimal SSE stream body for a debate."""
    personas = [
        {"id": "skeptic", "name": "The Skeptic", "role": "Critical Thinker",
         "avatar_emoji": "🔍", "color": "#ef4444", "is_customized": False},
        {"id": "pragmatist", "name": "The Pragmatist", "role": "Practical Thinker",
         "avatar_emoji": "🔧", "color": "#f59e0b", "is_customized": False},
    ]
    responses = [
        {"persona_id": "skeptic", "persona_name": "The Skeptic", "model": "gpt-4",
         "content": "Skeptic answer", "consensus": consensus, "consensus_score": 5 if consensus else 2},
        {"persona_id": "pragmatist", "persona_name": "The Pragmatist", "model": "gpt-4",
         "content": "Pragmatist answer", "consensus": consensus, "consensus_score": 5 if consensus else 2},
    ]
    consensus_scores = {"skeptic": 5 if consensus else 2, "pragmatist": 5 if consensus else 2}
    events = [
        {"type": "advisor_debate_start", "data": {"personas": personas, "max_rounds": 3, "question": question, "web_search": False}},
        {"type": "advisor_round_complete", "data": {"round_number": 1, "responses": responses, "consensus_votes": {"skeptic": consensus, "pragmatist": consensus}, "consensus_scores": consensus_scores, "average_consensus_score": 5 if consensus else 2, "consensus_reached": consensus}},
        {"type": "advisor_verdict", "data": {"model": "gpt-4", "content": "Final verdict text", "error": None}},
        {"type": "advisor_complete", "data": {
            "rounds": [{"round_number": 1, "responses": responses}],
            "consensus_reached": consensus,
            "verdict": {"model": "gpt-4", "content": "Final verdict text", "error": None},
            "tiebreaker": None,
            "personas": personas,
        }},
    ]
    return "".join(f"data: {json.dumps(e)}\n\n" for e in events)


@pytest.mark.asyncio
async def test_run_advisor_debate_success(server):
    sse_body = _make_debate_sse("What is the best approach?", consensus=True)
    with respx.mock:
        respx.post("http://test:8001/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "debate-conv-1", "title": ""})
        )
        respx.post("http://test:8001/api/conversations/debate-conv-1/debate/stream").mock(
            return_value=httpx.Response(200, text=sse_body,
                                        headers={"content-type": "text/event-stream"})
        )
        result = await server.call_tool("advisor_debate", {
            "question": "What is the best approach?",
            "persona_ids": ["skeptic", "pragmatist"],
        })
        data = get_json(result)

    assert data["status"] == "success"
    assert data["conversation_id"] == "debate-conv-1"
    assert data["question"] == "What is the best approach?"
    assert data["verdict"]["content"] == "Final verdict text"
    assert data["rounds_completed"] == 1
    assert len(data["personas"]) == 2


@pytest.mark.asyncio
async def test_run_advisor_debate_forwards_documents(server):
    stream_calls = []
    documents = [{"name": "brief.txt", "mime_type": "text/plain", "text": "Gamma"}]

    def capture_stream(request):
        stream_calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            text=_make_debate_sse("Should we approve?", consensus=True),
            headers={"content-type": "text/event-stream"},
        )

    with respx.mock:
        respx.post("http://test:8001/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "debate-conv-doc", "title": ""})
        )
        respx.post("http://test:8001/api/conversations/debate-conv-doc/debate/stream").mock(
            side_effect=capture_stream
        )

        result = await server.call_tool("advisor_debate", {
            "question": "Should we approve?",
            "persona_ids": ["skeptic", "pragmatist"],
            "documents": documents,
        })
        data = get_json(result)

    assert data["status"] == "success"
    assert stream_calls[0]["documents"] == documents


@pytest.mark.asyncio
async def test_run_advisor_debate_with_search(server):
    sse_body = (
        "data: " + json.dumps({"type": "advisor_search_start", "data": {"provider": "duckduckgo"}}) + "\n\n"
        + "data: " + json.dumps({"type": "advisor_search_complete", "data": {"search_query": "best approach"}}) + "\n\n"
        + _make_debate_sse("Best approach?", consensus=True)
    )
    with respx.mock:
        respx.post("http://test:8001/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "search-conv", "title": ""})
        )
        respx.post("http://test:8001/api/conversations/search-conv/debate/stream").mock(
            return_value=httpx.Response(200, text=sse_body,
                                        headers={"content-type": "text/event-stream"})
        )
        result = await server.call_tool("advisor_debate", {
            "question": "Best approach?",
            "persona_ids": ["skeptic", "pragmatist"],
            "search_provider": "duckduckgo",
        })
        data = get_json(result)

    assert data["status"] == "success"
    assert data["web_search"] is not None
    assert data["web_search"]["provider"] == "duckduckgo"


@pytest.mark.asyncio
async def test_run_advisor_debate_too_few_personas(server):
    result = await server.call_tool("advisor_debate", {
        "question": "Test?",
        "persona_ids": ["skeptic"],
    })
    text = get_text(result)
    assert "at least 2" in text.lower()


@pytest.mark.asyncio
async def test_run_advisor_debate_too_many_personas(server):
    result = await server.call_tool("advisor_debate", {
        "question": "Test?",
        "persona_ids": ["skeptic", "pragmatist", "innovator", "historian", "ethicist"],
    })
    text = get_text(result)
    assert "at most 4" in text.lower()


@pytest.mark.asyncio
async def test_run_advisor_debate_invalid_rounds(server):
    result = await server.call_tool("advisor_debate", {
        "question": "Test?",
        "persona_ids": ["skeptic", "pragmatist"],
        "max_rounds": 0,
    })
    text = get_text(result)
    assert "3 and 10" in text


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_rounds", [1, 2])
async def test_run_advisor_debate_rejects_rounds_below_three(server, invalid_rounds):
    result = await server.call_tool("advisor_debate", {
        "question": "Test?",
        "persona_ids": ["skeptic", "pragmatist"],
        "max_rounds": invalid_rounds,
    })
    text = get_text(result)
    assert "3 and 10" in text


@pytest.mark.asyncio
async def test_run_advisor_debate_network_error(server):
    with respx.mock:
        respx.post("http://test:8001/api/conversations").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        result = await server.call_tool("advisor_debate", {
            "question": "Test?",
            "persona_ids": ["skeptic", "pragmatist"],
        })
        data = get_json(result)

    assert data["status"] == "error"
    assert data["error"]["retryable"] is True
