"""LLM Advisors debate orchestrator."""

import asyncio
import logging
import re
from typing import List, Dict, Any, Optional

from .council import query_model
from .costs import build_advisor_cost_report
from .model_preflight import build_preflight_error_message, preflight_models
from .personas import get_personas_by_ids, Persona
from .settings import get_settings
from .advisor_prompts import (
    ADVISOR_ROUND1_PROMPT,
    ADVISOR_FOLLOWUP_PROMPT,
    ADVISOR_CROSS_POLLINATION_PROMPT,
    ADVISOR_VERDICT_PROMPT,
    ADVISOR_TIEBREAKER_PROMPT,
    CONSENSUS_TAG_INSTRUCTION,
)

logger = logging.getLogger(__name__)


def parse_consensus_tag(content: str) -> Optional[int]:
    """Extract CONSENSUS_SCORE: 1-5 from the end of a response."""
    if not content:
        return None
    match = re.search(r"CONSENSUS_SCORE:\s*\[?([1-5])\]?\s*$", content.strip(), re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def strip_consensus_tag(content: str) -> str:
    """Remove the CONSENSUS_SCORE tag from the response for display."""
    if not content:
        return content
    return re.sub(r"\n*CONSENSUS_SCORE:\s*\[?[1-5]\]?\s*$", "", content.strip(), flags=re.IGNORECASE).strip()


def build_rotation_order(persona_ids: List[str], round_number: int) -> List[str]:
    """Rotate speaking order for each round. Round 1 = original order, Round 2 = shift left by 1, etc."""
    n = len(persona_ids)
    shift = (round_number - 1) % n
    return persona_ids[shift:] + persona_ids[:shift]


def _format_transcript(rounds: List[Dict[str, Any]], personas: Dict[str, Persona]) -> str:
    """Format the debate transcript for injection into prompts."""
    lines = []
    for r in rounds:
        lines.append(f"--- Round {r['round_number']} ---")
        for resp in r["responses"]:
            p = personas.get(resp["persona_id"])
            name = p.name if p else resp["persona_id"]
            role = p.role if p else ""
            lines.append(f"\n{name} ({role}):\n{resp['content']}")
    return "\n".join(lines)


def _average_consensus_score(scores: Dict[str, Optional[int]]) -> Optional[float]:
    numeric_scores = [score for score in scores.values() if isinstance(score, int)]
    if not numeric_scores:
        return None
    return round(sum(numeric_scores) / len(numeric_scores), 2)


def _count_words(content: str) -> int:
    """Count display words for advisor response limit enforcement."""
    if not content:
        return 0
    return len(re.findall(r"\b[\w'-]+\b", content))


def _settings_prompt(settings: Any, key: str, default: str) -> str:
    """Return a saved prompt template, falling back to the built-in default."""
    prompt = getattr(settings, key, None)
    if isinstance(prompt, str) and prompt.strip():
        return prompt
    return default


def _format_debate_arc(
    all_rounds: List[Dict[str, Any]],
    personas: Dict[str, Persona],
    round_extracts: List[Dict[str, Any]],
    consensus_reached: bool,
    consensus_round: Optional[int],
) -> str:
    """Build a compact debate-arc signal for the verdict model."""
    if not all_rounds:
        return "No completed rounds."

    first_round = all_rounds[0]
    final_round = all_rounds[-1]
    first_extract = round_extracts[0]["content"] if round_extracts else "No distilled Round 1 summary was produced."

    lines = [
        f"Consensus reached: {'yes' if consensus_reached else 'no'}",
        f"Consensus round: {consensus_round if consensus_round else 'none'}",
        f"Final round average consensus score: {final_round.get('average_consensus_score')}",
        "",
        "Round 1 summary:",
        first_extract,
        "",
        "Final round summary:",
    ]

    for resp in final_round.get("responses", []):
        pid = resp["persona_id"]
        persona = personas.get(pid)
        name = persona.name if persona else resp.get("persona_name", pid)
        content = (resp.get("content") or "").strip().replace("\n", " ")
        summary = content[:300] + ("..." if len(content) > 300 else "")
        lines.append(
            f"- {name}: {summary} Final consensus score: {resp.get('consensus_score')}"
        )

    lines.extend(["", "Starting vs final positions:"])
    first_by_pid = {resp["persona_id"]: resp for resp in first_round.get("responses", [])}
    final_by_pid = {resp["persona_id"]: resp for resp in final_round.get("responses", [])}
    for pid, final_resp in final_by_pid.items():
        persona = personas.get(pid)
        name = persona.name if persona else final_resp.get("persona_name", pid)
        start = (first_by_pid.get(pid, {}).get("content") or "").strip().replace("\n", " ")
        final = (final_resp.get("content") or "").strip().replace("\n", " ")
        start_summary = start[:220] + ("..." if len(start) > 220 else "")
        final_summary = final[:220] + ("..." if len(final) > 220 else "")
        lines.append(
            f"- {name}: starting position: {start_summary}; "
            f"final position: {final_summary}; Final consensus score: {final_resp.get('consensus_score')}"
        )

    return "\n".join(lines)


def _resolve_model(
    persona_id: str,
    model_assignments: Optional[Dict[str, str]],
    default_model: str,
) -> str:
    """Determine which model to use for a given persona."""
    if model_assignments and persona_id in model_assignments:
        return model_assignments[persona_id]
    return default_model


async def _query_advisor(
    pid: str,
    prompt: str,
    personas_map: Dict[str, Persona],
    model_assignments: Optional[Dict[str, str]],
    default_model: str,
    temperature: float,
) -> tuple:
    persona = personas_map[pid]
    model = _resolve_model(pid, model_assignments, default_model)
    messages = [
        {"role": "system", "content": persona.system_prompt},
        {"role": "user", "content": prompt},
    ]
    try:
        result = await query_model(model, messages, temperature=temperature)
        if result.get("error"):
            return pid, model, None, result.get("error_message", "Model error"), result.get("usage"), result.get("cost")
        return pid, model, result.get("content", ""), None, result.get("usage"), result.get("cost")
    except Exception as e:
        return pid, model, None, str(e), None, None


def _unpack_advisor_result(result: tuple) -> tuple:
    """Accept old four-field test doubles while using six fields in production."""
    if len(result) == 4:
        pid, model, content, error = result
        return pid, model, content, error, None, None
    return result


async def _query_neutral(model: str, prompt: str, temperature: float = 0.3) -> Dict[str, Any]:
    """Call a neutral (non-persona) model and return a normalized result dict."""
    try:
        response = await query_model(model, [{"role": "user", "content": prompt}], temperature=temperature)
        if response.get("error"):
            return {
                "model": model,
                "content": None,
                "error": response.get("error_message"),
                "usage": response.get("usage"),
                "cost": response.get("cost"),
            }
        return {
            "model": model,
            "content": response.get("content", ""),
            "error": None,
            "usage": response.get("usage"),
            "cost": response.get("cost"),
        }
    except Exception as e:
        return {"model": model, "content": None, "error": str(e), "usage": None, "cost": None}


async def run_debate(
    question: str,
    persona_ids: List[str],
    model_assignments: Optional[Dict[str, str]] = None,
    default_model: Optional[str] = None,
    tiebreaker_model: Optional[str] = None,
    max_rounds: int = 3,
    web_search: bool = False,
    search_context: str = "",
    request: Any = None,
    preflight: bool = False,
):
    """
    Run a multi-round advisor debate.

    Async generator yielding SSE-compatible event dicts.

    Args:
        question: The question to debate
        persona_ids: List of persona IDs to participate (2-4)
        model_assignments: Optional per-persona model mapping
        default_model: Fallback model for all personas
        max_rounds: Maximum debate rounds (3-10)
        web_search: Whether web search was used
        search_context: Pre-fetched search results
        request: FastAPI request for disconnect detection
    """
    settings = get_settings()
    temperature = settings.advisor_temperature

    if not default_model:
        default_model = settings.advisor_default_model
    if not default_model:
        yield {"type": "advisor_error", "message": "No advisor model configured. Set a default model in Settings."}
        return
    if max_rounds < 3 or max_rounds > 10:
        yield {"type": "advisor_error", "message": "Rounds must be between 3 and 10."}
        return

    personas_list = get_personas_by_ids(persona_ids)
    if len(personas_list) < 2:
        yield {"type": "advisor_error", "message": "At least 2 valid advisors required."}
        return

    personas_map = {p.id: p for p in personas_list}
    personas_serialized = []
    for p in personas_list:
        p_dict = p.model_dump()
        p_dict["model"] = _resolve_model(p.id, model_assignments, default_model)
        personas_serialized.append(p_dict)
    verdict_model = tiebreaker_model or settings.advisor_tiebreaker_model or default_model

    if preflight:
        models_to_check = [p["model"] for p in personas_serialized]
        models_to_check.append(verdict_model)
        preflight_result = await preflight_models(models_to_check)
        if not preflight_result.ok:
            yield {
                "type": "advisor_error",
                "message": build_preflight_error_message(preflight_result),
            }
            return

    search_context_block = ""
    if search_context:
        search_context_block = (
            "You have access to the following real-time web search results. "
            "Use this information if relevant to the debate.\n\n"
            f"Search Results:\n{search_context}\n\n"
        )

    yield {
        "type": "advisor_debate_start",
        "data": {
            "personas": personas_serialized,
            "max_rounds": max_rounds,
            "question": question,
            "web_search": web_search,
        },
    }

    safe_question = question.replace("{", "{{").replace("}", "}}")

    all_rounds: List[Dict[str, Any]] = []
    cost_rounds: List[Dict[str, Any]] = []
    round_extracts: List[Dict[str, Any]] = []
    consensus_reached = False
    consensus_round: Optional[int] = None
    extract_model = verdict_model

    for round_num in range(1, max_rounds + 1):
        if request and await request.is_disconnected():
            logger.info("Client disconnected during advisor debate.")
            return

        is_first_round = round_num == 1
        order = build_rotation_order(persona_ids, round_num)

        yield {
            "type": "advisor_round_start",
            "data": {"round_number": round_num, "order": order, "is_parallel": True},
        }

        round_responses: List[Dict[str, Any]] = []
        consensus_votes: Dict[str, bool] = {}
        consensus_scores: Dict[str, Optional[int]] = {}
        word_limit = 150 if is_first_round else 250

        if is_first_round:
            prompt_template = _settings_prompt(
                settings, "advisor_round1_prompt", ADVISOR_ROUND1_PROMPT
            ).format(
                search_context_block=search_context_block,
                question=safe_question,
                consensus_tag=CONSENSUS_TAG_INSTRUCTION,
            )
        else:
            transcript_text = _format_transcript(all_rounds, personas_map)
            previous_extract = (
                round_extracts[-1]["content"]
                if round_extracts and round_extracts[-1].get("content")
                else "No distilled extract was produced for the previous round. Use the transcript as fallback context."
            )
            prompt_template = _settings_prompt(
                settings, "advisor_followup_prompt", ADVISOR_FOLLOWUP_PROMPT
            ).format(
                search_context_block=search_context_block if round_num == 2 else "",
                question=safe_question,
                transcript=transcript_text,
                round_number=round_num,
                previous_round_number=round_num - 1,
                cross_pollination_extract=previous_extract,
                consensus_tag=CONSENSUS_TAG_INSTRUCTION,
            )

        tasks = [asyncio.create_task(_query_advisor(
            pid, prompt_template, personas_map, model_assignments, default_model, temperature
        )) for pid in order]

        pending = set(tasks)
        completed_count = 0
        try:
            while pending:
                if request and await request.is_disconnected():
                    for t in pending:
                        t.cancel()
                    return

                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED, timeout=1.0
                )

                for task in done:
                    pid, model, content, error, usage, cost = _unpack_advisor_result(await task)
                    completed_count += 1

                    if error:
                        resp_data = {
                            "persona_id": pid,
                            "persona_name": personas_map[pid].name,
                            "model": model,
                            "content": None,
                            "error": error,
                            "consensus": False,
                            "consensus_score": None,
                            "usage": usage,
                            "cost": cost,
                        }
                    else:
                        consensus_score = parse_consensus_tag(content)
                        clean_content = strip_consensus_tag(content)
                        word_count = _count_words(clean_content)
                        exceeds_word_limit = word_count > word_limit
                        has_consensus = (
                            not exceeds_word_limit
                            and consensus_score is not None
                            and consensus_score >= 4
                        )
                        response_error = (
                            f"Advisor response exceeded {word_limit} word limit."
                            if exceeds_word_limit
                            else None
                        )
                        if not exceeds_word_limit:
                            consensus_votes[pid] = has_consensus
                            consensus_scores[pid] = consensus_score
                        resp_data = {
                            "persona_id": pid,
                            "persona_name": personas_map[pid].name,
                            "model": model,
                            "content": clean_content,
                            "error": response_error,
                            "consensus": has_consensus,
                            "consensus_score": None if exceeds_word_limit else consensus_score,
                            "word_count": word_count,
                            "word_limit": word_limit,
                            "usage": usage,
                            "cost": cost,
                        }

                    round_responses.append(resp_data)

                    yield {
                        "type": "advisor_response",
                        "data": resp_data,
                        "round": round_num,
                        "count": completed_count,
                        "total": len(order),
                    }

        except asyncio.CancelledError:
            for t in tasks:
                if not t.done():
                    t.cancel()
            return

        successful_responses = [r for r in round_responses if r["error"] is None]
        average_consensus_score = _average_consensus_score(consensus_scores)
        all_rounds.append({
            "round_number": round_num,
            "average_consensus_score": average_consensus_score,
            "responses": [
                {"persona_id": r["persona_id"], "persona_name": r["persona_name"],
                 "model": r["model"], "content": r["content"],
                 "consensus": r["consensus"], "consensus_score": r["consensus_score"],
                 "usage": r.get("usage"), "cost": r.get("cost")}
                for r in successful_responses
            ],
        })
        cost_rounds.append({
            "round_number": round_num,
            "responses": round_responses,
        })

        all_agree = (
            len(successful_responses) == len(personas_list)
            and len(consensus_scores) == len(personas_list)
            and all(score is not None and score >= 4 for score in consensus_scores.values())
        )
        if all_agree:
            consensus_round = round_num

        yield {
            "type": "advisor_round_complete",
            "data": {
                "round_number": round_num,
                "responses": round_responses,
                "consensus_votes": dict(consensus_votes),
                "consensus_scores": dict(consensus_scores),
                "average_consensus_score": average_consensus_score,
                "consensus_reached": all_agree,
            },
        }

        if all_agree:
            consensus_reached = True
            break

        if round_num < max_rounds:
            if request and await request.is_disconnected():
                logger.info("Client disconnected during advisor extract.")
                return
            round_transcript = _format_transcript([all_rounds[-1]], personas_map)
            extract_prompt = _settings_prompt(
                settings,
                "advisor_cross_pollination_prompt",
                ADVISOR_CROSS_POLLINATION_PROMPT,
            ).format(
                question=safe_question,
                round_number=round_num,
                round_transcript=round_transcript,
            )
            extract_result = await _query_neutral(extract_model, extract_prompt, temperature=0.2)
            if extract_result.get("error") or not extract_result.get("content"):
                yield {
                    "type": "advisor_error",
                    "message": (
                        "Cross-pollination extract failed after "
                        f"Round {round_num}: {extract_result.get('error') or 'empty response'}"
                    ),
                }
                return
            round_extracts.append({
                "round_number": round_num,
                "model": extract_result.get("model"),
                "content": extract_result.get("content") or "",
                "error": extract_result.get("error"),
                "usage": extract_result.get("usage"),
                "cost": extract_result.get("cost"),
            })

    transcript_text = _format_transcript(all_rounds, personas_map)

    tiebreaker_result = None
    if not consensus_reached and len(persona_ids) == 2:
        yield {"type": "advisor_tiebreaker_start"}

        tiebreaker_prompt = _settings_prompt(
            settings, "advisor_tiebreaker_prompt", ADVISOR_TIEBREAKER_PROMPT
        ).format(
            question=safe_question,
            transcript=transcript_text,
        )
        tiebreaker_result = await _query_neutral(verdict_model, tiebreaker_prompt)

        yield {"type": "advisor_tiebreaker", "data": tiebreaker_result}

    yield {"type": "advisor_verdict_start"}

    debate_arc = _format_debate_arc(
        all_rounds,
        personas_map,
        round_extracts,
        consensus_reached,
        consensus_round,
    )
    verdict_prompt = _settings_prompt(
        settings, "advisor_verdict_prompt", ADVISOR_VERDICT_PROMPT
    ).format(
        question=safe_question,
        transcript=transcript_text,
        debate_arc=debate_arc,
    )

    if tiebreaker_result and tiebreaker_result.get("content"):
        verdict_prompt += f"\n\nTiebreaker ruling:\n{tiebreaker_result['content']}"

    verdict_data = await _query_neutral(verdict_model, verdict_prompt)

    yield {"type": "advisor_verdict", "data": verdict_data}

    yield {
        "type": "advisor_complete",
        "data": {
            "rounds": all_rounds,
            "consensus_reached": consensus_reached,
            "consensus_round": consensus_round,
            "round_extracts": round_extracts,
            "tiebreaker": tiebreaker_result,
            "verdict": verdict_data,
            "personas": personas_serialized,
            "cost_report": build_advisor_cost_report(
                cost_rounds,
                verdict_data,
                tiebreaker_result,
                round_extracts,
            ),
        },
    }
