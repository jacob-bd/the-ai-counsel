"""Tests for the OpenCode Zen / Go direct provider (chat/completions + messages)."""

import json
import pytest

from backend.providers.opencode import OpenCodeProvider


class _FakeResponse:
    def __init__(self, status_code, json_body=None, text="", content_type="application/json"):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text or json.dumps(self._json)
        self.headers = {"content-type": content_type}

    def json(self):
        return self._json


class _FakeAsyncClient:
    """Captures the kwargs passed to httpx.AsyncClient and returns scripted responses."""

    instances: list = []
    responses: list = []  # list of (status, json, text) tuples, one per .post()/.get() call

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.entered = False
        type(self).instances.append(self)

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        self.kwargs["__url__"] = url
        self.kwargs["__method__"] = "POST"
        self.kwargs.update(kwargs)
        return self._next()

    async def get(self, url, **kwargs):
        self.kwargs["__url__"] = url
        self.kwargs["__method__"] = "GET"
        self.kwargs.update(kwargs)
        return self._next()

    def _next(self):
        if not type(self).responses:
            raise AssertionError("No scripted response left for httpx call")
        scripted = type(self).responses.pop(0)
        if len(scripted) == 3:
            status, body, text = scripted
            return _FakeResponse(status, body, text)
        status, body, text, content_type = scripted
        return _FakeResponse(status, body, text, content_type)


@pytest.fixture
def fake_httpx(monkeypatch):
    """Patch httpx.AsyncClient with a scriptable fake."""
    _FakeAsyncClient.instances = []
    _FakeAsyncClient.responses = []
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient


@pytest.fixture
def fake_settings(monkeypatch):
    class FakeSettings:
        opencode_api_key = "sk-zen-test"

    from backend import settings as settings_module
    from backend.providers import opencode as opencode_module

    def fake():
        return FakeSettings()

    monkeypatch.setattr(settings_module, "get_settings", fake)
    # Provider does `from ..settings import get_settings`, so the local name
    # must be patched too — patching the settings module alone has no effect.
    monkeypatch.setattr(opencode_module, "get_settings", fake)


@pytest.mark.asyncio
async def test_query_uses_chat_completions_with_bearer_auth(fake_httpx, fake_settings):
    fake_httpx.responses.append((
        200,
        {
            "choices": [{"message": {"content": "hello"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        },
        "",
    ))

    provider = OpenCodeProvider(product="zen")
    result = await provider.query("opencode-zen:glm-5.1", [{"role": "user", "content": "hi"}])

    assert result["content"] == "hello"
    assert result["error"] is False
    assert result["usage"]["prompt_tokens"] == 3
    headers = fake_httpx.instances[0].kwargs["headers"]
    assert headers["Authorization"] == "Bearer sk-zen-test"
    assert fake_httpx.instances[0].kwargs["__url__"] == "https://opencode.ai/zen/v1/chat/completions"


@pytest.mark.asyncio
async def test_query_strips_prefix_from_model_id(fake_httpx, fake_settings):
    fake_httpx.responses.append((200, {"choices": [{"message": {"content": "ok"}}]}, ""))

    provider = OpenCodeProvider(product="go")
    await provider.query("opencode-go:kimi-k2.5", [{"role": "user", "content": "hi"}])

    body = fake_httpx.instances[0].kwargs["json"]
    assert body["model"] == "kimi-k2.5"
    assert fake_httpx.instances[0].kwargs["__url__"] == "https://opencode.ai/zen/go/v1/chat/completions"


@pytest.mark.asyncio
async def test_query_without_key_returns_error(fake_httpx, monkeypatch):
    class EmptySettings:
        opencode_api_key = None

    import backend.providers.opencode as oc_module
    monkeypatch.setattr(oc_module, "get_settings", lambda: EmptySettings())

    provider = OpenCodeProvider(product="zen")
    result = await provider.query("opencode-zen:glm-5.1", [{"role": "user", "content": "hi"}])

    assert result["error"] is True
    assert "API key not configured" in result["error_message"]


@pytest.mark.asyncio
async def test_query_surfaces_api_error(fake_httpx, fake_settings):
    fake_httpx.responses.append((401, {}, "Unauthorized"))

    provider = OpenCodeProvider(product="zen")
    result = await provider.query("opencode-zen:glm-5.1", [{"role": "user", "content": "hi"}])
    assert result["error"] is True
    assert "401" in result["error_message"]


@pytest.mark.asyncio
async def test_get_models_filters_supported_protocols(fake_httpx, fake_settings):
    """Zen get_models includes chat/completions and messages models,
    excludes responses (GPT), Gemini, and utility models."""
    fake_httpx.responses.append((
        200,
        {
            "data": [
                {"id": "glm-5.1", "is_free": False},
                {"id": "deepseek-v4-flash", "is_free": False},
                {"id": "big-pickle", "is_free": True},
                {"id": "qwen3.5-plus", "is_free": False},
                {"id": "gpt-5", "is_free": False},
                {"id": "claude-sonnet-4-6", "is_free": False},
                {"id": "embed-v1", "is_free": False},
            ]
        },
        "",
    ))

    provider = OpenCodeProvider(product="zen")
    models = await provider.get_models()
    ids = [m["id"] for m in models]
    assert "opencode-zen:glm-5.1" in ids
    assert "opencode-zen:deepseek-v4-flash" in ids
    assert "opencode-zen:big-pickle" in ids
    assert "opencode-zen:qwen3.5-plus" in ids
    assert "opencode-zen:gpt-5" not in ids
    assert "opencode-zen:claude-sonnet-4-6" not in ids
    assert "opencode-zen:embed-v1" not in ids
    free = next(m for m in models if m["id"] == "opencode-zen:big-pickle")
    assert free["is_free"] is True
    assert free["provider"] == "OpenCode Zen"


@pytest.mark.asyncio
async def test_go_get_models_includes_messages_models(fake_httpx, fake_settings):
    """Go get_models includes both chat/completions and messages models."""
    fake_httpx.responses.append((
        200,
        {
            "data": [
                {"id": "glm-5", "is_free": False},
                {"id": "deepseek-v4-flash", "is_free": False},
                {"id": "minimax-m3", "is_free": False},
                {"id": "minimax-m2.5", "is_free": False},
                {"id": "qwen3.7-max", "is_free": False},
                {"id": "qwen3.6-plus", "is_free": False},
                {"id": "gpt-5", "is_free": False},
            ]
        },
        "",
    ))

    provider = OpenCodeProvider(product="go")
    models = await provider.get_models()
    ids = [m["id"] for m in models]
    assert "opencode-go:glm-5" in ids
    assert "opencode-go:deepseek-v4-flash" in ids
    assert "opencode-go:minimax-m3" in ids
    assert "opencode-go:minimax-m2.5" in ids
    assert "opencode-go:qwen3.7-max" in ids
    assert "opencode-go:qwen3.6-plus" in ids
    assert "opencode-go:gpt-5" not in ids


@pytest.mark.asyncio
async def test_validate_key_reports_model_count(fake_httpx, fake_settings):
    fake_httpx.responses.append((
        200,
        {"data": [{"id": "glm-5"}, {"id": "kimi-k2.5"}]},
        "",
    ))

    provider = OpenCodeProvider(product="zen")
    result = await provider.validate_key("")
    assert result["success"] is True, f"result={result}, instances={len(fake_httpx.instances)}, kwargs={fake_httpx.instances[0].kwargs if fake_httpx.instances else 'NONE'}"
    assert "2 models" in result["message"]


def test_provider_init_validates_product():
    with pytest.raises(ValueError):
        OpenCodeProvider(product="bogus")


@pytest.mark.asyncio
async def test_query_sends_stream_false(fake_httpx, fake_settings):
    fake_httpx.responses.append((200, {"choices": [{"message": {"content": "ok"}}]}, ""))

    provider = OpenCodeProvider(product="zen")
    await provider.query("opencode-zen:glm-5.1", [{"role": "user", "content": "hi"}])

    body = fake_httpx.instances[0].kwargs["json"]
    assert body["stream"] is False


@pytest.mark.asyncio
async def test_query_rejects_unsupported_model(fake_httpx, fake_settings):
    """Embed/audio/GPT models must be rejected at query() time, not
    surfaced as a confusing upstream 4xx."""
    provider = OpenCodeProvider(product="zen")
    result = await provider.query(
        "opencode-zen:text-embedding-3-small",
        [{"role": "user", "content": "hi"}],
    )
    assert result["error"] is True
    assert "not supported" in result["error_message"]
    assert fake_httpx.instances == [], "Should not have made an HTTP call"


@pytest.mark.asyncio
async def test_query_retries_on_rate_limit_then_succeeds(fake_httpx, fake_settings, monkeypatch):
    """429 responses should be retried up to MAX_RETRIES with exponential backoff."""
    sleeps: list[float] = []

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr("backend.providers.opencode.asyncio.sleep", fake_sleep)

    fake_httpx.responses.append((429, {}, "rate limited"))
    fake_httpx.responses.append((200, {"choices": [{"message": {"content": "ok"}}]}, ""))

    provider = OpenCodeProvider(product="zen")
    result = await provider.query("opencode-zen:glm-5.1", [{"role": "user", "content": "hi"}])

    assert result["error"] is False
    assert result["content"] == "ok"
    assert len(fake_httpx.instances) == 2
    assert sleeps == [1.0]


@pytest.mark.asyncio
async def test_query_gives_up_after_max_retries_on_429(fake_httpx, fake_settings, monkeypatch):
    async def fake_sleep(s):
        return None
    monkeypatch.setattr("backend.providers.opencode.asyncio.sleep", fake_sleep)
    fake_httpx.responses.append((429, {}, "rate limited"))
    fake_httpx.responses.append((429, {}, "rate limited"))

    provider = OpenCodeProvider(product="zen")
    result = await provider.query("opencode-zen:glm-5.1", [{"role": "user", "content": "hi"}])

    assert result["error"] is True
    assert "429" in result["error_message"]


@pytest.mark.asyncio
async def test_query_rejects_non_json_content_type(fake_httpx, fake_settings):
    """If the gateway defaults to streaming, we should fail fast with a clear
    error rather than crashing on JSON parsing."""
    fake_httpx.responses.append((
        200,
        {},
        "data: {}\n\n",
        "text/event-stream",
    ))

    provider = OpenCodeProvider(product="zen")
    result = await provider.query("opencode-zen:glm-5.1", [{"role": "user", "content": "hi"}])

    assert result["error"] is True
    assert "content-type" in result["error_message"].lower() or "stream" in result["error_message"].lower()


@pytest.mark.asyncio
async def test_query_messages_protocol_posts_to_messages_endpoint(fake_httpx, fake_settings):
    """Messages-protocol models POST to /messages with Anthropic body format."""
    fake_httpx.responses.append((
        200,
        {
            "content": [{"text": "hello from qwen"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
        "",
    ))

    provider = OpenCodeProvider(product="go")
    result = await provider.query(
        "opencode-go:minimax-m3",
        [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hi"},
        ],
    )

    assert result["error"] is False
    assert result["content"] == "hello from qwen"
    assert result["usage"]["input_tokens"] == 10
    assert fake_httpx.instances[0].kwargs["__url__"] == "https://opencode.ai/zen/go/v1/messages"
    body = fake_httpx.instances[0].kwargs["json"]
    assert body["model"] == "minimax-m3"
    assert body["max_tokens"] == 4096
    assert body["system"] == "You are helpful."
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert "stream" not in body
    headers = fake_httpx.instances[0].kwargs["headers"]
    assert headers["Authorization"] == "Bearer sk-zen-test"


@pytest.mark.asyncio
async def test_query_messages_without_system_message(fake_httpx, fake_settings):
    """Messages body should not include 'system' key when no system message."""
    fake_httpx.responses.append((
        200,
        {"content": [{"text": "ok"}], "usage": {"input_tokens": 1, "output_tokens": 1}},
        "",
    ))

    provider = OpenCodeProvider(product="zen")
    await provider.query("opencode-zen:qwen3.5-plus", [{"role": "user", "content": "hi"}])

    body = fake_httpx.instances[0].kwargs["json"]
    assert "system" not in body
    assert fake_httpx.instances[0].kwargs["__url__"] == "https://opencode.ai/zen/v1/messages"


@pytest.mark.asyncio
async def test_zen_qwen_uses_messages_not_chat_completions(fake_httpx, fake_settings):
    """Zen Qwen models must route to /messages, not /chat/completions."""
    provider = OpenCodeProvider(product="zen")
    assert provider._supports_messages("qwen3.5-plus") is True
    assert provider._supports_messages("qwen3.6-plus") is True
    assert provider._supports_chat_completions("qwen3.5-plus") is False
    assert provider._supports_chat_completions("qwen3.6-plus") is False


@pytest.mark.asyncio
async def test_go_minimax_uses_messages(fake_httpx, fake_settings):
    """Go MiniMax models must route to /messages."""
    provider = OpenCodeProvider(product="go")
    assert provider._supports_messages("minimax-m3") is True
    assert provider._supports_messages("minimax-m2.7") is True
    assert provider._supports_messages("minimax-m2.5") is True
    assert provider._supports_chat_completions("minimax-m3") is False
