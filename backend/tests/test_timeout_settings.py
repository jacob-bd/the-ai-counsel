"""Tests for configurable timeout settings."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from backend.settings import Settings

def _make_default_settings():
    return Settings()

@pytest.fixture()
def client():
    with patch("backend.main.get_settings") as mock_main_get, \
         patch("backend.main.save_settings") as mock_main_save, \
         patch("backend.settings.get_settings") as mock_settings_get, \
         patch("backend.settings.save_settings") as mock_settings_save:
        
        # Return a fresh Settings instance on every call to avoid cross-test contamination
        mock_main_get.side_effect = _make_default_settings
        mock_settings_get.side_effect = _make_default_settings
        mock_main_save.return_value = None
        mock_settings_save.return_value = None
        
        from backend.main import app
        with TestClient(app, client=("127.0.0.1", 50000)) as c:
            c._mock_get = mock_settings_get
            c._mock_save = mock_settings_save
            yield c

def test_get_settings_contains_timeouts(client):
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["model_timeout_seconds"] == 300
    assert data["preflight_timeout_seconds"] == 10.0
    assert data["claim_extraction_timeout_seconds"] == 180.0

def test_update_settings_timeouts_valid(client):
    payload = {
        "model_timeout_seconds": 500,
        "preflight_timeout_seconds": 25.5,
        "claim_extraction_timeout_seconds": 120.0,
    }
    response = client.put("/api/settings", json=payload)
    assert response.status_code == 200
    assert client._mock_save.called
    saved_updates = client._mock_save.call_args[0][0]
    assert saved_updates.model_timeout_seconds == 500
    assert saved_updates.preflight_timeout_seconds == 25.5
    assert saved_updates.claim_extraction_timeout_seconds == 120.0

def test_update_settings_timeouts_invalid_range(client):
    # Test out of bounds model timeout
    response = client.put("/api/settings", json={"model_timeout_seconds": 10})
    assert response.status_code == 400
    assert "model_timeout_seconds" in response.json()["detail"]

    # Test out of bounds preflight timeout
    response = client.put("/api/settings", json={"preflight_timeout_seconds": 0.5})
    assert response.status_code == 400
    assert "preflight_timeout_seconds" in response.json()["detail"]

    # Test out of bounds claim extraction timeout
    response = client.put("/api/settings", json={"claim_extraction_timeout_seconds": 5.0})
    assert response.status_code == 400
    assert "claim_extraction_timeout_seconds" in response.json()["detail"]
