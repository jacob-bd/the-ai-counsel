"""Structured 2A/2B/2C Audit Pipeline."""
import asyncio
import logging
import json
import re
import math
from typing import Any, AsyncGenerator, Dict, List, Optional, Callable, Awaitable
from collections import Counter

from .settings import get_settings
from .prompts import (
    apply_response_language,
    MATERIAL_CLAIM_EXTRACTION_PROMPT,
    STAGE3_AUDIT_PROMPT_DEFAULT,
)
from .config import get_chairman_model
from .council import (
    stage1_collect_responses,
    build_stage_texts,
    EvaluationError,
    parse_stage2a_output,
    query_model,
    stage3_synthesize_final,
    _query_model_gated
)
from .costs import build_iterative_debate_cost_report
from .corrected_draft import generate_corrected_draft
from .debate import _parse_audit_verdicts
from .json_repair import extract_json_block

logger = logging.getLogger(__name__)

STAGE2A_MAX_OUTPUT_TOKENS = 5000
STAGE2B_MAX_OUTPUT_TOKENS = 6000
STAGE2C_MAX_OUTPUT_TOKENS = 3000
MIN_VALID_EVALUATORS = 2
MIN_VALID_EVALUATOR_RATIO = 0.5

# We will implement the orchestration here.

async def stage2a_collect_evaluations(
    user_query: str,
    search_context: str,
    stage1_results: List[Dict[str, Any]],
    conversation_id: str,
    settings: Any,
    audit_profile: Optional[str] = None,
    disconnect_check: Optional[Callable[[], Awaitable[bool]]] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Collect Stage 2A holistic evaluations."""
    successful_results = [r for r in stage1_results if not r.get("error") and r.get("response")]
    eligible = len(successful_results)
    if eligible < MIN_VALID_EVALUATORS:
        yield {
            "type": "stage2a_error",
            "status": "insufficient_evaluators",
            "message": f"Insufficient successful responses for evaluation. Required at least {MIN_VALID_EVALUATORS}, got {eligible}."
        }
        return

    required = max(
        MIN_VALID_EVALUATORS,
        math.ceil(eligible * MIN_VALID_EVALUATOR_RATIO),
    )

    models = [r['model'] for r in successful_results]
    label_to_model = {chr(65 + i): r['model'] for i, r in enumerate(successful_results)}
    model_to_label = {v: k for k, v in label_to_model.items()}

    yield {
        "type": "stage2a_init",
        "total": len(models),
        "models": models,
        "label_to_model": label_to_model,
        "round": 1,
    }

    search_block = f"Context from Web Search:\n{search_context}\n" if search_context else ""

    async def _evaluate_model(model: str) -> Dict[str, Any]:
        # Exclude self
        other_results = [r for r in successful_results if r['model'] != model]
        if not other_results:
            return {"model": model, "error": True, "error_message": "No other responses to evaluate."}

        valid_labels = [model_to_label[r['model']] for r in other_results]
        valid_label_list = ", ".join([f"Response {lbl}" for lbl in valid_labels])

        responses_text = "\n\n".join([
            f"Response {model_to_label[r['model']]}:\n{r['response']}"
            for r in other_results
        ])

        profile = audit_profile or getattr(settings, "audit_profile", "general")
        if profile == "legal":
            from .prompts import STAGE2A_LEGAL_PROMPT
            prompt_template = STAGE2A_LEGAL_PROMPT
        else:
            from .prompts import STAGE2A_GENERAL_PROMPT
            prompt_template = STAGE2A_GENERAL_PROMPT

        prompt = prompt_template.format(
            user_query=user_query,
            search_context_block=search_block,
            responses_text=responses_text,
        )
        prompt += (
            f"\n\nCRITICAL: Your FINAL output must include ONLY these labels, "
            f"each exactly once: {valid_label_list}. "
        )
        prompt = apply_response_language(prompt, settings.response_language)

        messages = [{"role": "user", "content": prompt}]

        # Bounded retry: 1 retry
        last_error = None
        attempts_ledger = []
        for attempt in range(2):
            try:
                # Force new chat session for Notion2API by generating a unique session ID
                session_id = f"{conversation_id}-2a-{model}-{attempt}"

                response = await _query_model_gated(
                    model, messages, timeout=300, temperature=settings.stage2_temperature,
                    conversation_id=session_id, max_output_tokens=STAGE2A_MAX_OUTPUT_TOKENS
                )

                if response.get("error"):
                    last_error = response.get("error_message")
                    attempts_ledger.append({
                        "attempt": attempt + 1,
                        "status": "api_error",
                        "usage": response.get("usage"),
                        "cost": response.get("cost"),
                    })
                    break # Fatal API error, don't retry formatting

                content = response.get("content", "")

                # Strict parsing
                expected_keys = [f"Response {label}" for label in valid_labels]
                try:
                    parsed = parse_stage2a_output(content, expected_keys)
                    attempts_ledger.append({
                        "attempt": attempt + 1,
                        "status": "success",
                        "usage": response.get("usage"),
                        "cost": response.get("cost"),
                    })
                    return {
                        "model": model,
                        "raw_output": content,
                        "parsed": parsed,
                        "usage": response.get("usage"),
                        "cost": response.get("cost"),
                        "attempts": attempts_ledger,
                    }
                except EvaluationError as e:
                    last_error = str(e)
                    attempts_ledger.append({
                        "attempt": attempt + 1,
                        "status": "validation_failed",
                        "usage": response.get("usage"),
                        "cost": response.get("cost"),
                    })
                    logger.warning(f"Stage 2A validation failed for {model} (attempt {attempt+1}): {e}")
                    if attempt == 0:
                        messages.append({"role": "assistant", "content": content})
                        messages.append({"role": "user", "content": f"Validation Error: {e}\nPlease correct your output and provide ONLY valid JSON."})
            except Exception as e:
                last_error = str(e)
                attempts_ledger.append({
                    "attempt": attempt + 1,
                    "status": "exception",
                    "usage": None,
                    "cost": None,
                })
                break

        return {
            "model": model,
            "error": True,
            "error_message": f"Failed after retries: {last_error}",
            "status": "invalid_evaluator_output",
            "attempts": attempts_ledger,
        }

    tasks = [asyncio.create_task(_evaluate_model(m)) for m in models]
    for model in models:
        yield {
            "type": "provider_status",
            "data": {"stage": "stage2a", "model": model, "status": "running"},
            "round": 1,
        }

    # We yield progress as tasks complete
    count = 0
    results = []

    monitor_task = None
    if disconnect_check:
        async def monitor():
            try:
                while True:
                    await asyncio.sleep(0.5)
                    if await disconnect_check():
                        logger.info("Client disconnect detected in Stage 2A. Cancelling active tasks.")
                        for t in tasks:
                            if not t.done():
                                t.cancel()
                        break
            except asyncio.CancelledError:
                pass
        monitor_task = asyncio.create_task(monitor())

    try:
        for coro in asyncio.as_completed(tasks):
            res = await coro
            if isinstance(res, Exception):
                if isinstance(res, asyncio.CancelledError):
                    raise res
                res = {"error": True, "error_message": str(res)}

            count += 1
            results.append(res)
            yield {
                "type": "stage2a_progress",
                "data": res,
                "count": count,
                "total": len(models),
                "round": 1
            }
            if disconnect_check and await disconnect_check():
                raise asyncio.CancelledError("Client disconnected")
    finally:
        if monitor_task:
            monitor_task.cancel()
            try:
                await monitor_task
            except Exception:
                pass
        # Cancel any unfinished tasks
        unfinished = [t for t in tasks if not t.done()]
        if unfinished:
            for t in unfinished:
                t.cancel()
            await asyncio.gather(*unfinished, return_exceptions=True)

    successful_results = [r for r in results if not r.get("error")]
    successful = len(successful_results)
    if successful < required:
        has_invalid = any(r.get("status") == "invalid_evaluator_output" for r in results if r.get("error"))
        status = "invalid_evaluator_output" if has_invalid else "failed_quorum"
        yield {
            "type": "stage2a_error",
            "status": status,
            "message": f"Failed to reach evaluation quorum. Required {required} successful evaluations, got {successful}."
        }
        return

    # Summarize and yield complete
    yield {
        "type": "stage2a_complete",
        "data": results,
        "label_to_model": label_to_model,
        "round": 1
    }


async def extract_material_claims(
    responses_text: str,
    conversation_id: str,
    settings: Any,
    chairman_override: Optional[str] = None,
) -> Dict[str, Any]:
    from .json_repair import extract_json_block

    prompt = apply_response_language(
        MATERIAL_CLAIM_EXTRACTION_PROMPT.format(responses_text=responses_text),
        settings.response_language,
    )
    messages = [{"role": "user", "content": prompt}]

    extractor = chairman_override or get_chairman_model()
    timeout_val = getattr(settings, "claim_extraction_timeout_seconds", 180.0)

    last_error = None
    cumulative_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    cumulative_cost = 0.0
    attempts_ledger = []

    for attempt in range(2):
        try:
            session_id = f"{conversation_id}-extract-{attempt}"

            response = await _query_model_gated(
                extractor, messages, temperature=0.2, timeout=timeout_val, conversation_id=session_id,
                max_output_tokens=3000
            )

            # Record usage/cost. Some providers return explicit null values for
            # unavailable accounting fields, so coerce them to zero.
            usage = response.get("usage")
            if not isinstance(usage, dict):
                usage = {}
            cumulative_usage["input_tokens"] += int(usage.get("input_tokens") or 0)
            cumulative_usage["output_tokens"] += int(usage.get("output_tokens") or 0)
            cumulative_usage["total_tokens"] += int(usage.get("total_tokens") or 0)
            response_cost = response.get("cost")
            if isinstance(response_cost, dict):
                response_cost = response_cost.get("total_cost")
            if isinstance(response_cost, (int, float)):
                cumulative_cost += float(response_cost)

            if response.get("error"):
                last_error = response.get("error_message")
                attempts_ledger.append({
                    "attempt": attempt + 1,
                    "status": "api_error",
                    "usage": response.get("usage"),
                    "cost": response.get("cost"),
                })
                break

            content = response.get("content", "")
            try:
                result = extract_json_block(content)

                if not isinstance(result, dict):
                    raise EvaluationError(f"Expected a dictionary mapping response labels to claim lists, got {type(result).__name__}")

                normalized_result = {}
                total_claims = 0
                for key, val in result.items():
                    clean_key = str(key).strip().strip('"').strip("'").strip()
                    if not isinstance(val, list):
                        raise EvaluationError(f"Value for {clean_key} is not a list")
                    if len(val) > 8:
                        raise EvaluationError(
                            f"Response {clean_key} has {len(val)} claims, exceeding the maximum of 8."
                        )

                    normalized_claims = []
                    for index, item in enumerate(val, start=1):
                        default_id = f"{clean_key}_{index}"
                        if isinstance(item, str):
                            claim_id = default_id
                            claim_text = item.strip()
                        elif isinstance(item, dict):
                            raw_text = item.get("claim") or item.get("text") or item.get("content")
                            claim_text = raw_text.strip() if isinstance(raw_text, str) else ""
                            raw_id = item.get("id")
                            claim_id = str(raw_id).strip() if raw_id is not None else default_id
                        else:
                            raise EvaluationError(
                                f"Claim {index} for {clean_key} must be a string or object"
                            )

                        if not claim_text:
                            raise EvaluationError(
                                f"Claim {index} for {clean_key} is missing non-empty claim text"
                            )
                        if not claim_id:
                            claim_id = default_id
                        normalized_claims.append({"id": claim_id, "claim": claim_text})

                    normalized_result[clean_key] = normalized_claims
                    total_claims += len(normalized_claims)

                attempts_ledger.append({
                    "attempt": attempt + 1,
                    "status": "success",
                    "usage": response.get("usage"),
                    "cost": response.get("cost"),
                })

                return {
                    "claims": normalized_result,
                    "model": extractor,
                    "usage": response.get("usage"),
                    "cost": response.get("cost"),
                    "attempts": attempts_ledger,
                }
            except EvaluationError as e:
                last_error = str(e)
                attempts_ledger.append({
                    "attempt": attempt + 1,
                    "status": "validation_failed",
                    "usage": response.get("usage"),
                    "cost": response.get("cost"),
                })
                logger.warning(f"Claim extraction validation failed (attempt {attempt+1}): {e}")
                if attempt == 0:
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": f"Validation Error: {e}\nPlease correct your output and follow all constraints."})
        except asyncio.TimeoutError:
            logger.warning(f"Claim extraction timed out after {timeout_val}s")
            attempts_ledger.append({
                "attempt": attempt + 1,
                "status": "timeout",
                "usage": None,
                "cost": None,
            })
        except Exception as e:
            last_error = str(e)
            logger.error(f"Extraction error: {e}")
            attempts_ledger.append({
                "attempt": attempt + 1,
                "status": "exception",
                "usage": None,
                "cost": None,
            })
            break

    logger.warning(f"Material claim extraction failed after retries: {last_error}")
    return {
        "claims": None,
        "model": extractor,
        "usage": cumulative_usage,
        "cost": cumulative_cost,
        "attempts": attempts_ledger,
    }

def normalize_and_deduplicate_claims(
    raw_claims: Dict[str, List[Dict[str, str]]]
) -> List[Dict[str, Any]]:
    """
    Normalize, deduplicate, score materiality, and assign canonical IDs.
    Returns list of canonical claims, max 30.
    """
    # 1. Gather all claims with provenance
    all_claims = []
    for label, claims in raw_claims.items():
        for c in claims:
            all_claims.append({
                "original_id": c.get("id"),
                "claim": c.get("claim", ""),
                "source_label": label
            })

    # 2. Normalize and exact deduplication
    normalized_groups = {}
    for c in all_claims:
        text = c["claim"]
        norm = re.sub(r'\s+', ' ', text).lower().strip()
        # strip punctuation
        norm = re.sub(r'[^\w\s]', '', norm)

        if norm not in normalized_groups:
            normalized_groups[norm] = {
                "canonical_text": text,
                "source_claims": [c["original_id"]],
                "source_responses": [c["source_label"]],
            }
        else:
            if c["original_id"] not in normalized_groups[norm]["source_claims"]:
                normalized_groups[norm]["source_claims"].append(c["original_id"])
            if c["source_label"] not in normalized_groups[norm]["source_responses"]:
                normalized_groups[norm]["source_responses"].append(c["source_label"])

    # 3. Deterministic Materiality Scoring
    priority_keywords = {
        "jurisdiction": 10,
        "disposition": 10,
        "remedy": 10,
        "standard of review": 8,
        "waiver": 8,
        "preservation": 8,
        "evidence": 5,
        "record": 5,
        "error": 5,
        "statute": 7,
        "rule": 6
    }

    canonical_list = []
    for norm, data in normalized_groups.items():
        score = sum(val for kw, val in priority_keywords.items() if kw in norm)
        # Bonus for disagreement (multiple source responses)
        score += len(data["source_responses"]) * 2

        canonical_list.append({
            "canonical_text": data["canonical_text"],
            "source_claims": data["source_claims"],
            "source_responses": data["source_responses"],
            "materiality_score": score
        })

    # Sort by materiality descending, then by canonical_text ascending for determinism
    canonical_list.sort(key=lambda x: (-x["materiality_score"], x["canonical_text"]))

    # Cap at 30
    canonical_list = canonical_list[:30]

    # Assign stable canonical IDs
    for i, c in enumerate(canonical_list, 1):
        c["claim_id"] = f"C-{i:03d}"

    return canonical_list

async def stage2b_collect_audits(
    user_query: str,
    search_context: str,
    stage1_results: List[Dict[str, Any]],
    canonical_claims: List[Dict[str, Any]],
    conversation_id: str,
    settings: Any,
    audit_profile: Optional[str] = None,
    disconnect_check: Optional[Callable[[], Awaitable[bool]]] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Collect Stage 2B claim audits."""
    successful_results = [r for r in stage1_results if not r.get("error") and r.get("response")]
    eligible = len(successful_results)
    if eligible < MIN_VALID_EVALUATORS:
        yield {
            "type": "stage2b_error",
            "status": "insufficient_evaluators",
            "message": f"Insufficient successful responses for auditing. Required at least {MIN_VALID_EVALUATORS}, got {eligible}."
        }
        return

    required = max(
        MIN_VALID_EVALUATORS,
        math.ceil(eligible * MIN_VALID_EVALUATOR_RATIO),
    )

    models = [r['model'] for r in successful_results]
    label_to_model = {chr(65 + i): r['model'] for i, r in enumerate(successful_results)}
    model_to_label = {v: k for k, v in label_to_model.items()}

    yield {
        "type": "stage2b_init",
        "total": len(models),
        "models": models,
        "label_to_model": label_to_model,
        "round": 1,
    }

    search_block = f"Context from Web Search:\n{search_context}\n" if search_context else ""
    responses_text = "\n\n".join([
        f"Response {model_to_label[r['model']]}:\n{r['response']}"
        for r in successful_results
    ])

    claims_text = "\n".join([
        f'- {c["claim_id"]}: "{c["canonical_text"]}"'
        for c in canonical_claims
    ])

    profile = audit_profile or getattr(settings, "audit_profile", "general")
    if profile == "legal":
        from .prompts import STAGE2B_LEGAL_PROMPT
        prompt_template = STAGE2B_LEGAL_PROMPT
    else:
        from .prompts import STAGE2B_GENERAL_PROMPT
        prompt_template = STAGE2B_GENERAL_PROMPT

    prompt = prompt_template.format(
        user_query=user_query,
        search_context_block=search_block,
        responses_text=responses_text,
        canonical_claims_text=claims_text
    )
    prompt = apply_response_language(prompt, settings.response_language)

    expected_claim_ids = [c["claim_id"] for c in canonical_claims]

    async def _audit_model(model: str) -> Dict[str, Any]:
        messages = [{"role": "user", "content": prompt}]
        last_error = None
        attempts_ledger = []
        for attempt in range(2):
            try:
                session_id = f"{conversation_id}-2b-{model}-{attempt}"
                response = await _query_model_gated(
                    model, messages, timeout=300, temperature=settings.stage2_temperature,
                    conversation_id=session_id, max_output_tokens=STAGE2B_MAX_OUTPUT_TOKENS
                )

                if response.get("error"):
                    last_error = response.get("error_message")
                    attempts_ledger.append({
                        "attempt": attempt + 1,
                        "status": "api_error",
                        "usage": response.get("usage"),
                        "cost": response.get("cost"),
                    })
                    break

                content = response.get("content", "")
                try:
                    parsed = _parse_audit_verdicts(content, expected_claim_ids)
                    attempts_ledger.append({
                        "attempt": attempt + 1,
                        "status": "success",
                        "usage": response.get("usage"),
                        "cost": response.get("cost"),
                    })
                    return {
                        "model": model,
                        "raw_output": content,
                        "claim_verdicts": parsed,
                        "usage": response.get("usage"),
                        "cost": response.get("cost"),
                        "attempts": attempts_ledger,
                    }
                except EvaluationError as e:
                    last_error = str(e)
                    attempts_ledger.append({
                        "attempt": attempt + 1,
                        "status": "validation_failed",
                        "usage": response.get("usage"),
                        "cost": response.get("cost"),
                    })
                    logger.warning(f"Stage 2B validation failed for {model} (attempt {attempt+1}): {e}")
                    if attempt == 0:
                        messages.append({"role": "assistant", "content": content})
                        messages.append({"role": "user", "content": f"Validation Error: {e}\nPlease correct your output and provide ONLY valid JSON."})
            except Exception as e:
                last_error = str(e)
                attempts_ledger.append({
                    "attempt": attempt + 1,
                    "status": "exception",
                    "usage": None,
                    "cost": None,
                })
                break

        return {
            "model": model,
            "error": True,
            "error_message": f"Failed after retries: {last_error}",
            "status": "invalid_evaluator_output",
            "attempts": attempts_ledger,
        }

    tasks = [asyncio.create_task(_audit_model(m)) for m in models]
    for model in models:
        yield {
            "type": "provider_status",
            "data": {"stage": "stage2b", "model": model, "status": "running"},
            "round": 1,
        }

    count = 0
    results = []

    monitor_task = None
    if disconnect_check:
        async def monitor():
            try:
                while True:
                    await asyncio.sleep(0.5)
                    if await disconnect_check():
                        logger.info("Client disconnect detected in Stage 2B. Cancelling active tasks.")
                        for t in tasks:
                            if not t.done():
                                t.cancel()
                        break
            except asyncio.CancelledError:
                pass
        monitor_task = asyncio.create_task(monitor())

    try:
        for coro in asyncio.as_completed(tasks):
            res = await coro
            if isinstance(res, Exception):
                if isinstance(res, asyncio.CancelledError):
                    raise res
                res = {"error": True, "error_message": str(res)}

            count += 1
            results.append(res)
            yield {
                "type": "stage2b_progress",
                "data": res,
                "count": count,
                "total": len(models),
                "round": 1
            }
            if disconnect_check and await disconnect_check():
                raise asyncio.CancelledError("Client disconnected")
    finally:
        if monitor_task:
            monitor_task.cancel()
            try:
                await monitor_task
            except Exception:
                pass
        unfinished = [t for t in tasks if not t.done()]
        if unfinished:
            for t in unfinished:
                t.cancel()
            await asyncio.gather(*unfinished, return_exceptions=True)

    successful_results = [r for r in results if not r.get("error")]
    successful = len(successful_results)
    if successful < required:
        has_invalid = any(r.get("status") == "invalid_evaluator_output" for r in results if r.get("error"))
        status = "invalid_evaluator_output" if has_invalid else "failed_quorum"
        yield {
            "type": "stage2b_error",
            "status": status,
            "message": f"Failed to reach audit quorum. Required {required} successful audits, got {successful}."
        }
        return

    yield {
        "type": "stage2b_complete",
        "data": results,
        "label_to_model": label_to_model,
        "round": 1
    }


def aggregate_2b_results(stage2b_results: List[Dict[str, Any]], canonical_claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate Stage 2B audits into deterministic counts for Stage 2C."""
    successful_audits = [r for r in stage2b_results if not r.get("error")]

    # Check quorum
    total_evaluators = len(stage2b_results)
    valid_evaluators = len(successful_audits)

    if valid_evaluators < MIN_VALID_EVALUATORS or valid_evaluators / max(1, total_evaluators) < MIN_VALID_EVALUATOR_RATIO:
        return {
            "audit_status": "failed",
            "reason": "Insufficient valid evaluator responses",
            "valid_evaluators": valid_evaluators,
            "expected_evaluators": total_evaluators
        }

    status = "complete" if valid_evaluators == total_evaluators else "partial"

    aggregated = []
    for claim in canonical_claims:
        cid = claim["claim_id"]
        source_counts = Counter()
        assess_counts = Counter()

        for audit in successful_audits:
            verdicts = audit.get("claim_verdicts", {})
            if cid in verdicts:
                v = verdicts[cid]
                source_counts[v.get("source_support")] += 1
                assess_counts[v.get("substantive_assessment")] += 1

        aggregated.append({
            "claim_id": cid,
            "canonical_text": claim["canonical_text"],
            "support_counts": dict(source_counts),
            "assessment_counts": dict(assess_counts)
        })

    return {
        "audit_status": status,
        "valid_evaluators": valid_evaluators,
        "expected_evaluators": total_evaluators,
        "claims_evaluated": len(canonical_claims),
        "aggregated_claims": aggregated
    }


def format_aggregate_verdicts_for_prompt(aggregated_2b: Dict[str, Any]) -> str:
    """Format the canonical Stage 2B aggregate as authoritative Stage 3 context with compaction."""
    claims = aggregated_2b.get("aggregated_claims") or []

    contested_count = 0
    strong_count = 0

    contested_lines = []
    strong_lines = []

    for claim in claims:
        support = claim.get("support_counts") or {}
        assessment = claim.get("assessment_counts") or {}

        is_contested = any(support.get(k, 0) > 0 for k in ("partially_supported", "unsupported", "contradicted", "unverifiable")) or \
                       any(assessment.get(k, 0) > 0 for k in ("requires_qualification", "unsound", "unverifiable"))

        claim_id = claim.get("claim_id", "unknown")
        text = claim.get("canonical_text", "")

        if is_contested:
            contested_count += 1
            contested_lines.append(
                f'- {claim_id} | text="{text}" '
                f'| support_counts={json.dumps(support, sort_keys=True)} '
                f'| assessment_counts={json.dumps(assessment, sort_keys=True)}'
            )
        else:
            strong_count += 1
            strong_lines.append(
                f'- {claim_id} | text="{text}" | status=strong (sound/supported)'
            )

    header_lines = [
        f'audit_status: {aggregated_2b.get("audit_status", "unknown")}',
        f'claims_evaluated: {aggregated_2b.get("claims_evaluated", len(claims))}',
        f'valid_evaluators: {aggregated_2b.get("valid_evaluators", 0)}',
        f'expected_evaluators: {aggregated_2b.get("expected_evaluators", 0)}',
        f'total_contested_claims: {contested_count}',
        f'total_strong_claims: {strong_count}',
    ]

    budget_chars = 20000
    accumulated_chars = 0
    kept_strong_lines = []
    truncated_count = 0

    for line in strong_lines:
        if accumulated_chars + len(line) + 1 <= budget_chars:
            kept_strong_lines.append(line)
            accumulated_chars += len(line) + 1
        else:
            truncated_count += 1

    if truncated_count > 0:
        kept_strong_lines.append(
            f'[TRUNCATION METADATA: {truncated_count} strong claims omitted due to prompt size budget]'
        )

    all_lines = header_lines + ["\nCONTESTED/FLAWED CLAIMS (FULL METADATA):"] + contested_lines
    if kept_strong_lines:
        all_lines += ["\nSTRONG/SOUND CLAIMS (COMPACT):"] + kept_strong_lines

    return "\n".join(all_lines)


def format_audit_corrections_for_stage4(
    aggregated_2b: Dict[str, Any],
    stage2b_results: List[Dict[str, Any]],
    stage2c_result: Dict[str, Any],
) -> str:
    """Format only rejected/qualified/contested audit claims for Stage 4."""
    record = stage2c_result.get("record") or {}
    reject_ids = set(record.get("reject") or [])
    qualify_ids = set(record.get("qualify") or [])
    claim_lookup = {
        claim.get("claim_id"): claim
        for claim in (aggregated_2b.get("aggregated_claims") or [])
    }
    contested_ids = set()
    for claim_id, claim in claim_lookup.items():
        support_counts = claim.get("support_counts") or {}
        assessment_counts = claim.get("assessment_counts") or {}
        if any(support_counts.get(key, 0) for key in ("partially_supported", "unsupported", "contradicted", "unverifiable")):
            contested_ids.add(claim_id)
        if any(assessment_counts.get(key, 0) for key in ("requires_qualification", "unsound", "unverifiable")):
            contested_ids.add(claim_id)

    selected_ids = reject_ids | qualify_ids | contested_ids
    lines = []
    for claim_id in sorted(selected_ids):
        claim = claim_lookup.get(claim_id, {})
        disposition = (
            "REJECT" if claim_id in reject_ids
            else "QUALIFY" if claim_id in qualify_ids
            else "CONTESTED"
        )
        lines.append(
            f'- {claim_id} [{disposition}] "{claim.get("canonical_text", "")}"; '
            f'support_counts={json.dumps(claim.get("support_counts", {}), sort_keys=True)}; '
            f'assessment_counts={json.dumps(claim.get("assessment_counts", {}), sort_keys=True)}'
        )
        reasons = []
        for result in stage2b_results:
            detail = (result.get("claim_verdicts") or {}).get(claim_id) or {}
            reason = str(detail.get("reason", "")).strip()
            if reason and reason not in reasons:
                reasons.append(reason)
        for reason in reasons:
            lines.append(f"  - Required correction basis: {reason}")

    for label, values in (
        ("Authority gap", record.get("authority_gaps") or []),
        ("Record gap", record.get("record_gaps") or []),
        ("Stage 3 constraint", record.get("stage3_constraints") or []),
    ):
        for value in values:
            lines.append(f"- {label}: {value}")

    return "\n".join(lines) if lines else "No rejected or qualified claims were identified."


async def stage2c_adjudicate(
    aggregated_data: Dict[str, Any],
    conversation_id: str,
    settings: Any,
    audit_profile: Optional[str] = None,
    expected_claim_ids: Optional[List[str]] = None,
    chairman_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Stage 2C synthesis by Chairman model."""
    if aggregated_data.get("audit_status") == "failed":
        return {"error": True, "error_message": "Stage 2B failed quorum. Cannot run Stage 2C."}

    profile = audit_profile or getattr(settings, "audit_profile", "general")
    if profile == "legal":
        from .prompts import STAGE2C_LEGAL_PROMPT
        prompt_template = STAGE2C_LEGAL_PROMPT
    else:
        from .prompts import STAGE2C_GENERAL_PROMPT
        prompt_template = STAGE2C_GENERAL_PROMPT

    prompt = prompt_template.format(
        aggregated_audits_text=json.dumps(aggregated_data.get("aggregated_claims", []), indent=2)
    )
    prompt = apply_response_language(prompt, settings.response_language)

    messages = [{"role": "user", "content": prompt}]
    chairman = chairman_override or get_chairman_model()

    last_error = None
    attempts_ledger = []
    for attempt in range(2):
        try:
            session_id = f"{conversation_id}-2c-{attempt}"
            response = await _query_model_gated(
                chairman, messages, timeout=120, temperature=0.2, conversation_id=session_id,
                max_output_tokens=STAGE2C_MAX_OUTPUT_TOKENS
            )

            if response.get("error"):
                last_error = response.get("error_message")
                attempts_ledger.append({
                    "attempt": attempt + 1,
                    "status": "api_error",
                    "usage": response.get("usage"),
                    "cost": response.get("cost"),
                })
                break

            content = response.get("content", "")
            try:
                result = extract_json_block(content)
                if not isinstance(result, dict):
                    raise EvaluationError("Expected JSON dictionary for correction record.")

                # Basic validation
                for k in ["adopt", "reject", "qualify", "authority_gaps", "record_gaps", "stage3_constraints"]:
                    if k not in result or not isinstance(result[k], list):
                        raise EvaluationError(f"Missing or invalid key: {k}")

                # Verify Stage 2C claims against the actual list of canonical claim IDs
                if expected_claim_ids:
                    valid_set = set(expected_claim_ids)
                    for k in ["adopt", "reject", "qualify"]:
                        for cid in result[k]:
                            if cid not in valid_set:
                                raise EvaluationError(f"Stage 2C returned invalid/unknown claim ID '{cid}' in key '{k}'")

                # Success
                attempts_ledger.append({
                    "attempt": attempt + 1,
                    "status": "success",
                    "usage": response.get("usage"),
                    "cost": response.get("cost"),
                })
                return {
                    "record": result,
                    "model": chairman,
                    "raw_output": content,
                    "usage": response.get("usage"),
                    "cost": response.get("cost"),
                    "attempts": attempts_ledger,
                }
            except EvaluationError as e:
                last_error = str(e)
                attempts_ledger.append({
                    "attempt": attempt + 1,
                    "status": "validation_failed",
                    "usage": response.get("usage"),
                    "cost": response.get("cost"),
                })
                if attempt == 0:
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": f"Validation Error: {e}\nProvide valid JSON."})
        except Exception as e:
            last_error = str(e)
            attempts_ledger.append({
                "attempt": attempt + 1,
                "status": "exception",
                "usage": None,
                "cost": None,
            })
            break

    return {
        "error": True,
        "error_message": f"Stage 2C failed: {last_error}",
        "model": chairman,
        "attempts": attempts_ledger,
    }


async def run_audit_pipeline(
    user_query: str,
    search_context: str = "",
    request: Any = None,
    execution_mode: str = "full",
    models_override: Optional[List[str]] = None,
    chairman_override: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    debate_rounds: Optional[int] = None,
    conversation_id: Optional[str] = None,
    audit_profile: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Orchestrate the 3-stage Audit Pipeline."""
    settings = get_settings()

    async def disconnect_check():
        if request and hasattr(request, "is_disconnected"):
            return await request.is_disconnected()
        return False

    async def check_disconnect():
        if await disconnect_check():
            raise asyncio.CancelledError("Client disconnected")

    # --- Stage 1 ---
    yield {"type": "stage1_start", "round": 1}
    await asyncio.sleep(0.05)

    stage1_results = []
    total_models = 0

    async for item in stage1_collect_responses(
        user_query, search_context, request,
        models_override=models_override, history=history, conversation_id=conversation_id
    ):
        if isinstance(item, int):
            total_models = item
            yield {"type": "stage1_init", "total": total_models, "round": 1}
            continue
        if isinstance(item, dict) and item.get("type") == "provider_status":
            yield {**item, "round": 1}
            continue
        if isinstance(item, dict) and item.get("paused"):
            yield {"type": "stage1_pause", "data": item, "round": 1}
            continue
        stage1_results.append(item)
        yield {
            "type": "stage1_progress",
            "data": item,
            "count": len(stage1_results),
            "total": total_models,
            "round": 1
        }

    successful_results = [r for r in stage1_results if not r.get("error") and r.get("response")]
    if not successful_results:
        yield {
            "type": "debate_complete",
            "rounds": [{"stage1": stage1_results}],
            "critique_mode": "audit",
            "debate_rounds_configured": 1,
            "debate_rounds_executed": 1,
            "convergence_status": "not_applicable",
            "converged": False,
            "cost_report": None
        }
        return

    if execution_mode == "chat_only":
        cost_report = None
        yield {
            "type": "debate_complete",
            "rounds": [{"stage1": stage1_results}],
            "critique_mode": "audit",
            "debate_rounds_configured": 1,
            "debate_rounds_executed": 1,
            "convergence_status": "not_applicable",
            "converged": False,
            "cost_report": cost_report,
        }
        return

    # --- Stage 2A ---
    await check_disconnect()
    yield {"type": "stage2a_start", "round": 1}
    stage2a_results = []
    label_to_model = {}
    async for item in stage2a_collect_evaluations(
        user_query, search_context, stage1_results, conversation_id, settings,
        audit_profile=audit_profile, disconnect_check=disconnect_check
    ):
        if item["type"] == "stage2a_init":
            yield item
        elif item["type"] == "provider_status":
            yield item
        elif item["type"] == "stage2a_progress":
            stage2a_results.append(item["data"])
            yield item
        elif item["type"] == "stage2a_complete":
            label_to_model = item["label_to_model"]
            from .council import calculate_audit_aggregate_rankings
            aggregate_rankings = calculate_audit_aggregate_rankings(stage2a_results, label_to_model)
            item["metadata"] = {
                "label_to_model": label_to_model,
                "aggregate_rankings": aggregate_rankings,
            }
            yield item
        elif item["type"] == "stage2a_error":
            yield item
            partial_round = {
                "stage1": stage1_results,
                "stage2": stage2a_results,
                "stage2a": stage2a_results,
                "metadata": {
                    "label_to_model": label_to_model,
                    "stage2a_results": stage2a_results,
                },
            }
            yield {
                "type": "debate_complete",
                "rounds": [partial_round],
                "critique_mode": "audit",
                "debate_rounds_configured": 1,
                "debate_rounds_executed": 1,
                "convergence_status": "failed",
                "converged": False,
                "error": {
                    "stage": "stage2a",
                    "status": item.get("status") or "stage2a_failed",
                    "message": item.get("message") or "Stage 2A evaluation failed.",
                },
                "cost_report": build_iterative_debate_cost_report([partial_round], None),
            }
            return

    # --- Material Claim Extraction ---
    await check_disconnect()
    responses_text = "\n\n".join([
        f"Response {label}:\n{s['response']}"
        for label, r in label_to_model.items()
        for s in successful_results if s["model"] == r
    ])

    raw_claims_result = await extract_material_claims(responses_text, conversation_id, settings, chairman_override=chairman_override)
    raw_claims = raw_claims_result.get("claims")
    canonical_claims = []
    if raw_claims:
        canonical_claims = normalize_and_deduplicate_claims(raw_claims)

    if not canonical_claims:
        logger.warning("No canonical claims extracted; aborting.")
        error_message = "No canonical claims extracted from responses."
        yield {
            "type": "stage2b_error",
            "status": "no_canonical_claims",
            "message": error_message,
        }
        partial_round = {
            "stage1": stage1_results,
            "stage2": stage2a_results,
            "stage2a": stage2a_results,
            "metadata": {
                "label_to_model": label_to_model,
                "aggregate_rankings": aggregate_rankings,
                "canonical_claims": [],
                "stage2a_results": stage2a_results,
            },
        }
        yield {
            "type": "debate_complete",
            "rounds": [partial_round],
            "critique_mode": "audit",
            "debate_rounds_configured": 1,
            "debate_rounds_executed": 1,
            "convergence_status": "failed",
            "converged": False,
            "error": {
                "stage": "claim_decomposition",
                "status": "no_canonical_claims",
                "message": error_message,
            },
            "cost_report": build_iterative_debate_cost_report([partial_round], None),
        }
        return

    # --- Stage 2B ---
    await check_disconnect()
    yield {"type": "stage2b_start", "round": 1}
    stage2b_results = []
    async for item in stage2b_collect_audits(
        user_query, search_context, stage1_results, canonical_claims, conversation_id, settings,
        audit_profile=audit_profile, disconnect_check=disconnect_check
    ):
        if item["type"] == "stage2b_init":
            yield item
        elif item["type"] == "provider_status":
            yield item
        elif item["type"] == "stage2b_progress":
            stage2b_results.append(item["data"])
            yield item
        elif item["type"] == "stage2b_complete":
            yield item
        elif item["type"] == "stage2b_error":
            yield item
            partial_round = {
                "stage1": stage1_results,
                "stage2": stage2a_results,
                "stage2a": stage2a_results,
                "stage2b": stage2b_results,
                "metadata": {
                    "label_to_model": label_to_model,
                    "aggregate_rankings": aggregate_rankings,
                    "canonical_claims": canonical_claims,
                    "stage2a_results": stage2a_results,
                    "stage2b_results": stage2b_results,
                },
            }
            yield {
                "type": "debate_complete",
                "rounds": [partial_round],
                "critique_mode": "audit",
                "debate_rounds_configured": 1,
                "debate_rounds_executed": 1,
                "convergence_status": "failed",
                "converged": False,
                "error": {
                    "stage": "stage2b",
                    "status": item.get("status") or "stage2b_failed",
                    "message": item.get("message") or "Stage 2B audit failed.",
                },
                "cost_report": build_iterative_debate_cost_report([partial_round], None),
            }
            return

    # --- Stage 2C ---
    await check_disconnect()
    yield {"type": "stage2c_start", "round": 1}
    aggregated_2b = aggregate_2b_results(stage2b_results, canonical_claims)
    stage2c_result = await stage2c_adjudicate(
        aggregated_2b, conversation_id, settings,
        audit_profile=audit_profile,
        expected_claim_ids=[c["claim_id"] for c in canonical_claims],
        chairman_override=chairman_override,
    )
    if stage2c_result.get("error"):
        error_message = stage2c_result.get("error_message") or "Stage 2C adjudication failed"
        yield {
            "type": "stage2c_error",
            "status": "failed_adjudication",
            "message": error_message,
        }
        partial_round = {
            "stage1": stage1_results,
            "stage2": stage2a_results,
            "stage2a": stage2a_results,
            "stage2b": stage2b_results,
            "stage2c": stage2c_result,
            "metadata": {
                "label_to_model": label_to_model,
                "aggregate_rankings": aggregate_rankings,
                "canonical_claims": canonical_claims,
                "aggregated_2b": aggregated_2b,
                "aggregate_claim_verdicts": aggregated_2b,
                "stage2a_results": stage2a_results,
                "stage2b_results": stage2b_results,
                "stage2c_result": stage2c_result,
            },
        }
        yield {
            "type": "debate_complete",
            "rounds": [partial_round],
            "critique_mode": "audit",
            "debate_rounds_configured": 1,
            "debate_rounds_executed": 1,
            "convergence_status": "failed",
            "converged": False,
            "error": {
                "stage": "stage2c",
                "status": "failed_adjudication",
                "message": error_message,
            },
            "cost_report": build_iterative_debate_cost_report([partial_round], None),
        }
        return
    yield {"type": "stage2c_complete", "data": stage2c_result, "aggregated": aggregated_2b, "round": 1}

    # --- Stage 3 Synthesis ---
    stage3_response = None
    if execution_mode == "full":
        await check_disconnect()
        yield {"type": "stage3_start"}

        # Build synthesis prompt using Stage 2A and 2C Correction Record
        stage2a_text = "Holistic Evaluations (Stage 2A):\n"
        for r in stage2a_results:
            if not r.get("error"):
                stage2a_text += f"\nEvaluator {r['model']}:\n{json.dumps(r.get('parsed', {}), indent=2)}\n"

        stage2c_text = "Specific Correction Record (Stage 2C):\n"
        if not stage2c_result.get("error"):
            stage2c_text += json.dumps(stage2c_result.get("record", {}), indent=2)
        else:
            stage2c_text += "Not available.\n"

        stage1_text, _ = build_stage_texts(stage1_results, [])
        claim_audit_text = format_aggregate_verdicts_for_prompt(aggregated_2b)
        synthesis_prompt = STAGE3_AUDIT_PROMPT_DEFAULT.format(
            user_query=user_query,
            responses_text=stage1_text,
            rankings_text=stage2a_text + "\n" + stage2c_text,
            claim_audit_text=claim_audit_text,
            search_context_block=f"Context from Web Search:\n{search_context}\n" if search_context else ""
        )
        synthesis_prompt = apply_response_language(synthesis_prompt, settings.response_language)

        chairman = chairman_override or get_chairman_model()
        messages = [{"role": "user", "content": synthesis_prompt}]

        try:
            await check_disconnect()
            session_id = f"{conversation_id}-3"
            final_res = await query_model(
                chairman,
                messages,
                temperature=settings.chairman_temperature,
                conversation_id=session_id,
            )
            if not isinstance(final_res, dict):
                stage3_response = {
                    "model": chairman,
                    "error": True,
                    "error_message": "Stage 3 query returned an invalid response.",
                }
            elif final_res.get("error"):
                stage3_response = {
                    "model": chairman,
                    "error": True,
                    "error_message": final_res.get("error_message") or "Stage 3 provider error.",
                    "usage": final_res.get("usage"),
                    "cost": final_res.get("cost"),
                }
            else:
                stage3_response = {
                    "model": chairman,
                    "response": final_res.get("content", ""),
                    "usage": final_res.get("usage"),
                    "cost": final_res.get("cost"),
                }
        except Exception as e:
            stage3_response = {"model": chairman, "error": True, "error_message": str(e)}

        yield {"type": "stage3_complete", "data": stage3_response}

    # --- Stage 4 Corrected Draft ---
    stage4_result = None
    if (
        execution_mode == "full"
        and stage3_response
        and not stage3_response.get("error")
        and stage3_response.get("response")
    ):
        await check_disconnect()
        yield {"type": "stage4_start"}
        await asyncio.sleep(0.05)

        from .prompts import STAGE4_CORRECTED_DRAFT_PROMPT

        custom_stage4_prompt = getattr(settings, "stage4_prompt", "")
        corrections_text = format_audit_corrections_for_stage4(
            aggregated_2b,
            stage2b_results,
            stage2c_result,
        )
        stage4_result = await generate_corrected_draft(
            synthesize_fn=stage3_synthesize_final,
            default_template=STAGE4_CORRECTED_DRAFT_PROMPT,
            custom_template=custom_stage4_prompt if isinstance(custom_stage4_prompt, str) else "",
            total_rounds=1,
            original_text=user_query,
            verdict_text=stage3_response.get("response", ""),
            corrections_text=corrections_text,
            chairman_override=chairman_override,
            conversation_id=conversation_id,
            max_attempts=2,
            minimum_word_ratio=0.85,
        )
        yield {"type": "stage4_complete", "data": stage4_result}

    rounds_data = [{
        "stage1": stage1_results,
        "stage2": stage2a_results,  # for compatibility with frontend that expects stage2
        "stage2a": stage2a_results,
        "stage2b": stage2b_results,
        "stage2c": stage2c_result,
        "stage3": stage3_response,
        "metadata": {
            "label_to_model": label_to_model,
            "aggregate_rankings": aggregate_rankings if 'aggregate_rankings' in locals() else calculate_audit_aggregate_rankings(stage2a_results, label_to_model),
            "canonical_claims": canonical_claims,
            "aggregated_2b": aggregated_2b,
            "aggregate_claim_verdicts": aggregated_2b,
            "stage2a_results": stage2a_results,
            "stage2b_results": stage2b_results,
            "stage2c_result": stage2c_result,
        }
    }]

    # A provider error dictionary (rather than a raised exception) must surface
    # as a failed debate, not silently skip Stage 4 and complete.
    if (
        execution_mode == "full"
        and stage3_response
        and stage3_response.get("error")
    ):
        yield {
            "type": "debate_complete",
            "rounds": rounds_data,
            "critique_mode": "audit",
            "debate_rounds_configured": 1,
            "debate_rounds_executed": 1,
            "convergence_status": "failed",
            "converged": False,
            "error": {
                "stage": "stage3",
                "status": "failed_synthesis",
                "message": stage3_response.get("error_message") or "Stage 3 synthesis failed.",
            },
            "cost_report": build_iterative_debate_cost_report(rounds_data, None),
        }
        return

    yield {
        "type": "debate_complete",
        "rounds": rounds_data,
        "critique_mode": "audit",
        "debate_rounds_configured": 1,
        "debate_rounds_executed": 1,
        "convergence_status": "not_applicable",
        "converged": False,
        "stage4": stage4_result,
        "cost_report": build_iterative_debate_cost_report(rounds_data, stage4_result),
    }
