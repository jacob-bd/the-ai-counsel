"""Tests for iterative debate logic."""
from backend.debate import (
    check_convergence, truncate_text,
    pre_segment_paragraphs, format_numbered_paragraphs,
    aggregate_claim_verdicts, select_top_claims_for_model,
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
