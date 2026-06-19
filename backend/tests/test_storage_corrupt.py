"""Tests for corrupt conversation JSON handling."""

from fastapi.testclient import TestClient

from backend.main import app
from backend import storage


def test_corrupt_conversation_json_returns_404(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    storage.ensure_data_dir()

    conversation_id = "corrupt-conv"
    path = storage.get_conversation_path(conversation_id)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{not valid json")

    assert storage.get_conversation(conversation_id) is None

    with TestClient(app) as client:
        response = client.get(f"/api/conversations/{conversation_id}")

    assert response.status_code == 404


def test_missing_conversation_json_still_returns_404(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    storage.ensure_data_dir()

    with TestClient(app) as client:
        response = client.get("/api/conversations/missing-conv")

    assert response.status_code == 404


def test_valid_conversation_json_still_loads(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    conversation = storage.create_conversation("valid-conv")
    conversation["title"] = "Valid"
    storage.save_conversation(conversation)

    loaded = storage.get_conversation("valid-conv")
    assert loaded is not None
    assert loaded["title"] == "Valid"
