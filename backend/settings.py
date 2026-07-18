"""Settings storage and management."""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from .search import SearchProvider


class AdvisorPreset(BaseModel):
    """Saved advisor debate configuration (personas + models)."""
    id: str
    name: str
    persona_ids: List[str] = Field(default_factory=list)
    mode: str = "simple"  # "simple" | "advanced"
    default_model: str = ""
    tiebreaker_model: str = ""
    model_assignments: Optional[Dict[str, str]] = None
    max_rounds: int = 3
    search_provider: Optional[str] = None
    is_default: bool = False
    last_used_at: Optional[str] = None


class CouncilPreset(BaseModel):
    """Saved council lineup (members + chairman only)."""
    id: str
    name: str
    council_models: List[str] = Field(default_factory=list)
    chairman_model: str = ""
    is_default: bool = False
    last_used_at: Optional[str] = None

logger = logging.getLogger(__name__)

# Settings file path
SETTINGS_FILE = Path(__file__).parent.parent / "data" / "settings.json"

# Default models (matches original llm-council defaults)
DEFAULT_COUNCIL_MODELS = ["", ""]
DEFAULT_CHAIRMAN_MODEL = ""

# Default enabled providers
DEFAULT_ENABLED_PROVIDERS = {
    "openrouter": True,
    "ollama": False,
    "groq": False,
    "direct": False,  # Master toggle for all direct connections
    "custom": False,  # Custom OpenAI-compatible endpoint
    "xai-oauth": False,
    "openai-oauth": False,
    "github-copilot": False,
}

# Default direct provider toggles (individual)
DEFAULT_DIRECT_PROVIDER_TOGGLES = {
    "openai": False,
    "anthropic": False,
    "google": False,
    "mistral": False,
    "deepseek": False,
    "groq": False,
    "nvidia": False,
    "opencode-zen": False,
    "opencode-go": False,
}


# Available models for selection (popular OpenRouter models)
AVAILABLE_MODELS = [
    # OpenAI
    {"id": "openai/gpt-4o", "name": "GPT-4o [OpenRouter]", "provider": "OpenAI", "source": "openrouter"},
    {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini [OpenRouter]", "provider": "OpenAI", "source": "openrouter"},
    {"id": "openai/o1-preview", "name": "o1 Preview [OpenRouter]", "provider": "OpenAI", "source": "openrouter"},
    {"id": "openai/o1-mini", "name": "o1 Mini [OpenRouter]", "provider": "OpenAI", "source": "openrouter"},
    # Google
    {"id": "google/gemini-pro-1.5", "name": "Gemini 1.5 Pro [OpenRouter]", "provider": "Google", "source": "openrouter", "is_free": True},
    {"id": "google/gemini-flash-1.5", "name": "Gemini 1.5 Flash [OpenRouter]", "provider": "Google", "source": "openrouter", "is_free": True},
    {"id": "google/gemini-pro-vision", "name": "Gemini Pro Vision [OpenRouter]", "provider": "Google", "source": "openrouter"},
    # Anthropic
    {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet [OpenRouter]", "provider": "Anthropic", "source": "openrouter"},
    {"id": "anthropic/claude-3-opus", "name": "Claude 3 Opus [OpenRouter]", "provider": "Anthropic", "source": "openrouter"},
    {"id": "anthropic/claude-3-haiku", "name": "Claude 3 Haiku [OpenRouter]", "provider": "Anthropic", "source": "openrouter"},
    # Meta
    {"id": "meta-llama/llama-3.1-405b-instruct", "name": "Llama 3.1 405B [OpenRouter]", "provider": "Meta", "source": "openrouter"},
    {"id": "meta-llama/llama-3.1-70b-instruct", "name": "Llama 3.1 70B [OpenRouter]", "provider": "Meta", "source": "openrouter", "is_free": True},
    # Mistral
    {"id": "mistralai/mistral-large", "name": "Mistral Large [OpenRouter]", "provider": "Mistral", "source": "openrouter"},
    {"id": "mistralai/mistral-medium", "name": "Mistral Medium [OpenRouter]", "provider": "Mistral", "source": "openrouter"},
    # DeepSeek
    {"id": "deepseek/deepseek-chat", "name": "DeepSeek V3 [OpenRouter]", "provider": "DeepSeek", "source": "openrouter"},
]


from .prompts import (
    STAGE1_PROMPT_DEFAULT,
    STAGE2_PROMPT_DEFAULT,
    STAGE3_PROMPT_DEFAULT,
    TITLE_PROMPT_DEFAULT,
    QUERY_PROMPT_DEFAULT,
    STAGE4_CORRECTED_DRAFT_PROMPT,
    RESPONSE_LANGUAGE_DEFAULT,
    VALID_RESPONSE_LANGUAGES,
)
from .advisor_prompts import (
    ADVISOR_ROUND1_PROMPT,
    ADVISOR_FOLLOWUP_PROMPT,
    ADVISOR_CROSS_POLLINATION_PROMPT,
    ADVISOR_VERDICT_PROMPT,
    ADVISOR_TIEBREAKER_PROMPT,
)

class Settings(BaseModel):
    """Application settings."""
    search_provider: SearchProvider = SearchProvider.DUCKDUCKGO
    search_keyword_extraction: str = "direct"  # "direct", "yake", or "llm"
    search_result_count: int = 8  # Number of search results (5-15, default 8)
    search_hybrid_mode: bool = True  # Combine web+news search for DuckDuckGo

    # API Keys
    tavily_api_key: Optional[str] = None
    brave_api_key: Optional[str] = None
    serper_api_key: Optional[str] = None
    tinyfish_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    nvidia_api_key: Optional[str] = None
    opencode_api_key: Optional[str] = None

    # Ollama Settings
    ollama_base_url: str = "http://localhost:11434"

    # Custom OpenAI-compatible endpoint
    custom_endpoint_name: Optional[str] = None
    custom_endpoint_url: Optional[str] = None
    custom_endpoint_api_key: Optional[str] = None

    # Enabled Providers (which sources are available for council selection)
    enabled_providers: Dict[str, bool] = DEFAULT_ENABLED_PROVIDERS.copy()

    # Individual direct provider toggles
    direct_provider_toggles: Dict[str, bool] = DEFAULT_DIRECT_PROVIDER_TOGGLES.copy()

    # Council Configuration (unified across all providers)
    council_models: List[str] = DEFAULT_COUNCIL_MODELS.copy()
    chairman_model: str = DEFAULT_CHAIRMAN_MODEL
    
    # Temperature Settings
    council_temperature: float = 0.5
    chairman_temperature: float = 0.4
    stage2_temperature: float = 0.3  # Lower for consistent ranking output
    
    # Remote/Local filters
    council_member_filters: Optional[Dict[int, str]] = None
    chairman_filter: Optional[str] = None
    search_query_filter: Optional[str] = None

    full_content_results: int = 3  # Number of search results to fetch full content for (0 to disable)
    show_free_only: bool = False  # Filter to show only free OpenRouter models

    # System Prompts
    stage1_prompt: str = STAGE1_PROMPT_DEFAULT
    stage2_prompt: str = STAGE2_PROMPT_DEFAULT
    stage3_prompt: str = STAGE3_PROMPT_DEFAULT
    stage4_prompt: str = STAGE4_CORRECTED_DRAFT_PROMPT
    title_prompt: str = TITLE_PROMPT_DEFAULT
    query_prompt: str = QUERY_PROMPT_DEFAULT
    
    # Display Preferences
    date_format: str = "auto"  # "auto", "MM/DD/YYYY", "DD/MM/YYYY", "YYYY-MM-DD"
    response_language: str = RESPONSE_LANGUAGE_DEFAULT

    # Execution Mode
    execution_mode: str = "full"  # Default execution mode: 'chat_only', 'chat_ranking', 'full'

    # Iterative Debate
    critique_mode: str = "freeform"        # "freeform", "paragraph", "claim"
    debate_rounds: int = 1                 # Number of rounds (1 = current behavior)
    auto_converge: bool = True             # Stop early if rankings stabilize
    convergence_threshold: int = 2         # Consecutive stable rounds to trigger

    # Advisor Settings
    advisor_default_model: str = ""
    advisor_tiebreaker_model: str = ""
    advisor_temperature: float = 0.7
    advisor_default_rounds: int = 3
    advisor_round1_prompt: str = ADVISOR_ROUND1_PROMPT
    advisor_followup_prompt: str = ADVISOR_FOLLOWUP_PROMPT
    advisor_cross_pollination_prompt: str = ADVISOR_CROSS_POLLINATION_PROMPT
    advisor_verdict_prompt: str = ADVISOR_VERDICT_PROMPT
    advisor_tiebreaker_prompt: str = ADVISOR_TIEBREAKER_PROMPT
    advisor_presets: List[AdvisorPreset] = Field(default_factory=list)
    council_presets: List[CouncilPreset] = Field(default_factory=list)

    # Credential storage preference (secrets live in credentials.json or OS keyring)
    credential_storage: str = "file"  # "file" | "keyring"
    credentials_migrated: bool = False
    relay_ai_import_dismissed: bool = False
    # Secret IDs ignored even if present in env (Disconnect from Settings).
    disabled_secret_ids: List[str] = Field(default_factory=list)


PROMPT_DEFAULTS = {
    "stage1_prompt": STAGE1_PROMPT_DEFAULT,
    "stage2_prompt": STAGE2_PROMPT_DEFAULT,
    "stage3_prompt": STAGE3_PROMPT_DEFAULT,
    "stage4_prompt": STAGE4_CORRECTED_DRAFT_PROMPT,
    "title_prompt": TITLE_PROMPT_DEFAULT,
    "query_prompt": QUERY_PROMPT_DEFAULT,
    "advisor_round1_prompt": ADVISOR_ROUND1_PROMPT,
    "advisor_followup_prompt": ADVISOR_FOLLOWUP_PROMPT,
    "advisor_cross_pollination_prompt": ADVISOR_CROSS_POLLINATION_PROMPT,
    "advisor_verdict_prompt": ADVISOR_VERDICT_PROMPT,
    "advisor_tiebreaker_prompt": ADVISOR_TIEBREAKER_PROMPT,
}


MAX_ADVISOR_PRESETS = 20
MAX_COUNCIL_PRESETS = 20
MAX_COUNCIL_MEMBERS = 8


def _clamp_advisor_rounds(value: Any, default: int = 3) -> int:
    if not isinstance(value, int):
        return default
    return max(3, min(10, value))


def _normalize_advisor_presets(raw_presets: Any) -> List[Dict[str, Any]]:
    """Validate and sanitize persisted advisor presets."""
    if not isinstance(raw_presets, list):
        return []

    normalized: List[Dict[str, Any]] = []
    default_assigned = False

    for item in raw_presets[:MAX_ADVISOR_PRESETS]:
        if not isinstance(item, dict):
            continue
        preset_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not preset_id or not name:
            continue

        persona_ids = [
            str(pid).strip()
            for pid in (item.get("persona_ids") if isinstance(item.get("persona_ids"), list) else [])
            if str(pid).strip()
        ][:4]

        mode = item.get("mode", "simple")
        if mode not in ("simple", "advanced"):
            mode = "simple"

        model_assignments = item.get("model_assignments")
        if model_assignments is not None and not isinstance(model_assignments, dict):
            model_assignments = None
        if isinstance(model_assignments, dict):
            model_assignments = {
                str(k): str(v)
                for k, v in model_assignments.items()
                if str(k).strip() and str(v).strip()
            }

        search_provider = item.get("search_provider")
        if search_provider is not None:
            search_provider = str(search_provider).strip() or None

        is_default = bool(item.get("is_default"))
        if is_default and default_assigned:
            is_default = False
        if is_default:
            default_assigned = True

        last_used_at = item.get("last_used_at")
        if last_used_at is not None:
            last_used_at = str(last_used_at).strip() or None

        try:
            preset = AdvisorPreset(
                id=preset_id,
                name=name[:80],
                persona_ids=persona_ids,
                mode=mode,
                default_model=str(item.get("default_model") or ""),
                tiebreaker_model=str(item.get("tiebreaker_model") or ""),
                model_assignments=model_assignments,
                max_rounds=_clamp_advisor_rounds(item.get("max_rounds")),
                search_provider=search_provider,
                is_default=is_default,
                last_used_at=last_used_at,
            )
            normalized.append(preset.model_dump())
        except Exception:
            continue

    return normalized


def _normalize_council_presets(raw_presets: Any) -> List[Dict[str, Any]]:
    """Validate and sanitize persisted council presets."""
    if not isinstance(raw_presets, list):
        return []

    normalized: List[Dict[str, Any]] = []
    default_assigned = False

    for item in raw_presets[:MAX_COUNCIL_PRESETS]:
        if not isinstance(item, dict):
            continue
        preset_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not preset_id or not name:
            continue

        raw_models = item.get("council_models")
        if not isinstance(raw_models, list):
            raw_models = []
        council_models = [
            str(model_id).strip()
            for model_id in raw_models
            if str(model_id).strip()
        ][:MAX_COUNCIL_MEMBERS]

        is_default = bool(item.get("is_default"))
        if is_default and default_assigned:
            is_default = False
        if is_default:
            default_assigned = True

        last_used_at = item.get("last_used_at")
        if last_used_at is not None:
            last_used_at = str(last_used_at).strip() or None

        try:
            preset = CouncilPreset(
                id=preset_id,
                name=name[:80],
                council_models=council_models,
                chairman_model=str(item.get("chairman_model") or ""),
                is_default=is_default,
                last_used_at=last_used_at,
            )
            normalized.append(preset.model_dump())
        except Exception:
            continue

    return normalized


VALID_DATE_FORMATS = ("auto", "MM/DD/YYYY", "DD/MM/YYYY", "YYYY-MM-DD")


def _normalize_display_preferences(data: dict) -> dict:
    """Coerce invalid display preference values to safe defaults."""
    normalized = dict(data)
    if normalized.get("response_language") not in VALID_RESPONSE_LANGUAGES:
        normalized["response_language"] = RESPONSE_LANGUAGE_DEFAULT
    if normalized.get("date_format") not in VALID_DATE_FORMATS:
        normalized["date_format"] = "auto"
    return normalized


def _normalize_prompt_defaults(data: dict) -> dict:
    """Backfill defaults for older settings files that persisted invalid values."""
    normalized = _normalize_display_preferences(dict(data))
    for key, default in PROMPT_DEFAULTS.items():
        value = normalized.get(key)
        if not isinstance(value, str) or not value.strip():
            normalized[key] = default

    rounds = normalized.get("advisor_default_rounds")
    normalized["advisor_default_rounds"] = _clamp_advisor_rounds(rounds)

    normalized["advisor_presets"] = _normalize_advisor_presets(normalized.get("advisor_presets"))
    normalized["council_presets"] = _normalize_council_presets(normalized.get("council_presets"))
    return normalized


_settings_cache: Settings | None = None
_settings_mtime: float = 0.0


def get_settings() -> Settings:
    """Load settings from file with mtime-based cache. Returns cached instance if file hasn't changed."""
    global _settings_cache, _settings_mtime

    if SETTINGS_FILE.exists():
        try:
            mtime = SETTINGS_FILE.stat().st_mtime
            if _settings_cache is not None and mtime == _settings_mtime:
                return _settings_cache
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                _settings_cache = Settings(**_normalize_prompt_defaults(data))
                _settings_mtime = mtime
                return _settings_cache
        except Exception:
            logger.exception("Failed to load settings from %s", SETTINGS_FILE)

    if _settings_cache is not None and not SETTINGS_FILE.exists():
        _settings_cache = None
        _settings_mtime = 0.0

    return Settings()


def _redact_secret_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """Keep API keys out of settings.json (credential store is source of truth)."""
    from .credentials.ids import SETTINGS_FIELD_TO_SECRET_ID

    redacted = dict(data)
    for field in SETTINGS_FIELD_TO_SECRET_ID:
        redacted[field] = None
    return redacted


def save_settings(settings: Settings) -> None:
    """Save settings to file and update cache.

    Secret fields are always written as null — imports and Retest use the
    credential store (data/credentials.json or OS keystore), not settings.json.
    """
    global _settings_cache, _settings_mtime

    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

    payload = _redact_secret_fields(settings.model_dump())
    with open(SETTINGS_FILE, "w") as f:
        json.dump(payload, f, indent=2)

    # Cache the redacted model so in-memory reads match on-disk settings.json.
    _settings_cache = Settings(**payload)
    _settings_mtime = SETTINGS_FILE.stat().st_mtime


def update_settings(**kwargs) -> Settings:
    """Update specific settings and save."""
    current = get_settings()
    updated_data = current.model_dump()
    updated_data.update(kwargs)
    # Never persist secrets via kwargs (route through credential store instead).
    updated_data = _redact_secret_fields(updated_data)
    updated_data = _normalize_prompt_defaults(updated_data)
    updated = Settings(**updated_data)
    save_settings(updated)
    return updated
