"""Advisor debate, settings, and persona MCP tools."""

from __future__ import annotations

import json
from typing import Any

from ..client import CouncilClient
from .. import presets as preset_ops
from ..stream_buffer import buffer_debate, wrap_with_progress

VALID_PERSONA_IDS = (
    "skeptic, pragmatist, innovator, historian, ethicist, analyst, contrarian, "
    "strategist, humanist, risk-assessor, comedian, economist"
)


def register(server: Any, base_url: str) -> None:
    """Register advisor_debate, advisor_settings, and personas tools."""

    @server.tool(description=(
        "Run a named-persona advisor debate for decisions, risks, strategy, or tradeoffs. "
        "Requires question + 2-4 persona_ids. Optional: default_model, "
        "model_assignments, max_rounds (3-10), search_provider. Results include "
        "usage/cost details, word-limit warnings, and a cost_report."
    ))
    async def advisor_debate(
        question: str,
        persona_ids: list[str],
        default_model: str | None = None,
        model_assignments: dict | None = None,
        max_rounds: int = 3,
        search_provider: str | None = None,
        documents: list[dict] | None = None,
    ) -> str:
        if len(persona_ids) < 2:
            return "Error: at least 2 persona_ids are required."
        if len(persona_ids) > 4:
            return "Error: at most 4 persona_ids are supported."
        if not 3 <= max_rounds <= 10:
            return "Error: max_rounds must be between 3 and 10."

        try:
            async with CouncilClient(base_url) as client:
                prepared_documents = await client.prepare_documents(documents)
                conv = await client.create_conversation()
                conversation_id = conv["id"]
                events = client.stream_debate(
                    conversation_id=conversation_id,
                    question=question,
                    persona_ids=persona_ids,
                    default_model=default_model,
                    model_assignments=model_assignments,
                    max_rounds=max_rounds,
                    search_provider=search_provider,
                    documents=prepared_documents,
                )
                events = wrap_with_progress(events)
                result = await buffer_debate(events, conversation_id)
            return json.dumps(result, indent=2)
        except Exception as exc:
            return json.dumps({
                "status": "error",
                "error": {"type": "network_error", "message": str(exc), "retryable": True},
            }, indent=2)

    @server.tool(description=(
        "Manage advisor configuration. action: 'get', 'update', 'list_presets', "
        "'save_preset', 'delete_preset', 'set_default_preset'. "
        "save_preset requires preset_name + persona_ids (2-4)."
    ))
    async def advisor_settings(
        action: str,
        default_model: str | None = None,
        tiebreaker_model: str | None = None,
        temperature: float | None = None,
        default_rounds: int | None = None,
        preset_id: str | None = None,
        preset_name: str | None = None,
        persona_ids: list[str] | None = None,
        mode: str | None = None,
        model_assignments: dict[str, str] | None = None,
        max_rounds: int | None = None,
        search_provider: str | None = None,
        is_default: bool = False,
    ) -> str:
        action = action.strip().lower()
        valid = ("get", "update", "list_presets", "save_preset", "delete_preset", "set_default_preset")
        if action not in valid:
            return f"Error: action must be one of: {', '.join(valid)}."

        try:
            async with CouncilClient(base_url) as client:
                if action == "get":
                    settings = await client.get_settings()
                    config = {
                        "advisor_default_model": settings.get("advisor_default_model", ""),
                        "advisor_tiebreaker_model": settings.get("advisor_tiebreaker_model", ""),
                        "advisor_temperature": settings.get("advisor_temperature", 0.7),
                        "advisor_default_rounds": settings.get("advisor_default_rounds", 3),
                        "advisor_presets": settings.get("advisor_presets", []),
                    }
                    return json.dumps(config, indent=2)

                if action == "list_presets":
                    items = await preset_ops.list_advisor_presets(client)
                    return json.dumps(items, indent=2)

                if action == "save_preset":
                    if not preset_name:
                        return "Error: preset_name is required for save_preset."
                    if not persona_ids or len(persona_ids) < 2:
                        return "Error: persona_ids (2-4) required for save_preset."
                    saved = await preset_ops.save_advisor_preset(
                        client,
                        name=preset_name,
                        persona_ids=persona_ids,
                        mode=mode or "simple",
                        default_model=default_model or "",
                        tiebreaker_model=tiebreaker_model or "",
                        model_assignments=model_assignments,
                        max_rounds=max_rounds or default_rounds or 3,
                        search_provider=search_provider,
                        preset_id=preset_id,
                        is_default=is_default,
                    )
                    return json.dumps({"status": "saved", "preset": saved}, indent=2)

                if action == "delete_preset":
                    if not preset_id:
                        return "Error: preset_id is required for delete_preset."
                    await preset_ops.delete_advisor_preset(client, preset_id)
                    return json.dumps({"status": "deleted", "preset_id": preset_id}, indent=2)

                if action == "set_default_preset":
                    if not preset_id:
                        return "Error: preset_id is required for set_default_preset."
                    preset = await preset_ops.set_default_advisor_preset(client, preset_id)
                    return json.dumps({"status": "default_set", "preset": preset}, indent=2)

                updates: dict[str, Any] = {}
                if default_model is not None:
                    updates["advisor_default_model"] = default_model
                if tiebreaker_model is not None:
                    updates["advisor_tiebreaker_model"] = tiebreaker_model
                if temperature is not None:
                    updates["advisor_temperature"] = temperature
                if default_rounds is not None:
                    if not 3 <= default_rounds <= 10:
                        return "Error: default_rounds must be between 3 and 10."
                    updates["advisor_default_rounds"] = default_rounds

                if not updates:
                    return "Error: no update fields provided."

                await client.update_settings(**updates)
                return json.dumps({"status": "updated", "fields": list(updates.keys())}, indent=2)
        except Exception as exc:
            return json.dumps({"status": "error", "message": str(exc)}, indent=2)

    @server.tool(description=(
        "Manage advisor personas. action: 'list', 'get', 'update', 'reset'. "
        f"Valid persona IDs: {VALID_PERSONA_IDS}."
    ))
    async def personas(
        action: str,
        persona_id: str | None = None,
        name: str | None = None,
        role: str | None = None,
        description: str | None = None,
        system_prompt: str | None = None,
        avatar_emoji: str | None = None,
    ) -> str:
        action = action.strip().lower()
        if action not in ("list", "get", "update", "reset"):
            return "Error: action must be list, get, update, or reset."

        try:
            async with CouncilClient(base_url) as client:
                if action == "list":
                    items = await client.get_personas()
                    return json.dumps(items, indent=2)

                if not persona_id:
                    return "Error: persona_id is required."

                if action == "get":
                    all_personas = await client.get_personas()
                    match = next((p for p in all_personas if p["id"] == persona_id), None)
                    if match is None:
                        return f"Persona '{persona_id}' not found."
                    return json.dumps(match, indent=2)

                if action == "reset":
                    restored = await client.reset_persona(persona_id)
                    return json.dumps(restored, indent=2)

                fields: dict[str, str] = {}
                if name is not None:
                    fields["name"] = name
                if role is not None:
                    fields["role"] = role
                if description is not None:
                    fields["description"] = description
                if system_prompt is not None:
                    fields["system_prompt"] = system_prompt
                if avatar_emoji is not None:
                    fields["avatar_emoji"] = avatar_emoji
                if not fields:
                    return "Error: provide at least one field to update."

                updated = await client.update_persona(persona_id, **fields)
                return json.dumps(updated, indent=2)
        except Exception as exc:
            return json.dumps({"status": "error", "message": str(exc)}, indent=2)
