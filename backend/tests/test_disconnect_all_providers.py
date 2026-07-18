"""Disconnect-all clears credential store and disables providers."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.credentials import file_backend, store
from backend.credentials.ids import KNOWN_SECRET_IDS
from backend.settings import Settings


@pytest.fixture()
def cred_file(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    monkeypatch.setattr(file_backend, "CREDENTIALS_FILE", path)
    monkeypatch.setattr(store, "get_effective_mode", lambda: "file")
    monkeypatch.setattr(store, "_preferred_mode", lambda: "file")
    monkeypatch.setattr(store, "ENV_OVERRIDES", {})
    yield path


def test_disconnect_all_credentials_wipes_and_disables(cred_file, monkeypatch):
    store.set_secret("api:anthropic", "sk-ant")
    store.set_secret("api:openai", "sk-openai")
    # Clear disabled so keys are readable before disconnect.
    monkeypatch.setattr(store, "_disabled_secret_ids", lambda: set())

    updates = {}

    class FakeSettings:
        enabled_providers = {"direct": True, "openrouter": True}
        direct_provider_toggles = {"anthropic": True, "openai": True}

    monkeypatch.setattr("backend.settings.get_settings", lambda: FakeSettings())

    def fake_update(**kwargs):
        updates.update(kwargs)
        return FakeSettings()

    monkeypatch.setattr("backend.settings.update_settings", fake_update)

    result = store.disconnect_all_credentials()
    assert result["cleared"] == 2
    assert file_backend.get_secret("api:anthropic") is None
    assert file_backend.get_secret("api:openai") is None
    assert set(updates["disabled_secret_ids"]) == set(KNOWN_SECRET_IDS)
    assert updates["enabled_providers"]["direct"] is False
    assert updates["direct_provider_toggles"]["anthropic"] is False
    assert updates["custom_endpoint_url"] == ""


def test_disconnect_all_endpoint(cred_file, monkeypatch):
    store.set_secret("api:groq", "gsk-test")
    monkeypatch.setattr(store, "_disabled_secret_ids", lambda: set())

    with patch("backend.main.get_settings", return_value=Settings()), \
         patch("backend.main.update_settings", side_effect=lambda **kw: Settings(**{**Settings().model_dump(), **kw})), \
         patch("backend.main.build_settings_response", return_value={"ok": True}):
        from backend.main import app

        with TestClient(app, client=("127.0.0.1", 50000)) as client:
            resp = client.post("/api/settings/disconnect-all-providers")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "disconnected"
    assert body["cleared"] >= 1
    assert file_backend.get_secret("api:groq") is None
