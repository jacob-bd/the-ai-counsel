"""Tests for deliberation MCP tools."""

import base64
import json
import pytest
import respx
import httpx
from the_ai_counsel_mcp.server import create_server
from the_ai_counsel_mcp.tests.conftest import get_json


@pytest.fixture
def server():
    return create_server(base_url="http://test:8001")


# ── Helpers to build SSE bodies ────────────────────────────────────────────────

def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _stage1_sse_body(models=None) -> str:
    """Minimal SSE body with stage1_complete."""
    if models is None:
        models = [
            {"model": "openai:gpt-4.1", "response": "Hello from GPT", "error": None},
            {"model": "anthropic:claude-sonnet-4", "response": "Hello from Claude", "error": None},
        ]
    return (
        _sse({"type": "stage1_start"})
        + _sse({"type": "stage1_complete", "data": models})
        + _sse({"type": "complete"})
    )


def _full_deliberation_sse_body() -> str:
    """Full SSE body: stage1 + stage2 + stage3."""
    stage1_models = [
        {"model": "openai:gpt-4.1", "response": "GPT answer", "error": None},
        {"model": "anthropic:claude-sonnet-4", "response": "Claude answer", "error": None},
    ]
    stage2_rankings = [
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
    ]
    stage2_metadata = {
        "label_to_model": {
            "Response A": "openai:gpt-4.1",
            "Response B": "anthropic:claude-sonnet-4",
        },
        "aggregate_rankings": [
            {"model": "openai:gpt-4.1", "average_rank": 1.5, "rankings_count": 2},
            {"model": "anthropic:claude-sonnet-4", "average_rank": 1.5, "rankings_count": 2},
        ],
    }
    stage3_data = {
        "model": "anthropic:claude-opus-4",
        "response": "Synthesized final answer from the chairman.",
        "error": False,
    }
    return (
        _sse({"type": "stage1_start"})
        + _sse({"type": "stage1_complete", "data": stage1_models})
        + _sse({"type": "stage2_start"})
        + _sse({"type": "stage2_complete", "data": stage2_rankings, "metadata": stage2_metadata})
        + _sse({"type": "stage3_start"})
        + _sse({"type": "stage3_complete", "data": stage3_data})
        + _sse({"type": "complete"})
    )


def _stage1_plus_stage2_sse_body() -> str:
    """SSE body for chat_ranking mode: stage1 + stage2."""
    stage1_models = [
        {"model": "openai:gpt-4.1", "response": "GPT answer", "error": None},
        {"model": "anthropic:claude-sonnet-4", "response": "Claude answer", "error": None},
    ]
    stage2_rankings = [
        {
            "model": "openai:gpt-4.1",
            "ranking": "FINAL RANKING:\n1. Response B",
            "parsed_ranking": ["Response B"],
            "error": None,
        },
    ]
    stage2_metadata = {
        "label_to_model": {"Response B": "anthropic:claude-sonnet-4"},
        "aggregate_rankings": [
            {"model": "anthropic:claude-sonnet-4", "average_rank": 1.0, "rankings_count": 1},
        ],
    }
    return (
        _sse({"type": "stage1_start"})
        + _sse({"type": "stage1_complete", "data": stage1_models})
        + _sse({"type": "stage2_start"})
        + _sse({"type": "stage2_complete", "data": stage2_rankings, "metadata": stage2_metadata})
        + _sse({"type": "complete"})
    )


# ── run_stage1 ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_stage1_creates_conversation_and_returns_results(server):
    """run_stage1 creates a new conversation and returns stage1 results."""
    with respx.mock:
        respx.post("http://test:8001/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "conv-s1-1", "title": ""})
        )
        respx.post(
            "http://test:8001/api/conversations/conv-s1-1/message/stream"
        ).mock(
            return_value=httpx.Response(
                200,
                text=_stage1_sse_body(),
                headers={"content-type": "text/event-stream"},
            )
        )
        result = await server.call_tool("council_deliberate", {"action": "stage1", "query": "What is 2+2?"})
        data = get_json(result)

    assert data["conversation_id"] == "conv-s1-1"
    assert data["query"] == "What is 2+2?"
    assert data["summary"]["total"] == 2
    assert data["summary"]["succeeded"] == 2
    assert data["summary"]["failed"] == 0
    assert len(data["results"]) == 2
    assert data["results"][0]["model"] == "openai:gpt-4.1"
    assert data["results"][0]["response"] == "Hello from GPT"
    assert data["results"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_run_stage1_uses_provided_conversation_id(server):
    """run_stage1 uses an existing conversation_id when provided."""
    with respx.mock:
        # Must NOT call create conversation
        respx.post(
            "http://test:8001/api/conversations/existing-conv/message/stream"
        ).mock(
            return_value=httpx.Response(
                200,
                text=_stage1_sse_body(models=[
                    {"model": "openai:gpt-4.1", "response": "Reused", "error": None},
                ]),
                headers={"content-type": "text/event-stream"},
            )
        )
        result = await server.call_tool("council_deliberate", {"action": "stage1", 
            "query": "hello",
            "conversation_id": "existing-conv",
        })
        data = get_json(result)

    assert data["conversation_id"] == "existing-conv"
    assert data["results"][0]["response"] == "Reused"


@pytest.mark.asyncio
async def test_run_stage1_model_error(server):
    """run_stage1 correctly reports model-level errors."""
    error_body = _stage1_sse_body(models=[
        {"model": "openai:gpt-4.1", "response": "OK", "error": None},
        {"model": "groq:llama3", "response": None, "error": True, "error_message": "429 Too Many Requests"},
    ])
    with respx.mock:
        respx.post("http://test:8001/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "conv-err", "title": ""})
        )
        respx.post(
            "http://test:8001/api/conversations/conv-err/message/stream"
        ).mock(
            return_value=httpx.Response(
                200,
                text=error_body,
                headers={"content-type": "text/event-stream"},
            )
        )
        result = await server.call_tool("council_deliberate", {"action": "stage1", "query": "test"})
        data = get_json(result)

    assert data["summary"]["succeeded"] == 1
    assert data["summary"]["failed"] == 1
    failed = next(r for r in data["results"] if r["status"] == "error")
    assert failed["error"]["type"] == "rate_limit"
    assert failed["error"]["retryable"] is True


@pytest.mark.asyncio
async def test_run_stage1_web_search_flag(server):
    """run_stage1 with web_search=True includes search context in result."""
    search_body = (
        _sse({"type": "search_complete", "data": {"search_context": "web results", "search_query": "What is 2+2?"}})
        + _sse({"type": "stage1_complete", "data": [
            {"model": "openai:gpt-4.1", "response": "4", "error": None},
        ]})
        + _sse({"type": "complete"})
    )
    with respx.mock:
        respx.post("http://test:8001/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "conv-ws", "title": ""})
        )
        respx.post(
            "http://test:8001/api/conversations/conv-ws/message/stream"
        ).mock(
            return_value=httpx.Response(
                200,
                text=search_body,
                headers={"content-type": "text/event-stream"},
            )
        )
        result = await server.call_tool("council_deliberate", {"action": "stage1", 
            "query": "What is 2+2?",
            "web_search": True,
        })
        data = get_json(result)

    assert data["web_search"] is True
    assert data["search_context"] == "web results"


# ── run_stage2 ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_stage2_returns_rankings(server):
    """run_stage2 drains stage1 events and returns stage2 rankings."""
    with respx.mock:
        respx.post("http://test:8001/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "conv-s2", "title": ""})
        )
        respx.post(
            "http://test:8001/api/conversations/conv-s2/message/stream"
        ).mock(
            return_value=httpx.Response(
                200,
                text=_stage1_plus_stage2_sse_body(),
                headers={"content-type": "text/event-stream"},
            )
        )
        result = await server.call_tool("council_deliberate", {"action": "stage2", "query": "Explain quantum computing"})
        data = get_json(result)

    assert data["conversation_id"] == "conv-s2"
    assert "rankings" in data
    assert "aggregate_rankings" in data
    assert "label_to_model" in data
    assert len(data["rankings"]) == 1
    assert data["rankings"][0]["model"] == "openai:gpt-4.1"
    assert data["rankings"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_run_stage2_uses_provided_conversation_id(server):
    """run_stage2 uses provided conversation_id without creating a new one."""
    with respx.mock:
        respx.post(
            "http://test:8001/api/conversations/existing-s2/message/stream"
        ).mock(
            return_value=httpx.Response(
                200,
                text=_stage1_plus_stage2_sse_body(),
                headers={"content-type": "text/event-stream"},
            )
        )
        result = await server.call_tool("council_deliberate", {"action": "stage2", 
            "query": "test query",
            "conversation_id": "existing-s2",
        })
        data = get_json(result)

    assert data["conversation_id"] == "existing-s2"


# ── run_stage3 ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_stage3_returns_synthesis(server):
    """run_stage3 drains stage1/2 and returns stage3 synthesis."""
    with respx.mock:
        respx.post("http://test:8001/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "conv-s3", "title": ""})
        )
        respx.post(
            "http://test:8001/api/conversations/conv-s3/message/stream"
        ).mock(
            return_value=httpx.Response(
                200,
                text=_full_deliberation_sse_body(),
                headers={"content-type": "text/event-stream"},
            )
        )
        result = await server.call_tool("council_deliberate", {"action": "stage3", "query": "What is consciousness?"})
        data = get_json(result)

    assert data["conversation_id"] == "conv-s3"
    assert data["status"] == "success"
    assert data["synthesis"] == "Synthesized final answer from the chairman."
    assert data["chairman_model"] == "anthropic:claude-opus-4"


@pytest.mark.asyncio
async def test_run_stage3_uses_provided_conversation_id(server):
    """run_stage3 uses provided conversation_id."""
    with respx.mock:
        respx.post(
            "http://test:8001/api/conversations/existing-s3/message/stream"
        ).mock(
            return_value=httpx.Response(
                200,
                text=_full_deliberation_sse_body(),
                headers={"content-type": "text/event-stream"},
            )
        )
        result = await server.call_tool("council_deliberate", {"action": "stage3", 
            "query": "test",
            "conversation_id": "existing-s3",
        })
        data = get_json(result)

    assert data["conversation_id"] == "existing-s3"


# ── run_deliberation ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_deliberation_returns_all_stages(server):
    """run_deliberation returns stage1, stage2, stage3, and chairman_answer."""
    with respx.mock:
        respx.post("http://test:8001/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "conv-full", "title": ""})
        )
        respx.post(
            "http://test:8001/api/conversations/conv-full/message/stream"
        ).mock(
            return_value=httpx.Response(
                200,
                text=_full_deliberation_sse_body(),
                headers={"content-type": "text/event-stream"},
            )
        )
        result = await server.call_tool("council_deliberate", {"action": "full", 
            "query": "What is the best programming language?"
        })
        data = get_json(result)

    assert data["conversation_id"] == "conv-full"
    assert data["query"] == "What is the best programming language?"
    # Stage 1
    assert "stage1" in data
    assert data["stage1"]["summary"]["total"] == 2
    assert data["stage1"]["summary"]["succeeded"] == 2
    # Stage 2
    assert "stage2" in data
    assert len(data["stage2"]["rankings"]) == 2
    assert "aggregate_rankings" in data["stage2"]
    # Stage 3
    assert "stage3" in data
    assert data["stage3"]["status"] == "success"
    assert data["stage3"]["synthesis"] == "Synthesized final answer from the chairman."
    # Top-level shortcut
    assert data["chairman_answer"] == "Synthesized final answer from the chairman."


@pytest.mark.asyncio
async def test_run_deliberation_model_override_passed_in_stream(server):
    """run_deliberation passes model overrides in the stream request body, not via settings."""
    stream_calls = []

    def capture_stream(request):
        body = json.loads(request.content)
        stream_calls.append(body)
        return httpx.Response(
            200,
            text=_full_deliberation_sse_body(),
            headers={"content-type": "text/event-stream"},
        )

    with respx.mock:
        respx.post("http://test:8001/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "conv-override", "title": ""})
        )
        respx.post(
            "http://test:8001/api/conversations/conv-override/message/stream"
        ).mock(side_effect=capture_stream)

        override_models = ["groq:llama3-70b-8192", "ollama:llama3"]
        result = await server.call_tool("council_deliberate", {"action": "full", 
            "query": "test",
            "models": override_models,
        })
        data = get_json(result)

    # Model override is in the stream payload, not a separate PUT call
    assert len(stream_calls) == 1
    assert stream_calls[0]["council_models"] == override_models
    assert data["chairman_answer"] == "Synthesized final answer from the chairman."


@pytest.mark.asyncio
async def test_run_deliberation_no_settings_mutation_on_exception(server):
    """run_deliberation does not touch settings even when stream fails."""
    with respx.mock:
        respx.post("http://test:8001/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "conv-exc", "title": ""})
        )
        respx.post(
            "http://test:8001/api/conversations/conv-exc/message/stream"
        ).mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        result = await server.call_tool("council_deliberate", {"action": "full", 
            "query": "test",
            "models": ["groq:llama3-70b-8192", "ollama:llama3"],
        })
        data = get_json(result)
        assert data["status"] == "error"


@pytest.mark.asyncio
async def test_run_deliberation_no_model_override_skips_settings(server):
    """run_deliberation without models= should not touch settings."""
    with respx.mock:
        respx.post("http://test:8001/api/conversations").mock(
            return_value=httpx.Response(201, json={"id": "conv-nomod", "title": ""})
        )
        respx.post(
            "http://test:8001/api/conversations/conv-nomod/message/stream"
        ).mock(
            return_value=httpx.Response(
                200,
                text=_full_deliberation_sse_body(),
                headers={"content-type": "text/event-stream"},
            )
        )
        # No GET or PUT settings mock — should not be called
        result = await server.call_tool("council_deliberate", {"action": "full", "query": "test"})
        data = get_json(result)

    assert data["chairman_answer"] is not None


# ── quick_chat ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quick_chat_returns_single_model_response(server):
    """quick_chat calls /api/ask and returns the model's response."""
    ask_calls = []

    def capture_ask(request):
        body = json.loads(request.content)
        ask_calls.append(body)
        return httpx.Response(200, json={
            "conversation_id": "quick-conv-1",
            "response": "Quick answer from GPT",
            "model": "openai:gpt-4.1",
            "error": None,
        })

    with respx.mock:
        respx.post("http://test:8001/api/ask").mock(side_effect=capture_ask)

        result = await server.call_tool("model_chat", {"action": "quick", 
            "query": "What time is it?",
            "model": "openai:gpt-4.1",
        })
        data = get_json(result)

    assert data["conversation_id"] == "quick-conv-1"
    assert data["model"] == "openai:gpt-4.1"
    assert data["response"] == "Quick answer from GPT"
    assert data.get("error") is None
    assert data["web_search_used"] is False

    # Verify the /api/ask payload
    assert len(ask_calls) == 1
    assert ask_calls[0]["models"] == ["openai:gpt-4.1"]
    assert ask_calls[0]["execution_mode"] == "chat_only"
    assert ask_calls[0]["web_search"] is False


@pytest.mark.asyncio
async def test_quick_chat_forwards_text_documents(server):
    ask_calls = []

    def capture_ask(request):
        ask_calls.append(json.loads(request.content))
        return httpx.Response(200, json={
            "response": "Document answer",
            "model": "openai:gpt-4.1",
            "error": None,
        })

    documents = [{"name": "notes.txt", "mime_type": "text/plain", "text": "Alpha"}]

    with respx.mock:
        respx.post("http://test:8001/api/ask").mock(side_effect=capture_ask)

        result = await server.call_tool("model_chat", {
            "action": "quick",
            "query": "Summarize.",
            "model": "openai:gpt-4.1",
            "documents": documents,
        })
        data = get_json(result)

    assert data["response"] == "Document answer"
    assert ask_calls[0]["documents"] == documents


@pytest.mark.asyncio
async def test_quick_chat_extracts_base64_documents_before_model_call(server):
    extract_calls = []
    ask_calls = []
    encoded = base64.b64encode(b"Alpha").decode()

    def capture_extract(request):
        extract_calls.append(json.loads(request.content))
        return httpx.Response(200, json={
            "documents": [{"name": "notes.txt", "mime_type": "text/plain", "text": "Alpha"}],
            "attachments": [{"name": "notes.txt", "mime_type": "text/plain", "char_count": 5}],
            "warnings": [],
        })

    def capture_ask(request):
        ask_calls.append(json.loads(request.content))
        return httpx.Response(200, json={
            "response": "Document answer",
            "model": "openai:gpt-4.1",
            "error": None,
        })

    with respx.mock:
        respx.post("http://test:8001/api/documents/extract-json").mock(side_effect=capture_extract)
        respx.post("http://test:8001/api/ask").mock(side_effect=capture_ask)

        result = await server.call_tool("model_chat", {
            "action": "quick",
            "query": "Summarize.",
            "model": "openai:gpt-4.1",
            "documents": [{
                "name": "notes.txt",
                "mime_type": "text/plain",
                "data_base64": encoded,
            }],
        })
        data = get_json(result)

    assert data["response"] == "Document answer"
    assert extract_calls[0]["documents"][0]["data_base64"] == encoded
    assert ask_calls[0]["documents"] == [{"name": "notes.txt", "mime_type": "text/plain", "text": "Alpha"}]


@pytest.mark.asyncio
async def test_quick_chat_with_web_search(server):
    """quick_chat passes web_search to /api/ask."""
    with respx.mock:
        respx.post("http://test:8001/api/ask").mock(
            return_value=httpx.Response(200, json={
                "response": "Searched answer",
                "model": "openai:gpt-4.1",
                "error": None,
            })
        )

        result = await server.call_tool("model_chat", {"action": "quick", 
            "query": "latest news",
            "model": "openai:gpt-4.1",
            "web_search": True,
        })
        data = get_json(result)

    assert data["response"] == "Searched answer"
    assert data["web_search_used"] is True


@pytest.mark.asyncio
async def test_quick_chat_propagates_api_errors(server):
    """quick_chat propagates errors from /api/ask."""
    with respx.mock:
        respx.post("http://test:8001/api/ask").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        result = await server.call_tool("model_chat", {"action": "quick", 
            "query": "test",
            "model": "openai:gpt-4.1",
        })
        data = get_json(result)
        assert data["status"] == "error"
