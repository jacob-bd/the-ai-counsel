"""Tests for settings mutation and provider test endpoint authorization."""

import importlib
from unittest.mock import patch

from fastapi.testclient import TestClient


def _make_client(client_host="127.0.0.1"):
    patch_get = patch("backend.main.get_settings")
    patch_save = patch("backend.main.save_settings")
    mock_get = patch_get.start()
    mock_save = patch_save.start()
    from backend.settings import Settings

    mock_get.return_value = Settings()
    mock_save.return_value = None

    from backend.main import app

    client = TestClient(app, client=(client_host, 50000))
    client._patches = (patch_get, patch_save)
    return client


def _close_client(client):
    client.close()
    for patch_obj in client._patches:
        patch_obj.stop()


def test_remote_put_settings_rejected_without_admin_token():
    client = _make_client(client_host="203.0.113.10")
    try:
        response = client.put(
            "/api/settings",
            json={"search_result_count": 8},
        )
    finally:
        _close_client(client)

    assert response.status_code == 403


def test_remote_settings_test_endpoint_rejected_without_admin_token():
    client = _make_client(client_host="203.0.113.10")
    try:
        response = client.post(
            "/api/settings/test-tavily",
            json={"api_key": "tvly-test"},
        )
    finally:
        _close_client(client)

    assert response.status_code == 403


def test_loopback_settings_update_allowed_without_admin_token():
    client = _make_client(client_host="127.0.0.1")
    try:
        response = client.put(
            "/api/settings",
            json={"search_result_count": 8},
        )
    finally:
        _close_client(client)

    assert response.status_code == 200


def test_remote_settings_update_allowed_with_admin_token(monkeypatch):
    monkeypatch.setenv("LLM_COUNCIL_ADMIN_TOKEN", "test-token")
    import backend.main as main

    importlib.reload(main)

    with patch("backend.main.get_settings") as mock_get, patch("backend.main.save_settings") as mock_save:
        from backend.settings import Settings

        mock_get.return_value = Settings()
        mock_save.return_value = None
        with TestClient(main.app, client=("203.0.113.10", 50000)) as client:
            response = client.put(
                "/api/settings",
                json={"search_result_count": 8},
                headers={"Authorization": "Bearer test-token"},
            )

    assert response.status_code == 200

    monkeypatch.delenv("LLM_COUNCIL_ADMIN_TOKEN", raising=False)
    importlib.reload(main)
