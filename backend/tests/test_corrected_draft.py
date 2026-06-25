import pytest
from backend.corrected_draft import (
    apply_stage4_edit_plan,
    clean_corrected_draft,
    detect_stage4_meta_response,
    estimate_stage4_output_tokens,
    generate_corrected_draft,
    should_use_stage4_edit_plan,
    validate_corrected_draft,
)

def test_clean_corrected_draft_preserves_legitimate_references():
    # Legitimate reference inside text body should be kept:
    text = (
        "This document describes the company roadmap.\n"
        "We plan to evaluate OpenAI and Gemini for document classification.\n"
        "Our internal system currently integrates Claude."
    )
    cleaned = clean_corrected_draft(text)
    assert "OpenAI" in cleaned
    assert "Gemini" in cleaned
    assert "Claude" in cleaned
    assert "the Council" not in cleaned

def test_clean_corrected_draft_removes_wrapper_meta_commentary():
    # Conversational intro wrapper with model identity should be removed:
    text = (
        "I am Claude, and here is your corrected document:\n"
        "# Executive Summary\n"
        "The company is growing.\n"
        "I hope this helps!"
    )
    cleaned = clean_corrected_draft(text)
    assert "I am Claude" not in cleaned
    assert "I hope this helps!" not in cleaned
    assert "# Executive Summary" in cleaned
    assert "The company is growing." in cleaned

    # Notion AI wrapper should be removed:
    text = (
        "I'm Notion AI. As requested, here is the corrected draft:\n"
        "# Section 1\n"
        "Hello world"
    )
    cleaned = clean_corrected_draft(text)
    assert "Notion AI" not in cleaned
    assert "# Section 1" in cleaned


def test_detect_stage4_refusal_meta_response():
    refusal = (
        "I'll be straight with you about what I can and can't do here.\n\n"
        "### The source is incomplete\n"
        "I can't produce the full corrected document from this input.\n\n"
        "Want me to produce only the self-contained functions instead?"
    )
    assert detect_stage4_meta_response(refusal)

    valid_document = "# Document\n\nThe source is complete and this is the revised content."
    assert detect_stage4_meta_response(valid_document) is None


def test_estimate_stage4_output_tokens_scales_with_source_length():
    assert estimate_stage4_output_tokens("short") == 8192
    assert estimate_stage4_output_tokens("x" * 60000) >= 20000
    assert estimate_stage4_output_tokens("x" * 200000) == 32768


def test_apply_stage4_edit_plan_preserves_unedited_source():
    original = "alpha\nunique target\nomega"
    raw_plan = '{"edits":[{"old_text":"unique target","new_text":"corrected target"}]}'

    revised, applied, error = apply_stage4_edit_plan(original, raw_plan)

    assert not error
    assert applied == 1
    assert revised == "alpha\ncorrected target\nomega"


def test_apply_stage4_edit_plan_rejects_ambiguous_match():
    original = "repeat\nrepeat"
    raw_plan = '{"edits":[{"old_text":"repeat","new_text":"changed"}]}'

    revised, applied, error = apply_stage4_edit_plan(original, raw_plan)

    assert revised is None
    assert applied == 0
    assert "matched 2 locations" in error


def test_stage4_edit_plan_is_used_for_substantive_preservation_failures():
    medium_source = "word " * 300
    short_source = "word " * 100

    assert should_use_stage4_edit_plan(medium_source, "Draft is too short")
    assert not should_use_stage4_edit_plan(short_source, "Draft is too short")
    assert not should_use_stage4_edit_plan(medium_source, "Model returned a refusal")


def test_validate_corrected_draft_headings_structure():
    original = "# Section A\n## Section A.1\n# Section B"

    # 1. Exact match should pass
    valid, err = validate_corrected_draft(original, "# Section A\n## Section A.1\n# Section B")
    assert valid
    assert not err

    # 2. Missing heading should fail
    valid, err = validate_corrected_draft(original, "# Section A\n# Section B")
    assert not valid
    assert "Missing required sections/headings" in err
    assert "Section A.1" in err

    # 3. Wrong relative order should fail
    valid, err = validate_corrected_draft(original, "# Section B\n# Section A\n## Section A.1")
    assert not valid
    assert "Wrong relative order" in err or "Missing" in err

    # 4. Wrong level should fail
    valid, err = validate_corrected_draft(original, "# Section A\n# Section A.1\n# Section B")
    assert not valid
    assert "Missing" in err

def test_validate_corrected_draft_length():
    original = "a " * 100

    # 1. 90% length should pass
    valid, err = validate_corrected_draft(original, "a " * 90)
    assert valid

    # 2. Under 85% length should fail
    valid, err = validate_corrected_draft(original, "a " * 80)
    assert not valid
    assert "Draft is too short" in err

@pytest.mark.asyncio
async def test_generate_corrected_draft_fails_validation_twice():
    calls = []

    async def fake_synthesize(*args, **kwargs):
        calls.append(kwargs)
        return {"error": False, "response": "Too short response"}

    original = "a " * 100
    result = await generate_corrected_draft(
        synthesize_fn=fake_synthesize,
        default_template="Original: {original_text}\nVerdict: {verdict_text}\nCorrections: {corrections_text}",
        custom_template="",
        total_rounds=1,
        original_text=original,
        verdict_text="Some verdict",
        corrections_text="Some corrections",
        conversation_id="conversation-1",
        max_attempts=2,
    )

    assert result["error"] is True
    assert "Stage 4 failed preservation validation" in result["error_message"]
    assert result["validation"]["passed"] is False
    assert result["validation"]["attempts"] == 2
    assert len(result["validation"]["errors"]) == 1
    assert result["response"] == original
    assert result["failed_response"] == "Too short response"
    assert result["fallback_used"] is True

    assert [call["conversation_id"] for call in calls] == [
        "conversation-1-stage4-1",
        "conversation-1-stage4-2",
    ]
    assert all("source-document block is authoritative" in call["system_prompt_override"] for call in calls)
    assert all(call["max_output_tokens"] >= 8192 for call in calls)


@pytest.mark.asyncio
async def test_generate_corrected_draft_recovers_after_refusal():
    responses = [
        "I'll be straight with you about what I can and can't do. "
        "The source is incomplete. Want me to rewrite only part of it?",
        "# Section\n" + ("revised " * 90),
    ]

    async def fake_synthesize(*args, **kwargs):
        return {"error": False, "response": responses.pop(0)}

    original = "# Section\n" + ("original " * 100)
    result = await generate_corrected_draft(
        synthesize_fn=fake_synthesize,
        default_template="Source: {original_text}",
        custom_template="",
        total_rounds=1,
        original_text=original,
        verdict_text="",
        corrections_text="",
        max_attempts=2,
    )

    assert result["error"] is False
    assert result["fallback_used"] is False
    assert result["validation"]["passed"] is True
    assert result["validation"]["attempts"] == 2
    assert result["response"].startswith("# Section")


@pytest.mark.asyncio
async def test_generate_corrected_draft_recovers_long_source_with_exact_edit_plan():
    target = "const retryDelay = 1000;"
    original = "# Script\n" + ("preserved token\n" * 1300) + target + "\nend marker"
    calls = []
    responses = [
        "A compressed summary that cannot preserve the source.",
        '{"edits":[{"old_text":"const retryDelay = 1000;","new_text":"const retryDelay = 1500;"}]}',
    ]

    async def fake_synthesize(*args, **kwargs):
        calls.append(kwargs)
        return {
            "error": False,
            "model": "notion2api:opus",
            "response": responses.pop(0),
        }

    result = await generate_corrected_draft(
        synthesize_fn=fake_synthesize,
        default_template="Source: {original_text}\nCorrections: {corrections_text}",
        custom_template="",
        total_rounds=2,
        original_text=original,
        verdict_text="The retry delay should be increased.",
        corrections_text="Replace the retry delay with 1500 milliseconds.",
        conversation_id="long-document",
        max_attempts=2,
    )

    assert result["error"] is False
    assert result["fallback_used"] is False
    assert result["generation_strategy"] == "exact_edit_plan"
    assert result["validation"]["edits_applied"] == 1
    assert "const retryDelay = 1500;" in result["response"]
    assert result["response"].count("preserved token") == 1300
    assert result["failed_response"].startswith("A compressed summary")
    assert "PRESERVATION_CONTRACT" in calls[0]["prompt_override"]
    assert "not a replacement document" in calls[0]["prompt_override"].lower()
    assert "EXACT_EDIT_PLAN" in calls[1]["prompt_override"]
    assert calls[1]["max_output_tokens"] <= 12288


def test_validate_corrected_draft_placeholders():
    original = "This is a document with [FILL: company name] and <DATE>."

    # 1. Exact or subset/resolved placeholders should pass
    # Resolved [FILL: company name] -> Acme Corp, but kept <DATE>
    valid, err = validate_corrected_draft(original, "This is a document with Acme Corp and <DATE>.")
    assert valid
    assert not err

    # 2. Re-introducing original placeholders should pass
    valid, err = validate_corrected_draft(original, "This is a document with [FILL: company name] and <DATE>.")
    assert valid
    assert not err

    # 3. Newly invented placeholder should fail
    valid, err = validate_corrected_draft(original, "This is a document with Acme Corp and <DATE> and [TODO: add logo].")
    assert not valid
    assert "Prohibited newly invented placeholders" in err
    assert "TODO: add logo" in err
