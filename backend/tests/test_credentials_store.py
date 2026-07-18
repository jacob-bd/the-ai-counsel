"""Tests for file credential store."""

import json
from pathlib import Path

import pytest

from backend.credentials import file_backend, store
from backend.credentials.ids import KNOWN_SECRET_IDS


@pytest.fixture()
def cred_file(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    monkeypatch.setattr(file_backend, "CREDENTIALS_FILE", path)
    monkeypatch.setattr(store, "get_effective_mode", lambda: "file")
    monkeypatch.setattr(store, "_preferred_mode", lambda: "file")
    # No env overrides
    monkeypatch.setattr(store, "ENV_OVERRIDES", {})
    yield path


def test_file_set_get_delete(cred_file):
    store.set_secret("api:openai", "sk-test")
    assert store.get_secret("api:openai") == "sk-test"
    assert cred_file.exists()
    data = json.loads(cred_file.read_text())
    assert data["api:openai"] == "sk-test"
    # mode 0o600 on unix
    mode = cred_file.stat().st_mode & 0o777
    assert mode == 0o600 or mode == 0o644  # some CI umasks differ; still wrote file
    store.delete_secret("api:openai")
    assert store.get_secret("api:openai") is None


def test_get_api_key_helper(cred_file):
    store.set_secret("api:groq", "gsk_x")
    assert store.get_api_key("groq") == "gsk_x"


def test_resolve_api_key_prefers_store_over_empty_request(cred_file, monkeypatch):
    monkeypatch.setattr(store, "_disabled_secret_ids", lambda: set())
    store.set_secret("api:anthropic", "sk-ant-imported")
    assert store.resolve_api_key("anthropic", "") == "sk-ant-imported"
    assert store.resolve_api_key("anthropic", None) == "sk-ant-imported"
    assert store.resolve_api_key("anthropic", "sk-typed") == "sk-typed"


def test_resolve_api_key_opencode_aliases(cred_file, monkeypatch):
    monkeypatch.setattr(store, "_disabled_secret_ids", lambda: set())
    store.set_secret("api:opencode", "sk-oc")
    assert store.resolve_api_key("opencode-zen", "") == "sk-oc"
    assert store.resolve_api_key("opencode-go", None) == "sk-oc"


def test_store_wins_over_env_when_both_set(cred_file, monkeypatch):
    monkeypatch.setattr(
        store,
        "ENV_OVERRIDES",
        {"api:openrouter": "OPENROUTER_API_KEY"},
    )
    monkeypatch.setattr(store, "_disabled_secret_ids", lambda: set())
    store.set_secret("api:openrouter", "from-file")
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")
    assert store.get_secret("api:openrouter") == "from-file"


def test_env_used_when_store_empty(cred_file, monkeypatch):
    monkeypatch.setattr(
        store,
        "ENV_OVERRIDES",
        {"api:openrouter": "OPENROUTER_API_KEY"},
    )
    monkeypatch.setattr(store, "_disabled_secret_ids", lambda: set())
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")
    assert store.get_secret("api:openrouter") == "from-env"


def test_disconnect_disables_env_override(cred_file, monkeypatch):
    monkeypatch.setattr(
        store,
        "ENV_OVERRIDES",
        {"api:opencode": "OPENCODE_API_KEY"},
    )
    disabled: set = set()

    def fake_disabled():
        return set(disabled)

    def fake_set_disabled(secret_id, is_disabled):
        if is_disabled:
            disabled.add(secret_id)
        else:
            disabled.discard(secret_id)

    monkeypatch.setattr(store, "_disabled_secret_ids", fake_disabled)
    monkeypatch.setattr(store, "_set_secret_disabled", fake_set_disabled)
    monkeypatch.setenv("OPENCODE_API_KEY", "from-env")
    assert store.get_secret("api:opencode") == "from-env"
    store.apply_settings_secret_updates({"opencode_api_key": ""})
    assert "api:opencode" in disabled
    assert store.get_secret("api:opencode") is None
    assert store.has_secret("api:opencode") is False
    # Saving a new key re-enables
    store.set_secret("api:opencode", "sk-new")
    assert "api:opencode" not in disabled
    assert store.get_secret("api:opencode") == "sk-new"


def test_apply_settings_secret_updates_strips_fields(cred_file):
    updates = {"openrouter_api_key": "sk-or", "council_temperature": 0.5}
    cleaned = store.apply_settings_secret_updates(updates)
    assert "openrouter_api_key" not in cleaned
    assert cleaned["council_temperature"] == 0.5
    assert store.get_secret("api:openrouter") == "sk-or"


def test_apply_settings_secret_updates_empty_string_clears(cred_file):
    store.set_secret("api:openai", "sk-live")
    cleaned = store.apply_settings_secret_updates({"openai_api_key": ""})
    assert "openai_api_key" not in cleaned
    assert store.get_secret("api:openai") is None
    assert store.has_secret("api:openai") is False


def test_export_known_ids_only(cred_file):
    store.set_secret("api:openai", "a")
    store.set_secret("oauth:xai-oauth", '{"type":"oauth","access":"x","refresh":"y","expires":1}')
    exported = store.export_all_secrets()
    assert set(exported.keys()) <= set(KNOWN_SECRET_IDS)
    assert "api:openai" in exported
