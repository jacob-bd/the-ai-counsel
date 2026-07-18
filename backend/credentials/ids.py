"""Fixed secret ID registry (keyring has no list API)."""

from typing import Dict, List, Optional

# All known credential store keys.
KNOWN_SECRET_IDS: List[str] = [
    "api:openrouter",
    "api:openai",
    "api:anthropic",
    "api:google",
    "api:mistral",
    "api:deepseek",
    "api:groq",
    "api:nvidia",
    "api:opencode",
    "api:custom_endpoint",
    "api:tavily",
    "api:brave",
    "api:serper",
    "api:tinyfish",
    "oauth:xai-oauth",
    "oauth:openai-oauth",
    "oauth:github-copilot",
]

# Settings model field → secret id (for upgrade / PUT routing).
SETTINGS_FIELD_TO_SECRET_ID: Dict[str, str] = {
    "openrouter_api_key": "api:openrouter",
    "openai_api_key": "api:openai",
    "anthropic_api_key": "api:anthropic",
    "google_api_key": "api:google",
    "mistral_api_key": "api:mistral",
    "deepseek_api_key": "api:deepseek",
    "groq_api_key": "api:groq",
    "nvidia_api_key": "api:nvidia",
    "opencode_api_key": "api:opencode",
    "custom_endpoint_api_key": "api:custom_endpoint",
    "tavily_api_key": "api:tavily",
    "brave_api_key": "api:brave",
    "serper_api_key": "api:serper",
    "tinyfish_api_key": "api:tinyfish",
}

SECRET_ID_TO_SETTINGS_FIELD: Dict[str, str] = {v: k for k, v in SETTINGS_FIELD_TO_SECRET_ID.items()}

# Env var overrides (highest precedence).
ENV_OVERRIDES: Dict[str, str] = {
    "api:openrouter": "OPENROUTER_API_KEY",
    "api:openai": "OPENAI_API_KEY",
    "api:anthropic": "ANTHROPIC_API_KEY",
    "api:google": "GOOGLE_API_KEY",
    "api:mistral": "MISTRAL_API_KEY",
    "api:deepseek": "DEEPSEEK_API_KEY",
    "api:groq": "GROQ_API_KEY",
    "api:nvidia": "NVIDIA_API_KEY",
    "api:opencode": "OPENCODE_API_KEY",
    "api:tavily": "TAVILY_API_KEY",
    "api:brave": "BRAVE_API_KEY",
    "api:serper": "SERPER_API_KEY",
    "api:tinyfish": "TINYFISH_API_KEY",
}

OAUTH_PROVIDER_IDS = ("xai-oauth", "openai-oauth", "github-copilot")

OAUTH_SECRET_IDS = {
    "xai-oauth": "oauth:xai-oauth",
    "openai-oauth": "oauth:openai-oauth",
    "github-copilot": "oauth:github-copilot",
}

# GET /api/settings connected flag names
OAUTH_CONNECTED_FLAGS = {
    "xai-oauth": "xai_oauth_connected",
    "openai-oauth": "openai_oauth_connected",
    "github-copilot": "github_copilot_connected",
}


def api_secret_id(provider: str) -> str:
    return f"api:{provider}"


def oauth_secret_id(provider_id: str) -> Optional[str]:
    return OAUTH_SECRET_IDS.get(provider_id)
