from __future__ import annotations

import pytest
from backend import storage

def test_derive_conversation_title_normal():
    # Derived from first message, normalized spaces
    content = "  Hello   world, this is a   test message!  "
    title = storage.derive_conversation_title(content)
    assert title == "Hello world, this is a test message!"

def test_derive_conversation_title_strips_quotes():
    # Strips surrounding double and single quotes
    assert storage.derive_conversation_title('"My Title"') == "My Title"
    assert storage.derive_conversation_title("'Another Title'") == "Another Title"
    assert storage.derive_conversation_title('"Mixed\'') == "Mixed"

def test_derive_conversation_title_truncation():
    # Truncates to 50 characters with ...
    long_content = "This is a very very long user message that should definitely be truncated because it exceeds fifty characters by a lot."
    title = storage.derive_conversation_title(long_content)
    assert len(title) <= 50
    assert title.endswith("...")
    assert title == "This is a very very long user message that shou..."

def test_derive_conversation_title_non_ascii():
    # Handles non-ASCII / Unicode characters correctly
    unicode_content = "💡 Hello 🤖 World 🚀 — Large Language Models"
    title = storage.derive_conversation_title(unicode_content)
    assert title == "💡 Hello 🤖 World 🚀 — Large Language Models"

def test_derive_conversation_title_edge_cases():
    # Empty, None, or pure whitespace content fallback
    assert storage.derive_conversation_title("") == "Untitled Conversation"
    assert storage.derive_conversation_title("   ") == "Untitled Conversation"
    assert storage.derive_conversation_title(None) == "Untitled Conversation"
    assert storage.derive_conversation_title(123) == "Untitled Conversation"

def test_maybe_repair_conversation_title_repairs_default():
    # Repairs default/empty titles when messages are present
    conversation = {
        "id": "test-uuid",
        "created_at": "2026-06-05T00:00:00Z",
        "title": "New Conversation",
        "messages": [
            {"role": "user", "content": "How do I repair titles?"},
            {"role": "assistant", "content": "Like this."}
        ]
    }
    repaired = storage.maybe_repair_conversation_title(conversation)
    assert repaired is True
    assert conversation["title"] == "How do I repair titles?"

def test_maybe_repair_conversation_title_preserves_explicit():
    # Preserves explicitly set titles
    conversation = {
        "id": "test-uuid",
        "created_at": "2026-06-05T00:00:00Z",
        "title": "My Custom Title",
        "messages": [
            {"role": "user", "content": "Overwrite this please."}
        ]
    }
    repaired = storage.maybe_repair_conversation_title(conversation)
    assert repaired is False
    assert conversation["title"] == "My Custom Title"

def test_maybe_repair_conversation_title_no_messages():
    # Does not repair if there are no user messages
    conversation = {
        "id": "test-uuid",
        "created_at": "2026-06-05T00:00:00Z",
        "title": "New Conversation",
        "messages": []
    }
    repaired = storage.maybe_repair_conversation_title(conversation)
    assert repaired is False
    assert conversation["title"] == "New Conversation"
