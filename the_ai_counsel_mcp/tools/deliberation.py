"""Council deliberation and direct model chat MCP tools."""

from __future__ import annotations

import json

from ..client import CouncilClient
from ..stream_buffer import buffer_stage1, buffer_stage2, buffer_stage3, buffer_iterative_debate, wrap_with_progress


def _combine_cost_report(*stage_results: dict) -> dict:
    from backend.costs import summarize_buffered_stages

    return summarize_buffered_stages(*stage_results)


def register(server, base_url: str) -> None:
    """Register council_deliberate and model_chat tools."""

    @server.tool(description=(
        "Run council deliberation. action: 'stage1' (individual responses), "
        "'stage2' (peer rankings), 'stage3' (chairman synthesis only), "
        "'full' (all 3 stages). Pass conversation_id to continue a thread. "
        "web_search enriches the query. models overrides council members for 'full' only. "
        "Results include usage/cost details and a cost_report."
    ))
    async def council_deliberate(
        action: str,
        query: str,
        web_search: bool = False,
        conversation_id: str | None = None,
        models: list[str] | None = None,
        documents: list[dict] | None = None,
    ) -> str:
        action = action.strip().lower()
        if action not in ("stage1", "stage2", "stage3", "full"):
            return "Error: action must be stage1, stage2, stage3, or full."

        try:
            async with CouncilClient(base_url) as client:
                prepared_documents = await client.prepare_documents(documents)
                if not conversation_id:
                    conv = await client.create_conversation()
                    conversation_id = conv["id"]

                if action == "stage1":
                    events = client.stream_message(
                        conversation_id, query, web_search=web_search, execution_mode="chat_only",
                        documents=prepared_documents,
                    )
                    events = wrap_with_progress(events)
                    result, _ = await buffer_stage1(events, conversation_id, query)
                    result["cost_report"] = _combine_cost_report(result)
                    return json.dumps(result, indent=2)

                if action == "stage2":
                    events = client.stream_message(
                        conversation_id, query, web_search=False, execution_mode="chat_ranking",
                        documents=prepared_documents,
                    )
                    events = wrap_with_progress(events)
                    _, remaining = await buffer_stage1(events, conversation_id, query)
                    result, _ = await buffer_stage2(remaining, conversation_id)
                    result["cost_report"] = _combine_cost_report(result)
                    return json.dumps(result, indent=2)

                if action == "stage3":
                    events = client.stream_message(
                        conversation_id, query, web_search=False, execution_mode="full",
                        documents=prepared_documents,
                    )
                    events = wrap_with_progress(events)
                    _, after1 = await buffer_stage1(events, conversation_id, query)
                    _, after2 = await buffer_stage2(after1, conversation_id)
                    result = await buffer_stage3(after2, conversation_id)
                    result["cost_report"] = _combine_cost_report(result)
                    return json.dumps(result, indent=2)

                events = client.stream_message(
                    conversation_id, query,
                    web_search=web_search, execution_mode="full",
                    council_models=models,
                    documents=prepared_documents,
                )
                events = wrap_with_progress(events)
                stage1, after1 = await buffer_stage1(events, conversation_id, query)
                stage2, after2 = await buffer_stage2(after1, conversation_id)
                stage3 = await buffer_stage3(after2, conversation_id)

            return json.dumps({
                "conversation_id": conversation_id,
                "query": query,
                "stage1": stage1,
                "stage2": stage2,
                "stage3": stage3,
                "chairman_answer": stage3.get("synthesis"),
                "cost_report": _combine_cost_report(stage1, stage2, stage3),
            }, indent=2)
        except Exception as exc:
            return json.dumps({"status": "error", "message": str(exc)}, indent=2)

    @server.tool(description=(
        "Chat with a single model. action: 'quick' (one-shot, saved with no prior memory) or "
        "'multi_turn' (pass conversation_id from prior response to continue). "
        "model must include provider prefix, e.g. openai:gpt-4.1 or ollama:llama3. "
        "Results include usage/cost details and a cost_report."
    ))
    async def model_chat(
        action: str,
        query: str,
        model: str,
        conversation_id: str | None = None,
        web_search: bool = False,
        documents: list[dict] | None = None,
    ) -> str:
        action = action.strip().lower()
        if action not in ("quick", "multi_turn"):
            return "Error: action must be quick or multi_turn."

        try:
            async with CouncilClient(base_url) as client:
                prepared_documents = await client.prepare_documents(documents)
                if action == "quick":
                    result = await client.ask(
                        content=query,
                        models=[model],
                        web_search=web_search,
                        execution_mode="chat_only",
                        documents=prepared_documents,
                    )
                    return json.dumps({
                        "conversation_id": result.get("conversation_id"),
                        "model": result.get("model", model),
                        "response": result.get("response"),
                        "error": result.get("error"),
                        "usage": result.get("usage"),
                        "cost": result.get("cost"),
                        "cost_report": result.get("cost_report"),
                        "web_search_used": web_search,
                    }, indent=2)

                if not conversation_id:
                    conv = await client.create_conversation()
                    conversation_id = conv["id"]
                events = client.stream_message(
                    conversation_id, query,
                    web_search=web_search, execution_mode="chat_only",
                    council_models=[model],
                    documents=prepared_documents,
                )
                result, _ = await buffer_stage1(events, conversation_id, query)

            responses = result.get("results", [])
            first = responses[0] if responses else {}
            return json.dumps({
                "conversation_id": conversation_id,
                "model": first.get("model", model),
                "response": first.get("response"),
                "error": first.get("error"),
                "usage": first.get("usage"),
                "cost": first.get("cost"),
                "cost_report": _combine_cost_report(result),
                "web_search_used": web_search,
            }, indent=2)
        except Exception as exc:
            return json.dumps({"status": "error", "message": str(exc)}, indent=2)

    @server.tool(description=(
        "Run a multi-round iterative debate with convergence detection. "
        "Models debate across rounds, refining answers based on peer feedback. "
        "Supports 3 critique modes: 'freeform' (default), 'paragraph' (per-paragraph), "
        "and 'claim' (per-claim with canonical claim extraction). "
        "Returns all rounds data plus the chairman's corrected draft (Stage 4). "
        "Results include a cost_report. "
        "Set debate_rounds (1-5, default from settings) for number of rounds. "
        "auto_converge (bool) stops early if rankings stabilize; "
        "convergence_threshold (1-3) sets how many stable rounds trigger early stop."
    ))
    async def run_iterative_debate(
        query: str,
        debate_rounds: int | None = None,
        critique_mode: str | None = None,
        auto_converge: bool | None = None,
        convergence_threshold: int | None = None,
        web_search: bool = False,
        models: list[str] | None = None,
        documents: list[dict] | None = None,
    ) -> str:
        try:
            async with CouncilClient(base_url) as client:
                prepared_documents = await client.prepare_documents(documents)
                settings_patch = {}
                if critique_mode:
                    critique_mode = critique_mode.strip().lower()
                    if critique_mode not in ("freeform", "paragraph", "claim"):
                        return "Error: critique_mode must be freeform, paragraph, or claim."
                    settings_patch["critique_mode"] = critique_mode
                if auto_converge is not None:
                    settings_patch["auto_converge"] = auto_converge
                if convergence_threshold is not None:
                    if not (1 <= convergence_threshold <= 3):
                        return "Error: convergence_threshold must be 1, 2, or 3."
                    settings_patch["convergence_threshold"] = convergence_threshold
                if settings_patch:
                    await client.update_settings(**settings_patch)

                conv = await client.create_conversation()
                conversation_id = conv["id"]

                events = client.stream_debate_message(
                    conversation_id,
                    query,
                    web_search=web_search,
                    execution_mode="full",
                    council_models=models,
                    debate_rounds=debate_rounds,
                    documents=prepared_documents,
                )
                events = wrap_with_progress(events)

                result = await buffer_iterative_debate(events, conversation_id)
                return json.dumps(result, indent=2)
        except Exception as exc:
            return json.dumps({"status": "error", "message": str(exc)}, indent=2)
