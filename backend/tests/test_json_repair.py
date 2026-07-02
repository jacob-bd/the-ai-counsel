"""Tests for JSON extraction and repair."""
from backend.json_repair import extract_json_block, repair_json


def test_extract_json_from_markdown():
    text = 'Some text\n```json\n{"key": "value"}\n```\nMore text'
    assert extract_json_block(text) == {"key": "value"}


def test_extract_json_fallback_braces():
    text = 'Preamble {"key": "value"} postamble'
    assert extract_json_block(text) == {"key": "value"}


def test_repair_trailing_comma():
    text = '{"a": 1, "b": 2,}'
    assert repair_json(text) == {"a": 1, "b": 2}


def test_repair_returns_none_on_garbage():
    assert repair_json("not json at all") is None


def test_extract_nested_json():
    text = 'Result: {"outer": {"inner": [1, 2]}}'
    result = extract_json_block(text)
    assert result == {"outer": {"inner": [1, 2]}}


def test_extract_json_array():
    text = 'Here: [{"a": 1}, {"b": 2}]'
    result = extract_json_block(text)
    assert result == [{"a": 1}, {"b": 2}]


def test_extract_empty_text():
    assert extract_json_block("") is None
    assert extract_json_block(None) is None


def test_repair_empty_text():
    assert repair_json("") is None
    assert repair_json(None) is None


def test_extract_json_uppercase_fence():
    text = 'Some text\n```JSON\n{"key": "value"}\n```\nMore text'
    assert extract_json_block(text) == {"key": "value"}


def test_extract_json_with_stray_braces_in_preamble():
    text = 'File {73-FA-25-8855} evaluation: {"key": "value"}'
    assert extract_json_block(text) == {"key": "value"}


def test_extract_json_multiple_fences_fallback():
    text = 'Bad:\n```json\n{bad_json\n```\nGood:\n```json\n{"key": "value"}\n```'
    assert extract_json_block(text) == {"key": "value"}


def test_extract_json_ignores_delimiters_inside_strings():
    text = 'Result: {"message": "literal } and [ text", "items": [1, 2]}'
    assert extract_json_block(text) == {
        "message": "literal } and [ text",
        "items": [1, 2],
    }


def test_extract_json_supports_unlabelled_fence():
    text = 'Result:\n```\n[{"a": 1}]\n```'
    assert extract_json_block(text) == [{"a": 1}]
