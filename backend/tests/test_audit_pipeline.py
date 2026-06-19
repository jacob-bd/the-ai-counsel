import pytest
import json
import asyncio
from backend.audit_pipeline import parse_stage2a_output, _parse_audit_verdicts
from backend.council import EvaluationError

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

def test_parse_audit_verdicts_malformed():
    with pytest.raises(EvaluationError):
        _parse_audit_verdicts("Not JSON")

def test_parse_audit_verdicts_349_claims_collapse():
    # Simulate a degraded JSON where responses become boilerplate
    degraded_json = {
        f"C{i:03d}": {
            "source_support": "supported",
            "substantive_assessment": "sound",
            "reason": "." if i > 10 else "This is a properly long reason that should pass."
        }
        for i in range(30)
    }
    with pytest.raises(EvaluationError, match="Degenerate reason"):
        _parse_audit_verdicts(json.dumps(degraded_json))

def test_parse_audit_verdicts_repetitive_boilerplate():
    # Simulate verdict collapse > 95%
    repetitive_json = {
        f"C{i:03d}": {
            "source_support": "supported",
            "substantive_assessment": "sound",
            "reason": "This is a properly long reason but repetitive."
        }
        for i in range(20)
    }
    with pytest.raises(EvaluationError, match="Repetitive boilerplate"):
        _parse_audit_verdicts(json.dumps(repetitive_json))
