import json

from backend import storage


def _save_titled_conversation(tmp_path, monkeypatch, conversation_id, title, messages):
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    conversation = {
        "id": conversation_id,
        "created_at": "2026-06-03T19:41:00+00:00",
        "title": title,
        "mode": "council",
        "messages": messages,
    }
    storage.save_conversation(conversation)
    return conversation


def test_run_summary_hidden_until_title_assigned(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    conversation = storage.create_conversation("draft", mode="council")
    conversation["messages"].append({
        "role": "assistant",
        "stage1": [],
        "metadata": {
            "execution_mode": "full",
            "debate_rounds_configured": 2,
            "critique_mode": "paragraph",
            "web_search": True,
        },
    })
    storage.save_conversation(conversation)

    listed = storage.list_conversations()
    assert "run_summary" not in listed[0]


def test_run_summary_council_debate(tmp_path, monkeypatch):
    _save_titled_conversation(
        tmp_path,
        monkeypatch,
        "council-1",
        "Remote-First vs Hybrid Policy",
        [{
            "role": "assistant",
            "stage1": [],
            "metadata": {
                "execution_mode": "full",
                "debate_rounds_configured": 2,
                "critique_mode": "paragraph",
                "auto_converge": True,
                "web_search": True,
            },
        }],
    )

    listed = storage.list_conversations()
    assert listed[0]["run_summary"] == "2 rnd · Paragraph · Auto-converge · Search"


def test_run_summary_advisor_debate(tmp_path, monkeypatch):
    _save_titled_conversation(
        tmp_path,
        monkeypatch,
        "adv-1",
        "Expand to Europe?",
        [{
            "role": "assistant",
            "mode": "advisors",
            "rounds": [{"round_number": 1}, {"round_number": 2}, {"round_number": 3}],
            "metadata": {
                "persona_ids": ["skeptic", "pragmatist", "innovator", "ethicist"],
                "max_rounds": 5,
                "rounds_executed": 3,
                "consensus_reached": True,
                "web_search": True,
            },
        }],
    )

    listed = storage.list_conversations()
    assert listed[0]["run_summary"] == "4 advisors · 3/5 rnd · Consensus · Search"


def test_rebuild_index_includes_run_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "legacy.json").write_text(json.dumps({
        "id": "legacy",
        "created_at": "2026-06-02T00:00:00+00:00",
        "title": "Legacy Council",
        "messages": [{
            "role": "assistant",
            "stage1": [],
            "metadata": {
                "execution_mode": "chat_only",
                "web_search": True,
            },
        }],
    }))

    index = storage.rebuild_index()
    assert index[0]["run_summary"] == "Chat Only · Search"


def test_run_summary_converged_early(tmp_path, monkeypatch):
    _save_titled_conversation(
        tmp_path,
        monkeypatch,
        "council-converged",
        "Budget Debate",
        [{
            "role": "assistant",
            "stage1": [],
            "metadata": {
                "execution_mode": "full",
                "debate_rounds_configured": 3,
                "debate_rounds_executed": 2,
                "critique_mode": "freeform",
                "auto_converge": True,
                "converged": True,
            },
        }],
    )

    listed = storage.list_conversations()
    assert listed[0]["run_summary"] == "2 rnd · Freeform · Auto-converge · Converged early"


def test_run_summary_search_context_only(tmp_path, monkeypatch):
    _save_titled_conversation(
        tmp_path,
        monkeypatch,
        "council-search-legacy",
        "Market Outlook",
        [{
            "role": "assistant",
            "stage1": [],
            "metadata": {
                "execution_mode": "chat_ranking",
                "search_context": {"results": []},
            },
        }],
    )

    listed = storage.list_conversations()
    assert listed[0]["run_summary"] == "Chat + Ranking · Search"


def test_run_summary_claim_critique_mode(tmp_path, monkeypatch):
    _save_titled_conversation(
        tmp_path,
        monkeypatch,
        "council-claim",
        "Policy Review",
        [{
            "role": "assistant",
            "stage1": [],
            "metadata": {
                "execution_mode": "full",
                "debate_rounds_configured": 1,
                "critique_mode": "claim",
            },
        }],
    )

    listed = storage.list_conversations()
    assert listed[0]["run_summary"] == "1 rnd · Claim-by-Claim (Legacy)"


def test_run_summary_full_deliberation_standard(tmp_path, monkeypatch):
    """Standard 3-stage council (non-debate) is one freeform round."""
    _save_titled_conversation(
        tmp_path,
        monkeypatch,
        "council-full",
        "SaaS Pricing Model Comparison",
        [{
            "role": "assistant",
            "stage1": [],
            "stage3": {"response": "done"},
            "metadata": {
                "execution_mode": "full",
                "web_search": True,
            },
        }],
    )

    listed = storage.list_conversations()
    assert listed[0]["run_summary"] == "1 rnd · Freeform · Search"


def test_run_summary_one_round_freeform_debate(tmp_path, monkeypatch):
    _save_titled_conversation(
        tmp_path,
        monkeypatch,
        "council-freeform-1",
        "Quick Debate",
        [{
            "role": "assistant",
            "stage1": [],
            "metadata": {
                "execution_mode": "full",
                "debate_rounds_configured": 1,
                "critique_mode": "freeform",
                "web_search": True,
            },
        }],
    )

    listed = storage.list_conversations()
    assert listed[0]["run_summary"] == "1 rnd · Freeform · Search"
