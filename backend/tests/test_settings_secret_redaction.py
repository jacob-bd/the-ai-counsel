"""settings.json must never persist API keys (credential store is source of truth)."""

import json

from backend.settings import Settings, save_settings


def test_save_settings_strips_api_keys(tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("backend.settings.SETTINGS_FILE", settings_file)

    save_settings(
        Settings(
            openrouter_api_key="sk-should-not-persist",
            anthropic_api_key="sk-ant-nope",
            council_models=["ollama:llama3"],
        )
    )

    on_disk = json.loads(settings_file.read_text())
    assert on_disk["openrouter_api_key"] is None
    assert on_disk["anthropic_api_key"] is None
    assert on_disk["council_models"] == ["ollama:llama3"]
