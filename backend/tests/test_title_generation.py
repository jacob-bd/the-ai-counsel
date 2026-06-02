from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.council import (
    clean_generated_short_text,
    generate_conversation_title,
    generate_search_query,
    stage3_synthesize_final,
    strip_thinking_blocks,
)


def test_clean_generated_short_text_strips_complete_think_block_before_truncation():
    title = clean_generated_short_text(
        "<think>The user wants a 3-stage council comparison.</think>\n\nModel Metrics Matrix"
    )

    assert title == "Model Metrics Matrix"


def test_clean_generated_short_text_falls_back_when_think_block_is_unclosed():
    title = clean_generated_short_text(
        "<think>The user wants a 3-stage council comparison.",
        fallback="Why is the matrix truncated?",
    )

    assert title == "Why is the matrix truncated?"


def test_clean_generated_short_text_removes_title_prefix_quotes_and_punctuation():
    assert clean_generated_short_text('"Title: Council Matrix Layout."') == "Council Matrix Layout"


def test_strip_thinking_blocks_removes_complete_and_unclosed_markup():
    assert strip_thinking_blocks("<think>hidden</think>\n\nVisible answer") == "Visible answer"
    assert strip_thinking_blocks("<think>hidden only") == ""


@pytest.mark.asyncio
async def test_generate_conversation_title_sanitizes_reasoning_output():
    with (
        patch("backend.council.get_chairman_model", return_value="openai:gpt-4.1"),
        patch("backend.council.query_model", new_callable=AsyncMock) as mock_query,
    ):
        mock_query.return_value = {
            "error": False,
            "content": "<think>Need a concise title.</think>\n\nMatrix Scaling Fix",
        }

        title = await generate_conversation_title("Why is the matrix truncated?")

    assert title == "Matrix Scaling Fix"


@pytest.mark.asyncio
async def test_generate_search_query_sanitizes_reasoning_output():
    with (
        patch("backend.council.get_chairman_model", return_value="openai:gpt-4.1"),
        patch("backend.council.query_model", new_callable=AsyncMock) as mock_query,
    ):
        mock_query.return_value = {
            "error": False,
            "content": "<think>Need search terms.</think>\n\nCSS sticky table horizontal scroll",
        }

        query = await generate_search_query("How do I make a wide table usable?")

    assert query == "CSS sticky table horizontal scroll"


@pytest.mark.asyncio
async def test_stage3_synthesis_sanitizes_chairman_thinking_markup():
    with (
        patch("backend.council.get_chairman_model", return_value="opencode-zen:minimax-m3-free"),
        patch("backend.council.query_model", new_callable=AsyncMock) as mock_query,
    ):
        mock_query.return_value = {
            "error": False,
            "content": "<think>Need to synthesize privately.</think>\n\nFinal answer.",
            "usage": {"total_tokens": 10},
            "cost": {"total_cost": 0},
        }

        result = await stage3_synthesize_final(
            "Question",
            [{"model": "google:gemini-3.5-flash", "response": "Answer", "error": False}],
            [{"model": "google:gemini-3.5-flash", "ranking": "FINAL RANKING:\n1. Response A"}],
        )

    assert result["response"] == "Final answer."
    assert "<think>" not in result["response"]


@pytest.mark.asyncio
async def test_stage3_synthesis_does_not_prepend_reasoning_when_content_exists():
    with (
        patch("backend.council.get_chairman_model", return_value="opencode-zen:minimax-m3-free"),
        patch("backend.council.query_model", new_callable=AsyncMock) as mock_query,
    ):
        mock_query.return_value = {
            "error": False,
            "content": "Final answer.",
            "reasoning": "Private reasoning should not be shown.",
            "usage": {"total_tokens": 10},
            "cost": {"total_cost": 0},
        }

        result = await stage3_synthesize_final(
            "Question",
            [{"model": "google:gemini-3.5-flash", "response": "Answer", "error": False}],
            [{"model": "google:gemini-3.5-flash", "ranking": "FINAL RANKING:\n1. Response A"}],
        )

    assert result["response"] == "Final answer."
