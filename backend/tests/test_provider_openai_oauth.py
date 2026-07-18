"""ChatGPT OAuth Responses provider mapping."""

from backend.providers.openai_oauth import (
    CHATGPT_CODEX_UNSUPPORTED,
    _extract_responses_text,
    _messages_to_responses_input,
)


def test_messages_to_responses_splits_system():
    instructions, items = _messages_to_responses_input(
        [
            {"role": "system", "content": "Be brief"},
            {"role": "user", "content": "Hello"},
        ]
    )
    assert instructions == "Be brief"
    assert items[0]["role"] == "user"
    assert items[0]["content"][0]["text"] == "Hello"


def test_extract_output_text():
    assert _extract_responses_text({"output_text": "hi"}) == "hi"
    assert (
        _extract_responses_text(
            {
                "output": [
                    {"content": [{"type": "output_text", "text": "a"}, {"text": "b"}]}
                ]
            }
        )
        == "ab"
    )


def test_luna_unsupported():
    assert "gpt-5.6-luna" in CHATGPT_CODEX_UNSUPPORTED
