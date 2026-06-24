import pytest
import json
import base64
import httpx
from unittest.mock import patch, AsyncMock
from backend.providers.custom_openai import CustomOpenAIProvider
from backend.settings import Settings

class _FakeResponse:
    def __init__(self, status_code, json_body=None, text="", headers=None):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text or json.dumps(self._json)
        self.headers = headers or {"content-type": "application/json"}

    def json(self):
        return self._json

    async def aread(self):
        return self.text.encode("utf-8")


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
        status, body, headers = type(self).responses.pop(0)
        return _FakeResponse(status, body, headers=headers)

    async def get(self, url, **kwargs):
        self.kwargs["__url__"] = url
        self.kwargs["__method__"] = "GET"
        self.kwargs.update(kwargs)
        if not type(self).responses:
            raise AssertionError("No scripted response left for httpx get")
        status, body, headers = type(self).responses.pop(0)
        return _FakeResponse(status, body, headers=headers)


@pytest.fixture
def fake_httpx(monkeypatch):
    _FakeAsyncClient.instances = []
    _FakeAsyncClient.responses = []
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient


@pytest.fixture
def custom_settings(monkeypatch):
    settings = Settings(
        custom_endpoint_name="TestCustom",
        custom_endpoint_url="http://127.0.0.1:8200/v1",
        custom_endpoint_api_key="test-key",
        custom_endpoint_supports_attachments=True,
    )
    monkeypatch.setattr("backend.providers.custom_openai.get_settings", lambda: settings)
    return settings


@pytest.mark.asyncio
async def test_custom_openai_query_sends_attachments_when_enabled(fake_httpx, custom_settings):
    fake_httpx.responses.append((
        200,
        {"choices": [{"message": {"content": "custom reply"}}], "usage": {"total_tokens": 5}},
        {}
    ))

    provider = CustomOpenAIProvider()
    attachments = [{"name": "file.pdf", "content_type": "application/pdf", "file_data": "base64bytes"}]

    result = await provider.query(
        "custom:gpt-5",
        [{"role": "user", "content": "hello"}],
        attachments=attachments,
    )

    assert result["content"] == "custom reply"
    assert not result["error"]

    sent = fake_httpx.instances[-1].kwargs
    assert sent["__url__"] == "http://127.0.0.1:8200/v1/chat/completions"
    assert sent["headers"]["Authorization"] == "Bearer test-key"
    assert sent["json"]["model"] == "gpt-5"
    assert sent["json"]["attachments"] == attachments


@pytest.mark.asyncio
async def test_custom_openai_query_omits_attachments_when_disabled(fake_httpx, custom_settings):
    custom_settings.custom_endpoint_supports_attachments = False
    fake_httpx.responses.append((
        200,
        {"choices": [{"message": {"content": "custom reply"}}], "usage": {"total_tokens": 5}},
        {}
    ))

    provider = CustomOpenAIProvider()
    attachments = [{"name": "file.pdf", "content_type": "application/pdf", "file_data": "base64bytes"}]

    result = await provider.query(
        "custom:gpt-5",
        [{"role": "user", "content": "hello"}],
        attachments=attachments,
    )

    assert not result["error"]
    sent = fake_httpx.instances[-1].kwargs
    assert "attachments" not in sent["json"]


@pytest.mark.asyncio
async def test_custom_openai_retry_limit_logic(fake_httpx, custom_settings, monkeypatch):
    # Mock sleep to avoid delay in tests
    monkeypatch.setattr("backend.providers.custom_openai.asyncio.sleep", AsyncMock())

    # 2 rate limit failures, then 1 success
    fake_httpx.responses.extend([
        (429, {"error": "rate limit"}, {"retry-after": "1"}),
        (503, {"error": "congestion"}, {}),
        (200, {"choices": [{"message": {"content": "recovered"}}]}, {})
    ])

    provider = CustomOpenAIProvider()
    result = await provider.query(
        "custom:gpt-5",
        [{"role": "user", "content": "hello"}],
    )

    assert result["content"] == "recovered"
    assert len(fake_httpx.instances) == 3
