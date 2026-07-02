import pytest
import json
import httpx
from backend.providers.anthropic import AnthropicProvider
from backend.settings import Settings

class _FakeResponse:
    def __init__(self, status_code, json_body=None, text="", headers=None):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text or json.dumps(self._json)
        self.headers = headers or {"content-type": "application/json"}

    def json(self):
        return self._json


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

    async def get(self, url, **kwargs):
        self.kwargs["__url__"] = url
        self.kwargs["__method__"] = "GET"
        self.kwargs.update(kwargs)
        if not type(self).responses:
            raise AssertionError("No scripted response left for httpx get")
        status, body = type(self).responses.pop(0)
        return _FakeResponse(status, body)


@pytest.fixture
def fake_httpx(monkeypatch):
    _FakeAsyncClient.instances = []
    _FakeAsyncClient.responses = []
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient


@pytest.fixture
def anthropic_settings(monkeypatch):
    settings = Settings(
        anthropic_api_key="test-key"
    )
    monkeypatch.setattr("backend.providers.anthropic.get_settings", lambda: settings)
    return settings


@pytest.mark.asyncio
async def test_anthropic_get_models_success(fake_httpx, anthropic_settings):
    fake_httpx.responses.append((
        200,
        {
            "data": [
                {"id": "claude-3-5-sonnet-20241022", "type": "model", "display_name": "Claude 3.5 Sonnet"},
                {"id": "claude-3-5-haiku-20241022", "type": "model"}
            ]
        }
    ))

    provider = AnthropicProvider()
    models = await provider.get_models()

    assert len(models) == 2
    # Sorted by name (uppercase 'Claude' before lowercase 'claude')
    assert models[0]["id"] == "anthropic:claude-3-5-sonnet-20241022"
    assert models[0]["name"] == "Claude 3.5 Sonnet [Anthropic]"
    assert models[1]["id"] == "anthropic:claude-3-5-haiku-20241022"
    assert models[1]["name"] == "claude-3-5-haiku-20241022 [Anthropic]"


@pytest.mark.asyncio
async def test_anthropic_get_models_fallback_on_failure(fake_httpx, anthropic_settings):
    # API returns a 500 error
    fake_httpx.responses.append((500, {}))

    provider = AnthropicProvider()
    models = await provider.get_models()

    # Should fall back to hardcoded models
    assert len(models) > 0
    sonnet5 = next((m for m in models if m["id"] == "anthropic:claude-sonnet-5"), None)
    assert sonnet5 is not None
    assert sonnet5["name"] == "Claude Sonnet 5 [Anthropic]"
    assert sonnet5["provider"] == "Anthropic"
