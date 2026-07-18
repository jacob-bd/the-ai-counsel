"""Configuration for the LLM Council."""

import os
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Data directory for conversation storage
DATA_DIR = "data/conversations"


def get_openrouter_api_key() -> str:
    """Get OpenRouter API key from credential store or environment."""
    from .credentials import get_api_key

    return get_api_key("openrouter") or os.getenv("OPENROUTER_API_KEY", "")


def get_ollama_base_url() -> str:
    """Get Ollama base URL from settings."""
    from .settings import get_settings
    return get_settings().ollama_base_url


def get_council_models() -> list:
    """Get council models from settings."""
    from .settings import get_settings, DEFAULT_COUNCIL_MODELS
    settings = get_settings()
    return settings.council_models or DEFAULT_COUNCIL_MODELS


def get_chairman_model() -> str:
    """Get chairman model from settings."""
    from .settings import get_settings, DEFAULT_CHAIRMAN_MODEL
    settings = get_settings()
    return settings.chairman_model or DEFAULT_CHAIRMAN_MODEL


# Legacy constants for backwards compatibility
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
COUNCIL_MODELS = [
    "openai/gpt-4.1",
    "google/gemini-2.5-pro",
    "anthropic/claude-sonnet-4",
    "x-ai/grok-3",
]
CHAIRMAN_MODEL = "google/gemini-2.5-pro"
