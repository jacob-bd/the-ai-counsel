"""Tests for keyring backend chunking and migrate (fake keyring)."""

import pytest

from backend.credentials import keyring_backend, store


class FakeKeyring:
    def __init__(self):
        self.data = {}

    def get_password(self, service, account):
        return self.data.get((service, account))

    def set_password(self, service, account, password):
        self.data[(service, account)] = password

    def delete_password(self, service, account):
        self.data.pop((service, account), None)


@pytest.fixture()
def fake_kr(monkeypatch):
    fake = FakeKeyring()
    import keyring

    monkeypatch.setattr(keyring, "get_password", fake.get_password)
    monkeypatch.setattr(keyring, "set_password", fake.set_password)
    monkeypatch.setattr(keyring, "delete_password", fake.delete_password)
    return fake


def test_chunk_roundtrip(fake_kr):
    big = "x" * 2500
    keyring_backend.set_secret("oauth:openai-oauth", big)
    assert keyring_backend.get_secret("oauth:openai-oauth") == big
    meta = fake_kr.get_password(keyring_backend.SERVICE, "oauth:openai-oauth")
    assert meta.startswith(keyring_backend.KEYRING_CHUNK_PREFIX)
    keyring_backend.delete_secret("oauth:openai-oauth")
    assert keyring_backend.get_secret("oauth:openai-oauth") is None


@pytest.mark.asyncio
async def test_migrate_file_to_keyring(tmp_path, monkeypatch, fake_kr):
    from backend.credentials import file_backend

    path = tmp_path / "credentials.json"
    monkeypatch.setattr(file_backend, "CREDENTIALS_FILE", path)
    monkeypatch.setattr(store, "is_container_environment", lambda: False)
    monkeypatch.setattr(
        "backend.credentials.availability.probe_keyring",
        lambda: (True, None),
    )
    monkeypatch.setattr(
        "backend.credentials.store.probe_availability",
        lambda: {"file": True, "keyring": True, "unavailable_reason": None},
    )
    monkeypatch.setattr(store, "_preferred_mode", lambda: "file")
    monkeypatch.setattr(store, "get_effective_mode", lambda: "file")

    # Stub settings update
    calls = {}

    def fake_update(**kwargs):
        calls.update(kwargs)
        return None

    monkeypatch.setattr("backend.settings.update_settings", fake_update)
    monkeypatch.setattr("backend.settings.get_settings", lambda: type("S", (), {"credential_storage": "file"})())

    store.set_secret("api:openai", "sk-1")
    # Switch effective mode helpers during migrate
    monkeypatch.setattr(store, "get_effective_mode", lambda: "file")

    result = await store.migrate_storage_mode("keyring")
    assert result["moved"] >= 1
    assert keyring_backend.get_secret("api:openai") == "sk-1"
    assert calls.get("credential_storage") == "keyring"
