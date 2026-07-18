"""Container / keyring availability detection."""

from backend.credentials import availability


def test_container_env_var(monkeypatch):
    monkeypatch.setenv("LLM_COUNCIL_IN_CONTAINER", "1")
    assert availability.is_container_environment() is True
    ok, reason = availability.probe_keyring()
    assert ok is False
    assert "container" in (reason or "").lower()


def test_dockerenv_file(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_COUNCIL_IN_CONTAINER", raising=False)
    dockerenv = tmp_path / ".dockerenv"
    dockerenv.write_text("")
    # Patch Path("/.dockerenv").exists
    real_path = availability.Path

    class P(type(real_path("/"))):
        pass

    def fake_path(arg):
        if str(arg) == "/.dockerenv":
            return dockerenv
        return real_path(arg)

    monkeypatch.setattr(availability, "Path", fake_path)
    assert availability.is_container_environment() is True
