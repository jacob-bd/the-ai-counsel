"""JSON-based storage for conversations."""

import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path
from .config import DATA_DIR
from .metadata_utils import metadata_used_search


INDEX_FILE_NAME = "conversations_index.json"
VALID_CONVERSATION_MODES = {"council", "advisors"}
DEFAULT_CONVERSATION_TITLE = "New Conversation"

def is_default_conversation_title(title: Optional[str]) -> bool:
    """Check if the title is a default, placeholder, or empty title."""
    return not title or title in (DEFAULT_CONVERSATION_TITLE, "Untitled Conversation", "")

def derive_conversation_title(content: str) -> str:
    """Derive a short title from the first message content."""
    if not content or not isinstance(content, str):
        return "Untitled Conversation"
    # Normalize whitespace/newlines
    title = " ".join(content.split())
    if not title:
        return "Untitled Conversation"
    # Strip quotes
    title = title.strip('"\'')
    if len(title) > 50:
        title = title[:47].rstrip() + "..."
    return title

def maybe_repair_conversation_title(conversation: Dict[str, Any]) -> bool:
    """Repair conversation title if it is default/placeholder and has user messages."""
    current_title = conversation.get("title", DEFAULT_CONVERSATION_TITLE)
    if is_default_conversation_title(current_title):
        first_user_content = None
        for msg in conversation.get("messages", []):
            if msg.get("role") == "user" and msg.get("content"):
                first_user_content = msg["content"]
                break
        if first_user_content:
            conversation["title"] = derive_conversation_title(first_user_content)
            return True
    return False


# Keep in sync with frontend/src/constants/critiqueMode.js
CRITIQUE_MODE_LABELS = {
    "freeform": "Freeform",
    "paragraph": "Paragraph",
    "claim": "Claim-by-Claim",
}


def ensure_data_dir():
    """Ensure the data directory exists."""
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)


def get_conversation_path(conversation_id: str) -> str:
    """Get the file path for a conversation."""
    return os.path.join(DATA_DIR, f"{conversation_id}.json")


def get_index_path() -> str:
    """Get the file path for the conversation index."""
    return os.path.join(DATA_DIR, INDEX_FILE_NAME)


def _load_index() -> Optional[List[Dict[str, Any]]]:
    """Load the conversation index file."""
    path = get_index_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_index(index: List[Dict[str, Any]]):
    """Save the conversation index file."""
    ensure_data_dir()
    path = get_index_path()
    with open(path, 'w') as f:
        json.dump(index, f, indent=2)


def _normalize_conversation_mode(mode: Any) -> str:
    """Return a valid conversation mode, defaulting to council."""
    if isinstance(mode, str) and mode in VALID_CONVERSATION_MODES:
        return mode
    return "council"


def _message_is_advisor_debate(message: Dict[str, Any]) -> bool:
    """Detect advisor debate messages, including older records missing mode."""
    if message.get("mode") == "advisors" or message.get("type") == "advisor_debate":
        return True

    metadata = message.get("metadata") or {}
    has_advisor_metadata = any(
        key in metadata
        for key in ("persona_ids", "default_model", "tiebreaker_model", "model_assignments")
    )
    has_advisor_payload = (
        isinstance(message.get("rounds"), list)
        and (
            "verdict" in message
            or "tiebreaker" in message
            or "personas" in message
            or has_advisor_metadata
        )
    )
    return has_advisor_payload


def infer_conversation_mode(conversation: Dict[str, Any]) -> str:
    """Infer the conversation mode from explicit metadata and saved messages."""
    if any(_message_is_advisor_debate(msg) for msg in conversation.get("messages", [])):
        return "advisors"
    return _normalize_conversation_mode(conversation.get("mode"))


def _is_conversation_record(data: Any) -> bool:
    """Return whether a JSON object looks like a stored conversation."""
    return (
        isinstance(data, dict)
        and isinstance(data.get("id"), str)
        and isinstance(data.get("created_at"), str)
        and isinstance(data.get("messages"), list)
    )


def derive_run_summary(conversation: Dict[str, Any]) -> Optional[str]:
    """Build a compact sidebar summary from the latest assistant message."""
    if conversation.get("title", DEFAULT_CONVERSATION_TITLE) == DEFAULT_CONVERSATION_TITLE:
        return None

    message = None
    for msg in reversed(conversation.get("messages", [])):
        if msg.get("role") == "assistant" and not msg.get("error"):
            message = msg
            break
    if message is None:
        return None

    metadata = message.get("metadata") or {}
    parts: List[str] = []

    if _message_is_advisor_debate(message):
        persona_ids = metadata.get("persona_ids") or [
            persona.get("id")
            for persona in (message.get("personas") or [])
            if isinstance(persona, dict) and persona.get("id")
        ]
        if persona_ids:
            parts.append(f"{len(persona_ids)} advisors")

        rounds_executed = metadata.get("rounds_executed")
        if rounds_executed is None:
            rounds_executed = len(message.get("rounds") or [])
        max_rounds = metadata.get("max_rounds")
        if rounds_executed and max_rounds:
            parts.append(f"{rounds_executed}/{max_rounds} rnd")
        elif rounds_executed:
            parts.append(f"{rounds_executed} rnd")

        if metadata.get("consensus_reached"):
            parts.append("Consensus")
    else:
        execution_mode = metadata.get("execution_mode")
        critique_mode = metadata.get("critique_mode", "freeform")

        if execution_mode == "chat_only":
            parts.append("Chat Only")
        elif execution_mode == "chat_ranking":
            parts.append("Chat + Ranking")
        elif execution_mode == "full":
            rounds = (
                metadata.get("debate_rounds_executed")
                or metadata.get("debate_rounds_configured")
                or 1
            )
            parts.append(f"{rounds} rnd")
            parts.append(CRITIQUE_MODE_LABELS.get(critique_mode, critique_mode))
            if rounds > 1 and metadata.get("auto_converge"):
                parts.append("Auto-converge")
            if metadata.get("converged"):
                parts.append("Converged early")

    if metadata_used_search(metadata):
        parts.append("Search")

    return " · ".join(parts) if parts else None


def derive_conversation_cost(conversation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Sum cost_report totals across all assistant messages for sidebar display."""
    total_cost = 0.0
    has_any_cost = False
    has_unknown_costs = False
    has_estimates = False
    total_calls = 0

    for msg in conversation.get("messages", []):
        if msg.get("role") != "assistant" or msg.get("error"):
            continue
        report = (msg.get("metadata") or {}).get("cost_report")
        if not isinstance(report, dict):
            continue

        has_any_cost = True
        if report.get("has_unknown_costs"):
            has_unknown_costs = True
        if report.get("has_estimates"):
            has_estimates = True

        report_total = report.get("total_cost")
        if isinstance(report_total, (int, float)) and not isinstance(report_total, bool):
            total_cost += float(report_total)

        report_calls = report.get("total_calls")
        if isinstance(report_calls, int):
            total_calls += report_calls

    if not has_any_cost:
        return None

    if has_unknown_costs:
        cost_status = "partial"
    elif has_estimates:
        cost_status = "estimated"
    elif total_cost == 0:
        cost_status = "free"
    else:
        cost_status = "known"

    return {
        "total_cost": round(total_cost, 6),
        "cost_status": cost_status,
        "total_calls": total_calls,
    }


def _build_index_entry(
    conversation: Dict[str, Any],
    *,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    maybe_repair_conversation_title(conversation)
    entry = {
        "id": conversation["id"],
        "created_at": conversation["created_at"],
        "title": conversation.get("title", DEFAULT_CONVERSATION_TITLE),
        "mode": mode if mode is not None else infer_conversation_mode(conversation),
        "message_count": len(conversation["messages"]),
    }
    run_summary = derive_run_summary(conversation)
    if run_summary:
        entry["run_summary"] = run_summary
    cost = derive_conversation_cost(conversation)
    if cost:
        entry["total_cost"] = cost["total_cost"]
        entry["cost_status"] = cost["cost_status"]
        entry["total_calls"] = cost["total_calls"]
    return entry


def rebuild_index() -> List[Dict[str, Any]]:
    """
    Rebuild the conversation index from actual conversation files.
    Use this fallback if index is missing or corrupted.
    """
    ensure_data_dir()
    index = []
    
    for filename in os.listdir(DATA_DIR):
        if filename.endswith('.json') and filename != INDEX_FILE_NAME:
            path = os.path.join(DATA_DIR, filename)
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    if not _is_conversation_record(data):
                        continue
                    index.append(_build_index_entry(data))
            except (json.JSONDecodeError, OSError):
                continue

    # Sort by creation time, newest first
    index.sort(key=lambda x: x["created_at"], reverse=True)
    _save_index(index)
    return index


def _update_index_entry(conversation: Dict[str, Any], *, mode: Optional[str] = None):
    """Update or add a single entry in the index."""
    index = _load_index()
    if index is None:
        index = rebuild_index()
        return  # rebuild already includes the current state if file was saved

    entry = _build_index_entry(conversation, mode=mode)
    # Remove existing entry if present
    index = [item for item in index if item["id"] != conversation["id"]]
    
    # Add new entry
    index.append(entry)
    
    # Sort and save
    index.sort(key=lambda x: x["created_at"], reverse=True)
    _save_index(index)


def _remove_from_index(conversation_id: str):
    """Remove an entry from the index."""
    index = _load_index()
    if index is None:
        return  # No index to remove from

    # Filter out the deleted conversation
    new_index = [item for item in index if item["id"] != conversation_id]
    
    if len(new_index) != len(index):
        _save_index(new_index)


def create_conversation(conversation_id: str, mode: str = "council") -> Dict[str, Any]:
    """
    Create a new conversation.

    Args:
        conversation_id: Unique identifier for the conversation
        mode: Conversation mode — "council" or "advisors"

    Returns:
        New conversation dict
    """
    ensure_data_dir()

    conversation = {
        "id": conversation_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "title": "New Conversation",
        "mode": _normalize_conversation_mode(mode),
        "messages": []
    }

    # Save to file
    path = get_conversation_path(conversation_id)
    with open(path, 'w') as f:
        json.dump(conversation, f, indent=2)

    # Update index
    _update_index_entry(conversation, mode=conversation["mode"])

    return conversation


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """
    Load a conversation from storage.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        Conversation dict or None if not found
    """
    path = get_conversation_path(conversation_id)

    if not os.path.exists(path):
        return None

    with open(path, 'r') as f:
        conversation = json.load(f)
    if maybe_repair_conversation_title(conversation):
        # Save to persist the repaired title
        save_conversation(conversation)
    conversation["mode"] = infer_conversation_mode(conversation)
    return conversation


def save_conversation(conversation: Dict[str, Any]):
    """
    Save a conversation to storage.

    Args:
        conversation: Conversation dict to save
    """
    ensure_data_dir()
    conversation["mode"] = infer_conversation_mode(conversation)
    maybe_repair_conversation_title(conversation)

    path = get_conversation_path(conversation['id'])
    with open(path, 'w') as f:
        json.dump(conversation, f, indent=2)

    # Update index
    _update_index_entry(conversation, mode=conversation["mode"])


def list_conversations() -> List[Dict[str, Any]]:
    """
    List all conversations (metadata only).
    Uses cached index file for O(1) performance.

    Returns:
        List of conversation metadata dicts
    """
    ensure_data_dir()

    # Try to load from index first
    index = _load_index()
    
    # If index missing or invalid, rebuild it
    if index is None:
        return rebuild_index()
        
    return index


def add_user_message(conversation_id: str, content: str, conversation: Optional[Dict[str, Any]] = None):
    """Add a user message to a conversation.

    Args:
        conversation_id: Conversation identifier
        content: User message content
        conversation: Pre-loaded conversation dict (avoids redundant disk read)
    """
    if conversation is None:
        conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    # If this is the very first message in a reused empty draft, reset the creation date to now
    if len(conversation["messages"]) == 0:
        conversation["created_at"] = datetime.now(timezone.utc).isoformat()

    conversation["messages"].append({
        "role": "user",
        "content": content
    })

    save_conversation(conversation)


def add_assistant_message(
    conversation_id: str,
    stage1: List[Dict[str, Any]],
    stage2: Optional[List[Dict[str, Any]]] = None,
    stage3: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    conversation: Optional[Dict[str, Any]] = None
):
    """Add an assistant message to a conversation.

    Args:
        conversation_id: Conversation identifier
        stage1: List of individual model responses (always present)
        stage2: List of model rankings (None if execution_mode was 'chat_only')
        stage3: Final synthesized response (None if execution_mode was not 'full')
        metadata: Optional metadata including execution_mode, label_to_model, etc.
        conversation: Pre-loaded conversation dict (avoids redundant disk read)
    """
    if conversation is None:
        conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    message = {
        "role": "assistant",
        "stage1": stage1,
    }

    if stage2 is not None:
        message["stage2"] = stage2
    if stage3 is not None:
        message["stage3"] = stage3
    if metadata:
        message["metadata"] = metadata

    conversation["messages"].append(message)
    save_conversation(conversation)


def add_advisor_message(
    conversation_id: str,
    rounds: List[Dict[str, Any]],
    verdict: Optional[Dict[str, Any]] = None,
    tiebreaker: Optional[Dict[str, Any]] = None,
    personas: Optional[List[Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    conversation: Optional[Dict[str, Any]] = None
):
    """Add an advisor debate message to a conversation.

    Args:
        conversation_id: Conversation identifier
        rounds: List of round dicts, each with round_number and responses
        verdict: Structured verdict (summary, consensus, disagreements, etc.)
        tiebreaker: Tiebreaker result if vote was tied
        metadata: Optional metadata (persona_ids, models, etc.)
        conversation: Pre-loaded conversation dict (avoids redundant disk read)
    """
    if conversation is None:
        conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    message = {
        "role": "assistant",
        "mode": "advisors",
        "rounds": rounds,
    }

    if personas is not None:
        message["personas"] = personas
    if verdict is not None:
        message["verdict"] = verdict
    if tiebreaker is not None:
        message["tiebreaker"] = tiebreaker
    if metadata:
        message["metadata"] = metadata

    conversation["mode"] = "advisors"
    conversation["messages"].append(message)
    save_conversation(conversation)


def add_error_message(conversation_id: str, error_text: str):
    """
    Add an error message to a conversation to record a failed turn.

    Args:
        conversation_id: Conversation identifier
        error_text: The error description
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    message = {
        "role": "assistant",
        "content": None,
        "error": error_text,
        "stage1": [],
        "stage2": None,
        "stage3": None
    }

    conversation["messages"].append(message)
    save_conversation(conversation)


def update_conversation_title(conversation_id: str, title: str):
    """
    Update the title of a conversation.

    Args:
        conversation_id: Conversation identifier
        title: New title for the conversation
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["title"] = title
    save_conversation(conversation)


def delete_conversation(conversation_id: str) -> bool:
    """
    Delete a conversation.

    Args:
        conversation_id: Conversation identifier

    Returns:
        True if deleted, False if not found
    """
    path = get_conversation_path(conversation_id)

    if not os.path.exists(path):
        return False

    os.remove(path)
    
    # Update index
    _remove_from_index(conversation_id)
    
    return True
