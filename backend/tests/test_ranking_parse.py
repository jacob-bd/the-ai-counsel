"""Tests for Stage 2 ranking parse helpers."""

from backend.council import build_stage_texts, is_evaluator_refusal, parse_ranking_from_text


def test_parse_ranking_filters_hallucinated_labels():
    text = """Response A is strong.
Response B is weaker.

FINAL RANKING:
1. Response C
2. Response A
3. Response B"""

    parsed = parse_ranking_from_text(
        text,
        expected_count=2,
        valid_labels=["Response A", "Response B"],
    )

    assert parsed == ["Response A", "Response B"]


def test_parse_ranking_deduplicates_labels():
    text = """FINAL RANKING:
1. Response A
2. Response A
3. Response B"""

    parsed = parse_ranking_from_text(
        text,
        expected_count=2,
        valid_labels=["Response A", "Response B"],
    )

    assert parsed == ["Response A", "Response B"]


def test_parse_ranking_recovers_markdown_heading_and_parenthesized_numbers():
    text = """Response A is more complete, while Response B is more concise.

### **Final Ranking**
1) **Response B**
2) **Response A**"""

    parsed = parse_ranking_from_text(
        text,
        expected_count=2,
        valid_labels=["Response A", "Response B"],
    )

    assert parsed == ["Response B", "Response A"]


def test_parse_ranking_recovers_inline_freeform_order():
    text = """Both answers are useful, but B is more precise.

Overall ranking (best to worst): Response B > Response A"""

    parsed = parse_ranking_from_text(
        text,
        expected_count=2,
        valid_labels=["Response A", "Response B"],
    )

    assert parsed == ["Response B", "Response A"]


def test_parse_ranking_recovers_numbered_tail_without_heading():
    text = """Response A is thorough. Response B is more focused.

1. Response B
2. Response A"""

    parsed = parse_ranking_from_text(
        text,
        expected_count=2,
        valid_labels=["Response A", "Response B"],
    )

    assert parsed == ["Response B", "Response A"]


def test_build_stage_texts_excludes_failed_rankings():
    stage1 = [{"model": "model-a", "response": "Candidate answer"}]
    stage2 = [
        {"model": "model-a", "ranking": "Valid ranking", "error": None},
        {"model": "model-b", "ranking": "Malformed model-name ranking", "error": True},
    ]

    _, stage2_text = build_stage_texts(stage1, stage2)

    assert "Valid ranking" in stage2_text
    assert "Malformed model-name ranking" not in stage2_text


def test_detects_stage2_refusal_separately_from_format_error():
    refusal = """I cannot perform this task.

I am Notion AI, and my capabilities are strictly limited to Notion workspace operations.
I do not have tools or the ability to compare, analyze, or rank external candidate responses.
"""

    assert is_evaluator_refusal(refusal) is True
    assert is_evaluator_refusal("FINAL RANKING:\n1. Response B\n2. Response A") is False