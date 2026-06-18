---
name: the-ai-counsel-api
version: 0.10.4
description: The AI Counsel — MCP-first (10 action-based tools) when The AI Counsel MCP server is connected; REST/curl fallback when MCP is unavailable, for cron scripts, or raw SSE. Triggers on "ask the council", "run a debate", "configure models", "run a deliberation", "check council health", etc.
---

# The AI Counsel — API & MCP Skill

## Overview

The AI Counsel has two operating modes:

- **Council mode** — 3-stage multi-LLM deliberation: individual responses → anonymous peer ranking → chairman synthesis
- **Advisor mode** — Named personas debate a question across configurable rounds, reaching consensus or delivering a structured verdict

Use **Council** for direct answers, creative prompts, factual questions, and "give me the best response" synthesis. Use **Advisor** only when the user wants named personas to debate a decision, tradeoff, risk review, prioritization, strategy, ethics, or genuine disagreement. Simple prompts can drift off-topic in Advisor mode because advisor prompts intentionally force positions, rebuttals, consensus scoring, and verdicts.

**Transport rule (read first):** If The AI Counsel **MCP tools are available** in your session, **call them** — do **not** shell out to `curl` for the same operation. This skill’s REST sections are the **fallback reference** when MCP is missing, the SSE session is stale, or you need raw SSE/admin export.

**MCP server (v0.10.0):** Built-in SSE at `http://localhost:8001/mcp/sse` (stdio: `python -m the_ai_counsel_mcp`). Exposes **10 action-based tools** (not 25). Verify via `GET /api/health` → `"mcp": {"tools": 10, "sse_url": "..."}`.

**Default base URL (REST fallback only):** `http://localhost:8001`  
**Remote server:** replace with `http://<server-ip>:8001`

---

## MCP-first routing

### When to use MCP (preferred)

Use MCP when your tool list includes any of these **10 tools** (server may appear as `the-ai-counsel`, `ai-counsel`, or `user-the-ai-counsel`):

| You want to… | MCP tool | Action(s) | Do **not** use curl |
|--------------|----------|-----------|---------------------|
| Check server / providers | `providers` | `health` | ~~`GET /api/health`~~ |
| Test an API key | `providers` | `test` | ~~`POST /api/settings/test-provider`~~ |
| List models | `providers` | `list_models` | ~~`GET /api/models`…~~ |
| Read council config (+ presets) | `council_settings` | `get` | ~~`GET /api/settings`~~ (council fields) |
| Update council members/chairman/mode | `council_settings` | `update` | ~~`PUT /api/settings`~~ (council fields) |
| Council preset CRUD | `council_settings` | `list_presets`, `save_preset`, `delete_preset`, `set_default_preset` | ~~`PUT /api/settings`~~ |
| Set search provider / API key | `providers` | `set_search`, `set_api_key` | ~~`PUT /api/settings`~~ |
| Backup / restore / reset config | `config_backup` | `export`, `import`, `reset` | ~~export/import/reset endpoints~~ |
| Full deliberation | `council_deliberate` | `full` | ~~`/api/ask` or message stream~~ |
| Stage 1 / 2 / 3 only | `council_deliberate` | `stage1`, `stage2`, `stage3` | ~~stage stream endpoints~~ |
| One-shot model chat | `model_chat` | `quick` | ~~`POST /api/ask`~~ |
| Multi-turn chat with a model | `model_chat` | `multi_turn` | ~~conversation message endpoints~~ |
| List / read conversations | `conversations` | `list`, `get` | ~~conversation GETs~~ |
| Check active run progress | `conversations` | `progress` | ~~`GET /api/conversations/{id}/progress`~~ |
| List / read / edit personas | `personas` | `list`, `get`, `update`, `reset` | ~~`/api/personas`~~ |
| Read advisor defaults (+ presets) | `advisor_settings` | `get` | ~~`GET /api/settings`~~ (advisor fields) |
| Update advisor defaults | `advisor_settings` | `update` | ~~`PUT /api/settings`~~ (advisor fields) |
| Advisor preset CRUD | `advisor_settings` | `list_presets`, `save_preset`, `delete_preset`, `set_default_preset` | ~~`PUT /api/settings`~~ |
| Run advisor debate | `advisor_debate` | _(direct params)_ | ~~`debate/stream`~~ |
| Run multi-round debate | `run_iterative_debate` | _(direct params)_ | ~~debate message endpoints~~ |

**Breaking change (v0.5.2):** Legacy 25-tool names (`run_deliberation`, `get_council_config`, `check_health`, etc.) were removed. Always use the 10 tools above with `action` parameters.

## MCP Tool Catalog (10 tools)

| Tool | Actions / usage |
|------|-----------------|
| `council_deliberate` | `stage1`, `stage2`, `stage3`, `full` |
| `model_chat` | `quick`, `multi_turn` |
| `advisor_debate` | Direct params: `question`, `persona_ids` (2–4), optional `max_rounds`, models |
| `run_iterative_debate` | Direct params: `query`, optional `debate_rounds` (1–5), `critique_mode` (`freeform`/`paragraph`/`claim`), `auto_converge` (bool), `convergence_threshold` (1–3), `web_search`, `models` |
| `council_settings` | `get`, `update` (members/chairman/temps/mode/prompts/provider toggles/**debate config**), `list_presets`, `save_preset`, `delete_preset`, `set_default_preset` |
| `advisor_settings` | Same preset actions + `get`, `update` |
| `personas` | `list`, `get`, `update`, `reset` |
| `conversations` | `list`, `get`, `progress` |
| `providers` | `list_models`, `health`, `test`, `set_api_key`, `set_search` |
| `config_backup` | `export`, `import`, `reset` |

In Claude Code, tools appear as `mcp__the-ai-counsel__<name>` (server identifier may vary). Full parameters: [`docs/mcp/TOOLS.md`](../../docs/mcp/TOOLS.md).

**Document inputs:** `council_deliberate`, `model_chat`, `advisor_debate`, and `run_iterative_debate` accept optional `documents`. Pass already extracted text as `{name, mime_type, text}` or source files as `{name, mime_type, data_base64}`. Base64 documents are extracted by the backend before model calls; providers receive normalized text context, not raw file bytes.

**Agent checklist before running curl:**

1. Are MCP tools for this server visible in my tool list?
2. Is there a row in the table above for this task?
3. If **yes** to both → **call the MCP tool**. Only use REST if the MCP call fails or the task is in “REST only” below.

### When to use REST (fallback)

| Scenario | Why REST, not MCP |
|----------|-------------------|
| **Cron / CI / non-MCP scripts** | No MCP transport |
| **MCP errors** (connection refused, stale SSE, tool not found) | Fallback per this skill |
| **Raw SSE event parsing** (custom UIs) | MCP deliberation tools return consolidated results, not per-event SSE |
| **Admin export with bearer token** | `GET /api/settings/export` — manual admin action |

See [`docs/mcp/TOOLS.md`](../../docs/mcp/TOOLS.md) for MCP parameters and [`docs/mcp/EXAMPLES.md`](../../docs/mcp/EXAMPLES.md) for walkthroughs.

---

## Quick Reference (REST fallback)

Use this table **only when MCP tools are unavailable** or the operation has no MCP equivalent (see routing above).

| Operation | Method | Endpoint |
|-----------|--------|----------|
| Health check | GET | `/api/health` (includes `"mcp": {"tools": 10}`) |
| **One-shot query (persisted, no prior history)** | **POST** | **`/api/ask`** |
| Get settings (council + advisor config) | GET | `/api/settings` |
| Update settings | PUT | `/api/settings` |
| List all models | GET | `/api/models` + `/api/models/direct` + `/api/ollama/tags` + `/api/custom-endpoint/models` |
| List conversations | GET | `/api/conversations` |
| Create conversation | POST | `/api/conversations` |
| Get conversation | GET | `/api/conversations/{id}` |
| **Get live run progress** | **GET** | **`/api/conversations/{id}/progress`** |
| Extract uploaded documents | POST | `/api/documents/extract` |
| Extract JSON/base64 documents | POST | `/api/documents/extract-json` |
| Send message (sync JSON) | POST | `/api/conversations/{id}/message` |
| Send message (SSE stream) | POST | `/api/conversations/{id}/message/stream` |
| **Run council debate (SSE stream)** | **POST** | **`/api/conversations/{id}/message/debate`** |
| **Run advisor debate (SSE stream)** | **POST** | **`/api/conversations/{id}/debate/stream`** |
| List all personas | GET | `/api/personas` |
| Update a persona | PATCH | `/api/personas/{id}` |
| Reset persona to defaults | DELETE | `/api/personas/{id}/override` |
| Test a provider | POST | `/api/settings/test-provider` |
| Export settings (backup) | GET | `/api/settings/export` |
| Import settings (restore) | POST | `/api/settings/import` |
| Reset settings to defaults | POST | `/api/settings/reset` |

**Model ID prefix format:**
```
openrouter:anthropic/claude-sonnet-4   → Cloud via OpenRouter
ollama:llama3.1:latest                 → Local Ollama
anthropic:claude-sonnet-4              → Direct Anthropic API
openai:gpt-4.1                         → Direct OpenAI API
custom:nvidia/nemotron-3-super-120b    → Custom endpoint
groq:llama3-70b-8192                   → Groq fast inference
opencode-zen:glm-5.1                   → Direct OpenCode Zen (chat/completions only, v1)
opencode-go:kimi-k2.5                  → Direct OpenCode Go (chat/completions only, v1; subscription)
```

**OpenCode note (v0.8.0):** The OpenCode provider only exposes models that route to `/v1/chat/completions`. GPT Responses, Anthropic Messages, and per-model Gemini are not supported in v1 and are filtered out of `/v1/models`. A single shared `opencode_api_key` field covers both products; Go users can also use Zen's free models. Use `POST /api/settings/test-opencode` to validate both products at once.

---

## Choosing the Right Endpoint

| Scenario | Endpoint | Why |
|----------|----------|-----|
| One-shot query, no history needed | `POST /api/ask` | Simplest path. One call; the completed run is saved and returns `conversation_id`. |
| One-shot query with web search | `POST /api/ask` with `web_search: true` | Same simplicity, adds search context. |
| Full deliberation, don't need live progress | `POST /api/ask` with `execution_mode: "full"` | Returns all stages in one JSON response. |
| Multi-turn conversation with follow-ups | `POST /api/conversations/{id}/message` | Models see full prior context. JSON response. |
| Multi-turn with live SSE progress | `POST /api/conversations/{id}/message/stream` | Real-time stage updates + multi-turn context. |
| **Persona-driven debate** | **`POST /api/conversations/{id}/debate/stream`** | Named advisors argue across rounds; returns verdict. |
| **Multi-round council debate** | **`POST /api/conversations/{id}/message/debate`** | Iterative debate with critique modes; streams council debate rounds. |
| **Monitor an active run** | **`GET /api/conversations/{id}/progress`** | Poll partial results of a run started by another client. |

**Key principles:**
- Never mutate global config for ad-hoc queries. Use per-request `models` / `council_models` / `chairman_model` overrides instead.
- Use optional `documents` on `/api/ask`, conversation message endpoints, council debate, and advisor debate when prompts need file context.
- Use conversation endpoints when you need follow-up questions — models automatically receive prior turns as context.
- `/api/ask` does not load prior history. Each successful call creates a new saved conversation visible in the UI and returns its `conversation_id`.
- Advisor debates always require a conversation — create one first, then stream the debate to it.
- Use `GET /api/conversations/{id}/progress` to check on an active run started by another client (MCP, UI, or another script) — returns `{active: false}` when no run is in progress.

---

## Provider & model availability

**Provider toggles are global:**

`enabled_providers` and `direct_provider_toggles` (Settings → Council Config) control which providers appear in **all** model pickers — Council Setup, Advisor Setup, and Settings temperature controls. A provider must be both **configured** (API key set / Ollama connected) and **enabled** (toggle on) for its models to appear. By default, providers are enabled when first configured.

REST/MCP agents listing models should call the model list endpoints directly (`/api/models`, `/api/models/direct`, `/api/ollama/tags`, `/api/custom-endpoint/models`). Availability depends on credentials, not UI toggles.

---

## Cost reporting

All council runs, iterative council debates, advisor debates, `/api/ask` responses, saved conversation metadata, and MCP deliberation outputs expose cost data:

- Per model call: `usage` (normalized token counts) and `cost` (provider, tokens, USD cost, pricing source, confidence, status).
- Per run: `cost_report` with total USD cost, input/output/total token totals, call totals, known/unknown/estimated/free counts, breakdown by model and stage, and raw call rows.

Token semantics:

- `input_tokens` are prompt/context tokens.
- `output_tokens` are visible generated output tokens.
- `reasoning_tokens` are preserved inside `usage` and call rows when providers report them. When providers bill reasoning as output, the estimated output cost includes those reasoning tokens.
- `total_tokens` is the provider-reported total when available; otherwise it falls back to input plus output.

Pricing order:

1. Provider-reported cost when available. OpenRouter `usage.cost` / `usage.total_cost` is treated as known.
2. Known-free rules report `$0`: `ollama:*`, `nvidia:*`, OpenRouter models ending in `:free`, the known free `opencode-zen:*` models, and custom endpoints whose configured `endpoint_url` contains the official `opencode.ai` host.
3. OpenCode hardcoded pricing table for paid OpenCode Go and Zen models (`pricing_source: "table:opencode"`, `cost_status: "estimated"`).
4. Catalog estimate from `https://ai-model-pricing.com/api/v1/pricing.json`, cached locally in `data/model_pricing_cache.json`.
5. Fallback catalog estimate from LiteLLM's `model_prices_and_context_window.json`.
6. If usage is present but pricing cannot be matched, the report preserves token usage and marks cost as unknown.

Environment overrides:

| Variable | Default |
|----------|---------|
| `LLM_COUNCIL_PRICING_SOURCE_URL` | `https://ai-model-pricing.com/api/v1/pricing.json` |
| `LLM_COUNCIL_LITELLM_PRICING_URL` | `https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json` |
| `LLM_COUNCIL_PRICING_CACHE_TTL_SECONDS` | `86400` |

Custom endpoint note: custom OpenAI-compatible endpoints do not have a universal billing API. OpenCode Zen and OpenCode Go are first-class direct providers (`opencode-zen:` and `opencode-go:` prefixes) with their own pricing table in `costs.py` — see "OpenCode note" above. Other custom endpoints use catalog estimates only when the upstream model ID can be matched, otherwise cost is unknown.

---

## Document uploads and extraction

Document inputs are converted to plain text before model calls so they work consistently across OpenRouter, Ollama, Groq, direct providers, custom endpoints, REST, MCP, and the UI.

Supported v1 formats:

- PDFs
- Text-like files: `.txt`, `.md`, `.csv`, `.json`, `.yaml`, `.xml`, `.html`
- Logs, source code, and common config files

REST endpoints:

- `POST /api/documents/extract` accepts multipart uploads from the UI and returns extracted document payloads plus warnings.
- `POST /api/documents/extract-json` accepts JSON documents with `data_base64` and returns extracted document payloads plus warnings.

Request bodies that accept `documents`:

- `POST /api/ask`
- `POST /api/conversations/{id}/message`
- `POST /api/conversations/{id}/message/stream`
- `POST /api/conversations/{id}/message/debate`
- `POST /api/conversations/{id}/debate/stream`

Document payload shape:

```json
{
  "name": "notes.txt",
  "mime_type": "text/plain",
  "text": "Meeting notes..."
}
```

For source files over MCP/JSON, use `data_base64` instead of `text`; the MCP client extracts those files through `/api/documents/extract-json` before starting the model run.

Conversation history stores attachment metadata only: file name, MIME type, byte size, extracted character count, page count when available, and warnings. It does not store raw file bytes or extracted text.

PDF handling:

- Embedded text extraction uses `pdfplumber`.
- OCR is optional. Set `LLM_COUNCIL_OCR_ENABLED=1` and install OCRmyPDF, Tesseract, Ghostscript, and qpdf in the backend runtime.
- If OCR is disabled or unavailable, extraction continues with embedded text and warnings.

---

## Examples (REST fallback)

### 1. One-Shot Query (scripts / REST-only environments)

The simplest way to query a model. Each successful call creates a new
conversation visible in the UI and returns its `conversation_id`; no prior
conversation history is loaded.

```bash
curl -X POST http://localhost:8001/api/ask \
  -H "Content-Type: application/json" \
  -d '{
    "content": "What is the capital of France?",
    "models": ["custom:moonshotai/kimi-k2.6"],
    "execution_mode": "chat_only"
  }'
# → {"conversation_id": "...", "response": "The capital of France is Paris.", "model": "custom:moonshotai/kimi-k2.6", "error": null}
```

```python
import httpx

async def ask(query, model, web_search=False, base_url="http://localhost:8001"):
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{base_url}/api/ask", json={
            "content": query,
            "models": [model],
            "web_search": web_search,
            "execution_mode": "chat_only",
        })
        return r.json()["response"]

# Usage:
# answer = await ask("Explain quantum tunneling", "openai:gpt-4.1")
```

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `content` | string | Yes | — | The question/prompt |
| `models` | array of strings | No | Global council config | 1+ model IDs to query |
| `chairman_model` | string | No | Global chairman config | Override chairman for `full` mode |
| `web_search` | boolean | No | `false` | Enable web search context |
| `execution_mode` | string | No | `"chat_only"` | `chat_only`, `chat_ranking`, or `full` |
| `documents` | array | No | `[]` | Extracted document payloads from `/api/documents/extract` or `/api/documents/extract-json` |

**Response shapes by mode:**

- **`chat_only` + 1 model:** `{"conversation_id": "...", "response": "...", "model": "...", "error": null, "usage": {...}, "cost": {...}, "cost_report": {...}}`
- **`chat_only` + N models:** `{"conversation_id": "...", "responses": [{model, response, error, usage, cost}, ...], "cost_report": {...}}`
- **`chat_ranking`:** `{"conversation_id": "...", "responses": [...], "rankings": [...], "aggregate_rankings": [...], "label_to_model": {...}, "cost_report": {...}}`
- **`full`:** `{"conversation_id": "...", "response": "...", "chairman_model": "...", "responses": [...], "rankings": [...], "aggregate_rankings": [...], "label_to_model": {...}, "cost_report": {...}}`

`conversation_id` identifies the saved UI conversation. `cost_report` is always
in USD. It summarizes `total_cost`, `input_tokens`, `output_tokens`,
`total_tokens`, `total_calls`, `known_cost_calls`, `unknown_cost_calls`,
`estimated_calls`, `free_calls`, `by_model`, `by_stage`, and raw `calls`.

---

### 2. One-Shot with Multiple Models

```bash
curl -X POST http://localhost:8001/api/ask \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Compare REST vs GraphQL",
    "models": ["openai:gpt-4.1", "anthropic:claude-sonnet-4", "custom:moonshotai/kimi-k2.6"],
    "execution_mode": "chat_only"
  }'
# → {"responses": [{model, response, error}, {model, response, error}, ...]}
```

---

### 3. One-Shot Full Deliberation

```python
async def deliberate(query, models, base_url="http://localhost:8001"):
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(f"{base_url}/api/ask", json={
            "content": query,
            "models": models,
            "execution_mode": "full",
            "web_search": True,
        })
        data = r.json()
        return data["response"]  # Chairman's synthesized answer
```

No conversation setup. No config mutation. One call; use the returned
`conversation_id` to inspect the saved run.

---

### 4. Streaming with Per-Request Overrides (REST-only — live SSE progress)

When you need SSE events for real-time progress (stage1_progress, stage2_progress, etc.), use the streaming endpoint with per-request model overrides:

```python
import asyncio, httpx, json

async def stream_deliberation(query, models, chairman=None, web_search=False, base_url="http://localhost:8001"):
    async with httpx.AsyncClient(timeout=300) as client:
        # Create conversation (only needed for stream endpoint)
        conv = (await client.post(f"{base_url}/api/conversations", json={})).json()
        conv_id = conv["id"]

        # Stream with per-request overrides — global config untouched
        payload = {
            "content": query,
            "web_search": web_search,
            "execution_mode": "full",
            "council_models": models,        # per-request override
            "chairman_model": chairman,       # per-request override
        }

        stage3 = {}
        async with client.stream("POST", f"{base_url}/api/conversations/{conv_id}/message/stream", json=payload) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                t = event.get("type")
                if t == "stage3_complete":
                    stage3 = event["data"]

        return stage3.get("response")
```

**Per-request override fields (available on both `/message` and `/message/stream`):**

| Field | Type | Description |
|-------|------|-------------|
| `council_models` | array of strings | Override which models run in Stage 1+2 |
| `chairman_model` | string | Override which model runs Stage 3 synthesis |

These fields are optional. If omitted, the global config is used. They **never mutate** settings.

---

### 5. Multi-Turn Conversations (Follow-Up Questions)

Conversation endpoints automatically pass prior turns as context to the models. The models see the full chat history, so follow-up questions work naturally.

```python
import httpx

async def multi_turn_chat(base_url="http://localhost:8001"):
    async with httpx.AsyncClient(timeout=120) as client:
        # Create conversation once
        conv = (await client.post(f"{base_url}/api/conversations", json={})).json()
        conv_id = conv["id"]

        # First question
        r1 = await client.post(f"{base_url}/api/conversations/{conv_id}/message", json={
            "content": "What is a monad in functional programming?",
            "execution_mode": "chat_only",
            "council_models": ["openai:gpt-4.1"],
        })
        print("A1:", r1.json()["stage1"][0]["response"])

        # Follow-up — the model remembers the previous exchange
        r2 = await client.post(f"{base_url}/api/conversations/{conv_id}/message", json={
            "content": "Can you give me a concrete example in Python?",
            "execution_mode": "chat_only",
            "council_models": ["openai:gpt-4.1"],
        })
        print("A2:", r2.json()["stage1"][0]["response"])

        # Third turn — full context of turns 1+2 is available
        r3 = await client.post(f"{base_url}/api/conversations/{conv_id}/message", json={
            "content": "How does this compare to Rust's Result type?",
            "execution_mode": "chat_only",
            "council_models": ["openai:gpt-4.1"],
        })
        print("A3:", r3.json()["stage1"][0]["response"])
```

**How context works:**
- Each message sent to a conversation endpoint includes all prior user/assistant turns as chat history
- For assistant context, the system uses the chairman synthesis (stage3) when available, otherwise the first successful model response from stage1
- `/api/ask` creates a new saved conversation per call but has no multi-turn memory (use conversation message endpoints for follow-ups)
- You can reuse the same `conversation_id` across sessions — history is persisted to disk

**When to use multi-turn vs one-shot:**

| Scenario | Endpoint | Multi-turn? |
|----------|----------|-------------|
| Independent questions, no follow-up needed | `POST /api/ask` | No |
| Research session with follow-ups | `POST /api/conversations/{id}/message` | Yes |
| Interactive exploration with live progress | `POST /api/conversations/{id}/message/stream` | Yes |

---

### 6. Sync Conversation Endpoint (JSON, saves to history)

For when you want conversation history but don't need SSE streaming:

```bash
# Create conversation first
CONV_ID=$(curl -s -X POST http://localhost:8001/api/conversations -H "Content-Type: application/json" -d '{}' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Send message (returns JSON, saves to conversation)
curl -X POST "http://localhost:8001/api/conversations/$CONV_ID/message" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Explain monads in simple terms",
    "execution_mode": "chat_only",
    "council_models": ["openai:gpt-4.1"]
  }'
```

Response includes all stages that were executed:
```json
{
  "stage1": [{"model": "openai:gpt-4.1", "response": "...", "error": null, "usage": {...}, "cost": {...}}],
  "stage2": null,
  "stage3": null,
  "aggregate_rankings": null,
  "label_to_model": null,
  "cost_report": {...}
}
```

---

### 7. Health Check

```bash
curl http://localhost:8001/api/health
# → {"status": "ok", "service": "LLM Council API"}
```

---

### 8. Get Current Council Configuration

```bash
curl http://localhost:8001/api/settings | python3 -m json.tool
```

Key fields returned:
- `council_models` — list of model IDs in the council
- `chairman_model` — model that synthesizes the final answer
- `execution_mode` — `"full"` / `"chat_ranking"` / `"chat_only"` (persisted; omitted from some GET responses — use export for full blob)
- `search_provider` — active search provider
- `enabled_providers` — global provider toggles (`openrouter`, `ollama`, `groq`, `direct`, `custom`) — apply to all model pickers (Council, Advisors, Settings)
- `direct_provider_toggles` — per-direct-provider toggles (also global)
- `date_format` — display date format (`"auto"`, `"MM/DD/YYYY"`, `"DD/MM/YYYY"`, `"YYYY-MM-DD"`)
- `response_language` — language for council/advisor model responses (default `"English"`)
- `valid_response_languages` — read-only list of allowed `response_language` values (canonical source: `VALID_RESPONSE_LANGUAGES` in `backend/prompts.py`)
- `response_language_default` — default language string (`"English"`)
- `advisor_presets` — saved advisor lineups (see §18)
- `council_presets` — saved council lineups (members + chairman; see §18b)
- `*_api_key_set` — boolean flags (never returns actual keys)
- `custom_endpoint_name` / `custom_endpoint_url` — custom provider details

---

### 9. Update Global Council Configuration

```bash
curl -X PUT http://localhost:8001/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "council_models": ["custom:z-ai/glm-5.1", "ollama:granite4.1:8b", "custom:moonshotai/kimi-k2.6"],
    "chairman_model": "custom:nvidia/nemotron-3-super-120b-a12b",
    "execution_mode": "full"
  }'
```

All fields are optional — only provided fields are updated. Requires minimum 1 model.

**Valid `execution_mode` values:**
- `"full"` — all 3 stages (individual → peer review → chairman synthesis)
- `"chat_ranking"` — stages 1+2 (no chairman synthesis)
- `"chat_only"` — stage 1 only (fastest, individual responses)

**Temperature fields:**

| Field | Default | Description |
|-------|---------|-------------|
| `council_temperature` | `0.5` | Stage 1 creativity (higher = more varied individual responses) |
| `chairman_temperature` | `0.4` | Stage 3 synthesis creativity |
| `stage2_temperature` | `0.3` | Stage 2 ranking consistency (lower = more deterministic) |

Provider note: some models only accept their default temperature. The backend omits temperature automatically for known restricted models so preflight and calls do not fail on provider-specific `temperature` validation.

---

### 10. Configure System Prompts, Search Tuning, and Provider Toggles

```bash
curl -X PUT http://localhost:8001/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "stage1_prompt": "You are an expert analyst. Answer with evidence and cite sources.",
    "stage2_prompt": "Rank the responses below by accuracy and depth.",
    "stage3_prompt": "Synthesize the best elements from all responses into a definitive answer.",
    "enabled_providers": {"openrouter": true, "ollama": false, "groq": true, "direct": false},
    "direct_provider_toggles": {"openai": true, "anthropic": true, "google": false, "nvidia": true}
  }'
```

**Editable system prompt fields:**

| Field | Description |
|-------|-------------|
| `stage1_prompt` | System prompt for Stage 1 individual model responses |
| `stage2_prompt` | System prompt for Stage 2 peer ranking |
| `stage3_prompt` | System prompt for Stage 3 chairman synthesis |
| `stage4_prompt` | System prompt for Stage 4 corrected draft (multi-round debate only) |
| `title_prompt` | Prompt used to generate conversation titles |
| `query_prompt` | Prompt used to reformulate user query for web search (LLM mode) |

**Search tuning fields:**

| Field | Default | Description |
|-------|---------|-------------|
| `search_result_count` | `8` | Number of web search results to retrieve (5–15) |
| `search_hybrid_mode` | `true` | DuckDuckGo: combine web + news results for better current-events coverage |
| `full_content_results` | `3` | How many top results to fetch full article text via Jina Reader (0 = disabled) |

**`enabled_providers` keys:** `openrouter`, `ollama`, `groq`, `direct` (master toggle for all direct), `custom`

**Note:** These toggles are **global** — they filter model lists in all pickers (Council Setup, Advisor Setup, and Settings).

**`direct_provider_toggles` keys:** `openai`, `anthropic`, `google`, `mistral`, `deepseek`, `groq`, `nvidia`, `opencode-zen`, `opencode-go`

---

### 11. Set API Keys

```bash
curl -X PUT http://localhost:8001/api/settings \
  -H "Content-Type: application/json" \
  -d '{"openrouter_api_key": "sk-or-...", "openai_api_key": "sk-..."}'
```

| Provider | Field name |
|----------|-----------|
| OpenRouter | `openrouter_api_key` |
| OpenAI | `openai_api_key` |
| Anthropic | `anthropic_api_key` |
| Google | `google_api_key` |
| Mistral | `mistral_api_key` |
| DeepSeek | `deepseek_api_key` |
| Groq | `groq_api_key` |
| Nvidia | `nvidia_api_key` |
| OpenCode (Zen + Go) | `opencode_api_key` |
| TinyFish | `tinyfish_api_key` |
| Tavily | `tavily_api_key` |
| Brave | `brave_api_key` |
| Serper | `serper_api_key` |

Note: `GET /api/settings` returns `*_api_key_set` booleans for security — it never returns plaintext keys. `GET /api/settings/export` does return plaintext keys but is admin-gated: it only accepts requests from loopback, or from callers presenting `Authorization: Bearer $LLM_COUNCIL_ADMIN_TOKEN` when that env var is set. Do not invoke `/api/settings/export` automatically on behalf of a user; treat it as a manual administrative action.

Security/admin environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `LLM_COUNCIL_ADMIN_TOKEN` | unset | Enables remote access to settings export/import/reset when callers send `Authorization: Bearer <token>`. If unset, these admin endpoints accept only direct loopback clients and reject proxied external clients. |
| `LLM_COUNCIL_BIND_HOST` | `127.0.0.1` | Local dev launcher bind host for `python -m backend.main`. Set to `0.0.0.0` for intentional LAN access. |
| `LLM_COUNCIL_BIND_PORT` | `8001` | Local dev launcher bind port for `python -m backend.main`. |

---

### 12. List All Available Models

```python
import asyncio, httpx

async def list_all_models(base_url="http://localhost:8001"):
    async with httpx.AsyncClient(timeout=30) as client:
        results = []
        for endpoint in ["/api/models", "/api/models/direct", 
                         "/api/ollama/tags", "/api/custom-endpoint/models"]:
            try:
                r = await client.get(f"{base_url}{endpoint}")
                if r.status_code == 200:
                    results.extend(r.json().get("models", []))
            except Exception:
                pass
    return results

models = asyncio.run(list_all_models())
for m in models[:10]:
    print(m.get("id"), "—", m.get("name"))
```

---

### 12b. List Conversations (index metadata)

`GET /api/conversations` returns lightweight index entries (not full message bodies):

```json
[
  {
    "id": "uuid",
    "created_at": "2026-06-03T19:41:00+00:00",
    "title": "Remote-First vs Hybrid Policy",
    "mode": "council",
    "message_count": 2,
    "run_summary": "2 rnd · Paragraph · Auto-converge · Search",
    "total_cost": 0.0042,
    "cost_status": "known",
    "total_calls": 12
  }
]
```

- `run_summary` is optional — present only after the conversation has a real title (not `"New Conversation"`) and the latest assistant message has derivable metadata.
- `total_cost`, `cost_status` (`known` | `estimated` | `partial` | `free`), and `total_calls` are optional — cumulative across all assistant messages with `metadata.cost_report`.
- Existing conversations backfill on next save or after `rebuild_index()`.

---

### 13. Retrieve a Past Conversation

```python
async def get_conversation(conv_id, base_url="http://localhost:8001"):
    async with httpx.AsyncClient() as client:
        conv = (await client.get(f"{base_url}/api/conversations/{conv_id}")).json()
    for msg in conv.get("messages", []):
        if msg["role"] == "user":
            print("Q:", msg["content"])
        elif msg["role"] == "assistant":
            s3 = msg.get("stage3", {})
            if s3:
                print("A (chairman):", s3.get("response", "")[:500])
    return conv
```

---

### 13b. Check Live Progress of an Active Run

Poll this endpoint to observe an in-progress council deliberation or multi-round debate from another client. Returns partial stage results as they stream.

```bash
curl http://localhost:8001/api/conversations/$CONV_ID/progress | python3 -m json.tool
```

**Response when a run is active:**
```json
{
  "active": true,
  "stage": "stage1",
  "execution_mode": "full",
  "progress": {
    "stage1": {"count": 2, "total": 4},
    "stage2": {"count": 0, "total": 0}
  },
  "stage1": [
    {"model": "openai:gpt-4.1", "response": "...", "error": null},
    {"model": "anthropic:claude-sonnet-4", "response": "...", "error": null}
  ],
  "stage2": null,
  "stage3": null,
  "stage4": null
}
```

**Response when no run is active:**
```json
{"active": false}
```

```python
import asyncio, httpx

async def poll_progress(conv_id: str, base_url="http://localhost:8001"):
    async with httpx.AsyncClient() as client:
        while True:
            r = await client.get(f"{base_url}/api/conversations/{conv_id}/progress")
            data = r.json()
            if not data.get("active"):
                print("Run complete or no active run.")
                break
            s1 = data["progress"]["stage1"]
            print(f"Stage: {data['stage']} — {s1['count']}/{s1['total']} models done")
            await asyncio.sleep(2)
```

**Use cases:**
- Frontend auto-reconnects to in-progress runs when navigating back to a conversation
- MCP agents or scripts can monitor a deliberation started elsewhere
- Dashboard / status views that show active council activity

---

### 14. List and Inspect Personas

```bash
# List all 12 personas with current customizations
curl http://localhost:8001/api/personas | python3 -m json.tool

# Each persona has: id, name, role, description, system_prompt, avatar_emoji, color, is_customized
```

```python
import httpx

async def get_persona(persona_id, base_url="http://localhost:8001"):
    async with httpx.AsyncClient() as client:
        personas = (await client.get(f"{base_url}/api/personas")).json()
    return next((p for p in personas if p["id"] == persona_id), None)
```

**Built-in persona IDs:** `skeptic`, `pragmatist`, `innovator`, `historian`, `ethicist`, `analyst`, `contrarian`, `strategist`, `humanist`, `risk-assessor`, `comedian`, `economist`

---

### 15. Update a Persona

Customize any persona's name, role, description, system prompt, or emoji. Changes persist to disk and mark `is_customized: true`.

```bash
curl -X PATCH http://localhost:8001/api/personas/skeptic \
  -H "Content-Type: application/json" \
  -d '{
    "name": "The Devil'"'"'s Advocate",
    "role": "Adversarial Thinker",
    "system_prompt": "You are The Devil'"'"'s Advocate. Your role is to challenge every claim aggressively, find the weakest link in any argument, and force other advisors to defend their positions rigorously."
  }'
# → Returns the updated persona object with is_customized: true
```

Only provided fields are changed; others keep their current values.

**To reset a persona to its factory defaults:**

```bash
curl -X DELETE http://localhost:8001/api/personas/skeptic/override
# → Returns the restored default persona with is_customized: false
```

---

### 16. Run an Advisor Debate

Personas debate your question across configurable rounds, then a neutral model produces a verdict.

Use this for questions that need disagreement, tradeoff analysis, prioritization, risk review, strategy, ethics, or a decision. For simple answer generation, prefer `model_chat` or `council_deliberate`; the advisor prompt design intentionally creates positions and rebuttals.

```python
import asyncio, httpx, json

async def run_advisor_debate(
    question: str,
    persona_ids: list[str],           # 2-4 required
    default_model: str,
    max_rounds: int = 3,
    search_provider: str | None = None,
    base_url: str = "http://localhost:8001",
) -> dict:
    async with httpx.AsyncClient(timeout=300) as client:
        # Create a fresh conversation to hold the debate
        conv = (await client.post(f"{base_url}/api/conversations", json={})).json()
        conv_id = conv["id"]

        payload = {
            "question": question,
            "persona_ids": persona_ids,
            "default_model": default_model,
            "max_rounds": max_rounds,
            "web_search": search_provider is not None,
            "search_provider": search_provider,
        }

        result = {}
        async with client.stream("POST", f"{base_url}/api/conversations/{conv_id}/debate/stream", json=payload) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                if event.get("type") == "advisor_complete":
                    result = event["data"]
                    result["conversation_id"] = conv_id

        return result

# Usage
result = asyncio.run(run_advisor_debate(
    question="Should we rewrite this service in Rust?",
    persona_ids=["skeptic", "pragmatist", "innovator"],
    default_model="openai:gpt-4.1",
    max_rounds=3,
))
print("Consensus:", result["consensus_reached"])
print("Verdict:", result["verdict"]["content"])
```

**Debate request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `question` | string | Yes | — | The topic to debate |
| `persona_ids` | array | Yes | — | 2–4 persona IDs |
| `default_model` | string | No | `advisor_default_model` setting | Model for all advisors |
| `model_assignments` | object | No | — | Per-persona overrides: `{"skeptic": "openai:gpt-4.1"}` |
| `max_rounds` | integer | No | `advisor_default_rounds` setting | Number of rounds (3–10) |
| `web_search` | boolean | No | `false` | Enable web search context |
| `search_provider` | string | No | — | `duckduckgo`, `tavily`, `brave`, `serper`, `tinyfish` |

Advisor response rows include `word_count`, `word_limit`, `word_limit_exceeded`, and optional `warning`. Exceeding the word limit is treated as guidance failure, not a model failure: the response is kept and surfaced with a warning.

**`advisor_complete` event data:**

```json
{
  "rounds": [
    {
      "round_number": 1,
      "average_consensus_score": 2.33,
      "responses": [
        {"persona_id": "skeptic", "persona_name": "The Skeptic", "model": "openai:gpt-4.1",
         "content": "I question whether Rust's learning curve justifies the rewrite...",
         "consensus": false,
         "consensus_score": 2}
      ]
    }
  ],
  "consensus_reached": false,
  "consensus_round": null,
  "round_extracts": [
    {
      "round_number": 1,
      "model": "openai:gpt-4.1",
      "content": "Advisor: The Skeptic\nOverall position: ...\nStrongest claims:\n- ...",
      "error": null
    }
  ],
  "tiebreaker": null,
  "verdict": {
    "model": "openai:gpt-4.1",
    "content": "## Summary\n\nThe debate highlighted...\n\n## Verdict\n\nA targeted rewrite...",
    "error": null
  },
  "personas": [...]
}
```

---

### 17. Advisor Debate with Per-Persona Models and Web Search

```python
result = asyncio.run(run_advisor_debate(
    question="What is the best architecture for a real-time data pipeline?",
    persona_ids=["analyst", "innovator", "pragmatist", "risk-assessor"],
    default_model="openai:gpt-4.1",
    max_rounds=3,
    search_provider="duckduckgo",
))

# Access individual round responses
for round_data in result["rounds"]:
    print(f"\n--- Round {round_data['round_number']} ---")
    for resp in round_data["responses"]:
        print(f"{resp['persona_name']}: {resp['content'][:200]}...")

print("\n=== VERDICT ===")
print(result["verdict"]["content"])
```

**To assign different models per persona:**

```bash
curl -X POST "http://localhost:8001/api/conversations/$CONV_ID/debate/stream" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Monolith vs microservices for a 5-person startup?",
    "persona_ids": ["skeptic", "pragmatist", "innovator"],
    "model_assignments": {
      "skeptic": "anthropic:claude-sonnet-4-6",
      "pragmatist": "openai:gpt-4.1",
      "innovator": "custom:moonshotai/kimi-k2.6"
    },
    "max_rounds": 3
  }'
```

---

### 18. Configure Advisor Settings

```bash
# Set default model and round count for advisor debates
curl -X PUT http://localhost:8001/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "advisor_default_model": "openai:gpt-4.1",
    "advisor_tiebreaker_model": "anthropic:claude-sonnet-4-6",
    "advisor_temperature": 0.7,
    "advisor_default_rounds": 3
  }'
```

**Advisor settings fields:**

| Field | Default | Description |
|-------|---------|-------------|
| `advisor_default_model` | `""` | Model for all advisors when no per-persona assignment given |
| `advisor_tiebreaker_model` | `""` | Model for tiebreaker + verdict synthesis (falls back to `advisor_default_model`) |
| `advisor_temperature` | `0.7` | LLM temperature for advisor calls |
| `advisor_default_rounds` | `3` | Default number of debate rounds (3–10) |
| `advisor_presets` | `[]` | Saved advisor setups (personas, model mode, models, optional rounds/search). Max 20 presets. Each preset: `{ id, name, persona_ids, mode, default_model, tiebreaker_model, model_assignments, max_rounds, search_provider, is_default, last_used_at }` |

**Advisor prompt customization fields** (all reset-to-default via `POST /api/settings/reset`):

| Field | Description |
|-------|-------------|
| `advisor_round1_prompt` | System prompt for the first debate round |
| `advisor_followup_prompt` | System prompt for subsequent follow-up rounds |
| `advisor_cross_pollination_prompt` | Prompt for synthesizing prior round context into follow-ups |
| `advisor_verdict_prompt` | Prompt for the final verdict / summary model |
| `advisor_tiebreaker_prompt` | Prompt for the tiebreaker model (2-persona deadlock) |

**Save or update presets via REST:**

```bash
curl -X PUT http://localhost:8001/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "advisor_presets": [
      {
        "id": "preset-uuid-here",
        "name": "Startup Panel",
        "persona_ids": ["skeptic", "pragmatist", "innovator"],
        "mode": "simple",
        "default_model": "openai:gpt-4.1",
        "tiebreaker_model": "openai:gpt-4.1",
        "model_assignments": null,
        "max_rounds": 3,
        "search_provider": null,
        "is_default": true,
        "last_used_at": null
      }
    ]
  }'
```

MCP: `advisor_settings` action `get` returns `advisor_presets`. Preset CRUD: `advisor_settings` actions `list_presets`, `save_preset`, `delete_preset`, `set_default_preset`.

---

### 18b. Council Presets (`council_presets`)

Saved from welcome-screen **Council Setup** — council members + chairman only (not execution mode). Max 20 presets; one `is_default` auto-loads on open.

| Field | Default | Description |
|-------|---------|-------------|
| `council_presets` | `[]` | Each preset: `{ id, name, council_models, chairman_model, is_default, last_used_at }` |

```bash
curl -X PUT http://localhost:8001/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "council_presets": [
      {
        "id": "preset-uuid",
        "name": "Coding Council",
        "council_models": ["openai:gpt-4.1", "anthropic:claude-3.5-sonnet"],
        "chairman_model": "openai:gpt-4.1",
        "is_default": true
      }
    ]
  }'
```

MCP: `council_settings` action `get` returns `council_presets`. Preset CRUD: `council_settings` actions `list_presets`, `save_preset`, `delete_preset`, `set_default_preset`.

**UI behavior:** Main-screen editor (Council Setup) is the **only** place to pick council members and chairman — auto-saves on each change. Lineup is read-only in a conversation after the first message. Settings provides provider toggles (global) and temperature controls only; model selection was removed from Settings to avoid duplication.

---

### 19. Custom OpenAI-Compatible Endpoints (OpenCode Zen Setup)

The AI Counsel allows you to connect to any OpenAI-compatible API (such as Together, Fireworks, Together, vLLM, LM Studio, or OpenCode Zen) and use their models seamlessly.

To register a custom provider (e.g. OpenCode Zen at `https://opencode.ai/zen/v1/` with a default model query API):

```bash
curl -X PUT http://localhost:8001/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "custom_endpoint_name": "OpenCodeZen",
    "custom_endpoint_url": "https://opencode.ai/zen/v1/",
    "custom_endpoint_api_key": "your-api-key-here",
    "enabled_providers": {
      "openrouter": false,
      "ollama": true,
      "groq": false,
      "direct": false,
      "custom": true
    }
  }'
```

Once saved and enabled, you can reference the custom models by prepending the `custom:` prefix:
- `custom:deepseek-v4-flash-free`
- `custom:big-pickle`
- `custom:nemotron-3-super-free`

For example, to run a stateless query using `custom:deepseek-v4-flash-free`:
```bash
curl -X POST http://localhost:8001/api/ask \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Explain functional programming in one sentence.",
    "models": ["custom:deepseek-v4-flash-free"],
    "execution_mode": "chat_only"
  }'
```

---

### 20. Setup Walkthrough for Per-Persona Debate Models

You can customize exactly which model runs which persona to match their specific personalities (e.g., giving *The Skeptic* a highly detailed model, and *The Pragmatist* a fast, concise model).

Here is a python script demonstrating how to configure and launch a customized 3-persona debate where:
- **The Skeptic** runs on a premium cloud model (`openrouter:anthropic/claude-3.5-sonnet`)
- **The Pragmatist** runs on a fast inference model (`groq:llama3-70b-8192`)
- **The Innovator** runs on a local model (`ollama:granite4:1b`)

```python
import asyncio, httpx, json

async def run_hybrid_debate():
    async with httpx.AsyncClient(timeout=300) as client:
        # 1. Create a fresh conversation
        conv = (await client.post("http://localhost:8001/api/conversations", json={})).json()
        conv_id = conv["id"]

        # 2. Setup the debate payload
        payload = {
            "question": "Should we move our frontend state from Redux to Jotai?",
            "persona_ids": ["skeptic", "pragmatist", "innovator"],
            "max_rounds": 3,
            "default_model": "openrouter:google/gemini-pro-1.5",
            "model_assignments": {
                "skeptic": "openrouter:anthropic/claude-3.5-sonnet", # premium detail
                "pragmatist": "groq:llama3-70b-8192",                # fast pragmatic responses
                "innovator": "ollama:granite4:1b"                   # creative local experiments
            }
        }

        # 3. Stream the debate
        async with client.stream("POST", f"http://localhost:8001/api/conversations/{conv_id}/debate/stream", json=payload) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                
                # Print real-time updates as advisors speak
                if event.get("type") == "advisor_response":
                    data = event["data"]
                    print(f"\n[{data['persona_name']}] speaking via ({data['model']}):")
                    print(data["content"])
                
                elif event.get("type") == "advisor_complete":
                    print("\n=== DEBATE VERDICT ===")
                    print(event["data"]["verdict"]["content"])

asyncio.run(run_hybrid_debate())
```

---

### 21. Hybrid Local/Cloud Council Configuration

For maximum budget efficiency, you can run a hybrid council where multiple fast/cheap models answer independently in Stage 1, and a powerful local or cloud model synthesizes the answer as the Chairman in Stage 3.

Example: **OpenCode Zen / Groq for Stage 1 & 2**, and **Ollama granite4:1b locally for Chairman Stage 3**:

```bash
# 1. Save settings
curl -X PUT http://localhost:8001/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "council_models": [
      "custom:deepseek-v4-flash-free",
      "custom:nemotron-3-super-free",
      "groq:llama3-70b-8192"
    ],
    "chairman_model": "ollama:granite4:1b",
    "execution_mode": "full"
  }'

# 2. Deliberate
curl -X POST http://localhost:8001/api/ask \
  -H "Content-Type: application/json" \
  -d '{
    "content": "What is the best way to cache user sessions in a distributed web app?",
    "execution_mode": "full"
  }'
```

---

### 22. Multi-Round Council Debate

The Council Debate Config adds iterative refinement loops: models answer, peer-review each other, rewrite — then the Chairman synthesizes. See [`docs/COUNCIL-DEBATE-CONFIG.md`](../docs/COUNCIL-DEBATE-CONFIG.md) for the full guide.

**Quick decision guide:**

| Use case | `critique_mode` | `debate_rounds` |
|----------|----------------|----------------|
| Most questions | `freeform` | 2 |
| Structured essays, technical comparisons | `paragraph` | 2–3 |
| Fact-checking, claim accuracy | `claim` | 2 |
| Research / maximum depth | `freeform` or `claim` | 3–5 |

#### MCP — preferred

```python
# Simplest: 2-round freeform, auto-converge on (default)
result = await run_iterative_debate(
    query="What are the tradeoffs between REST and GraphQL?",
    debate_rounds=2,
    critique_mode="freeform",
)
print(result["stage4"]["response"])  # Chairman's corrected draft

# Paragraph mode: structured critique per section
result = await run_iterative_debate(
    query="Explain the CAP theorem and its practical implications",
    debate_rounds=3,
    critique_mode="paragraph",
    models=["openai:gpt-4.1", "anthropic:claude-sonnet-4-5", "google:gemini-2.5-flash"],
)

# Claim mode: per-fact verdicts (adds 1 extra API call per round)
result = await run_iterative_debate(
    query="Is nuclear energy a net positive for climate change?",
    debate_rounds=2,
    critique_mode="claim",
    auto_converge=True,
    convergence_threshold=1,   # stop after first stable round
)

# Force all rounds — no early stop
result = await run_iterative_debate(
    query="Compare PostgreSQL vs MongoDB for a social network",
    debate_rounds=5,
    auto_converge=False,
)
```

#### Update debate defaults via council_settings

```python
# Set global defaults so all future debates use these values
await council_settings(
    action="update",
    critique_mode="paragraph",
    debate_rounds=2,
    auto_converge=True,
    convergence_threshold=2,
)
```

#### REST fallback — run_iterative_debate equivalent

There is no single REST endpoint for multi-round debate. Use the SSE stream endpoint with `debate_rounds` in the payload:

```python
import asyncio, httpx, json

async def run_debate_rest(
    query: str,
    debate_rounds: int = 2,
    critique_mode: str = "freeform",
    models: list[str] | None = None,
    base_url: str = "http://localhost:8001",
) -> dict:
    async with httpx.AsyncClient(timeout=600) as client:
        # Optionally update debate settings before the run
        await client.put(f"{base_url}/api/settings", json={
            "critique_mode": critique_mode,
            "debate_rounds": debate_rounds,
        })

        conv = (await client.post(f"{base_url}/api/conversations", json={})).json()
        conv_id = conv["id"]

        payload = {
            "content": query,
            "execution_mode": "full",
            "debate_rounds": debate_rounds,
        }
        if models:
            payload["council_models"] = models

        stage4 = {}
        all_rounds = []
        async with client.stream(
            "POST",
            f"{base_url}/api/conversations/{conv_id}/message/stream",
            json=payload,
        ) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                t = event.get("type")
                if t == "stage4_complete":
                    stage4 = event.get("data", {})
                elif t == "debate_complete":
                    all_rounds = event.get("rounds", [])

        return {"stage4": stage4, "rounds": all_rounds, "conversation_id": conv_id}

# Usage
result = asyncio.run(run_debate_rest(
    query="What is the best approach for distributed database consistency?",
    debate_rounds=2,
    critique_mode="paragraph",
    models=["openai:gpt-4.1", "anthropic:claude-sonnet-4-5", "groq:llama3-70b-8192"],
))
print(result["stage4"]["response"])
```

**Debate config fields (REST `PUT /api/settings` or per-request on `/message/stream`):**

| Field | Type | Valid values | Default | Description |
|-------|------|-------------|---------|-------------|
| `critique_mode` | string | `freeform`, `paragraph`, `claim` | `freeform` | How models give feedback between rounds |
| `debate_rounds` | integer | 1–5 | `1` | Number of Stage 1→2→3 cycles before Stage 4 |
| `auto_converge` | boolean | — | `true` | Stop early when rankings stabilize |
| `convergence_threshold` | integer | 1–3 | `2` | Consecutive stable rounds needed to trigger early stop |

---

## Backup and Restore

```bash
# Export full settings from the backend host itself (includes actual API key values)
curl http://localhost:8001/api/settings/export -o council-settings.json

# Remote export requires LLM_COUNCIL_ADMIN_TOKEN on the server
curl -H "Authorization: Bearer $LLM_COUNCIL_ADMIN_TOKEN" \
  http://SERVER:8001/api/settings/export -o council-settings.json

# Import settings from backup locally, or add the same Authorization header remotely
curl -X POST http://localhost:8001/api/settings/import \
  -H "Content-Type: application/json" \
  -d @council-settings.json

# Reset all settings to factory defaults locally, or add the same Authorization header remotely
curl -X POST http://localhost:8001/api/settings/reset
```

---

## Search Provider Configuration

```bash
# Switch to TinyFish (free, 5 req/min)
curl -X PUT http://localhost:8001/api/settings \
  -H "Content-Type: application/json" \
  -d '{"search_provider": "tinyfish", "tinyfish_api_key": "sk-tinyfish-..."}'

# Valid providers: duckduckgo, tavily, brave, serper, tinyfish
# duckduckgo requires no key; all others require an API key
```

### Search Query Processing Mode

Control how your prompt is sent to the search engine via `search_keyword_extraction`:

```bash
curl -X PUT http://localhost:8001/api/settings \
  -H "Content-Type: application/json" \
  -d '{"search_keyword_extraction": "direct"}'
```

| Value | Behaviour |
|-------|-----------|
| `"direct"` | Send the exact user query to the search engine (default, recommended) |
| `"yake"` | Extract key terms with YAKE before searching — useful for very long prompts |
| `"llm"` | Use the Chairman model to reformulate the query into an optimal search term — slower but can improve results for complex questions |

> **DuckDuckGo note:** DDG applies its own built-in query optimisation internally. `"direct"` is recommended when using DuckDuckGo; `"llm"` is skipped for DDG even if selected.

---

## Key SSE Event Types

### Council streaming (`/message/stream`)

| Event | When | Contains |
|-------|------|----------|
| `search_start` | Web search begins | `provider` |
| `search_complete` | After web search | `search_context`, `search_query` |
| `stage1_init` | Before Stage 1 responses | `total` (model count) |
| `stage1_progress` | Each model responds | `data`: `{model, response, error, usage, cost}`, `count`, `total` |
| `stage1_complete` | After all models respond | `data`: list of `{model, response, error, usage, cost}` |
| `stage2_init` | Before Stage 2 rankings | `total` |
| `stage2_progress` | Each model ranks | `data`: `{model, ranking, parsed_ranking, usage, cost}`, `count`, `total` |
| `stage2_complete` | After peer review | `metadata`: `{label_to_model, aggregate_rankings}` |
| `stage3_complete` | After chairman synthesis | `data`: `{model, response, error, usage, cost}` |
| `stage4_start` | Stage 4 corrected draft begins | — |
| `stage4_complete` | Stage 4 corrected draft done | `data`: `{model, response, error, usage, cost}` |
| `round_start` | Each debate round begins | `round`, `total_rounds` |
| `round_complete` | Each debate round finishes | `round` |
| `convergence` | Early stop triggered | `round`, `message` |
| `debate_complete` | All debate rounds done | `total_rounds_executed`, `converged`, `critique_mode`, `rounds`, `stage4`, `cost_report` |
| `title_complete` | Title generated | `data`: `{title}` |
| `error` | On failure | `message` |
| `complete` | Stream finished | optional `metadata.cost_report` |

### Advisor debate streaming (`/debate/stream`)

| Event | When | Contains |
|-------|------|----------|
| `advisor_search_start` | Web search begins | — |
| `advisor_search_complete` | After web search | `data`: `{search_query}` |
| `advisor_debate_start` | Debate initialized | `data`: `{personas, max_rounds, question, web_search}` |
| `advisor_round_start` | Each round begins | `data`: `{round_number, order, is_parallel}` |
| `advisor_response` | Each persona responds | `data`: `{persona_id, persona_name, model, content, error, warning, consensus, consensus_score, word_count, word_limit, word_limit_exceeded, usage, cost}`, `round`, `count`, `total` |
| `advisor_round_complete` | Round finishes | `data`: `{round_number, responses, consensus_votes, consensus_reached}` |
| `advisor_tiebreaker_start` | Tiebreaker triggered (2 personas, no consensus) | — |
| `advisor_tiebreaker` | Tiebreaker result | `data`: `{model, content, error, usage, cost}` |
| `advisor_verdict_start` | Verdict generation begins | — |
| `advisor_verdict` | Verdict result | `data`: `{model, content, error, usage, cost}` |
| `advisor_complete` | **Authoritative final event** | `data`: `{rounds, consensus_reached, verdict, tiebreaker, personas, cost_report}` |
| `advisor_error` | Debate failed | `message` |
| `title_complete` | Title generated (first message only) | `data`: `{title}` |

**Important:** Always prefer `advisor_complete` as the authoritative source. Earlier per-event data is provisional accumulation; `advisor_complete` contains the final cleaned result used for persistence.

---

## Error Handling

Model errors appear inside stage results — not as top-level failures:

```python
for model_result in stage1:
    if model_result.get("error"):
        msg = model_result.get("error_message", "unknown error")
        if "429" in msg:
            print(f"{model_result['model']}: rate limited — retryable")
        elif "401" in msg or "403" in msg:
            print(f"{model_result['model']}: auth error — check API key")
        else:
            print(f"{model_result['model']}: failed — {msg}")
    else:
        print(f"{model_result['model']}: responded")
```

The `/api/ask` endpoint returns HTTP 502 if ALL models fail, with error details in the response body.

The council continues with successful models even if some fail.

---

## Troubleshooting

**Backend unreachable (`ConnectionRefused`)**
- Local: verify `uv run python -m backend.main` is running on port 8001
- Remote: check `http://<server>:8001/api/health` is accessible; firewall may be blocking port 8001
- Docker: run `docker ps` to confirm container is up and healthy

**Council models not updating**
- PUT to `/api/settings` returns the full settings object — check `council_models` in the response
- Model IDs must include provider prefix (e.g., `custom:z-ai/glm-5.1`, not `z-ai/glm-5.1`)

**SSE stream hangs or times out**
- Use `timeout=300` on the httpx client for full deliberations (can take 60-120 seconds)
- Check backend logs for provider-side errors
- Consider using `POST /api/ask` instead — no streaming complexity

**Model returns error in Stage 1**
- Check `*_api_key_set` flags in `/api/settings` — key may be missing
- Test a specific provider: `POST /api/settings/test-provider` with `{"provider_id": "openai", "api_key": "sk-..."}`
- Custom endpoint models need `custom_endpoint_url` and `custom_endpoint_api_key` configured

**Settings not persisting after restart**
- Settings are stored in `data/settings.json` — if using Docker, confirm the `./data` volume is mounted

---

## Installation

**Option 1: Clone and symlink**
```bash
git clone https://github.com/jacob-bd/the-ai-counsel.git
mkdir -p ~/.claude/skills
ln -s "$(pwd)/the-ai-counsel/skills/the-ai-counsel-api" ~/.claude/skills/the-ai-counsel-api
```

**Option 2: Copy directly**
```bash
mkdir -p ~/.claude/skills/the-ai-counsel-api
curl -o ~/.claude/skills/the-ai-counsel-api/SKILL.md \
  https://raw.githubusercontent.com/jacob-bd/the-ai-counsel/main/skills/the-ai-counsel-api/SKILL.md
```

After installation, Claude Code automatically discovers and loads the skill when you ask about council operations.
