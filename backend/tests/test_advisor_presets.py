"""Tests for advisor preset settings persistence."""
import json

import pytest


def test_normalize_advisor_presets_validates_and_limits():
    from backend.settings import _normalize_advisor_presets

    raw = [
        {
            "id": "preset-1",
            "name": "Startup Panel",
            "persona_ids": ["skeptic", "pragmatist", "innovator"],
            "mode": "simple",
            "default_model": "openai:gpt-4.1",
            "max_rounds": 4,
            "is_default": True,
        },
        {
            "id": "",
            "name": "Invalid",
        },
        {
            "id": "preset-2",
            "name": "Advanced",
            "mode": "advanced",
            "model_assignments": {"skeptic": "openai:gpt-4.1", "pragmatist": "anthropic:claude-3.5-sonnet"},
            "max_rounds": 99,
            "is_default": True,
        },
    ]

    normalized = _normalize_advisor_presets(raw)

    assert len(normalized) == 2
    assert normalized[0]["name"] == "Startup Panel"
    assert normalized[0]["is_default"] is True
    assert normalized[1]["max_rounds"] == 10
    assert normalized[1]["is_default"] is False


def test_settings_loader_normalizes_advisor_presets(tmp_path, monkeypatch):
    from backend import settings as settings_module

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "advisor_presets": [
            {
                "id": "abc",
                "name": "Default Panel",
                "persona_ids": ["skeptic", "pragmatist"],
                "mode": "simple",
                "default_model": "openai:gpt-4.1",
                "is_default": True,
            }
        ]
    }))
    monkeypatch.setattr(settings_module, "SETTINGS_FILE", settings_path)
    monkeypatch.setattr(settings_module, "_settings_cache", None)
    monkeypatch.setattr(settings_module, "_settings_mtime", 0.0)

    settings = settings_module.get_settings()

    assert len(settings.advisor_presets) == 1
    assert settings.advisor_presets[0].name == "Default Panel"
    assert settings.advisor_presets[0].is_default is True


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


def test_put_settings_accepts_advisor_presets(client):
    payload = {
        "advisor_presets": [
            {
                "id": "preset-1",
                "name": "Quick Debate",
                "persona_ids": ["skeptic", "pragmatist"],
                "mode": "simple",
                "default_model": "openai:gpt-4.1",
                "is_default": True,
            }
        ]
    }

    response = client.put("/api/settings", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "advisor_presets" in data
    assert data["advisor_presets"][0]["name"] == "Quick Debate"
    client._mock_update.assert_called_once()
