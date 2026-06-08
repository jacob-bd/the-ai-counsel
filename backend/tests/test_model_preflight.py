from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.model_preflight import build_preflight_error_message, preflight_models


@pytest.mark.asyncio
async def test_preflight_reports_immediate_model_failure():
    with patch("backend.model_preflight.query_model", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {
            "error": True,
            "error_message": "NVIDIA API error: 401 - unauthorized",
        }

        result = await preflight_models(["nvidia:missing-access"], timeout=5.0)

    assert result.ok is False
    assert result.failures == [
        {
            "model": "nvidia:missing-access",
            "error": "NVIDIA API error: 401 - unauthorized",
        }
    ]
    assert "nvidia:missing-access" in build_preflight_error_message(result)
    assert "401" in build_preflight_error_message(result)


@pytest.mark.asyncio
async def test_preflight_does_not_block_on_timeout():
    with patch("backend.model_preflight.query_model", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {
            "error": True,
            "error_message": "Request timed out after 5s",
        }

        result = await preflight_models(["openrouter:slow-model"], timeout=5.0)

    assert result.ok is True
    assert result.failures == []
    assert result.timeouts == ["openrouter:slow-model"]


@pytest.mark.asyncio
async def test_preflight_deduplicates_models_before_querying():
    with patch("backend.model_preflight.query_model", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {"error": False, "content": "OK"}

        result = await preflight_models(["openai:GPT-4.1", "openai:gpt-4.1", ""], timeout=5.0)

    assert result.ok is True
    assert mock_query.await_count == 1
    assert mock_query.call_args[0][0] == "openai:GPT-4.1"


@pytest.mark.asyncio
async def test_preflight_semaphore_does_not_change_behavior():
    with patch("backend.model_preflight.query_model", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {"error": False, "content": "OK"}

        models = [f"openai:gpt-{i}" for i in range(10)]
        result = await preflight_models(models, timeout=5.0)

    assert result.ok is True
    assert mock_query.call_count == 10


def test_is_transient_rate_limit_classification():
    from backend.model_preflight import _is_transient_rate_limit

    # Status code 429 is always rate limit
    assert _is_transient_rate_limit(429, "Any message") is True
    # Status code 503 is only soft-failed when the body indicates transient congestion
    assert _is_transient_rate_limit(503, "Service Unavailable") is False
    assert _is_transient_rate_limit(503, "temporary endpoint congestion") is True
    assert _is_transient_rate_limit(503, "rate limit from upstream") is True

    # Standard substrings are rate limit
    assert _is_transient_rate_limit(400, "rate limit exceeded") is True
    assert _is_transient_rate_limit(500, "Too Many Requests") is True
    assert _is_transient_rate_limit(0, "API quota exhausted") is True
    assert _is_transient_rate_limit(0, "Throttled request") is True

    # Genuine errors are not rate limits
    assert _is_transient_rate_limit(401, "unauthorized access") is False
    assert _is_transient_rate_limit(404, "model not found") is False
    assert _is_transient_rate_limit(500, "internal server error") is False


@pytest.mark.asyncio
async def test_preflight_soft_fails_on_rate_limit():
    with patch("backend.model_preflight.query_model", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {
            "error": True,
            "error_message": "Rate limit exceeded (HTTP 429)",
            "debug_timeline": [{"status": 429}]
        }

        # Mock sleep to avoid waiting during retries
        with patch("backend.model_preflight.asyncio.sleep", new_callable=AsyncMock):
            result = await preflight_models(["openai:gpt-4o"], timeout=1.0)

    assert result.ok is True  # Allowed to proceed (soft-fail)
    assert result.failures == []
    assert result.rate_limited == ["openai:gpt-4o"]
    assert mock_query.call_count == 3  # Initial + 2 retries


@pytest.mark.asyncio
async def test_preflight_hard_fails_on_genuine_error():
    with patch("backend.model_preflight.query_model", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {
            "error": True,
            "error_message": "Model not found (HTTP 404)",
            "debug_timeline": [{"status": 404}]
        }

        result = await preflight_models(["openai:gpt-4o"], timeout=1.0)

    assert result.ok is False  # Genuine error (hard-fail)
    assert result.failures == [{"model": "openai:gpt-4o", "error": "Model not found (HTTP 404)"}]
    assert result.rate_limited == []
    assert mock_query.call_count == 1  # No retries for hard failures


@pytest.mark.asyncio
async def test_preflight_hard_fails_on_plain_503():
    with patch("backend.model_preflight.query_model", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {
            "error": True,
            "error_message": "Service Unavailable",
            "debug_timeline": [{"status": 503}]
        }

        result = await preflight_models(["custom:unstable-model"], timeout=1.0)

    assert result.ok is False
    assert result.failures == [{"model": "custom:unstable-model", "error": "Service Unavailable"}]
    assert result.rate_limited == []
    assert mock_query.call_count == 1

