import pytest

from backend import costs


@pytest.mark.asyncio
async def test_openrouter_reported_cost_is_preserved():
    response = {
        "content": "ok",
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "cost": 0.00012345,
        },
    }

    result = await costs.attach_cost("openrouter:openai/gpt-4o-mini", response)

    assert result["usage"]["reported_cost"] == 0.00012345
    assert result["cost"]["total_cost"] == 0.00012345
    assert result["cost"]["reported_total_cost"] == 0.00012345
    assert result["cost"]["cost_status"] == "known"
    assert result["cost"]["pricing_source"] == "provider:openrouter_usage"


@pytest.mark.asyncio
async def test_unprefixed_openrouter_free_model_reports_zero():
    model = "meta-llama/llama-3.3-70b-instruct:free"

    assert costs.provider_for_model(model) == "openrouter"

    cost = await costs.estimate_call_cost(
        model,
        {"prompt_tokens": 50, "completion_tokens": 25},
    )

    assert cost["total_cost"] == 0.0
    assert cost["cost_status"] == "free"
    assert cost["pricing_source"] == "free:openrouter"


@pytest.mark.asyncio
async def test_ollama_usage_reports_zero_cost():
    cost = await costs.estimate_call_cost(
        "ollama:llama3.1:latest",
        {"prompt_eval_count": 12, "eval_count": 8},
    )

    assert cost["input_tokens"] == 12
    assert cost["output_tokens"] == 8
    assert cost["total_tokens"] == 20
    assert cost["total_cost"] == 0.0
    assert cost["pricing_source"] == "free:ollama"


@pytest.mark.asyncio
async def test_custom_opencode_endpoint_reports_zero(monkeypatch):
    class Settings:
        custom_endpoint_name = "OpenCode Go"
        custom_endpoint_url = "https://example.test/v1"

    from backend import settings as settings_module

    monkeypatch.setattr(settings_module, "get_settings", lambda: Settings())

    cost = await costs.estimate_call_cost(
        "custom:gpt-5.1",
        {"prompt_tokens": 100, "completion_tokens": 50},
    )

    assert cost["total_cost"] == 0.0
    assert cost["cost_status"] == "free"
    assert cost["pricing_source"] == "free:opencode"


@pytest.mark.asyncio
async def test_catalog_estimate_and_council_summary(monkeypatch):
    async def fake_pricing(provider, native_id, input_tokens):
        return {
            "input_cost_per_1m": 1.0,
            "output_cost_per_1m": 2.0,
            "cached_input_cost_per_1m": 0.25,
            "source": "catalog:test",
            "source_url": "https://pricing.example.test",
            "confidence": "high",
        }

    monkeypatch.setattr(costs, "_resolve_catalog_pricing", fake_pricing)

    paid_call = await costs.estimate_call_cost(
        "openai:gpt-test",
        {"input_tokens": 1000, "output_tokens": 500},
    )
    free_call = await costs.estimate_call_cost(
        "nvidia:nemotron-test",
        {"prompt_tokens": 200, "completion_tokens": 100},
    )

    report = costs.build_council_cost_report(
        stage1=[
            {"model": "openai:gpt-test", "cost": paid_call},
            {"model": "nvidia:nemotron-test", "cost": free_call},
        ],
    )

    assert paid_call["total_cost"] == 0.002
    assert report["total_cost"] == 0.002
    assert report["total_calls"] == 2
    assert report["estimated_calls"] == 1
    assert report["free_calls"] == 1
    assert report["by_model"][0]["name"] == "openai:gpt-test"


def test_advisor_cost_report_includes_errors_and_extracts():
    known = {
        "model": "openai:gpt-test",
        "total_tokens": 20,
        "total_cost": 0.001,
        "cost_status": "estimated",
        "is_estimate": True,
    }
    unknown = {
        "model": "custom:unknown-model",
        "total_tokens": 30,
        "total_cost": None,
        "cost_status": "unknown",
        "is_estimate": True,
    }
    free = {
        "model": "ollama:llama3.1",
        "total_tokens": 40,
        "total_cost": 0.0,
        "cost_status": "free",
        "is_estimate": False,
    }

    report = costs.build_advisor_cost_report(
        rounds=[{
            "round_number": 1,
            "responses": [
                {"persona_id": "skeptic", "persona_name": "Skeptic", "cost": known},
                {"persona_id": "pragmatist", "persona_name": "Pragmatist", "error": "timeout", "cost": unknown},
            ],
        }],
        round_extracts=[{"model": "ollama:llama3.1", "cost": free}],
    )

    assert report["total_calls"] == 3
    assert report["total_cost"] == 0.001
    assert report["unknown_cost_calls"] == 1
    assert report["free_calls"] == 1
    assert report["by_stage"][0]["name"] == "advisor_extract"


@pytest.mark.asyncio
async def test_opencode_zen_free_model_reports_zero():
    cost = await costs.estimate_call_cost(
        "opencode-zen:big-pickle",
        {"prompt_tokens": 200, "completion_tokens": 100},
    )
    assert cost["total_cost"] == 0.0
    assert cost["cost_status"] == "free"
    assert cost["pricing_source"] == "free:opencode"


@pytest.mark.asyncio
async def test_opencode_zen_paid_model_uses_hardcoded_pricing():
    cost = await costs.estimate_call_cost(
        "opencode-zen:glm-5.1",
        {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000},
    )
    # $1.40 / $4.40 per 1M => 1.40 + 4.40 = 5.80
    assert cost["total_cost"] == 5.80
    assert cost["cost_status"] == "estimated"
    assert cost["pricing_source"] == "table:opencode"
    assert cost["input_cost_per_1m"] == 1.40
    assert cost["output_cost_per_1m"] == 4.40


@pytest.mark.asyncio
async def test_opencode_go_subscription_model_includes_note():
    cost = await costs.estimate_call_cost(
        "opencode-go:glm-5",
        {"prompt_tokens": 100, "completion_tokens": 50},
    )
    assert cost["pricing_source"] == "table:opencode"
    assert cost["cost_status"] == "estimated"
    assert any("subscription" in n for n in cost["notes"])


@pytest.mark.asyncio
async def test_opencode_unknown_model_marks_unknown():
    cost = await costs.estimate_call_cost(
        "opencode-zen:gpt-5-future-model",
        {"prompt_tokens": 100, "completion_tokens": 50},
    )
    assert cost["total_cost"] is None
    assert cost["cost_status"] == "unknown"
    assert cost["pricing_source"] is None
    assert any("hardcoded pricing table" in n for n in cost["notes"])


def test_opencode_provider_prefix_is_recognized():
    assert costs.provider_for_model("opencode-zen:glm-5") == "opencode-zen"
    assert costs.provider_for_model("opencode-go:kimi-k2.5") == "opencode-go"
    assert costs.provider_model_id("opencode-zen:glm-5") == "glm-5"
