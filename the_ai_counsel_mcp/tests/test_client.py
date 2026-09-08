import json

import httpx
import pytest
import respx

from the_ai_counsel_mcp.client import CouncilClient

# Mock against the client's own default so these tests follow PORT_BACKEND.
BASE = CouncilClient().base_url


@pytest.mark.asyncio
async def test_health_check():
    with respx.mock:
        respx.get(f"{BASE}/api/health").mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )
        async with CouncilClient() as client:
            result = await client.health()
        assert result == {"status": "ok"}


@pytest.mark.asyncio
async def test_get_settings():
    with respx.mock:
        respx.get(f"{BASE}/api/settings").mock(
            return_value=httpx.Response(200, json={"council_models": ["openai:gpt-4.1"]})
        )
        async with CouncilClient() as client:
            result = await client.get_settings()
        assert result["council_models"] == ["openai:gpt-4.1"]


@pytest.mark.asyncio
async def test_update_settings():
    with respx.mock:
        respx.put(f"{BASE}/api/settings").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        async with CouncilClient() as client:
            result = await client.update_settings(council_temperature=0.7)
        assert result == {"success": True}


@pytest.mark.asyncio
async def test_list_conversations():
    with respx.mock:
        respx.get(f"{BASE}/api/conversations").mock(
            return_value=httpx.Response(200, json=[{"id": "abc", "title": "Test"}])
        )
        async with CouncilClient() as client:
            result = await client.list_conversations()
        assert result[0]["id"] == "abc"


@pytest.mark.asyncio
async def test_create_conversation():
    with respx.mock:
        respx.post(f"{BASE}/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "new-id", "title": ""})
        )
        async with CouncilClient() as client:
            result = await client.create_conversation()
        assert result["id"] == "new-id"


@pytest.mark.asyncio
async def test_ollama_models_returns_empty_on_error():
    with respx.mock:
        respx.get(f"{BASE}/api/ollama/tags").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        async with CouncilClient() as client:
            result = await client.get_ollama_models()
        assert result == []


@pytest.mark.asyncio
async def test_stream_message_yields_events():
    sse_body = (
        "data: {\"type\": \"stage1_start\"}\n\n"
        "data: {\"type\": \"stage1_complete\", \"data\": []}\n\n"
        "data: {\"type\": \"complete\"}\n\n"
    )
    with respx.mock:
        respx.post(
            f"{BASE}/api/conversations/conv-1/message/stream"
        ).mock(
            return_value=httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})
        )
        events = []
        async with CouncilClient() as client:
            async for event in client.stream_message("conv-1", "hello"):
                events.append(event)
    assert len(events) == 3
    assert events[0]["type"] == "stage1_start"
    assert events[2]["type"] == "complete"


@pytest.mark.asyncio
async def test_export_settings():
    with respx.mock:
        respx.get(f"{BASE}/api/settings/export").mock(
            return_value=httpx.Response(200, json={"council_models": ["openai:gpt-4.1"], "openai_api_key": "sk-test"})
        )
        async with CouncilClient() as client:
            data = await client.export_settings()
        assert data["council_models"] == ["openai:gpt-4.1"]
        assert data["openai_api_key"] == "sk-test"


@pytest.mark.asyncio
async def test_import_settings():
    with respx.mock:
        respx.post(f"{BASE}/api/settings/import").mock(
            return_value=httpx.Response(200, json={"status": "imported"})
        )
        async with CouncilClient() as client:
            result = await client.import_settings({"council_models": ["openai:gpt-4.1", "anthropic:claude-sonnet-4"]})
        assert result["status"] == "imported"


@pytest.mark.asyncio
async def test_reset_settings():
    with respx.mock:
        respx.post(f"{BASE}/api/settings/reset").mock(
            return_value=httpx.Response(200, json={"status": "reset"})
        )
        async with CouncilClient() as client:
            result = await client.reset_settings()
        assert result["status"] == "reset"


# ── Persona client methods ────────────────────────────────────────────────────

PERSONAS = [
    {"id": "skeptic", "name": "The Skeptic", "role": "Critical Thinker",
     "avatar_emoji": "🔍", "color": "#ef4444", "is_customized": False},
    {"id": "pragmatist", "name": "The Pragmatist", "role": "Practical Thinker",
     "avatar_emoji": "🔧", "color": "#f59e0b", "is_customized": False},
]


@pytest.mark.asyncio
async def test_get_personas_returns_list():
    with respx.mock:
        respx.get(f"{BASE}/api/personas").mock(
            return_value=httpx.Response(200, json=PERSONAS)
        )
        async with CouncilClient() as client:
            result = await client.get_personas()
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["id"] == "skeptic"


@pytest.mark.asyncio
async def test_get_personas_raises_on_error():
    with respx.mock:
        respx.get(f"{BASE}/api/personas").mock(
            return_value=httpx.Response(500)
        )
        with pytest.raises(httpx.HTTPStatusError):
            async with CouncilClient() as client:
                await client.get_personas()


@pytest.mark.asyncio
async def test_update_persona_sends_patch():
    updated = {**PERSONAS[0], "name": "Super Skeptic", "is_customized": True}
    with respx.mock:
        route = respx.patch(f"{BASE}/api/personas/skeptic").mock(
            return_value=httpx.Response(200, json=updated)
        )
        async with CouncilClient() as client:
            result = await client.update_persona("skeptic", name="Super Skeptic")
    assert result["name"] == "Super Skeptic"
    assert route.called
    sent = json.loads(route.calls[0].request.content)
    assert sent == {"name": "Super Skeptic"}


@pytest.mark.asyncio
async def test_update_persona_not_found_raises():
    with respx.mock:
        respx.patch(f"{BASE}/api/personas/ghost").mock(
            return_value=httpx.Response(404)
        )
        with pytest.raises(httpx.HTTPStatusError):
            async with CouncilClient() as client:
                await client.update_persona("ghost", name="Ghost")


@pytest.mark.asyncio
async def test_reset_persona_sends_delete():
    restored = {**PERSONAS[0], "is_customized": False}
    with respx.mock:
        route = respx.delete(f"{BASE}/api/personas/skeptic/override").mock(
            return_value=httpx.Response(200, json=restored)
        )
        async with CouncilClient() as client:
            result = await client.reset_persona("skeptic")
    assert result["is_customized"] is False
    assert route.called


@pytest.mark.asyncio
async def test_reset_persona_not_found_raises():
    with respx.mock:
        respx.delete(f"{BASE}/api/personas/ghost/override").mock(
            return_value=httpx.Response(404)
        )
        with pytest.raises(httpx.HTTPStatusError):
            async with CouncilClient() as client:
                await client.reset_persona("ghost")


# ── stream_debate client method ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stream_debate_yields_events():
    events_data = [
        {"type": "advisor_debate_start", "data": {"personas": [], "max_rounds": 3, "question": "Q?", "web_search": False}},
        {"type": "advisor_complete", "data": {"rounds": [], "consensus_reached": False, "verdict": None, "tiebreaker": None, "personas": []}},
    ]
    sse_body = "".join(f"data: {json.dumps(e)}\n\n" for e in events_data)

    with respx.mock:
        respx.post(f"{BASE}/api/conversations/c1/debate/stream").mock(
            return_value=httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})
        )
        collected = []
        async with CouncilClient() as client:
            async for evt in client.stream_debate("c1", "Q?", ["skeptic", "pragmatist"]):
                collected.append(evt)

    assert len(collected) == 2
    assert collected[0]["type"] == "advisor_debate_start"
    assert collected[1]["type"] == "advisor_complete"


@pytest.mark.asyncio
async def test_stream_debate_sends_correct_payload():
    sse_body = "data: {\"type\": \"advisor_complete\", \"data\": {}}\n\n"

    with respx.mock:
        route = respx.post(f"{BASE}/api/conversations/c2/debate/stream").mock(
            return_value=httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})
        )
        async with CouncilClient() as client:
            async for _ in client.stream_debate(
                "c2", "Test?", ["skeptic", "pragmatist"],
                default_model="openai:gpt-4.1",
                max_rounds=3,
                search_provider="duckduckgo",
            ):
                pass

    sent = json.loads(route.calls[0].request.content)
    assert sent["question"] == "Test?"
    assert sent["persona_ids"] == ["skeptic", "pragmatist"]
    assert sent["default_model"] == "openai:gpt-4.1"
    assert sent["max_rounds"] == 3
    assert sent["web_search"] is True
    assert sent["search_provider"] == "duckduckgo"


@pytest.mark.asyncio
async def test_stream_debate_skips_invalid_json_lines():
    sse_body = (
        "data: not-valid-json\n\n"
        "data: {\"type\": \"advisor_debate_start\", \"data\": {}}\n\n"
    )
    with respx.mock:
        respx.post(f"{BASE}/api/conversations/c3/debate/stream").mock(
            return_value=httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})
        )
        collected = []
        async with CouncilClient() as client:
            async for evt in client.stream_debate("c3", "Q?", ["skeptic", "pragmatist"]):
                collected.append(evt)

    assert len(collected) == 1
    assert collected[0]["type"] == "advisor_debate_start"
