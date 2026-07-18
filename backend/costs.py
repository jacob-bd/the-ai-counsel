"""Token usage and cost reporting helpers."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

from .config import DATA_DIR


PRICING_SOURCE_URL = os.getenv(
    "LLM_COUNCIL_PRICING_SOURCE_URL",
    "https://ai-model-pricing.com/api/v1/pricing.json",
)
LITELLM_PRICING_FALLBACK_URL = os.getenv(
    "LLM_COUNCIL_LITELLM_PRICING_URL",
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json",
)
PRICING_CACHE_TTL_SECONDS = int(os.getenv("LLM_COUNCIL_PRICING_CACHE_TTL_SECONDS", "86400"))
PRICING_FAILURE_TTL_SECONDS = 300
PRICING_CACHE_PATH = Path(DATA_DIR) / "model_pricing_cache.json"

_catalog_lock = asyncio.Lock()
_catalog_cache: Optional[Dict[str, Any]] = None
_catalog_failure_until = 0.0
_SUPPORTED_PROVIDER_PREFIXES = {
    "openrouter",
    "ollama",
    "openai",
    "openai-oauth",
    "anthropic",
    "google",
    "mistral",
    "deepseek",
    "groq",
    "custom",
    "nvidia",
    "opencode-zen",
    "opencode-go",
    "xai-oauth",
    "github-copilot",
}
_SUBSCRIPTION_OAUTH_PROVIDERS = {"xai-oauth", "openai-oauth", "github-copilot"}
_OPENCODE_PROVIDERS = {"opencode-zen", "opencode-go"}

# OpenCode Zen / Go published per-1M-token prices. Keys are the native model id
# (the suffix after the provider prefix). OpenCode Go is subscription-based;
# these per-1M prices are published for usage-limit calculations and are shown
# as estimates so users can see relative cost across models.
_OPENCODE_PRICING: Dict[str, Dict[str, Dict[str, Optional[float]]]] = {
    "opencode-zen": {
        "deepseek-v4-flash": {"input": 0.14, "output": 0.28, "cached": 0.03},
        "minimax-m2.7": {"input": 0.30, "output": 1.20, "cached": 0.06},
        "minimax-m2.5": {"input": 0.30, "output": 1.20, "cached": 0.06},
        "glm-5.1": {"input": 1.40, "output": 4.40, "cached": 0.26},
        "glm-5": {"input": 1.00, "output": 3.20, "cached": 0.20},
        "kimi-k2.5": {"input": 0.60, "output": 3.00, "cached": 0.10},
        "kimi-k2.6": {"input": 0.95, "output": 4.00, "cached": 0.16},
        "qwen3.7-max": {"input": 2.50, "output": 7.50, "cached": 0.50},
        "qwen3.7-plus": {"input": 0.40, "output": 1.60, "cached": 0.04},
        "qwen3.6-plus": {"input": 0.50, "output": 3.00, "cached": 0.05},
        "qwen3.5-plus": {"input": 0.20, "output": 1.20, "cached": 0.02},
        "grok-build-0.1": {"input": 1.00, "output": 2.00, "cached": 0.20},
    },
    "opencode-go": {
        "glm-5.1": {"input": 1.40, "output": 4.40, "cached": 0.26},
        "glm-5": {"input": 1.00, "output": 3.20, "cached": 0.20},
        "kimi-k2.5": {"input": 0.60, "output": 3.00, "cached": 0.10},
        "kimi-k2.6": {"input": 0.95, "output": 4.00, "cached": 0.16},
        "mimo-v2.5": {"input": 0.14, "output": 0.28, "cached": 0.0028},
        "mimo-v2.5-pro": {"input": 1.74, "output": 3.48, "cached": 0.0145},
        "deepseek-v4-pro": {"input": 1.74, "output": 3.48, "cached": 0.0145},
        "deepseek-v4-flash": {"input": 0.14, "output": 0.28, "cached": 0.0028},
        "minimax-m3": {"input": 0.60, "output": 2.40, "cached": 0.12},
        "minimax-m2.7": {"input": 0.30, "output": 1.20, "cached": 0.06},
        "minimax-m2.5": {"input": 0.30, "output": 1.20, "cached": 0.06},
        "qwen3.7-max": {"input": 2.50, "output": 7.50, "cached": 0.50},
        "qwen3.7-plus": {"input": 0.40, "output": 1.60, "cached": 0.04},
        "qwen3.6-plus": {"input": 0.50, "output": 3.00, "cached": 0.05},
    },
}

# OpenCode free models. Zen publishes four currently-free models; Go is a
# subscription so all Go entries are paid. Keep in sync with the upstream
# /v1/models is_free flag — this list is the v1 fallback when the catalog
# hasn't been fetched yet.
_OPENCODE_FREE_MODELS: Dict[str, set] = {
    "opencode-zen": {
        "big-pickle",
        "deepseek-v4-flash-free",
        "mimo-v2.5-free",
        "nemotron-3-super-free",
        "minimax-m3-free",
        "qwen3.6-plus-free",
    },
    "opencode-go": set(),
}


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_money(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), 8)


def _first_int(*values: Any) -> Optional[int]:
    for value in values:
        parsed = _to_int(value)
        if parsed is not None:
            return parsed
    return None


def provider_for_model(model_id: str) -> str:
    """Return the provider prefix used by this app."""
    if ":" in model_id:
        provider = model_id.split(":", 1)[0].lower()
        if provider in _SUPPORTED_PROVIDER_PREFIXES:
            return provider
    return "openrouter"


def provider_model_id(model_id: str) -> str:
    """Strip the app provider prefix while preserving provider-native slashes."""
    provider = provider_for_model(model_id)
    if provider != "openrouter" and ":" in model_id:
        return model_id.split(":", 1)[1]
    if model_id.startswith("openrouter:"):
        return model_id.split(":", 1)[1]
    return model_id


def normalize_usage(raw_usage: Any, provider: str = "") -> Dict[str, Any]:
    """Normalize common token usage formats into one shape."""
    if not isinstance(raw_usage, dict):
        return {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "cached_input_tokens": 0,
            "cache_write_tokens": 0,
            "reasoning_tokens": 0,
        }

    prompt_details = raw_usage.get("prompt_tokens_details") or {}
    completion_details = raw_usage.get("completion_tokens_details") or {}

    input_tokens = _first_int(
        raw_usage.get("prompt_tokens"),
        raw_usage.get("input_tokens"),
        raw_usage.get("promptTokenCount"),
        raw_usage.get("prompt_eval_count"),
    )
    output_tokens = _first_int(
        raw_usage.get("completion_tokens"),
        raw_usage.get("output_tokens"),
        raw_usage.get("candidatesTokenCount"),
        raw_usage.get("eval_count"),
    )
    total_tokens = _first_int(
        raw_usage.get("total_tokens"),
        raw_usage.get("totalTokenCount"),
    )
    cached_input_tokens = _first_int(
        prompt_details.get("cached_tokens"),
        raw_usage.get("cached_tokens"),
        raw_usage.get("cache_read_input_tokens"),
        raw_usage.get("cachedContentTokenCount"),
    )
    cache_write_tokens = _first_int(
        prompt_details.get("cache_write_tokens"),
        raw_usage.get("cache_creation_input_tokens"),
    )
    reasoning_tokens = _first_int(
        completion_details.get("reasoning_tokens"),
        raw_usage.get("thoughtsTokenCount"),
        raw_usage.get("reasoning_tokens"),
    )

    if total_tokens is None:
        known_parts = [v for v in (input_tokens, output_tokens) if isinstance(v, int)]
        total_tokens = sum(known_parts) if known_parts else None

    reported_cost = _to_float(raw_usage.get("cost"))
    if reported_cost is None:
        reported_cost = _to_float(raw_usage.get("total_cost"))
    if reported_cost is None:
        reported_cost = _to_float(raw_usage.get("reported_cost"))

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cached_input_tokens": cached_input_tokens or 0,
        "cache_write_tokens": cache_write_tokens or 0,
        "reasoning_tokens": reasoning_tokens or 0,
        "reported_cost": reported_cost,
        "raw_provider": provider,
    }


def _is_zero_cost_model(model_id: str, provider: str) -> Tuple[bool, Optional[str]]:
    normalized = model_id.lower()
    native_id = provider_model_id(model_id).lower()

    if provider == "ollama":
        return True, "free:ollama"
    if provider == "nvidia":
        return True, "free:nvidia"
    if provider in _SUBSCRIPTION_OAUTH_PROVIDERS:
        return True, "free:subscription"
    if provider == "openrouter" and native_id.endswith(":free"):
        return True, "free:openrouter"

    if provider in _OPENCODE_PROVIDERS:
        if native_id in _OPENCODE_FREE_MODELS.get(provider, set()):
            return True, "free:opencode"
        if native_id.endswith("-free"):
            return True, "free:opencode"

    if provider == "custom":
        try:
            from .settings import get_settings

            settings = get_settings()
            endpoint_url = (settings.custom_endpoint_url or "").lower()
        except Exception:
            endpoint_url = ""
        if "opencode.ai" in endpoint_url:
            return True, "free:opencode"

    return False, None


async def _fetch_json(url: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("pricing source did not return a JSON object")
        return data


def _read_disk_catalog() -> Optional[Dict[str, Any]]:
    if not PRICING_CACHE_PATH.exists():
        return None
    try:
        with PRICING_CACHE_PATH.open("r") as f:
            wrapped = json.load(f)
        if not isinstance(wrapped, dict) or "data" not in wrapped:
            return None
        fetched_at = _to_float(wrapped.get("fetched_at")) or 0
        if time.time() - fetched_at > PRICING_CACHE_TTL_SECONDS:
            return None
        return wrapped
    except (OSError, json.JSONDecodeError):
        return None


def _write_disk_catalog(source_url: str, data: Dict[str, Any]) -> None:
    try:
        Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
        with PRICING_CACHE_PATH.open("w") as f:
            json.dump(
                {
                    "fetched_at": time.time(),
                    "source_url": source_url,
                    "data": data,
                },
                f,
            )
    except OSError:
        pass


async def _get_pricing_catalog() -> Optional[Dict[str, Any]]:
    global _catalog_cache, _catalog_failure_until
    if _catalog_cache is not None:
        return _catalog_cache
    if time.time() < _catalog_failure_until:
        return None

    async with _catalog_lock:
        if _catalog_cache is not None:
            return _catalog_cache
        if time.time() < _catalog_failure_until:
            return None

        cached = _read_disk_catalog()
        if cached is not None:
            _catalog_cache = cached
            return _catalog_cache

        for url in (PRICING_SOURCE_URL, LITELLM_PRICING_FALLBACK_URL):
            try:
                data = await _fetch_json(url)
                wrapped = {"fetched_at": time.time(), "source_url": url, "data": data}
                _write_disk_catalog(url, data)
                _catalog_cache = wrapped
                _catalog_failure_until = 0.0
                return _catalog_cache
            except Exception:
                continue

        _catalog_failure_until = time.time() + PRICING_FAILURE_TTL_SECONDS

    return None


def _normalize_match_id(value: Any) -> str:
    return str(value or "").strip().lower().replace(":", "/")


def _catalog_platform(provider: str, native_id: str) -> Optional[str]:
    if provider == "openrouter":
        return "openrouter"
    if provider in {"openai", "anthropic", "google", "mistral", "deepseek", "groq", "nvidia"}:
        return provider
    if provider == "custom":
        # A custom endpoint can expose upstream model IDs. Use those only as a
        # low-confidence estimate unless the endpoint itself is known-free.
        return None
    return provider or None


def _matches_ai_pricing_model(model: Dict[str, Any], native_id: str, platform: Optional[str]) -> bool:
    native_norm = _normalize_match_id(native_id)
    aliases = model.get("aliases") if isinstance(model.get("aliases"), dict) else {}

    if platform:
        alias = aliases.get(platform)
        if _normalize_match_id(alias) == native_norm:
            return True
    else:
        for alias in aliases.values():
            if _normalize_match_id(alias) == native_norm:
                return True

    return _normalize_match_id(model.get("model_id")) == native_norm


def _choose_ai_pricing_entry(
    entries: List[Dict[str, Any]],
    platform: Optional[str],
    input_tokens: Optional[int],
) -> Optional[Dict[str, Any]]:
    candidates = [
        e for e in entries
        if isinstance(e, dict)
        and e.get("modality", "text") == "text"
        and (platform is None or e.get("platform") == platform)
    ]
    if not candidates:
        candidates = [
            e for e in entries
            if isinstance(e, dict) and e.get("modality", "text") == "text"
        ]
    if not candidates:
        return None

    def score(entry: Dict[str, Any]) -> Tuple[int, int, float]:
        tier = str(entry.get("tier") or "")
        notes = str(entry.get("notes") or "").lower()
        threshold = _to_int(entry.get("context_threshold"))
        long_context_match = 0
        if threshold and input_tokens is not None:
            if input_tokens > threshold and "long context" in notes:
                long_context_match = 3
            elif input_tokens <= threshold and "long context" not in notes:
                long_context_match = 2
        tier_score = {"standard": 4, "default": 3, "flex": 2, "batch": 1}.get(tier, 0)
        price = _to_float(entry.get("input_per_1m_tokens")) or 0.0
        return (long_context_match, tier_score, -price)

    return max(candidates, key=score)


_PROVIDER_PRICING_URLS: Dict[str, str] = {
    "openai": "https://platform.openai.com/docs/pricing",
    "anthropic": "https://platform.claude.com/docs/en/about-claude/pricing",
    "google": "https://ai.google.dev/pricing",
    "groq": "https://groq.com/pricing/",
    "mistral": "https://docs.mistral.ai/getting-started/models/pricing/",
    "deepseek": "https://platform.deepseek.com/docs/pricing",
    "nvidia": "https://build.nvidia.com/pricing",
    "openrouter": "https://openrouter.ai/models",
}


def _resolve_ai_model_pricing(
    data: Dict[str, Any],
    provider: str,
    native_id: str,
    input_tokens: Optional[int],
) -> Optional[Dict[str, Any]]:
    models = data.get("models")
    if not isinstance(models, list):
        return None

    platform = _catalog_platform(provider, native_id)
    for model in models:
        if not isinstance(model, dict):
            continue
        if not _matches_ai_pricing_model(model, native_id, platform):
            continue
        entry = _choose_ai_pricing_entry(model.get("pricing", []), platform, input_tokens)
        if not entry:
            continue
        return {
            "input_cost_per_1m": _to_float(entry.get("input_per_1m_tokens")),
            "output_cost_per_1m": _to_float(entry.get("output_per_1m_tokens")),
            "cached_input_cost_per_1m": _to_float(entry.get("cached_input_per_1m_tokens")),
            "source": "catalog:ai-model-pricing",
            "source_url": _PROVIDER_PRICING_URLS.get(provider) or entry.get("source_url") or "https://ai-model-pricing.com/api/v1/pricing.json",
            "source_quality": entry.get("source_quality") or "catalog",
            "matched_model": model.get("model_id"),
            "matched_platform": entry.get("platform"),
            "confidence": "medium" if provider == "custom" else "high",
        }
    return None


def _calculate_token_costs(
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    cached_input_tokens: int,
    reasoning_tokens: int,
    input_price: float,
    output_price: float,
    cached_price: Optional[float],
) -> Tuple[float, float, float, float]:
    billable_input = max((input_tokens or 0) - cached_input_tokens, 0)
    input_cost = (billable_input * input_price) / 1_000_000
    cached_cost = 0.0
    if cached_input_tokens and cached_price is not None:
        cached_cost = (cached_input_tokens * cached_price) / 1_000_000
    billable_output = (output_tokens or 0) + reasoning_tokens
    output_cost = (billable_output * output_price) / 1_000_000
    total_cost = input_cost + cached_cost + output_cost
    return input_cost, cached_cost, output_cost, total_cost


def _litellm_candidate_keys(provider: str, native_id: str) -> List[str]:
    native = native_id.strip()
    keys = [native]
    if provider == "openrouter":
        keys.extend([f"openrouter/{native}", native.removeprefix("openrouter/")])
    elif provider == "anthropic":
        keys.extend([native.removeprefix("anthropic/"), f"anthropic/{native}"])
    elif provider == "google":
        keys.extend([native, f"gemini/{native}", f"google/{native}"])
    elif provider in {"openai", "mistral", "deepseek", "groq", "nvidia"}:
        keys.extend([native.removeprefix(f"{provider}/"), f"{provider}/{native}"])
    return list(dict.fromkeys(keys))


def _resolve_litellm_pricing(
    data: Dict[str, Any],
    provider: str,
    native_id: str,
) -> Optional[Dict[str, Any]]:
    for key in _litellm_candidate_keys(provider, native_id):
        item = data.get(key)
        if not isinstance(item, dict):
            continue
        return {
            "input_cost_per_1m": (_to_float(item.get("input_cost_per_token")) or 0.0) * 1_000_000,
            "output_cost_per_1m": (_to_float(item.get("output_cost_per_token")) or 0.0) * 1_000_000,
            "cached_input_cost_per_1m": (_to_float(item.get("cache_read_input_token_cost")) or 0.0) * 1_000_000,
            "source": "catalog:litellm",
            "source_url": LITELLM_PRICING_FALLBACK_URL,
            "source_quality": "catalog",
            "matched_model": key,
            "matched_platform": item.get("litellm_provider"),
            "confidence": "medium" if provider == "custom" else "high",
        }
    return None


async def _resolve_catalog_pricing(
    provider: str,
    native_id: str,
    input_tokens: Optional[int],
) -> Optional[Dict[str, Any]]:
    wrapped = await _get_pricing_catalog()
    if not wrapped:
        return None
    data = wrapped.get("data") if isinstance(wrapped, dict) else None
    if not isinstance(data, dict):
        return None

    if isinstance(data.get("models"), list):
        resolved = _resolve_ai_model_pricing(data, provider, native_id, input_tokens)
        if resolved:
            return resolved

    return _resolve_litellm_pricing(data, provider, native_id)


def _build_opencode_call_cost(
    base: Dict[str, Any],
    provider: str,
    native_id: str,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    cached_input_tokens: int,
) -> Dict[str, Any]:
    """Compute a cost record for an OpenCode Zen / Go call from the hardcoded table.

    The table holds published per-1M prices from opencode.ai/docs. Go entries
    are subscription-based; we still show the published per-1M price as an
    estimate so users get a relative sense of cost across models.
    """
    key = (native_id or "").lower()
    table = _OPENCODE_PRICING.get(provider, {})
    entry = table.get(key)
    if not entry:
        return {
            **base,
            "notes": [
                f"OpenCode model '{native_id}' is not in the hardcoded pricing table.",
                "Add it via Settings → Custom Model Prices or use the upstream /v1/models is_free flag.",
            ],
        }

    input_price = entry.get("input")
    output_price = entry.get("output")
    cached_price = entry.get("cached")
    if input_price is None or output_price is None:
        return {
            **base,
            "notes": ["OpenCode pricing entry was incomplete for this model."],
        }

    reasoning_tokens = base.get("reasoning_tokens") or 0
    input_cost, cached_cost, output_cost, total_cost = _calculate_token_costs(
        input_tokens,
        output_tokens,
        cached_input_tokens,
        reasoning_tokens,
        input_price,
        output_price,
        cached_price,
    )

    note = "OpenCode Go is subscription-based; the per-1M price is shown for reference." if provider == "opencode-go" else None
    return {
        **base,
        "input_cost": _round_money(input_cost + cached_cost),
        "output_cost": _round_money(output_cost),
        "total_cost": _round_money(total_cost),
        "input_cost_per_1m": input_price,
        "output_cost_per_1m": output_price,
        "cached_input_cost_per_1m": cached_price,
        "pricing_source": "table:opencode",
        "pricing_source_url": "https://opencode.ai/docs/zen/" if provider == "opencode-zen" else "https://opencode.ai/docs/go/",
        "pricing_confidence": "high",
        "cost_status": "estimated",
        "is_estimate": True,
        "notes": [note] if note else [],
    }


async def estimate_call_cost(model_id: str, usage: Dict[str, Any]) -> Dict[str, Any]:
    """Build a per-call usage/cost record for a model response."""
    provider = provider_for_model(model_id)
    native_id = provider_model_id(model_id)
    normalized_usage = normalize_usage(usage, provider)
    input_tokens = normalized_usage.get("input_tokens")
    output_tokens = normalized_usage.get("output_tokens")
    total_tokens = normalized_usage.get("total_tokens")
    cached_input_tokens = normalized_usage.get("cached_input_tokens") or 0

    is_free, free_source = _is_zero_cost_model(model_id, provider)
    base = {
        "model": model_id,
        "provider": provider,
        "currency": "USD",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cached_input_tokens": cached_input_tokens,
        "cache_write_tokens": normalized_usage.get("cache_write_tokens") or 0,
        "reasoning_tokens": normalized_usage.get("reasoning_tokens") or 0,
        "input_cost": None,
        "output_cost": None,
        "total_cost": None,
        "reported_total_cost": None,
        "input_cost_per_1m": None,
        "output_cost_per_1m": None,
        "cached_input_cost_per_1m": None,
        "pricing_source": None,
        "pricing_source_url": None,
        "pricing_confidence": "unknown",
        "cost_status": "unknown",
        "is_estimate": True,
        "notes": [],
    }

    if is_free:
        notes = []
        if free_source == "free:subscription":
            notes = [
                "Subscription OAuth — usage is covered by your provider subscription, not metered API billing."
            ]
        return {
            **base,
            "input_cost": 0.0,
            "output_cost": 0.0,
            "total_cost": 0.0,
            "pricing_source": free_source,
            "pricing_confidence": "high",
            "cost_status": "free",
            "is_estimate": False,
            "notes": notes,
        }

    reported_cost = normalized_usage.get("reported_cost")
    if provider == "openrouter" and reported_cost is not None:
        return {
            **base,
            "total_cost": _round_money(reported_cost),
            "reported_total_cost": _round_money(reported_cost),
            "pricing_source": "provider:openrouter_usage",
            "pricing_confidence": "high",
            "cost_status": "known",
            "is_estimate": False,
        }

    if provider in _OPENCODE_PROVIDERS:
        return _build_opencode_call_cost(base, provider, native_id, input_tokens, output_tokens, cached_input_tokens)

    if input_tokens is None and output_tokens is None and total_tokens is None:
        return {
            **base,
            "notes": ["Provider did not return token usage for this call."],
        }

    pricing = await _resolve_catalog_pricing(provider, native_id, input_tokens)
    if not pricing:
        return {
            **base,
            "notes": ["Usage captured, but pricing was not available for this model."],
        }

    input_price = pricing.get("input_cost_per_1m")
    output_price = pricing.get("output_cost_per_1m")
    cached_price = pricing.get("cached_input_cost_per_1m")

    if input_price is None or output_price is None:
        return {
            **base,
            "pricing_source": pricing.get("source"),
            "pricing_source_url": pricing.get("source_url"),
            "pricing_confidence": pricing.get("confidence", "unknown"),
            "notes": ["Pricing entry was incomplete for this model."],
        }

    reasoning_tokens = normalized_usage.get("reasoning_tokens") or 0
    input_cost, cached_cost, output_cost, total_cost = _calculate_token_costs(
        input_tokens,
        output_tokens,
        cached_input_tokens,
        reasoning_tokens,
        input_price,
        output_price,
        cached_price,
    )

    is_zero = input_price == 0 and output_price == 0 and (cached_price in (None, 0))
    return {
        **base,
        "input_cost": _round_money(input_cost + cached_cost),
        "output_cost": _round_money(output_cost),
        "total_cost": _round_money(total_cost),
        "input_cost_per_1m": input_price,
        "output_cost_per_1m": output_price,
        "cached_input_cost_per_1m": cached_price,
        "pricing_source": pricing.get("source"),
        "pricing_source_url": pricing.get("source_url"),
        "pricing_confidence": pricing.get("confidence", "unknown"),
        "cost_status": "free" if is_zero else "estimated",
        "is_estimate": not is_zero,
        "notes": [] if provider != "custom" else ["Custom endpoint cost is an upstream model estimate unless the endpoint is known-free."],
    }


async def attach_cost(model_id: str, response: Dict[str, Any]) -> Dict[str, Any]:
    """Attach normalized usage and cost data to a provider response."""
    if not isinstance(response, dict):
        return response
    provider = provider_for_model(model_id)
    raw_usage = response.get("usage")
    response["usage"] = normalize_usage({} if raw_usage is None else raw_usage, provider)
    response["cost"] = await estimate_call_cost(model_id, response["usage"])
    return response


def _iter_costed_calls(
    items: Optional[Iterable[Dict[str, Any]]],
    stage: str,
    round_number: Optional[int] = None,
    role_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        cost = item.get("cost")
        if not isinstance(cost, dict):
            continue
        call = dict(cost)
        call["stage"] = stage
        if round_number is not None:
            call["round"] = round_number
        if role_key and item.get(role_key):
            call["role"] = item.get(role_key)
        if item.get("persona_name"):
            call["persona_name"] = item.get("persona_name")
        calls.append(call)
    return calls


def _summarize_calls(calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_cost = 0.0
    known_cost_calls = 0
    unknown_cost_calls = 0
    estimated_calls = 0
    free_calls = 0
    total_input = 0
    total_output = 0
    total_tokens = 0
    by_model: Dict[str, Dict[str, Any]] = {}
    by_stage: Dict[str, Dict[str, Any]] = {}

    def ensure_bucket(target: Dict[str, Dict[str, Any]], key: str) -> Dict[str, Any]:
        if key not in target:
            target[key] = {
                "name": key,
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
                "known_cost_calls": 0,
                "unknown_cost_calls": 0,
                "estimated_calls": 0,
                "free_calls": 0,
                "pricing_sources": [],
            }
        return target[key]

    for call in calls:
        cost = call.get("total_cost")
        has_cost = isinstance(cost, (int, float))
        if has_cost:
            total_cost += float(cost)
            known_cost_calls += 1
        else:
            unknown_cost_calls += 1

        if call.get("is_estimate"):
            estimated_calls += 1
        if call.get("cost_status") == "free":
            free_calls += 1

        input_tokens = call.get("input_tokens") if isinstance(call.get("input_tokens"), int) else 0
        output_tokens = call.get("output_tokens") if isinstance(call.get("output_tokens"), int) else 0
        tokens = call.get("total_tokens") if isinstance(call.get("total_tokens"), int) else (input_tokens + output_tokens)
        total_input += input_tokens
        total_output += output_tokens
        total_tokens += tokens

        for bucket in (
            ensure_bucket(by_model, str(call.get("model") or "unknown")),
            ensure_bucket(by_stage, str(call.get("stage") or "unknown")),
        ):
            bucket["calls"] += 1
            bucket["input_tokens"] += input_tokens
            bucket["output_tokens"] += output_tokens
            bucket["total_tokens"] += tokens
            if has_cost:
                bucket["total_cost"] += float(cost)
                bucket["known_cost_calls"] += 1
            else:
                bucket["unknown_cost_calls"] += 1
            if call.get("is_estimate"):
                bucket["estimated_calls"] += 1
            if call.get("cost_status") == "free":
                bucket["free_calls"] += 1
            source = call.get("pricing_source")
            if source and source not in bucket["pricing_sources"]:
                bucket["pricing_sources"].append(source)

    def finish_bucket(bucket: Dict[str, Any]) -> Dict[str, Any]:
        bucket["total_cost"] = _round_money(bucket["total_cost"]) or 0.0
        return bucket

    return {
        "currency": "USD",
        "total_cost": _round_money(total_cost) or 0.0,
        "input_tokens": total_input,
        "output_tokens": total_output,
        "total_tokens": total_tokens,
        "total_calls": len(calls),
        "known_cost_calls": known_cost_calls,
        "unknown_cost_calls": unknown_cost_calls,
        "estimated_calls": estimated_calls,
        "free_calls": free_calls,
        "has_unknown_costs": unknown_cost_calls > 0,
        "has_estimates": estimated_calls > 0,
        "by_model": sorted(
            (finish_bucket(v) for v in by_model.values()),
            key=lambda item: item["total_cost"],
            reverse=True,
        ),
        "by_stage": sorted(
            (finish_bucket(v) for v in by_stage.values()),
            key=lambda item: item["name"],
        ),
        "calls": calls,
    }


def summarize_buffered_stages(*stage_results: Any) -> Dict[str, Any]:
    """Build a cost report from arbitrary buffered stage dicts.

    Accepts the shapes produced by ``the_ai_counsel_mcp.stream_buffer``:

    - Stage 1: ``{"results": [{"model", "cost", ...}, ...]}``
    - Stage 2: ``{"rankings": [{"model", "cost", ...}, ...]}``
    - Stage 3: ``{"chairman_model", "cost": {...}}`` (single call, top-level)
    - Iterative debate: ``{"rounds": [{"responses": [{"cost", ...}, ...]}, ...],
      "stage4": {"cost", ...}}``
    - Advisor debate: ``{"rounds": {round_num: {"responses": [{"cost", ...}, ...]}},
      "verdict": {"cost", ...}, "tiebreaker": {"cost", ...}}``

    The same shape is returned as ``_summarize_calls`` (the canonical
    backend cost report). Re-implementations of this logic in the MCP
    layer should call this helper instead of duplicating the bucketing.
    """
    calls: List[Dict[str, Any]] = []

    def _collect_cost_dict(cost: Any) -> None:
        if isinstance(cost, dict):
            calls.append(cost)

    def _walk_item(item: Any) -> None:
        if not isinstance(item, dict):
            return
        if "cost" in item and isinstance(item["cost"], dict):
            _collect_cost_dict(item["cost"])
        for key in ("results", "rankings", "responses"):
            sub = item.get(key)
            if isinstance(sub, list):
                for child in sub:
                    _walk_item(child)
            elif isinstance(sub, dict):
                if all(isinstance(v, dict) and "round" in v for v in sub.values()):
                    for v in sub.values():
                        _walk_item(v)
                else:
                    _walk_item(sub)
        rounds = item.get("rounds")
        if isinstance(rounds, list):
            for r in rounds:
                _walk_item(r)
        elif isinstance(rounds, dict):
            for v in rounds.values():
                _walk_item(v)
        for key in ("verdict", "tiebreaker", "stage4", "synthesis"):
            sub = item.get(key)
            if isinstance(sub, dict):
                _walk_item(sub)

    for stage in stage_results:
        if not isinstance(stage, dict):
            continue
        _walk_item(stage)

    return _summarize_calls(calls)


def build_council_cost_report(
    stage1: Optional[List[Dict[str, Any]]],
    stage2: Optional[List[Dict[str, Any]]] = None,
    stage3: Optional[Dict[str, Any]] = None,
    stage4: Optional[Dict[str, Any]] = None,
    round_number: Optional[int] = None,
) -> Dict[str, Any]:
    calls = []
    calls.extend(_iter_costed_calls(stage1, "stage1", round_number))
    calls.extend(_iter_costed_calls(stage2, "stage2", round_number))
    if isinstance(stage3, dict):
        calls.extend(_iter_costed_calls([stage3], "stage3", round_number))
    if isinstance(stage4, dict):
        calls.extend(_iter_costed_calls([stage4], "stage4", round_number))
    return _summarize_calls(calls)


def build_iterative_debate_cost_report(
    rounds: List[Dict[str, Any]],
    stage4: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    calls: List[Dict[str, Any]] = []
    for round_data in rounds or []:
        round_number = round_data.get("round_number")
        calls.extend(_iter_costed_calls(round_data.get("stage1"), "stage1", round_number))
        calls.extend(_iter_costed_calls(round_data.get("stage2"), "stage2", round_number))
        if isinstance(round_data.get("stage3"), dict):
            calls.extend(_iter_costed_calls([round_data["stage3"]], "stage3", round_number))
    if isinstance(stage4, dict):
        calls.extend(_iter_costed_calls([stage4], "stage4"))
    return _summarize_calls(calls)


def build_advisor_cost_report(
    rounds: List[Dict[str, Any]],
    verdict: Optional[Dict[str, Any]] = None,
    tiebreaker: Optional[Dict[str, Any]] = None,
    round_extracts: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    calls: List[Dict[str, Any]] = []
    for round_data in rounds or []:
        round_number = round_data.get("round_number") or round_data.get("round")
        calls.extend(
            _iter_costed_calls(
                round_data.get("responses"),
                "advisor_round",
                round_number,
                role_key="persona_id",
            )
        )
    calls.extend(_iter_costed_calls(round_extracts, "advisor_extract"))
    if isinstance(tiebreaker, dict):
        calls.extend(_iter_costed_calls([tiebreaker], "advisor_tiebreaker"))
    if isinstance(verdict, dict):
        calls.extend(_iter_costed_calls([verdict], "advisor_verdict"))
    return _summarize_calls(calls)
