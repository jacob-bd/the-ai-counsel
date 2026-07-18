"""Build API settings payloads with credential redaction."""

from __future__ import annotations

from typing import Any, Dict

from .credentials import get_availability, has_secret
from .credentials.ids import SETTINGS_FIELD_TO_SECRET_ID
from .credentials.upgrade import ensure_credentials_upgraded
from .prompts import RESPONSE_LANGUAGE_DEFAULT, VALID_RESPONSE_LANGUAGES
from .settings import get_settings


def _key_set(secret_id: str) -> bool:
    return has_secret(secret_id)


def _github_copilot_plan_fields() -> Dict[str, Any]:
    """Non-secret Copilot plan summary for Settings UI (no tokens)."""
    if not _key_set("oauth:github-copilot"):
        return {
            "github_copilot_plan": None,
            "github_copilot_sku": None,
            "github_copilot_is_free_plan": None,
            "github_copilot_login": None,
        }
    try:
        from .providers.github_copilot import get_cached_copilot_account

        account = get_cached_copilot_account() or {}
    except Exception:
        account = {}
    return {
        "github_copilot_plan": account.get("copilot_plan"),
        "github_copilot_sku": account.get("access_type_sku"),
        "github_copilot_is_free_plan": account.get("is_free_plan"),
        "github_copilot_login": account.get("login"),
    }


def build_settings_response(settings=None) -> Dict[str, Any]:
    ensure_credentials_upgraded()
    if settings is None:
        settings = get_settings()
    avail = get_availability()
    return {
        "search_provider": settings.search_provider,
        "search_keyword_extraction": settings.search_keyword_extraction,
        "search_result_count": settings.search_result_count,
        "search_hybrid_mode": settings.search_hybrid_mode,
        "ollama_base_url": settings.ollama_base_url,
        "full_content_results": settings.full_content_results,
        "custom_endpoint_name": settings.custom_endpoint_name,
        "custom_endpoint_url": settings.custom_endpoint_url,
        "serper_api_key_set": _key_set("api:serper"),
        "tavily_api_key_set": _key_set("api:tavily"),
        "brave_api_key_set": _key_set("api:brave"),
        "tinyfish_api_key_set": _key_set("api:tinyfish"),
        "openrouter_api_key_set": _key_set("api:openrouter"),
        "openai_api_key_set": _key_set("api:openai"),
        "anthropic_api_key_set": _key_set("api:anthropic"),
        "google_api_key_set": _key_set("api:google"),
        "mistral_api_key_set": _key_set("api:mistral"),
        "deepseek_api_key_set": _key_set("api:deepseek"),
        "groq_api_key_set": _key_set("api:groq"),
        "nvidia_api_key_set": _key_set("api:nvidia"),
        "opencode_api_key_set": _key_set("api:opencode"),
        "custom_endpoint_api_key_set": _key_set("api:custom_endpoint"),
        "xai_oauth_connected": _key_set("oauth:xai-oauth"),
        "openai_oauth_connected": _key_set("oauth:openai-oauth"),
        "github_copilot_connected": _key_set("oauth:github-copilot"),
        **_github_copilot_plan_fields(),
        "credential_storage": avail.get("effective") if avail.get("in_container") else settings.credential_storage,
        "credential_storage_preferred": settings.credential_storage,
        "credential_storage_available": {
            "file": True,
            "keyring": bool(avail.get("keyring")),
        },
        "credential_storage_unavailable_reason": avail.get("unavailable_reason"),
        "credential_storage_effective": avail.get("effective"),
        "relay_ai_import_dismissed": bool(settings.relay_ai_import_dismissed),
        "enabled_providers": settings.enabled_providers,
        "direct_provider_toggles": settings.direct_provider_toggles,
        "council_models": settings.council_models,
        "chairman_model": settings.chairman_model,
        "council_member_filters": settings.council_member_filters,
        "chairman_filter": settings.chairman_filter,
        "search_query_filter": settings.search_query_filter,
        "council_temperature": settings.council_temperature,
        "chairman_temperature": settings.chairman_temperature,
        "stage2_temperature": settings.stage2_temperature,
        "stage1_prompt": settings.stage1_prompt,
        "stage2_prompt": settings.stage2_prompt,
        "stage3_prompt": settings.stage3_prompt,
        "stage4_prompt": settings.stage4_prompt,
        "title_prompt": settings.title_prompt,
        "query_prompt": settings.query_prompt,
        "advisor_default_model": settings.advisor_default_model,
        "advisor_tiebreaker_model": settings.advisor_tiebreaker_model,
        "advisor_temperature": settings.advisor_temperature,
        "advisor_default_rounds": settings.advisor_default_rounds,
        "advisor_round1_prompt": settings.advisor_round1_prompt,
        "advisor_followup_prompt": settings.advisor_followup_prompt,
        "advisor_cross_pollination_prompt": settings.advisor_cross_pollination_prompt,
        "advisor_verdict_prompt": settings.advisor_verdict_prompt,
        "advisor_tiebreaker_prompt": settings.advisor_tiebreaker_prompt,
        "advisor_presets": [
            p.model_dump() if hasattr(p, "model_dump") else p for p in settings.advisor_presets
        ],
        "council_presets": [
            p.model_dump() if hasattr(p, "model_dump") else p for p in settings.council_presets
        ],
        "date_format": settings.date_format,
        "response_language": settings.response_language,
        "valid_response_languages": list(VALID_RESPONSE_LANGUAGES),
        "response_language_default": RESPONSE_LANGUAGE_DEFAULT,
        "critique_mode": settings.critique_mode,
        "debate_rounds": settings.debate_rounds,
        "auto_converge": settings.auto_converge,
        "convergence_threshold": settings.convergence_threshold,
        "show_free_only": settings.show_free_only,
        "execution_mode": settings.execution_mode,
    }


def build_admin_export() -> Dict[str, Any]:
    """Full settings + secrets for admin export."""
    ensure_credentials_upgraded()
    from .credentials import export_all_secrets

    settings = get_settings()
    data = settings.model_dump()
    # Clear inline secret fields; attach under credentials.
    for field in SETTINGS_FIELD_TO_SECRET_ID:
        data[field] = None
    data["credentials"] = export_all_secrets()
    return data


def apply_admin_import(payload: Dict[str, Any]) -> None:
    from .credentials import import_secrets, wipe_all_secrets
    from .credentials.ids import SETTINGS_FIELD_TO_SECRET_ID
    from .settings import Settings, _normalize_prompt_defaults, save_settings

    data = dict(payload)
    secrets = data.pop("credentials", None) or {}
    # Legacy: secrets still inline in settings fields.
    for field, secret_id in SETTINGS_FIELD_TO_SECRET_ID.items():
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            secrets[secret_id] = value.strip()
        data[field] = None

    normalized = Settings(**_normalize_prompt_defaults(data))
    save_settings(normalized)
    if secrets:
        import_secrets(secrets, replace_existing=True)
