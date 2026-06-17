from __future__ import annotations

import base64
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import (
    PipelineResult,
    SendMessageRequest,
    app,
    _build_council_preflight_models,
    _run_model_preflight,
)
from backend.model_preflight import ModelPreflightResult
from backend import storage


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


def test_sync_message_passes_effective_content_and_stores_attachment_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    storage.create_conversation("conv-doc-sync")
    captured = {}

    async def fake_pipeline(content, *args, **kwargs):
        captured["content"] = content
        return PipelineResult(
            stage1=[{"model": "model_a", "response": "ok", "error": None}],
            cost_report={"total_cost": 0, "total_calls": 0},
        )

    with patch("backend.main._run_model_preflight", new_callable=AsyncMock) as preflight:
        preflight.return_value = ""
        with patch("backend.main._run_council_pipeline", side_effect=fake_pipeline):
            with TestClient(app) as client:
                response = client.post(
                    "/api/conversations/conv-doc-sync/message",
                    json={
                        "content": "Summarize.",
                        "execution_mode": "chat_only",
                        "documents": [{
                            "name": "notes.txt",
                            "mime_type": "text/plain",
                            "text": "Document fact: Alpha",
                        }],
                    },
                )

    assert response.status_code == 200
    assert "Attached Documents" in captured["content"]
    assert "Document fact: Alpha" in captured["content"]
    saved = storage.get_conversation("conv-doc-sync")
    user_message = saved["messages"][0]
    assert user_message["content"] == "Summarize."
    assert user_message["attachments"][0]["name"] == "notes.txt"
    assert "text" not in user_message["attachments"][0]


def test_iterative_debate_passes_effective_content(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    storage.create_conversation("conv-doc-debate")
    captured = {}

    async def fake_debate(content, *args, **kwargs):
        captured["content"] = content
        yield {"type": "debate_complete", "rounds": [], "cost_report": {"total_cost": 0, "total_calls": 0}}

    with patch("backend.main._run_model_preflight", new_callable=AsyncMock) as preflight:
        preflight.return_value = ""
        with patch("backend.main.generate_conversation_title", new_callable=AsyncMock) as title:
            title.return_value = "Document Debate"
            with patch("backend.main.run_iterative_debate", side_effect=fake_debate):
                with TestClient(app) as client:
                    with client.stream(
                        "POST",
                        "/api/conversations/conv-doc-debate/message/debate",
                        json={
                            "content": "Debate this.",
                            "execution_mode": "chat_only",
                            "documents": [{
                                "name": "notes.txt",
                                "mime_type": "text/plain",
                                "text": "Document fact: Beta",
                            }],
                        },
                    ) as response:
                        list(response.iter_text())

    assert response.status_code == 200
    assert "Attached Documents" in captured["content"]
    assert "Document fact: Beta" in captured["content"]


def test_advisor_debate_passes_effective_question(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    storage.create_conversation("conv-doc-advisor", mode="advisors")
    captured = {}

    async def fake_advisor_debate(**kwargs):
        captured["question"] = kwargs["question"]
        yield {
            "type": "advisor_complete",
            "data": {
                "rounds": [],
                "verdict": {"content": "verdict"},
                "tiebreaker": None,
                "personas": [],
                "cost_report": {"total_cost": 0, "total_calls": 0},
            },
        }

    with patch("backend.main.generate_conversation_title", new_callable=AsyncMock) as title:
        title.return_value = "Advisor Documents"
        with patch("backend.main.run_debate", side_effect=fake_advisor_debate):
            with TestClient(app) as client:
                with client.stream(
                    "POST",
                    "/api/conversations/conv-doc-advisor/debate/stream",
                    json={
                        "question": "Should we approve?",
                        "persona_ids": ["skeptic", "pragmatist"],
                        "default_model": "openai:gpt-4.1",
                        "max_rounds": 3,
                        "documents": [{
                            "name": "brief.txt",
                            "mime_type": "text/plain",
                            "text": "Document fact: Gamma",
                        }],
                    },
                ) as response:
                    list(response.iter_text())

    assert response.status_code == 200
    assert "Attached Documents" in captured["question"]
    assert "Document fact: Gamma" in captured["question"]


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
