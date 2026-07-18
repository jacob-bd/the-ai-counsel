# Documentation Sync Checklist

When you change The AI Counsel behavior, **update every surface in the same PR** (or same release commit). Do not ship code without syncing docs.

Canonical API reference: [`skills/the-ai-counsel-api/SKILL.md`](../skills/the-ai-counsel-api/SKILL.md)

---

## Always update (versioned releases)

When bumping version, update **all three together** (see `AGENTS.md` → Versioning Checklist):

| File | What to update |
|------|----------------|
| `CHANGELOG.md` | `## [x.y.z]` or `## [Unreleased]` entries |
| `pyproject.toml` | `[project] version` |
| `frontend/package.json` | top-level `version` |
| `frontend/package-lock.json` | root `version` and `packages[""].version` |
| `frontend/src/components/Sidebar.jsx` | `sidebar-version` |
| `skills/the-ai-counsel-api/SKILL.md` | YAML frontmatter `version:` |

---

## Per change type — file matrix

### Settings / API fields (`backend/settings.py`, `PUT /api/settings`, `GET /api/settings`)

| File | Action |
|------|--------|
| `skills/the-ai-counsel-api/SKILL.md` | Field table, curl examples, GET response keys |
| `docs/mcp/TOOLS.md` | MCP tools (`council_settings`, `council_deliberate`, etc.) |
| `docs/mcp/EXAMPLES.md` | Example payloads if behavior changes |
| `AGENTS.md` | Settings UI section, storage notes |
| `README.md` | Configuration / first-time setup if user-facing |
| `docs/QUICKSTART.md` | Setup steps |
| `docs/CREDENTIALS.md` | Secret storage, Disconnect, relay-ai import, file↔keychain |
| `the_ai_counsel_mcp/tools/*.py` | Tool descriptions + returned JSON shape |
| `the_ai_counsel_mcp/tests/test_tools_*.py` | Assertions on new fields |
| `CHANGELOG.md` | Added/changed/fixed |

### Credentials / OAuth / relay-ai import

| File | Action |
|------|--------|
| `docs/CREDENTIALS.md` | User-facing source of truth for storage modes and import/migrate |
| `skills/the-ai-counsel-api/SKILL.md` | REST credential endpoints, Retest/store rules, disconnect-all |
| `docs/DOCKER.md` / `docs/MIGRATION.md` | `credentials.json` vs `settings.json` |
| `AGENTS.md` | Settings section 2 (LLM API Keys) + Backup Disconnect All |
| `CHANGELOG.md` | |

### General settings / response language

| File | Action |
|------|--------|
| `backend/prompts.py` | `VALID_RESPONSE_LANGUAGES`, `apply_response_language()` — injected before council/advisor/debate prompts; title/search query stay English |
| `backend/settings.py` | `response_language` field; invalid values fall back to English on load/import |
| `frontend/src/components/settings/GeneralSettings.jsx` | Date format, response language, relay-ai import (Settings → General) |
| `skills/the-ai-counsel-api/SKILL.md` | GET keys `response_language`, `valid_response_languages`, `response_language_default` |
| `AGENTS.md` | 8-section Settings list; General first; auto-save behavior |
| `CHANGELOG.md` | User-facing General section and language list |

### Council behavior (members, chairman, streaming, execution modes)

| File | Action |
|------|--------|
| `skills/the-ai-counsel-api/SKILL.md` | Council endpoints, overrides, `council_models` / `chairman_model` |
| `docs/mcp/TOOLS.md` | `council_settings`, `council_deliberate`, health via `providers` |
| `AGENTS.md` | Architecture, execution modes, frontend components |
| `README.md` | Council overview if flow changes |
| `CHANGELOG.md` | |

### Advisor behavior (debates, personas, presets, model pickers)

| File | Action |
|------|--------|
| `skills/the-ai-counsel-api/SKILL.md` | Debate stream, advisor settings, `advisor_presets` |
| `docs/mcp/TOOLS.md` | `advisor_debate`, `advisor_settings`, `personas` |
| `docs/mcp/EXAMPLES.md` | Advisor walkthroughs |
| `docs/QUICKSTART.md` | Advisor setup path |
| `AGENTS.md` | Advisor modules, UI components |
| `the_ai_counsel_mcp/tools/advisors.py` | Tool descriptions + `advisor_settings` payload |
| `CHANGELOG.md` | |

### Provider / model routing (new prefix, NVIDIA, Ollama, etc.)

| File | Action |
|------|--------|
| `skills/the-ai-counsel-api/SKILL.md` | Model ID prefix table |
| `AGENTS.md` | Provider icons, prefix order (only if table lives there — prefer SKILL.md) |
| `README.md` | Provider list in config |
| `CHANGELOG.md` | |

### Frontend UX only (no API change)

| File | Action |
|------|--------|
| `AGENTS.md` | Component table, user flows |
| `README.md` | Screenshots / setup prose if misleading |
| `docs/QUICKSTART.md` | Step-by-step |
| `CHANGELOG.md` | |

### Sidebar index fields (`run_summary`, conversation cost)

| File | Action |
|------|--------|
| `backend/storage.py` | `derive_run_summary`, `derive_conversation_cost`, `_build_index_entry`, index field shape |
| `backend/main.py` | `ConversationMetadata` must include all index fields (`run_summary`, `total_cost`, `cost_status`, `total_calls`); assistant metadata that feeds summaries |
| `frontend/src/components/Sidebar.jsx` | Render stacked date/time, `conv.run_summary`, and cost pill; sidebar search includes summary text |
| `frontend/src/utils/dateFormat.js` | `formatDatePart` / `formatTimePart` for sidebar timestamp layout (respects `date_format` setting) |
| `frontend/src/utils/formatCost.js` | Shared USD formatting for sidebar pill and `CostReport.jsx` |
| `frontend/src/constants/critiqueMode.js` | Compact critique labels — keep in sync with `CRITIQUE_MODE_LABELS` in `backend/storage.py` |
| `backend/tests/test_run_summary.py` | Summary string contract |
| `backend/tests/test_conversation_cost.py` | Cumulative cost index contract |
| `CHANGELOG.md` | User-facing sidebar behavior |

Rules:
- Summary appears only after title is assigned (not while title is `"New Conversation"`).
- Cost appears once any assistant message has `metadata.cost_report` (includes follow-up totals).
- Server builds index fields; frontend displays index data only.
- Existing conversations need a save or `rebuild_index()` to backfill index entries (`run_summary` and cost fields).
- Sidebar shows date on one line and time on the next; do not collapse back to a single timestamp string without updating `Sidebar.jsx` and this checklist.

### MCP-only (new/changed tools)

| File | Action |
|------|--------|
| `docs/mcp/TOOLS.md` | Full tool entry (params, examples) |
| `docs/mcp/INSTRUCTIONS.md` | Agent routing rules (mirror `the_ai_counsel_mcp/server.py`) |
| `the_ai_counsel_mcp/server.py` | MCP `instructions=` string — prefer tools over curl |
| `docs/mcp/README.md` | Tool count (`10`); `GET /api/health` → `mcp.tools` when total changes |
| `docs/mcp/EXAMPLES.md` | New workflows |
| `skills/the-ai-counsel-api/SKILL.md` | MCP-first routing + REST fallback table |
| `the_ai_counsel_mcp/tests/` | Tool tests |
| `CHANGELOG.md` | |

---

## Product rules (keep docs aligned)

Document these consistently everywhere they appear:

### Provider availability

| Surface | Model sources |
|---------|----------------|
| **All UI pickers** (Council Setup, Advisor Setup) | `enabled_providers` + `direct_provider_toggles` filter which sources appear — **global**, applies to both Council and Advisors |
| **MCP / REST** | Use `GET /api/models`, `/api/models/direct`, `/api/ollama/tags`, `/api/custom-endpoint/models` — availability depends on credentials, not UI toggles |

### Settings vs main screen (planned / shipped)

| Data | Council main screen | Settings |
|------|---------------------|----------|
| `council_models`, `chairman_model` | Editable on welcome (Council Setup) only; locked in conversation after first message |
| `council_presets` | Welcome Council Setup UI + `PUT /api/settings` |
| `advisor_presets` | Advisor Setup UI + `PUT /api/settings` |
| Temperatures, prompts, provider toggles | Settings only |
| Lineup locked after first council message | Yes (v1) |

### Advisor presets (`advisor_presets`)

- Max 20 presets; one `is_default`
- Saves: personas, `mode` (simple/advanced), models, optional rounds + web search
- Does **not** save debate question text
- REST: `GET/PUT /api/settings` field `advisor_presets`
- MCP: `advisor_settings` action `get` returns presets; preset CRUD via `advisor_settings` preset actions (REST fallback: `PUT /api/settings`)

---

## Shipped in v0.11.0 (credentials / OAuth)

- [x] Credential store (`credentials.json` / OS keystore `the-ai-counsel`) — `docs/CREDENTIALS.md`, SKILL Credentials section, README/DOCKER/QUICKSTART/MIGRATION
- [x] Subscription OAuth + Copilot plan filtering — SKILL prefixes, CHANGELOG, Settings UI
- [x] relay-ai import (General) + Disconnect All (Backup & Reset) — SKILL REST table, CREDENTIALS.md
- [x] Retest / Disconnect env-override behavior — SKILL + CREDENTIALS.md

## Shipped in v0.5.2 (sync verified)

- [x] **MCP 10-tool consolidation** — `the_ai_counsel_mcp/tools/*.py`, `server.py`, `docs/mcp/TOOLS.md`, `INSTRUCTIONS.md`, SKILL routing table
- [x] **MCP-first routing** — SKILL MCP-first section, `server.py` instructions, `docs/mcp/INSTRUCTIONS.md`
- [x] **Inline council setup** — `CouncilSetup.jsx`, `council_presets`, auto-save, chairman optional in Chat Only
- [x] `advisor_presets` — backend, UI, SKILL §18, CHANGELOG, MCP `advisor_settings`
- [x] Advisors use configured providers (not council toggles) — SKILL, AGENTS, QUICKSTART, README, MCP TOOLS/EXAMPLES
- [x] Council Config toggles labeled council-only — UI copy + docs
- [x] `+ New Council` switches to council mode from advisors — CHANGELOG, AGENTS
- [x] `docs/DOC-SYNC.md` checklist — linked from README, AGENTS
- [x] MCP tests for 10-tool API (139 tests)
- [x] Migration guide (`docs/MIGRATION.md`) — linked from README and DOCKER.md

---

## PR self-check

Before merge, confirm:

- [ ] `CHANGELOG.md` `[Unreleased]` updated
- [ ] `skills/the-ai-counsel-api/SKILL.md` field tables and examples match `backend/settings.py`
- [ ] `docs/mcp/TOOLS.md` matches `the_ai_counsel_mcp/tools/*.py` signatures
- [ ] `AGENTS.md` reflects current UI flows (no stale “Settings only” for advisors)
- [ ] MCP tool JSON examples include new settings fields
- [ ] Tests updated for MCP GET settings shape
