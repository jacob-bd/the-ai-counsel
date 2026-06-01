"""OpenRouter API client for making LLM requests."""

import asyncio
import httpx
from typing import List, Dict, Any, Optional
from .config import get_openrouter_api_key, OPENROUTER_API_URL

# Retry configuration
MAX_RETRIES = 2
INITIAL_RETRY_DELAY = 1.0  # seconds

# Known broken/deprecated models that OpenRouter lists but don't actually work
BROKEN_MODELS = {
    "openai/gpt-oss-120b:free",   # Returns 404
    "openai/gpt-oss-20b:free",    # Returns 404
    "moonshotai/kimi-k2:free",    # Returns 404 - superseded by kimi-k2-0905
}


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
    temperature: float = 0.7
) -> Optional[Dict[str, Any]]:
    """
    Query a single model via OpenRouter API with retry logic for rate limits.

    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-4o")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds
        temperature: Model temperature

    Returns:
        Response dict with 'content', optional 'reasoning_details', and 'error' if failed
    """
    api_key = get_openrouter_api_key()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }

    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    OPENROUTER_API_URL,
                    headers=headers,
                    json=payload
                )

                # Handle rate limiting with retry
                if response.status_code == 429:
                    retry_delay = INITIAL_RETRY_DELAY * (2 ** attempt)
                    print(f"Rate limited on {model}, retrying in {retry_delay}s (attempt {attempt + 1}/{MAX_RETRIES})")
                    last_error = "rate_limited"
                    await asyncio.sleep(retry_delay)
                    continue

                # Handle other client errors without retry
                if response.status_code == 400:
                    error_detail = "bad_request"
                    try:
                        error_data = response.json()
                        error_detail = error_data.get("error", {}).get("message", "bad_request")
                    except:
                        pass
                    print(f"Bad request for {model}: {error_detail}")
                    return {
                        'content': None,
                        'error': 'bad_request',
                        'error_message': f"Model returned error: {error_detail}"
                    }

                response.raise_for_status()

                data = response.json()
                message = data['choices'][0]['message']

                return {
                    'content': message.get('content'),
                    'reasoning': message.get('reasoning'), # Capture reasoning field (common in DeepSeek R1/reasoning models)
                    'reasoning_details': message.get('reasoning_details'),
                    'usage': data.get('usage'),
                    'error': None
                }

        except httpx.HTTPStatusError as e:
            print(f"HTTP error querying model {model}: {e}")
            last_error = f"http_{e.response.status_code}"
        except httpx.RemoteProtocolError as e:
            # This handles "peer closed connection without sending complete message body"
            retry_delay = INITIAL_RETRY_DELAY * (2 ** attempt)
            print(f"Remote protocol error (disconnect) on {model}: {e}. Retrying in {retry_delay}s...")
            last_error = "protocol_error"
            await asyncio.sleep(retry_delay)
            continue
        except httpx.TimeoutException:
            print(f"Timeout querying model {model}")
            last_error = "timeout"
        except Exception as e:
            print(f"Error querying model {model}: {e}")
            last_error = str(e)
            break  # Don't retry on unknown errors

    # All retries exhausted or non-retryable error
    error_messages = {
        "rate_limited": "Rate limited - too many requests",
        "timeout": "Request timed out",
    }
    return {
        'content': None,
        'error': last_error,
        'error_message': error_messages.get(last_error, f"Error: {last_error}")
    }


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]],
    temperature: float = 0.7
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple models in parallel with batching for rate limit protection.
    
    For 6+ models, processes in batches of 3 to avoid hitting rate limits.

    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model

    Returns:
        Dict mapping model identifier to response dict (or None if failed)
    """
    import asyncio

    # For 6+ models, use batching to avoid rate limits
    BATCH_SIZE = 3
    if len(models) >= 6:
        print(f"Batching {len(models)} models into groups of {BATCH_SIZE} to avoid rate limits")
        results = {}
        
        # Process in batches
        for i in range(0, len(models), BATCH_SIZE):
            batch = models[i:i + BATCH_SIZE]
            print(f"Processing batch {i//BATCH_SIZE + 1}: {batch}")
            
            # Create tasks for this batch
            tasks = [query_model(model, messages, temperature=temperature) for model in batch]
            
            # Wait for batch to complete
            batch_responses = await asyncio.gather(*tasks)
            
            # Map batch results
            for model, response in zip(batch, batch_responses):
                results[model] = response
            
            # Small delay between batches (except for last batch)
            if i + BATCH_SIZE < len(models):
                await asyncio.sleep(0.5)
        
        return results
    
    # For 5 or fewer models, send all at once (original behavior)
    tasks = [query_model(model, messages, temperature=temperature) for model in models]

    # Wait for all to complete
    responses = await asyncio.gather(*tasks)

    # Map models to their responses
    return {model: response for model, response in zip(models, responses)}


async def fetch_models() -> List[Dict[str, Any]]:
    """
    Fetch available models from OpenRouter API.
    Returns a list of model definitions compatible with the frontend.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://openrouter.ai/api/v1/models")
            if response.status_code != 200:
                print(f"Failed to fetch OpenRouter models: {response.status_code}")
                return []
            
            data = response.json()
            models = []
            for item in data.get("data", []):
                model_id = item.get("id", "")
                
                # Skip known broken models
                if model_id in BROKEN_MODELS:
                    continue
                
                # Determine if free based on pricing
                pricing = item.get("pricing", {})
                is_free = (
                    float(pricing.get("prompt", 0)) == 0 and 
                    float(pricing.get("completion", 0)) == 0
                )
                
                # Extract provider from ID (e.g. "google/gemini" -> "Google")
                provider = "OpenRouter" # Default
                if "/" in model_id:
                    provider_slug = model_id.split("/")[0]
                    # Capitalize nicely
                    if provider_slug == "openai": provider = "OpenAI"
                    elif provider_slug == "anthropic": provider = "Anthropic"
                    elif provider_slug == "google": provider = "Google"
                    elif provider_slug == "meta-llama": provider = "Meta"
                    elif provider_slug == "mistralai": provider = "Mistral"
                    elif provider_slug == "deepseek": provider = "DeepSeek"
                    else: provider = provider_slug.title()
                
                models.append({
                    "id": model_id,
                    "name": item.get("name"),
                    "provider": provider, 
                    "source": "openrouter", # Explicitly set for frontend grouping
                    "context_length": item.get("context_length"),
                    "is_free": is_free,
                    "pricing": pricing
                })
            
            return models
    except Exception as e:
        print(f"Error fetching OpenRouter models: {e}")
        return []
