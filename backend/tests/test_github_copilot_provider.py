"""GitHub Copilot model filtering, plan classification, and error mapping."""

from backend.oauth.github_copilot import classify_copilot_account
from backend.providers.github_copilot import (
    _copilot_model_allowed,
    _friendly_copilot_error,
    _is_copilot_free_model,
    _normalize_copilot_models,
)


def test_classify_free_sku():
    account = classify_copilot_account(
        {"login": "alice", "access_type_sku": "free_limited_copilot", "copilot_plan": "individual"}
    )
    assert account["is_free_plan"] is True
    assert account["login"] == "alice"


def test_classify_student_sku():
    account = classify_copilot_account(
        {"access_type_sku": "free_educational_quota", "copilot_plan": "individual"}
    )
    assert account["is_free_plan"] is True


def test_classify_paid_plan():
    account = classify_copilot_account(
        {"access_type_sku": "copilot_individual_pro", "copilot_plan": "individual_pro"}
    )
    assert account["is_free_plan"] is False


def test_free_plan_allowlist_hides_premium_and_gpt5_mini():
    rows = [
        {"id": "gpt-4.1", "model_picker_enabled": True},
        {"id": "gpt-4o", "model_picker_enabled": True},
        {"id": "gpt-5-mini", "model_picker_enabled": True, "billing": {"multiplier": 0}},
        {"id": "gemini-3.5-flash", "model_picker_enabled": True},
        {"id": "gpt-5.4", "model_picker_enabled": True},
    ]
    free_ids = {m["id"] for m in _normalize_copilot_models(rows, is_free_plan=True)}
    paid_ids = {m["id"] for m in _normalize_copilot_models(rows, is_free_plan=False)}
    assert free_ids == {"github-copilot:gpt-4.1", "github-copilot:gpt-4o"}
    assert "github-copilot:gpt-5.4" in paid_ids
    assert "github-copilot:gemini-3.5-flash" in paid_ids
    assert "github-copilot:gpt-5-mini" not in free_ids


def test_copilot_excludes_auto_router_aliases():
    rows = [
        {"id": "gpt-5.6-luna-free-auto", "model_picker_enabled": True},
        {"id": "goldeneye-free-auto", "model_picker_enabled": True},
        {"id": "gpt-4.1", "model_picker_enabled": True},
        {"id": "text-embedding-3-small", "model_picker_enabled": True},
    ]
    models = _normalize_copilot_models(rows, is_free_plan=True)
    ids = {m["id"] for m in models}
    assert ids == {"github-copilot:gpt-4.1"}


def test_copilot_requires_chat_completions_endpoint_when_listed():
    rows = [
        {
            "id": "responses-only",
            "model_picker_enabled": True,
            "supported_endpoints": ["/responses"],
        },
        {
            "id": "gpt-4o",
            "model_picker_enabled": True,
            "supported_endpoints": ["/chat/completions"],
        },
    ]
    models = _normalize_copilot_models(rows, is_free_plan=False)
    ids = {m["id"] for m in models}
    assert ids == {"github-copilot:gpt-4o"}


def test_copilot_free_label_on_included_models():
    rows = [
        {"id": "gpt-4.1", "billing": {"multiplier": 0}},
        {"id": "gemini-3.5-flash", "billing": {"multiplier": 14}, "model_picker_enabled": True},
        {"id": "gpt-4o"},
    ]
    by_id = {m["id"]: m for m in _normalize_copilot_models(rows, is_free_plan=False)}
    assert by_id["github-copilot:gpt-4.1"]["is_free"] is True
    assert "· Free" in by_id["github-copilot:gpt-4.1"]["name"]
    assert by_id["github-copilot:gpt-4o"]["is_free"] is True
    assert by_id["github-copilot:gemini-3.5-flash"]["is_free"] is False


def test_is_copilot_free_model_multiplier():
    assert _is_copilot_free_model({"id": "x", "billing": {"multiplier": 0}}) is True
    assert _is_copilot_free_model({"id": "x", "billing": {"multiplier": 0.33}}) is False
    assert _is_copilot_free_model({"id": "gpt-5.6-luna-free-auto"}) is False


def test_copilot_model_allowed_defaults():
    assert _copilot_model_allowed({"id": "gpt-4o"}, is_free_plan=True) is True
    assert _copilot_model_allowed({"id": "gpt-5-mini"}, is_free_plan=True) is False
    assert _copilot_model_allowed({"id": "gpt-5.4"}, is_free_plan=False) is True


def test_friendly_model_not_supported_message():
    body = (
        '{"error":{"message":"The requested model is not supported.",'
        '"code":"model_not_supported"}}'
    )
    msg = _friendly_copilot_error(400, body)
    assert "Auto/router" in msg
    assert "gpt-4.1" in msg
