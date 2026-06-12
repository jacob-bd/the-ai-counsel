import contextlib
import json

import pytest

from backend.providers.notion2api import Notion2APIProvider


class _FakeResponse:
    def __init__(self, status_code, json_body=None, text="", content_type="application/json"):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text or json.dumps(self._json)
        self.headers = {"content-type": content_type}

    def json(self):
        return self._json

    async def aread(self):
        return self.text.encode("utf-8")

    async def aiter_lines(self):
        for line in self.text.splitlines():
            yield line


class _FakeAsyncClient:
    instances = []
    responses = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        type(self).instances.append(self)

    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        self.kwargs["__url__"] = url
        self.kwargs["__method__"] = "POST"
        self.kwargs.update(kwargs)
        if not type(self).responses:
            raise AssertionError("No scripted response left for httpx post")
        status, body, text = type(self).responses.pop(0)
        return _FakeResponse(status, body, text)

    async def get(self, url, **kwargs):
        self.kwargs["__url__"] = url
        self.kwargs["__method__"] = "GET"
        self.kwargs.update(kwargs)
        if not type(self).responses:
            raise AssertionError("No scripted response left for httpx get")
        status, body, text = type(self).responses.pop(0)
        return _FakeResponse(status, body, text)

    @contextlib.asynccontextmanager
    async def stream(self, method, url, **kwargs):
        self.kwargs["__url__"] = url
        self.kwargs["__method__"] = method
        self.kwargs.update(kwargs)
        if not type(self).responses:
            raise AssertionError(f"No scripted response left for httpx stream {method}")
        status, body, text = type(self).responses.pop(0)
        yield _FakeResponse(status, body, text)


@pytest.fixture
def fake_httpx(monkeypatch):
    _FakeAsyncClient.instances = []
    _FakeAsyncClient.responses = []
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient


@pytest.fixture
def notion_env(monkeypatch):
    monkeypatch.setenv("NOTION2API_BASE_URL", "http://127.0.0.1:8120/v1")
    monkeypatch.setenv("NOTION2API_API_KEY", "test-token")


@pytest.mark.asyncio
async def test_notion2api_query_uses_dedicated_prefix_and_endpoint(fake_httpx, notion_env):
    fake_httpx.responses.append((
        200,
        {"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 3}},
        "",
    ))
    provider = Notion2APIProvider()
    result = await provider.query(
        "notion2api:claude-opus4.7",
        [{"role": "user", "content": "hi"}],
        temperature=0.2,
    )

    assert result == {"content": "ok", "usage": {"total_tokens": 3}, "error": False}
    sent = fake_httpx.instances[-1].kwargs
    assert sent["__url__"] == "http://127.0.0.1:8120/v1/chat/completions"
    assert sent["headers"]["Authorization"] == "Bearer test-token"
    assert sent["json"]["model"] == "claude-opus4.7"
    assert sent["json"]["messages"] == [{"role": "user", "content": "hi"}]
    assert sent["timeout"] == 600.0


@pytest.mark.asyncio
async def test_notion2api_get_models_prefixes_and_filters(fake_httpx, notion_env):
    fake_httpx.responses.append((
        200,
        {"data": [
            {"id": "gpt-5.2"},
            {"id": "text-embedding-3-large"},
            {"id": "claude-opus4.7"},
            {"id": ""},
        ]},
        "",
    ))

    models = await Notion2APIProvider().get_models()

    assert [m["id"] for m in models] == [
        "notion2api:claude-opus4.7",
        "notion2api:gpt-5.2",
    ]
    assert all(m["source"] == "notion2api" for m in models)
    assert all(m["provider"] == "Notion2API" for m in models)


@pytest.mark.asyncio
async def test_notion2api_validate_connection_accepts_explicit_url_and_token(fake_httpx, monkeypatch):
    monkeypatch.delenv("NOTION2API_API_KEY", raising=False)
    fake_httpx.responses.append((200, {"data": [{"id": "model-a"}]}, ""))

    result = await Notion2APIProvider().validate_connection(
        "http://localhost:9000/v1",
        "abc",
    )

    assert result["success"] is True
    assert result["message"] == "Connected to Notion2API. Found 1 models."
    sent = fake_httpx.instances[-1].kwargs
    assert sent["__url__"] == "http://localhost:9000/v1/models"
    assert sent["headers"]["Authorization"] == "Bearer abc"


@pytest.mark.asyncio
async def test_notion2api_query_reports_http_error(fake_httpx, notion_env):
    fake_httpx.responses.append((403, {"error": "forbidden"}, "Forbidden"))

    result = await Notion2APIProvider().query(
        "notion2api:gpt-5.2",
        [{"role": "user", "content": "hi"}],
    )

    assert result["error"] is True
    assert "Notion2API error: 403" in result["error_message"]


@pytest.mark.asyncio
async def test_notion2api_query_retries_upstream_empty_response(fake_httpx, notion_env, monkeypatch):
    async def _no_sleep(_delay):
        return None

    monkeypatch.setattr("backend.providers.notion2api.asyncio.sleep", _no_sleep)
    empty_response = {
        "error": {
            "message": "Notion returned empty content.",
            "type": "upstream_empty_response",
            "param": None,
            "code": "NOTION_EMPTY",
            "suggestion": "Send the message again.",
        }
    }
    fake_httpx.responses.extend([
        (503, empty_response, json.dumps(empty_response)),
        (200, {"choices": [{"message": {"content": "retried ok"}}]}, ""),
    ])

    result = await Notion2APIProvider().query(
        "notion2api:claude-opus4.8",
        [{"role": "user", "content": "hi"}],
    )

    assert result == {"content": "retried ok", "usage": None, "error": False}
    assert len(fake_httpx.instances) == 2


@pytest.mark.asyncio
async def test_notion2api_query_respects_longer_explicit_timeout(fake_httpx, notion_env):
    fake_httpx.responses.append((
        200,
        {"choices": [{"message": {"content": "ok"}}]},
        "",
    ))

    await Notion2APIProvider().query(
        "notion2api:gpt-5.5",
        [{"role": "user", "content": "hi"}],
        timeout=900.0,
    )

    assert fake_httpx.instances[-1].kwargs["timeout"] == 900.0


@pytest.mark.asyncio
async def test_notion2api_query_does_not_persist_without_conversation_id(fake_httpx, notion_env):
    fake_httpx.responses.append((
        200,
        {"choices": [{"message": {"content": "ok"}}]},
        "",
    ))

    await Notion2APIProvider().query(
        "notion2api:claude-opus4.7",
        [{"role": "user", "content": "hi"}],
    )

    sent = fake_httpx.instances[-1].kwargs["json"]
    assert "conversation_id" not in sent
    assert "metadata" not in sent


@pytest.mark.asyncio
async def test_notion2api_query_persists_with_stable_per_model_conversation_id(fake_httpx, notion_env):
    fake_httpx.responses.append((
        200,
        {"choices": [{"message": {"content": "ok"}}]},
        "",
    ))

    await Notion2APIProvider().query(
        "notion2api:claude-opus4.7",
        [{"role": "user", "content": "hi"}],
        conversation_id="conv-123",
    )

    sent = fake_httpx.instances[-1].kwargs["json"]
    assert sent["conversation_id"] == "ai-counsel-conv-123-claude-opus4.7"
    assert sent["metadata"] == {
        "persist_remote_chat": True,
        "source": "ai-counsel",
    }
