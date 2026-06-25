"""Tests for iterative debate logic."""
import pytest

from backend.council import EvaluationError
from backend.debate import (
    check_convergence, truncate_text,
    pre_segment_paragraphs, format_numbered_paragraphs,
    aggregate_claim_verdicts, select_top_claims_for_model,
    format_claim_verdicts_for_prompt, format_contested_claims_for_stage4,
    _parse_claim_verdicts_from_ranking,
)

MAX_DEBATE_ROUNDS = 5


class TestConvergence:
    def test_stable_top_half(self):
        prev = [{"model": "a", "average_rank": 1.0}, {"model": "b", "average_rank": 2.0},
                {"model": "c", "average_rank": 3.0}, {"model": "d", "average_rank": 4.0}]
        curr = [{"model": "a", "average_rank": 1.2}, {"model": "b", "average_rank": 1.8},
                {"model": "d", "average_rank": 3.0}, {"model": "c", "average_rank": 4.0}]
        assert check_convergence(curr, prev) is True

    def test_unstable(self):
        prev = [{"model": "a", "average_rank": 1.0}, {"model": "b", "average_rank": 2.0},
                {"model": "c", "average_rank": 3.0}]
        curr = [{"model": "c", "average_rank": 1.0}, {"model": "a", "average_rank": 2.0},
                {"model": "b", "average_rank": 3.0}]
        assert check_convergence(curr, prev) is False

    def test_empty(self):
        assert check_convergence([], [{"model": "a", "average_rank": 1.0}]) is False
        assert check_convergence([{"model": "a", "average_rank": 1.0}], []) is False

    def test_single_model(self):
        assert check_convergence(
            [{"model": "a", "average_rank": 1.0}],
            [{"model": "a", "average_rank": 1.0}]
        ) is True

    def test_model_dropped(self):
        prev = [{"model": "a", "average_rank": 1.0}, {"model": "b", "average_rank": 2.0},
                {"model": "c", "average_rank": 3.0}]
        curr = [{"model": "a", "average_rank": 1.0}, {"model": "b", "average_rank": 2.0}]
        assert check_convergence(curr, prev) is True

    def test_no_common_models(self):
        prev = [{"model": "a", "average_rank": 1.0}]
        curr = [{"model": "x", "average_rank": 1.0}]
        assert check_convergence(curr, prev) is False

    def test_one_common_model(self):
        prev = [{"model": "a", "average_rank": 1.0}, {"model": "b", "average_rank": 2.0}]
        curr = [{"model": "a", "average_rank": 1.0}, {"model": "x", "average_rank": 2.0}]
        assert check_convergence(curr, prev) is True


class TestTruncateText:
    def test_short(self):
        assert truncate_text("hello", 100) == "hello"

    def test_long(self):
        text = "a" * 200
        result = truncate_text(text, 100)
        assert "[...truncated...]" in result
        assert result.startswith("a" * 50)
        assert result.endswith("a" * 50)

    def test_none(self):
        assert truncate_text(None, 100) == ""

    def test_empty(self):
        assert truncate_text("", 100) == ""


class TestParagraphSegmentation:
    def test_basic_split(self):
        text = "Para one.\n\nPara two.\n\nPara three."
        assert len(pre_segment_paragraphs(text)) == 3

    def test_empty(self):
        assert pre_segment_paragraphs("") == []
        assert pre_segment_paragraphs(None) == []

    def test_single_paragraph(self):
        assert pre_segment_paragraphs("Just one paragraph.") == ["Just one paragraph."]

    def test_strips_whitespace(self):
        text = "  First.  \n\n  Second.  "
        result = pre_segment_paragraphs(text)
        assert result == ["First.", "Second."]

    def test_numbered_format(self):
        text = "First paragraph.\n\nSecond paragraph."
        result = format_numbered_paragraphs(text)
        assert "[Para 1]" in result
        assert "[Para 2]" in result
        assert "First paragraph." in result

    def test_numbered_format_empty(self):
        assert format_numbered_paragraphs("") == ""
        assert format_numbered_paragraphs(None) == ""


class TestClaimAggregation:
    def test_majority_verdict(self):
        results = [
            {"claim_verdicts": {"A1": {"verdict": "strong"}, "A2": {"verdict": "flawed"}}},
            {"claim_verdicts": {"A1": {"verdict": "strong"}, "A2": {"verdict": "flawed"}}},
            {"claim_verdicts": {"A1": {"verdict": "weak"}, "A2": {"verdict": "flawed"}}},
        ]
        agg = aggregate_claim_verdicts(results)
        assert agg["A1"]["majority_verdict"] == "strong"
        assert agg["A1"]["agreement"] == round(2/3, 2)
        assert agg["A2"]["majority_verdict"] == "flawed"
        assert agg["A2"]["agreement"] == 1.0

    def test_empty_results(self):
        assert aggregate_claim_verdicts([]) == {}

    def test_missing_claim_verdicts(self):
        results = [
            {"model": "a", "ranking": "text"},
            {"model": "b", "claim_verdicts": {"A1": {"verdict": "strong"}}},
        ]
        agg = aggregate_claim_verdicts(results)
        assert "A1" in agg
        assert agg["A1"]["majority_verdict"] == "strong"


class TestCrossPollination:
    def test_selects_strong_from_others(self):
        canonical = {
            "Response A": [{"id": "A1", "claim": "claim a1"}],
            "Response B": [{"id": "B1", "claim": "claim b1"}, {"id": "B2", "claim": "claim b2"}],
        }
        verdicts = {
            "A1": {"majority_verdict": "flawed", "agreement": 1.0},
            "B1": {"majority_verdict": "strong", "agreement": 0.75},
            "B2": {"majority_verdict": "weak", "agreement": 0.5},
        }
        label_to_model = {"Response A": "model_a", "Response B": "model_b"}

        top = select_top_claims_for_model(canonical, verdicts, "model_a", label_to_model)
        assert len(top) == 1
        assert top[0]["id"] == "B1"

    def test_excludes_own_claims(self):
        canonical = {
            "Response A": [{"id": "A1", "claim": "strong own claim"}],
        }
        verdicts = {"A1": {"majority_verdict": "strong", "agreement": 1.0}}
        label_to_model = {"Response A": "model_a"}

        top = select_top_claims_for_model(canonical, verdicts, "model_a", label_to_model)
        assert len(top) == 0

    def test_max_claims_limit(self):
        canonical = {
            "Response B": [
                {"id": f"B{i}", "claim": f"claim {i}"} for i in range(10)
            ],
        }
        verdicts = {
            f"B{i}": {"majority_verdict": "strong", "agreement": 0.8}
            for i in range(10)
        }
        label_to_model = {"Response A": "model_a", "Response B": "model_b"}

        top = select_top_claims_for_model(canonical, verdicts, "model_a", label_to_model, max_claims=3)
        assert len(top) == 3


class TestStage3ClaimMetadata:
    def test_authoritative_count_and_all_claims_are_formatted(self):
        canonical = {
            "Response A": [{"id": "A1", "claim": "Claim one"}],
            "Response B": [{"id": "B1", "claim": "Claim two"}],
        }
        aggregated = {
            "A1": {"majority_verdict": "strong", "agreement": 1.0, "verdicts": {"strong": 4}},
            "B1": {"majority_verdict": "flawed", "agreement": 0.75, "verdicts": {"flawed": 3, "strong": 1}},
        }
        text = format_claim_verdicts_for_prompt(canonical, aggregated)
        assert "claims_evaluated: 2" in text
        assert "A1" in text
        assert "B1" in text
        assert '"flawed": 3' in text

    def test_stage4_context_excludes_strong_claims(self):
        canonical = {
            "Response A": [
                {"id": "A1", "claim": "Keep this"},
                {"id": "A2", "claim": "Fix this"},
            ]
        }
        aggregated = {
            "A1": {"majority_verdict": "strong", "agreement": 1.0, "verdicts": {"strong": 4}},
            "A2": {"majority_verdict": "flawed", "agreement": 0.75, "verdicts": {"flawed": 3, "strong": 1}},
        }
        stage2 = [{"claim_verdicts": {"A2": {"reason": "The amount is unsupported."}}}]
        text = format_contested_claims_for_stage4(canonical, aggregated, stage2)
        assert "A2" in text
        assert "The amount is unsupported." in text
        assert "A1" not in text


class TestClaimVerdictParsing:
    def test_accepts_complete_substantive_claim_verdicts(self):
        text = '''```json
{"A1":{"verdict":"strong","reason":"The payment deadline is stated directly in the supplied contract."},"A2":{"verdict":"weak","reason":"The conclusion is plausible but needs a defined notice period."}}
```
FINAL RANKING:
1. Response A
2. Response B'''
        parsed = _parse_claim_verdicts_from_ranking(text, ["A1", "A2"])
        assert parsed["A1"]["verdict"] == "strong"
        assert parsed["A2"]["verdict"] == "weak"

    def test_rejects_tautological_claim_reasons(self):
        text = '{"A1":{"verdict":"strong","reason":"Accurately reflects the claim in GPT 5.5."}}'
        with pytest.raises(EvaluationError, match="boilerplate"):
            _parse_claim_verdicts_from_ranking(text, ["A1"])

    def test_rejects_missing_claim_ids(self):
        text = '{"A1":{"verdict":"strong","reason":"The clause expressly provides a thirty-day payment deadline."}}'
        with pytest.raises(EvaluationError, match="Claim IDs"):
            _parse_claim_verdicts_from_ranking(text, ["A1", "A2"])
