from __future__ import annotations

import base64
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import (
    SendMessageRequest,
    app,
    _build_council_preflight_models,
    _run_model_preflight,
)
from backend.model_preflight import ModelPreflightResult


def test_council_preflight_includes_chairman_for_full_mode():
    body = SendMessageRequest(
        content="Question?",
        execution_mode="full",
        council_models=["openai:gpt-4.1"],
        chairman_model="openrouter:chair",
    )

    assert _build_council_preflight_models(body) == [
        "openai:gpt-4.1",
        "openrouter:chair",
    ]


def test_council_preflight_skips_chairman_for_chat_only_mode():
    body = SendMessageRequest(
        content="Question?",
        execution_mode="chat_only",
        council_models=["openai:gpt-4.1"],
        chairman_model="openrouter:chair",
    )

    assert _build_council_preflight_models(body) == ["openai:gpt-4.1"]


def test_send_message_request_accepts_documents():
    body = SendMessageRequest(
        content="Question?",
        documents=[{"name": "notes.txt", "mime_type": "text/plain", "text": "Alpha"}],
    )

    assert body.documents[0]["text"] == "Alpha"


def test_extract_documents_multipart_text_file():
    with TestClient(app) as client:
        response = client.post(
            "/api/documents/extract",
            files=[("files", ("notes.txt", b"Alpha", "text/plain"))],
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["documents"][0]["text"] == "Alpha"
    assert payload["attachments"][0]["name"] == "notes.txt"
    assert "text" not in payload["attachments"][0]


def test_extract_documents_json_base64_text_file():
    encoded = base64.b64encode(b"Alpha").decode()

    with TestClient(app) as client:
        response = client.post(
            "/api/documents/extract-json",
            json={
                "documents": [{
                    "name": "notes.txt",
                    "mime_type": "text/plain",
                    "data_base64": encoded,
                }]
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["documents"][0]["text"] == "Alpha"
    assert payload["attachments"][0]["char_count"] == 5


@pytest.mark.asyncio
async def test_run_model_preflight_returns_user_facing_error_message():
    failed = ModelPreflightResult(
        failures=[{"model": "openrouter:bad-model", "error": "OpenRouter API error: 401"}]
    )

    with patch("backend.main.preflight_models", new_callable=AsyncMock) as mock_preflight:
        mock_preflight.return_value = failed

        message = await _run_model_preflight(["openrouter:bad-model"])

    assert "openrouter:bad-model" in message
    assert "401" in message
