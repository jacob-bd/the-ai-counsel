"""Tests for council model normalization and validation."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from fastapi import HTTPException
from backend.main import SendMessageRequest, app, _build_council_preflight_models, _validate_council_request
from backend.model_validation import requires_chairman, validate_council_lineup
from backend.settings import DEFAULT_COUNCIL_MODELS, Settings, normalize_model_ids


def test_default_settings_council_models_is_empty_list():
    assert DEFAULT_COUNCIL_MODELS == []
    assert Settings().council_models == []


def test_normalize_model_ids_strips_and_deduplicates():
    assert normalize_model_ids([" openai:gpt-4.1 ", "", "openai:gpt-4.1", "  "]) == [
        "openai:gpt-4.1",
    ]


def test_requires_chairman_by_mode():
    assert requires_chairman("chat_only") is False
    assert requires_chairman("chat_ranking") is False
    assert requires_chairman("full") is True
    assert requires_chairman("chat_only", critique_mode="audit") is True


def test_validate_rejects_empty_council_lineup():
    with pytest.raises(ValueError, match="At least one council model"):
        validate_council_lineup([], None, execution_mode="chat_only")


def test_validate_rejects_full_mode_without_chairman():
    with pytest.raises(ValueError, match="chairman model is required"):
        validate_council_lineup(
            ["openai:gpt-4.1"],
            "",
            execution_mode="full",
        )


def test_build_preflight_models_skips_chairman_for_chat_only():
    body = SendMessageRequest(
        content="Question?",
        execution_mode="chat_only",
        council_models=["openai:gpt-4.1"],
        chairman_model="openrouter:chair",
    )

    assert _build_council_preflight_models(body) == ["openai:gpt-4.1"]


def test_build_preflight_models_includes_chairman_for_full_mode():
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


def test_empty_model_override_rejected_before_provider_dispatch(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.main.storage.DATA_DIR", str(tmp_path))
    from backend import storage

    storage.create_conversation("conv-empty-models")

    with patch("backend.council._query_model_gated", new_callable=AsyncMock) as mock_query:
        with TestClient(app) as client:
            response = client.post(
                "/api/conversations/conv-empty-models/message",
                json={
                    "content": "Question?",
                    "execution_mode": "chat_only",
                    "council_models": ["", "   "],
                },
            )

    assert response.status_code == 400
    assert "At least one council model" in response.json()["detail"]
    mock_query.assert_not_awaited()


def test_full_mode_without_chairman_rejected_before_provider_dispatch(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.main.storage.DATA_DIR", str(tmp_path))
    from backend import storage

    storage.create_conversation("conv-no-chair")

    with patch("backend.council._query_model_gated", new_callable=AsyncMock) as mock_query:
        with TestClient(app) as client:
            response = client.post(
                "/api/conversations/conv-no-chair/message",
                json={
                    "content": "Question?",
                    "execution_mode": "full",
                    "council_models": ["openai:gpt-4.1"],
                    "chairman_model": "   ",
                },
            )

    assert response.status_code == 400
    assert "chairman model is required" in response.json()["detail"]
    mock_query.assert_not_awaited()


def test_validate_council_request_raises_http_exception():
    body = SendMessageRequest(
        content="Question?",
        execution_mode="full",
        council_models=[],
        chairman_model="",
    )

    with pytest.raises(HTTPException) as exc_info:
        _validate_council_request(body)

    assert exc_info.value.status_code == 400
