"""relay-ai credential discovery/import."""

from backend.credentials import relay_import


def test_discover_empty_in_container(monkeypatch):
    monkeypatch.setattr(relay_import, "is_container_environment", lambda: True)
    result = relay_import.discover_relay_ai_credentials(force=True)
    assert result["items"] == []
    assert "container" in (result.get("reason") or "").lower()


def test_discover_requires_registry_when_missing(monkeypatch):
    monkeypatch.setattr(relay_import, "is_container_environment", lambda: False)
    monkeypatch.setattr(
        relay_import,
        "_relay_providers_path",
        lambda: type("P", (), {"exists": lambda self: False})(),
    )
    result = relay_import.discover_relay_ai_credentials(force=True)
    assert result["items"] == []
    assert "providers.json" in (result.get("reason") or "")


def test_discover_registry_only_probes_listed(monkeypatch):
    monkeypatch.setattr(relay_import, "is_container_environment", lambda: False)
    relay_import.clear_discover_cache()

    monkeypatch.setattr(
        relay_import,
        "_load_registry",
        lambda: (
            ["xai-oauth", "openai", "claude-code", "antigravity"],
            {"xai-oauth": "oauth", "openai": "api_key", "claude-code": "oauth"},
        ),
    )
    monkeypatch.setattr(
        relay_import,
        "_relay_providers_path",
        lambda: type("P", (), {"exists": lambda self: True})(),
    )

    probed = []

    def fake_raw(account):
        probed.append(account)
        if account == "oauth:provider:xai-oauth":
            return '{"type":"oauth","access":"a","refresh":"b","expires":1}'
        if account == "provider:openai":
            return "sk-test"
        return None

    monkeypatch.setattr(relay_import, "_read_relay_keyring_raw", fake_raw)
    monkeypatch.setattr(relay_import, "has_secret", lambda _sid: False)
    result = relay_import.discover_relay_ai_credentials(force=True)
    ids = {i["relay_id"] for i in result["items"]}
    assert "xai-oauth" in ids
    assert "openai" in ids
    assert "claude-code" not in ids
    assert "antigravity" not in ids
    assert not any("claude-code" in a or "antigravity" in a for a in probed)
    # Presence check only — no chunk reassembly calls via full reader
    for item in result["items"]:
        assert "access" not in item
        assert "refresh" not in item


def test_discover_cache_avoids_second_keyring_hit(monkeypatch):
    monkeypatch.setattr(relay_import, "is_container_environment", lambda: False)
    relay_import.clear_discover_cache()
    monkeypatch.setattr(
        relay_import,
        "_load_registry",
        lambda: (["xai-oauth"], {"xai-oauth": "oauth"}),
    )
    monkeypatch.setattr(
        relay_import,
        "_relay_providers_path",
        lambda: type("P", (), {"exists": lambda self: True})(),
    )
    calls = {"n": 0}

    def fake_raw(account):
        calls["n"] += 1
        return '{"type":"oauth","access":"a","refresh":"b","expires":1}'

    monkeypatch.setattr(relay_import, "_read_relay_keyring_raw", fake_raw)
    monkeypatch.setattr(relay_import, "has_secret", lambda _sid: False)
    first = relay_import.discover_relay_ai_credentials(force=True)
    second = relay_import.discover_relay_ai_credentials(force=False)
    assert first["items"]
    assert second["items"] == first["items"]
    assert calls["n"] == 1


def test_import_api_keys_enables_direct_providers(monkeypatch):
    """Import writes to credential store and enables toggles; settings.json stays key-free."""
    monkeypatch.setattr(relay_import, "is_container_environment", lambda: False)
    monkeypatch.setattr(relay_import, "has_secret", lambda _sid: False)
    stored = {}
    monkeypatch.setattr(
        relay_import,
        "set_secret",
        lambda sid, raw: stored.__setitem__(sid, raw),
    )
    monkeypatch.setattr(
        relay_import,
        "_read_relay_keyring",
        lambda account: {
            "provider:anthropic": "sk-ant-imported",
            "provider:openai": "sk-openai-imported",
        }.get(account),
    )

    updates = {}

    class FakeSettings:
        enabled_providers = {"direct": False, "openrouter": False}
        direct_provider_toggles = {"anthropic": False, "openai": False}

    monkeypatch.setattr(
        "backend.settings.get_settings",
        lambda: FakeSettings(),
    )

    def fake_update(**kwargs):
        updates.update(kwargs)
        return FakeSettings()

    monkeypatch.setattr("backend.settings.update_settings", fake_update)

    result = relay_import.import_relay_ai_credentials(
        ["anthropic", "openai"], replace_existing=True
    )
    assert result["imported"] == ["anthropic", "openai"]
    assert stored["api:anthropic"] == "sk-ant-imported"
    assert stored["api:openai"] == "sk-openai-imported"
    assert updates["enabled_providers"]["direct"] is True
    assert updates["direct_provider_toggles"]["anthropic"] is True
    assert updates["direct_provider_toggles"]["openai"] is True
