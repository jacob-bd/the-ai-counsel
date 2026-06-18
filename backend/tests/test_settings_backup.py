"""Tests for settings export/import/reset endpoints."""
import json
import importlib
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


# We import the app after patching to avoid side effects during module load.
# The patches target backend.main's namespace where get_settings and save_settings
# are used (already imported at module level via `from .settings import ...`).


def _make_default_settings():
    from backend.settings import Settings
    return Settings()


def _make_settings_with_keys():
    """Return a Settings instance with some API keys set."""
    from backend.settings import Settings
    return Settings(
        openrouter_api_key="sk-or-test-key-123",
        groq_api_key="gsk_test_key_456",
    )


@pytest.fixture()
def client():
    """TestClient with mocked filesystem settings functions."""
    with patch("backend.main.get_settings") as mock_get, \
         patch("backend.main.save_settings") as mock_save:
        mock_get.return_value = _make_default_settings()
        mock_save.return_value = None
        from backend.main import app
        with TestClient(app, client=("127.0.0.1", 50000)) as c:
            # Expose mocks via the client so individual tests can reconfigure them.
            c._mock_get = mock_get
            c._mock_save = mock_save
            yield c


def _make_client(client_host="127.0.0.1"):
    """Create a TestClient with settings IO mocked and a specific peer host."""
    patch_get = patch("backend.main.get_settings")
    patch_save = patch("backend.main.save_settings")
    mock_get = patch_get.start()
    mock_save = patch_save.start()
    mock_get.return_value = _make_default_settings()
    mock_save.return_value = None

    from backend.main import app

    c = TestClient(app, client=(client_host, 50000))
    c._mock_get = mock_get
    c._mock_save = mock_save
    c._patches = (patch_get, patch_save)
    return c


def _close_client(c):
    c.close()
    for p in c._patches:
        p.stop()


# ---------------------------------------------------------------------------
# Export tests
# ---------------------------------------------------------------------------


def test_export_returns_json_download(client):
    """GET /api/settings/export should return 200 with Content-Disposition attachment."""
    response = client.get("/api/settings/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    cd = response.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert "council-settings.json" in cd


def test_export_includes_api_key_values(client):
    """Exported JSON must contain actual key fields, not _key_set booleans."""
    # Reconfigure mock to return settings with a real key value.
    client._mock_get.return_value = _make_settings_with_keys()
    response = client.get("/api/settings/export")
    assert response.status_code == 200
    data = response.json()
    # The real key value must be present (not a boolean *_key_set field).
    assert data.get("openrouter_api_key") == "sk-or-test-key-123"
    assert data.get("groq_api_key") == "gsk_test_key_456"
    # Ensure there are no *_key_set fields (those only appear in the secure GET endpoint).
    for key in data:
        assert not key.endswith("_key_set"), f"Unexpected boolean key field: {key}"


def test_export_rejects_remote_client_without_admin_token():
    """GET /api/settings/export rejects non-loopback callers when no admin token is set."""
    c = _make_client(client_host="203.0.113.10")
    try:
        response = c.get("/api/settings/export")
    finally:
        _close_client(c)

    assert response.status_code == 403


def test_export_rejects_proxied_remote_client_without_admin_token():
    """Loopback reverse proxies must not make external clients look like local admins."""
    c = _make_client(client_host="127.0.0.1")
    try:
        response = c.get(
            "/api/settings/export",
            headers={"X-Real-IP": "203.0.113.10"},
        )
    finally:
        _close_client(c)

    assert response.status_code == 403


def test_export_accepts_remote_client_with_admin_token(monkeypatch):
    """Bearer token allows explicit remote admin access."""
    monkeypatch.setenv("LLM_COUNCIL_ADMIN_TOKEN", "test-token")
    import backend.main as main
    importlib.reload(main)

    with patch("backend.main.get_settings") as mock_get, \
         patch("backend.main.save_settings") as mock_save:
        mock_get.return_value = _make_default_settings()
        mock_save.return_value = None
        with TestClient(main.app, client=("203.0.113.10", 50000)) as c:
            response = c.get(
                "/api/settings/export",
                headers={"Authorization": "Bearer test-token"},
            )

    assert response.status_code == 200

    monkeypatch.delenv("LLM_COUNCIL_ADMIN_TOKEN", raising=False)
    importlib.reload(main)


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------


def test_import_valid_settings(client):
    """POST /api/settings/import with a valid blob returns status=imported."""
    from backend.settings import Settings
    payload = Settings().model_dump(mode="json")
    response = client.post("/api/settings/import", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "imported"
    # save_settings should have been called exactly once.
    client._mock_save.assert_called_once()


def test_import_invalid_json(client):
    """POST /api/settings/import with non-JSON body returns 422."""
    response = client.post(
        "/api/settings/import",
        content=b"this is not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_import_invalid_settings(client):
    """POST /api/settings/import with a field of the wrong type returns 422."""
    # council_temperature must be a float; passing a string should fail validation.
    bad_payload = {"council_temperature": "not-a-number"}
    response = client.post("/api/settings/import", json=bad_payload)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Reset tests
# ---------------------------------------------------------------------------


def test_reset_returns_success(client):
    """POST /api/settings/reset returns status=reset."""
    response = client.post("/api/settings/reset")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "reset"


def test_reset_saves_defaults(client):
    """After reset, exported settings match fresh Settings() defaults."""
    # Call reset first.
    reset_resp = client.post("/api/settings/reset")
    assert reset_resp.status_code == 200

    # save_settings was called; grab the argument it was called with.
    call_args = client._mock_save.call_args
    assert call_args is not None
    saved_settings = call_args[0][0]  # First positional argument

    from backend.settings import Settings
    defaults = Settings()

    # Core defaults should match.
    assert saved_settings.council_temperature == defaults.council_temperature
    assert saved_settings.chairman_temperature == defaults.chairman_temperature
    assert saved_settings.council_models == defaults.council_models
    assert saved_settings.chairman_model == defaults.chairman_model
    # API keys should be None (default).
    assert saved_settings.openrouter_api_key is None
    assert saved_settings.groq_api_key is None


def test_get_settings_returns_council_title_query_and_advisor_prompts(client):
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()

    assert data["title_prompt"]
    assert data["query_prompt"]
    assert data["advisor_round1_prompt"]
    assert data["advisor_followup_prompt"]
    assert data["advisor_cross_pollination_prompt"]
    assert data["advisor_verdict_prompt"]
    assert data["advisor_tiebreaker_prompt"]


def test_update_settings_persists_council_title_query_and_advisor_prompts(client):
    from backend.settings import Settings

    payload = {
        "title_prompt": "Custom title {user_query}",
        "query_prompt": "Custom query {user_query}",
        "advisor_round1_prompt": "Custom round 1 {question}{consensus_tag}",
        "advisor_followup_prompt": "Custom followup {question}{transcript}{round_number}{previous_round_number}{cross_pollination_extract}{consensus_tag}",
        "advisor_cross_pollination_prompt": "Custom extract {question}{round_number}{round_transcript}",
        "advisor_verdict_prompt": "Custom verdict {question}{transcript}{debate_arc}",
        "advisor_tiebreaker_prompt": "Custom tiebreaker {question}{transcript}",
    }

    updated_settings = Settings(**payload)
    with patch("backend.main.update_settings", return_value=updated_settings) as mock_update:
        response = client.put("/api/settings", json=payload)

    assert response.status_code == 200
    mock_update.assert_called_once()
    update_kwargs = mock_update.call_args.kwargs
    for key, value in payload.items():
        assert update_kwargs[key] == value

    data = response.json()
    for key, value in payload.items():
        assert data[key] == value


def test_update_settings_persists_search_tuning_fields(client):
    from backend.settings import Settings

    payload = {
        "search_keyword_extraction": "llm",
        "search_result_count": 12,
        "search_hybrid_mode": False,
        "full_content_results": 7,
    }

    updated_settings = Settings(**payload)
    with patch("backend.main.update_settings", return_value=updated_settings) as mock_update:
        response = client.put("/api/settings", json=payload)

    assert response.status_code == 200
    mock_update.assert_called_once()
    update_kwargs = mock_update.call_args.kwargs
    for key, value in payload.items():
        assert update_kwargs[key] == value

    data = response.json()
    for key, value in payload.items():
        assert data[key] == value


def test_update_settings_rejects_invalid_search_result_count(client):
    response = client.put("/api/settings", json={"search_result_count": 16})

    assert response.status_code == 400
    assert "search_result_count" in response.json()["detail"]


def test_default_settings_returns_council_and_advisor_prompt_defaults(client):
    response = client.get("/api/settings/defaults")
    assert response.status_code == 200
    data = response.json()

    assert data["title_prompt"]
    assert data["query_prompt"]
    assert data["advisor_round1_prompt"]
    assert data["advisor_followup_prompt"]
    assert data["advisor_cross_pollination_prompt"]
    assert data["advisor_verdict_prompt"]
    assert data["advisor_tiebreaker_prompt"]


def test_settings_loader_backfills_blank_prompt_values(tmp_path, monkeypatch):
    from backend import settings as settings_module
    from backend.prompts import TITLE_PROMPT_DEFAULT, QUERY_PROMPT_DEFAULT
    from backend.advisor_prompts import ADVISOR_ROUND1_PROMPT

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "title_prompt": "",
        "query_prompt": "   ",
        "advisor_round1_prompt": "",
    }))
    monkeypatch.setattr(settings_module, "SETTINGS_FILE", settings_path)
    monkeypatch.setattr(settings_module, "_settings_cache", None)
    monkeypatch.setattr(settings_module, "_settings_mtime", 0.0)

    settings = settings_module.get_settings()

    assert settings.title_prompt == TITLE_PROMPT_DEFAULT
    assert settings.query_prompt == QUERY_PROMPT_DEFAULT
    assert settings.advisor_round1_prompt == ADVISOR_ROUND1_PROMPT


def test_settings_loader_clamps_persisted_advisor_default_rounds(tmp_path, monkeypatch):
    from backend import settings as settings_module

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"advisor_default_rounds": 2}))
    monkeypatch.setattr(settings_module, "SETTINGS_FILE", settings_path)
    monkeypatch.setattr(settings_module, "_settings_cache", None)
    monkeypatch.setattr(settings_module, "_settings_mtime", 0.0)

    settings = settings_module.get_settings()

    assert settings.advisor_default_rounds == 3
