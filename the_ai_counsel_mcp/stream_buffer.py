"""SSE stream buffer — converts raw backend events into structured stage results."""

from __future__ import annotations
import asyncio


from collections.abc import AsyncIterator
from typing import Any

from backend.metadata_utils import metadata_used_search

from .errors import classify_http_error, classify_exception


def _classify_model_error(error: Any, error_message: str | None = None) -> dict | None:
    """Convert a model error value into a structured error dict, or None if no error."""
    if not error:
        return None
    msg = error_message or (str(error) if error is not True else "Unknown provider error")
    # Try to detect HTTP status codes embedded in the message
    for code in (429, 401, 403, 404):
        if str(code) in msg:
            return classify_http_error(code, msg)
    return classify_exception(Exception(msg))


def _build_stage1_result(conversation_id: str, query: str, stage1_data: list, search: dict) -> dict:
    """Build the Stage 1 response dict from accumulated events."""
    results = []
    for item in stage1_data:
        model = item.get("model", "unknown")
        response = item.get("response")
        error = item.get("error")
        error_message = item.get("error_message")

        if error:
            error_info = _classify_model_error(error, error_message)
            results.append({
                "model": model,
                "response": None,
                "status": "error",
                "error": error_info,
                "usage": item.get("usage"),
                "cost": item.get("cost"),
            })
        else:
            results.append({
                "model": model,
                "response": response,
                "status": "success",
                "usage": item.get("usage"),
                "cost": item.get("cost"),
            })

    succeeded = sum(1 for r in results if r["status"] == "success")
    return {
        "conversation_id": conversation_id,
        "query": query,
        "web_search": metadata_used_search(search),
        "search_context": search.get("search_context"),
        "results": results,
        "summary": {"total": len(results), "succeeded": succeeded, "failed": len(results) - succeeded},
    }


def _build_stage2_result(conversation_id: str, stage2_data: list, metadata: dict) -> dict:
    """Build the Stage 2 response dict from accumulated events."""
    rankings = []
    for item in stage2_data:
        model = item.get("model", "unknown")
        error = item.get("error")
        if error:
            rankings.append({
                "model": model,
                "ranking_text": None,
                "parsed_ranking": [],
                "status": "error",
                "error": _classify_model_error(error),
                "usage": item.get("usage"),
                "cost": item.get("cost"),
            })
        else:
            rankings.append({
                "model": model,
                "ranking_text": item.get("ranking"),
                "parsed_ranking": item.get("parsed_ranking", []),
                "status": "success",
                "usage": item.get("usage"),
                "cost": item.get("cost"),
            })
    return {
        "conversation_id": conversation_id,
        "label_to_model": metadata.get("label_to_model", {}),
        "rankings": rankings,
        "aggregate_rankings": metadata.get("aggregate_rankings", []),
    }


def _build_stage3_result(conversation_id: str, stage3_data: dict) -> dict:
    """Build the Stage 3 response dict."""
    error = stage3_data.get("error")
    return {
        "conversation_id": conversation_id,
        "chairman_model": stage3_data.get("model", "unknown"),
        "synthesis": stage3_data.get("response") if not error else None,
        "status": "error" if error else "success",
        "error": _classify_model_error(error, stage3_data.get("error_message")) if error else None,
        "usage": stage3_data.get("usage"),
        "cost": stage3_data.get("cost"),
    }


async def _drain_to_list(events: AsyncIterator[dict]) -> list[dict]:
    """Drain an async iterator into a plain list."""
    return [event async for event in events]


async def _events_from_list(events: list[dict]) -> AsyncIterator[dict]:
    """Wrap a list as an async generator."""
    for event in events:
        yield event


async def wrap_with_progress(events: AsyncIterator[dict]) -> AsyncIterator[dict]:
    """
    Wrap an event stream, emitting MCP progress notifications in the background.
    This continuous heartbeat prevents client-side timeouts (e.g., 60 seconds)
    during long-running, silent deliberations (like stage 2 ranking).
    """
    try:
        from mcp.server.lowlevel.server import request_ctx
        ctx = request_ctx.get()
        progress_token = ctx.meta.progressToken if ctx.meta else None
    except LookupError:
        # Not running inside an active MCP request context (e.g., unit tests)
        ctx = None
        progress_token = None

    if not ctx:
        async for event in events:
            yield event
        return

    # Background heartbeat task to prevent 60s client timeouts during silent inference.
    # Uses send_log_message (no progressToken required) so the heartbeat fires even when
    # the MCP client does not provide a progressToken in its tool call.
    async def heartbeat():
        while True:
            await asyncio.sleep(10)
            try:
                if progress_token:
                    await ctx.session.send_progress_notification(
                        progress_token=progress_token,
                        progress=0.5,
                        message="Deliberating...",
                    )
                else:
                    await ctx.session.send_log_message(
                        level="debug",
                        data="deliberation in progress",
                    )
            except Exception:
                # Connection closed or session destroyed, stop heartbeat
                break

    task = asyncio.create_task(heartbeat())
    try:
        async for event in events:
            yield event
    finally:
        task.cancel()


async def buffer_stage1(
    events: AsyncIterator[dict],
    conversation_id: str,
    query: str,
) -> tuple[dict, AsyncIterator[dict]]:
    """
    Consume all events from the stream, find stage1_complete, then return:
    - The structured Stage 1 result dict
    - An async iterator over the remaining events (everything after stage1_complete)

    Drains the full event list first so the iterator is not partially consumed
    when passed to buffer_stage2 or buffer_stage3.
    """
    all_events = await _drain_to_list(events)

    search_info: dict = {}
    stage1_data: list[dict] = []
    complete_index: int | None = None

    for i, event in enumerate(all_events):
        event_type = event.get("type")

        if event_type == "search_complete":
            search_info = event.get("data", {})
        elif event_type == "stage1_progress":
            # Accumulate incrementally as a fallback if stage1_complete is absent
            stage1_data.append(event.get("data", {}))
        elif event_type == "stage1_complete":
            # Authoritative full list supersedes incremental accumulation
            stage1_data = event.get("data", stage1_data)
            complete_index = i
            break
        elif event_type in ("error", "complete"):
            # Stream ended early — stop here; include this event in remaining
            complete_index = i - 1
            break

    remaining_start = (complete_index + 1) if complete_index is not None else len(all_events)
    result = _build_stage1_result(conversation_id, query, stage1_data, search_info)
    return result, _events_from_list(all_events[remaining_start:])


async def buffer_stage2(
    events: AsyncIterator[dict],
    conversation_id: str,
) -> tuple[dict, AsyncIterator[dict]]:
    """
    Consume all events from the stream, find stage2_complete, then return:
    - The structured Stage 2 result dict
    - An async iterator over the remaining events (everything after stage2_complete)
    """
    all_events = await _drain_to_list(events)

    stage2_data: list[dict] = []
    metadata: dict = {}
    complete_index: int | None = None

    for i, event in enumerate(all_events):
        event_type = event.get("type")

        if event_type == "stage2_progress":
            stage2_data.append(event.get("data", {}))
        elif event_type == "stage2_complete":
            stage2_data = event.get("data", stage2_data)
            metadata = event.get("metadata", {})
            complete_index = i
            break
        elif event_type in ("error", "complete"):
            complete_index = i - 1
            break

    remaining_start = (complete_index + 1) if complete_index is not None else len(all_events)
    result = _build_stage2_result(conversation_id, stage2_data, metadata)
    return result, _events_from_list(all_events[remaining_start:])


async def buffer_debate(events: AsyncIterator[dict], conversation_id: str) -> dict:
    """
    Consume all events from an advisor debate SSE stream.

    Returns a structured dict containing rounds, verdict, tiebreaker, personas,
    and web-search info. Prefers the authoritative advisor_complete event but
    falls back to per-event accumulation if the stream ends prematurely.
    """
    all_events = await _drain_to_list(events)

    # Accumulated state
    web_search: dict | None = None
    search_provider: str | None = None
    personas: list[dict] = []
    rounds_acc: dict[int, dict] = {}   # round_number -> {round, responses}
    tiebreaker: dict | None = None
    verdict: dict | None = None
    consensus_reached: bool = False
    consensus_round: int | None = None
    round_extracts: list[dict] = []
    cost_report: dict | None = None
    question: str = ""

    for event in all_events:
        etype = event.get("type")

        if etype == "advisor_search_start":
            search_provider = event.get("data", {}).get("provider")

        elif etype == "advisor_search_complete":
            query = event.get("data", {}).get("search_query", "")
            web_search = {"provider": search_provider or "unknown", "query": query}

        elif etype == "advisor_debate_start":
            data = event.get("data", {})
            personas = data.get("personas", [])
            question = data.get("question", "")

        elif etype == "advisor_round_start":
            rnum = event.get("data", {}).get("round_number", 1)
            if rnum not in rounds_acc:
                rounds_acc[rnum] = {"round": rnum, "responses": []}

        elif etype == "advisor_response":
            rnum = event.get("round", 1)
            resp_data = event.get("data", {})
            if rnum not in rounds_acc:
                rounds_acc[rnum] = {"round": rnum, "responses": []}
            rounds_acc[rnum]["responses"].append(resp_data)

        elif etype == "advisor_round_complete":
            data = event.get("data", {})
            rnum = data.get("round_number", 1)
            consensus_reached = data.get("consensus_reached", False)
            if consensus_reached:
                consensus_round = rnum
            # Authoritative responses for this round
            rounds_acc[rnum] = {
                "round": rnum,
                "responses": data.get("responses", []),
                "consensus_scores": data.get("consensus_scores", {}),
                "average_consensus_score": data.get("average_consensus_score"),
            }

        elif etype == "advisor_tiebreaker":
            tiebreaker = event.get("data")

        elif etype == "advisor_verdict":
            verdict = event.get("data")

        elif etype == "advisor_complete":
            # Authoritative final event — overrides all accumulated data
            data = event.get("data", {})
            stored_rounds = data.get("rounds", [])
            rounds_acc = {
                r["round_number"]: {
                    "round": r["round_number"],
                    "responses": r.get("responses", []),
                    "consensus_scores": r.get("consensus_scores", {}),
                    "average_consensus_score": r.get("average_consensus_score"),
                }
                for r in stored_rounds
            }
            consensus_reached = data.get("consensus_reached", False)
            consensus_round = data.get("consensus_round", consensus_round)
            round_extracts = data.get("round_extracts", round_extracts)
            if data.get("tiebreaker"):
                tiebreaker = data["tiebreaker"]
            if data.get("verdict"):
                verdict = data["verdict"]
            if data.get("personas"):
                personas = data["personas"]
            cost_report = data.get("cost_report")
            break

        elif etype == "advisor_error":
            return {
                "conversation_id": conversation_id,
                "status": "error",
                "error": {
                    "type": "provider_error",
                    "message": event.get("message", "Advisor debate failed"),
                    "retryable": False,
                },
            }

    rounds_list = [rounds_acc[k] for k in sorted(rounds_acc)]

    if verdict is None:
        return {
            "conversation_id": conversation_id,
            "status": "error",
            "error": {
                "type": "provider_error",
                "message": "Debate did not produce a verdict",
                "retryable": True,
            },
        }

    verdict_model = verdict.get("model", "unknown")
    return {
        "conversation_id": conversation_id,
        "question": question,
        "status": "success",
        "consensus_reached": consensus_reached,
        "consensus_round": consensus_round,
        "rounds_completed": len(rounds_list),
        "web_search": web_search,
        "personas": personas,
        "rounds": rounds_list,
        "round_extracts": round_extracts,
        "tiebreaker": tiebreaker,
        "verdict": verdict,
        "cost_report": cost_report,
        "summary": {
            "total_personas": len(personas),
            "rounds_run": len(rounds_list),
            "consensus": consensus_reached,
            "verdict_model": verdict_model,
        },
    }


async def buffer_stage3(events: AsyncIterator[dict], conversation_id: str) -> dict:
    """
    Consume events until stage3_complete or error, return Stage 3 result dict.
    Does not need to return a remaining iterator — Stage 3 is the final stage.
    """
    async for event in events:
        event_type = event.get("type")
        if event_type == "stage3_complete":
            return _build_stage3_result(conversation_id, event.get("data", {}))
        elif event_type == "error":
            return {
                "conversation_id": conversation_id,
                "chairman_model": "unknown",
                "synthesis": None,
                "status": "error",
                "error": {
                    "type": "provider_error",
                    "message": event.get("message", "Unknown error"),
                    "retryable": False,
                },
            }

    # Stream ended without stage3_complete
    return {
        "conversation_id": conversation_id,
        "chairman_model": "unknown",
        "synthesis": None,
        "status": "error",
        "error": {
            "type": "provider_error",
            "message": "Stage 3 did not complete",
            "retryable": True,
        },
    }


async def buffer_iterative_debate(events: AsyncIterator[dict], conversation_id: str) -> dict:
    """Consume events until debate_complete or error, returning the full multi-round debate results."""
    all_events = await _drain_to_list(events)

    rounds = []
    stage4 = None
    cost_report = None
    converged = False
    critique_mode = "freeform"
    error_msg = None

    for event in all_events:
        etype = event.get("type")
        if etype == "debate_complete":
            rounds = event.get("rounds", rounds)
            stage4 = event.get("stage4", stage4)
            cost_report = event.get("cost_report", cost_report)
            converged = event.get("converged", converged)
            critique_mode = event.get("critique_mode", critique_mode)
            break
        elif etype == "convergence":
            converged = True
        elif etype == "stage4_complete":
            stage4 = event.get("data")
        elif etype == "error":
            error_msg = event.get("message", "Unknown error")
            break

    if error_msg:
        return {
            "conversation_id": conversation_id,
            "status": "error",
            "error": {
                "type": "provider_error",
                "message": error_msg,
                "retryable": False,
            }
        }

    return {
        "conversation_id": conversation_id,
        "status": "success",
        "critique_mode": critique_mode,
        "converged": converged,
        "rounds": rounds,
        "stage4": stage4,
        "cost_report": cost_report,
    }
