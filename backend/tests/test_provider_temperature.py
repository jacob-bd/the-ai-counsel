from __future__ import annotations

import json

import pytest

from backend.providers.anthropic import AnthropicProvider
from backend.providers.openai import OpenAIProvider
from backend.providers.temperature import (
    is_anthropic_temperature_deprecated_model,
    is_openai_fixed_temperature_model,
)


class _FakeResponse:
    def __init__(self, status_code=200, json_body=None):
        self.status_code = status_code
        self._json = json_body or {"choices": [{"message": {"content": "ok"}}]}
        self.text = json.dumps(self._json)
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"Unexpected status in fake response: {self.status_code}")


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
        self.kwargs.update(kwargs)
        if type(self).responses:
            return type(self).responses.pop(0)
        return _FakeResponse()


@pytest.fixture
def fake_httpx(monkeypatch):
    _FakeAsyncClient.instances = []
    _FakeAsyncClient.responses = []

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient


@pytest.mark.parametrize(
    "model_id",
    [
        "openai:gpt-5.5",
        "openai:gpt-5.2-mini",
        "openrouter:openai/gpt-5.1",
        "openai:o1-preview",
        "openai:o3-mini",
        "openai:o4-mini",
    ],
)
def test_openai_fixed_temperature_model_detection(model_id):
    assert is_openai_fixed_temperature_model(model_id) is True


@pytest.mark.parametrize(
    "model_id",
    [
        "anthropic:claude-opus-4-8",
        "anthropic:claude-sonnet-4-6",
        "openrouter:anthropic/claude-haiku-4-5-20251001",
        "anthropic:claude-fable-5",
    ],
)
def test_anthropic_deprecated_temperature_model_detection(model_id):
    assert is_anthropic_temperature_deprecated_model(model_id) is True


@pytest.mark.asyncio
async def test_openai_omits_temperature_for_fixed_temperature_models(fake_httpx, monkeypatch):
    import backend.providers.openai as openai_module

    class FakeSettings:
        openai_api_key = "sk-test"

    monkeypatch.setattr(openai_module, "get_settings", lambda: FakeSettings())

    provider = OpenAIProvider()
    result = await provider.query(
        "openai:gpt-5.5",
        [{"role": "user", "content": "hi"}],
        temperature=0.0,
    )

    assert result["error"] is False
    body = fake_httpx.instances[0].kwargs["json"]
    assert body["model"] == "gpt-5.5"
    assert "temperature" not in body


@pytest.mark.asyncio
async def test_openai_keeps_temperature_for_standard_chat_models(fake_httpx, monkeypatch):
    import backend.providers.openai as openai_module

    class FakeSettings:
        openai_api_key = "sk-test"

    monkeypatch.setattr(openai_module, "get_settings", lambda: FakeSettings())

    provider = OpenAIProvider()
    await provider.query(
        "openai:gpt-4.1",
        [{"role": "user", "content": "hi"}],
        temperature=0.2,
    )

    body = fake_httpx.instances[0].kwargs["json"]
    assert body["temperature"] == 0.2


@pytest.mark.asyncio
async def test_anthropic_omits_temperature_for_new_claude_models(fake_httpx, monkeypatch):
    import backend.providers.anthropic as anthropic_module

    class FakeSettings:
        anthropic_api_key = "sk-test"

    monkeypatch.setattr(anthropic_module, "get_settings", lambda: FakeSettings())
    fake_httpx.responses.append(
        _FakeResponse(200, {"content": [{"type": "text", "text": "ok"}]})
    )

    provider = AnthropicProvider()
    result = await provider.query(
        "anthropic:claude-opus-4-8",
        [{"role": "user", "content": "hi"}],
        temperature=0.3,
    )

    assert result["error"] is False
    body = fake_httpx.instances[0].kwargs["json"]
    assert body["model"] == "claude-opus-4-8"
    assert "temperature" not in body


@pytest.mark.asyncio
async def test_anthropic_keeps_temperature_for_older_claude_models(fake_httpx, monkeypatch):
    import backend.providers.anthropic as anthropic_module

    class FakeSettings:
        anthropic_api_key = "sk-test"

    monkeypatch.setattr(anthropic_module, "get_settings", lambda: FakeSettings())
    fake_httpx.responses.append(
        _FakeResponse(200, {"content": [{"type": "text", "text": "ok"}]})
    )

    provider = AnthropicProvider()
    await provider.query(
        "anthropic:claude-3-5-sonnet-20241022",
        [{"role": "user", "content": "hi"}],
        temperature=0.3,
    )

    body = fake_httpx.instances[0].kwargs["json"]
    assert body["temperature"] == 0.3


@pytest.mark.parametrize(
    "model_id",
    [
        "notion2api:claude-fable-5",
        "notion2api:claude-sonnet-4-6",
        "notion2api:openai/gpt-5.1",
    ],
)
def test_notion2api_should_omit_temperature_helper(model_id):
    from backend.providers.temperature import should_omit_temperature

    assert should_omit_temperature(model_id, "notion2api") is True


def test_notion2api_should_keep_temperature_for_standard_model():
    from backend.providers.temperature import should_omit_temperature

    assert should_omit_temperature("notion2api:claude-opus4.7", "notion2api") is False


@pytest.mark.asyncio
async def test_openrouter_omits_temperature_for_upstream_fixed_models(fake_httpx, monkeypatch):
    import backend.openrouter as openrouter_module

    monkeypatch.setattr(openrouter_module, "get_openrouter_api_key", lambda: "sk-test")

    result = await openrouter_module.query_model(
        "openai/gpt-5.5",
        [{"role": "user", "content": "hi"}],
        temperature=0.0,
    )

    assert result["error"] is None
    body = fake_httpx.instances[0].kwargs["json"]
    assert body["model"] == "openai/gpt-5.5"
    assert "temperature" not in body
