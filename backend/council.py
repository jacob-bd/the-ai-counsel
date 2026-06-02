"""3-stage LLM Council orchestration."""

from typing import List, Dict, Any, Tuple
import asyncio
import logging
import re
from . import openrouter
from . import ollama_client
from .config import get_council_models, get_chairman_model
from .costs import attach_cost
from .settings import get_settings

logger = logging.getLogger(__name__)


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


async def query_model(model: str, messages: List[Dict[str, str]], timeout: float = 120.0, temperature: float = 0.7) -> Dict[str, Any]:
    """Dispatch query to appropriate provider."""
    provider = get_provider_for_model(model)
    response = await provider.query(model, messages, timeout, temperature)
    if isinstance(response, dict):
        return await attach_cost(model, response)
    return response


async def query_models_parallel(models: List[str], messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """Dispatch parallel query to appropriate providers."""
    tasks = []
    model_to_task_map = {}
    
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
            return m, await query_model(m, messages)
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
    per_model_messages: "Dict[str, List[Dict[str, str]]] | None" = None
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

    Yields:
        - First yield: total_models (int)
        - Subsequent yields: Individual model results (dict)
    """
    settings = get_settings()

    # Build search context block if search results provided
    search_context_block = ""
    if search_context:
        from .prompts import STAGE1_SEARCH_CONTEXT_TEMPLATE
        search_context_block = STAGE1_SEARCH_CONTEXT_TEMPLATE.format(search_context=search_context)

    # Use customizable Stage 1 prompt
    try:
        prompt_template = settings.stage1_prompt
        if not prompt_template:
            from .prompts import STAGE1_PROMPT_DEFAULT
            prompt_template = STAGE1_PROMPT_DEFAULT

        prompt = prompt_template.format(
            user_query=user_query,
            search_context_block=search_context_block
        )
    except (KeyError, AttributeError, TypeError) as e:
        logger.warning(f"Error formatting Stage 1 prompt: {e}. Using fallback.")
        prompt = f"{search_context_block}Question: {user_query}" if search_context_block else user_query

    if messages_override is not None:
        messages = messages_override
    else:
        messages = (history or []) + [{"role": "user", "content": prompt}]

    models = models_override if models_override is not None and len(models_override) > 0 else get_council_models()
    
    # Yield total count first
    yield len(models)

    council_temp = settings.council_temperature

    async def _query_safe(m: str):
        try:
            model_msgs = per_model_messages.get(m, messages) if per_model_messages else messages
            return m, await query_model(m, model_msgs, temperature=council_temp)
        except Exception as e:
            return m, {"error": True, "error_message": str(e)}

    # Create tasks
    tasks = [asyncio.create_task(_query_safe(m)) for m in models]
    
    # Process as they complete
    pending = set(tasks)
    try:
        while pending:
            # Check for client disconnect
            if request and await request.is_disconnected():
                logger.info("Client disconnected during Stage 1. Cancelling tasks...")
                for t in pending:
                    t.cancel()
                raise asyncio.CancelledError("Client disconnected")

            # Wait for the next task to complete (with timeout to check for disconnects)
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED, timeout=1.0)

            for task in done:
                try:
                    model, response = await task
                    
                    result = None
                    if response is not None:
                        if response.get('error'):
                            # Include failed models with error info
                            result = {
                                "model": model,
                                "response": None,
                                "error": response.get('error'),
                                "error_message": response.get('error_message', 'Unknown error'),
                                "usage": response.get('usage'),
                                "cost": response.get('cost'),
                            }
                        else:
                            # Successful response - ensure content is always a string
                            content = response.get('content', '')
                            if not isinstance(content, str):
                                # Handle case where API returns non-string content (array, object, etc.)
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
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Error processing Stage 1 task result: {e}")

    except asyncio.CancelledError:
        # Ensure all tasks are cancelled if we get cancelled
        for t in tasks:
            if not t.done():
                t.cancel()
        raise


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    search_context: str = "",
    request: Any = None,
    prompt_override: "str | None" = None,
) -> Any: # Returns an async generator
    """
    Stage 2: Collect peer rankings from all council models.
    
    Yields:
        - First yield: label_to_model mapping (dict)
        - Subsequent yields: Individual model results (dict)
    """
    settings = get_settings()

    # Filter to only successful responses for ranking
    successful_results = [r for r in stage1_results if not r.get('error')]

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
            valid_label_list = ", ".join(label_to_model.keys())
            ranking_prompt += (
                f"\n\nCRITICAL: Your FINAL RANKING must include ONLY these labels, "
                f"each exactly once: {valid_label_list}. "
                f"Do not invent or reference any other response labels."
            )
        except (KeyError, AttributeError, TypeError) as e:
            logger.warning(f"Error formatting Stage 2 prompt: {e}. Using fallback.")
            valid_label_list = ", ".join(label_to_model.keys())
            ranking_prompt = (
                f"Question: {user_query}\n\n{responses_text}\n\n"
                f"Rank these responses. FINAL RANKING must include ONLY: {valid_label_list}."
            )

    messages = [{"role": "user", "content": ranking_prompt}]

    # Only use models that successfully responded in Stage 1
    # (no point asking failed models to rank - they'll just fail again)
    successful_models = [r['model'] for r in successful_results]

    # Use dedicated Stage 2 temperature (lower for consistent ranking output)
    stage2_temp = settings.stage2_temperature

    async def _query_safe(m: str):
        try:
            return m, await query_model(m, messages, temperature=stage2_temp)
        except Exception as e:
            return m, {"error": True, "error_message": str(e)}

    # Create tasks
    tasks = [asyncio.create_task(_query_safe(m)) for m in successful_models]

    # Process as they complete
    pending = set(tasks)
    try:
        while pending:
            # Check for client disconnect
            if request and await request.is_disconnected():
                logger.info("Client disconnected during Stage 2. Cancelling tasks...")
                for t in pending:
                    t.cancel()
                raise asyncio.CancelledError("Client disconnected")

            # Wait for the next task to complete (with timeout to check for disconnects)
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED, timeout=1.0)

            for task in done:
                try:
                    model, response = await task
                    
                    result = None
                    if response is not None:
                        if response.get('error'):
                            # Include failed models with error info
                            result = {
                                "model": model,
                                "ranking": None,
                                "parsed_ranking": [],
                                "error": response.get('error'),
                                "error_message": response.get('error_message', 'Unknown error'),
                                "usage": response.get('usage'),
                                "cost": response.get('cost'),
                            }
                        else:
                            # Ensure content is always a string before parsing
                            full_text = response.get('content', '')
                            if not isinstance(full_text, str):
                                # Handle case where API returns non-string content (array, object, etc.)
                                full_text = str(full_text) if full_text is not None else ''
                            full_text = strip_thinking_blocks(full_text)
                            
                            # Parse with expected count to avoid duplicates
                            expected_count = len(successful_results)
                            valid_labels = list(label_to_model.keys())
                            parsed = parse_ranking_from_text(
                                full_text,
                                expected_count=expected_count,
                                valid_labels=valid_labels,
                            )
                            
                            result = {
                                "model": model,
                                "ranking": full_text,
                                "parsed_ranking": parsed,
                                "error": None,
                                "usage": response.get('usage'),
                                "cost": response.get('cost'),
                            }
                    
                    if result:
                        yield result
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Error processing task result: {e}")

    except asyncio.CancelledError:
        # Ensure all tasks are cancelled if we get cancelled
        for t in tasks:
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
        if result.get('ranking') is not None
    ])
    return stage1_text, stage2_text


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    search_context: str = "",
    chairman_override: "str | None" = None,
    prompt_override: "str | None" = None
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

    # Determine message structure based on whether the prompt is default or custom
    from .prompts import STAGE3_PROMPT_DEFAULT
    
    # Check if we are using the default prompt (or if it's empty/None, which falls back to default)
    is_default_prompt = (not settings.stage3_prompt) or (settings.stage3_prompt.strip() == STAGE3_PROMPT_DEFAULT.strip())

    if is_default_prompt:
        # If using default, split into System (Persona) and User (Data) for better adherence at low temp
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
        response = await query_model(chairman_model, messages, temperature=chairman_temp)

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
            "response": f"Error: Unable to generate final synthesis due to unexpected error.",
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
) -> List[str]:
    """
    Parse the FINAL RANKING section from the model's response.

    Args:
        ranking_text: The full text response from the model
        expected_count: Optional number of expected ranked items (to truncate duplicates)
        valid_labels: Optional allow-list of labels (e.g. Response A, Response B)

    Returns:
        List of response labels in ranked order
    """
    import re

    # Defensive: ensure ranking_text is a string
    if not isinstance(ranking_text, str):
        ranking_text = str(ranking_text) if ranking_text is not None else ''

    matches = []
    valid_set = set(valid_labels) if valid_labels else None

    # Look for "FINAL RANKING:" section
    if "FINAL RANKING:" in ranking_text:
        # Extract everything after "FINAL RANKING:"
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            # Try to extract numbered list format (e.g., "1. Response A")
            # This pattern looks for: number, period, optional space, "Response X"
            numbered_matches = re.findall(r'\d+\.\s*Response [A-Z]', ranking_section)
            if numbered_matches:
                # Extract just the "Response X" part
                matches = [re.search(r'Response [A-Z]', m).group() for m in numbered_matches]
            else:
                # Fallback: Extract all "Response X" patterns in order from the section
                matches = re.findall(r'Response [A-Z]', ranking_section)
    
    # If no matches found in section (or section missing), fallback to full text search
    if not matches:
        matches = re.findall(r'Response [A-Z]', ranking_text)

    # Drop duplicates and labels outside the allow-list (e.g. hallucinated Response C)
    seen = set()
    filtered = []
    for label in matches:
        if label in seen:
            continue
        if valid_set is not None and label not in valid_set:
            continue
        seen.add(label)
        filtered.append(label)
    matches = filtered

    # Truncate if expected_count is provided
    if expected_count and len(matches) > expected_count:
        matches = matches[:expected_count]
        
    return matches


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Calculate aggregate rankings across all models.

    Args:
        stage2_results: Rankings from each model
        label_to_model: Mapping from anonymous labels to model names

    Returns:
        List of dicts with model name and average rank, sorted best to worst
    """
    from collections import defaultdict

    # Track positions for each model
    model_positions = defaultdict(list)

    for ranking in stage2_results:
        ranking_text = ranking['ranking']

        # Parse the ranking from the structured format
        expected_count = len(label_to_model)
        valid_labels = list(label_to_model.keys())
        parsed_ranking = parse_ranking_from_text(
            ranking_text,
            expected_count=expected_count,
            valid_labels=valid_labels,
        )

        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_model:
                model_name = label_to_model[label]
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
