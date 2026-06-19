"""Iterative debate orchestration: round loops, convergence, helpers."""

import math
import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from .settings import get_settings
from .prompts import apply_response_language
from .config import get_council_models, get_chairman_model
from .council import (
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
    calculate_aggregate_rankings,
    build_stage_texts,
)
from .costs import build_iterative_debate_cost_report

logger = logging.getLogger(__name__)

MAX_DEBATE_ROUNDS = 5
MAX_SYNTHESIS_CHARS = 6000  # ~1500 tokens


def check_convergence(
    current_rankings: List[Dict[str, Any]],
    previous_rankings: List[Dict[str, Any]],
) -> bool:
    """Check if aggregate ranking order stabilized (top-K unchanged)."""
    if not current_rankings or not previous_rankings:
        return False

    current_models = {r["model"] for r in current_rankings}
    previous_models = {r["model"] for r in previous_rankings}
    common = current_models & previous_models

    if len(common) == 0:
        return False  # No common models = can't compare = not converged
    if len(common) == 1:
        return True  # Degenerate: single common model is trivially stable

    current_order = [r["model"] for r in current_rankings if r["model"] in common]
    previous_order = [r["model"] for r in previous_rankings if r["model"] in common]

    k = math.ceil(len(current_order) / 2)
    return current_order[:k] == previous_order[:k]


def truncate_text(text: Optional[str], max_chars: int) -> str:
    """Truncate preserving start and end."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n[...truncated...]\n" + text[-half:]


def _build_rankings_summary(
    aggregate_rankings: List[Dict[str, Any]],
) -> str:
    """Format rankings as readable summary."""
    if not aggregate_rankings:
        return "No rankings available."
    lines = []
    for i, r in enumerate(aggregate_rankings, 1):
        lines.append(f"{i}. {r['model']} (avg rank: {r['average_rank']})")
    return "\n".join(lines)


def pre_segment_paragraphs(response_text: str) -> List[str]:
    """Split response into paragraphs on double-newlines. Returns list of paragraph strings."""
    if not response_text:
        return []
    paragraphs = [p.strip() for p in response_text.split("\n\n") if p.strip()]
    return paragraphs


def format_numbered_paragraphs(response_text: str) -> str:
    """Format response with [Para N] markers for stable evaluator references."""
    paragraphs = pre_segment_paragraphs(response_text)
    return "\n\n".join(f"[Para {i+1}] {p}" for i, p in enumerate(paragraphs))


async def extract_canonical_claims(
    responses_text: str,
    chairman_model: Optional[str] = None,
) -> Optional[Dict[str, List[Dict[str, str]]]]:
    """Extract canonical claims via single LLM call using the chairman model.

    Uses the chairman to avoid bias (council models should not write their own exam).
    Falls back to free-form mode if extraction fails or times out (90s).
    Returns {label: [{id, claim}]} or None on failure.
    """
    from .prompts import CLAIM_EXTRACTION_PROMPT
    from .council import query_model
    from .json_repair import extract_json_block

    settings = get_settings()
    prompt = apply_response_language(
        CLAIM_EXTRACTION_PROMPT.format(responses_text=responses_text),
        settings.response_language,
    )
    messages = [{"role": "user", "content": prompt}]

    extractor = chairman_model or get_chairman_model()
    timeout_val = getattr(settings, "claim_extraction_timeout_seconds", 180.0)
    # For Notion2API models the provider clamps to max(timeout_val, 600s), so
    # pass timeout_val explicitly so both the httpx connection and the outer
    # asyncio.wait_for share the same budget.  Previously query_model used its
    # default of 120 s while wait_for used 180 s — on slow requests httpx could
    # be the first to give up, discarding partial content.
    try:
        response = await asyncio.wait_for(
            query_model(extractor, messages, temperature=0.2, timeout=timeout_val),
            timeout=timeout_val,
        )
    except asyncio.TimeoutError:
        logger.warning(f"Claim extraction timed out after {timeout_val}s, falling back to free-form")
        return None


    if not response or response.get("error"):
        return None

    content = response.get("content", "")
    result = extract_json_block(content)

    # Validate shape: must be {label: [{id, claim}]}
    if not isinstance(result, dict):
        logger.warning("Claim extraction returned non-dict (%s), falling back to free-form", type(result).__name__)
        return None

    # Normalize keys (strip whitespace, newlines, and outer quotes) to prevent KeyErrors on lookups
    normalized_result = {}
    for key, val in result.items():
        clean_key = str(key).strip().strip('"').strip("'").strip()
        normalized_result[clean_key] = val
    result = normalized_result

    # Verify values are lists of dicts with 'id' and 'claim' keys
    for key, claims in result.items():
        if not isinstance(claims, list):
            logger.warning("Claim extraction value for '%s' is not a list, falling back", key)
            return None

    return result


def aggregate_claim_verdicts(
    stage2_results: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Aggregate per-claim verdicts across evaluators.

    Returns {claim_id: {majority_verdict, agreement, verdicts}}.
    """
    from collections import Counter

    all_verdicts: Dict[str, List[str]] = {}

    for result in stage2_results:
        claim_verdicts = result.get("claim_verdicts", {})
        for claim_id, v in claim_verdicts.items():
            all_verdicts.setdefault(claim_id, []).append(v.get("verdict", ""))

    aggregated = {}
    for claim_id, verdicts in all_verdicts.items():
        counter = Counter(verdicts)
        majority = counter.most_common(1)[0][0] if counter else "unknown"
        total = len(verdicts)
        agreement = counter[majority] / total if total > 0 else 0
        aggregated[claim_id] = {
            "majority_verdict": majority,
            "agreement": round(agreement, 2),
            "verdicts": dict(counter),
        }

    return aggregated


def select_top_claims_for_model(
    canonical_claims: Dict[str, List[Dict[str, str]]],
    aggregated_verdicts: Dict[str, Dict[str, Any]],
    target_model: str,
    label_to_model: Dict[str, str],
    max_claims: int = 5,
) -> List[Dict[str, Any]]:
    """Select top-rated claims from OTHER models for cross-pollination."""
    model_to_label = {v: k for k, v in label_to_model.items()}
    target_label = model_to_label.get(target_model)

    candidates = []
    for label, claims in canonical_claims.items():
        if label == target_label:
            continue
        for claim in claims:
            cid = claim["id"]
            verdict_info = aggregated_verdicts.get(cid, {})
            if verdict_info.get("majority_verdict") == "strong":
                candidates.append({
                    **claim,
                    "agreement": verdict_info.get("agreement", 0),
                    "source_label": label,
                })

    candidates.sort(key=lambda x: x["agreement"], reverse=True)
    return candidates[:max_claims]


def _format_own_claims(
    model: str,
    canonical_claims: Dict[str, List[Dict[str, str]]],
    aggregated: Dict[str, Dict[str, Any]],
    label_to_model: Dict[str, str],
) -> str:
    """Format a model's own claims with peer verdicts for round N+1 prompt."""
    model_to_label = {v: k for k, v in label_to_model.items()}
    label = model_to_label.get(model)
    if not label or label not in canonical_claims:
        return "No claims from your previous response."

    lines = []
    for claim in canonical_claims[label]:
        cid = claim["id"]
        verdict_info = aggregated.get(cid, {})
        majority = verdict_info.get("majority_verdict", "unknown").upper()
        agreement = verdict_info.get("agreement", 0)
        lines.append(f'- {cid}: "{claim["claim"]}" — {majority} ({agreement:.0%} agree)')
    return "\n".join(lines) if lines else "No claims from your previous response."


def _format_own_paragraphs(
    model: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str],
) -> str:
    """Format a model's own paragraphs with peer verdicts for round N+1 prompt."""
    model_to_label = {v: k for k, v in label_to_model.items()}
    label = model_to_label.get(model)
    if not label:
        return "No paragraph feedback available."

    # Find the model's response
    model_response = None
    for r in stage1_results:
        if r.get("model") == model and r.get("response"):
            model_response = r["response"]
            break
    if not model_response:
        return "No paragraph feedback available."

    paragraphs = pre_segment_paragraphs(model_response)

    # Collect annotations for this model's response from all evaluators
    para_verdicts: Dict[int, List[str]] = {}
    para_comments: Dict[int, List[str]] = {}
    for result in stage2_results:
        annotations = result.get("annotations", [])
        if not isinstance(annotations, list):
            continue
        for ann in annotations:
            if not isinstance(ann, dict):
                continue
            ann_response = ann.get("response")
            if ann_response == label:
                pn = ann.get("paragraph", 0)
                para_verdicts.setdefault(pn, []).append(ann.get("verdict", ""))
                if ann.get("comment"):
                    para_comments.setdefault(pn, []).append(ann["comment"])

    lines = []
    for i, para in enumerate(paragraphs, 1):
        verdicts = para_verdicts.get(i, [])
        if verdicts:
            from collections import Counter
            c = Counter(verdicts)
            majority = c.most_common(1)[0][0].upper()
            lines.append(f'- [Para {i}] "{para[:80]}..." — {majority}')
        else:
            lines.append(f'- [Para {i}] "{para[:80]}..." — No feedback')
    return "\n".join(lines) if lines else "No paragraph feedback available."


def _select_top_paragraphs_from_others(
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    target_model: str,
    label_to_model: Dict[str, str],
    max_paras: int = 5,
) -> str:
    """Select top-rated paragraphs from OTHER models for cross-pollination."""
    model_to_label = {v: k for k, v in label_to_model.items()}
    target_label = model_to_label.get(target_model)

    # Collect annotations per (label, paragraph) across evaluators
    from collections import Counter
    para_scores: Dict[tuple, list] = {}
    for result in stage2_results:
        annotations = result.get("annotations", [])
        if not isinstance(annotations, list):
            continue
        for ann in annotations:
            if not isinstance(ann, dict):
                continue
            ann_response = ann.get("response", "")
            key = (ann_response, ann.get("paragraph", 0))
            para_scores.setdefault(key, []).append(ann.get("verdict", ""))

    # Find strong paragraphs from other models
    candidates = []
    for (label, para_num), verdicts in para_scores.items():
        if label == target_label:
            continue
        c = Counter(verdicts)
        if c and c.most_common(1)[0][0] == "strong":
            agreement = c["strong"] / len(verdicts)
            # Find the actual paragraph text
            model_name = label_to_model.get(label)
            para_text = ""
            for r in stage1_results:
                if r.get("model") == model_name and r.get("response"):
                    paras = pre_segment_paragraphs(r["response"])
                    if 1 <= para_num <= len(paras):
                        para_text = paras[para_num - 1]
                    break
            if para_text:
                candidates.append({
                    "label": label,
                    "paragraph": para_num,
                    "text": para_text[:150],
                    "agreement": agreement,
                })

    candidates.sort(key=lambda x: x["agreement"], reverse=True)
    lines = []
    for c in candidates[:max_paras]:
        lines.append(f'- [{c["label"]} Para {c["paragraph"]}] "{c["text"]}..." — STRONG ({c["agreement"]:.0%} agree)')
    return "\n".join(lines) if lines else "None"


def _parse_claim_verdicts_from_ranking(ranking_text: str) -> Optional[Dict[str, Dict[str, str]]]:
    """Extract claim verdict JSON from a Stage 2 ranking response."""
    from .json_repair import extract_json_block
    if not ranking_text:
        return None
    result = extract_json_block(ranking_text)
    if isinstance(result, dict):
        # Validate it looks like claim verdicts {id: {verdict, reason}}
        if all(isinstance(v, dict) and "verdict" in v for v in result.values()):
            return result
    return None


def _parse_audit_verdicts(ranking_text: str, expected_claim_ids: list = None) -> dict:
    from .json_repair import extract_json_block
    from .council import EvaluationError
    if not ranking_text:
        raise EvaluationError("Empty output from evaluator")

    result = extract_json_block(ranking_text)
    if not isinstance(result, dict):
        raise EvaluationError("Output JSON is not a dictionary mapping claim IDs to verdicts")

    VALID_SOURCE = {"supported", "partially_supported", "unsupported", "contradicted", "unverifiable"}
    VALID_SUBSTANTIVE = {"sound", "requires_qualification", "unsound", "unverifiable"}

    if expected_claim_ids:
        missing = set(expected_claim_ids) - set(result.keys())
        if missing:
            raise EvaluationError(f"Missing expected claim IDs: {missing}")

    verdict_combos = []

    for claim_id, v in result.items():
        if not isinstance(v, dict):
            raise EvaluationError(f"Claim {claim_id} value is not a dictionary")
        if v.get("source_support") not in VALID_SOURCE:
            raise EvaluationError(f"Claim {claim_id} has invalid source_support: {v.get('source_support')}")
        if v.get("substantive_assessment") not in VALID_SUBSTANTIVE:
            raise EvaluationError(f"Claim {claim_id} has invalid substantive_assessment: {v.get('substantive_assessment')}")

        reason = str(v.get("reason", "")).strip()
        if len(reason) < 20 or not any(ch.isalnum() for ch in reason):
            raise EvaluationError(f"Degenerate reason for claim {claim_id}; retry evaluator. Reason given: '{reason}'")

        if reason.lower() in ("supported.", "correct.", "accurate.", "yes.", "supported", "correct"):
            raise EvaluationError(f"Boilerplate reason for claim {claim_id}: {reason}")

        verdict_combos.append((v["source_support"], v["substantive_assessment"]))

    if len(verdict_combos) >= 10:
        from collections import Counter
        counts = Counter(verdict_combos)
        most_common, count = counts.most_common(1)[0]
        if count / len(verdict_combos) > 0.95:
            raise EvaluationError("Repetitive boilerplate and verdict-collapse detected (>95% identical verdicts)")

    return result


def _parse_paragraph_annotations_from_ranking(ranking_text: str) -> Optional[List[Dict[str, Any]]]:
    """Extract paragraph annotation JSON from a Stage 2 ranking response."""
    from .json_repair import extract_json_block
    if not ranking_text:
        return None
    result = extract_json_block(ranking_text)
    if isinstance(result, list):
        return result
    return None


async def run_iterative_debate(
    user_query: str,
    search_context: str = "",
    request: Any = None,
    execution_mode: str = "full",
    models_override: Optional[List[str]] = None,
    chairman_override: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    debate_rounds: Optional[int] = None,
    conversation_id: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Orchestrate multi-round debate. Yields SSE-ready event dicts.

    Supports three critique modes: freeform, paragraph, claim.

    The caller (main.py endpoint) is responsible for:
    - JSON-serializing and SSE-framing each yielded dict
    - Title generation (after generator exhausts)
    - Storage (using the debate_complete event's rounds data)
    - Yielding the final 'complete' event
    """
    settings = get_settings()
    num_rounds = min(
        debate_rounds if debate_rounds is not None else settings.debate_rounds,
        MAX_DEBATE_ROUNDS,
    )
    auto_converge = settings.auto_converge
    convergence_threshold = settings.convergence_threshold
    critique_mode = settings.critique_mode  # "freeform", "paragraph", or "claim"

    # Validate: chat_only doesn't support multi-round
    if execution_mode == "chat_only":
        num_rounds = 1

    previous_synthesis: Optional[str] = None
    previous_rankings: Optional[List[Dict[str, Any]]] = None
    previous_canonical_claims: Optional[Dict[str, List[Dict[str, str]]]] = None
    previous_aggregated_verdicts: Optional[Dict[str, Dict[str, Any]]] = None
    previous_label_to_model: Dict[str, str] = {}
    previous_stage1_results: List[Dict[str, Any]] = []
    previous_stage2_results: List[Dict[str, Any]] = []
    all_rounds_data: List[Dict[str, Any]] = []
    convergence_count = 0
    converged = False

    for round_num in range(1, num_rounds + 1):
        if request and await request.is_disconnected():
            raise asyncio.CancelledError("Client disconnected")

        yield {"type": "round_start", "round": round_num, "total_rounds": num_rounds}

        # --- Build Stage 1 messages ---
        messages_override = None
        per_model_messages = None
        effective_mode = critique_mode  # May fall back to freeform

        if round_num > 1:
            from .prompts import (
                STAGE1_ROUND_N_FREEFORM_PROMPT,
                STAGE1_ROUND_N_CHAT_RANKING_PROMPT,
                STAGE1_ROUND_N_CLAIM_PROMPT,
                STAGE1_ROUND_N_PARAGRAPH_PROMPT,
                STAGE1_SEARCH_CONTEXT_TEMPLATE,
            )
            search_block = ""
            if search_context:
                search_block = STAGE1_SEARCH_CONTEXT_TEMPLATE.format(search_context=search_context)

            if effective_mode == "claim" and previous_canonical_claims and previous_aggregated_verdicts:
                # Per-model personalized prompts for claim mode
                models = models_override or get_council_models()
                per_model_messages = {}
                for model in models:
                    own_critiques = _format_own_claims(
                        model, previous_canonical_claims,
                        previous_aggregated_verdicts, previous_label_to_model,
                    )
                    top_others = select_top_claims_for_model(
                        previous_canonical_claims, previous_aggregated_verdicts,
                        model, previous_label_to_model,
                    )
                    top_text = "\n".join([
                        f'- {c["id"]}: "{c["claim"]}" — STRONG ({c["agreement"]:.0%} agree)'
                        for c in top_others
                    ]) or "None"

                    prompt = STAGE1_ROUND_N_CLAIM_PROMPT.format(
                        round_number=round_num,
                        user_query=user_query,
                        search_context_block=search_block,
                        own_claims_with_critiques=own_critiques,
                        top_claims_from_others=top_text,
                    )
                    per_model_messages[model] = [{
                        "role": "user",
                        "content": apply_response_language(prompt, settings.response_language),
                    }]

            elif effective_mode == "paragraph" and previous_rankings:
                # Per-model personalized prompts for paragraph mode
                models = models_override or get_council_models()
                per_model_messages = {}
                for model in models:
                    own_paras = _format_own_paragraphs(
                        model, previous_stage1_results,
                        previous_stage2_results, previous_label_to_model,
                    )
                    top_paras = _select_top_paragraphs_from_others(
                        previous_stage1_results, previous_stage2_results,
                        model, previous_label_to_model,
                    )
                    prompt = STAGE1_ROUND_N_PARAGRAPH_PROMPT.format(
                        round_number=round_num,
                        user_query=user_query,
                        search_context_block=search_block,
                        own_paragraphs_with_critiques=own_paras,
                        top_paragraphs_from_others=top_paras,
                    )
                    per_model_messages[model] = [{
                        "role": "user",
                        "content": apply_response_language(prompt, settings.response_language),
                    }]

            elif execution_mode == "full" and previous_synthesis:
                # Freeform mode (or fallback)
                round_prompt = STAGE1_ROUND_N_FREEFORM_PROMPT.format(
                    round_number=round_num,
                    user_query=user_query,
                    search_context_block=search_block,
                    previous_synthesis=truncate_text(previous_synthesis, MAX_SYNTHESIS_CHARS),
                    previous_rankings_summary=_build_rankings_summary(previous_rankings or []),
                )
                messages_override = [{
                    "role": "user",
                    "content": apply_response_language(round_prompt, settings.response_language),
                }]
            else:
                # chat_ranking mode: feedback from rankings only
                round_prompt = STAGE1_ROUND_N_CHAT_RANKING_PROMPT.format(
                    round_number=round_num,
                    user_query=user_query,
                    search_context_block=search_block,
                    previous_rankings_summary=_build_rankings_summary(previous_rankings or []),
                    your_rank="{model_rank}",
                    total_models=len(previous_rankings or []),
                    rank_feedback="Improve your response based on peer feedback.",
                )
                messages_override = [{
                    "role": "user",
                    "content": apply_response_language(round_prompt, settings.response_language),
                }]

        # --- Stage 1 ---
        yield {"type": "stage1_start", "round": round_num}
        await asyncio.sleep(0.05)

        stage1_results: List[Dict[str, Any]] = []
        total_models = 0

        async for item in stage1_collect_responses(
            user_query,
            search_context if round_num == 1 else "",
            request,
            models_override=models_override,
            history=history if round_num == 1 else None,
            messages_override=messages_override,
            per_model_messages=per_model_messages,
            conversation_id=conversation_id,
        ):
            if isinstance(item, int):
                total_models = item
                yield {"type": "stage1_init", "total": total_models, "round": round_num}
                continue
            # Skip pause-event sentinels — they must not pollute stage1_results
            # (they have no 'error' key, so they would survive Stage 2's
            # successful_results filter and produce a duplicate model entry).
            if isinstance(item, dict) and item.get("paused"):
                yield {"type": "stage1_pause", "data": item, "round": round_num}
                continue
            stage1_results.append(item)
            yield {
                "type": "stage1_progress",
                "data": item,
                "count": len(stage1_results),
                "total": total_models,
                "round": round_num,
            }
            await asyncio.sleep(0.01)

        yield {"type": "stage1_complete", "data": stage1_results, "round": round_num}
        await asyncio.sleep(0.05)

        if not any(r for r in stage1_results if not r.get("error")):
            yield {"type": "error", "message": "All models failed in Stage 1."}
            return

        # --- Mode-aware Stage 2 preparation ---
        stage2_results: List[Dict[str, Any]] = []
        label_to_model: Dict[str, str] = {}
        aggregate_rankings: List[Dict[str, Any]] = []
        canonical_claims: Optional[Dict[str, List[Dict[str, str]]]] = None
        aggregated_verdicts: Optional[Dict[str, Dict[str, Any]]] = None

        if execution_mode in ("chat_ranking", "full"):
            if request and await request.is_disconnected():
                raise asyncio.CancelledError("Client disconnected")

            # Build label_to_model for mode-specific prompt building
            successful_results = [r for r in stage1_results if not r.get("error")]
            labels = [chr(65 + i) for i in range(len(successful_results))]
            label_to_model_preview = {
                f"Response {label}": result["model"]
                for label, result in zip(labels, successful_results)
            }

            stage2_prompt_override = None

            if effective_mode == "paragraph":
                # Build paragraph-annotated responses text
                search_context_block = ""
                if search_context:
                    search_context_block = f"Context from Web Search:\n{search_context}\n"

                responses_text = "\n\n".join([
                    f"Response {label}:\n{format_numbered_paragraphs(result['response'])}"
                    for label, result in zip(labels, successful_results)
                ])

                from .prompts import STAGE2_PARAGRAPH_PROMPT
                stage2_prompt_override = STAGE2_PARAGRAPH_PROMPT.format(
                    user_query=user_query,
                    search_context_block=search_context_block,
                    responses_text=responses_text,
                )

            elif effective_mode == "claim":
                # Extract canonical claims first
                responses_text_for_extraction = "\n\n".join([
                    f"Response {label}:\n{result['response']}"
                    for label, result in zip(labels, successful_results)
                ])

                canonical_claims = await extract_canonical_claims(
                    responses_text_for_extraction, chairman_override
                )

                if canonical_claims is None:
                    logger.warning("Claim extraction failed, falling back to freeform for this round")
                    effective_mode = "freeform"
                else:
                    # Build claim-aware Stage 2 prompt
                    search_context_block = ""
                    if search_context:
                        search_context_block = f"Context from Web Search:\n{search_context}\n"

                    responses_text = "\n\n".join([
                        f"Response {label}:\n{result['response']}"
                        for label, result in zip(labels, successful_results)
                    ])

                    claims_text = "\n".join([
                        f'  {c["id"]}: "{c["claim"]}"'
                        for label_claims in canonical_claims.values()
                        for c in label_claims
                    ])

                    from .prompts import STAGE2_CLAIM_PROMPT
                    stage2_prompt_override = STAGE2_CLAIM_PROMPT.format(
                        user_query=user_query,
                        search_context_block=search_context_block,
                        responses_text=responses_text,
                        canonical_claims_text=claims_text,
                    )

            yield {"type": "stage2_start", "round": round_num}
            await asyncio.sleep(0.05)

            async for item in stage2_collect_rankings(
                user_query, stage1_results, search_context, request,
                prompt_override=stage2_prompt_override,
                conversation_id=conversation_id,
            ):
                if isinstance(item, dict) and not item.get("model"):
                    label_to_model = item
                    yield {"type": "stage2_init", "total": len(label_to_model), "round": round_num}
                    continue
                # Skip pause-event sentinels — same reason as Stage 1 above.
                if isinstance(item, dict) and item.get("paused"):
                    yield {"type": "stage2_pause", "data": item, "round": round_num}
                    continue
                # Post-process: extract structured data from ranking text
                if effective_mode == "claim" and item.get("ranking"):
                    cv = _parse_claim_verdicts_from_ranking(item["ranking"])
                    if cv:
                        item["claim_verdicts"] = cv
                elif effective_mode == "paragraph" and item.get("ranking"):
                    anns = _parse_paragraph_annotations_from_ranking(item["ranking"])
                    if anns:
                        item["annotations"] = anns
                stage2_results.append(item)
                yield {
                    "type": "stage2_progress",
                    "data": item,
                    "count": len(stage2_results),
                    "total": len(label_to_model),
                    "round": round_num,
                }
                await asyncio.sleep(0.01)

            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

            # Aggregate claim verdicts if in claim mode
            if effective_mode == "claim" and canonical_claims:
                aggregated_verdicts = aggregate_claim_verdicts(stage2_results)

            stage2_complete_metadata = {
                "label_to_model": label_to_model,
                "aggregate_rankings": aggregate_rankings,
            }
            if canonical_claims:
                stage2_complete_metadata["canonical_claims"] = canonical_claims
            if aggregated_verdicts:
                stage2_complete_metadata["aggregate_claim_verdicts"] = aggregated_verdicts

            yield {
                "type": "stage2_complete",
                "data": stage2_results,
                "metadata": stage2_complete_metadata,
                "round": round_num,
            }
            await asyncio.sleep(0.05)

            # Convergence
            if auto_converge and previous_rankings and round_num > 1:
                if check_convergence(aggregate_rankings, previous_rankings):
                    convergence_count += 1
                else:
                    convergence_count = 0
                if convergence_count >= convergence_threshold:
                    converged = True
                    yield {
                        "type": "convergence",
                        "round": round_num,
                        "message": f"Rankings stabilized after {round_num} rounds",
                    }

            previous_rankings = aggregate_rankings

        # --- Stage 3 ---
        stage3_result: Optional[Dict[str, Any]] = None

        if execution_mode == "full":
            if request and await request.is_disconnected():
                raise asyncio.CancelledError("Client disconnected")

            yield {"type": "stage3_start", "round": round_num}
            await asyncio.sleep(0.05)

            is_final = converged or (round_num == num_rounds)

            # Build final chairman prompt for last round
            prompt_override = None
            if is_final and round_num > 1:
                search_block = ""
                if search_context:
                    search_block = f"Context from Web Search:\n{search_context}\n"

                stage1_text, stage2_text = build_stage_texts(stage1_results, stage2_results)

                if effective_mode == "claim" and canonical_claims:
                    from .prompts import STAGE3_FINAL_CLAIM_PROMPT

                    # Build claim evolution summary
                    evolution_lines = []
                    for label, claims in canonical_claims.items():
                        for claim in claims:
                            cid = claim["id"]
                            vi = (aggregated_verdicts or {}).get(cid, {})
                            verdict = vi.get("majority_verdict", "unknown").upper()
                            evolution_lines.append(f'- {cid} "{claim["claim"]}": {verdict}')
                    claim_evolution = "\n".join(evolution_lines) or "No claim data available."

                    prompt_override = STAGE3_FINAL_CLAIM_PROMPT.format(
                        total_rounds=round_num,
                        user_query=user_query,
                        search_context_block=search_block,
                        claim_evolution_summary=claim_evolution,
                        stage1_text=stage1_text,
                        stage2_text=stage2_text,
                    )
                elif previous_synthesis:
                    from .prompts import STAGE3_FINAL_FREEFORM_PROMPT

                    prompt_override = STAGE3_FINAL_FREEFORM_PROMPT.format(
                        total_rounds=round_num,
                        user_query=user_query,
                        search_context_block=search_block,
                        previous_synthesis=truncate_text(previous_synthesis, MAX_SYNTHESIS_CHARS),
                        stage1_text=stage1_text,
                        stage2_text=stage2_text,
                    )

            stage3_result = await stage3_synthesize_final(
                user_query, stage1_results, stage2_results, search_context,
                chairman_override=chairman_override,
                prompt_override=prompt_override,
                conversation_id=conversation_id,
            )
            yield {"type": "stage3_complete", "data": stage3_result, "round": round_num}

            previous_synthesis = stage3_result.get("response", "") if stage3_result else None

        # Save state for next round's per-model prompts
        previous_canonical_claims = canonical_claims
        previous_aggregated_verdicts = aggregated_verdicts
        previous_label_to_model = label_to_model
        previous_stage1_results = stage1_results
        previous_stage2_results = stage2_results

        # Save round data
        round_metadata = {
            "label_to_model": label_to_model,
            "aggregate_rankings": aggregate_rankings,
        }
        if canonical_claims:
            round_metadata["canonical_claims"] = canonical_claims
        if aggregated_verdicts:
            round_metadata["aggregate_claim_verdicts"] = aggregated_verdicts

        round_data = {
            "round_number": round_num,
            "critique_mode": effective_mode,
            "stage1": stage1_results,
            "stage2": stage2_results if execution_mode in ("chat_ranking", "full") else None,
            "stage3": stage3_result if execution_mode == "full" else None,
            "metadata": round_metadata,
        }
        all_rounds_data.append(round_data)

        yield {"type": "round_complete", "round": round_num}

        if converged:
            break

    # --- Stage 4: Corrected Draft (after all rounds, if full mode) ---
    stage4_result: Optional[Dict[str, Any]] = None

    if execution_mode == "full" and previous_synthesis and num_rounds > 1:
        if request and await request.is_disconnected():
            raise asyncio.CancelledError("Client disconnected")

        yield {"type": "stage4_start"}
        await asyncio.sleep(0.05)

        from .prompts import STAGE4_CORRECTED_DRAFT_PROMPT

        stage4_template = settings.stage4_prompt.strip() or STAGE4_CORRECTED_DRAFT_PROMPT
        try:
            stage4_prompt = stage4_template.format(
                total_rounds=len(all_rounds_data),
                original_text=truncate_text(user_query, 12000),
                verdict_text=truncate_text(previous_synthesis, 10000),
            )
        except (KeyError, IndexError, ValueError):
            stage4_prompt = STAGE4_CORRECTED_DRAFT_PROMPT.format(
                total_rounds=len(all_rounds_data),
                original_text=truncate_text(user_query, 12000),
                verdict_text=truncate_text(previous_synthesis, 10000),
            )

        stage4_result = await stage3_synthesize_final(
            user_query, [], [], "",
            chairman_override=chairman_override,
            prompt_override=stage4_prompt,
            conversation_id=conversation_id,
        )
        yield {"type": "stage4_complete", "data": stage4_result}

    # Final event with all data for storage
    yield {
        "type": "debate_complete",
        "total_rounds_executed": len(all_rounds_data),
        "converged": converged,
        "critique_mode": critique_mode,
        "stage4": stage4_result,
        "rounds": all_rounds_data,
        "cost_report": build_iterative_debate_cost_report(all_rounds_data, stage4_result),
    }
