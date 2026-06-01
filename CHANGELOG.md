# Changelog

All notable changes to The AI Counsel will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.8.0] - 2026-06-01

### Added

- **OpenCode Zen and OpenCode Go as direct providers** — Two new council model sources, addressing [opencode.ai](https://opencode.ai) without going through OpenRouter.
  - Prefixes: `opencode-zen:` (Zen dispatch) and `opencode-go:` (Go dispatch).
  - v1 scope: chat/completions only. The provider filters each product's `/v1/models` listing to chat-capable model families and drops non-`/chat/completions` endpoints (GPT Responses, Anthropic Messages, per-model Gemini). Multi-protocol support is a future release.
  - Single shared API key field. A user with only a Zen subscription, only a Go subscription, or both on the same key is supported. Go users can also use Zen's free models.
  - Settings → "LLM API Keys" has a new OpenCode subsection with a single "Test & Save" button that validates both products in one call (`POST /api/settings/test-opencode`).
  - `direct_provider_toggles` now defaults `opencode-zen` and `opencode-go` to `false` (Council-only; Advisor model pickers ignore these toggles, per AGENTS.md).
  - Cost attribution: hardcoded pricing table in `backend/costs.py` (`_OPENCODE_PRICING`, `_OPENCODE_FREE_MODELS`) reports `pricing_source: "table:opencode"` for paid models and `pricing_source: "free:opencode"` for the four known-free Zen models (big-pickle, deepseek-v4-flash-free, mimo-v2.5-free, nemotron-3-super-free). Go's published per-1M prices are surfaced with a "subscription" note and `cost_status: "estimated"`.
  - Council grid uses a new `opencode.svg` icon and a dedicated `#211E1E` (OpenCode brand grey) accent. Prefix detection is ordered before generic `gpt`/`claude` substring fallbacks in `councilGridUtils.js`.

- **Run cost reporting**: Council, iterative debate, advisor debate, REST, and MCP responses now include per-call usage/cost metadata plus a summarized `cost_report` by model and stage. The UI shows a compact run-cost panel with token totals, call counts, pricing confidence, and model breakdowns.
- **Pricing catalog integration**: Added cached pricing lookups from `ai-model-pricing.com` with LiteLLM pricing as fallback. Known-free Ollama, NVIDIA, OpenRouter `:free`, and OpenCode custom endpoints report `$0`.

## [0.7.0] - 2026-05-30

### Added

**Multi-Round Iterative Council Debate** — Contributed by **@manavgup** ([PR #11](https://github.com/jacob-bd/llm-council-plus/pull/11), building on his earlier iterative debate foundation):

- **Multi-Round Debate Orchestration**: Models debate across configurable rounds (1–5), refining answers based on peer feedback with convergence detection and early stopping.
- **Three Critique Modes**: "Free-form" (open-ended feedback), "Paragraph-level" (per-paragraph structured evaluation with stable `[Para N]` markers), and "Claim-level" (per-claim canonical extraction and verdict mapping).
- **Canonical Claim Extraction & Verification**: Chairman model decomposes responses into falsifiable claims; peer models evaluate each claim with color-coded verdicts (strong/weak/flawed). Includes JSON extraction and repair utilities for robust LLM structured output parsing.
- **Cross-Pollination**: Per-model personalized prompts — each model receives its own critiques plus top-rated claims from peers for adoption in subsequent rounds.
- **ClaimCards UI**: Expandable cards grouped by source model with per-evaluator verdicts, contested-first layout, and evolution timeline.
- **Stateful Interactive Round Selector**: `.round-navigator` in the frontend for clicking and navigating individual debate rounds retroactively.
- **Stage 4: Corrected Draft**: Post-debate rewriting stage where the chairman synthesizes the final corrected draft, highlighting `[REVISED]` or `[NEW]` components.
- **Debate Settings UI**: Critique mode radio buttons with cost hints, round count configuration, convergence settings, and dedicated config section.
- **20 New Tests**: Backend test suites for paragraph mode, claim aggregation, cross-pollination, JSON repair, and multi-round debate orchestration.

**Other additions:**

- **Debate MCP Tools Integration**: Added new `run_iterative_debate` tool (10 MCP tools total) and updated `council_settings` to support critique modes and debate rounds configuration.
- **Live Progress Endpoint**: `GET /api/conversations/{id}/progress` returns real-time progress for active streaming runs (council or debate), including current stage, model counts, and partial responses. Frontend auto-reconnects to in-progress runs when navigating back to a conversation.
- **Custom Endpoint Disconnect**: Settings now includes a "Disconnect" button to clear custom OpenAI-compatible endpoint configuration and disable the provider in one action.

### Changed
- **Chairman Card UX**: Chairman card now always displays the provider logo, model name, and provider label regardless of thinking state. A spinning ring overlay and hourglass badge indicate active processing without replacing the identity information.
- **UTC Timestamps**: Conversation `created_at` timestamps now use timezone-aware `datetime.now(timezone.utc)` instead of naive `utcnow()` with manual `"Z"` suffix.
- **Progress Polling Safety**: Frontend stops progress polling before starting new SSE streams (council or debate) to prevent competing state updates on the same conversation.

## [0.6.1] - 2026-05-30

### Added
- **Stage 2 Deliberation Heatmap Matrix** (Ported from PR #179 by @UmaimaKhan01): Added a premium, glassmorphic $N \times N$ matrix detailing anonymous peer evaluation grades ( emerald green 1st, soft amber 2nd, modern crimson 3rd, ruby 4th+).
- **Segmented UI View Toggle**: Fully responsive segmented tab switcher (`🏆 Leaderboard` vs `📊 Detail Matrix`) to prevent page clutter and let users swap details dynamically.
- **Auto-Threshold Toggle Control**: Hides the Detail Matrix toggle on low-model runs (less than 3 models) where peer matrices are logically inapplicable, ensuring zero UI clutter.

### Fixed
- **Clean Lazy Creation State Refactor**: Replaced legacy empty file initialization drafts with a pure client-side lazily created draft state (`'draft'`), completely eliminating orphaned JSON file clutter on user disks.
- **Heatmap Score Math Alignment**: Aligned the matrix average scoring calculations exactly with backend leaderboard logic, resolving a visual desync between aggregate scores.
- **Rebuilt Index Mode Desync**: Hardened index indexing logic in the storage layers to read accurate conversation tags (`mode`), correcting mismatched ADV/CNC sidebar badge allocations on legacy items.

## [0.6.0] - 2026-05-28

### Added
- **API Key & Model Count Feedback**: Settings panel now queries and displays model counts (e.g. `✓ API key configured · 44 models available`) for OpenRouter, Groq, direct providers, and Ollama in real-time.

### Fixed
- **CORS LAN Access**: Expanded dev CORS regex to allow local network IP connections (e.g., `192.168.x.x`), resolving blank screen settings page loading issues when accessed remotely.
- **Auto-Scrolling in Chat**: Fixed chat scroll positioning during active response generation to instantly scroll to bottom.
- **Conversation Title Overwrite**: Fixed a race condition where council-mode conversation titles were overwritten back to `"New Conversation"` during final assistant message save.
- **Chairman Display Mode Logic**: Fixed the Chairman card showing up in the UI for messages executed in `chat_only` mode by linking the grid layout to the message's specific metadata execution mode rather than the current UI state.

## [0.5.2] - 2026-05-27

### Added
- **Inline council setup**: Edit council members and chairman on the welcome screen (landing + empty conversation) with auto-save, compact member list (+ Add up to 8), live grid preview, and **council presets** (members + chairman only; default auto-loads).
- **Interactive Council Grid**: Introduced `EditableCouncilGrid` supporting inline slot editing, adding member models up to 8, and quick-swapping models directly on the landing screen.
- **Advisor model presets**: Save and load named advisor setups (selected personas, Simple/Advanced model assignment, optional rounds and web search) from the Model Assignment section in Advisor Setup. Presets persist in `settings.json` via `advisor_presets`.
- **Documentation sync checklist**: [`docs/DOC-SYNC.md`](docs/DOC-SYNC.md) — required file matrix for keeping REST API, MCP tools, skill, and user docs aligned on every change.
- **MCP preset CRUD**: `council_settings` and `advisor_settings` now support `list_presets`, `save_preset`, `delete_preset`, and `set_default_preset` actions.
- **Presets & parsing unit tests**: Added comprehensive backend test suites (`test_advisor_presets.py`, `test_council_presets.py`, `test_ranking_parse.py`) and updated MCP integration tests to verify consolidated 9-tool behavior.

### Changed
- **MCP tool consolidation (breaking)**: Replaced 25 single-purpose MCP tools with **9 action-based tools** — `council_deliberate`, `model_chat`, `advisor_debate`, `council_settings`, `advisor_settings`, `personas`, `conversations`, `providers`, `config_backup`. Legacy names (`run_deliberation`, `get_council_config`, `check_health`, etc.) removed.
- **MCP-first agent routing**: Skill and MCP server instructions tell agents to prefer MCP tools over curl when both are available; REST documented as fallback (`skills/the-ai-counsel-api/SKILL.md`, `the_ai_counsel_mcp/server.py`, `docs/mcp/INSTRUCTIONS.md`, `docs/mcp/TOOLS.md`).
- **Advisor model sources decoupled from Council toggles**: Advisor Setup model pickers list all **configured** providers (API keys, Ollama URL, custom endpoint). Settings → Council Config `enabled_providers` toggles apply to **LLM Council only**.
- **Council Config copy**: Clarifies provider toggles are council-only; advisors always use configured providers from LLM API Keys.
- **New Council navigation**: Sidebar **+ New Council** from advisors mode now switches to council mode (previously stayed on advisor UI).
- **Chairman validation**: Chairman required only for **Full Deliberation**; Chat Only and Chat + Ranking no longer block send without a chairman.
- **Stream API**: Frontend sends `council_models` / `chairman_model` on message stream so the run matches the on-screen lineup.
- **MCP docs sync**: All docs and `skills/the-ai-counsel-api/SKILL.md` updated for **9-tool** MCP catalog; `/api/health` reports `tools: 9`.

### Fixed
- **Stage 2 peer ranking parsing**: Hardened text parser to validate that parsed rankings only include labels actually presented in the prompt, preventing models from hallucinating non-existent labels.
- **Model labeling fixes**: Fixed a bug where anonymous models were incorrectly mapped/labeled during Stage 2 aggregation.
- **Production build crash**: Fixed circular dependency initialization crash in the production bundle by removing rollup `manualChunks`.
- **Direct installation layout lockups**: Standardized `--prefix frontend` usage for all install instructions to avoid nested directory lockups when switching between environments.

### Removed
- **25 legacy MCP tools** — see migration table in `docs/mcp/INSTRUCTIONS.md`.

## [0.5.1] - 2026-05-24

### Added
- **Start a New Council Session Button**: Prominent glowing turquoise CTA button placed cleanly below the Council grid row on the home dashboard (only in Council mode), allowing users to easily launch new deliberation sessions.
- **Single-Port MCP SSE Integration**: FastMCP server is now mounted directly onto the main FastAPI web server at `/mcp` on port `8001`. This allows zero-install remote connection via a single port (SSE session endpoint at `/mcp/sse` and JSON-RPC message endpoint at `/mcp/messages`).
- **MCP Auto-Discovery**: The `/api/health` endpoint now includes an `mcp` metadata block advertising the active SSE URL and tool count to help agents auto-register the server.

### Changed
- **Removed Port 8002**: Removed all references, environment variables, mappings, and background process commands for port `8002` since both the REST API and MCP server run on port `8001`.
- **Streamlined Documentation**: Rewrote all 5 MCP docs, `README.md`, and `AGENTS.md` to reflect the single-port architecture.

## [0.5.0] - 2026-05-24

### Added
- **LLM Advisors mode**: Entirely new persona-driven debate system where named advisor personas argue your question across configurable rounds, reaching consensus or voting to deliver a structured verdict with action plan
- **10 built-in advisor personas**: The Skeptic, The Pragmatist, The Innovator, The Historian, The Ethicist, The Data Analyst, The Contrarian, The Strategist, The Humanist, and The Risk Assessor — each with unique system prompts, roles, emoji avatars, and color-coded identities
- **Persona customization**: Edit any persona's name, role, description, system prompt, and avatar emoji — overrides persist to `data/persona_overrides.json` with per-persona reset to defaults
- **Debate orchestration** (`backend/advisors.py`): Multi-round debate engine with rotating speaking order, consensus detection via `CONSENSUS:YES/NO` tags, automatic early termination on agreement, and tiebreaker invocation when advisors remain split
- **Structured verdict system**: Neutral analyst synthesizes debate transcript into Summary, Consensus Points, Disagreements table, Verdict, Recommended Next Steps, and Open Uncertainties
- **NVIDIA NIM provider** (`backend/providers/nvidia.py`): Native support for NVIDIA Build (NIM) models at `integrate.api.nvidia.com/v1` with `nvidia:` prefix routing, API key management, and model listing
- **Landing page** (`LandingPage.jsx`, `LandingPage.css`): New dual-mode entry screen with animated glass cards for "Enter Council" and "Start Advisory Session", custom SVG icons, gradient orbs, and grid background
- **Advisor Setup UI** (`AdvisorSetup.jsx`, `AdvisorSetup.css`): Full configuration panel with question input, model selection via `SearchableModelSelect`, round count slider, web search toggle, persona selection grid with inline editing, and glassmorphic styling
- **Debate View UI** (`DebateView.jsx`, `DebateView.css`): Live debate display with per-round sections, persona-colored response cards, consensus banners, tiebreaker section, verdict panel with copy-to-clipboard, and streaming progress indicators
- **Advisor Grid** (`AdvisorGrid.jsx`, `AdvisorGrid.css`): Visual grid showing active debate participants with round progress and active-speaker highlighting
- **Advisor API endpoints**: `POST /api/advisor/debate/stream` (SSE streaming debate), `GET /api/personas` (list all personas), `PATCH /api/personas/{id}` (save overrides), `DELETE /api/personas/{id}/override` (reset to default)
- **Advisor conversation persistence**: `add_advisor_message()` in storage saves full debate transcripts (rounds, verdict, tiebreaker, persona IDs) alongside existing council conversations
- **Advisor settings**: `advisor_default_model` and `advisor_default_rounds` fields in settings with validation (1–10 rounds, 2–4 advisors per debate)
- **NVIDIA SVG icon** (`frontend/src/assets/icons/nvidia.svg`) with provider detection in `CouncilGrid.jsx`
- **Complete MCP documentation rewrite** (`docs/mcp/TOOLS.md`): Exposes all **25 tools** across 5 categories, with full parameter listings and JSON output examples (including 11 new tools previously missing from docs)
- **Advisor MCP examples** (`docs/mcp/EXAMPLES.md`): Added 3 comprehensive walkthrough examples covering running advisor debates, customizing/resetting personas via tools, and configuring global advisor preferences
- **Quickstart Advisor Integration** (`docs/QUICKSTART.md`): Added complete walkthroughs for configuring and running the first Advisor debate, custom personas tips, and mode comparison matrix

### Changed
- **App architecture**: `App.jsx` refactored to support dual-mode routing — landing page → council mode or advisors mode, with independent state management for each
- **Sidebar**: Updated to show mode-aware conversation list with Home button navigation back to landing page
- **`SearchableModelSelect`**: Now normalizes dashes to spaces during search so NVIDIA model names (e.g., `nvidia/llama-3.1-nemotron-ultra-253b-v1`) match correctly
- **CouncilGrid provider detection**: NVIDIA prefix (`nvidia:`) added to provider icon lookup chain
- **Settings UI**: NVIDIA API key section added to Provider Settings with test/save flow
- **`ChatInterface`**: Extended to support both council and advisor question submission flows
- **`the-ai-counsel-api` skill updated to v0.5.0**: Documents advisor endpoints, persona API, NVIDIA provider, and dual-mode architecture
- **Main README expanded**: Updated MCP Server details to cover dual-mode capability (Council + Advisors) and all 25 tools
- **Skill Reference expanded** (`skills/the-ai-counsel-api/SKILL.md`): Added extensive examples for custom OpenAI endpoint configuration (OpenCode Zen), hybrid local/cloud council setups, and per-persona model assignment walkthroughs

### Removed
- **Outdated binary assets**: Cleaned up stale PNG screenshots (`header.png`, `landing_page.png`, `debate_page.png`) from repository root
- **Git status noise**: Added `.antigravitycli/` config directories to `.gitignore`

## [0.4.2] - 2026-05-15

### Added
- **AGENTS.md canonical agent guide**: Single source of truth for AI agents (Claude Code, Codex, Gemini CLI) working in this repository — replaces scattered instructions across CLAUDE.md and GEMINI.md
- **Admin endpoint security** (PR #9): `/api/settings/export`, `/api/settings/import`, and `/api/settings/reset` now require `LLM_COUNCIL_ADMIN_TOKEN` when accessed by remote or proxied clients. Direct loopback clients are still allowed without a token. Thanks @jonathanzhan1975!

### Changed
- **Jina Reader fetch hardening** (PR #9): Stricter URL validation before fetching full article content via Jina Reader. Thanks @jonathanzhan1975!
- **Docker entrypoint escaping** (PR #9): Config values injected into `config.js` are now properly escaped to prevent shell injection. Thanks @jonathanzhan1975!
- **Docs reconciliation** (PR #10): CLAUDE.md slimmed to a pointer at AGENTS.md; stale GEMINI.md archived to `docs/archive/`. Thanks @jonathanzhan1975!
- **Admin security variables documented**: `LLM_COUNCIL_ADMIN_TOKEN` usage added to AGENTS.md and `docs/DOCKER.md`
- **Custom endpoint error messages improved**: Timeout and connection errors now display actionable messages (e.g., "Request timed out after 120s") instead of "Unknown error"

## [0.4.1] - 2026-05-10

### Added
- **`POST /api/ask` one-shot endpoint**: Single call, no conversation state, returns JSON directly. Accepts `models`, `chairman_model`, `web_search`, and `execution_mode`. Ideal for scripts and MCP agents.
- **`POST /api/conversations/{id}/message` sync endpoint**: Non-streaming JSON alternative to SSE. Saves to conversation history without requiring event stream parsing.
- **Per-request model overrides**: `council_models` and `chairman_model` fields on both streaming and sync message endpoints. Never mutates global config for ad-hoc queries.
- **`PipelineResult` dataclass**: Shared orchestration helper (`_run_council_pipeline`) eliminates duplicated stage1/2/3 collection logic across sync endpoints.
- **Multi-turn conversation memory**: Conversation endpoints pass full prior chat history to models. Follow-up questions carry context automatically.
- **MCP `chat` tool**: Multi-turn equivalent of `quick_chat` — pass `conversation_id` to continue a conversation with memory. (14 tools total)
- **UI: single-model council support**: Council members can now be reduced to 1 in the Settings UI (was minimum 2).
- **UI: chairman auto-disables**: Chairman section dims and becomes non-interactive when execution mode is not "Full Deliberation".

### Changed
- **Minimum council models reduced to 1**: Single-model queries are now valid for any execution mode (was 2 minimum).
- **`execution_mode` uses `Literal` type**: Pydantic rejects invalid values at parse time instead of runtime checks in each handler.
- **Settings cache**: `get_settings()` now uses mtime-based caching — repeated calls within the same request return the cached instance instead of re-reading disk (eliminates 5-10 redundant file reads per deliberation).
- **Storage I/O reduced**: `add_user_message()` and `add_assistant_message()` accept pre-loaded `conversation` kwarg, avoiding redundant reads after 404 checks.
- **Web search setup deduplicated**: Shared `_apply_search_env()` and `_fetch_search_context()` helpers replace 3 copy-pasted blocks (also fixes missing Serper env var in sync/oneshot paths).
- **Dead import removed**: `from .search import perform_web_search, SearchProvider` removed from `council.py` (unused there).
- **MCP `quick_chat` uses `/api/ask`**: No more save/restore of global settings — calls one-shot endpoint directly.
- **MCP `run_deliberation` uses per-request overrides**: Passes `council_models` in stream body instead of mutating settings with try/finally restore.
- **MCP client `ask()` method added**: `CouncilClient.ask()` wraps `POST /api/ask` for one-shot queries.
- **MCP client `stream_message` accepts overrides**: `council_models` and `chairman_model` params added to avoid settings mutation.
- **`the-ai-counsel-api` skill updated to v0.4.1**: Documents `/api/ask`, per-request overrides, sync endpoint, multi-turn conversations, SSE event table, and "Choosing the Right Endpoint" decision matrix.
- **`DEFAULT_EXECUTION_MODE` constant**: Extracted shared default (`'full'`) to `api.js` — eliminates magic string duplication across `App.jsx`, `Settings.jsx`, `CouncilConfig.jsx`.
- **`.subsection--disabled` CSS class**: Replaces inline opacity/pointer-events with reusable class (consistent with `.source-disabled`).
- **Chairman `SearchableModelSelect` respects disabled state**: `isDisabled` prop wired so keyboard users cannot change chairman when irrelevant.

## [0.4.0] - 2026-05-10

### Added
- **Settings export/import/reset endpoints**: `GET /api/settings/export` returns a full settings backup including actual API key values; `POST /api/settings/import` restores from a backup blob; `POST /api/settings/reset` wipes all settings to factory defaults
- **4 new MCP tools** (17 total): `set_api_key` — set any provider API key by name; `export_config` — backup full config as JSON; `import_config` — restore config from JSON string; `reset_config` — factory reset
- **Extended `configure_council` MCP tool**: now accepts `stage1_prompt`, `stage2_prompt`, `stage3_prompt`, `enabled_providers`, and `direct_provider_toggles` in addition to existing parameters
- **Sidebar delete button always visible**: trash icon now shows at 40% opacity on all conversations (was hover-only), brightens to full on hover
- **18 new tests**: backend export/import/reset endpoint tests, MCP tool tests for all new tools, and client method tests (108 total, up from 90)

### Changed
- **`the-ai-counsel-api` skill updated to v0.4.0**: documents system prompt fields, `enabled_providers`/`direct_provider_toggles` dict formats, all API key field names, and backup/restore endpoints
- **`import_settings` endpoint simplified**: uses Pydantic body parsing (`Settings` model) instead of manual JSON parsing — FastAPI now returns field-level 422 validation errors instead of generic 400s
- **`export_settings` endpoint**: uses `model_dump_json()` (single-pass) instead of `model_dump()` + `json.dumps()` (two-pass)

## [0.3.0] - 2026-05-10

### Added
- **MCP server** (`the_ai_counsel_mcp/`): Expose The AI Counsel as a Model Context Protocol server, letting Claude Code, Gemini CLI, and other MCP clients send questions to the council and retrieve deliberation results programmatically
- **13 MCP tools**: `list_models`, `get_council_config`, `configure_council`, `set_search_provider`, `run_stage1`, `run_stage2`, `run_stage3`, `run_deliberation`, `quick_chat`, `list_conversations`, `get_conversation`, `check_health`, `test_provider`
- **stdio transport** (default): MCP server runs as a local process; AI tools communicate via stdin/stdout with outbound HTTP to the Council backend (local or remote)
- **SSE transport**: MCP server runs as an HTTP server on port 8002; AI tools connect via URL with no local installation required
- **TinyFish search provider**: 5th web search option using TinyFish's free-tier Fetch API (5 req/min); requires free API key from agent.tinyfish.ai
- **90 tests**: backend TinyFish provider tests, MCP integration tests covering all 13 tools and both transport modes
- **`docs/mcp/`**: Comprehensive MCP documentation including transport selection guide, step-by-step setup for stdio and SSE, full tools reference, and real-world usage examples
- **`the-ai-counsel-api` Claude Code skill** (`skills/the-ai-counsel-api/SKILL.md`, v0.3.0): Installable skill for interacting with the Council via REST API without MCP — covers all endpoints, SSE parsing, error handling, and troubleshooting

## [0.2.3] - 2026-05-04

### Added
- **Docker support** (PR #5): Single-container deployment via `docker compose up -d --build` serving both frontend and API on port 8001. Thanks @kcelsi!
- **Docker healthcheck**: Backend liveness polling via `/api/health` every 30s with automatic restart on failure
- **Non-root container user**: Container now runs as `appuser` for reduced attack surface
- **`docs/` directory**: New structured documentation folder
- **`docs/DOCKER.md`**: Comprehensive Docker deployment guide covering environment variables, persistent storage, Ollama integration, reverse proxy setup (nginx/Caddy with SSE notes), upgrades, and troubleshooting

### Changed
- **CORS hardening**: Dev-ports regex (`5173|5174|3000`) is now suppressed when the built frontend is present (Docker/production mode) — same-origin deployments no longer expose API to external dev-port origins
- **Root cleanup**: Removed stub `main.py`; moved `QUICKSTART.md` and `TEST_PLAN_SEARCH.md` into `docs/`
- **README**: Docker section condensed to quick-start + link to `docs/DOCKER.md`; stale CORS description updated

## [0.2.2] - 2026-02-18

### Fixed
- **Ollama Configuration**: Fixed an issue where the "Local (Ollama)" toggle was disabled even when Ollama was connected (PR #4). Thanks @patrickgamer!

## [0.2.1] - 2026-01-31

### Added
- **Serper.dev Integration**: Google Search via Serper API with 2,500 free queries
- **DuckDuckGo Search Optimization**: Intelligent query processing with intent detection, hybrid web+news search, and relevance reranking
- **Search Settings**: Configurable result count (5-15) and hybrid mode toggle for DuckDuckGo
- **Query Intent Detection**: Automatically detects current events, factual, comparison, and research queries
- **Auto-save Council Config**: Council members and chairman selections now auto-save (no more forgetting to click Save)
- **Council Validation**: Prevent saving incomplete configurations (empty member slots or missing chairman)

### Changed
- **Improved Font Readability**: Switched markdown headers and model names from stylized 'Syne' to readable 'Plus Jakarta Sans'
- **Search Query Processing**: DuckDuckGo now automatically removes conversational fluff and adds temporal context
- **Search Provider Auto-switch**: Testing a search API key now auto-saves and switches to that provider

### Fixed
- YAKE keyword extraction setting now only shows for Tavily/Brave (DuckDuckGo has built-in optimization)
- Font inconsistency between Stage 3 (Chairman) and Stage 1/2 responses
- CORS support for additional frontend port (5174)

## [0.2.0] - 2026-01-31

### Added
- **Mobile Responsiveness**: Full mobile support with hamburger menu, responsive layouts, and touch-friendly UI
- **Chat History Search**: Filter conversations by title in the sidebar
- **Source Validation**: Disable model source toggles when API key not configured with helpful tooltips
- **Version Display**: Show version number in sidebar and settings

### Changed
- **UI Redesign**: New "Council Chamber" dark theme with refined glassmorphism
- **Typography**: Updated font stack (Syne, Plus Jakarta Sans, Source Serif 4, JetBrains Mono)
- **Hero Animations**: Staggered fade-in animations for welcome screen elements

### Fixed
- Auto-cleanup of empty conversations when switching or creating new ones
- Duplicate API route in backend
- Duplicate CSS blocks causing style conflicts
- React key anti-pattern in message list
- Redundant decorator in provider base class

## [0.1.0] - Initial Release

### Added
- 3-stage deliberation system (Individual Responses → Peer Ranking → Chairman Synthesis)
- Multi-provider support: OpenRouter, Ollama, Groq, Direct providers, Custom endpoints
- Web search integration: DuckDuckGo, Tavily, Brave with Jina Reader
- Execution modes: Chat Only, Chat + Ranking, Full Deliberation
- Conversation persistence with JSON storage
- Settings management with import/export
- "I'm Feeling Lucky" random model selection
