"""Tests for Stage 2 aggregate ranking resilience."""

from backend.council import calculate_aggregate_rankings


LABEL_TO_MODEL = {
    "Response A": "model_a",
    "Response B": "model_b",
    "Response C": "model_c",
}


def _valid_ranking(order: str) -> str:
    labels = {
        "A": "Response A",
        "B": "Response B",
        "C": "Response C",
    }
    lines = [f"{index}. {labels[label]}" for index, label in enumerate(order, start=1)]
    return "FINAL RANKING:\n" + "\n".join(lines)


def test_one_failed_ranking_plus_valid_rankings():
    stage2_results = [
        {"model": "evaluator_1", "error": True, "error_message": "timeout"},
        {
            "model": "evaluator_2",
            "ranking": _valid_ranking("CAB"),
        },
        {
            "model": "evaluator_3",
            "ranking": _valid_ranking("BCA"),
        },
    ]

    aggregate = calculate_aggregate_rankings(stage2_results, LABEL_TO_MODEL)

    assert aggregate
    assert aggregate[0]["model"] == "model_c"
    assert all(item["rankings_count"] == 2 for item in aggregate)


def test_all_evaluators_fail_returns_empty_list():
    stage2_results = [
        {"model": "evaluator_1", "error": True},
        {"model": "evaluator_2", "ranking": "not a ranking"},
        {"model": "evaluator_3", "ranking": None},
        {"model": "evaluator_4", "ranking": "   "},
    ]

    assert calculate_aggregate_rankings(stage2_results, LABEL_TO_MODEL) == []


def test_malformed_ranking_is_skipped_without_exception():
    stage2_results = [
        {
            "model": "evaluator_1",
            "ranking": "FINAL RANKING:\n1. Response X\n2. Response Y",
        },
        {
            "model": "evaluator_2",
            "ranking": _valid_ranking("ABC"),
        },
    ]

    aggregate = calculate_aggregate_rankings(stage2_results, LABEL_TO_MODEL)

    assert len(aggregate) == 3
    assert aggregate[0]["rankings_count"] == 1
