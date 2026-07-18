"""Retest endpoints must read keys from the credential store (not settings.json)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.credentials import file_backend, store


@pytest.fixture()
def cred_file(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    monkeypatch.setattr(file_backend, "CREDENTIALS_FILE", path)
    monkeypatch.setattr(store, "get_effective_mode", lambda: "file")
    monkeypatch.setattr(store, "_preferred_mode", lambda: "file")
    monkeypatch.setattr(store, "ENV_OVERRIDES", {})
    monkeypatch.setattr(store, "_disabled_secret_ids", lambda: set())
    yield path


@pytest.fixture()
def client(cred_file):
    from backend.main import app

    with TestClient(app, client=("127.0.0.1", 50000)) as c:
        yield c


def test_retest_uses_stored_anthropic_key(client, cred_file):
    store.set_secret("api:anthropic", "sk-ant-from-store")
    mock_validate = AsyncMock(return_value={"success": True, "message": "ok"})

    with patch("backend.providers.anthropic.AnthropicProvider.validate_key", mock_validate):
        resp = client.post(
            "/api/settings/test-provider",
            json={"provider_id": "anthropic", "api_key": ""},
        )

    assert resp.status_code == 200
    assert resp.json()["success"] is True
    mock_validate.assert_awaited_once_with("sk-ant-from-store")


def test_retest_without_store_or_request_fails(client, cred_file):
    resp = client.post(
        "/api/settings/test-provider",
        json={"provider_id": "anthropic", "api_key": ""},
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "success": False,
        "message": "No API key provided or configured",
    }
