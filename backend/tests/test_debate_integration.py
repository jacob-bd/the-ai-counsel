"""Integration tests for iterative debate orchestration."""
import pytest
from unittest.mock import patch, MagicMock
from backend.debate import run_iterative_debate


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.debate_rounds = 2
    s.auto_converge = True
    s.convergence_threshold = 2
    s.critique_mode = "freeform"
    s.council_temperature = 0.5
    s.stage2_temperature = 0.3
    s.chairman_temperature = 0.4
    s.stage1_prompt = None
    s.stage2_prompt = None
    s.stage3_prompt = None
    s.council_models = ["model_a", "model_b"]
    return s


def _fake_stage1(*args, **kwargs):
    async def gen():
        yield 2
        yield {"model": "model_a", "response": "Answer A", "error": None}
        yield {"model": "model_b", "response": "Answer B", "error": None}
    return gen()


def _fake_stage2(*args, **kwargs):
    async def gen():
        yield {"Response A": "model_a", "Response B": "model_b"}
        yield {"model": "model_a", "ranking": "1. Response A\n2. Response B\n\nFINAL RANKING:\n1. Response A\n2. Response B", "parsed_ranking": ["Response A", "Response B"], "error": None}
        yield {"model": "model_b", "ranking": "1. Response A\n2. Response B\n\nFINAL RANKING:\n1. Response A\n2. Response B", "parsed_ranking": ["Response A", "Response B"], "error": None}
    return gen()


@pytest.mark.asyncio
async def test_two_rounds_yields_correct_events(mock_settings):
    """Two-round full mode yields round_start/complete for each round plus debate_complete."""
    with patch("backend.debate.get_settings", return_value=mock_settings), \
         patch("backend.debate.stage1_collect_responses", side_effect=_fake_stage1), \
         patch("backend.debate.stage2_collect_rankings", side_effect=_fake_stage2), \
         patch("backend.debate.stage3_synthesize_final", return_value={"model": "chair", "response": "Synthesis", "error": False}), \
         patch("backend.debate.get_council_models", return_value=["model_a", "model_b"]):

        events = []
        async for event in run_iterative_debate("test?", "", None, "full", debate_rounds=2):
            events.append(event)

        types = [e["type"] for e in events]
        assert types.count("round_start") == 2
        assert types.count("round_complete") == 2
        assert types.count("stage3_complete") == 2
        assert "debate_complete" in types

        dc = next(e for e in events if e["type"] == "debate_complete")
        assert len(dc["rounds"]) == 2


@pytest.mark.asyncio
async def test_chat_only_forces_single_round(mock_settings):
    """chat_only mode forces debate_rounds to 1 regardless of setting."""
    with patch("backend.debate.get_settings", return_value=mock_settings), \
         patch("backend.debate.stage1_collect_responses", side_effect=_fake_stage1):

        events = []
        async for event in run_iterative_debate("test?", "", None, "chat_only", debate_rounds=3):
            events.append(event)

        types = [e["type"] for e in events]
        assert types.count("round_start") == 1


@pytest.mark.asyncio
async def test_convergence_stops_early(mock_settings):
    """Identical rankings across rounds trigger early convergence."""
    mock_settings.debate_rounds = 5
    mock_settings.convergence_threshold = 1

    with patch("backend.debate.get_settings", return_value=mock_settings), \
         patch("backend.debate.stage1_collect_responses", side_effect=_fake_stage1), \
         patch("backend.debate.stage2_collect_rankings", side_effect=_fake_stage2), \
         patch("backend.debate.stage3_synthesize_final", return_value={"model": "chair", "response": "Final", "error": False}):

        events = []
        async for event in run_iterative_debate("test?", "", None, "full", debate_rounds=5):
            events.append(event)

        types = [e["type"] for e in events]
        assert types.count("round_start") == 2
        assert "convergence" in types


@pytest.mark.asyncio
async def test_all_models_fail_stops(mock_settings):
    """All models failing in Stage 1 yields error and stops."""
    def _fail_stage1(*args, **kwargs):
        async def gen():
            yield 2
            yield {"model": "model_a", "response": None, "error": True, "error_message": "timeout"}
            yield {"model": "model_b", "response": None, "error": True, "error_message": "timeout"}
        return gen()

    with patch("backend.debate.get_settings", return_value=mock_settings), \
         patch("backend.debate.stage1_collect_responses", side_effect=_fail_stage1):

        events = []
        async for event in run_iterative_debate("test?", "", None, "full", debate_rounds=2):
            events.append(event)

        types = [e["type"] for e in events]
        assert "error" in types
        assert "debate_complete" not in types


@pytest.mark.asyncio
async def test_chat_ranking_with_rounds(mock_settings):
    """chat_ranking mode runs Stage 1+2 without Stage 3."""
    with patch("backend.debate.get_settings", return_value=mock_settings), \
         patch("backend.debate.stage1_collect_responses", side_effect=_fake_stage1), \
         patch("backend.debate.stage2_collect_rankings", side_effect=_fake_stage2):

        events = []
        async for event in run_iterative_debate("test?", "", None, "chat_ranking", debate_rounds=2):
            events.append(event)

        types = [e["type"] for e in events]
        assert types.count("round_start") == 2
        assert "stage3_complete" not in types
        assert "debate_complete" in types


@pytest.mark.asyncio
async def test_partial_model_failure_round2(mock_settings):
    """One model failing in round 2 doesn't stop the debate (other model succeeded)."""
    call_count = [0]
    def _stage1_with_failure(*args, **kwargs):
        call_count[0] += 1
        async def gen():
            yield 2
            if call_count[0] == 1:
                yield {"model": "model_a", "response": "A1", "error": None}
                yield {"model": "model_b", "response": "B1", "error": None}
            else:
                yield {"model": "model_a", "response": "A2", "error": None}
                yield {"model": "model_b", "response": None, "error": True, "error_message": "timeout"}
        return gen()

    with patch("backend.debate.get_settings", return_value=mock_settings), \
         patch("backend.debate.stage1_collect_responses", side_effect=_stage1_with_failure), \
         patch("backend.debate.stage2_collect_rankings", side_effect=_fake_stage2), \
         patch("backend.debate.stage3_synthesize_final", return_value={"model": "chair", "response": "OK", "error": False}):

        events = []
        async for event in run_iterative_debate("test?", "", None, "full", debate_rounds=2):
            events.append(event)

        types = [e["type"] for e in events]
        assert types.count("round_complete") == 2


@pytest.mark.asyncio
async def test_debate_rounds_param_overrides_settings(mock_settings):
    """debate_rounds param takes precedence over settings.debate_rounds."""
    mock_settings.debate_rounds = 5

    with patch("backend.debate.get_settings", return_value=mock_settings), \
         patch("backend.debate.stage1_collect_responses", side_effect=_fake_stage1), \
         patch("backend.debate.stage2_collect_rankings", side_effect=_fake_stage2), \
         patch("backend.debate.stage3_synthesize_final", return_value={"model": "chair", "response": "OK", "error": False}):

        events = []
        async for event in run_iterative_debate("test?", "", None, "full", debate_rounds=2):
            events.append(event)

        dc = next(e for e in events if e["type"] == "debate_complete")
        assert dc["total_rounds_executed"] == 2


@pytest.mark.asyncio
async def test_final_round_uses_prompt_override(mock_settings):
    """Final round calls stage3_synthesize_final with prompt_override set."""
    with patch("backend.debate.get_settings", return_value=mock_settings), \
         patch("backend.debate.stage1_collect_responses", side_effect=_fake_stage1), \
         patch("backend.debate.stage2_collect_rankings", side_effect=_fake_stage2), \
         patch("backend.debate.stage3_synthesize_final", return_value={"model": "chair", "response": "Final", "error": False}) as mock_s3:

        events = []
        async for event in run_iterative_debate("test?", "", None, "full", debate_rounds=2):
            events.append(event)

        # 2 rounds of Stage 3 + 1 Stage 4 corrected draft = 3 calls
        assert mock_s3.call_count == 3
        # The second call (final round Stage 3) should have prompt_override
        final_round_call = mock_s3.call_args_list[1]
        assert final_round_call.kwargs.get("prompt_override") is not None
        # The third call (Stage 4 corrected draft) should also have prompt_override
        stage4_call = mock_s3.call_args_list[2]
        assert stage4_call.kwargs.get("prompt_override") is not None
