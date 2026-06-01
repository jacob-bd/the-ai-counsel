"""FastAPI backend for LLM Council."""

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Any, Literal, Optional
import logging
import os
import secrets
import uuid
import json
import asyncio

from . import storage
from .council import generate_conversation_title, generate_search_query, stage1_collect_responses, stage2_collect_rankings, stage3_synthesize_final, calculate_aggregate_rankings, PROVIDERS
from .config import get_chairman_model, get_council_models
from .costs import build_advisor_cost_report, build_council_cost_report, build_iterative_debate_cost_report
from .model_preflight import build_preflight_error_message, preflight_models
from .search import perform_web_search, SearchProvider
from .settings import get_settings, save_settings, update_settings, Settings, DEFAULT_COUNCIL_MODELS, DEFAULT_CHAIRMAN_MODEL, AVAILABLE_MODELS, PROMPT_DEFAULTS
from .personas import get_all_personas, save_persona_override, delete_persona_override, get_persona
from .advisors import run_debate
from .debate import run_iterative_debate, MAX_DEBATE_ROUNDS

logger = logging.getLogger(__name__)

# In-memory registry of active streaming council/debate runs.
# Key: conversation_id, Value: progress snapshot updated as stages complete.
# NOTE: process-local — only valid for single-worker deployments.
_active_runs: Dict[str, Dict[str, Any]] = {}


def _register_run(conversation_id: str, execution_mode: str) -> None:
    _active_runs[conversation_id] = {
        "stage": "initializing",
        "execution_mode": execution_mode,
        "progress": {
            "stage1": {"total": 0},
            "stage2": {"total": 0},
        },
    }


def _save_partial_results(
    conversation_id: str,
    body,
    stage1_results: list,
    stage2_results: list,
    stage3_result,
    conversation: dict,
    label_to_model: Optional[dict] = None,
    aggregate_rankings=None,
    extra_metadata: Optional[dict] = None,
) -> None:
    partial_metadata: Dict[str, Any] = {
        "execution_mode": body.execution_mode,
        "incomplete": True,
    }
    if extra_metadata:
        partial_metadata.update(extra_metadata)
    if label_to_model:
        partial_metadata["label_to_model"] = label_to_model
    if aggregate_rankings:
        partial_metadata["aggregate_rankings"] = aggregate_rankings
    if "cost_report" not in partial_metadata:
        partial_metadata["cost_report"] = build_council_cost_report(
            stage1_results,
            stage2_results,
            stage3_result,
        )
    storage.add_assistant_message(
        conversation_id,
        stage1_results,
        stage2_results if body.execution_mode in ["chat_ranking", "full"] and stage2_results else None,
        stage3_result if body.execution_mode == "full" else None,
        partial_metadata,
        conversation=conversation,
    )

app = FastAPI(title="The AI Counsel API")

# Sensitive settings endpoints (export/import/reset) leak or wipe API keys, so
# they MUST be authenticated. Behavior:
#   - If LLM_COUNCIL_ADMIN_TOKEN is set, require `Authorization: Bearer <token>`.
#   - Otherwise, only allow requests from loopback (127.0.0.1 / ::1).
# This keeps the default Docker deployment safe even when bound to 0.0.0.0,
# while letting operators opt in to remote admin via a strong token.
_ADMIN_TOKEN = os.getenv("LLM_COUNCIL_ADMIN_TOKEN", "").strip()
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _is_loopback_host(host: str) -> bool:
    """Return whether a host string represents a loopback caller."""
    if not host:
        return False
    normalized = host.strip().strip("[]").lower()
    if normalized in _LOOPBACK_HOSTS:
        return True
    return False


def _forwarded_client_hosts(request: Request) -> List[str]:
    """Extract original client hosts from common reverse-proxy headers."""
    hosts: List[str] = []
    x_real_ip = request.headers.get("x-real-ip", "").strip()
    if x_real_ip:
        hosts.append(x_real_ip)

    x_forwarded_for = request.headers.get("x-forwarded-for", "")
    hosts.extend(part.strip() for part in x_forwarded_for.split(",") if part.strip())

    forwarded = request.headers.get("forwarded", "")
    for entry in forwarded.split(","):
        for part in entry.split(";"):
            key, sep, value = part.strip().partition("=")
            if sep and key.lower() == "for":
                hosts.append(value.strip().strip('"'))

    return hosts


def _require_admin(request: Request) -> None:
    """Auth guard for endpoints that read or rewrite stored credentials."""
    if _ADMIN_TOKEN:
        auth = request.headers.get("authorization", "")
        prefix = "Bearer "
        if not auth.startswith(prefix) or not secrets.compare_digest(auth[len(prefix):], _ADMIN_TOKEN):
            raise HTTPException(status_code=401, detail="Admin authentication required")
        return
    client_host = request.client.host if request.client else ""
    if not _is_loopback_host(client_host):
        raise HTTPException(
            status_code=403,
            detail=(
                "Admin endpoint disabled for non-loopback clients. "
                "Set LLM_COUNCIL_ADMIN_TOKEN to allow remote access."
            ),
        )
    forwarded_hosts = _forwarded_client_hosts(request)
    if any(not _is_loopback_host(host) for host in forwarded_hosts):
        raise HTTPException(
            status_code=403,
            detail=(
                "Admin endpoint disabled for proxied non-loopback clients. "
                "Set LLM_COUNCIL_ADMIN_TOKEN to allow remote access."
            ),
        )

FRONTEND_DIST_DIR = os.getenv(
    "FRONTEND_DIST_DIR",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist"),
)

CORS_FRONTEND_HOSTS = [
    origin.strip()
    for origin in os.getenv("FRONTEND_HOST", "").split(",")
    if origin.strip()
]

_dev_cors_regex = r"https?://(localhost|127\.0\.0\.1|(?:\d{1,3}\.){3}\d{1,3}|\[[a-fA-F0-9:]+\]):\d+"

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_FRONTEND_HOSTS,
    allow_origin_regex=_dev_cors_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    mode: str = "council"


class StartDebateRequest(BaseModel):
    """Request to start an advisor debate."""
    question: str
    persona_ids: List[str]
    model_assignments: Optional[Dict[str, str]] = None
    default_model: Optional[str] = None
    tiebreaker_model: Optional[str] = None
    max_rounds: int = 3
    web_search: bool = False
    search_provider: Optional[str] = None


ExecutionMode = Literal["chat_only", "chat_ranking", "full"]


class SendMessageRequest(BaseModel):
    content: str
    web_search: bool = False
    search_provider: Optional[str] = None
    execution_mode: ExecutionMode = "full"
    council_models: Optional[List[str]] = None
    chairman_model: Optional[str] = None
    debate_rounds: Optional[int] = None


class AskRequest(BaseModel):
    content: str
    models: Optional[List[str]] = None
    chairman_model: Optional[str] = None
    web_search: bool = False
    execution_mode: ExecutionMode = "chat_only"


def _validate_execution_mode(mode: str) -> None:
    """Validate execution_mode for endpoints using Optional[str] (e.g. settings update)."""
    valid = ("chat_only", "chat_ranking", "full")
    if mode not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid execution_mode. Must be one of: {list(valid)}")


def _apply_search_env(settings: Settings, provider_override: Optional[str] = None) -> SearchProvider:
    """Set env vars for the active search provider and return it."""
    provider_str = provider_override if provider_override else settings.search_provider
    provider = SearchProvider(provider_str)
    if settings.serper_api_key and provider == SearchProvider.SERPER:
        os.environ["SERPER_API_KEY"] = settings.serper_api_key
    if settings.tavily_api_key and provider == SearchProvider.TAVILY:
        os.environ["TAVILY_API_KEY"] = settings.tavily_api_key
    if settings.brave_api_key and provider == SearchProvider.BRAVE:
        os.environ["BRAVE_API_KEY"] = settings.brave_api_key
    if settings.tinyfish_api_key and provider == SearchProvider.TINYFISH:
        os.environ["TINYFISH_API_KEY"] = settings.tinyfish_api_key
    return provider


async def _fetch_search_context(content: str, settings: Settings, provider_override: Optional[str] = None) -> tuple:
    """Run web search and return (search_context, search_query)."""
    provider = _apply_search_env(settings, provider_override)
    # Use LLM query generation only when explicitly selected and not using DuckDuckGo
    # (DDG has built-in query optimization; no need to pre-process)
    if settings.search_keyword_extraction == "llm" and provider != SearchProvider.DUCKDUCKGO:
        search_query = await generate_search_query(content)
    else:
        search_query = content
    search_result = await perform_web_search(
        search_query,
        settings.search_result_count,
        provider,
        settings.full_content_results,
        settings.search_keyword_extraction,
        hybrid_mode=settings.search_hybrid_mode
    )
    return search_result["results"], search_query, search_result


def _build_chat_history(conversation: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extract prior turns from a conversation into [{role, content}, ...] for multi-turn context."""
    history = []
    for msg in conversation.get("messages", []):
        if msg["role"] == "user":
            history.append({"role": "user", "content": msg["content"]})
        elif msg["role"] == "assistant":
            # Prefer chairman synthesis (stage3), fall back to first stage1 response
            content = None
            if msg.get("stage3") and msg["stage3"].get("response"):
                content = msg["stage3"]["response"]
            elif msg.get("stage1") and len(msg["stage1"]) > 0:
                first_success = next(
                    (r for r in msg["stage1"] if not r.get("error")),
                    msg["stage1"][0]
                )
                content = first_success.get("response", "")
            if content:
                history.append({"role": "assistant", "content": content})
    return history


def _build_council_preflight_models(body: SendMessageRequest) -> List[str]:
    """Return the models that must be available before a council run starts."""
    models = list(body.council_models or get_council_models())
    if body.execution_mode == "full":
        models.append(body.chairman_model or get_chairman_model())
    return models


async def _run_model_preflight(models: List[str]) -> str:
    """Return a user-facing error message if model preflight fails."""
    result = await preflight_models(models)
    if result.ok:
        return ""
    return build_preflight_error_message(result)


from dataclasses import dataclass, field


@dataclass
class PipelineResult:
    stage1: List[Dict[str, Any]] = field(default_factory=list)
    stage2: List[Dict[str, Any]] = field(default_factory=list)
    stage3: Optional[Dict[str, Any]] = None
    label_to_model: Dict[str, str] = field(default_factory=dict)
    aggregate_rankings: Any = None
    cost_report: Optional[Dict[str, Any]] = None


async def _run_council_pipeline(
    content: str,
    execution_mode: str,
    search_context: str,
    *,
    models_override: Optional[List[str]] = None,
    chairman_override: Optional[str] = None,
    request: Optional[Request] = None,
    history: Optional[List[Dict[str, str]]] = None,
    preflight: bool = True,
) -> PipelineResult:
    """Shared orchestration for stage1 → stage2 → stage3 (non-streaming)."""
    result = PipelineResult()

    if preflight:
        body = SendMessageRequest(
            content=content,
            execution_mode=execution_mode,
            council_models=models_override,
            chairman_model=chairman_override,
        )
        preflight_error = await _run_model_preflight(_build_council_preflight_models(body))
        if preflight_error:
            raise HTTPException(status_code=400, detail=preflight_error)

    async for item in stage1_collect_responses(content, search_context, request=request, models_override=models_override, history=history):
        if isinstance(item, int):
            continue
        result.stage1.append(item)

    if not any(r for r in result.stage1 if not r.get('error')):
        errors = [r.get('error_message', 'Unknown error') for r in result.stage1 if r.get('error')]
        raise HTTPException(status_code=502, detail=f"All models failed: {'; '.join(errors)}")

    if execution_mode in ("chat_ranking", "full"):
        async for item in stage2_collect_rankings(content, result.stage1, search_context, request=request):
            if isinstance(item, dict) and not item.get('model'):
                result.label_to_model = item
                continue
            result.stage2.append(item)
        result.aggregate_rankings = calculate_aggregate_rankings(result.stage2, result.label_to_model) if result.stage2 else None

    if execution_mode == "full":
        result.stage3 = await stage3_synthesize_final(
            content, result.stage1, result.stage2, search_context,
            chairman_override=chairman_override
        )

    result.cost_report = build_council_cost_report(result.stage1, result.stage2, result.stage3)
    return result


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""
    id: str
    created_at: str
    title: str
    mode: str = "council"
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""
    id: str
    created_at: str
    title: str
    mode: str = "council"
    messages: List[Dict[str, Any]]





@app.get("/api/health")
async def health_check(request: Request):
    """Health check endpoint."""
    host = request.headers.get("host", "localhost:8001")
    scheme = request.headers.get("x-forwarded-proto", "http")
    return {
        "status": "ok",
        "service": "The AI Counsel API",
        "mcp": {
            "sse_url": f"{scheme}://{host}/mcp/sse",
            "tools": 10,
        },
    }


@app.get("/")
async def root():
    """Serve the frontend when built, otherwise return a basic health check."""
    index_path = os.path.join(FRONTEND_DIST_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"status": "ok", "service": "The AI Counsel API"}


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""
    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id, mode=request.mode)
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    deleted = storage.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted"}


@app.get("/api/conversations/{conversation_id}/progress")
async def get_conversation_progress(conversation_id: str):
    """Return live progress for an active streaming run, or {active: false} if none."""
    run = _active_runs.get(conversation_id)
    if run is None:
        return {"active": False}
    s1 = run.get("stage1_responses") or []
    s2 = run.get("stage2_responses") or []
    return {
        "active": True,
        "stage": run["stage"],
        "execution_mode": run["execution_mode"],
        "progress": {
            "stage1": {"count": len(s1), "total": run["progress"]["stage1"]["total"]},
            "stage2": {"count": len(s2), "total": run["progress"]["stage2"]["total"]},
        },
        "stage1": s1 or None,
        "stage2": s2 or None,
        "stage3": run.get("stage3_response"),
        "stage4": run.get("stage4_response"),
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, body: SendMessageRequest, request: Request):
    """Send a message and stream the 3-stage council process."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    history = _build_chat_history(conversation)
    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    async def event_generator():
        title_task = None
        stage1_results = []
        stage2_results = []
        stage3_result = None
        label_to_model = {}
        aggregate_rankings = {}
        cost_report = None
        _register_run(conversation_id, body.execution_mode)
        try:
            storage.add_user_message(conversation_id, body.content, conversation=conversation)

            preflight_error = await _run_model_preflight(_build_council_preflight_models(body))
            if preflight_error:
                storage.add_error_message(conversation_id, preflight_error)
                yield f"data: {json.dumps({'type': 'error', 'message': preflight_error})}\n\n"
                return

            # Start title generation in parallel (don't await yet)
            if is_first_message:
                title_task = asyncio.create_task(generate_conversation_title(body.content))

            search_context = ""
            search_query = ""
            if body.search_provider or body.web_search:
                if await request.is_disconnected():
                    raise asyncio.CancelledError("Client disconnected")

                settings = get_settings()
                provider = _apply_search_env(settings, body.search_provider)

                _active_runs[conversation_id]["stage"] = "search"
                yield f"data: {json.dumps({'type': 'search_start', 'data': {'provider': provider.value}})}\n\n"

                if await request.is_disconnected():
                    raise asyncio.CancelledError("Client disconnected")

                # Use LLM query generation only when explicitly selected and not using DuckDuckGo
                # (DDG has built-in query optimization; no need to pre-process)
                if settings.search_keyword_extraction == "llm" and provider != SearchProvider.DUCKDUCKGO:
                    search_query = await generate_search_query(body.content)
                else:
                    search_query = body.content

                if await request.is_disconnected():
                    raise asyncio.CancelledError("Client disconnected")

                search_result = await perform_web_search(
                    search_query,
                    settings.search_result_count,
                    provider,
                    settings.full_content_results,
                    settings.search_keyword_extraction,
                    hybrid_mode=settings.search_hybrid_mode
                )
                search_context = search_result["results"]
                extracted_query = search_result["extracted_query"]
                search_intent = search_result.get("intent", "unknown")
                yield f"data: {json.dumps({'type': 'search_complete', 'data': {'search_query': search_query, 'extracted_query': extracted_query, 'search_context': search_context, 'provider': provider.value, 'intent': search_intent}})}\n\n"
                await asyncio.sleep(0.05)

            # Stage 1: Collect responses
            _active_runs[conversation_id]["stage"] = "stage1"
            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
            await asyncio.sleep(0.05)

            total_models = 0

            async for item in stage1_collect_responses(body.content, search_context, request, models_override=body.council_models, history=history):
                if isinstance(item, int):
                    total_models = item
                    _active_runs[conversation_id]["progress"]["stage1"]["total"] = total_models
                    yield f"data: {json.dumps({'type': 'stage1_init', 'total': total_models})}\n\n"
                    continue

                stage1_results.append(item)
                _active_runs[conversation_id]["stage1_responses"] = stage1_results
                yield f"data: {json.dumps({'type': 'stage1_progress', 'data': item, 'count': len(stage1_results), 'total': total_models})}\n\n"
                await asyncio.sleep(0.01)

            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"
            await asyncio.sleep(0.05)

            # Check if any models responded successfully in Stage 1
            if not any(r for r in stage1_results if not r.get('error')):
                error_msg = 'All models failed to respond in Stage 1, likely due to rate limits or API errors. Please try again or adjust your model selection.'
                storage.add_error_message(conversation_id, error_msg)
                yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                return # Stop further processing

            # Stage 2: Only if mode is 'chat_ranking' or 'full'
            if body.execution_mode in ["chat_ranking", "full"]:
                _active_runs[conversation_id]["stage"] = "stage2"
                yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
                await asyncio.sleep(0.05)

                # Iterate over the async generator
                async for item in stage2_collect_rankings(body.content, stage1_results, search_context, request):
                    # First item is the label mapping
                    if isinstance(item, dict) and not item.get('model'):
                        label_to_model = item
                        _active_runs[conversation_id]["progress"]["stage2"]["total"] = len(label_to_model)
                        # Send init event with total count
                        yield f"data: {json.dumps({'type': 'stage2_init', 'total': len(label_to_model)})}\n\n"
                        continue

                    # Subsequent items are results
                    stage2_results.append(item)
                    _active_runs[conversation_id]["stage2_responses"] = stage2_results

                    yield f"data: {json.dumps({'type': 'stage2_progress', 'data': item, 'count': len(stage2_results), 'total': len(label_to_model)})}\n\n"
                    await asyncio.sleep(0.01)

                aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
                yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate_rankings, 'search_query': search_query, 'search_context': search_context}})}\n\n"
                await asyncio.sleep(0.05)

            # Stage 3: Only if mode is 'full'
            if body.execution_mode == "full":
                _active_runs[conversation_id]["stage"] = "stage3"
                yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
                await asyncio.sleep(0.05)

                # Check for disconnect before starting Stage 3
                if await request.is_disconnected():
                    print("Client disconnected before Stage 3")
                    raise asyncio.CancelledError("Client disconnected")

                stage3_result = await stage3_synthesize_final(body.content, stage1_results, stage2_results, search_context, chairman_override=body.chairman_model)
                _active_runs[conversation_id]["stage3_response"] = stage3_result
                yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

            cost_report = build_council_cost_report(stage1_results, stage2_results, stage3_result)

            # Wait for title generation if it was started
            if title_task:
                try:
                    title = await title_task
                    storage.update_conversation_title(conversation_id, title)
                    conversation["title"] = title
                    yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"
                except Exception as e:
                    print(f"Error waiting for title task: {e}")

            # Save complete assistant message with metadata
            metadata = {
                "execution_mode": body.execution_mode,  # Save mode for historical context
                "cost_report": cost_report,
            }

            # Only include stage2/stage3 metadata if they were executed
            if body.execution_mode in ["chat_ranking", "full"]:
                metadata["label_to_model"] = label_to_model
                metadata["aggregate_rankings"] = aggregate_rankings

            if search_context:
                metadata["search_context"] = search_context
            if search_query:
                metadata["search_query"] = search_query

            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results if body.execution_mode in ["chat_ranking", "full"] else None,
                stage3_result if body.execution_mode == "full" else None,
                metadata,
                conversation=conversation
            )

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete', 'metadata': {'cost_report': cost_report}})}\n\n"

        except asyncio.CancelledError:
            print(f"Stream cancelled for conversation {conversation_id}")
            if stage1_results:
                try:
                    _save_partial_results(
                        conversation_id, body, stage1_results, stage2_results,
                        stage3_result, conversation,
                        label_to_model=label_to_model,
                        aggregate_rankings=aggregate_rankings,
                        extra_metadata={"cost_report": build_council_cost_report(stage1_results, stage2_results, stage3_result)},
                    )
                    print(f"Saved partial results: {len(stage1_results)} stage1, {len(stage2_results)} stage2")
                except Exception as save_err:
                    print(f"Could not save partial results: {save_err}")
            # Even if cancelled, try to save the title if it's ready or nearly ready
            if title_task:
                try:
                    title = await asyncio.wait_for(title_task, timeout=2.0)
                    storage.update_conversation_title(conversation_id, title)
                    print(f"Saved title despite cancellation: {title}")
                except Exception as e:
                    print(f"Could not save title during cancellation: {e}")
            raise
        except Exception as e:
            print(f"Stream error: {e}")
            # Save error to conversation history
            storage.add_error_message(conversation_id, f"Error: {str(e)}")
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            _active_runs.pop(conversation_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.post("/api/conversations/{conversation_id}/message/debate")
async def send_debate_message_stream(conversation_id: str, body: SendMessageRequest, request: Request):
    """Send a message and stream the multi-round iterative debate process."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    history = _build_chat_history(conversation)
    is_first_message = len(conversation["messages"]) == 0

    async def event_generator():
        title_task = None
        rounds_data = []
        final_stage1 = []
        final_stage2 = []
        final_stage3 = None
        final_label_to_model = {}
        final_aggregate_rankings = []
        final_canonical_claims = None
        final_aggregate_claim_verdicts = None
        final_stage4 = None
        cost_report = None
        debate_critique_mode = "freeform"
        debate_converged = False
        _register_run(conversation_id, body.execution_mode)
        try:
            storage.add_user_message(conversation_id, body.content, conversation=conversation)

            preflight_error = await _run_model_preflight(_build_council_preflight_models(body))
            if preflight_error:
                storage.add_error_message(conversation_id, preflight_error)
                yield f"data: {json.dumps({'type': 'error', 'message': preflight_error})}\n\n"
                return

            # Start title generation in parallel
            if is_first_message:
                title_task = asyncio.create_task(generate_conversation_title(body.content))

            search_context = ""
            search_query = ""
            if body.search_provider or body.web_search:
                if await request.is_disconnected():
                    raise asyncio.CancelledError("Client disconnected")

                settings = get_settings()
                provider = _apply_search_env(settings, body.search_provider)

                yield f"data: {json.dumps({'type': 'search_start', 'data': {'provider': provider.value}})}\n\n"

                if await request.is_disconnected():
                    raise asyncio.CancelledError("Client disconnected")

                if settings.search_keyword_extraction == "llm" and provider != SearchProvider.DUCKDUCKGO:
                    search_query = await generate_search_query(body.content)
                else:
                    search_query = body.content

                if await request.is_disconnected():
                    raise asyncio.CancelledError("Client disconnected")

                search_result = await perform_web_search(
                    search_query,
                    settings.search_result_count,
                    provider,
                    settings.full_content_results,
                    settings.search_keyword_extraction,
                    hybrid_mode=settings.search_hybrid_mode
                )
                search_context = search_result["results"]
                extracted_query = search_result["extracted_query"]
                search_intent = search_result.get("intent", "unknown")
                yield f"data: {json.dumps({'type': 'search_complete', 'data': {'search_query': search_query, 'extracted_query': extracted_query, 'search_context': search_context, 'provider': provider.value, 'intent': search_intent}})}\n\n"
                await asyncio.sleep(0.05)

            settings = get_settings()
            effective_rounds = body.debate_rounds if body.debate_rounds is not None else settings.debate_rounds
            effective_rounds = min(max(effective_rounds, 1), MAX_DEBATE_ROUNDS)

            async for event in run_iterative_debate(
                body.content, search_context, request, body.execution_mode,
                models_override=body.council_models,
                chairman_override=body.chairman_model,
                history=history,
                debate_rounds=effective_rounds,
            ):
                event_type = event.get("type")
                yield f"data: {json.dumps(event)}\n\n"
                await asyncio.sleep(0.01)

                run_info = _active_runs[conversation_id]
                if event_type == "search_start":
                    run_info["stage"] = "search"
                elif event_type == "stage1_start":
                    run_info["stage"] = "stage1"
                    run_info["progress"]["stage1"] = {"total": 0}
                elif event_type == "stage1_init":
                    run_info["progress"]["stage1"]["total"] = event.get("total", 0)
                elif event_type in ["stage1_complete", "stage1_progress"]:
                    stage1_data = event.get("data")
                    if isinstance(stage1_data, list):
                        run_info["stage1_responses"] = stage1_data
                    elif isinstance(stage1_data, dict):
                        responses = run_info.setdefault("stage1_responses", [])
                        seen = run_info.setdefault("_seen_stage1", set())
                        model_id = stage1_data.get("model")
                        if model_id not in seen:
                            seen.add(model_id)
                            responses.append(stage1_data)
                elif event_type == "stage2_start":
                    run_info["stage"] = "stage2"
                    run_info["progress"]["stage2"] = {"total": 0}
                elif event_type == "stage2_init":
                    run_info["progress"]["stage2"]["total"] = event.get("total", 0)
                elif event_type in ["stage2_complete", "stage2_progress"]:
                    stage2_data = event.get("data")
                    if isinstance(stage2_data, list):
                        run_info["stage2_responses"] = stage2_data
                    elif isinstance(stage2_data, dict):
                        responses = run_info.setdefault("stage2_responses", [])
                        seen = run_info.setdefault("_seen_stage2", set())
                        model_id = stage2_data.get("model")
                        if model_id not in seen:
                            seen.add(model_id)
                            responses.append(stage2_data)
                elif event_type == "stage3_start":
                    run_info["stage"] = "stage3"
                elif event_type == "stage3_complete":
                    run_info["stage3_response"] = event.get("data")
                elif event_type == "stage4_start":
                    run_info["stage"] = "stage4"
                elif event_type == "stage4_complete":
                    run_info["stage4_response"] = event.get("data")

                if event_type == "debate_complete":
                    rounds_data = event.get("rounds", [])
                    cost_report = event.get("cost_report") or build_iterative_debate_cost_report(rounds_data, event.get("stage4"))
                    debate_converged = event.get("converged", False)
                    debate_critique_mode = event.get("critique_mode", "freeform")
                    if rounds_data:
                        last = rounds_data[-1]
                        final_stage1 = last.get("stage1", [])
                        final_stage2 = last.get("stage2") or []
                        final_stage3 = last.get("stage3")
                        last_meta = last.get("metadata", {})
                        final_label_to_model = last_meta.get("label_to_model", {})
                        final_aggregate_rankings = last_meta.get("aggregate_rankings", [])
                        final_canonical_claims = last_meta.get("canonical_claims")
                        final_aggregate_claim_verdicts = last_meta.get("aggregate_claim_verdicts")
                    final_stage4 = event.get("stage4")

            if title_task:
                try:
                    title = await title_task
                    storage.update_conversation_title(conversation_id, title)
                    conversation["title"] = title
                    yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"
                except Exception as e:
                    print(f"Error waiting for title task: {e}")

            # Save assistant message with metadata
            metadata = {
                "execution_mode": body.execution_mode,
                "critique_mode": debate_critique_mode,
                "debate_rounds_configured": effective_rounds,
                "debate_rounds_executed": len(rounds_data),
                "converged": debate_converged,
                "rounds": rounds_data,
                "cost_report": cost_report or build_iterative_debate_cost_report(rounds_data, final_stage4),
            }
            if body.execution_mode in ["chat_ranking", "full"]:
                metadata["label_to_model"] = final_label_to_model
                metadata["aggregate_rankings"] = final_aggregate_rankings
            if final_canonical_claims:
                metadata["canonical_claims"] = final_canonical_claims
            if final_aggregate_claim_verdicts:
                metadata["aggregate_claim_verdicts"] = final_aggregate_claim_verdicts
            if final_stage4:
                metadata["stage4"] = final_stage4
            if search_context:
                metadata["search_context"] = search_context
            if search_query:
                metadata["search_query"] = search_query

            storage.add_assistant_message(
                conversation_id,
                final_stage1,
                final_stage2 if body.execution_mode in ["chat_ranking", "full"] else None,
                final_stage3 if body.execution_mode == "full" else None,
                metadata,
                conversation=conversation
            )

            yield f"data: {json.dumps({'type': 'complete', 'metadata': {'cost_report': metadata['cost_report']}})}\n\n"

        except asyncio.CancelledError:
            print(f"Stream cancelled for conversation {conversation_id}")
            if final_stage1:
                try:
                    _save_partial_results(
                        conversation_id, body, final_stage1, final_stage2,
                        final_stage3, conversation,
                        label_to_model=final_label_to_model,
                        extra_metadata={
                            "rounds": rounds_data,
                            "cost_report": build_iterative_debate_cost_report(rounds_data, final_stage4),
                        },
                    )
                    print(f"Saved partial debate results: {len(rounds_data)} rounds")
                except Exception as save_err:
                    print(f"Could not save partial debate results: {save_err}")
            if title_task:
                try:
                    title = await asyncio.wait_for(title_task, timeout=2.0)
                    storage.update_conversation_title(conversation_id, title)
                except Exception as e:
                    print(f"Could not save title during cancellation: {e}")
            raise
        except Exception as e:
            print(f"Stream error: {e}")
            storage.add_error_message(conversation_id, f"Error: {str(e)}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            _active_runs.pop(conversation_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/api/personas")
async def list_personas():
    """List all available advisor personas (with user overrides applied)."""
    return [p.model_dump() for p in get_all_personas()]


class PersonaOverrideRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    avatar_emoji: Optional[str] = None


@app.patch("/api/personas/{persona_id}")
async def update_persona(persona_id: str, body: PersonaOverrideRequest):
    """Save user overrides for a persona."""
    if not get_persona(persona_id):
        raise HTTPException(status_code=404, detail="Persona not found")
    updated = save_persona_override(persona_id, body.model_dump(exclude_none=True))
    return updated.model_dump()


@app.delete("/api/personas/{persona_id}/override")
async def reset_persona(persona_id: str):
    """Remove user overrides and restore persona defaults."""
    if not get_persona(persona_id):
        raise HTTPException(status_code=404, detail="Persona not found")
    restored = delete_persona_override(persona_id)
    return restored.model_dump()


@app.post("/api/conversations/{conversation_id}/debate/stream")
async def start_debate_stream(conversation_id: str, body: StartDebateRequest, request: Request):
    """Start an advisor debate and stream results via SSE."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if len(body.persona_ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 advisors required")
    if len(body.persona_ids) > 4:
        raise HTTPException(status_code=400, detail="Maximum 4 advisors allowed")
    if body.max_rounds < 3 or body.max_rounds > 10:
        raise HTTPException(status_code=400, detail="Rounds must be between 3 and 10")

    is_first_message = len(conversation["messages"]) == 0

    async def event_generator():
        try:
            storage.add_user_message(conversation_id, body.question, conversation=conversation)

            search_context = ""
            if body.search_provider or body.web_search:
                settings = get_settings()
                yield f"data: {json.dumps({'type': 'advisor_search_start'})}\n\n"
                search_context, search_query, _ = await _fetch_search_context(body.question, settings, body.search_provider)
                yield f"data: {json.dumps({'type': 'advisor_search_complete', 'data': {'search_query': search_query}})}\n\n"

            all_rounds = []
            verdict_data = None
            tiebreaker_data = None
            saved_personas = []
            cost_report = None

            web_search_used = bool(body.search_provider or body.web_search)
            async for event in run_debate(
                question=body.question,
                persona_ids=body.persona_ids,
                model_assignments=body.model_assignments,
                default_model=body.default_model,
                tiebreaker_model=body.tiebreaker_model,
                max_rounds=body.max_rounds,
                web_search=web_search_used,
                search_context=search_context,
                request=request,
                preflight=True,
            ):
                event_type = event.get("type", "")

                if event_type == "advisor_complete":
                    all_rounds = event["data"]["rounds"]
                    verdict_data = event["data"]["verdict"]
                    tiebreaker_data = event["data"].get("tiebreaker")
                    saved_personas = event["data"].get("personas", [])
                    cost_report = event["data"].get("cost_report")

                if event_type == "advisor_error":
                    message = event.get("message", "Advisor debate failed")
                    storage.add_error_message(conversation_id, message)
                    yield f"data: {json.dumps(event)}\n\n"
                    return

                yield f"data: {json.dumps(event)}\n\n"

            metadata = {
                "persona_ids": body.persona_ids,
                "default_model": body.default_model,
                "tiebreaker_model": body.tiebreaker_model,
                "model_assignments": body.model_assignments,
                "max_rounds": body.max_rounds,
                "web_search": web_search_used,
                "cost_report": cost_report or build_advisor_cost_report(all_rounds, verdict_data, tiebreaker_data),
            }
            if search_context:
                metadata["search_context"] = search_context

            storage.add_advisor_message(
                conversation_id,
                rounds=all_rounds,
                verdict=verdict_data,
                tiebreaker=tiebreaker_data,
                personas=saved_personas,
                metadata=metadata,
                conversation=conversation,
            )

            if is_first_message:
                title = await generate_conversation_title(body.question)
                storage.update_conversation_title(conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

        except asyncio.CancelledError:
            if is_first_message:
                try:
                    title = await generate_conversation_title(body.question)
                    storage.update_conversation_title(conversation_id, title)
                except Exception:
                    pass
            raise
        except Exception as e:
            logger.error(f"Debate stream error: {e}")
            storage.add_error_message(conversation_id, f"Debate error: {str(e)}")
            yield f"data: {json.dumps({'type': 'advisor_error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.post("/api/conversations/{conversation_id}/message")
async def send_message_sync(conversation_id: str, body: SendMessageRequest):
    """Send a message and return JSON response (non-streaming)."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    history = _build_chat_history(conversation)

    preflight_error = await _run_model_preflight(_build_council_preflight_models(body))
    if preflight_error:
        raise HTTPException(status_code=400, detail=preflight_error)

    storage.add_user_message(conversation_id, body.content, conversation=conversation)

    search_context = ""
    search_query = ""
    if body.web_search:
        settings = get_settings()
        search_context, search_query, _ = await _fetch_search_context(body.content, settings)

    result = await _run_council_pipeline(
        body.content, body.execution_mode, search_context,
        models_override=body.council_models, chairman_override=body.chairman_model,
        history=history,
        preflight=False,
    )

    metadata = {"execution_mode": body.execution_mode, "cost_report": result.cost_report}
    if body.execution_mode in ("chat_ranking", "full"):
        metadata["label_to_model"] = result.label_to_model
        metadata["aggregate_rankings"] = result.aggregate_rankings
    if search_context:
        metadata["search_context"] = search_context
    if search_query:
        metadata["search_query"] = search_query

    storage.add_assistant_message(
        conversation_id,
        result.stage1,
        result.stage2 if body.execution_mode in ("chat_ranking", "full") else None,
        result.stage3 if body.execution_mode == "full" else None,
        metadata,
        conversation=conversation
    )

    return {
        "stage1": result.stage1,
        "stage2": result.stage2 if result.stage2 else None,
        "stage3": result.stage3,
        "aggregate_rankings": result.aggregate_rankings if result.aggregate_rankings else None,
        "label_to_model": result.label_to_model if result.label_to_model else None,
        "cost_report": result.cost_report,
    }


@app.post("/api/ask")
async def ask_oneshot(body: AskRequest):
    """One-shot query: no conversation, no state. Returns JSON directly."""
    settings = get_settings()
    models = body.models if body.models else settings.council_models

    if not models:
        raise HTTPException(status_code=400, detail="At least one model is required")

    preflight_body = SendMessageRequest(
        content=body.content,
        execution_mode=body.execution_mode,
        council_models=models,
        chairman_model=body.chairman_model,
    )
    preflight_error = await _run_model_preflight(_build_council_preflight_models(preflight_body))
    if preflight_error:
        raise HTTPException(status_code=400, detail=preflight_error)

    search_context = ""
    if body.web_search:
        search_context, _, _ = await _fetch_search_context(body.content, settings)

    result = await _run_council_pipeline(
        body.content, body.execution_mode, search_context,
        models_override=models, chairman_override=body.chairman_model,
        preflight=False,
    )

    if body.execution_mode == "chat_only" and len(result.stage1) == 1:
        r = result.stage1[0]
        return {
            "response": r.get("response"),
            "model": r.get("model"),
            "error": r.get("error"),
            "usage": r.get("usage"),
            "cost": r.get("cost"),
            "cost_report": result.cost_report,
        }

    if body.execution_mode == "chat_only":
        return {"responses": result.stage1, "cost_report": result.cost_report}

    if body.execution_mode == "chat_ranking":
        return {
            "responses": result.stage1,
            "rankings": result.stage2,
            "aggregate_rankings": result.aggregate_rankings,
            "label_to_model": result.label_to_model,
            "cost_report": result.cost_report,
        }

    return {
        "response": result.stage3.get("response") if result.stage3 else None,
        "chairman_model": result.stage3.get("model") if result.stage3 else None,
        "responses": result.stage1,
        "rankings": result.stage2,
        "aggregate_rankings": result.aggregate_rankings,
        "label_to_model": result.label_to_model,
        "cost_report": result.cost_report,
    }


class UpdateSettingsRequest(BaseModel):
    """Request to update settings."""
    search_provider: Optional[str] = None
    search_keyword_extraction: Optional[str] = None
    ollama_base_url: Optional[str] = None
    full_content_results: Optional[int] = None

    # Custom OpenAI-compatible endpoint
    custom_endpoint_name: Optional[str] = None
    custom_endpoint_url: Optional[str] = None
    custom_endpoint_api_key: Optional[str] = None

    # API Keys
    serper_api_key: Optional[str] = None
    tavily_api_key: Optional[str] = None
    brave_api_key: Optional[str] = None
    tinyfish_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    nvidia_api_key: Optional[str] = None
    opencode_api_key: Optional[str] = None

    # Enabled Providers
    enabled_providers: Optional[Dict[str, bool]] = None
    direct_provider_toggles: Optional[Dict[str, bool]] = None

    # Council Configuration (unified)
    council_models: Optional[List[str]] = None
    chairman_model: Optional[str] = None
    
    # Remote/Local filters
    council_member_filters: Optional[Dict[int, str]] = None
    chairman_filter: Optional[str] = None
    search_query_filter: Optional[str] = None

    # Temperature Settings
    council_temperature: Optional[float] = None
    chairman_temperature: Optional[float] = None
    stage2_temperature: Optional[float] = None

    # Execution Mode
    execution_mode: Optional[str] = None

    # Iterative Debate
    critique_mode: Optional[str] = None
    debate_rounds: Optional[int] = None
    auto_converge: Optional[bool] = None
    convergence_threshold: Optional[int] = None

    # System Prompts
    stage1_prompt: Optional[str] = None
    stage2_prompt: Optional[str] = None
    stage3_prompt: Optional[str] = None
    stage4_prompt: Optional[str] = None
    title_prompt: Optional[str] = None
    query_prompt: Optional[str] = None

    # Advisor Settings
    advisor_default_model: Optional[str] = None
    advisor_tiebreaker_model: Optional[str] = None
    advisor_temperature: Optional[float] = None
    advisor_default_rounds: Optional[int] = None
    advisor_round1_prompt: Optional[str] = None
    advisor_followup_prompt: Optional[str] = None
    advisor_cross_pollination_prompt: Optional[str] = None
    advisor_verdict_prompt: Optional[str] = None
    advisor_tiebreaker_prompt: Optional[str] = None
    advisor_presets: Optional[List[Dict[str, Any]]] = None
    council_presets: Optional[List[Dict[str, Any]]] = None



class TestTavilyRequest(BaseModel):
    """Request to test Tavily API key."""
    api_key: str | None = None


@app.get("/api/settings")
async def get_app_settings():
    """Get current application settings."""
    settings = get_settings()
    return {
        "search_provider": settings.search_provider,
        "search_keyword_extraction": settings.search_keyword_extraction,
        "ollama_base_url": settings.ollama_base_url,
        "full_content_results": settings.full_content_results,

        # Custom Endpoint
        "custom_endpoint_name": settings.custom_endpoint_name,
        "custom_endpoint_url": settings.custom_endpoint_url,
        # Don't send the API key to frontend for security

        # API Key Status
        "serper_api_key_set": bool(settings.serper_api_key),
        "tavily_api_key_set": bool(settings.tavily_api_key),
        "brave_api_key_set": bool(settings.brave_api_key),
        "tinyfish_api_key_set": bool(settings.tinyfish_api_key),
        "openrouter_api_key_set": bool(settings.openrouter_api_key),
        "openai_api_key_set": bool(settings.openai_api_key),
        "anthropic_api_key_set": bool(settings.anthropic_api_key),
        "google_api_key_set": bool(settings.google_api_key),
        "mistral_api_key_set": bool(settings.mistral_api_key),
        "deepseek_api_key_set": bool(settings.deepseek_api_key),
        "groq_api_key_set": bool(settings.groq_api_key),
        "nvidia_api_key_set": bool(settings.nvidia_api_key),
        "opencode_api_key_set": bool(settings.opencode_api_key),
        "custom_endpoint_api_key_set": bool(settings.custom_endpoint_api_key),

        # Enabled Providers
        "enabled_providers": settings.enabled_providers,
        "direct_provider_toggles": settings.direct_provider_toggles,

        # Council Configuration (unified)
        "council_models": settings.council_models,
        "chairman_model": settings.chairman_model,

        # Remote/Local filters
        "council_member_filters": settings.council_member_filters,
        "chairman_filter": settings.chairman_filter,
        "search_query_filter": settings.search_query_filter,

        # Temperature Settings
        "council_temperature": settings.council_temperature,
        "chairman_temperature": settings.chairman_temperature,
        "stage2_temperature": settings.stage2_temperature,

        # Prompts
        "stage1_prompt": settings.stage1_prompt,
        "stage2_prompt": settings.stage2_prompt,
        "stage3_prompt": settings.stage3_prompt,
        "stage4_prompt": settings.stage4_prompt,
        "title_prompt": settings.title_prompt,
        "query_prompt": settings.query_prompt,

        # Advisor Settings
        "advisor_default_model": settings.advisor_default_model,
        "advisor_tiebreaker_model": settings.advisor_tiebreaker_model,
        "advisor_temperature": settings.advisor_temperature,
        "advisor_default_rounds": settings.advisor_default_rounds,
        "advisor_round1_prompt": settings.advisor_round1_prompt,
        "advisor_followup_prompt": settings.advisor_followup_prompt,
        "advisor_cross_pollination_prompt": settings.advisor_cross_pollination_prompt,
        "advisor_verdict_prompt": settings.advisor_verdict_prompt,
        "advisor_tiebreaker_prompt": settings.advisor_tiebreaker_prompt,
        "advisor_presets": [p.model_dump() if hasattr(p, "model_dump") else p for p in settings.advisor_presets],
        "council_presets": [p.model_dump() if hasattr(p, "model_dump") else p for p in settings.council_presets],

        # Iterative Debate
        "critique_mode": settings.critique_mode,
        "debate_rounds": settings.debate_rounds,
        "auto_converge": settings.auto_converge,
        "convergence_threshold": settings.convergence_threshold,
    }



@app.get("/api/settings/defaults")
async def get_default_settings():
    """Get default model settings."""
    from .settings import DEFAULT_ENABLED_PROVIDERS
    return {
        "council_models": DEFAULT_COUNCIL_MODELS,
        "chairman_model": DEFAULT_CHAIRMAN_MODEL,
        "enabled_providers": DEFAULT_ENABLED_PROVIDERS,
        **PROMPT_DEFAULTS,
    }


@app.get("/api/settings/export", dependencies=[Depends(_require_admin)])
async def export_settings():
    """Export complete settings as a downloadable JSON file (includes actual API key values).

    Admin-only — see _require_admin. Without auth, returning plaintext keys to any
    network peer would be a credential disclosure.
    """
    settings = get_settings()
    content = settings.model_dump_json(indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=council-settings.json"},
    )


@app.post("/api/settings/import", dependencies=[Depends(_require_admin)])
async def import_settings(new_settings: Settings):
    """Import settings from a full settings JSON blob (admin-only)."""
    save_settings(new_settings)
    return {"status": "imported", "message": "Settings imported successfully"}


@app.post("/api/settings/reset", dependencies=[Depends(_require_admin)])
async def reset_settings():
    """Reset all settings to defaults (admin-only)."""
    save_settings(Settings())
    return {"status": "reset", "message": "Settings reset to defaults"}


@app.put("/api/settings")
async def update_app_settings(request: UpdateSettingsRequest):
    """Update application settings."""
    updates = {}

    if request.search_provider is not None:
        # Validate provider
        try:
            provider = SearchProvider(request.search_provider)
            updates["search_provider"] = provider
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid search provider. Must be one of: {[p.value for p in SearchProvider]}"
            )

    if request.search_keyword_extraction is not None:
        if request.search_keyword_extraction not in ["direct", "yake", "llm"]:
             raise HTTPException(
                status_code=400,
                detail="Invalid keyword extraction mode. Must be 'direct', 'yake', or 'llm'"
            )
        updates["search_keyword_extraction"] = request.search_keyword_extraction

    if request.ollama_base_url is not None:
        updates["ollama_base_url"] = request.ollama_base_url

    # Custom endpoint
    if request.custom_endpoint_name is not None:
        updates["custom_endpoint_name"] = request.custom_endpoint_name
    if request.custom_endpoint_url is not None:
        updates["custom_endpoint_url"] = request.custom_endpoint_url
    if request.custom_endpoint_api_key is not None:
        updates["custom_endpoint_api_key"] = request.custom_endpoint_api_key

    if request.full_content_results is not None:
        # Validate range
        if request.full_content_results < 0 or request.full_content_results > 10:
            raise HTTPException(
                status_code=400,
                detail="full_content_results must be between 0 and 10"
            )
        updates["full_content_results"] = request.full_content_results

    # Prompt updates
    if request.stage1_prompt is not None:
        updates["stage1_prompt"] = request.stage1_prompt
    if request.stage2_prompt is not None:
        updates["stage2_prompt"] = request.stage2_prompt
    if request.stage3_prompt is not None:
        updates["stage3_prompt"] = request.stage3_prompt
    if request.stage4_prompt is not None:
        updates["stage4_prompt"] = request.stage4_prompt
    if request.title_prompt is not None:
        updates["title_prompt"] = request.title_prompt
    if request.query_prompt is not None:
        updates["query_prompt"] = request.query_prompt

    if request.serper_api_key is not None:
        updates["serper_api_key"] = request.serper_api_key
        # Also set in environment for immediate use
        if request.serper_api_key:
            os.environ["SERPER_API_KEY"] = request.serper_api_key

    if request.tavily_api_key is not None:
        updates["tavily_api_key"] = request.tavily_api_key
        # Also set in environment for immediate use
        if request.tavily_api_key:
            os.environ["TAVILY_API_KEY"] = request.tavily_api_key

    if request.brave_api_key is not None:
        updates["brave_api_key"] = request.brave_api_key
        # Also set in environment for immediate use
        if request.brave_api_key:
            os.environ["BRAVE_API_KEY"] = request.brave_api_key

    if request.tinyfish_api_key is not None:
        updates["tinyfish_api_key"] = request.tinyfish_api_key
        if request.tinyfish_api_key:
            os.environ["TINYFISH_API_KEY"] = request.tinyfish_api_key

    if request.openrouter_api_key is not None:
        updates["openrouter_api_key"] = request.openrouter_api_key
        
    # Direct Provider Keys
    if request.openai_api_key is not None:
        updates["openai_api_key"] = request.openai_api_key
    if request.anthropic_api_key is not None:
        updates["anthropic_api_key"] = request.anthropic_api_key
    if request.google_api_key is not None:
        updates["google_api_key"] = request.google_api_key
    if request.mistral_api_key is not None:
        updates["mistral_api_key"] = request.mistral_api_key
    if request.deepseek_api_key is not None:
        updates["deepseek_api_key"] = request.deepseek_api_key
    if request.groq_api_key is not None:
        updates["groq_api_key"] = request.groq_api_key
    if request.nvidia_api_key is not None:
        updates["nvidia_api_key"] = request.nvidia_api_key
    if request.opencode_api_key is not None:
        updates["opencode_api_key"] = request.opencode_api_key

    # Enabled Providers
    if request.enabled_providers is not None:
        updates["enabled_providers"] = request.enabled_providers

    if request.direct_provider_toggles is not None:
        updates["direct_provider_toggles"] = request.direct_provider_toggles

    # Council Configuration (unified)
    if request.council_models is not None:
        if len(request.council_models) < 1:
            raise HTTPException(
                status_code=400,
                detail="At least one council model must be selected"
            )
        if len(request.council_models) > 8:
            raise HTTPException(
                status_code=400,
                detail="Maximum of 8 council models allowed"
            )
        updates["council_models"] = request.council_models

    if request.chairman_model is not None:
        updates["chairman_model"] = request.chairman_model
        
    # Remote/Local filters
    if request.council_member_filters is not None:
        updates["council_member_filters"] = request.council_member_filters
    if request.chairman_filter is not None:
        updates["chairman_filter"] = request.chairman_filter
    if request.search_query_filter is not None:
        updates["search_query_filter"] = request.search_query_filter

    # Temperature Settings
    if request.council_temperature is not None:
        updates["council_temperature"] = request.council_temperature
    if request.chairman_temperature is not None:
        updates["chairman_temperature"] = request.chairman_temperature
    if request.stage2_temperature is not None:
        updates["stage2_temperature"] = request.stage2_temperature

    if request.execution_mode is not None:
        _validate_execution_mode(request.execution_mode)
        updates["execution_mode"] = request.execution_mode

    if request.critique_mode is not None:
        if request.critique_mode not in ("freeform", "paragraph", "claim"):
            raise HTTPException(status_code=400, detail="critique_mode must be freeform, paragraph, or claim")
        updates["critique_mode"] = request.critique_mode
    if request.debate_rounds is not None:
        if not (1 <= request.debate_rounds <= MAX_DEBATE_ROUNDS):
            raise HTTPException(status_code=400, detail=f"debate_rounds must be 1-{MAX_DEBATE_ROUNDS}")
        updates["debate_rounds"] = request.debate_rounds
    if request.auto_converge is not None:
        updates["auto_converge"] = request.auto_converge
    if request.convergence_threshold is not None:
        if not (1 <= request.convergence_threshold <= 5):
            raise HTTPException(status_code=400, detail="convergence_threshold must be 1-5")
        updates["convergence_threshold"] = request.convergence_threshold

    if request.advisor_default_model is not None:
        updates["advisor_default_model"] = request.advisor_default_model
    if request.advisor_tiebreaker_model is not None:
        updates["advisor_tiebreaker_model"] = request.advisor_tiebreaker_model
    if request.advisor_temperature is not None:
        updates["advisor_temperature"] = request.advisor_temperature
    if request.advisor_default_rounds is not None:
        updates["advisor_default_rounds"] = max(3, min(10, request.advisor_default_rounds))
    if request.advisor_round1_prompt is not None:
        updates["advisor_round1_prompt"] = request.advisor_round1_prompt
    if request.advisor_followup_prompt is not None:
        updates["advisor_followup_prompt"] = request.advisor_followup_prompt
    if request.advisor_cross_pollination_prompt is not None:
        updates["advisor_cross_pollination_prompt"] = request.advisor_cross_pollination_prompt
    if request.advisor_verdict_prompt is not None:
        updates["advisor_verdict_prompt"] = request.advisor_verdict_prompt
    if request.advisor_tiebreaker_prompt is not None:
        updates["advisor_tiebreaker_prompt"] = request.advisor_tiebreaker_prompt
    if request.advisor_presets is not None:
        from .settings import _normalize_advisor_presets
        updates["advisor_presets"] = _normalize_advisor_presets(request.advisor_presets)
    if request.council_presets is not None:
        from .settings import _normalize_council_presets
        updates["council_presets"] = _normalize_council_presets(request.council_presets)

    if updates:
        settings = update_settings(**updates)
    else:
        settings = get_settings()

    return {
        "search_provider": settings.search_provider,
        "search_keyword_extraction": settings.search_keyword_extraction,
        "ollama_base_url": settings.ollama_base_url,
        "full_content_results": settings.full_content_results,

        # Custom Endpoint
        "custom_endpoint_name": settings.custom_endpoint_name,
        "custom_endpoint_url": settings.custom_endpoint_url,

        # API Key Status
        "serper_api_key_set": bool(settings.serper_api_key),
        "tavily_api_key_set": bool(settings.tavily_api_key),
        "brave_api_key_set": bool(settings.brave_api_key),
        "tinyfish_api_key_set": bool(settings.tinyfish_api_key),
        "openrouter_api_key_set": bool(settings.openrouter_api_key),
        "openai_api_key_set": bool(settings.openai_api_key),
        "anthropic_api_key_set": bool(settings.anthropic_api_key),
        "google_api_key_set": bool(settings.google_api_key),
        "mistral_api_key_set": bool(settings.mistral_api_key),
        "deepseek_api_key_set": bool(settings.deepseek_api_key),
        "groq_api_key_set": bool(settings.groq_api_key),
        "nvidia_api_key_set": bool(settings.nvidia_api_key),
        "opencode_api_key_set": bool(settings.opencode_api_key),
        "custom_endpoint_api_key_set": bool(settings.custom_endpoint_api_key),

        # Enabled Providers
        "enabled_providers": settings.enabled_providers,
        "direct_provider_toggles": settings.direct_provider_toggles,

        # Council Configuration (unified)
        "council_models": settings.council_models,
        "chairman_model": settings.chairman_model,

        # Remote/Local filters
        "council_member_filters": settings.council_member_filters,
        "chairman_filter": settings.chairman_filter,

        # Prompts
        "stage1_prompt": settings.stage1_prompt,
        "stage2_prompt": settings.stage2_prompt,
        "stage3_prompt": settings.stage3_prompt,
        "stage4_prompt": settings.stage4_prompt,
        "title_prompt": settings.title_prompt,
        "query_prompt": settings.query_prompt,

        # Advisor Settings
        "advisor_default_model": settings.advisor_default_model,
        "advisor_tiebreaker_model": settings.advisor_tiebreaker_model,
        "advisor_temperature": settings.advisor_temperature,
        "advisor_default_rounds": settings.advisor_default_rounds,
        "advisor_round1_prompt": settings.advisor_round1_prompt,
        "advisor_followup_prompt": settings.advisor_followup_prompt,
        "advisor_cross_pollination_prompt": settings.advisor_cross_pollination_prompt,
        "advisor_verdict_prompt": settings.advisor_verdict_prompt,
        "advisor_tiebreaker_prompt": settings.advisor_tiebreaker_prompt,
        "advisor_presets": [p.model_dump() if hasattr(p, "model_dump") else p for p in settings.advisor_presets],
        "council_presets": [p.model_dump() if hasattr(p, "model_dump") else p for p in settings.council_presets],

        # Iterative Debate
        "critique_mode": settings.critique_mode,
        "debate_rounds": settings.debate_rounds,
        "auto_converge": settings.auto_converge,
        "convergence_threshold": settings.convergence_threshold,
    }


@app.get("/api/models/direct")
async def get_direct_models():
    """Get available models from all configured direct providers."""
    all_models = []
    
    # Iterate over all providers
    for provider_id, provider in PROVIDERS.items():
        # Skip OpenRouter and Ollama as they are handled separately
        if provider_id in ["openrouter", "ollama", "hybrid"]:
            continue
            
        try:
            # Fetch models from provider
            models = await provider.get_models()
            all_models.extend(models)
        except Exception as e:
            print(f"Error fetching models for {provider_id}: {e}")
            
    return all_models


@app.post("/api/settings/test-tavily")
async def test_tavily_api(request: TestTavilyRequest):
    """Test Tavily API key with a simple search."""
    import httpx
    settings = get_settings()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": request.api_key or settings.tavily_api_key,
                    "query": "test",
                    "max_results": 1,
                    "search_depth": "basic",
                },
            )

            if response.status_code == 200:
                return {"success": True, "message": "API key is valid"}
            elif response.status_code == 401:
                return {"success": False, "message": "Invalid API key"}
            else:
                return {"success": False, "message": f"API error: {response.status_code}"}

    except httpx.TimeoutException:
        return {"success": False, "message": "Request timed out"}
    except Exception as e:
        return {"success": False, "message": str(e)}


class TestBraveRequest(BaseModel):
    """Request to test Brave API key."""
    api_key: str | None = None


@app.post("/api/settings/test-brave")
async def test_brave_api(request: TestBraveRequest):
    """Test Brave API key with a simple search."""
    import httpx
    settings = get_settings()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": "test", "count": 1},
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": request.api_key or settings.brave_api_key,
                },
            )

            if response.status_code == 200:
                return {"success": True, "message": "API key is valid"}
            elif response.status_code == 401 or response.status_code == 403:
                return {"success": False, "message": "Invalid API key"}
            else:
                return {"success": False, "message": f"API error: {response.status_code}"}

    except httpx.TimeoutException:
        return {"success": False, "message": "Request timed out"}
    except Exception as e:
        return {"success": False, "message": str(e)}


class TestSerperRequest(BaseModel):
    """Request to test Serper API key."""
    api_key: str | None = None


@app.post("/api/settings/test-serper")
async def test_serper_api(request: TestSerperRequest):
    """Test Serper API key with a simple search."""
    import httpx
    settings = get_settings()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://google.serper.dev/search",
                json={"q": "test", "num": 1},
                headers={
                    "X-API-KEY": request.api_key or settings.serper_api_key,
                    "Content-Type": "application/json",
                },
            )

            if response.status_code == 200:
                return {"success": True, "message": "API key is valid"}
            elif response.status_code == 401 or response.status_code == 403:
                return {"success": False, "message": "Invalid API key"}
            else:
                return {"success": False, "message": f"API error: {response.status_code}"}

    except httpx.TimeoutException:
        return {"success": False, "message": "Request timed out"}
    except Exception as e:
        return {"success": False, "message": str(e)}


class TestTinyfishRequest(BaseModel):
    """Request to test TinyFish API key."""
    api_key: str | None = None


@app.post("/api/settings/test-tinyfish")
async def test_tinyfish_api(request: TestTinyfishRequest):
    """Test TinyFish API key with a simple search."""
    import httpx
    settings = get_settings()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://api.search.tinyfish.ai/",
                params={"query": "test"},
                headers={"X-API-Key": request.api_key or settings.tinyfish_api_key},
            )

            if response.status_code == 200:
                return {"success": True, "message": "API key is valid"}
            elif response.status_code == 401 or response.status_code == 403:
                return {"success": False, "message": "Invalid API key"}
            else:
                return {"success": False, "message": f"API error: {response.status_code}"}

    except httpx.TimeoutException:
        return {"success": False, "message": "Request timed out"}
    except Exception as e:
        return {"success": False, "message": str(e)}


class TestOpenRouterRequest(BaseModel):
    """Request to test OpenRouter API key."""
    api_key: Optional[str] = None


class TestProviderRequest(BaseModel):
    """Request to test a specific provider's API key."""
    provider_id: str
    api_key: str


@app.post("/api/settings/test-provider")
async def test_provider_api(request: TestProviderRequest):
    """Test an API key for a specific provider."""
    from .council import PROVIDERS
    from .settings import get_settings
    
    if request.provider_id not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Invalid provider ID")

    api_key = request.api_key
    if not api_key:
        # Try to get from settings
        settings = get_settings()
        # Provider-id → settings-key map. Falls back to "<id>_api_key".
        _PROVIDER_SETTINGS_KEY_OVERRIDES = {
            "opencode-zen": "opencode_api_key",
            "opencode-go": "opencode_api_key",
        }
        setting_key = _PROVIDER_SETTINGS_KEY_OVERRIDES.get(
            request.provider_id, f"{request.provider_id}_api_key"
        )
        if hasattr(settings, setting_key):
             api_key = getattr(settings, setting_key)
    
    if not api_key:
         return {"success": False, "message": "No API key provided or configured"}

    provider = PROVIDERS[request.provider_id]
    return await provider.validate_key(api_key)


class TestOpenCodeRequest(BaseModel):
    """Request to test the OpenCode API key against Zen and/or Go."""
    api_key: Optional[str] = None
    product: Optional[str] = None  # "zen" | "go" | None (= test both)


@app.post("/api/settings/test-opencode")
async def test_opencode_key(request: TestOpenCodeRequest):
    """Test the OpenCode API key by listing models on Zen and/or Go."""
    from .providers.opencode import OpenCodeProvider

    api_key = request.api_key
    if not api_key:
        api_key = get_settings().opencode_api_key
    if not api_key:
        return {"success": False, "message": "No OpenCode API key provided or configured"}

    products = [request.product] if request.product in ("zen", "go") else ["zen", "go"]
    results: Dict[str, Any] = {}
    for product in products:
        provider = OpenCodeProvider(product=product)
        results[product] = await provider.validate_key(api_key)

    if request.product:
        return results[request.product]
    return {
        "success": any(r.get("success") for r in results.values()),
        "results": results,
    }


class TestOllamaRequest(BaseModel):
    """Request to test Ollama connection."""
    base_url: str


@app.get("/api/ollama/tags")
async def get_ollama_tags(base_url: Optional[str] = None):
    """Fetch available models from Ollama."""
    import httpx
    from .config import get_ollama_base_url
    
    if not base_url:
        base_url = get_ollama_base_url()
        
    if base_url.endswith('/'):
        base_url = base_url[:-1]
        
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{base_url}/api/tags")
            
            if response.status_code != 200:
                return {"models": [], "error": f"Ollama API error: {response.status_code}"}
                
            data = response.json()
            models = []
            for model in data.get("models", []):
                models.append({
                    "id": model.get("name"),
                    "name": model.get("name"),
                    # Ollama doesn't return context length in tags
                    "context_length": None,
                    "is_free": True,
                    "modified_at": model.get("modified_at")
                })
                
            # Sort by modified_at (newest first), fallback to name
            models.sort(key=lambda x: x.get("modified_at", ""), reverse=True)
            return {"models": models}
            
    except httpx.ConnectError:
        return {"models": [], "error": "Could not connect to Ollama. Is it running?"}
    except Exception as e:
        return {"models": [], "error": str(e)}


@app.post("/api/settings/test-ollama")
async def test_ollama_connection(request: TestOllamaRequest):
    """Test connection to Ollama instance."""
    import httpx
    
    base_url = request.base_url
    if base_url.endswith('/'):
        base_url = base_url[:-1]
        
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{base_url}/api/tags")
            
            if response.status_code == 200:
                return {"success": True, "message": "Successfully connected to Ollama"}
            else:
                return {"success": False, "message": f"Ollama API error: {response.status_code}"}
                
    except httpx.ConnectError:
        return {"success": False, "message": "Could not connect to Ollama. Is it running at this URL?"}
    except Exception as e:
        return {"success": False, "message": str(e)}


class TestCustomEndpointRequest(BaseModel):
    """Request to test custom OpenAI-compatible endpoint."""
    name: str
    url: str
    api_key: Optional[str] = None


@app.post("/api/settings/test-custom-endpoint")
async def test_custom_endpoint(request: TestCustomEndpointRequest):
    """Test connection to a custom OpenAI-compatible endpoint."""
    from .providers.custom_openai import CustomOpenAIProvider

    provider = CustomOpenAIProvider()
    return await provider.validate_connection(request.url, request.api_key or "")


@app.get("/api/custom-endpoint/models")
async def get_custom_endpoint_models():
    """Fetch available models from the custom endpoint."""
    from .providers.custom_openai import CustomOpenAIProvider
    from .settings import get_settings

    settings = get_settings()
    if not settings.custom_endpoint_url:
        return {"models": [], "error": "No custom endpoint configured"}

    provider = CustomOpenAIProvider()
    models = await provider.get_models()
    return {"models": models}


@app.get("/api/models")
async def get_openrouter_models():
    """Fetch available models from OpenRouter API."""
    import httpx
    from .config import get_openrouter_api_key

    api_key = get_openrouter_api_key()
    if not api_key:
        return {"models": [], "error": "No OpenRouter API key configured"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )

            if response.status_code != 200:
                return {"models": [], "error": f"API error: {response.status_code}"}

            data = response.json()
            models = []
            
            # Comprehensive exclusion list for non-text/chat models
            excluded_terms = [
                "embed", "audio", "whisper", "tts", "dall-e", "realtime", 
                "vision-only", "voxtral", "speech", "transcribe", "sora"
            ]

            for model in data.get("data", []):
                mid = model.get("id", "").lower()
                name_lower = model.get("name", "").lower()
                
                if any(term in mid for term in excluded_terms) or any(term in name_lower for term in excluded_terms):
                    continue

                # Extract pricing - free models have 0 cost
                pricing = model.get("pricing", {})
                prompt_price = float(pricing.get("prompt", "0") or "0")
                completion_price = float(pricing.get("completion", "0") or "0")
                is_free = prompt_price == 0 and completion_price == 0

                models.append({
                    "id": f"openrouter:{model.get('id')}",
                    "name": f"{model.get('name', model.get('id'))} [OpenRouter]",
                    "provider": "OpenRouter",
                    "context_length": model.get("context_length"),
                    "is_free": is_free,
                })

            # Sort by name
            models.sort(key=lambda x: x["name"].lower())
            return {"models": models}

    except httpx.TimeoutException:
        return {"models": [], "error": "Request timed out"}
    except Exception as e:
        return {"models": [], "error": str(e)}


@app.post("/api/settings/test-openrouter")
async def test_openrouter_api(request: TestOpenRouterRequest):
    """Test OpenRouter API key with a simple request."""
    import httpx
    from .config import get_openrouter_api_key

    # Use provided key or fall back to saved key
    api_key = request.api_key if request.api_key else get_openrouter_api_key()
    
    if not api_key:
        return {"success": False, "message": "No API key provided or configured"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={
                    "Authorization": f"Bearer {api_key}",
                },
            )

            if response.status_code == 200:
                return {"success": True, "message": "API key is valid"}
            elif response.status_code == 401:
                return {"success": False, "message": "Invalid API key"}
            else:
                return {"success": False, "message": f"API error: {response.status_code}"}

    except httpx.TimeoutException:
        return {"success": False, "message": "Request timed out"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ---------- MCP server (mounted on same port as REST API) ----------
try:
    from the_ai_counsel_mcp.server import create_server as _create_mcp_server
    _mcp = _create_mcp_server(base_url="http://127.0.0.1:8001")
    app.mount("/mcp", _mcp.sse_app())
    logger.info("MCP server mounted at /mcp (SSE at /mcp/sse, messages at /mcp/messages)")
except Exception:
    logger.warning("MCP server not available — the_ai_counsel_mcp package may not be installed", exc_info=True)


if os.path.isdir(FRONTEND_DIST_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    # Default to loopback for the local dev launcher. Set LLM_COUNCIL_BIND_HOST
    # to 0.0.0.0 explicitly when you intentionally want network exposure
    # (Docker CMD already passes --host 0.0.0.0).
    bind_host = os.getenv("LLM_COUNCIL_BIND_HOST", "127.0.0.1")
    bind_port = int(os.getenv("LLM_COUNCIL_BIND_PORT", "8001"))
    if bind_host not in _LOOPBACK_HOSTS and not _ADMIN_TOKEN:
        logger.warning(
            "Binding to %s without LLM_COUNCIL_ADMIN_TOKEN set: "
            "admin endpoints will reject non-loopback callers. "
            "Set LLM_COUNCIL_ADMIN_TOKEN to enable remote admin.",
            bind_host,
        )
    uvicorn.run(app, host=bind_host, port=bind_port)
