"""Tests for the OpenCode Zen / Go direct provider (chat/completions only)."""

import json
import pytest

from backend.providers.opencode import OpenCodeProvider


class _FakeResponse:
    def __init__(self, status_code, json_body=None, text=""):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text or json.dumps(self._json)

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
        status, body, text = type(self).responses.pop(0)
        return _FakeResponse(status, body, text)


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
async def test_get_models_filters_to_chat_completions(fake_httpx, fake_settings):
    fake_httpx.responses.append((
        200,
        {
            "data": [
                {"id": "glm-5.1", "is_free": False},
                {"id": "deepseek-v4-flash", "is_free": False},
                {"id": "big-pickle", "is_free": True},
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
    assert "opencode-zen:gpt-5" not in ids
    assert "opencode-zen:claude-sonnet-4-6" not in ids
    assert "opencode-zen:embed-v1" not in ids
    free = next(m for m in models if m["id"] == "opencode-zen:big-pickle")
    assert free["is_free"] is True
    assert free["provider"] == "OpenCode Zen"


@pytest.mark.asyncio
async def test_go_get_models_excludes_messages_protocol(fake_httpx, fake_settings):
    fake_httpx.responses.append((
        200,
        {
            "data": [
                {"id": "glm-5", "is_free": False},
                {"id": "deepseek-v4-flash", "is_free": False},
                {"id": "minimax-m2.5", "is_free": False},
                {"id": "qwen3.6-plus", "is_free": False},
            ]
        },
        "",
    ))

    provider = OpenCodeProvider(product="go")
    models = await provider.get_models()
    ids = [m["id"] for m in models]
    assert "opencode-go:glm-5" in ids
    assert "opencode-go:deepseek-v4-flash" in ids
    assert "opencode-go:minimax-m2.5" not in ids
    assert "opencode-go:qwen3.6-plus" not in ids


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
