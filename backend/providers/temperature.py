"""Provider-specific temperature compatibility helpers."""

from __future__ import annotations

import re
from typing import Any

INTERNAL_PROVIDER_PREFIXES = {
    "anthropic",
    "custom",
    "deepseek",
    "github-copilot",
    "google",
    "groq",
    "mistral",
    "nvidia",
    "ollama",
    "openai",
    "openai-oauth",
    "opencode-go",
    "opencode-zen",
    "openrouter",
    "xai-oauth",
}

OPENAI_FIXED_TEMPERATURE_PREFIXES = ("gpt-5",)
OPENAI_REASONING_MODEL_RE = re.compile(r"^o(?:1|3|4)(?:[-.]|$)")
ANTHROPIC_NO_TEMPERATURE_RE = re.compile(r"^claude-(?:opus|sonnet|haiku)-[4-9](?:[-.]|$)")


def split_upstream_model(model_id: str) -> tuple[str, str]:
    """Return the upstream provider slug and model name when present."""

    normalized = (model_id or "").strip().lower()
    if ":" in normalized:
        prefix, rest = normalized.split(":", 1)
        if prefix in INTERNAL_PROVIDER_PREFIXES:
            normalized = rest

    if "/" in normalized:
        provider, model = normalized.split("/", 1)
        return provider, model

    return "", normalized


def is_openai_fixed_temperature_model(model_id: str) -> bool:
    provider, model = split_upstream_model(model_id)
    if provider and provider != "openai":
        return False
    return model.startswith(OPENAI_FIXED_TEMPERATURE_PREFIXES) or bool(
        OPENAI_REASONING_MODEL_RE.match(model)
    )


def is_anthropic_temperature_deprecated_model(model_id: str) -> bool:
    provider, model = split_upstream_model(model_id)
    if provider and provider != "anthropic":
        return False
    return bool(ANTHROPIC_NO_TEMPERATURE_RE.match(model))


def should_omit_temperature(model_id: str, provider: str) -> bool:
    """Whether a request should leave temperature out and use provider default."""

    if provider == "openai":
        return is_openai_fixed_temperature_model(model_id)
    if provider == "anthropic":
        return is_anthropic_temperature_deprecated_model(model_id)
    if provider in {"custom", "openrouter"}:
        return (
            is_openai_fixed_temperature_model(model_id)
            or is_anthropic_temperature_deprecated_model(model_id)
        )
    return False


def add_temperature_if_supported(
    payload: dict[str, Any],
    model_id: str,
    provider: str,
    temperature: float,
) -> dict[str, Any]:
    """Mutate and return payload with temperature only when the model accepts it."""

    if not should_omit_temperature(model_id, provider):
        payload["temperature"] = temperature
    return payload
