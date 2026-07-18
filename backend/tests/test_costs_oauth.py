"""Subscription OAuth cost attribution."""

import pytest

from backend.costs import _is_zero_cost_model


def test_oauth_prefixes_are_free():
    for provider in ("xai-oauth", "openai-oauth", "github-copilot"):
        ok, source = _is_zero_cost_model(f"{provider}:model", provider)
        assert ok is True
        assert source == "free:subscription"


@pytest.mark.asyncio
async def test_estimate_call_cost_subscription_note():
    from backend.costs import estimate_call_cost

    result = await estimate_call_cost(
        "openai-oauth:gpt-5",
        {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )
    assert result.get("cost_status") == "free"
    assert result.get("total_cost") == 0.0
    notes = result.get("notes") or []
    assert any("subscription" in n.lower() for n in notes)
