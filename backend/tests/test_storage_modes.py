import json

from backend import storage


def test_save_conversation_infers_advisor_mode_from_message(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))

    conversation = storage.create_conversation("conv-1", mode="council")
    conversation["messages"].append({
        "role": "assistant",
        "rounds": [{"round_number": 1, "responses": []}],
        "verdict": {"content": "Decision"},
        "personas": [],
    })

    storage.save_conversation(conversation)

    saved = storage.get_conversation("conv-1")
    listed = storage.list_conversations()

    assert saved["mode"] == "advisors"
    assert listed[0]["mode"] == "advisors"


def test_rebuild_index_infers_advisor_mode_for_older_records(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "legacy.json").write_text(json.dumps({
        "id": "legacy",
        "created_at": "2026-06-02T00:00:00+00:00",
        "title": "Legacy Advisor",
        "messages": [
            {
                "role": "assistant",
                "rounds": [{"round_number": 1, "responses": []}],
                "metadata": {"persona_ids": ["skeptic", "pragmatist"]},
            }
        ],
    }))

    index = storage.rebuild_index()

    assert index[0]["mode"] == "advisors"


def test_rebuild_index_skips_non_conversation_json(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "model_pricing_cache.json").write_text(json.dumps({
        "openai:gpt-test": {"input": 1, "output": 1}
    }))
    (tmp_path / "conversation.json").write_text(json.dumps({
        "id": "conversation",
        "created_at": "2026-06-02T00:00:00+00:00",
        "title": "Valid",
        "messages": [],
    }))

    index = storage.rebuild_index()

    assert len(index) == 1
    assert index[0]["id"] == "conversation"


def test_add_user_message_stores_attachment_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    conversation = storage.create_conversation("conv-attachments")

    storage.add_user_message(
        conversation["id"],
        "Analyze this.",
        attachments=[{
            "name": "report.pdf",
            "mime_type": "application/pdf",
            "char_count": 123,
            "truncated": False,
            "ocr_used": False,
            "page_count": 1,
            "warnings": [],
        }],
    )

    loaded = storage.get_conversation(conversation["id"])
    msg = loaded["messages"][0]
    assert msg["attachments"][0]["name"] == "report.pdf"
    assert "text" not in msg["attachments"][0]
