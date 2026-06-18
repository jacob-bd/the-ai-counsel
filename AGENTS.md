# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

The AI Counsel is a 3-stage deliberation system where multiple LLMs collaboratively answer user questions through:
1. **Stage 1**: Individual model responses (with optional web search context)
2. **Stage 2**: Anonymous peer review/ranking to prevent bias
3. **Stage 3**: Chairman synthesis of collective wisdom

**Key Innovation**: Hybrid architecture supporting OpenRouter (cloud), Ollama (local), Groq (fast inference), direct provider connections, and custom OpenAI-compatible endpoints.

## Running the Application

**Quick Start:**
```bash
./start.sh
```

**Manual Start:**
```bash
# Backend (from project root)
uv run python -m backend.main

# Frontend (in new terminal)
cd frontend
npm run dev
```

**Ports:**
- Backend: `http://localhost:8001` (NOT 8000 - avoid conflicts)
- Frontend: `http://localhost:5173`
- MCP Server (SSE): Built-in at `/mcp` on the backend (`http://localhost:8001/mcp/sse`) — **10 action-based tools** (`council_deliberate`, `model_chat`, `advisor_debate`, `run_iterative_debate`, `council_settings`, `advisor_settings`, `personas`, `conversations`, `providers`, `config_backup`). See [`docs/mcp/TOOLS.md`](docs/mcp/TOOLS.md). `GET /api/health` reports `"mcp": {"tools": 10}`.

**Network Access:**
```bash
# Backend with network access:
LLM_COUNCIL_BIND_HOST=0.0.0.0 uv run python -m backend.main

# Frontend with network access:
cd frontend && npm run dev -- --host
```

**Backend bind variables:**
- `LLM_COUNCIL_BIND_HOST`: dev launcher bind host, default `127.0.0.1`. Use `0.0.0.0` only when you intentionally want LAN access.
- `LLM_COUNCIL_BIND_PORT`: dev launcher bind port, default `8001`.
- `LLM_COUNCIL_ADMIN_TOKEN`: required for remote access to `/api/settings/export`, `/api/settings/import`, and `/api/settings/reset`. Without it, those admin endpoints only accept direct loopback clients and reject proxied external clients.

**Installing Dependencies:**
```bash
# Backend
uv sync

# Frontend
npm install --prefix frontend
```

**Important**: If switching between Intel/Apple Silicon Macs with iCloud sync:
```bash
rm -rf frontend/node_modules && npm install --prefix frontend
```
This fixes binary incompatibilities (e.g., `@rollup/rollup-darwin-*` variants).

## Architecture Overview

### Backend (`backend/`)

**Provider System** (`backend/providers/`)
- **Base**: `base.py` - Abstract interface for all LLM providers
- **Implementations**: `openrouter.py`, `ollama.py`, `groq.py`, `openai.py`, `anthropic.py`, `google.py`, `mistral.py`, `deepseek.py`, `custom_openai.py`, `opencode.py` (OpenCode Zen + Go, chat/completions only)
- **Auto-routing**: Model IDs with prefix (e.g., `openai:gpt-4.1`, `ollama:llama3`, `custom:model-name`) route to correct provider
- **Routing logic**: `council.py:get_provider_for_model()` handles prefix parsing

**Core Modules**

| Module | Purpose |
|--------|---------|
| `council.py` | Orchestration: stage1/2/3 collection, rankings, title generation |
| `search.py` | Web search: DuckDuckGo, Tavily, Brave, Serper, TinyFish with Jina Reader content fetch |
| `settings.py` | Config management, persisted to `data/settings.json` |
| `config.py` | OpenRouter endpoint URL, data dir constant, settings-aware getters (`get_openrouter_api_key`, `get_council_models`, `get_chairman_model`, ...) that bridge env vars and `settings.py` |
| `costs.py` | Usage normalization, pricing lookup/cache, per-call cost attribution, and run-level cost reports |
| `documents.py` | Document validation and text extraction for uploads (text-like files and PDFs; optional OCR fallback) |
| `prompts.py` | Default system prompts for all stages (Stage 1/2/3, Title, Query) |
| `main.py` | FastAPI app with streaming SSE endpoints, live progress tracking (`_active_runs`), and MCP server mount |
| `storage.py` | Conversation persistence in `data/conversations/{id}.json`; index entries include optional `run_summary`, `total_cost`, `cost_status`, `total_calls` via `derive_run_summary()` / `derive_conversation_cost()` |

### Frontend (`frontend/src/`)

| Component | Purpose |
|-----------|---------|
| `App.jsx` | Main orchestration, SSE streaming, conversation state |
| `ChatInterface.jsx` | User input, web search toggle, execution mode |
| `DocumentUpload.jsx` | File picker/extraction UI for Council and Advisor document context |
| `Stage1.jsx` | Tab view of individual model responses |
| `Stage2.jsx` | Peer rankings with de-anonymization, aggregate scores |
| `Stage3.jsx` | Chairman synthesis (final answer) |
| `CostReport.jsx` | Compact run-cost panel with total cost, token/call counts, confidence status, and per-model breakdown (uses `formatCost.js`) |
| `CouncilGrid.jsx` | Visual grid of council members with provider icons |
| `CouncilSetup.jsx` | Inline council editor on welcome screen (members, chairman, presets; auto-save) |
| `Settings.jsx` | 8-section settings: General, LLM API Keys, Council Config, Council Debate Config, Council System Prompts, Advisor System Prompts, Search Providers, Backup & Reset |
| `GeneralSettings.jsx` | Date format and response language (General section) |
| `Sidebar.jsx` | Conversation list with stacked date/time, run summaries, cumulative cost pill, sidebar search on summary text, inline delete confirmation |
| `SearchableModelSelect.jsx` | Searchable dropdown for model selection |

**Styling**: "Council Chamber" dark theme (refined Midnight Glass). CSS variables in `index.css` (`--font-display`: Syne, `--font-ui`: Plus Jakarta Sans, `--font-content`: Source Serif 4, `--font-code`: JetBrains Mono). Primary accent blue (#3b82f6), chairman gold (#fbbf24). Staggered hero/card animations; glass panels with backdrop-filter.

## Critical Implementation Details

### Python Module Imports
**ALWAYS** use relative imports in backend modules:
```python
from .config import ...
from .council import ...
```
**NEVER** use absolute imports like `from backend.config import ...`

**Run backend as module** from project root:
```bash
uv run python -m backend.main  # Correct
cd backend && python main.py  # WRONG - breaks imports
```

### Model ID Prefix Format
Canonical reference table lives in [`skills/the-ai-counsel-api/SKILL.md`](skills/the-ai-counsel-api/SKILL.md) under "Quick Reference → Model ID prefix format". When changing the prefix set, update SKILL.md first; this section intentionally does not duplicate the table.

### Model Name Display Helper
Use this pattern in Stage components to handle both `/` and `:` delimiters:
```jsx
const getShortModelName = (modelId) => {
  if (!modelId) return 'Unknown';
  if (modelId.includes('/')) return modelId.split('/').pop();
  if (modelId.includes(':')) return modelId.split(':').pop();
  return modelId;
};
```

### Provider Icon Detection (CouncilGrid.jsx)
Check prefixes FIRST before name-based detection to avoid mismatches:
```jsx
const getProviderInfo = (modelId) => {
    const id = modelId.toLowerCase();
    // Check prefixes FIRST (order matters!)
    if (id.startsWith('custom:')) return PROVIDER_CONFIG.custom;
    if (id.startsWith('ollama:')) return PROVIDER_CONFIG.ollama;
    if (id.startsWith('groq:')) return PROVIDER_CONFIG.groq;
    // Then check name-based patterns...
};
```

### Stage 2 Ranking Format
The prompt enforces strict format for parsing:
```
1. Individual evaluations
2. Blank line
3. "FINAL RANKING:" header (all caps, with colon)
4. Numbered list: "1. Response C", "2. Response A", etc.
```
Fallback regex extracts "Response X" patterns if format not followed.

### Streaming & Abort Logic
- Backend checks `request.is_disconnected()` inside loops
- Frontend aborts via AbortController signal
- **Critical**: Always inject raw `Request` object into streaming endpoints (Pydantic models lack `is_disconnected()`)

### ReactMarkdown Safety
```jsx
<div className="markdown-content">
  <ReactMarkdown>
    {typeof content === 'string' ? content : String(content || '')}
  </ReactMarkdown>
</div>
```
Always wrap in `.markdown-content` div and ensure string type (some providers return arrays/objects).

### Tab Bounds Safety
In Stage1/Stage2, auto-adjust activeTab when out of bounds during streaming:
```jsx
useEffect(() => {
  if (activeTab >= responses.length && responses.length > 0) {
    setActiveTab(responses.length - 1);
  }
}, [responses.length]);
```

## Common Gotchas

1. **Port Conflicts**: Backend uses 8001 (not 8000). Update `backend/main.py` and `frontend/src/api.js` together.

2. **CORS Errors**: Frontend origins must match `main.py` CORS middleware (localhost:5173 and :3000).

3. **Missing Metadata**: `label_to_model` and `aggregate_rankings` are ephemeral - only in API responses, not stored.

4. **Duplicate Tabs**: Use immutable state updates (spread operator), not mutations. StrictMode runs effects twice.

5. **Search Rate Limits**: DuckDuckGo can rate-limit. Retry logic in `search.py` handles this.

6. **Jina Reader 451 Errors**: Many news sites block AI scrapers. Use Tavily/Brave or set `full_content_results` to 0.

7. **Model Deduplication**: When multiple sources provide same model, use Map-based deduplication preferring direct connections.

8. **Binary Dependencies**: `node_modules` in iCloud can break between Mac architectures. Delete and reinstall.

9. **Custom Endpoint Icons**: Models from custom endpoints may match name patterns (e.g., "claude"). Check `custom:` prefix first.

## Data Flow

```
User Query (+ optional web search / file uploads)
 ↓
[Document Extraction: text files + PDFs via pdfplumber, optional OCR]
 ↓
[Web Search: DuckDuckGo/Tavily/Brave + Jina Reader]
 ↓
Stage 1: Parallel queries → Stream individual responses
 ↓
Stage 2: Anonymize → Parallel peer rankings → Parse rankings
 ↓
Calculate aggregate rankings
 ↓
Stage 3: Chairman synthesis → Stream final answer
 ↓
Save conversation (stage1, stage2, stage3 only)
```

## API Endpoints

### One-Shot Query (Persisted)
```
POST /api/ask
Body: {content, models?, web_search?, execution_mode?, documents?}
→ JSON response with conversation_id; completed run appears in the UI
```
Each call creates a new conversation for auditability. The endpoint remains
one-shot: it does not load prior conversation history.

### Document Extraction / Uploads
```
POST /api/documents/extract
→ multipart upload endpoint used by the UI

POST /api/documents/extract-json
Body: {documents: [{name, mime_type?, data_base64}]}
→ JSON/base64 extraction endpoint used by MCP clients
```
Document-bearing requests accept extracted payloads as `documents: [{name, mime_type, text, metadata?}]` on `/api/ask`, conversation message endpoints, council debate, and advisor debate. Providers receive normalized text context; conversation storage keeps attachment metadata only.

PDFs use `pdfplumber` for embedded text. OCR is optional and requires `LLM_COUNCIL_OCR_ENABLED=1` plus OCRmyPDF, Tesseract, Ghostscript, and qpdf in the backend runtime. If OCR is unavailable, extraction continues with warnings instead of blocking normal text extraction.

### Per-Request Model Overrides
Both `/api/conversations/{id}/message` (sync) and `/api/conversations/{id}/message/stream` (SSE) accept optional `council_models` and `chairman_model` fields that override global config for that request only. Never mutate settings for ad-hoc queries.

### Live Progress (Reconnection)
```
GET /api/conversations/{id}/progress
→ {active, stage, execution_mode, progress: {stage1: {count, total}, stage2: {count, total}}, stage1, stage2, stage3, stage4}
→ {active: false} when no run is in progress
```
Frontend uses this to reconnect to in-progress runs when navigating back to a conversation. The progress data is held in-memory (`_active_runs` dict in `main.py`) and cleared when the streaming handler completes.

Advisor runs are also tracked in `_active_runs`: progress includes advisor round/order/completion state, partial rounds, tiebreaker/verdict phases, and returns `{active: false}` after completion.

### Council Debate (Multi-Round)
```
POST /api/conversations/{id}/message/debate
Body: {content, execution_mode?, council_models?, chairman_model?, web_search?, debate_rounds?, critique_mode?}
→ SSE stream (same events as /message/stream plus debate-specific events)
```

### Minimum Model Count
The minimum is 1 model (not 2). Single-model queries are valid for any execution mode.

## Cost Reporting

Every council, iterative debate, and advisor run should carry:
- Per-call `usage` and `cost` fields on model response objects when the provider returns usage.
- A run-level `metadata.cost_report` in stored conversations and stream completion events.
- A top-level `cost_report` from JSON endpoints and MCP tools.
- Cost reports expose `input_tokens`, `output_tokens`, `total_tokens`, calls, estimates/free/unknown buckets, and per-model/stage rows. Provider-reported reasoning tokens are preserved and billed as output when the provider reports them that way.

`backend/costs.py` is the single attribution path. It normalizes token usage from OpenAI-compatible, Anthropic, Google, and Ollama response formats, then prices calls in this order:
1. Provider-reported cost, currently OpenRouter `usage.cost` / `usage.total_cost`.
2. Known-free rules: `ollama:*`, `nvidia:*`, unprefixed or prefixed OpenRouter models ending in `:free`, the hardcoded `opencode-zen:*` set (any model whose name ends in `-free`, plus an explicit list), and custom endpoints whose `endpoint_url` contains `opencode.ai` (the official host). Note: a custom endpoint whose *name* (but not URL) contains "opencode" is NOT auto-free — it falls through to the catalog path with a `cost_status` of `estimated`.
3. OpenCode hardcoded pricing table (`_OPENCODE_PRICING` in `costs.py`) for paid OpenCode Go and Zen models. `pricing_source` is `table:opencode`; `cost_status` is `estimated`; Go entries are flagged with a `note` explaining the subscription model.
4. Cached pricing catalog estimate from `LLM_COUNCIL_PRICING_SOURCE_URL` (default `https://ai-model-pricing.com/api/v1/pricing.json`), falling back to `LLM_COUNCIL_LITELLM_PRICING_URL` (default LiteLLM `model_prices_and_context_window.json`). Provider-specific `source_url` overrides in `_PROVIDER_PRICING_URLS` win over the catalog's `entry.source_url` for direct providers (openai/anthropic/google/groq/mistral/deepseek/nvidia/openrouter) so the displayed link points at the vendor's own pricing page.
5. Unknown cost with token usage preserved when pricing is unavailable.

Catalog data is cached at `data/model_pricing_cache.json`; TTL is `LLM_COUNCIL_PRICING_CACHE_TTL_SECONDS` (default `86400`). Custom endpoints are only zero-cost when known-free; otherwise they use upstream model estimates when a catalog match exists and mark the cost as estimated.

## Advisors vs Council Fit

Use Council for direct answers, factual/creative prompts, and "give me the best response" synthesis. Use Advisors when the prompt has a real decision, tradeoff, risk review, prioritization, strategy, ethics, or disagreement. The Advisor prompts intentionally force positions, rebuttals, consensus scoring, and verdicts; simple prompts can drift into debates over criteria.

## Execution Modes

Three modes control deliberation depth (UI label → API enum):
- **Chat Only** (`chat_only`): Stage 1 only (quick responses)
- **Chat + Ranking** (`chat_ranking`): Stages 1 & 2 (peer review without synthesis)
- **Full Deliberation** (`full`): All 3 stages

**Two distinct defaults — do not confuse them:**
- The **global config default** (used by the stateful conversation flow, `/api/conversations/{id}/message[/stream]`) is `full`.
- The **per-request default** of the stateless `/api/ask` endpoint is `chat_only`, because that endpoint is designed for cheap one-shot queries.

If you change either default, update both this section and the `execution_mode` field defaults in `backend/main.py` (`SendMessageRequest`, `AskRequest`) plus the `/api/ask` request table in `skills/the-ai-counsel-api/SKILL.md`.

## Testing & Debugging

```bash
# Check Ollama models
curl http://localhost:11434/api/tags

# Test custom endpoint
curl https://your-endpoint.com/v1/models -H "Authorization: Bearer $API_KEY"

# View logs
# Watch terminal running backend/main.py
```

## Web Search

**Providers**: DuckDuckGo (free), Tavily (API), Brave (API), Serper (API), TinyFish (API). The canonical list of valid `search_provider` enum values is `duckduckgo`, `tavily`, `brave`, `serper`, `tinyfish` — also documented in `skills/the-ai-counsel-api/SKILL.md`. Add new providers in `backend/search.py` (`SearchProvider` enum) first.

**Full Content Fetching**: Jina Reader (`https://r.jina.ai/{url}`) extracts article text for top N results (configurable 0-10, default 3). Falls back to summary if fetch fails or yields <500 chars. 25-second timeout per article, 60-second total search budget.

**Search Query Processing**:
- **Direct** (default): Send exact query to search engine
- **YAKE**: Extract keywords first (useful for long prompts)

## Settings

**UI Sections** (sidebar navigation):
1. **General**: Display preferences (date format) and response language for council/advisor model outputs. Language is injected at runtime via `apply_response_language()` in `prompts.py` (not editable in system prompt tabs); title and search-query generation stay English.
2. **LLM API Keys**: OpenRouter, Groq, Ollama, Direct providers, Custom endpoint
3. **Council Config**: **Global** provider toggles — Local (Ollama) standalone, Remote APIs master toggle with OpenRouter, Groq, Custom, and Direct Connections underneath. Temperature controls for all three stages (Council Heat, Peer Ranking Heat, Chairman Heat). Model selection (members/chairman) is handled exclusively on the welcome screen via Council Setup.
4. **Council Debate Config**: Critique mode, debate rounds, auto-converge, convergence threshold
5. **Council System Prompts**: Stage 1 / Stage 2 / Stage 3 / Title / Search Query are user-editable and persisted in `settings.json` (fields `stage1_prompt` / `stage2_prompt` / `stage3_prompt` / `title_prompt` / `query_prompt`, all five updated via `PUT /api/settings`), each with reset-to-default. The Title and Query prompts (`TITLE_PROMPT_DEFAULT` / query-generation prompt in `backend/prompts.py`) are used internally by `generate_conversation_title` and `generate_search_query`.
6. **Advisor System Prompts**: Round 1, follow-up, cross-pollination, verdict, tiebreaker prompts
7. **Search Providers**: DuckDuckGo, Tavily, Brave, Serper, TinyFish + Jina full content settings
8. **Backup & Reset**: Import/Export config, reset to defaults

**Council presets** (`council_presets` in `settings.json`): Saved from welcome-screen Council Setup — members + chairman only. Max 20; one default auto-loads. Main screen and Settings edit the same `council_models` / `chairman_model` fields. Lineup locked in a conversation after the first message.

**Advisor presets** (`advisor_presets` in `settings.json`): Saved from Advisor Setup — personas, simple/advanced mode, model assignments, optional rounds/web search. Max 20; one default. See `skills/the-ai-counsel-api/SKILL.md`.

**Provider availability (important)**:
- `enabled_providers` and `direct_provider_toggles` are **global** — they control which providers appear in all model pickers: Council Setup (welcome screen), Advisor Setup, and Settings temperature controls.
- A provider must be both **configured** (API key set / Ollama connected) and **enabled** (toggle on) for its models to appear.
- By default, providers are enabled when their API key is first configured. Users can disable individual providers in Settings → Council Config.

**Documentation sync**: When changing API, settings fields, MCP tools, or user-facing flows, update all surfaces listed in [`docs/DOC-SYNC.md`](docs/DOC-SYNC.md) in the same PR.

**Auto-Save Behavior**:
- **Credentials auto-save**: API keys and URLs save immediately on successful test
- **All other settings auto-save**: Debounced (~1s) on change — council config, temperatures, prompts, search, debate, General (date format + response language). No Save button in Settings.
- UX flow: Test → Success → Auto-save → Clear input → "Settings saved!"

**Temperature Controls** (all in Settings → Council Config):
- Council Heat (Stage 1): Individual response creativity (default: 0.5)
- Peer Ranking Heat (Stage 2): Ranking consistency (default: 0.3)
- Chairman Heat (Stage 3): Final synthesis creativity (default: 0.4)

**Rate Limit Warnings**:
- Formula: `(council_members × 2) + 2` requests per council run
- OpenRouter free tier: 20 RPM, 50 requests/day
- Groq: 30 RPM, 14,400 requests/day

**Storage**: `data/settings.json`

## Design Principles

- **Graceful Degradation**: Single model failure doesn't block entire council
- **Transparency**: All raw outputs inspectable via tabs
- **De-anonymization**: Models receive "Response A/B/C", frontend displays real names
- **Progress Indicators**: "X/Y completed" during streaming
- **Provider Flexibility**: Mix cloud, local, and custom endpoints freely

## Code Safety Guidelines

**Communication:**
- NEVER make assumptions when requirements are vague - ask for clarification
- Provide options with pros/cons for different approaches
- Confirm understanding before significant changes

**Code Safety:**
- NEVER use placeholders like `// ...` in edits - this deletes code
- Always provide full content when writing/editing files
- FastAPI: Inject raw `Request` object to access `is_disconnected()`
- React: Use spread operators for immutable state updates (StrictMode runs effects twice)

## Versioning Checklist

When bumping the version, **all** of the following files must be updated together:

| File | Location of version |
|------|-------------------|
| `CHANGELOG.md` | `## [x.y.z]` header at top |
| `pyproject.toml` | `[project] version = "x.y.z"` |
| `frontend/package.json` | top-level `"version": "x.y.z"` |
| `frontend/package-lock.json` | root `"version"` and `packages[""].version` |
| `frontend/src/components/Sidebar.jsx` | `<div className="sidebar-version">vX.Y.Z</div>` |
| `skills/the-ai-counsel-api/SKILL.md` | YAML frontmatter `version: x.y.z` |

Always update all version surfaces in the same commit. The CHANGELOG drives the canonical version; backend metadata, frontend metadata, UI, and skill must match.

**Full documentation sync** (settings fields, MCP tools, advisor/council flows): follow [`docs/DOC-SYNC.md`](docs/DOC-SYNC.md).

**GitHub Releases:** For public version bumps, create an annotated `vX.Y.Z` tag and a GitHub Release from that tag. Release notes should come from the matching `CHANGELOG.md` section. See [`docs/RELEASE.md`](docs/RELEASE.md).

## Future Enhancements

- Model performance analytics over time
- Export conversations to markdown/PDF
- Custom ranking criteria (beyond accuracy/insight)
- Backend caching for repeated queries
- Multiple custom endpoints support
