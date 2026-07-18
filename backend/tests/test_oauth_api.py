"""OAuth FastAPI endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend.credentials import file_backend, store

    monkeypatch.setattr(file_backend, "CREDENTIALS_FILE", tmp_path / "credentials.json")
    monkeypatch.setattr(store, "get_effective_mode", lambda: "file")
    monkeypatch.setattr(store, "_preferred_mode", lambda: "file")

    with patch("backend.settings_payload.ensure_credentials_upgraded", return_value=False):
        from backend.main import app

        with TestClient(app, client=("127.0.0.1", 50000)) as c:
            yield c


def test_settings_redacts_secrets(client):
    data = client.get("/api/settings").json()
    assert "openrouter_api_key" not in data
    assert "xai_oauth_connected" in data
    assert "credential_storage_available" in data
    assert data["credential_storage_available"]["file"] is True


def test_oauth_start_allowlist(client):
    r = client.post("/api/oauth/claude-code/start")
    assert r.status_code == 400


def test_oauth_start_success(client):
    with patch(
        "backend.main.start_oauth_session",
        new=AsyncMock(
            return_value={
                "session_id": "s1",
                "provider_id": "xai-oauth",
                "user_code": "ABCD",
                "verification_uri": "https://example.com",
                "expires_in": 300,
                "status": "pending",
            }
        ),
    ):
        r = client.post("/api/oauth/xai-oauth/start")
    assert r.status_code == 200
    assert r.json()["user_code"] == "ABCD"
