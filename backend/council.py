"""3-stage LLM Council orchestration."""

from typing import List, Dict, Any, Optional, Callable
import asyncio
import logging
import random
import re
import time
from .config import get_council_models, get_chairman_model
from .costs import attach_cost
from .settings import get_settings, normalize_model_ids
from .prompts import apply_response_language

logger = logging.getLogger(__name__)

STAGE2_MAX_OUTPUT_TOKENS_DEFAULT = 32768
STAGE2_FORMAT_RETRY_ATTEMPTS = 2
_STAGE2_TRUNCATION_REASONS = {
    "length",
    "max_tokens",
    "max_output_tokens",
    "token_limit",
    "output_limit",
}


class EvaluationError(Exception):
    """Raised when an evaluator produces invalid, unparseable, or degenerate output."""
    pass


def is_evaluator_refusal(text: str) -> bool:
    """Return True when Stage 2 output is a refusal rather than a malformed ranking."""
    normalized = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    if not normalized:
        return False

    strong_markers = (
        "i cannot perform this task",
        "i can't perform this task",
        "the request you pasted requires capabilities and a role i do not have",
        "i do not have tools or the ability to",
        "my capabilities are strictly limited to notion workspace operations",
    )
    if any(marker in normalized for marker in strong_markers):
        return True

    refusal_terms = (
        "cannot compare",
        "cannot rank",
        "cannot evaluate",
        "do not have the ability to rank",
        "do not have the ability to evaluate",
    )
    return any(term in normalized for term in refusal_terms) and "response" in normalized


def is_annotation_only_evaluator_output(text: str) -> bool:
    """Detect paragraph-verdict JSON that omitted the mandatory peer ranking."""
    raw = str(text or "")
    normalized = raw.casefold()
    annotation_keys = (
        '"response"',
        '"paragraph"',
        '"verdict"',
        '"comment"',
    )
    has_annotations = all(key in normalized for key in annotation_keys)
    has_ranking_contract = bool(
        re.search(r"(?im)^\s*(?:#{1,6}\s*)?(?:final\s+|overall\s+)?ranking\b", raw)
        or re.search(r"(?is)[\"']ranking[\"']\s*:\s*\[", raw)
    )
    return has_annotations and not has_ranking_contract


_NOTION_COUNCIL_LOCK: asyncio.Lock | None = None
_NOTION_COUNCIL_LOCK_LOOP: asyncio.AbstractEventLoop | None = None
_NOTION_STAGGER_SECONDS = 3.0
_NOTION_503_PAUSE_SECONDS = 30.0
_NOTION_503_MAX_RETRIES = 2
_last_notion_call_started_at = 0.0


def _is_notion2api_model(model: str) -> bool:
    normalized = (model or "").strip().lower()
    if normalized.startswith("notion2api:"):
        return True
    if normalized.startswith("custom:"):
        settings = get_settings()
        if not settings.enabled_providers.get("custom"):
            return False
        name = (settings.custom_endpoint_name or "").lower()
        url = (settings.custom_endpoint_url or "").lower()
        if "notion" in name or "notion2api" in name:
            return True
        return "notion" in url or "notion2api" in url
    return False


def _is_notion_sonnet5_model(model: str) -> bool:
    normalized = (model or "").strip().lower()
    if ":" in normalized:
        normalized = normalized.rsplit(":", 1)[-1]
    return normalized in {
        "angel-cake-high",
        "claude-sonnet5",
        "claude-sonnet-5",
        "sonnet-5",
        "sonnet5",
    }


def build_stage1_prompt(
    model: str,
    settings: Any,
    user_query: str,
    search_context_block: str = "",
) -> str:
    from .prompts import STAGE1_PROMPT_DEFAULT, STAGE1_SONNET5_COMPAT_PROMPT

    if _is_notion_sonnet5_model(model):
        template = STAGE1_SONNET5_COMPAT_PROMPT
    else:
        template = getattr(settings, "stage1_prompt", "") or STAGE1_PROMPT_DEFAULT

    try:
        return template.format(
            user_query=user_query,
            search_context_block=search_context_block,
        )
    except Exception:
        fallback = (
            STAGE1_SONNET5_COMPAT_PROMPT
            if _is_notion_sonnet5_model(model)
            else STAGE1_PROMPT_DEFAULT
        )
        return fallback.format(
            user_query=user_query,
            search_context_block=search_context_block,
        )


def _notion_council_lock() -> asyncio.Lock:
    global _NOTION_COUNCIL_LOCK, _NOTION_COUNCIL_LOCK_LOOP
    loop = asyncio.get_running_loop()
    if _NOTION_COUNCIL_LOCK is None or _NOTION_COUNCIL_LOCK_LOOP is not loop:
        _NOTION_COUNCIL_LOCK = asyncio.Lock()
        _NOTION_COUNCIL_LOCK_LOOP = loop
    return _NOTION_COUNCIL_LOCK


async def _wait_notion_stagger() -> None:
    global _last_notion_call_started_at
    now = time.monotonic()
    if _last_notion_call_started_at > 0:
        delay = _NOTION_STAGGER_SECONDS - (now - _last_notion_call_started_at)
        if delay > 0:
            await asyncio.sleep(delay)
    _last_notion_call_started_at = time.monotonic()


def _vary_notion_thread_title(model: str, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Put the model name on its own first line so Notion thread titles differ per member."""
    if not _is_notion2api_model(model):
        return messages

    label = model.split(":", 1)[-1].strip() or model
    varied: List[Dict[str, str]] = []
    for msg in messages:
        if msg.get("role") != "user":
            varied.append(msg)
            continue
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            varied.append(msg)
            continue
        first_line = content.splitlines()[0].strip() if content else ""
        if first_line == label:
            varied.append(msg)
        else:
            varied.append({**msg, "content": f"{label}\n{content}"})
    return varied


def _is_notion_overload_result(result: Dict[str, Any] | None) -> bool:
    if not result or not result.get("error"):
        return False
    if result.get("rate_limited"):
        return True
    message = (result.get("error_message") or "").lower()
    if any(marker in message for marker in ("503", "service unavailable", "rate limit", "rate_limit", "temporarily unavailable")):
        return True
    timeline = result.get("debug_timeline") or []
    if timeline:
        try:
            return int(timeline[-1].get("status") or 0) == 503
        except (TypeError, ValueError):
            return False
    return False


async def _query_model_gated(
    model: str,
    messages: List[Dict[str, str]],
    *,
    timeout: float,
    temperature: float,
    attachments: List[Dict[str, Any]] | None = None,
    conversation_id: str | None = None,
    max_output_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Stagger Notion request starts without serializing in-flight model calls."""
    if not _is_notion2api_model(model):
        return await _query_model_raw(
            model,
            messages,
            timeout=timeout,
            temperature=temperature,
            attachments=attachments,
            conversation_id=conversation_id,
            max_output_tokens=max_output_tokens,
        )

    lock = _notion_council_lock()
    messages = _vary_notion_thread_title(model, messages)

    async def _make_call():
        async with lock:
            await _wait_notion_stagger()
        return await _query_model_raw(
            model,
            messages,
            timeout=timeout,
            temperature=temperature,
            attachments=attachments,
            conversation_id=conversation_id,
            max_output_tokens=max_output_tokens,
        )

    result = await _make_call()

    retries = 0
    while _is_notion_overload_result(result) and retries < _NOTION_503_MAX_RETRIES:
        retries += 1
        logger.warning(
            "Notion2API overload for %s; pausing %.0fs before retry %d/%d",
            model,
            _NOTION_503_PAUSE_SECONDS,
            retries,
            _NOTION_503_MAX_RETRIES,
        )
        await asyncio.sleep(_NOTION_503_PAUSE_SECONDS)
        global _last_notion_call_started_at
        _last_notion_call_started_at = time.monotonic()
        result = await _make_call()

    return result


THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>[\s\S]*?</think>", re.IGNORECASE)
UNCLOSED_THINK_RE = re.compile(r"<think\b[^>]*>[\s\S]*$", re.IGNORECASE)


from .providers.openai import OpenAIProvider
from .providers.anthropic import AnthropicProvider
from .providers.google import GoogleProvider
from .providers.mistral import MistralProvider
from .providers.deepseek import DeepSeekProvider
from .providers.openrouter import OpenRouterProvider
from .providers.ollama import OllamaProvider
from .providers.groq import GroqProvider
from .providers.custom_openai import CustomOpenAIProvider
from .providers.nvidia import NvidiaProvider
from .providers.opencode import OpenCodeProvider
from .providers.notion2api import Notion2APIProvider

# Initialize providers
PROVIDERS = {
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
    "google": GoogleProvider(),
    "mistral": MistralProvider(),
    "deepseek": DeepSeekProvider(),
    "groq": GroqProvider(),
    "nvidia": NvidiaProvider(),
    "openrouter": OpenRouterProvider(),
    "ollama": OllamaProvider(),
    "custom": CustomOpenAIProvider(),
    "notion2api": Notion2APIProvider(),
    "opencode-zen": OpenCodeProvider(product="zen"),
    "opencode-go": OpenCodeProvider(product="go"),
}

def get_provider_for_model(model_id: str) -> Any:
    """Determine the provider for a given model ID."""
    if ":" in model_id:
        provider_name = model_id.split(":")[0]
        if provider_name in PROVIDERS:
            return PROVIDERS[provider_name]

    # Default to OpenRouter for unprefixed models (legacy support)
    return PROVIDERS["openrouter"]


_STAGE2_MODEL_ALIAS_CACHE: Dict[str, List[str]] = {}


def _normalize_model_alias(value: str) -> str:
    """Normalize display-name drift such as ``GPT-5.5`` vs ``GPT 5.5``."""
    return "".join(character for character in str(value or "").casefold() if character.isalnum())


def _metadata_aliases(model: Dict[str, Any]) -> List[str]:
    """Extract user-visible and transport aliases from provider model metadata."""
    aliases = set()
    for key in ("id", "canonical_id", "display_name", "name", "public_name", "model_family"):
        value = str(model.get(key) or "").strip()
        if value:
            aliases.add(value)
            aliases.add(re.sub(r"\s*\[[^]]+\]\s*$", "", value).strip())

    raw_aliases = model.get("aliases")
    if isinstance(raw_aliases, list):
        aliases.update(str(alias).strip() for alias in raw_aliases if str(alias).strip())

    expanded = set(aliases)
    for alias in aliases:
        if ":" in alias:
            expanded.add(alias.split(":", 1)[1])
        for prefix in ("claude ", "openai ", "google ", "xai "):
            if alias.casefold().startswith(prefix):
                expanded.add(alias[len(prefix):].strip())
    return sorted(alias for alias in expanded if alias)


async def build_stage2_label_aliases(label_to_model: Dict[str, str]) -> Dict[str, List[str]]:
    """Resolve each anonymized response label to accepted model-name aliases.

    Evaluators are instructed to rank anonymous labels, but some providers still
    emit the visible model names. Provider metadata is the authoritative bridge
    from opaque model IDs (for example Notion2API transport IDs) back to those
    visible names. Failures here are non-fatal; canonical IDs remain available.
    """
    aliases_by_label: Dict[str, set[str]] = {}
    labels_by_provider: Dict[Any, List[tuple[str, str]]] = {}

    for label, model_id in label_to_model.items():
        model_text = str(model_id or "").strip()
        base_aliases = {model_text}
        if ":" in model_text:
            base_aliases.add(model_text.split(":", 1)[1])
        cached_aliases = _STAGE2_MODEL_ALIAS_CACHE.get(model_text.casefold(), [])
        base_aliases.update(cached_aliases)
        aliases_by_label[label] = {alias for alias in base_aliases if alias}
        if not cached_aliases:
            labels_by_provider.setdefault(get_provider_for_model(model_text), []).append((label, model_text))

    async def fetch_provider_models(provider: Any) -> tuple[Any, List[Dict[str, Any]]]:
        try:
            models = await provider.get_models()
            return provider, models if isinstance(models, list) else []
        except Exception as exc:
            logger.warning("Unable to load model aliases for Stage 2 recovery: %s", exc)
            return provider, []

    provider_results = await asyncio.gather(
        *(fetch_provider_models(provider) for provider in labels_by_provider),
    )
    for provider, models in provider_results:
        requested = labels_by_provider.get(provider, [])
        for label, model_id in requested:
            target_full = model_id.casefold()
            target_suffix = model_id.split(":", 1)[-1].casefold()
            for metadata in models:
                metadata_ids = {
                    str(metadata.get("id") or "").strip().casefold(),
                    str(metadata.get("canonical_id") or "").strip().casefold(),
                }
                metadata_suffixes = {value.split(":", 1)[-1] for value in metadata_ids if value}
                metadata_alias_ids = {
                    str(alias).strip().casefold()
                    for alias in (metadata.get("aliases") or [])
                    if str(alias).strip()
                } if isinstance(metadata.get("aliases"), list) else set()
                if not (
                    target_full in metadata_ids
                    or target_suffix in metadata_suffixes
                    or target_suffix in metadata_alias_ids
                ):
                    continue
                resolved_aliases = _metadata_aliases(metadata)
                aliases_by_label[label].update(resolved_aliases)
                _STAGE2_MODEL_ALIAS_CACHE[model_id.casefold()] = resolved_aliases
                break

    return {
        label: sorted(aliases)
        for label, aliases in aliases_by_label.items()
    }


async def _query_model_raw(
    model: str,
    messages: List[Dict[str, str]],
    *,
    timeout: float = 120.0,
    temperature: float = 0.7,
    max_output_tokens: Optional[int] = None,
    conversation_id: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Dispatch query to appropriate provider directly."""
    provider = get_provider_for_model(model)
    try:
        from .providers.notion2api import Notion2APIProvider
        from .providers.custom_openai import CustomOpenAIProvider
        if isinstance(provider, (Notion2APIProvider, CustomOpenAIProvider)):
            response = await provider.query(
                model_id=model,
                messages=messages,
                timeout=timeout,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                conversation_id=conversation_id,
                attachments=attachments,
            )
        else:
            response = await provider.query(model, messages, timeout, temperature)
    except Exception as exc:
        logger.exception("Provider call failed for %s", model)
        response = {"error": True, "error_message": str(exc)}

    if isinstance(response, dict):
        return await attach_cost(model, response)
    return response


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    *,
    timeout: float = 120.0,
    temperature: float = 0.7,
    max_output_tokens: Optional[int] = None,
    conversation_id: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Dispatch query with serialization for Notion2API."""
    try:
        settings = get_settings()
        firing_mode = settings.notion2api_firing_mode
    except Exception:
        firing_mode = "rapid_fire"

    if _is_notion2api_model(model) and firing_mode == "random_delay":
        return await _query_model_gated(
            model,
            messages,
            timeout=timeout,
            temperature=temperature,
            attachments=attachments,
            conversation_id=conversation_id,
            max_output_tokens=max_output_tokens,
        )
    return await _query_model_raw(
        model,
        messages,
        timeout=timeout,
        temperature=temperature,
        attachments=attachments,
        conversation_id=conversation_id,
        max_output_tokens=max_output_tokens,
    )


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]],
    conversation_id: "str | None" = None,
) -> Dict[str, Any]:
    """Dispatch parallel query to appropriate providers."""
    tasks = []

    # Group models by provider to optimize batching if supported (mostly for OpenRouter/Ollama legacy)
    # But for simplicity and modularity, we'll just spawn individual tasks for now
    # OpenRouter and Ollama wrappers might handle their own internal concurrency if we called a batch method,
    # but the base interface is single query.
    # To maintain OpenRouter's batch efficiency if it exists, we could check type, but let's stick to simple asyncio.gather first.

    # Actually, the previous implementation used specific batch logic for Ollama and OpenRouter.
    # We should preserve that if possible, OR just rely on asyncio.gather which is fine for HTTP clients.
    # The previous `_query_ollama_batch` was just a helper to strip prefixes.
    # `openrouter.query_models_parallel` was doing the gather.

    # Let's just use asyncio.gather for all. It's clean and effective.

    async def _query_safe(m: str):
        try:
            return m, await query_model(m, messages, conversation_id=conversation_id)
        except Exception as e:
            return m, {"error": True, "error_message": str(e)}

    tasks = [_query_safe(m) for m in models]
    results = await asyncio.gather(*tasks)

    return dict(results)


def strip_thinking_blocks(text: Any) -> str:
    """Remove hidden-reasoning markup from model-visible text."""

    cleaned = str(text or "").strip()
    cleaned = THINK_BLOCK_RE.sub("", cleaned)
    cleaned = UNCLOSED_THINK_RE.sub("", cleaned)
    return cleaned.strip()


def get_response_finish_reason(response: Dict[str, Any] | None) -> str | None:
    """Extract a provider stop/finish reason from common response shapes."""
    if not isinstance(response, dict):
        return None

    for key in ("finish_reason", "stop_reason"):
        value = response.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    metadata = response.get("metadata")
    if isinstance(metadata, dict):
        for key in ("finish_reason", "stop_reason"):
            value = metadata.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()

    choices = response.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            value = choice.get("finish_reason") or choice.get("stop_reason")
            if value is not None and str(value).strip():
                return str(value).strip()
    return None


def response_was_truncated(response: Dict[str, Any] | None) -> bool:
    """Return True when provider metadata indicates an incomplete output."""
    if not isinstance(response, dict):
        return False
    if response.get("truncated") is True or response.get("stream_interrupted") is True:
        return True
    finish_reason = (get_response_finish_reason(response) or "").strip().lower()
    return finish_reason in _STAGE2_TRUNCATION_REASONS


def _strip_stage2_output_contract(prompt: str) -> str:
    """Remove stale output-format instructions while preserving the evaluation task."""
    cleaned = str(prompt or "")
    cleaned = cleaned.split("\n\nCRITICAL OUTPUT CONTRACT:", 1)[0]
    cleaned = re.split(
        r"\n\s*Respond with valid JSON followed by your ranking\s*:\s*",
        cleaned,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return cleaned.rstrip()


def build_stage2_recovery_prompt(
    original_prompt: str,
    valid_labels: List[str],
    parse_error: str,
    structured_output_instructions: Optional[str] = None,
) -> str:
    """Build a deterministic retry prompt without conflicting prior contracts."""
    task_prompt = _strip_stage2_output_contract(original_prompt)
    allowed_labels = ", ".join(valid_labels)
    numbered_slots = "\n".join(
        f"{index}. <one unused allowed Response label>"
        for index in range(1, len(valid_labels) + 1)
    )
    structured_suffix = ""
    if structured_output_instructions:
        return_instruction = (
            "Return the complete ranking block first, with every allowed label exactly once.\n"
        )
        structured_suffix = (
            "\nAfter the ranking block, return the required structured evaluation exactly as follows:\n"
            f"{structured_output_instructions.strip()}"
        )
    else:
        return_instruction = (
            "Return ONLY the complete ranking block below, with every allowed label exactly once.\n"
        )
    return (
        f"{task_prompt}\n\n"
        "RECOVERY RETRY: The previous answer was received but failed validation "
        f"({parse_error}). Do not include analysis, a preface, or commentary. "
        f"Allowed labels: {allowed_labels}. Use each exactly once and no others. "
        f"{return_instruction}"
        "FINAL RANKING:\n"
        f"{numbered_slots}"
        f"{structured_suffix}"
    )


def build_stage2_result(
    model: str,
    response: Dict[str, Any] | None,
    valid_labels: List[str],
    expected_count: int,
    attempts: Optional[List[Dict[str, Any]]] = None,
    label_aliases: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Classify a Stage 2 provider result without conflating parse failure with no response."""
    response = response if isinstance(response, dict) else {
        "error": True,
        "error_message": "Provider returned no response object.",
    }
    attempt_ledger = list(attempts or [])
    finish_reason = get_response_finish_reason(response)
    truncated = response_was_truncated(response)

    if response.get("error"):
        result = {
            "model": model,
            "ranking": response.get("content"),
            "parsed_ranking": [],
            "error": True,
            "status": "provider_error",
            "error_message": response.get("error_message", "Provider request failed."),
            "usage": response.get("usage"),
            "cost": response.get("cost"),
            "finish_reason": finish_reason,
            "truncated": truncated,
        }
    else:
        full_text = strip_thinking_blocks(response.get("content", ""))
        try:
            parsed = parse_ranking_from_text(
                full_text,
                expected_count=expected_count,
                valid_labels=valid_labels,
                label_aliases=label_aliases,
            )
            result = {
                "model": model,
                "ranking": full_text,
                "parsed_ranking": parsed,
                "error": None,
                "status": "completed",
                "usage": response.get("usage"),
                "cost": response.get("cost"),
                "finish_reason": finish_reason,
                "truncated": truncated,
            }
        except EvaluationError as exc:
            evaluator_refused = is_evaluator_refusal(full_text)
            annotation_only = is_annotation_only_evaluator_output(full_text)
            status = (
                "evaluator_refused"
                if evaluator_refused
                else "truncated_evaluator_output"
                if truncated
                else "annotation_only_evaluator_output"
                if annotation_only
                else "invalid_evaluator_output"
            )
            if evaluator_refused:
                message = "Evaluator refused the ranking task and returned no usable ranking."
            elif truncated:
                message = (
                    "Evaluator output ended before a complete ranking could be parsed. "
                    f"Provider finish reason: {finish_reason or 'stream interruption'}."
                )
            elif annotation_only:
                message = (
                    "Evaluator returned paragraph annotations but omitted the required complete "
                    "peer ranking. Annotation-only output is not a valid Stage 2 ranking."
                )
            else:
                message = str(exc)
            result = {
                "model": model,
                "ranking": full_text,
                "parsed_ranking": [],
                "error": True,
                "status": status,
                "error_message": message,
                "parse_error": str(exc),
                "usage": response.get("usage"),
                "cost": response.get("cost"),
                "finish_reason": finish_reason,
                "truncated": truncated,
            }

    if attempt_ledger:
        result["attempts"] = attempt_ledger
        result["recovered_after_retry"] = bool(
            result.get("error") is None
            and any(attempt.get("status") != "completed" for attempt in attempt_ledger[:-1])
        )
    return result


def clean_generated_short_text(text: str, fallback: str = "Untitled Conversation", max_length: int = 50) -> str:
    """Clean model-generated labels such as titles and search queries."""

    cleaned = strip_thinking_blocks(text)
    cleaned = " ".join(cleaned.replace("\r", " ").replace("\n", " ").split())
    cleaned = cleaned.strip(" \"'`“”‘’.,;:-")
    cleaned = re.sub(r"^\s*(?:title|search query)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" \"'`“”‘’.,;:-")

    if not cleaned:
        cleaned = strip_thinking_blocks(fallback)
        cleaned = " ".join(cleaned.replace("\r", " ").replace("\n", " ").split())
        cleaned = cleaned.strip(" \"'`“”‘’.,;:-")
        cleaned = re.sub(r"^\s*(?:title|search query)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip(" \"'`“”‘’.,;:-")

    if not cleaned:
        cleaned = "Untitled Conversation"

    if len(cleaned) > max_length:
        cleaned = cleaned[: max_length - 3].rstrip(" \"'`“”‘’.,;:-") + "..."
    return cleaned


async def stage1_collect_responses(
    user_query: str,
    search_context: str = "",
    request: Any = None,
    models_override: "List[str] | None" = None,
    history: "List[Dict[str, str]] | None" = None,
    messages_override: "List[Dict[str, str]] | None" = None,
    per_model_messages: "Dict[str, List[Dict[str, str]]] | None" = None,
    conversation_id: "str | None" = None,
    attachments: List[Dict[str, Any]] | None = None,
    documents: List[Dict[str, Any]] | None = None,
    round_num: int = 1,
) -> Any:
    """
    Stage 1: Collect individual responses from all council models.

    Args:
        user_query: The user's question
        search_context: Optional web search results to provide context
        request: FastAPI request object for checking disconnects
        models_override: Per-request model list (bypasses global config)
        history: Prior conversation turns as [{role, content}, ...] for multi-turn
        messages_override: Optional messages override to bypass default prompt
        per_model_messages: Optional messages per model
        attachments: Obsolete, kept for legacy signature compatibility
        documents: File attachments with base64 data for native ingestion
        round_num: The current debate round number (used for replay policy)
    """
    settings = get_settings()

    models = (
        normalize_model_ids(models_override)
        if models_override is not None
        else get_council_models()
    )

    # Yield total count first
    yield len(models)

    council_temp = settings.council_temperature

    from .documents import prepare_documents, AttachmentCapabilities
    from .providers.notion2api import Notion2APIProvider
    from .providers.custom_openai import CustomOpenAIProvider

    def _get_capabilities_for_model(m: str) -> AttachmentCapabilities:
        provider = get_provider_for_model(m)
        replay_policy = getattr(settings, "attachment_replay_policy", "stateless_only")

        # Initial capabilities based on model type
        if isinstance(provider, Notion2APIProvider):
            initial_enabled = True
            is_stateful = True
            supported_mimes = {
                "application/pdf", "text/csv", "image/png", "image/jpeg",
                "image/gif", "image/webp", "image/heic", "text/plain", "text/markdown", "application/json"
            }
        elif isinstance(provider, CustomOpenAIProvider):
            initial_enabled = getattr(settings, "custom_endpoint_supports_attachments", False)
            is_stateful = getattr(settings, "custom_endpoint_is_stateful", False)
            supported_mimes = {
                "application/pdf", "text/csv", "image/png", "image/jpeg",
                "image/gif", "image/webp", "image/heic", "text/plain", "text/markdown", "application/json"
            }
        else:
            initial_enabled = False
            is_stateful = False
            supported_mimes = set()

        # Adjust capability based on round_num and replay policy
        effective_enabled = initial_enabled
        if initial_enabled and round_num > 1:
            if replay_policy == "first_round":
                effective_enabled = False
            elif replay_policy == "stateless_only":
                if is_stateful:
                    effective_enabled = False

        return AttachmentCapabilities(
            enabled=effective_enabled,
            supported_mime_types=supported_mimes,
            stateful=is_stateful,
        )

    async def _query_safe(m: str):
        try:
            # Determine capabilities of this specific model's provider
            caps = _get_capabilities_for_model(m)

            # Prepare documents according to provider capability
            prepared = prepare_documents(documents, caps)

            # Build the search context block if search results provided
            search_context_block = ""
            if search_context:
                from .prompts import STAGE1_SEARCH_CONTEXT_TEMPLATE
                search_context_block = STAGE1_SEARCH_CONTEXT_TEMPLATE.format(search_context=search_context)

            from .documents import format_documents_for_prompt
            fallback_block = format_documents_for_prompt(prepared.fallback_documents)
            model_query = user_query
            if fallback_block:
                model_query = f"{user_query}\n\n{fallback_block}"

            model_prompt = build_stage1_prompt(
                m,
                settings,
                model_query,
                search_context_block,
            )

            if messages_override is None and per_model_messages is None:
                model_prompt = apply_response_language(model_prompt, settings.response_language)

            if messages_override is not None:
                model_msgs = messages_override
            elif per_model_messages and m in per_model_messages:
                model_msgs = per_model_messages[m]
            else:
                model_msgs = (history or []) + [{"role": "user", "content": model_prompt}]

            model_timeout = getattr(settings, "model_timeout_seconds", 300)

            # Native attachments to pass to provider
            model_attachments = prepared.native_candidates if prepared.native_candidates else None

            return m, await query_model(
                m,
                model_msgs,
                timeout=model_timeout,
                temperature=council_temp,
                attachments=model_attachments,
                conversation_id=conversation_id,
            )
        except Exception as e:
            return m, {"error": True, "error_message": str(e)}

    from .main import _active_runs
    run_info = _active_runs.get(conversation_id) if conversation_id else None
    if run_info:
        run_info["paused"] = False
        run_info["pause_event"] = None
        run_info["continuation_mode"] = "normal"
        run_info["failed_providers"] = []
        run_info["pending_providers"] = list(models)
        run_info["active_providers"] = []

    pending_models = list(models)
    active_tasks = {}
    last_notion_fire_time = 0.0
    fail_safe_initial_wait_done = False

    firing_mode = getattr(settings, "notion2api_firing_mode", "rapid_fire")
    seq_max = getattr(settings, "notion2api_sequential_max_concurrent", 3)
    pause_on_failure = getattr(settings, "notion2api_pause_on_failure", True)

    try:
        while pending_models or active_tasks:
            # Check for client disconnect
            if request and await request.is_disconnected():
                raise asyncio.CancelledError("Client disconnected")

            # Check if paused
            if run_info and run_info.get("paused"):
                pause_event = run_info.get("pause_event")
                if pause_event:
                    await pause_event.wait()

                # Check fail-safe mode pause on resume
                if run_info and run_info.get("continuation_mode") == "fail_safe" and not fail_safe_initial_wait_done:
                    logger.info("[Fail-Safe] Pausing 30s on resume...")
                    for _ in range(60):
                        if request and await request.is_disconnected():
                            raise asyncio.CancelledError("Client disconnected")
                        await asyncio.sleep(0.5)
                    fail_safe_initial_wait_done = True

            # Try to spawn new tasks
            for m in list(pending_models):
                if run_info and run_info.get("paused"):
                    break

                is_notion = _is_notion2api_model(m)
                if not is_notion:
                    # Direct models: spawn immediately
                    pending_models.remove(m)
                    if run_info:
                        run_info["pending_providers"] = list(pending_models)
                        run_info["active_providers"].append(m)
                    active_tasks[m] = asyncio.create_task(_query_safe(m))
                    yield {
                        "type": "provider_status",
                        "data": {
                            "stage": "stage1",
                            "model": m,
                            "status": "running",
                        },
                    }
                else:
                    # Notion2API model: check concurrency and stagger
                    current_mode = run_info.get("continuation_mode", "normal") if run_info else "normal"
                    if current_mode == "conservative":
                        max_notion_conc = 1
                    else:
                        if firing_mode == "sequential":
                            max_notion_conc = seq_max
                        elif firing_mode == "random_delay":
                            max_notion_conc = 1
                        else:
                            max_notion_conc = len(models)

                    active_notion_count = sum(1 for am in active_tasks if _is_notion2api_model(am))
                    if active_notion_count >= max_notion_conc:
                        continue

                    now = time.monotonic()
                    if current_mode == "conservative":
                        stagger_delay = random.uniform(15.0, 25.0)
                    elif current_mode == "fail_safe":
                        stagger_delay = random.uniform(5.0, 13.0)
                    else:
                        if firing_mode == "random_delay":
                            stagger_delay = random.uniform(5.0, 13.0)
                        else:
                            stagger_delay = 0.0

                    if now - last_notion_fire_time < stagger_delay:
                        continue

                    # Spawn Notion task
                    pending_models.remove(m)
                    if run_info:
                        run_info["pending_providers"] = list(pending_models)
                        run_info["active_providers"].append(m)
                    active_tasks[m] = asyncio.create_task(_query_safe(m))
                    yield {
                        "type": "provider_status",
                        "data": {
                            "stage": "stage1",
                            "model": m,
                            "status": "running",
                        },
                    }
                    last_notion_fire_time = now

            # Wait for any active tasks to complete
            if active_tasks:
                done, _ = await asyncio.wait(
                    list(active_tasks.values()),
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=0.2
                )

                for task in done:
                    completed_model = None
                    for model_id, t in active_tasks.items():
                        if t == task:
                            completed_model = model_id
                            break

                    if completed_model:
                        active_tasks.pop(completed_model)
                        if run_info:
                            if completed_model in run_info["active_providers"]:
                                run_info["active_providers"].remove(completed_model)

                        try:
                            model, response = await task
                            result = None
                            if response is not None:
                                if response.get('error'):
                                    result = {
                                        "model": model,
                                        "response": None,
                                        "error": response.get('error'),
                                        "error_message": response.get('error_message', 'Unknown error'),
                                        "usage": response.get('usage'),
                                        "cost": response.get('cost'),
                                    }
                                else:
                                    content = response.get('content', '')
                                    if not isinstance(content, str):
                                        content = str(content) if content is not None else ''
                                    content = strip_thinking_blocks(content)
                                    result = {
                                        "model": model,
                                        "response": content,
                                        "error": None,
                                        "usage": response.get('usage'),
                                        "cost": response.get('cost'),
                                    }

                            if result:
                                yield result

                            # Check for failure pause!
                            if response and response.get('error') and pause_on_failure:
                                if run_info:
                                    run_info["paused"] = True
                                    run_info["pause_event"] = asyncio.Event()
                                    if completed_model not in run_info["failed_providers"]:
                                        run_info["failed_providers"].append(completed_model)

                                # Yield pause event
                                yield {
                                    "model": completed_model,
                                    "paused": True,
                                    "pending_count": len(pending_models) + len(active_tasks)
                                }
                        except asyncio.CancelledError:
                            raise
                        except Exception as e:
                            logger.error(f"Error processing Stage 1 task result: {e}")
            else:
                await asyncio.sleep(0.1)

    except asyncio.CancelledError:
        for t in active_tasks.values():
            if not t.done():
                t.cancel()
        raise


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    search_context: str = "",
    request: Any = None,
    prompt_override: "str | None" = None,
    conversation_id: "str | None" = None,
    output_validator: "Optional[Callable[[str], Dict[str, Any]]]" = None,
    structured_output_recovery: "str | None" = None,
) -> Any: # Returns an async generator
    """
    Stage 2: Collect peer rankings from all council models.

    Yields:
        - First yield: label_to_model mapping (dict)
        - Subsequent yields: Individual model results (dict)
    """
    settings = get_settings()

    # Filter to only successful responses for ranking.
    # Also exclude pause-event sentinels ({"model": X, "paused": True}) — they
    # carry no ranking content and would cause duplicate model entries if included.
    successful_results = [
        r for r in stage1_results
        if not r.get('error') and not r.get('paused')
    ]

    # Create anonymized labels for responses (Response A, Response B, etc.)
    labels = [chr(65 + i) for i in range(len(successful_results))]  # A, B, C, ...

    # Create mapping from label to model name
    label_to_model = {
        f"Response {label}": result['model']
        for label, result in zip(labels, successful_results)
    }

    # Yield the mapping first so the caller has it
    yield label_to_model

    # Build the ranking prompt
    responses_text = "\n\n".join([
        f"Response {label}:\n{result['response']}"
        for label, result in zip(labels, successful_results)
    ])

    valid_label_list = ", ".join(label_to_model.keys())
    if prompt_override:
        ranking_prompt = prompt_override
    else:
        search_context_block = ""
        if search_context:
            search_context_block = f"Context from Web Search:\n{search_context}\n"

        try:
            # Ensure prompt is not None
            prompt_template = settings.stage2_prompt
            if not prompt_template:
                from .prompts import STAGE2_PROMPT_DEFAULT
                prompt_template = STAGE2_PROMPT_DEFAULT

            ranking_prompt = prompt_template.format(
                user_query=user_query,
                responses_text=responses_text,
                search_context_block=search_context_block
            )
        except (KeyError, AttributeError, TypeError) as e:
            logger.warning(f"Error formatting Stage 2 prompt: {e}. Using fallback.")
            ranking_prompt = (
                f"Question: {user_query}\n\n{responses_text}\n\n"
                f"Rank these responses."
            )

    # Apply the anonymity and parseability contract to every Stage 2 prompt,
    # including paragraph/claim prompt overrides.
    ranking_prompt += (
        f"\n\nCRITICAL OUTPUT CONTRACT: Use ONLY these anonymized labels, "
        f"each exactly once: {valid_label_list}. "
        f"Do not identify, infer, mention, or rank model/provider names. "
        f"Do not invent or reference any other response labels. "
        f"BEGIN your response with a complete ranking block using this exact syntax:\n"
        f"FINAL RANKING:\n"
        f"1. <one allowed Response label>\n"
        f"Continue the numbered list through {len(label_to_model)} ranked items. "
        f"Place this ranking before any audit or explanation so it survives output truncation. "
        f"Do not repeat or revise the ranking later in the response."
    )

    ranking_prompt = apply_response_language(ranking_prompt, settings.response_language)

    messages = [{"role": "user", "content": ranking_prompt}]

    # Only use models that successfully responded in Stage 1
    # (no point asking failed models to rank - they'll just fail again)
    successful_models = [r['model'] for r in successful_results]

    # Use dedicated Stage 2 temperature (lower for consistent ranking output)
    stage2_temp = settings.stage2_temperature
    try:
        stage2_max_output_tokens = int(
            getattr(settings, "stage2_max_output_tokens", STAGE2_MAX_OUTPUT_TOKENS_DEFAULT)
            or STAGE2_MAX_OUTPUT_TOKENS_DEFAULT
        )
    except (TypeError, ValueError):
        stage2_max_output_tokens = STAGE2_MAX_OUTPUT_TOKENS_DEFAULT
    stage2_max_output_tokens = max(4096, min(stage2_max_output_tokens, 32768))

    valid_labels = list(label_to_model.keys())
    expected_count = len(successful_results)
    label_aliases = await build_stage2_label_aliases(label_to_model)

    async def _query_safe(m: str):
        attempt_messages = messages
        attempts_ledger: List[Dict[str, Any]] = []
        model_timeout = getattr(settings, "model_timeout_seconds", 300)

        for attempt in range(1, STAGE2_FORMAT_RETRY_ATTEMPTS + 1):
            safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "-", m).strip("-") or "model"
            attempt_conversation_id = (
                f"{conversation_id}-stage2-{safe_model}-{attempt}"
                if conversation_id
                else None
            )
            try:
                response = await query_model(
                    m,
                    attempt_messages,
                    timeout=model_timeout,
                    temperature=stage2_temp,
                    conversation_id=attempt_conversation_id,
                    max_output_tokens=stage2_max_output_tokens,
                )
            except Exception as exc:
                response = {"error": True, "error_message": str(exc)}

            result = build_stage2_result(
                m,
                response,
                valid_labels=valid_labels,
                expected_count=expected_count,
                label_aliases=label_aliases,
            )
            if result.get("error") is None and output_validator:
                try:
                    validated_fields = output_validator(result.get("ranking", ""))
                    if validated_fields:
                        result.update(validated_fields)
                except EvaluationError as exc:
                    result["error"] = True
                    result["status"] = "invalid_structured_evaluator_output"
                    result["error_message"] = f"Invalid structured evaluation: {exc}"
                    result["parse_error"] = str(exc)

            attempt_record = {
                "attempt": attempt,
                "status": result.get("status", "completed"),
                "error_message": result.get("error_message"),
                "finish_reason": result.get("finish_reason"),
                "truncated": bool(result.get("truncated")),
                "usage": result.get("usage"),
                "cost": result.get("cost"),
            }

            retryable_format_failure = result.get("status") in {
                "invalid_evaluator_output",
                "invalid_structured_evaluator_output",
                "annotation_only_evaluator_output",
                "truncated_evaluator_output",
            }
            if retryable_format_failure:
                attempt_record["raw_response"] = result.get("ranking", "")
            attempts_ledger.append(attempt_record)

            if retryable_format_failure and attempt < STAGE2_FORMAT_RETRY_ATTEMPTS:
                attempt_messages = [{
                    "role": "user",
                    "content": build_stage2_recovery_prompt(
                        ranking_prompt,
                        valid_labels,
                        result.get("parse_error") or result.get("error_message") or "missing ranking",
                        structured_output_instructions=structured_output_recovery,
                    ),
                }]
                continue

            result["attempts"] = attempts_ledger
            result["recovered_after_retry"] = bool(
                result.get("error") is None and attempt > 1
            )
            result["max_output_tokens"] = stage2_max_output_tokens
            return m, result

        return m, build_stage2_result(
            m,
            {"error": True, "error_message": "Stage 2 retry loop ended without a terminal result."},
            valid_labels=valid_labels,
            expected_count=expected_count,
            attempts=attempts_ledger,
            label_aliases=label_aliases,
        )

    from .main import _active_runs
    run_info = _active_runs.get(conversation_id) if conversation_id else None
    if run_info:
        run_info["paused"] = False
        run_info["pause_event"] = None
        run_info["continuation_mode"] = "normal"
        if "failed_providers" not in run_info:
            run_info["failed_providers"] = []
        run_info["pending_providers"] = list(successful_models)
        run_info["active_providers"] = []

    pending_models = list(successful_models)
    active_tasks = {}
    last_notion_fire_time = 0.0
    fail_safe_initial_wait_done = False

    firing_mode = getattr(settings, "notion2api_firing_mode", "rapid_fire")
    seq_max = getattr(settings, "notion2api_sequential_max_concurrent", 3)
    pause_on_failure = getattr(settings, "notion2api_pause_on_failure", True)

    try:
        while pending_models or active_tasks:
            # Check for client disconnect
            if request and await request.is_disconnected():
                raise asyncio.CancelledError("Client disconnected")

            # Check if paused
            if run_info and run_info.get("paused"):
                pause_event = run_info.get("pause_event")
                if pause_event:
                    await pause_event.wait()

                # Check fail-safe mode pause on resume
                if run_info and run_info.get("continuation_mode") == "fail_safe" and not fail_safe_initial_wait_done:
                    logger.info("[Fail-Safe] Pausing 30s on resume...")
                    for _ in range(60):
                        if request and await request.is_disconnected():
                            raise asyncio.CancelledError("Client disconnected")
                        await asyncio.sleep(0.5)
                    fail_safe_initial_wait_done = True

            # Try to spawn new tasks
            for m in list(pending_models):
                if run_info and run_info.get("paused"):
                    break

                is_notion = _is_notion2api_model(m)
                if not is_notion:
                    # Direct models: spawn immediately
                    pending_models.remove(m)
                    if run_info:
                        run_info["pending_providers"] = list(pending_models)
                        run_info["active_providers"].append(m)
                    active_tasks[m] = asyncio.create_task(_query_safe(m))
                    yield {
                        "type": "provider_status",
                        "data": {
                            "stage": "stage2",
                            "model": m,
                            "status": "running",
                        },
                    }
                else:
                    # Notion2API model: check concurrency and stagger
                    current_mode = run_info.get("continuation_mode", "normal") if run_info else "normal"
                    if current_mode == "conservative":
                        max_notion_conc = 1
                    else:
                        if firing_mode == "sequential":
                            max_notion_conc = seq_max
                        elif firing_mode == "random_delay":
                            max_notion_conc = 1
                        else:
                            max_notion_conc = len(successful_models)

                    active_notion_count = sum(1 for am in active_tasks if _is_notion2api_model(am))
                    if active_notion_count >= max_notion_conc:
                        continue

                    now = time.monotonic()
                    if current_mode == "conservative":
                        stagger_delay = random.uniform(15.0, 25.0)
                    elif current_mode == "fail_safe":
                        stagger_delay = random.uniform(5.0, 13.0)
                    else:
                        if firing_mode == "random_delay":
                            stagger_delay = random.uniform(5.0, 13.0)
                        else:
                            stagger_delay = 0.0

                    if now - last_notion_fire_time < stagger_delay:
                        continue

                    # Spawn Notion task
                    pending_models.remove(m)
                    if run_info:
                        run_info["pending_providers"] = list(pending_models)
                        run_info["active_providers"].append(m)
                    active_tasks[m] = asyncio.create_task(_query_safe(m))
                    yield {
                        "type": "provider_status",
                        "data": {
                            "stage": "stage2",
                            "model": m,
                            "status": "running",
                        },
                    }
                    last_notion_fire_time = now

            # Wait for any active tasks to complete
            if active_tasks:
                done, _ = await asyncio.wait(
                    list(active_tasks.values()),
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=0.2
                )

                for task in done:
                    completed_model = None
                    for model_id, t in active_tasks.items():
                        if t == task:
                            completed_model = model_id
                            break

                    if completed_model:
                        active_tasks.pop(completed_model)
                        if run_info:
                            if completed_model in run_info["active_providers"]:
                                run_info["active_providers"].remove(completed_model)

                        try:
                            model, result = await task

                            if result:
                                yield result

                            # Pause only for an actual provider invocation failure. A model
                            # response that cannot be parsed has already received a compact
                            # automatic format retry and should not be mislabeled as downtime.
                            if (
                                result
                                and result.get("status") == "provider_error"
                                and pause_on_failure
                            ):
                                if run_info:
                                    run_info["paused"] = True
                                    run_info["pause_event"] = asyncio.Event()
                                    if completed_model not in run_info["failed_providers"]:
                                        run_info["failed_providers"].append(completed_model)

                                yield {
                                    "model": completed_model,
                                    "paused": True,
                                    "pending_count": len(pending_models) + len(active_tasks)
                                }
                        except asyncio.CancelledError:
                            raise
                        except Exception as e:
                            logger.error(f"Error processing Stage 2 task result: {e}")
            else:
                await asyncio.sleep(0.1)

    except asyncio.CancelledError:
        for t in active_tasks.values():
            if not t.done():
                t.cancel()
        raise


def build_stage_texts(
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
) -> tuple:
    """Build formatted text summaries from stage results. Returns (stage1_text, stage2_text)."""
    stage1_text = "\n\n".join([
        f"Model: {result['model']}\nResponse: {result.get('response', 'No response')}"
        for result in stage1_results
        if result.get('response') is not None
    ])
    stage2_text = "\n\n".join([
        f"Model: {result['model']}\nRanking: {result.get('ranking', 'No ranking')}"
        for result in stage2_results
        if not result.get("error") and result.get('ranking') is not None
    ])
    return stage1_text, stage2_text


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    search_context: str = "",
    chairman_override: "str | None" = None,
    prompt_override: "str | None" = None,
    conversation_id: "str | None" = None,
    system_prompt_override: "str | None" = None,
    max_output_tokens: "int | None" = None,
) -> Dict[str, Any]:
    """
    Stage 3: Chairman synthesizes final response.

    Args:
        user_query: The original user query
        stage1_results: Individual model responses from Stage 1
        stage2_results: Rankings from Stage 2
        search_context: Optional web search results
        chairman_override: Per-request chairman model (bypasses global config)
        prompt_override: Optional prompt override

    Returns:
        Dict with 'model' and 'response' keys
    """
    settings = get_settings()

    # Build comprehensive context for chairman (only include successful responses)
    stage1_text, stage2_text = build_stage_texts(stage1_results, stage2_results)

    if prompt_override:
        chairman_prompt = prompt_override
    else:
        search_context_block = ""
        if search_context:
            search_context_block = f"Context from Web Search:\n{search_context}\n"

        try:
            # Ensure prompt is not None
            prompt_template = settings.stage3_prompt
            if not prompt_template:
                from .prompts import STAGE3_PROMPT_DEFAULT
                prompt_template = STAGE3_PROMPT_DEFAULT

            chairman_prompt = prompt_template.format(
                user_query=user_query,
                stage1_text=stage1_text,
                stage2_text=stage2_text,
                search_context_block=search_context_block
            )
        except (KeyError, AttributeError, TypeError) as e:
            logger.warning(f"Error formatting Stage 3 prompt: {e}. Using fallback.")
            chairman_prompt = f"Question: {user_query}\n\nSynthesis required."

    from .prompts import STAGE3_PROMPT_DEFAULT
    chairman_prompt = apply_response_language(chairman_prompt, settings.response_language)

    # Check if we are using the default prompt (or if it's empty/None, which falls back to default)
    is_default_prompt = (not settings.stage3_prompt) or (settings.stage3_prompt.strip() == STAGE3_PROMPT_DEFAULT.strip())

    if system_prompt_override:
        messages = [
            {"role": "system", "content": system_prompt_override},
            {"role": "user", "content": chairman_prompt},
        ]
    elif is_default_prompt:
        messages = [
            {"role": "system", "content": "You are the Chairman of an LLM Council. Your task is to synthesize the provided model responses into a single, comprehensive answer."},
            {"role": "user", "content": chairman_prompt}
        ]
    else:
        # If custom prompt, send as single User message to respect user's custom persona/structure
        messages = [{"role": "user", "content": chairman_prompt}]

    # Query the chairman model with error handling
    chairman_model = chairman_override if chairman_override else get_chairman_model()
    chairman_temp = settings.chairman_temperature

    try:
        model_timeout = getattr(settings, "model_timeout_seconds", 300)
        response = await query_model(
            chairman_model,
            messages,
            timeout=model_timeout,
            temperature=chairman_temp,
            conversation_id=conversation_id,
            max_output_tokens=max_output_tokens,
        )

        # Check for error in response
        if response is None or response.get('error'):
            error_msg = response.get('error_message', 'Unknown error') if response else 'No response received'
            return {
                "model": chairman_model,
                "response": f"Error synthesizing final answer: {error_msg}",
                "error": True,
                "error_message": error_msg,
                "usage": response.get('usage') if response else None,
                "cost": response.get('cost') if response else None,
            }

        content = strip_thinking_blocks(response.get('content') or '')
        reasoning = strip_thinking_blocks(response.get('reasoning') or response.get('reasoning_details') or '')
        final_response = content or reasoning

        if not final_response:
             final_response = "No response generated by the Chairman."

        return {
            "model": chairman_model,
            "response": final_response,
            "error": False,
            "usage": response.get('usage'),
            "cost": response.get('cost'),
        }

    except Exception as e:
        logger.error(f"Unexpected error in Stage 3 synthesis: {e}")
        error_response = {
            "model": chairman_model,
            "response": "Error: Unable to generate final synthesis due to unexpected error.",
            "error": True,
            "error_message": str(e),
            "usage": None,
            "cost": None,
        }
        try:
            await attach_cost(chairman_model, error_response)
        except Exception as attach_err:
            logger.warning("Failed to attach cost on Stage 3 error: %s", attach_err)
        return error_response


def parse_ranking_from_text(
    ranking_text: str,
    expected_count: int = None,
    valid_labels: List[str] = None,
    label_aliases: Optional[Dict[str, List[str]]] = None,
) -> List[str]:
    """Parse a Stage 2 ranking without treating harmless formatting drift as failure.

    The preferred contract is a ``FINAL RANKING:`` heading followed by a numbered
    list of anonymized response labels. Recovery also accepts provider display
    names when ``label_aliases`` maps those names back to the current anonymous
    labels. A complete, unique, exact set is still required.
    """
    import re

    if not isinstance(ranking_text, str):
        ranking_text = str(ranking_text) if ranking_text is not None else ""

    valid_labels = list(valid_labels or [])
    valid_set = set(valid_labels) if valid_labels else None
    canonical_labels = {label.casefold(): label for label in valid_labels}

    def canonicalize(label: str) -> str:
        normalized = re.sub(r"\s+", " ", label.strip()).casefold()
        return canonical_labels.get(normalized, re.sub(r"\s+", " ", label.strip()).title())

    def validate(matches: List[str]) -> List[str]:
        seen = set()
        filtered = []
        for raw_label in matches:
            label = canonicalize(raw_label)
            if valid_set and label not in valid_set:
                continue
            if label in seen:
                continue
            seen.add(label)
            filtered.append(label)

        if expected_count and len(filtered) != expected_count:
            raise EvaluationError(f"Expected {expected_count} ranked items, got {len(filtered)}.")
        if valid_set and set(filtered) != valid_set:
            missing = sorted(valid_set - set(filtered))
            raise EvaluationError(f"Ranking omitted required labels: {', '.join(missing)}.")
        if not filtered:
            raise EvaluationError("No valid response labels found in the ranking.")
        return filtered

    alias_candidates: Dict[str, set[str]] = {}
    for label in valid_labels:
        aliases = [label]
        if label_aliases:
            aliases.extend(label_aliases.get(label, []))
        for alias in aliases:
            normalized = _normalize_model_alias(alias)
            if normalized:
                alias_candidates.setdefault(normalized, set()).add(label)
    alias_lookup = {
        alias: next(iter(labels))
        for alias, labels in alias_candidates.items()
        if len(labels) == 1
    }

    ranking_prefix_pattern = re.compile(r"^\s*(?:\d+\s*[.):-]|[-*\u2022])\s*")

    def clean_ranking_entry(line: str) -> str:
        candidate = ranking_prefix_pattern.sub("", str(line or "").strip())
        candidate = re.sub(r"^(?:\*\*|__|`)+", "", candidate)
        candidate = re.sub(r"(?:\*\*|__|`)+$", "", candidate)
        return candidate.strip()

    def resolve_alias_entry(line: str) -> Optional[str]:
        return alias_lookup.get(_normalize_model_alias(clean_ranking_entry(line)))

    def parse_alias_section(section: str) -> List[str]:
        resolved: List[str] = []
        for raw_line in section.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            if stripped.startswith(("{", "[")) and resolved:
                break

            label = resolve_alias_entry(raw_line)
            if label:
                if label in resolved:
                    raise EvaluationError(f"Duplicate ranked model name resolves to {label}.")
                resolved.append(label)
                if expected_count and len(resolved) == expected_count:
                    return validate(resolved)
                continue

            if resolved:
                candidate = clean_ranking_entry(raw_line)
                looks_like_rank_item = bool(ranking_prefix_pattern.match(raw_line))
                looks_like_plain_name = (
                    len(candidate) <= 100
                    and len(candidate.split()) <= 8
                    and not re.search(r"[:{}]", candidate)
                )
                if looks_like_rank_item or looks_like_plain_name:
                    raise EvaluationError(
                        f"Unknown or ambiguous model name in ranking: {candidate}."
                    )
                break

        return validate(resolved) if resolved else []

    label_pattern = r"Response\s+[A-Z]"
    line_pattern = re.compile(
        rf"^\s*(?:\d+\s*[.):-]|[-*\u2022])\s*(?:\*\*|__)?({label_pattern})(?:\*\*|__)?\b",
        re.IGNORECASE,
    )
    heading_pattern = re.compile(
        r"(?im)^\s*(?:#{1,6}\s*)?(?:\*\*|__)?(?:final\s+|overall\s+)?ranking"
        r"(?:\s*\(best\s+to\s+worst\))?(?:\*\*|__)?\s*:?[ \t]*$"
    )

    # Preferred and markdown-heading forms.
    heading_matches = list(heading_pattern.finditer(ranking_text))
    if heading_matches:
        ranking_section = ranking_text[heading_matches[-1].end():]
        matches = [
            match.group(1)
            for line in ranking_section.splitlines()
            if (match := line_pattern.match(line))
        ]
        if matches:
            return validate(matches)
        alias_matches = parse_alias_section(ranking_section)
        if alias_matches:
            return alias_matches

    # Common single-line form: "Final ranking: Response B > Response A".
    inline_pattern = re.compile(
        r"(?im)^\s*(?:#{1,6}\s*)?(?:\*\*|__)?(?:final\s+|overall\s+)?ranking"
        r"(?:\s*\(best\s+to\s+worst\))?(?:\*\*|__)?\s*:\s*(.+)$"
    )
    for inline_match in reversed(list(inline_pattern.finditer(ranking_text))):
        inline_text = inline_match.group(1)
        inline_labels = re.findall(label_pattern, inline_text, flags=re.IGNORECASE)
        if inline_labels and (
            len(inline_labels) == 1
            or re.search(r"(?:>|\u2192|\u21d2|,|;|\bthen\b)", inline_text, flags=re.IGNORECASE)
        ):
            return validate(inline_labels)

        if re.search(r"(?:>|\u2192|\u21d2|,|;|\bthen\b)", inline_text, flags=re.IGNORECASE):
            parts = re.split(r"\s*(?:>|\u2192|\u21d2|,|;|\bthen\b)\s*", inline_text, flags=re.IGNORECASE)
            resolved = [resolve_alias_entry(part) for part in parts if part.strip()]
            if resolved and all(resolved):
                if len(set(resolved)) != len(resolved):
                    raise EvaluationError("Duplicate model names found in ranking.")
                return validate(resolved)

    # Structured-output variant: {"ranking": ["Response B", "Response A"]}.
    json_match = re.search(
        r"(?is)[\"']ranking[\"']\s*:\s*\[(.*?)\]",
        ranking_text,
    )
    if json_match:
        json_labels = re.findall(label_pattern, json_match.group(1), flags=re.IGNORECASE)
        if json_labels:
            return validate(json_labels)
        quoted_items = re.findall(r"[\"']([^\"']+)[\"']", json_match.group(1))
        resolved = [resolve_alias_entry(item) for item in quoted_items]
        if resolved and all(resolved):
            if len(set(resolved)) != len(resolved):
                raise EvaluationError("Duplicate model names found in ranking array.")
            return validate(resolved)

    # Last-resort recovery for a ranking-only tail with no heading. Limiting the
    # scan to consecutive trailing ranking lines avoids mistaking the evaluator's
    # earlier per-response discussion for rank order.
    nonempty_lines = [line for line in ranking_text.splitlines() if line.strip()]
    trailing_matches = []
    for line in reversed(nonempty_lines):
        match = line_pattern.match(line)
        if not match:
            break
        trailing_matches.append(match.group(1))
    if trailing_matches:
        return validate(list(reversed(trailing_matches)))

    trailing_aliases = []
    for line in reversed(nonempty_lines):
        if not ranking_prefix_pattern.match(line):
            break
        label = resolve_alias_entry(line)
        if not label:
            break
        trailing_aliases.append(label)
    if trailing_aliases:
        resolved = list(reversed(trailing_aliases))
        if len(set(resolved)) != len(resolved):
            raise EvaluationError("Duplicate model names found in ranking tail.")
        return validate(resolved)

    raise EvaluationError(
        "No unambiguous ranking found. End the response with FINAL RANKING: "
        "followed by a numbered list such as '1. Response A'."
    )


def build_stage2a_json_skeleton(valid_labels: List[str]) -> Dict[str, Any]:
    """Build a strict JSON skeleton for Stage 2A retry prompts."""
    responses = {
        label: {
            "overall_assessment": "One concise holistic evaluation.",
            "material_defects": [],
        }
        for label in valid_labels
    }
    return {
        "responses": responses,
        "ranking": list(valid_labels),
    }


def parse_stage2a_output(
    ranking_text: str,
    valid_labels: List[str],
) -> Dict[str, Any]:
    """
    Parse the Stage 2A JSON-native response evaluation and ranking.
    Requires exact set equality between valid_labels, keys in 'responses', and labels in 'ranking'.
    """
    from .json_repair import extract_json_block
    if not ranking_text:
        raise EvaluationError("Empty output from evaluator")

    result = extract_json_block(ranking_text)
    if not isinstance(result, dict):
        raise EvaluationError("Output JSON is not a dictionary")

    responses = result.get("responses")
    ranking = result.get("ranking")

    if not isinstance(responses, dict):
        raise EvaluationError("Output JSON missing 'responses' dictionary")
    if not isinstance(ranking, list):
        raise EvaluationError("Output JSON missing 'ranking' list")

    expected_set = set(valid_labels)
    responses_set = set(responses.keys())
    ranking_set = set(ranking)

    if expected_set != responses_set:
        raise EvaluationError(f"Keys in 'responses' do not match expected labels. Expected: {expected_set}, Got: {responses_set}")

    if expected_set != ranking_set:
        raise EvaluationError(f"Labels in 'ranking' do not match expected labels. Expected: {expected_set}, Got: {ranking_set}")

    # Verify no duplicates in ranking
    if len(ranking) != len(ranking_set):
        raise EvaluationError("Duplicate labels found in ranking array")

    return result


def parse_stage2a_output_with_fallback(
    ranking_text: str,
    valid_labels: List[str],
) -> Dict[str, Any]:
    """
    Parse Stage 2A output strictly, then recover a degraded ranking-only result
    from markdown or partial JSON when strict validation fails.
    """
    try:
        return parse_stage2a_output(ranking_text, valid_labels)
    except EvaluationError as strict_error:
        try:
            recovered = parse_ranking_from_text(
                ranking_text,
                expected_count=len(valid_labels),
                valid_labels=valid_labels,
            )
        except EvaluationError:
            raise strict_error from None

        prefixed = [label if label.startswith("Response ") else f"Response {label}" for label in recovered]
        expected_set = set(valid_labels)
        if set(prefixed) != expected_set:
            raise strict_error from None

        return {
            "responses": {
                label: {
                    "degraded": True,
                    "overall_assessment": (
                        "Ranking recovered from non-JSON evaluator output; "
                        "per-response scores unavailable."
                    ),
                }
                for label in valid_labels
            },
            "ranking": prefixed,
            "degraded": True,
            "degraded_reason": "Recovered ranking from non-JSON output.",
        }


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str],
) -> List[Dict[str, Any]]:
    """
    Calculate aggregate rankings across all models.

    Skips failed, missing, blank, or malformed evaluator rankings. Returns an
    empty list when no valid rankings survive (never fabricates a default order).

    Args:
        stage2_results: Rankings from each model
        label_to_model: Mapping from anonymous labels to model names

    Returns:
        List of dicts with model name and average rank, sorted best to worst
    """
    from collections import defaultdict

    model_positions = defaultdict(list)
    valid_ranking_count = 0

    for result in stage2_results:
        if not isinstance(result, dict) or result.get("error"):
            continue

        ranking_text = result.get("ranking")
        if not isinstance(ranking_text, str) or not ranking_text.strip():
            continue

        try:
            parsed_ranking = parse_ranking_from_text(
                ranking_text,
                expected_count=len(label_to_model),
                valid_labels=list(label_to_model),
            )
        except (EvaluationError, TypeError, ValueError):
            logger.warning(
                "Skipping malformed Stage 2 ranking from model %s",
                result.get("model", "<unknown>"),
            )
            continue

        valid_ranking_count += 1

        for position, label in enumerate(parsed_ranking, start=1):
            model = label_to_model.get(label)
            if model:
                model_positions[model].append(position)

    if valid_ranking_count == 0:
        logger.warning("No valid Stage 2 rankings survived aggregation")
        return []

    aggregate = [
        {
            "model": model,
            "average_rank": round(sum(positions) / len(positions), 2),
            "rankings_count": len(positions),
        }
        for model, positions in model_positions.items()
        if positions
    ]
    aggregate.sort(key=lambda item: item["average_rank"])
    return aggregate


def calculate_audit_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Calculate aggregate rankings for Stage 2A in Audit mode.
    Each result contains a 'parsed' field, which is a dictionary with a 'ranking' list.
    """
    from collections import defaultdict

    model_positions = defaultdict(list)

    for result in stage2_results:
        if result.get("error") or "parsed" not in result:
            continue
        parsed = result["parsed"]
        ranking_list = parsed.get("ranking")
        if not isinstance(ranking_list, list):
            continue

        for position, label in enumerate(ranking_list, start=1):
            lbl_key = label.strip()
            if lbl_key.startswith("Response "):
                lbl_key = lbl_key.removeprefix("Response ").strip()
            if lbl_key in label_to_model:
                model_name = label_to_model[lbl_key]
                model_positions[model_name].append(position)

    # Calculate average position for each model
    aggregate = []
    for model, positions in model_positions.items():
        if positions:
            avg_rank = sum(positions) / len(positions)
            aggregate.append({
                "model": model,
                "average_rank": round(avg_rank, 2),
                "rankings_count": len(positions)
            })

    # Sort by average rank (lower is better)
    aggregate.sort(key=lambda x: x['average_rank'])

    return aggregate



async def generate_conversation_title(user_query: str) -> str:
    """
    Generate a short title for a conversation based on the first user message.

    Uses a fast LLM call (chairman) with customizable prompt.

    Args:
        user_query: The first user message

    Returns:
        A short title (max 50 chars)
    """
    # Validate input
    if not user_query or not isinstance(user_query, str):
        return "Untitled Conversation"

    settings = get_settings()
    try:
        prompt_template = getattr(settings, 'title_prompt', None)
        if not prompt_template:
            from .prompts import TITLE_PROMPT_DEFAULT
            prompt_template = TITLE_PROMPT_DEFAULT
        prompt = prompt_template.format(user_query=user_query)
    except Exception as e:
        logger.warning(f"Error formatting title prompt: {e}. Using fallback.")
        return clean_generated_short_text(user_query)

    chairman_model = get_chairman_model()
    messages = [{"role": "user", "content": prompt}]

    try:
        response = await query_model(chairman_model, messages, temperature=0.3)
        if response and not response.get('error'):
            title = clean_generated_short_text(response.get('content', ''), fallback=user_query)
            if title:
                return title
    except Exception as e:
        logger.error(f"Error generating title: {e}")

    # Simple heuristic fallback
    return clean_generated_short_text(user_query)


async def generate_search_query(user_query: str) -> str:
    """Generate search query from user query using the Chairman model.

    Args:
        user_query: The user's full question

    Returns:
        Search query truncated to 100 characters for safety
    """
    settings = get_settings()
    try:
        prompt_template = getattr(settings, 'query_prompt', None)
        if not prompt_template:
            from .prompts import QUERY_PROMPT_DEFAULT
            prompt_template = QUERY_PROMPT_DEFAULT
        prompt = prompt_template.format(user_query=user_query)
    except Exception as e:
        logger.warning(f"Error formatting query prompt: {e}. Using fallback.")
        return user_query[:100]

    chairman_model = get_chairman_model()
    messages = [{"role": "user", "content": prompt}]

    try:
        response = await query_model(chairman_model, messages, temperature=0.1)
        if response and not response.get('error'):
            query = clean_generated_short_text(response.get('content', ''), fallback=user_query, max_length=100)
            if query:
                return query
    except Exception as e:
        logger.error(f"Error generating search query: {e}")

    return user_query[:100]  # Fallback to direct query
