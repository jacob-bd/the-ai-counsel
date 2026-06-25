"""Regression tests for Stage 2 prompt overrides and anonymous ranking labels."""
from types import SimpleNamespace

import pytest

from backend import council


@pytest.mark.asyncio
async def test_prompt_override_receives_anonymous_label_contract(monkeypatch):
    captured_prompts = []

    settings = SimpleNamespace(
        response_language="English",
        stage2_prompt="",
        stage2_temperature=0.3,
        model_timeout_seconds=5,
        notion2api_firing_mode="rapid_fire",
        notion2api_sequential_max_concurrent=3,
        notion2api_pause_on_failure=False,
    )

    async def fake_query_model(model, messages, **kwargs):
        captured_prompts.append(messages[-1]["content"])
        return {
            "content": "{}\nFINAL RANKING:\n1. Response A\n2. Response B",
            "error": False,
        }

    monkeypatch.setattr(council, "get_settings", lambda: settings)
    monkeypatch.setattr(council, "query_model", fake_query_model)

    stage1_results = [
        {"model": "openai:model-a", "response": "First answer", "error": None},
        {"model": "openai:model-b", "response": "Second answer", "error": None},
    ]

    items = []
    async for item in council.stage2_collect_rankings(
        "Question",
        stage1_results,
        prompt_override="Evaluate the supplied claims.",
    ):
        items.append(item)

    assert len(captured_prompts) == 2
    for prompt in captured_prompts:
        assert "CRITICAL OUTPUT CONTRACT" in prompt
        assert "Response A, Response B" in prompt
        assert "Do not identify, infer, mention, or rank model/provider names" in prompt

    results = [item for item in items if isinstance(item, dict) and item.get("model")]
    assert all(result["parsed_ranking"] == ["Response A", "Response B"] for result in results)


@pytest.mark.asyncio
async def test_stage2_retries_truncated_output_with_compact_ranking_prompt(monkeypatch):
    calls = []
    per_model_calls = {}
    settings = SimpleNamespace(
        response_language="English",
        stage2_prompt="",
        stage2_temperature=0.2,
        stage2_max_output_tokens=16000,
        model_timeout_seconds=5,
        notion2api_firing_mode="rapid_fire",
        notion2api_sequential_max_concurrent=3,
        notion2api_pause_on_failure=False,
    )

    async def fake_query_model(model, messages, **kwargs):
        calls.append((model, messages[-1]["content"], kwargs))
        count = per_model_calls.get(model, 0) + 1
        per_model_calls[model] = count
        if count == 1:
            return {
                "content": "Detailed audit that ended before the ranking.",
                "finish_reason": "length",
                "error": False,
            }
        return {
            "content": "FINAL RANKING:\n1. Response B\n2. Response A",
            "finish_reason": "stop",
            "error": False,
        }

    monkeypatch.setattr(council, "get_settings", lambda: settings)
    monkeypatch.setattr(council, "query_model", fake_query_model)

    stage1_results = [
        {"model": "notion2api:model-a", "response": "First answer", "error": None},
        {"model": "notion2api:model-b", "response": "Second answer", "error": None},
    ]
    items = []
    async for item in council.stage2_collect_rankings(
        "Question",
        stage1_results,
        conversation_id="conversation-1",
    ):
        items.append(item)

    results = [item for item in items if isinstance(item, dict) and item.get("model")]
    assert len(results) == 2
    assert all(result["error"] is None for result in results)
    assert all(result["recovered_after_retry"] is True for result in results)
    assert all(result["parsed_ranking"] == ["Response B", "Response A"] for result in results)
    assert all(result["attempts"][0]["status"] == "truncated_evaluator_output" for result in results)
    assert all(result["max_output_tokens"] == 16000 for result in results)
    assert len(calls) == 4
    assert all(call[2]["max_output_tokens"] == 16000 for call in calls)
    retry_prompts = [prompt for _, prompt, _ in calls if "RECOVERY RETRY" in prompt]
    assert len(retry_prompts) == 2
    assert all("Return ONLY the complete ranking block" in prompt for prompt in retry_prompts)
