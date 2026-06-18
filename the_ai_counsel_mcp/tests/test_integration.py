"""End-to-end integration tests for The AI Counsel MCP server.

These tests verify complete workflows: MCP tool → CouncilClient → SSE stream buffer → result.
All HTTP calls are mocked via respx.

Unlike the per-tool unit tests, each test here exercises an entire user-facing scenario
from tool invocation through conversation creation, SSE streaming, and result parsing.
"""

import json
import pytest
import respx
import httpx
from the_ai_counsel_mcp.server import create_server


BASE_URL = "http://test:8001"


# ── SSE event sequence fixtures ─────────────────────────────────────────────────

def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


STAGE1_EVENTS = (
    _sse({"type": "stage1_start"})
    + _sse({"type": "stage1_init", "total": 2})
    + _sse({"type": "stage1_progress", "data": {
        "model": "openai:gpt-4.1",
        "response": "Paris is the capital of France.",
        "error": None,
    }, "count": 1, "total": 2})
    + _sse({"type": "stage1_progress", "data": {
        "model": "anthropic:claude-sonnet-4",
        "response": "The capital of France is Paris.",
        "error": None,
    }, "count": 2, "total": 2})
    + _sse({"type": "stage1_complete", "data": [
        {"model": "openai:gpt-4.1", "response": "Paris is the capital of France.", "error": None},
        {"model": "anthropic:claude-sonnet-4", "response": "The capital of France is Paris.", "error": None},
    ]})
)

FULL_DELIBERATION_EVENTS = (
    STAGE1_EVENTS
    + _sse({"type": "stage2_start"})
    + _sse({"type": "stage2_init", "total": 2})
    + _sse({"type": "stage2_progress", "data": {
        "model": "openai:gpt-4.1",
        "ranking": "FINAL RANKING:\n1. Response B\n2. Response A",
        "parsed_ranking": ["Response B", "Response A"],
        "error": None,
    }, "count": 1, "total": 2})
    + _sse({"type": "stage2_progress", "data": {
        "model": "anthropic:claude-sonnet-4",
        "ranking": "FINAL RANKING:\n1. Response A\n2. Response B",
        "parsed_ranking": ["Response A", "Response B"],
        "error": None,
    }, "count": 2, "total": 2})
    + _sse({"type": "stage2_complete", "data": [
        {
            "model": "openai:gpt-4.1",
            "ranking": "FINAL RANKING:\n1. Response B\n2. Response A",
            "parsed_ranking": ["Response B", "Response A"],
            "error": None,
        },
        {
            "model": "anthropic:claude-sonnet-4",
            "ranking": "FINAL RANKING:\n1. Response A\n2. Response B",
            "parsed_ranking": ["Response A", "Response B"],
            "error": None,
        },
    ], "metadata": {
        "label_to_model": {
            "Response A": "openai:gpt-4.1",
            "Response B": "anthropic:claude-sonnet-4",
        },
        "aggregate_rankings": [
            {"model": "openai:gpt-4.1", "average_rank": 1.5, "rankings_count": 2},
            {"model": "anthropic:claude-sonnet-4", "average_rank": 1.5, "rankings_count": 2},
        ],
        "search_query": "",
        "search_context": "",
    }})
    + _sse({"type": "stage3_start"})
    + _sse({"type": "stage3_complete", "data": {
        "model": "anthropic:claude-sonnet-4",
        "response": "France's capital is Paris, universally agreed upon by all council members.",
        "error": False,
    }})
    + _sse({"type": "complete"})
)


# ── Helpers ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def server():
    return create_server(base_url=BASE_URL)


from the_ai_counsel_mcp.tests.conftest import get_json


# ── Integration: full deliberation workflow ─────────────────────────────────────

@pytest.mark.asyncio
async def test_full_deliberation_workflow(server):
    """Complete run_deliberation: create conversation → stream all stages → return chairman answer."""
    with respx.mock:
        respx.post(f"{BASE_URL}/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "conv-integration-1", "title": ""})
        )
        respx.post(f"{BASE_URL}/api/conversations/conv-integration-1/message/stream").mock(
            return_value=httpx.Response(
                200,
                text=FULL_DELIBERATION_EVENTS,
                headers={"content-type": "text/event-stream"},
            )
        )
        result = await server.call_tool("council_deliberate", {"action": "full", "query": "What is the capital of France?"})

    data = get_json(result)
    assert data["conversation_id"] == "conv-integration-1"
    assert data["chairman_answer"] == "France's capital is Paris, universally agreed upon by all council members."
    assert data["stage1"]["summary"]["succeeded"] == 2
    assert data["stage1"]["summary"]["failed"] == 0
    assert data["stage2"]["label_to_model"] == {
        "Response A": "openai:gpt-4.1",
        "Response B": "anthropic:claude-sonnet-4",
    }
    assert data["stage3"]["status"] == "success"
    assert data["stage3"]["synthesis"] == "France's capital is Paris, universally agreed upon by all council members."


@pytest.mark.asyncio
async def test_stage1_only_workflow(server):
    """run_stage1 returns individual responses without running stage 2 or 3."""
    stage1_only_events = STAGE1_EVENTS + _sse({"type": "complete"})
    with respx.mock:
        respx.post(f"{BASE_URL}/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "conv-s1", "title": ""})
        )
        respx.post(f"{BASE_URL}/api/conversations/conv-s1/message/stream").mock(
            return_value=httpx.Response(
                200,
                text=stage1_only_events,
                headers={"content-type": "text/event-stream"},
            )
        )
        result = await server.call_tool("council_deliberate", {"action": "stage1", "query": "What is the capital of France?"})

    data = get_json(result)
    assert data["conversation_id"] == "conv-s1"
    assert data["summary"]["total"] == 2
    assert data["summary"]["succeeded"] == 2
    assert data["summary"]["failed"] == 0
    assert len(data["results"]) == 2
    assert data["results"][0]["model"] == "openai:gpt-4.1"
    assert data["results"][0]["response"] == "Paris is the capital of France."
    assert data["results"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_deliberation_with_one_model_failure(server):
    """run_deliberation correctly classifies a rate-limited model as failed."""
    events = (
        _sse({"type": "stage1_complete", "data": [
            {"model": "openai:gpt-4.1", "response": "Paris", "error": None},
            {"model": "ollama:llama3", "response": None, "error": True,
             "error_message": "429 Too Many Requests"},
        ]})
        + _sse({"type": "stage2_complete", "data": [], "metadata": {
            "label_to_model": {},
            "aggregate_rankings": [],
            "search_query": "",
            "search_context": "",
        }})
        + _sse({"type": "stage3_complete", "data": {
            "model": "anthropic:claude-sonnet-4",
            "response": "Paris",
            "error": False,
        }})
        + _sse({"type": "complete"})
    )
    with respx.mock:
        respx.post(f"{BASE_URL}/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "conv-fail", "title": ""})
        )
        respx.post(f"{BASE_URL}/api/conversations/conv-fail/message/stream").mock(
            return_value=httpx.Response(
                200,
                text=events,
                headers={"content-type": "text/event-stream"},
            )
        )
        result = await server.call_tool("council_deliberate", {"action": "full", "query": "test"})

    data = get_json(result)
    assert data["stage1"]["summary"]["failed"] == 1
    failed = next(r for r in data["stage1"]["results"] if r["status"] == "error")
    assert failed["error"]["type"] == "rate_limit"
    assert failed["error"]["retryable"] is True


@pytest.mark.asyncio
async def test_quick_chat_workflow(server):
    """quick_chat uses /api/ask — no settings mutation."""
    ask_calls = []

    def capture_ask(request):
        ask_calls.append(json.loads(request.content))
        return httpx.Response(200, json={
            "response": "42",
            "model": "openai:gpt-4.1",
            "error": None,
        })

    with respx.mock:
        respx.post(f"{BASE_URL}/api/ask").mock(side_effect=capture_ask)
        result = await server.call_tool("model_chat", {"action": "quick", "query": "What is 6x7?", "model": "openai:gpt-4.1"})

    data = get_json(result)
    assert data["response"] == "42"
    assert data["model"] == "openai:gpt-4.1"
    assert data.get("error") is None

    # Verify /api/ask was called with correct params
    assert len(ask_calls) == 1
    assert ask_calls[0]["models"] == ["openai:gpt-4.1"]
    assert ask_calls[0]["execution_mode"] == "chat_only"


@pytest.mark.asyncio
async def test_health_check_integration(server):
    """check_health returns backend status and provider configuration."""
    with respx.mock:
        respx.get(f"{BASE_URL}/api/health").mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )
        respx.get(f"{BASE_URL}/api/settings").mock(
            return_value=httpx.Response(200, json={
                "council_models": ["openai:gpt-4.1"],
                "chairman_model": "anthropic:claude-sonnet-4",
                "execution_mode": "full",
                "search_provider": "duckduckgo",
                "ollama_base_url": "http://localhost:11434",
                "openai_api_key_set": True,
                "anthropic_api_key_set": True,
                "tinyfish_api_key_set": False,
            })
        )
        result = await server.call_tool("providers", {"action": "health"})

    data = get_json(result)
    assert data["backend"] == "reachable"
    assert "openai" in data["configured_providers"]
    assert "anthropic" in data["configured_providers"]
    assert "tinyfish" not in data["configured_providers"]
    assert data["search_provider"] == "duckduckgo"
    assert data["base_url"] == BASE_URL


@pytest.mark.asyncio
async def test_council_config_roundtrip(server):
    """configure_council → get_council_config reflects the update."""
    with respx.mock:
        respx.put(f"{BASE_URL}/api/settings").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        update_result = await server.call_tool("council_settings", {"action": "update", 
            "models": ["openai:gpt-4.1", "anthropic:claude-sonnet-4", "groq:llama3-70b-8192"],
            "execution_mode": "full",
        })
    update_data = get_json(update_result)
    assert update_data["status"] == "updated"
    assert "council_models" in update_data["fields"]
    assert "execution_mode" in update_data["fields"]

    with respx.mock:
        respx.get(f"{BASE_URL}/api/settings").mock(
            return_value=httpx.Response(200, json={
                "council_models": ["openai:gpt-4.1", "anthropic:claude-sonnet-4", "groq:llama3-70b-8192"],
                "chairman_model": "anthropic:claude-sonnet-4",
                "council_temperature": 0.5,
                "chairman_temperature": 0.4,
                "stage2_temperature": 0.3,
                "execution_mode": "full",
                "search_provider": "duckduckgo",
            })
        )
        config_result = await server.call_tool("council_settings", {"action": "get"})
    config = get_json(config_result)
    assert len(config["council_models"]) == 3
    assert config["execution_mode"] == "full"
    assert "openai:gpt-4.1" in config["council_models"]


@pytest.mark.asyncio
async def test_deliberation_model_override_uses_per_request(server):
    """run_deliberation passes model overrides in stream payload, no settings mutation."""
    stream_calls = []

    def capture_stream(request):
        stream_calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            text=FULL_DELIBERATION_EVENTS,
            headers={"content-type": "text/event-stream"},
        )

    with respx.mock:
        respx.post(f"{BASE_URL}/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "conv-override", "title": ""})
        )
        respx.post(f"{BASE_URL}/api/conversations/conv-override/message/stream").mock(
            side_effect=capture_stream
        )
        override_models = ["groq:llama3-70b-8192", "ollama:llama3"]
        result = await server.call_tool("council_deliberate", {"action": "full", 
            "query": "test override",
            "models": override_models,
        })
        data = get_json(result)

    # council_models passed in stream body, no PUT to settings
    assert len(stream_calls) == 1
    assert stream_calls[0]["council_models"] == override_models
    assert data["chairman_answer"] is not None


@pytest.mark.asyncio
async def test_deliberation_model_override_no_settings_on_exception(server):
    """run_deliberation does not touch settings even on stream failure."""
    with respx.mock:
        respx.post(f"{BASE_URL}/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "conv-exc", "title": ""})
        )
        respx.post(f"{BASE_URL}/api/conversations/conv-exc/message/stream").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        result = await server.call_tool("council_deliberate", {"action": "full", 
            "query": "test",
            "models": ["groq:llama3-70b-8192", "ollama:llama3"],
        })
        data = get_json(result)
        assert data["status"] == "error"


@pytest.mark.asyncio
async def test_web_search_context_flows_through_to_result(server):
    """run_stage1 with web_search=True captures and returns search context."""
    search_events = (
        _sse({"type": "search_complete", "data": {
            "search_context": "France is a country in Western Europe. Paris is its capital.",
            "search_query": "capital of France",
        }})
        + _sse({"type": "stage1_complete", "data": [
            {"model": "openai:gpt-4.1", "response": "Paris is the capital.", "error": None},
        ]})
        + _sse({"type": "complete"})
    )
    with respx.mock:
        respx.post(f"{BASE_URL}/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "conv-ws", "title": ""})
        )
        respx.post(f"{BASE_URL}/api/conversations/conv-ws/message/stream").mock(
            return_value=httpx.Response(
                200,
                text=search_events,
                headers={"content-type": "text/event-stream"},
            )
        )
        result = await server.call_tool("council_deliberate", {"action": "stage1", 
            "query": "What is the capital of France?",
            "web_search": True,
        })

    data = get_json(result)
    assert data["web_search"] is True
    assert "France" in data["search_context"]
    assert data["results"][0]["response"] == "Paris is the capital."


@pytest.mark.asyncio
async def test_stage2_rankings_aggregate_correctly(server):
    """run_stage2 drains stage1 events, collects rankings, returns aggregate scores."""
    stage1_plus_stage2 = (
        _sse({"type": "stage1_start"})
        + _sse({"type": "stage1_complete", "data": [
            {"model": "openai:gpt-4.1", "response": "Answer A", "error": None},
            {"model": "anthropic:claude-sonnet-4", "response": "Answer B", "error": None},
        ]})
        + _sse({"type": "stage2_start"})
        + _sse({"type": "stage2_complete", "data": [
            {
                "model": "openai:gpt-4.1",
                "ranking": "FINAL RANKING:\n1. Response B\n2. Response A",
                "parsed_ranking": ["Response B", "Response A"],
                "error": None,
            },
            {
                "model": "anthropic:claude-sonnet-4",
                "ranking": "FINAL RANKING:\n1. Response B\n2. Response A",
                "parsed_ranking": ["Response B", "Response A"],
                "error": None,
            },
        ], "metadata": {
            "label_to_model": {
                "Response A": "openai:gpt-4.1",
                "Response B": "anthropic:claude-sonnet-4",
            },
            "aggregate_rankings": [
                {"model": "anthropic:claude-sonnet-4", "average_rank": 1.0, "rankings_count": 2},
                {"model": "openai:gpt-4.1", "average_rank": 2.0, "rankings_count": 2},
            ],
        }})
        + _sse({"type": "complete"})
    )
    with respx.mock:
        respx.post(f"{BASE_URL}/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "conv-s2-agg", "title": ""})
        )
        respx.post(f"{BASE_URL}/api/conversations/conv-s2-agg/message/stream").mock(
            return_value=httpx.Response(
                200,
                text=stage1_plus_stage2,
                headers={"content-type": "text/event-stream"},
            )
        )
        result = await server.call_tool("council_deliberate", {"action": "stage2", "query": "Which approach is better?"})

    data = get_json(result)
    assert data["conversation_id"] == "conv-s2-agg"
    assert len(data["rankings"]) == 2
    assert len(data["aggregate_rankings"]) == 2
    # anthropic ranked #1 by both rankers → average_rank 1.0 wins
    top = data["aggregate_rankings"][0]
    assert top["model"] == "anthropic:claude-sonnet-4"
    assert top["average_rank"] == 1.0
    assert "label_to_model" in data


@pytest.mark.asyncio
async def test_quick_chat_no_response_returns_error(server):
    """quick_chat propagates 502 from /api/ask when all models fail."""
    with respx.mock:
        respx.post(f"{BASE_URL}/api/ask").mock(
            return_value=httpx.Response(502, json={"detail": "All models failed: timeout"})
        )

        result = await server.call_tool("model_chat", {"action": "quick", 
            "query": "test",
            "model": "openai:gpt-4.1",
        })
        data = get_json(result)
        assert data["status"] == "error"
