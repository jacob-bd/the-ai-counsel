import pytest
import json
import asyncio
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from backend.audit_pipeline import (
    _parse_audit_verdicts,
    run_audit_pipeline,
    normalize_and_deduplicate_claims,
    stage2a_collect_evaluations,
    stage2b_collect_audits,
    extract_material_claims,
    format_aggregate_verdicts_for_prompt,
    format_audit_corrections_for_stage4
)
from backend.council import (
    EvaluationError,
    parse_stage2a_output,
    parse_stage2a_output_with_fallback,
    build_stage2a_json_skeleton,
)


# ==========================================
# Legacy Parser Tests
# ==========================================

def test_parse_stage2a_output_valid():
    content = '''
    ```json
    {
      "responses": {
        "Response A": {"score": 4},
        "Response B": {"score": 3},
        "Response C": {"score": 5}
      },
      "ranking": [
        "Response C",
        "Response A",
        "Response B"
      ]
    }
    ```
    '''
    expected_keys = ["Response A", "Response B", "Response C"]
    result = parse_stage2a_output(content, expected_keys)
    assert result["ranking"] == ["Response C", "Response A", "Response B"]

def test_parse_stage2a_output_leakage():
    content = '''
    {
      "responses": {
        "Response A": {},
        "Response B": {}
      },
      "ranking": ["Response A", "Response B", "Response C"]
    }
    '''
    with pytest.raises(EvaluationError):
        parse_stage2a_output(content, ["Response A", "Response B"])


def test_parse_stage2a_output_with_fallback_recovers_markdown_ranking():
    content = """
    Here are my thoughts on each response.

    FINAL RANKING:
    1. Response B
    2. Response A
    """
    result = parse_stage2a_output_with_fallback(content, ["Response A", "Response B"])
    assert result["degraded"] is True
    assert result["ranking"] == ["Response B", "Response A"]
    assert set(result["responses"].keys()) == {"Response A", "Response B"}


def test_build_stage2a_json_skeleton_includes_all_labels():
    skeleton = build_stage2a_json_skeleton(["Response A", "Response B"])
    assert set(skeleton["responses"].keys()) == {"Response A", "Response B"}
    assert skeleton["ranking"] == ["Response A", "Response B"]

def test_parse_audit_verdicts_malformed():
    with pytest.raises(EvaluationError):
        _parse_audit_verdicts("Not JSON", [])

def test_parse_audit_verdicts_349_claims_collapse():
    degraded_json = {
        f"C-{i:03d}": {
            "source_support": "supported",
            "substantive_assessment": "sound",
            "reason": "." if i > 10 else "This is a properly long reason that should pass."
        }
        for i in range(30)
    }
    with pytest.raises(EvaluationError, match="Degenerate reason"):
        _parse_audit_verdicts(json.dumps(degraded_json), [f"C-{i:03d}" for i in range(30)])

def test_parse_audit_verdicts_repetitive_boilerplate():
    repetitive_json = {
        f"C-{i:03d}": {
            "source_support": "supported",
            "substantive_assessment": "sound",
            "reason": "This is a properly long reason but repetitive."
        }
        for i in range(20)
    }
    with pytest.raises(EvaluationError, match="Repetitive boilerplate"):
        _parse_audit_verdicts(json.dumps(repetitive_json), [f"C-{i:03d}" for i in range(20)])


# ==========================================
# E2E Orchestration & Execution Mode Tests
# ==========================================

@pytest.fixture
def mock_settings():
    return SimpleNamespace(
        debate_rounds=1,
        critique_mode="audit",
        audit_profile="general",
        stage2_temperature=0.3,
        chairman_temperature=0.4,
        response_language="English",
        stage4_prompt="",
        claim_extraction_timeout_seconds=180.0,
    )

def make_async_gen(items):
    async def gen(*args, **kwargs):
        for item in items:
            yield item
    return gen

@pytest.mark.asyncio
async def test_run_audit_pipeline_full_e2e(mock_settings):
    """Verify that run_audit_pipeline in 'full' mode runs all stages and dispatches correctly."""
    stage1_items = [
        2,
        {"model": "model_a", "response": "Answer A", "error": None},
        {"model": "model_b", "response": "Answer B", "error": None}
    ]
    stage2a_items = [
        {"type": "stage2a_init", "total": 2, "round": 1},
        {"type": "stage2a_progress", "data": {"model": "model_a", "parsed": {"ranking": ["Response B", "Response A"]}}, "count": 1, "total": 2, "round": 1},
        {"type": "stage2a_progress", "data": {"model": "model_b", "parsed": {"ranking": ["Response B", "Response A"]}}, "count": 2, "total": 2, "round": 1},
        {"type": "stage2a_complete", "data": [{"model": "model_a"}, {"model": "model_b"}], "label_to_model": {"A": "model_a", "B": "model_b"}, "round": 1}
    ]
    stage2b_items = [
        {"type": "stage2b_init", "total": 2, "round": 1},
        {"type": "stage2b_progress", "data": {"model": "model_a"}, "count": 1, "total": 2, "round": 1},
        {"type": "stage2b_progress", "data": {"model": "model_b"}, "count": 2, "total": 2, "round": 1},
        {"type": "stage2b_complete", "data": [], "label_to_model": {}, "round": 1}
    ]

    raw_claims = {"A": [{"id": "c1", "claim": "disposition is sound"}]}
    stage2c_val = {"record": {"adopt": ["C-001"], "reject": [], "qualify": [], "authority_gaps": [], "record_gaps": [], "stage3_constraints": []}}

    with patch("backend.audit_pipeline.get_settings", return_value=mock_settings), \
         patch("backend.audit_pipeline.stage1_collect_responses", side_effect=make_async_gen(stage1_items)), \
         patch("backend.audit_pipeline.stage2a_collect_evaluations", side_effect=make_async_gen(stage2a_items)), \
         patch("backend.audit_pipeline.extract_material_claims", return_value={"claims": raw_claims, "model": "extractor"}), \
         patch("backend.audit_pipeline.stage2b_collect_audits", side_effect=make_async_gen(stage2b_items)), \
         patch("backend.audit_pipeline.stage2c_adjudicate", return_value=stage2c_val), \
         patch("backend.audit_pipeline.query_model", return_value={"content": "Final Synthesis"}) as mock_query, \
         patch("backend.audit_pipeline.stage3_synthesize_final", return_value={"model": "chairman", "response": "Query? corrected", "error": False}), \
         patch("backend.audit_pipeline.get_chairman_model", return_value="chairman"):

        events = []
        async for event in run_audit_pipeline("Query?", execution_mode="full", models_override=["model_a", "model_b"], conversation_id="test-conv"):
            events.append(event)

        event_types = [e["type"] for e in events]
        assert "stage1_start" in event_types
        assert "stage2a_start" in event_types
        assert "stage2b_start" in event_types
        assert "stage2c_start" in event_types
        assert "stage3_start" in event_types
        assert "stage3_complete" in event_types
        assert "stage4_start" in event_types
        assert "stage4_complete" in event_types
        assert "debate_complete" in event_types

        stage3_prompt = mock_query.call_args.args[1][0]["content"]
        assert "claims_evaluated: 1" in stage3_prompt
        assert "C-001" in stage3_prompt

        complete_event = next(e for e in events if e["type"] == "debate_complete")
        assert complete_event["critique_mode"] == "audit"
        assert complete_event["debate_rounds_executed"] == 1
        assert complete_event["convergence_status"] == "not_applicable"


@pytest.mark.parametrize(
    ("provider_message", "expected_message"),
    [
        ("API Failure", "API Failure"),
        (None, "Stage 3 provider error."),
        ("", "Stage 3 provider error."),
    ],
)
@pytest.mark.asyncio
async def test_run_audit_pipeline_stage3_provider_error_surfaces(
    mock_settings,
    provider_message,
    expected_message,
):
    """A provider error dictionary must fail the debate and skip Stage 4."""
    stage1_items = [
        2,
        {"model": "model_a", "response": "Answer A", "error": None},
        {"model": "model_b", "response": "Answer B", "error": None}
    ]
    stage2a_items = [
        {"type": "stage2a_init", "total": 2, "round": 1},
        {"type": "stage2a_progress", "data": {"model": "model_a", "parsed": {"ranking": ["Response B", "Response A"]}}, "count": 1, "total": 2, "round": 1},
        {"type": "stage2a_progress", "data": {"model": "model_b", "parsed": {"ranking": ["Response B", "Response A"]}}, "count": 2, "total": 2, "round": 1},
        {"type": "stage2a_complete", "data": [{"model": "model_a"}, {"model": "model_b"}], "label_to_model": {"A": "model_a", "B": "model_b"}, "round": 1}
    ]
    stage2b_items = [
        {"type": "stage2b_init", "total": 2, "round": 1},
        {"type": "stage2b_progress", "data": {"model": "model_a"}, "count": 1, "total": 2, "round": 1},
        {"type": "stage2b_progress", "data": {"model": "model_b"}, "count": 2, "total": 2, "round": 1},
        {"type": "stage2b_complete", "data": [], "label_to_model": {}, "round": 1}
    ]
    raw_claims = {"A": [{"id": "c1", "claim": "disposition is sound"}]}
    stage2c_val = {"record": {"adopt": ["C-001"], "reject": [], "qualify": [], "authority_gaps": [], "record_gaps": [], "stage3_constraints": []}}

    with patch("backend.audit_pipeline.get_settings", return_value=mock_settings), \
         patch("backend.audit_pipeline.stage1_collect_responses", side_effect=make_async_gen(stage1_items)), \
         patch("backend.audit_pipeline.stage2a_collect_evaluations", side_effect=make_async_gen(stage2a_items)), \
         patch("backend.audit_pipeline.extract_material_claims", return_value={"claims": raw_claims, "model": "extractor"}), \
         patch("backend.audit_pipeline.stage2b_collect_audits", side_effect=make_async_gen(stage2b_items)), \
         patch("backend.audit_pipeline.stage2c_adjudicate", return_value=stage2c_val), \
         patch("backend.audit_pipeline.query_model", return_value={
             "error": True,
             "error_message": provider_message,
             "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
             "cost": {
                 "model": "chairman",
                 "provider": "test",
                 "input_tokens": 10,
                 "output_tokens": 2,
                 "total_tokens": 12,
                 "total_cost": 0.0123,
             },
         }), \
         patch("backend.audit_pipeline.get_chairman_model", return_value="chairman"):

        events = []
        async for event in run_audit_pipeline("Query?", execution_mode="full", models_override=["model_a", "model_b"], conversation_id="test-conv"):
            events.append(event)

        event_types = [e["type"] for e in events]
        assert "stage3_complete" in event_types
        assert "stage4_start" not in event_types
        assert "stage4_complete" not in event_types
        stage3 = next(e["data"] for e in events if e["type"] == "stage3_complete")
        assert stage3["usage"] == {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}
        assert stage3["cost"]["total_cost"] == 0.0123
        complete = next(e for e in events if e["type"] == "debate_complete")
        assert complete["convergence_status"] == "failed"
        assert complete["cost_report"]["total_cost"] == 0.0123
        assert complete["cost_report"]["total_calls"] == 1
        assert complete["error"]["stage"] == "stage3"
        assert complete["error"]["status"] == "failed_synthesis"
        assert complete["error"]["message"] == expected_message

@pytest.mark.asyncio
async def test_run_audit_pipeline_chat_only(mock_settings):
    """Verify that run_audit_pipeline in 'chat_only' mode runs only Stage 1."""
    stage1_items = [
        2,
        {"model": "model_a", "response": "Answer A", "error": None},
        {"model": "model_b", "response": "Answer B", "error": None}
    ]

    with patch("backend.audit_pipeline.get_settings", return_value=mock_settings), \
         patch("backend.audit_pipeline.stage1_collect_responses", side_effect=make_async_gen(stage1_items)):

        events = []
        async for event in run_audit_pipeline("Query?", execution_mode="chat_only", models_override=["model_a", "model_b"], conversation_id="test-conv"):
            events.append(event)

        event_types = [e["type"] for e in events]
        assert "stage1_start" in event_types
        assert "stage1_progress" in event_types
        assert "stage2a_start" not in event_types
        assert "stage2b_start" not in event_types
        assert "stage3_start" not in event_types
        assert "debate_complete" in event_types

@pytest.mark.asyncio
async def test_run_audit_pipeline_chat_ranking(mock_settings):
    """Verify that run_audit_pipeline in 'chat_ranking' runs Stages 1 and 2, but bypasses Stage 3."""
    stage1_items = [
        2,
        {"model": "model_a", "response": "Answer A", "error": None},
        {"model": "model_b", "response": "Answer B", "error": None}
    ]
    stage2a_items = [
        {"type": "stage2a_init", "total": 2, "round": 1},
        {"type": "stage2a_progress", "data": {"model": "model_a", "parsed": {"ranking": ["Response B", "Response A"]}}, "count": 1, "total": 2, "round": 1},
        {"type": "stage2a_complete", "data": [{"model": "model_a"}], "label_to_model": {"A": "model_a", "B": "model_b"}, "round": 1}
    ]
    stage2b_items = [
        {"type": "stage2b_init", "total": 2, "round": 1},
        {"type": "stage2b_progress", "data": {"model": "model_a"}, "count": 1, "total": 2, "round": 1},
        {"type": "stage2b_complete", "data": [], "label_to_model": {}, "round": 1}
    ]

    raw_claims = {"A": [{"id": "c1", "claim": "disposition is sound"}]}
    stage2c_val = {"record": {"adopt": ["C-001"], "reject": [], "qualify": [], "authority_gaps": [], "record_gaps": [], "stage3_constraints": []}}

    with patch("backend.audit_pipeline.get_settings", return_value=mock_settings), \
         patch("backend.audit_pipeline.stage1_collect_responses", side_effect=make_async_gen(stage1_items)), \
         patch("backend.audit_pipeline.stage2a_collect_evaluations", side_effect=make_async_gen(stage2a_items)), \
         patch("backend.audit_pipeline.extract_material_claims", return_value={"claims": raw_claims, "model": "extractor"}), \
         patch("backend.audit_pipeline.stage2b_collect_audits", side_effect=make_async_gen(stage2b_items)), \
         patch("backend.audit_pipeline.stage2c_adjudicate", return_value=stage2c_val), \
         patch("backend.audit_pipeline.get_chairman_model", return_value="chairman"):

        events = []
        async for event in run_audit_pipeline("Query?", execution_mode="chat_ranking", models_override=["model_a", "model_b"], conversation_id="test-conv"):
            events.append(event)

        event_types = [e["type"] for e in events]
        assert "stage1_start" in event_types
        assert "stage2a_start" in event_types
        assert "stage2b_start" in event_types
        assert "stage2c_start" in event_types
        assert "stage3_start" not in event_types
        assert "debate_complete" in event_types


@pytest.mark.asyncio
async def test_audit_empty_claims_falls_back_to_stage2a_synthesis(mock_settings):
    stage1_items = [
        2,
        {"model": "model_a", "response": "Answer A", "error": None},
        {"model": "model_b", "response": "Answer B", "error": None},
    ]
    stage2a_items = [
        {"type": "stage2a_init", "total": 2, "round": 1},
        {
            "type": "stage2a_progress",
            "data": {"model": "model_a", "parsed": {"ranking": ["Response A", "Response B"]}},
            "count": 1,
            "total": 2,
            "round": 1,
        },
        {
            "type": "stage2a_complete",
            "data": [{"model": "model_a"}],
            "label_to_model": {"A": "model_a", "B": "model_b"},
            "round": 1,
        },
    ]

    with patch("backend.audit_pipeline.get_settings", return_value=mock_settings), \
         patch("backend.audit_pipeline.stage1_collect_responses", side_effect=make_async_gen(stage1_items)), \
         patch("backend.audit_pipeline.stage2a_collect_evaluations", side_effect=make_async_gen(stage2a_items)), \
         patch("backend.audit_pipeline.extract_material_claims", return_value={"claims": {}, "model": "extractor"}), \
         patch("backend.audit_pipeline.query_model", return_value={"content": "Synthesis without claim audit"}) as mock_query, \
         patch("backend.audit_pipeline.get_chairman_model", return_value="chairman"):
        events = []
        async for event in run_audit_pipeline(
            "Query?",
            execution_mode="full",
            models_override=["model_a", "model_b"],
            conversation_id="test-conv",
        ):
            events.append(event)

    event_types = [e["type"] for e in events]
    assert "stage2b_skipped" in event_types
    assert "stage2b_start" not in event_types
    assert "stage3_start" in event_types
    assert "stage4_start" not in event_types

    complete_event = next(event for event in events if event["type"] == "debate_complete")
    assert complete_event.get("error") is None
    assert complete_event["convergence_status"] == "partial"
    assert complete_event["warnings"][0]["status"] == "no_canonical_claims"
    metadata = complete_event["rounds"][0]["metadata"]
    assert metadata["claim_audit_status"] == "unavailable"
    assert complete_event["rounds"][0]["stage3"]["response"] == "Synthesis without claim audit"

    stage3_prompt = mock_query.call_args.args[1][0]["content"]
    assert "claim-level audit was unavailable" in stage3_prompt.lower()


def test_format_aggregate_verdicts_for_prompt_includes_authoritative_count_and_claims():
    aggregated = {
        "audit_status": "complete",
        "claims_evaluated": 2,
        "valid_evaluators": 4,
        "expected_evaluators": 4,
        "aggregated_claims": [
            {
                "claim_id": "C-001",
                "canonical_text": "First claim",
                "support_counts": {"supported": 4},
                "assessment_counts": {"sound": 4},
            },
            {
                "claim_id": "C-002",
                "canonical_text": "Second claim",
                "support_counts": {"unsupported": 3},
                "assessment_counts": {"unsound": 3},
            },
        ],
    }
    text = format_aggregate_verdicts_for_prompt(aggregated)
    assert "claims_evaluated: 2" in text
    assert "C-001" in text
    assert "C-002" in text
    assert '"unsound": 3' in text


def test_format_audit_corrections_includes_contested_claims_and_excludes_sound_claims():
    aggregated = {
        "aggregated_claims": [
            {
                "claim_id": "C-001",
                "canonical_text": "Sound claim",
                "support_counts": {"supported": 4},
                "assessment_counts": {"sound": 4},
            },
            {
                "claim_id": "C-002",
                "canonical_text": "Contested claim",
                "support_counts": {"supported": 2, "unsupported": 2},
                "assessment_counts": {"sound": 2, "requires_qualification": 2},
            },
        ]
    }
    stage2b = [{"claim_verdicts": {"C-002": {"reason": "Needs a source and narrower wording."}}}]
    stage2c = {"record": {"adopt": ["C-001"], "reject": [], "qualify": [], "authority_gaps": [], "record_gaps": [], "stage3_constraints": []}}
    text = format_audit_corrections_for_stage4(aggregated, stage2b, stage2c)
    assert "C-002 [CONTESTED]" in text
    assert "Needs a source and narrower wording." in text
    assert "C-001" not in text


# ==========================================
# Provider Options & Token Limits Mapping
# ==========================================

class _FakeResponse:
    def __init__(self, status_code=200, json_body=None):
        self.status_code = status_code
        self._json = json_body or {"choices": [{"message": {"content": "ok"}}]}
        self.text = json.dumps(self._json)
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"HTTP Status Error: {self.status_code}")

    async def aread(self):
        return self.text.encode("utf-8")

    async def aiter_lines(self):
        yield f"data: {json.dumps(self._json)}"
        yield "data: [DONE]"

class _FakeAsyncClient:
    instances = []
    responses = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        type(self).instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        self.kwargs["__url__"] = url
        self.kwargs.update(kwargs)
        if type(self).responses:
            return type(self).responses.pop(0)
        return _FakeResponse()

    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def stream(self, method, url, **kwargs):
        self.kwargs["__url__"] = url
        self.kwargs.update(kwargs)
        resp = type(self).responses.pop(0) if type(self).responses else _FakeResponse()
        yield resp

@pytest.fixture
def fake_httpx(monkeypatch):
    _FakeAsyncClient.instances = []
    _FakeAsyncClient.responses = []
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient

@pytest.mark.asyncio
async def test_provider_token_limits_notion2api(fake_httpx, monkeypatch):
    from backend.providers.notion2api import Notion2APIProvider
    import backend.settings as settings_module
    monkeypatch.setattr(settings_module, "get_settings", lambda: MagicMock(
        notion2api_base_url="http://localhost:8120/v1",
        notion2api_api_key="sk-test",
        notion2api_firing_mode="rapid_fire"
    ))

    response_json = {"choices": [{"delta": {"content": "ok"}}]}
    fake_httpx.responses.append(_FakeResponse(200, response_json))

    provider = Notion2APIProvider()
    await provider.query("notion2api:fable5", [{"role": "user", "content": "hi"}], max_output_tokens=1200)

    body = fake_httpx.instances[-1].kwargs["json"]
    assert body["max_tokens"] == 1200


# ==========================================
# Quorum & Validation Abort Tests
# ==========================================

@pytest.mark.asyncio
async def test_stage2a_quorum_abort(mock_settings):
    """Verify that if Stage 2A collects fewer than MIN_VALID_EVALUATORS successful results, it aborts with quorum error."""
    stage1_results = [
        {"model": "model_a", "response": "A", "error": None},
        {"model": "model_b", "response": "B", "error": None}
    ]

    # Fake _query_model_gated that always returns failure for one evaluator
    call_count = 0
    async def fake_gated(model, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if model == "model_a":
            return {"error": True, "error_message": "API Failure"}
        else:
            # Valid json representation
            return {"content": '{"responses": {"Response A": {"score": 4}}, "ranking": ["Response B", "Response A"]}', "error": None}

    with patch("backend.audit_pipeline._query_model_gated", side_effect=fake_gated):
        events = []
        async for event in stage2a_collect_evaluations(
            "Query", "", stage1_results, "test-conv", mock_settings
        ):
            events.append(event)

        event_types = [e["type"] for e in events]
        assert "stage2a_error" in event_types
        err_event = next(e for e in events if e["type"] == "stage2a_error")
        assert err_event["status"] in ("failed_quorum", "invalid_evaluator_output")

@pytest.mark.asyncio
async def test_stage2b_validation_claim_ids(mock_settings):
    """Verify that Stage 2B rejects and filters out unknown/extra claim IDs in evaluator responses."""
    stage1_results = [
        {"model": "model_a", "response": "A", "error": None},
        {"model": "model_b", "response": "B", "error": None}
    ]
    canonical_claims = [
        {"claim_id": "C-001", "canonical_text": "Claim 1"},
        {"claim_id": "C-002", "canonical_text": "Claim 2"}
    ]

    # Evaluator returns verdicts containing an unknown claim ID: C-999
    audit_output = """
    {
      "C-001": {"source_support": "supported", "substantive_assessment": "sound", "reason": "Valid claim 1 justification here."},
      "C-002": {"source_support": "supported", "substantive_assessment": "sound", "reason": "Valid claim 2 justification here."},
      "C-999": {"source_support": "unsupported", "substantive_assessment": "defect", "reason": "Unexpected claim ID."}
    }
    """

    async def fake_gated(model, *args, **kwargs):
        return {"content": audit_output, "error": None}

    with patch("backend.audit_pipeline._query_model_gated", side_effect=fake_gated):
        events = []
        async for event in stage2b_collect_audits(
            "Query", "", stage1_results, canonical_claims, "test-conv", mock_settings
        ):
            events.append(event)

        progress_events = [e for e in events if e["type"] == "stage2b_progress"]
        for p in progress_events:
            # The parser should reject/raise, leading to model error since validation fails
            assert p["data"].get("error") is True


# ==========================================
# Self-Evaluation Exclusion & Capping
# ==========================================

@pytest.mark.asyncio
async def test_self_evaluation_exclusion_prompt(mock_settings):
    """Verify that Stage 2A collect evaluations excludes the evaluator's own response from its prompt."""
    stage1_results = [
        {"model": "model_a", "response": "Response content A", "error": None},
        {"model": "model_b", "response": "Response content B", "error": None},
        {"model": "model_c", "response": "Response content C", "error": None},
    ]

    captured_prompts = {}
    async def fake_gated(model, messages, **kwargs):
        captured_prompts[model] = messages[0]["content"]
        if model == "model_a":
            res_labels = ["Response B", "Response C"]
        elif model == "model_b":
            res_labels = ["Response A", "Response C"]
        else:
            res_labels = ["Response A", "Response B"]

        responses = {lbl: {"score": 4} for lbl in res_labels}
        ranking = list(reversed(res_labels))
        content = json.dumps({"responses": responses, "ranking": ranking})
        return {"content": content, "error": None}

    with patch("backend.audit_pipeline._query_model_gated", side_effect=fake_gated):
        events = []
        async for event in stage2a_collect_evaluations(
            user_query="Query",
            search_context="",
            stage1_results=stage1_results,
            conversation_id="test-conv",
            settings=mock_settings,
        ):
            events.append(event)

    # Assert successful Stage 2A completion and no errors
    assert any(e["type"] == "stage2a_complete" for e in events)
    assert not any(e["type"] == "stage2a_error" for e in events)

    # Ensure model_a did not receive "Response content A" or "Response A" in responses_text
    assert "model_a" in captured_prompts
    assert "Response A:" not in captured_prompts["model_a"]
    assert "Response content A" not in captured_prompts["model_a"]
    assert "Response B:" in captured_prompts["model_a"]
    assert "Response content B" in captured_prompts["model_a"]
    assert "Response C:" in captured_prompts["model_a"]
    assert "Response content C" in captured_prompts["model_a"]

    # Same for model_b
    assert "model_b" in captured_prompts
    assert "Response B:" not in captured_prompts["model_b"]
    assert "Response content B" not in captured_prompts["model_b"]
    assert "Response A:" in captured_prompts["model_b"]
    assert "Response content A" in captured_prompts["model_b"]

def test_claim_deduplication_and_capping():
    """Verify that normalize_and_deduplicate_claims caps the number of canonical claims strictly to 30 and is deterministic."""
    raw_claims = {
        "Response A": [
            {"id": f"c{i}", "claim": f"Claim {i} standard of review disposition." if i % 5 == 0 else f"Low-priority claim {i}."}
            for i in range(50)
        ]
    }

    canonical_1 = normalize_and_deduplicate_claims(raw_claims)
    assert len(canonical_1) <= 30

    # Reorder input list to verify deterministic ordering of results
    raw_claims_shuffled = {
        "Response A": list(reversed(raw_claims["Response A"]))
    }
    canonical_2 = normalize_and_deduplicate_claims(raw_claims_shuffled)

    assert [c["canonical_text"] for c in canonical_1] == [c["canonical_text"] for c in canonical_2]
    assert [c["claim_id"] for c in canonical_1] == [c["claim_id"] for c in canonical_2]
    assert "standard of review" in canonical_1[0]["canonical_text"].lower()



# ==========================================
# Client Disconnection Handling
# ==========================================

@pytest.mark.asyncio
async def test_client_disconnection_cancellation(mock_settings):
    """Verify that client disconnect check triggers asyncio task cancellation cleanly."""
    stage1_results = [
        {"model": "model_a", "response": "A", "error": None},
        {"model": "model_b", "response": "B", "error": None}
    ]

    # Return true immediately on disconnect check
    async def disconnect_check():
        return True

    # _query_model_gated that sleeps to simulate network latency
    async def fake_gated(*args, **kwargs):
        await asyncio.sleep(10)
        return {"content": "Evaluated", "error": None}

    with patch("backend.audit_pipeline._query_model_gated", side_effect=fake_gated):
        events = []
        try:
            async for event in stage2a_collect_evaluations(
                "Query", "", stage1_results, "test-conv", mock_settings, disconnect_check=disconnect_check
            ):
                events.append(event)
        except asyncio.CancelledError:
            pass

        # The manifest and dispatch evidence may be emitted before cancellation,
        # but no model result should complete after an immediate disconnect.
        assert events[0]["type"] == "stage2a_init"
        assert [event["type"] for event in events[1:]] == [
            "provider_status",
            "provider_status",
        ]
        assert not any(event["type"] == "stage2a_progress" for event in events)


# ==========================================
# Chairman Override Propagation
# ==========================================

@pytest.mark.asyncio
async def test_chairman_override_propagation(mock_settings):
    """Verify that the custom chairman override is propagated to Stage 3 synthesis."""
    stage1_items = [
        2,
        {"model": "model_a", "response": "Answer A", "error": None},
        {"model": "model_b", "response": "Answer B", "error": None}
    ]
    stage2a_items = [
        {"type": "stage2a_init", "total": 2, "round": 1},
        {"type": "stage2a_complete", "data": [{"model": "model_a"}], "label_to_model": {"A": "model_a", "B": "model_b"}, "round": 1}
    ]
    stage2b_items = [
        {"type": "stage2b_init", "total": 2, "round": 1},
        {"type": "stage2b_complete", "data": [], "label_to_model": {}, "round": 1}
    ]
    raw_claims = {"A": [{"id": "c1", "claim": "disposition is sound"}]}
    stage2c_val = {"record": {"adopt": ["C-001"], "reject": [], "qualify": [], "authority_gaps": [], "record_gaps": [], "stage3_constraints": []}}

    with patch("backend.audit_pipeline.get_settings", return_value=mock_settings), \
         patch("backend.audit_pipeline.stage1_collect_responses", side_effect=make_async_gen(stage1_items)), \
         patch("backend.audit_pipeline.stage2a_collect_evaluations", side_effect=make_async_gen(stage2a_items)), \
         patch("backend.audit_pipeline.extract_material_claims", return_value={"claims": raw_claims, "model": "extractor"}), \
         patch("backend.audit_pipeline.stage2b_collect_audits", side_effect=make_async_gen(stage2b_items)), \
         patch("backend.audit_pipeline.stage2c_adjudicate", return_value=stage2c_val), \
         patch("backend.audit_pipeline.query_model", return_value={"content": "Final Synthesis"}) as mock_query_model, \
         patch("backend.audit_pipeline.get_chairman_model", return_value="chairman"):

        events = []
        async for event in run_audit_pipeline(
            "Query?", execution_mode="full", models_override=["model_a", "model_b"], chairman_override="custom_chairman", conversation_id="test-conv"
        ):
            events.append(event)

        # Stage 3 query_model should be invoked with the overridden chairman model ID
        mock_query_model.assert_called_once()
        called_model = mock_query_model.call_args[0][0]
        assert called_model == "custom_chairman"


@pytest.mark.asyncio
async def test_stage2b_success(mock_settings):
    """Verify that Stage 2B collects successful audits and completes successfully."""
    stage1_results = [
        {"model": "model_a", "response": "A", "error": None},
        {"model": "model_b", "response": "B", "error": None}
    ]
    canonical_claims = [
        {"claim_id": "C-001", "canonical_text": "Claim 1"},
        {"claim_id": "C-002", "canonical_text": "Claim 2"}
    ]

    audit_output = """
    {
      "C-001": {"source_support": "supported", "substantive_assessment": "sound", "reason": "Valid claim 1 justification here that is sufficiently long."},
      "C-002": {"source_support": "supported", "substantive_assessment": "sound", "reason": "Valid claim 2 justification here that is sufficiently long."}
    }
    """

    async def fake_gated(model, *args, **kwargs):
        return {"content": audit_output, "error": None}

    with patch("backend.audit_pipeline._query_model_gated", side_effect=fake_gated):
        events = []
        async for event in stage2b_collect_audits(
            "Query", "", stage1_results, canonical_claims, "test-conv", mock_settings
        ):
            events.append(event)

        assert any(e["type"] == "stage2b_complete" for e in events)
        assert not any(e["type"] == "stage2b_error" for e in events)


@pytest.mark.asyncio
async def test_run_audit_pipeline_stage4_fails_validation_twice(mock_settings):
    """Verify that when Stage 4 fails validation twice in audit pipeline, it reports error correctly."""
    stage1_items = [
        2,
        {"model": "model_a", "response": "Answer A", "error": None},
        {"model": "model_b", "response": "Answer B", "error": None}
    ]
    stage2a_items = [
        {"type": "stage2a_init", "total": 2, "round": 1},
        {"type": "stage2a_progress", "data": {"model": "model_a", "parsed": {"ranking": ["Response B", "Response A"]}}, "count": 1, "total": 2, "round": 1},
        {"type": "stage2a_progress", "data": {"model": "model_b", "parsed": {"ranking": ["Response B", "Response A"]}}, "count": 2, "total": 2, "round": 1},
        {"type": "stage2a_complete", "data": [{"model": "model_a"}, {"model": "model_b"}], "label_to_model": {"A": "model_a", "B": "model_b"}, "round": 1}
    ]
    stage2b_items = [
        {"type": "stage2b_init", "total": 2, "round": 1},
        {"type": "stage2b_progress", "data": {"model": "model_a"}, "count": 1, "total": 2, "round": 1},
        {"type": "stage2b_progress", "data": {"model": "model_b"}, "count": 2, "total": 2, "round": 1},
        {"type": "stage2b_complete", "data": [], "label_to_model": {}, "round": 1}
    ]

    raw_claims = {"A": [{"id": "c1", "claim": "disposition is sound"}]}
    stage2c_val = {"record": {"adopt": ["C-001"], "reject": [], "qualify": [], "authority_gaps": [], "record_gaps": [], "stage3_constraints": []}}

    with patch("backend.audit_pipeline.get_settings", return_value=mock_settings), \
         patch("backend.audit_pipeline.stage1_collect_responses", side_effect=make_async_gen(stage1_items)), \
         patch("backend.audit_pipeline.stage2a_collect_evaluations", side_effect=make_async_gen(stage2a_items)), \
         patch("backend.audit_pipeline.extract_material_claims", return_value={"claims": raw_claims, "model": "extractor"}), \
         patch("backend.audit_pipeline.stage2b_collect_audits", side_effect=make_async_gen(stage2b_items)), \
         patch("backend.audit_pipeline.stage2c_adjudicate", return_value=stage2c_val), \
         patch("backend.audit_pipeline.query_model", return_value={"content": "Final Synthesis"}), \
         patch("backend.audit_pipeline.stage3_synthesize_final", return_value={"model": "chairman", "response": "Too short", "error": False}), \
         patch("backend.audit_pipeline.get_chairman_model", return_value="chairman"):

        events = []
        long_query = "# Header A\n" + "word " * 100
        async for event in run_audit_pipeline(long_query, execution_mode="full", models_override=["model_a", "model_b"], conversation_id="test-conv"):
            events.append(event)

        stage4_complete = next(e for e in events if e["type"] == "stage4_complete")
        data = stage4_complete["data"]
        assert data["error"] is True
        assert "Stage 4 failed preservation validation" in data["error_message"]
        assert data["validation"]["passed"] is False


@pytest.mark.asyncio
async def test_extract_material_claims_accepts_null_usage_and_cost(mock_settings):
    """Provider accounting fields may be explicit null without invalidating claims."""
    mock_settings.claim_extraction_timeout_seconds = 180.0
    response = {
        "content": json.dumps({
            "Response A": [
                {"id": "A-001", "claim": "Water boils near 100 C at sea level."}
            ]
        }),
        "usage": {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
        },
        "cost": None,
        "error": False,
    }

    with patch("backend.audit_pipeline._query_model_gated", return_value=response):
        result = await extract_material_claims(
            "Response A:\nAnswer A",
            "test-null-accounting",
            mock_settings,
            chairman_override="chairman",
        )

    assert result["claims"]["Response A"][0]["id"] == "A-001"
    assert result["cost"] is None


@pytest.mark.asyncio
async def test_extract_material_claims_accepts_non_dict_usage(mock_settings):
    """Provider accounting fields may be a non-dict truthy value without crashing."""
    mock_settings.claim_extraction_timeout_seconds = 180.0
    response = {
        "content": json.dumps({
            "Response A": [
                {"id": "A-001", "claim": "Water boils near 100 C at sea level."}
            ]
        }),
        "usage": "truthy but invalid type",
        "cost": 0.05,
        "error": False,
    }

    with patch("backend.audit_pipeline._query_model_gated", return_value=response):
        result = await extract_material_claims(
            "Response A:\nAnswer A",
            "test-nondict-accounting",
            mock_settings,
            chairman_override="chairman",
        )

    assert result["claims"]["Response A"][0]["id"] == "A-001"
    assert result["cost"] == 0.05


@pytest.mark.asyncio
async def test_extract_material_claims_accumulates_dict_cost_on_retry_failure(mock_settings):
    """Failed extraction retries must retain normalized per-call cost totals."""
    mock_settings.claim_extraction_timeout_seconds = 180.0
    responses = [
        {
            "content": json.dumps({"Response A": "not a list"}),
            "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
            "cost": {"total_cost": 0.01},
            "error": False,
        },
        {
            "content": json.dumps({"Response A": "still not a list"}),
            "usage": {"input_tokens": 4, "output_tokens": 5, "total_tokens": 9},
            "cost": {"total_cost": 0.02},
            "error": False,
        },
    ]

    with patch("backend.audit_pipeline._query_model_gated", side_effect=responses):
        result = await extract_material_claims(
            "Response A:\nAnswer A",
            "test-dict-cost-retries",
            mock_settings,
            chairman_override="chairman",
        )

    assert result["claims"] is None
    assert result["usage"] == {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12}
    assert result["cost"] == pytest.approx(0.03)
    assert [attempt["status"] for attempt in result["attempts"]] == [
        "validation_failed",
        "validation_failed",
    ]


@pytest.mark.asyncio
async def test_extract_material_claims_normalizes_supported_claim_shapes(mock_settings):
    mock_settings.claim_extraction_timeout_seconds = 180.0
    response = {
        "content": json.dumps({
            "Response A": [
                "  Water boils near 100 C.  ",
                {"id": " A-2 ", "text": "  Ice melts near 0 C. "},
                {"content": "Steam is gaseous water."},
            ]
        }),
        "usage": None,
        "cost": None,
        "error": False,
    }

    with patch("backend.audit_pipeline._query_model_gated", return_value=response):
        result = await extract_material_claims(
            "Response A:\nAnswer A",
            "test-normalized-claims",
            mock_settings,
            chairman_override="chairman",
        )

    assert result["claims"]["Response A"] == [
        {"id": "Response A_1", "claim": "Water boils near 100 C."},
        {"id": "A-2", "claim": "Ice melts near 0 C."},
        {"id": "Response A_3", "claim": "Steam is gaseous water."},
    ]


@pytest.mark.asyncio
async def test_extract_material_claims_retries_malformed_claim_with_correction(mock_settings):
    mock_settings.claim_extraction_timeout_seconds = 180.0
    responses = [
        {"content": json.dumps({"Response A": [{}]}), "usage": None, "cost": None, "error": False},
        {
            "content": json.dumps({"Response A": [{"id": "A-1", "claim": "Valid claim."}]}),
            "usage": None,
            "cost": None,
            "error": False,
        },
    ]

    with patch("backend.audit_pipeline._query_model_gated", side_effect=responses) as query:
        result = await extract_material_claims(
            "Response A:\nAnswer A",
            "test-corrected-claim-retry",
            mock_settings,
            chairman_override="chairman",
        )

    retry_messages = query.call_args_list[1].args[1]
    assert any("Validation Error:" in message["content"] for message in retry_messages)
    assert result["claims"]["Response A"] == [{"id": "A-1", "claim": "Valid claim."}]


@pytest.mark.asyncio
async def test_run_audit_pipeline_stage3_invalid_type_provider_result(mock_settings):
    """Verify that run_audit_pipeline handles a non-dictionary result from query_model gracefully."""
    stage1_items = [
        2,
        {"model": "model_a", "response": "Answer A", "error": None},
        {"model": "model_b", "response": "Answer B", "error": None}
    ]
    stage2a_items = [
        {"type": "stage2a_init", "total": 2, "round": 1},
        {"type": "stage2a_progress", "data": {"model": "model_a", "parsed": {"ranking": ["Response B", "Response A"]}}, "count": 1, "total": 2, "round": 1},
        {"type": "stage2a_progress", "data": {"model": "model_b", "parsed": {"ranking": ["Response B", "Response A"]}}, "count": 2, "total": 2, "round": 1},
        {"type": "stage2a_complete", "data": [{"model": "model_a"}, {"model": "model_b"}], "label_to_model": {"A": "model_a", "B": "model_b"}, "round": 1}
    ]
    stage2b_items = [
        {"type": "stage2b_init", "total": 2, "round": 1},
        {"type": "stage2b_progress", "data": {"model": "model_a"}, "count": 1, "total": 2, "round": 1},
        {"type": "stage2b_progress", "data": {"model": "model_b"}, "count": 2, "total": 2, "round": 1},
        {"type": "stage2b_complete", "data": [], "label_to_model": {}, "round": 1}
    ]
    raw_claims = {"A": [{"id": "c1", "claim": "disposition is sound"}]}
    stage2c_val = {"record": {"adopt": ["C-001"], "reject": [], "qualify": [], "authority_gaps": [], "record_gaps": [], "stage3_constraints": []}}

    with patch("backend.audit_pipeline.get_settings", return_value=mock_settings), \
         patch("backend.audit_pipeline.stage1_collect_responses", side_effect=make_async_gen(stage1_items)), \
         patch("backend.audit_pipeline.stage2a_collect_evaluations", side_effect=make_async_gen(stage2a_items)), \
         patch("backend.audit_pipeline.extract_material_claims", return_value={"claims": raw_claims, "model": "extractor"}), \
         patch("backend.audit_pipeline.stage2b_collect_audits", side_effect=make_async_gen(stage2b_items)), \
         patch("backend.audit_pipeline.stage2c_adjudicate", return_value=stage2c_val), \
         patch("backend.audit_pipeline.query_model", return_value="invalid string response"), \
         patch("backend.audit_pipeline.get_chairman_model", return_value="chairman"):

        events = []
        async for event in run_audit_pipeline("Query?", execution_mode="full", models_override=["model_a", "model_b"], conversation_id="test-conv"):
            events.append(event)

        event_types = [e["type"] for e in events]
        assert "stage3_complete" in event_types
        complete = next(e for e in events if e["type"] == "debate_complete")
        assert complete["convergence_status"] == "failed"
        assert complete["error"]["stage"] == "stage3"
        assert complete["error"]["status"] == "failed_synthesis"
        assert "invalid response" in complete["error"]["message"]
