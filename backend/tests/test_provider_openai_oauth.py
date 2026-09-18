"""ChatGPT OAuth Responses provider mapping and live listing."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.providers.openai_oauth import (
    CHATGPT_CODEX_UNSUPPORTED,
    CODEX_MODELS_CLIENT_VERSION,
    OPENAI_OAUTH_MODEL_SEEDS,
    OpenAIOauthProvider,
    _entries_to_models,
    _extract_responses_text,
    _messages_to_responses_input,
    _parse_chatgpt_model_entries,
    model_needs_responses_lite,
    model_transport_flags,
)


def test_messages_to_responses_splits_system():
    instructions, items = _messages_to_responses_input(
        [
            {"role": "system", "content": "Be brief"},
            {"role": "user", "content": "Hello"},
        ]
    )
    assert instructions == "Be brief"
    assert items[0]["role"] == "user"
    assert items[0]["content"][0]["text"] == "Hello"


def test_extract_output_text():
    assert _extract_responses_text({"output_text": "hi"}) == "hi"
    assert (
        _extract_responses_text(
            {
                "output": [
                    {"content": [{"type": "output_text", "text": "a"}, {"text": "b"}]}
                ]
            }
        )
        == "ab"
    )


def test_luna_supported_via_responses_lite():
    assert "gpt-5.6-luna" not in CHATGPT_CODEX_UNSUPPORTED
    assert model_needs_responses_lite("gpt-5.6-luna")
    flags = model_transport_flags("gpt-5.6-luna")
    assert flags["prefer_websockets"] is True
    assert flags["use_responses_lite"] is True
    luna = next(s for s in OPENAI_OAUTH_MODEL_SEEDS if s["id"] == "gpt-5.6-luna")
    assert luna.get("prefer_websockets") is True
    assert luna.get("use_responses_lite") is True


def test_parse_chatgpt_slug_catalog():
    entries = _parse_chatgpt_model_entries(
        {
            "models": [
                {
                    "slug": "gpt-5.6-luna",
                    "title": "GPT-5.6 Luna",
                    "prefer_websockets": True,
                    "use_responses_lite": True,
                },
                {"slug": "gpt-5.6-sol", "title": "GPT-5.6 Sol", "prefer_websockets": True},
                {"slug": "gpt-5.5-fast", "title": "should be filtered later"},
            ]
        }
    )
    assert [e["id"] for e in entries] == ["gpt-5.6-luna", "gpt-5.6-sol", "gpt-5.5-fast"]
    assert entries[0]["prefer_websockets"] is True


def test_entries_to_models_filters_unsupported_and_marks_lite():
    models = _entries_to_models(
        [
            {
                "id": "gpt-5.6-luna",
                "name": "gpt-5.6-luna",  # slug-as-name → prefer seed title
                "prefer_websockets": True,
                "use_responses_lite": True,
            },
            {"id": "gpt-5.5-fast", "name": "Fast"},
            {"id": "gpt-5.6-sol", "name": "gpt-5.6-sol", "prefer_websockets": True},
        ]
    )
    ids = {m["id"] for m in models}
    assert "openai-oauth:gpt-5.6-luna" in ids
    assert "openai-oauth:gpt-5.6-sol" in ids
    assert "openai-oauth:gpt-5.5-fast" not in ids
    luna = next(m for m in models if m["id"] == "openai-oauth:gpt-5.6-luna")
    assert luna["prefer_websockets"] is True
    assert luna["name"] == "GPT-5.6 Luna [ChatGPT]"
    assert model_needs_responses_lite("gpt-5.6-luna")


@pytest.mark.asyncio
async def test_get_models_uses_live_codex_catalog():
    provider = OpenAIOauthProvider()
    mock_cred = {"access": "tok", "accountId": "acc"}

    class _Resp:
        status_code = 200

        def json(self):
            return {
                "models": [
                    {
                        "slug": "gpt-5.6-luna",
                        "prefer_websockets": True,
                        "use_responses_lite": True,
                    },
                    {"slug": "gpt-5.6-terra", "prefer_websockets": True, "use_responses_lite": True},
                ]
            }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_Resp())
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("backend.providers.openai_oauth.get_oauth_credential", return_value=mock_cred),
        patch(
            "backend.providers.openai_oauth.get_valid_access_token",
            AsyncMock(return_value="access-token"),
        ),
        patch("backend.providers.openai_oauth.httpx.AsyncClient", return_value=mock_client),
    ):
        models = await provider.get_models()

    ids = [m["id"] for m in models]
    assert ids == ["openai-oauth:gpt-5.6-luna", "openai-oauth:gpt-5.6-terra"]
    assert models[0]["prefer_websockets"] is True
    assert models[0]["name"] == "GPT-5.6 Luna [ChatGPT]"
    mock_client.get.assert_awaited()
    _, kwargs = mock_client.get.await_args
    assert kwargs["params"]["client_version"] == CODEX_MODELS_CLIENT_VERSION


@pytest.mark.asyncio
async def test_query_luna_uses_websocket_transport():
    provider = OpenAIOauthProvider()
    mock_cred = {"access": "tok", "accountId": "acc"}
    ws_result = {"content": "hello from luna", "usage": {"total_tokens": 3}, "error": False}

    with (
        patch("backend.providers.openai_oauth.get_oauth_credential", return_value=mock_cred),
        patch(
            "backend.providers.openai_oauth.get_valid_access_token",
            AsyncMock(return_value="access-token"),
        ),
        patch(
            "backend.providers.openai_oauth.query_codex_responses_websocket",
            AsyncMock(return_value=ws_result),
        ) as ws_mock,
    ):
        result = await provider.query(
            "openai-oauth:gpt-5.6-luna",
            [{"role": "user", "content": "hi"}],
        )

    assert result == ws_result
    ws_mock.assert_awaited_once()
    kwargs = ws_mock.await_args.kwargs
    assert kwargs["payload"]["model"] == "gpt-5.6-luna"
    assert kwargs["use_responses_lite"] is True
    assert kwargs["headers"]["ChatGPT-Account-Id"] == "acc"


@pytest.mark.asyncio
async def test_responses_lite_websocket_collects_text():
    from backend.oauth.responses_websocket import query_codex_responses_websocket

    frames = [
        '{"type":"response.output_text.delta","delta":"Hel"}',
        '{"type":"response.output_text.delta","delta":"lo"}',
        '{"type":"response.completed","response":{"usage":{"total_tokens":2}}}',
    ]

    class _FakeWs:
        def __init__(self):
            self._i = 0
            self.sent = []

        async def send(self, msg):
            self.sent.append(msg)

        async def recv(self):
            if self._i >= len(frames):
                raise AssertionError("recv past end")
            frame = frames[self._i]
            self._i += 1
            return frame

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    fake = _FakeWs()
    with patch("backend.oauth.responses_websocket.websockets.connect", return_value=fake):
        result = await query_codex_responses_websocket(
            payload={"model": "gpt-5.6-luna", "input": [], "stream": True},
            headers={"Authorization": "Bearer x"},
            timeout=5.0,
            use_responses_lite=True,
        )

    assert result["error"] is False
    assert result["content"] == "Hello"
    assert result["usage"]["total_tokens"] == 2
    assert "response.create" in fake.sent[0]
