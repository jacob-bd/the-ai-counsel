"""Backend port resolution from PORT_BACKEND / LLM_COUNCIL_BIND_PORT."""

import pytest

from backend.main import _resolve_backend_port


def test_defaults_to_8001_when_unset(monkeypatch):
    monkeypatch.delenv("PORT_BACKEND", raising=False)
    monkeypatch.delenv("LLM_COUNCIL_BIND_PORT", raising=False)
    assert _resolve_backend_port() == 8001


def test_mcp_default_base_url_follows_port_backend(monkeypatch):
    monkeypatch.delenv("PORT_BACKEND", raising=False)
    from the_ai_counsel_mcp.client import default_base_url

    assert default_base_url() == "http://localhost:8001"
    monkeypatch.setenv("PORT_BACKEND", "9500")
    assert default_base_url() == "http://localhost:9500"


def test_reads_port_backend(monkeypatch):
    monkeypatch.delenv("LLM_COUNCIL_BIND_PORT", raising=False)
    monkeypatch.setenv("PORT_BACKEND", "9500")
    assert _resolve_backend_port() == 9500


def test_legacy_bind_port_takes_precedence(monkeypatch):
    """Existing deployments set LLM_COUNCIL_BIND_PORT; it must keep winning."""
    monkeypatch.setenv("PORT_BACKEND", "9500")
    monkeypatch.setenv("LLM_COUNCIL_BIND_PORT", "8500")
    assert _resolve_backend_port() == 8500


def test_blank_value_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("LLM_COUNCIL_BIND_PORT", raising=False)
    monkeypatch.setenv("PORT_BACKEND", "   ")
    assert _resolve_backend_port() == 8001


def test_surrounding_whitespace_is_tolerated(monkeypatch):
    monkeypatch.delenv("LLM_COUNCIL_BIND_PORT", raising=False)
    monkeypatch.setenv("PORT_BACKEND", " 8001 ")
    assert _resolve_backend_port() == 8001


@pytest.mark.parametrize("bad", ["abc", "70000", "0", "-1"])
def test_invalid_values_raise_an_actionable_error(monkeypatch, bad):
    """This resolves at import time, so a bare ValueError would break any
    importer -- the test suite and container healthcheck included."""
    monkeypatch.delenv("LLM_COUNCIL_BIND_PORT", raising=False)
    monkeypatch.setenv("PORT_BACKEND", bad)
    with pytest.raises(ValueError, match="PORT_BACKEND"):
        _resolve_backend_port()
