"""Tests for council preset settings persistence."""
import json

import pytest


def test_normalize_council_presets_validates_and_limits():
    from backend.settings import _normalize_council_presets

    raw = [
        {
            "id": "preset-1",
            "name": "Coding Council",
            "council_models": ["openai:gpt-4.1", "anthropic:claude-3.5-sonnet"],
            "chairman_model": "openai:gpt-4.1",
            "is_default": True,
        },
        {"id": "", "name": "Invalid"},
        {
            "id": "preset-2",
            "name": "Also Default",
            "council_models": ["ollama:llama3"],
            "is_default": True,
        },
    ]

    normalized = _normalize_council_presets(raw)

    assert len(normalized) == 2
    assert normalized[0]["name"] == "Coding Council"
    assert normalized[0]["is_default"] is True
    assert normalized[1]["is_default"] is False
    assert normalized[0]["council_models"] == ["openai:gpt-4.1", "anthropic:claude-3.5-sonnet"]


def test_settings_loader_normalizes_council_presets(tmp_path, monkeypatch):
    from backend import settings as settings_module

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "council_presets": [
            {
                "id": "abc",
                "name": "Daily Driver",
                "council_models": ["openai:gpt-4.1"],
                "chairman_model": "openai:gpt-4.1",
                "is_default": True,
            }
        ]
    }))
    monkeypatch.setattr(settings_module, "SETTINGS_FILE", settings_path)
    monkeypatch.setattr(settings_module, "_settings_cache", None)
    monkeypatch.setattr(settings_module, "_settings_mtime", 0.0)

    settings = settings_module.get_settings()

    assert len(settings.council_presets) == 1
    assert settings.council_presets[0].name == "Daily Driver"
    assert settings.council_presets[0].is_default is True


@pytest.fixture()
def client():
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from backend.settings import Settings

    with patch("backend.main.get_settings") as mock_get, \
         patch("backend.main.save_settings") as mock_save, \
         patch("backend.main.update_settings") as mock_update:
        mock_get.return_value = Settings()
        mock_update.side_effect = lambda **kwargs: Settings(**{**Settings().model_dump(), **kwargs})
        from backend.main import app
        with TestClient(app, client=("127.0.0.1", 50000)) as c:
            c._mock_update = mock_update
            yield c


def test_put_settings_accepts_council_presets(client):
    payload = {
        "council_presets": [
            {
                "id": "preset-1",
                "name": "Quick Council",
                "council_models": ["openai:gpt-4.1", "google:gemini-2.0-flash"],
                "chairman_model": "openai:gpt-4.1",
                "is_default": True,
            }
        ]
    }

    response = client.put("/api/settings", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "council_presets" in data
    assert data["council_presets"][0]["name"] == "Quick Council"
    client._mock_update.assert_called_once()
