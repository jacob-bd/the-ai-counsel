"""Tests for the accessible font-size setting."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def test_font_size_defaults_to_default():
    from backend.settings import FONT_SIZE_DEFAULT, Settings

    assert FONT_SIZE_DEFAULT == "default"
    assert Settings().font_size == FONT_SIZE_DEFAULT


def test_missing_and_invalid_font_size_normalize_to_default():
    from backend.settings import _normalize_prompt_defaults

    assert _normalize_prompt_defaults({})["font_size"] == "default"
    assert _normalize_prompt_defaults({"font_size": "giant"})["font_size"] == "default"
    assert _normalize_prompt_defaults({"font_size": "xlarge"})["font_size"] == "default"


def test_valid_font_size_is_preserved():
    from backend.settings import _normalize_prompt_defaults

    assert _normalize_prompt_defaults({"font_size": "large"})["font_size"] == "large"


@pytest.fixture()
def settings_client():
    from backend.main import app
    from backend.settings import Settings

    with patch("backend.main.update_settings") as update_settings, \
         patch("backend.main.build_settings_response") as build_settings_response, \
         patch("backend.main.apply_settings_secret_updates", side_effect=lambda updates: updates):
        update_settings.side_effect = lambda **updates: Settings(**updates)
        build_settings_response.side_effect = lambda settings: {"font_size": settings.font_size}
        with TestClient(app) as client:
            yield client


def test_put_settings_accepts_font_size_and_returns_persisted_value(settings_client):
    response = settings_client.put("/api/settings", json={"font_size": "large"})

    assert response.status_code == 200
    assert response.json()["font_size"] == "large"


def test_put_settings_rejects_unknown_font_size(settings_client):
    response = settings_client.put("/api/settings", json={"font_size": "giant"})

    assert response.status_code == 400
    assert "font_size" in response.json()["detail"]
