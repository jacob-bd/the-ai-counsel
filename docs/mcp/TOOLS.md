# MCP Tools Reference

The The AI Counsel MCP server exposes **10 action-based tools**. Each tool groups related operations behind an `action` parameter. Your AI assistant picks the tool and action from what you ask — you rarely need to name them directly.

**Breaking change (v0.5.2):** The previous 25 single-purpose tools were replaced by 9 consolidated tools. Old tool names (`run_deliberation`, `get_council_config`, `check_health`, etc.) no longer exist. **v0.7.0** added `run_iterative_debate` as the 10th tool.

---

## Tool Map

| Tool | Actions | Purpose |
|------|---------|---------|
| [`council_deliberate`](#council_deliberate) | `stage1`, `stage2`, `stage3`, `full` | Run council deliberation stages |
| [`model_chat`](#model_chat) | `quick`, `multi_turn` | Single-model chat (stateless or threaded) |
| [`advisor_debate`](#advisor_debate) | _(none — direct params)_ | Multi-round persona debate |
| [`run_iterative_debate`](#run_iterative_debate) | _(none — direct params)_ | Multi-round council debate with critique modes |
| [`council_settings`](#council_settings) | `get`, `update`, `list_presets`, `save_preset`, `delete_preset`, `set_default_preset` | Council config + presets |
| [`advisor_settings`](#advisor_settings) | `get`, `update`, `list_presets`, `save_preset`, `delete_preset`, `set_default_preset` | Advisor defaults + presets |
| [`personas`](#personas) | `list`, `get`, `update`, `reset` | Advisor persona CRUD |
| [`conversations`](#conversations) | `list`, `get` | Saved conversation history |
| [`providers`](#providers) | `list_models`, `health`, `test`, `set_api_key`, `set_search` | Models, health, keys, search |
| [`config_backup`](#config_backup) | `export`, `import`, `reset` | Full settings backup/restore |

## Cost Reports

Deliberation tools return a `cost_report` object when a run performs model calls. It includes USD `total_cost`, token totals, call counts, known/unknown/estimated/free counts, `by_model`, `by_stage` where applicable, and raw `calls`.

Cost attribution uses provider-reported cost first, then known-free rules (`ollama:*`, `nvidia:*`, OpenRouter `:free`, OpenCode custom endpoints), then cached catalog estimates from `ai-model-pricing.com` with LiteLLM as fallback. When pricing is unavailable, token usage is preserved and cost is marked unknown.

---

## council_deliberate

Run council deliberation. Creates a conversation automatically unless `conversation_id` is provided.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | Yes | `stage1`, `stage2`, `stage3`, or `full` |
| `query` | string | Yes | User question |
| `web_search` | boolean | No | Enrich query with web search (default `false`) |
| `conversation_id` | string | No | Continue an existing thread |
| `models` | string[] | No | Override council members for `full` only (1–8 model IDs) |

**Example:** Full deliberation with search
```json
{
  "action": "full",
  "query": "What are the pros and cons of microservices?",
  "web_search": true
}
```

**`full` response shape (abbreviated):**
```json
{
  "conversation_id": "uuid",
  "query": "...",
  "stage1": { "results": [...], "summary": {...} },
  "stage2": { "rankings": [...], "aggregate_rankings": [...] },
  "stage3": { "synthesis": "..." },
  "chairman_answer": "...",
  "cost_report": {"total_cost": 0.0042, "total_tokens": 12345, "by_model": [...]}
}
```

Errors return `{"status": "error", "message": "..."}`.

Stage-only actions also include `cost_report`. Individual result rows include `usage` and `cost` when the backend provider returned usage.

---

## model_chat

Chat with a single model.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | Yes | `quick` (one-shot via `/api/ask`) or `multi_turn` (conversation stream) |
| `query` | string | Yes | User message |
| `model` | string | Yes | Model ID with prefix, e.g. `openai:gpt-4.1` |
| `conversation_id` | string | No | Required for `multi_turn` follow-ups (from prior response) |
| `web_search` | boolean | No | Default `false` |

**Example:** Quick one-shot
```json
{
  "action": "quick",
  "query": "Summarize quantum computing in one paragraph.",
  "model": "openai:gpt-4.1"
}
```

Responses include `usage`, `cost`, and `cost_report` alongside the model response. Ollama, NVIDIA, OpenRouter `:free`, and OpenCode custom endpoint calls report zero cost.

---

## advisor_debate

Run a multi-round advisor debate with named personas.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `question` | string | Yes | Debate topic |
| `persona_ids` | string[] | Yes | 2–4 persona IDs |
| `default_model` | string | No | Default model for all personas |
| `model_assignments` | object | No | Per-persona model overrides |
| `max_rounds` | integer | No | 3–10 (default 3) |
| `search_provider` | string | No | Override search provider |

**Example:**
```json
{
  "question": "Should we adopt Rust for our backend?",
  "persona_ids": ["skeptic", "pragmatist", "innovator"],
  "max_rounds": 3
}
```

Response includes `cost_report` with total cost, token totals, call counts, and per-model breakdown. Advisor response, tiebreaker, and verdict rows include `usage` and `cost` when available.

---

## run_iterative_debate

Run a multi-round iterative debate with convergence detection. Models debate across rounds, refining answers based on peer feedback. Returns all rounds data plus the chairman's corrected draft (Stage 4).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | The question or topic to debate |
| `debate_rounds` | integer | No | 1–5 (default from settings) |
| `critique_mode` | string | No | `freeform` (default), `paragraph`, or `claim` |
| `auto_converge` | boolean | No | Stop early if rankings stabilize (default `true`) |
| `convergence_threshold` | integer | No | 1–3, consecutive stable rounds to trigger early stop (default `2`) |
| `web_search` | boolean | No | Enrich query with web search (default `false`) |
| `models` | string[] | No | Override council members for the debate |

**Example:**
```json
{
  "query": "What are the tradeoffs between REST and GraphQL?",
  "debate_rounds": 2,
  "critique_mode": "freeform",
  "web_search": true
}
```

**Response shape (abbreviated):**
```json
{
  "conversation_id": "uuid",
  "total_rounds_executed": 2,
  "converged": false,
  "critique_mode": "freeform",
  "rounds": [...],
  "stage4": {"model": "...", "response": "Chairman's corrected draft..."},
  "cost_report": {"total_cost": 0.0123, "by_model": [...]}
}
```

---

## council_settings

Manage council configuration and presets.

| Parameter | Type | Actions | Description |
|-----------|------|---------|-------------|
| `action` | string | All | See actions below |
| `models` | string[] | `update` | 1–8 council member model IDs |
| `chairman` | string | `update` | Chairman model ID |
| `council_temperature` | float | `update` | Stage 1 heat |
| `chairman_temperature` | float | `update` | Stage 3 heat |
| `stage2_temperature` | float | `update` | Stage 2 heat |
| `execution_mode` | string | `update` | `full`, `chat_ranking`, or `chat_only` |
| `stage1_prompt`, `stage2_prompt`, `stage3_prompt` | string | `update` | Custom system prompts |
| `title_prompt`, `query_prompt` | string | `update` | Title generation and LLM search query reformulation prompts |
| `search_provider` | string | `update` | `duckduckgo`, `tavily`, `brave`, `serper`, `tinyfish` |
| `search_keyword_extraction` | string | `update` | Query processing: `direct` (default), `yake`, or `llm` |
| `search_result_count` | integer | `update` | Number of results to fetch (5–15, default 8) |
| `search_hybrid_mode` | boolean | `update` | DuckDuckGo: combine web + news (default `true`) |
| `full_content_results` | integer | `update` | Jina Reader full-text fetch count (0–5, default 3; 0 = disabled) |
| `enabled_providers` | object | `update` | Council-only provider toggles |
| `direct_provider_toggles` | object | `update` | Per-direct-provider council toggles |
| `preset_id` | string | `save_preset`, `delete_preset`, `set_default_preset` | Preset UUID |
| `preset_name` | string | `save_preset` | Display name |
| `council_models` | string[] | `save_preset` | Members for preset (alias: `models`) |
| `chairman_model` | string | `save_preset` | Chairman for preset (alias: `chairman`) |
| `is_default` | boolean | `save_preset` | Mark as default preset |

**`get` response includes:** `council_models`, `chairman_model`, temperatures, `execution_mode`, `search_provider`, `council_presets`.

**`update` success:**
```json
{"status": "updated", "fields": ["council_models", "execution_mode"]}
```

Council **Settings** pickers respect `enabled_providers`; welcome-screen Council Setup and REST model lists use all configured providers (like advisors).

---

## advisor_settings

Manage advisor defaults and presets.

| Parameter | Type | Actions | Description |
|-----------|------|---------|-------------|
| `action` | string | All | `get`, `update`, `list_presets`, `save_preset`, `delete_preset`, `set_default_preset` |
| `default_model` | string | `update`, `save_preset` | Default debate model |
| `tiebreaker_model` | string | `update`, `save_preset` | Tiebreaker model |
| `temperature` | float | `update` | Advisor temperature |
| `default_rounds` | integer | `update`, `save_preset` | 3–10 |
| `preset_name` | string | `save_preset` | Display name |
| `persona_ids` | string[] | `save_preset` | 2–4 personas |
| `mode` | string | `save_preset` | `simple` or `advanced` |
| `model_assignments` | object | `save_preset` | Per-persona models |
| `max_rounds` | integer | `save_preset` | 3–10 |
| `search_provider` | string | `save_preset` | Optional search override |
| `preset_id` | string | `delete_preset`, `set_default_preset` | Preset UUID |
| `is_default` | boolean | `save_preset` | Mark as default |

**`get` response includes:** `advisor_default_model`, `advisor_tiebreaker_model`, `advisor_temperature`, `advisor_default_rounds`, `advisor_presets`.

---

## personas

Manage advisor personas.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | Yes | `list`, `get`, `update`, or `reset` |
| `persona_id` | string | For get/update/reset | e.g. `skeptic`, `pragmatist` |
| `name`, `role`, `description`, `system_prompt`, `avatar_emoji` | string | For `update` | Fields to change (at least one required) |

Valid IDs: `skeptic`, `pragmatist`, `innovator`, `historian`, `ethicist`, `analyst`, `contrarian`, `strategist`, `humanist`, `risk-assessor`, `comedian`, `economist`.

---

## conversations

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | Yes | `list`, `get`, or `progress` |
| `conversation_id` | string | For `get`/`progress` | Conversation UUID |

`list` returns human-readable text. `get` returns JSON summary with truncated user content and chairman synthesis excerpts. `progress` returns live progress of an active streaming run — `{active: true, stage, progress, stage1, stage2, stage3, stage4}` or `{active: false}` if idle.

---

## providers

Provider utilities, model listing, and health checks.

| Parameter | Type | Actions | Description |
|-----------|------|---------|-------------|
| `action` | string | All | `list_models`, `health`, `test`, `set_api_key`, `set_search` |
| `provider` | string | `test`, `set_api_key`, `set_search` | Provider name |
| `api_key` | string | `test`, `set_api_key`, `set_search` | API key value |

**`health` response:**
```json
{
  "backend": "reachable",
  "base_url": "http://localhost:8001",
  "council_models": [...],
  "chairman_model": "...",
  "execution_mode": "full",
  "search_provider": "duckduckgo",
  "configured_providers": ["openai", "groq"],
  "ollama_url": "http://localhost:11434"
}
```

If settings fetch fails while backend is up: includes `"settings_error": "..."`.

**`set_search` valid providers:** `duckduckgo`, `tavily`, `brave`, `serper`, `tinyfish`.

**`set_search` query processing mode** — set `search_keyword_extraction` via `council_settings` `update`:

| Value | Behaviour |
|-------|-----------|
| `"direct"` | Send exact query to search engine (default) |
| `"yake"` | Extract key terms with YAKE before searching |
| `"llm"` | Chairman model reformulates the query (skipped for DuckDuckGo) |

**`set_api_key` valid providers:** `openrouter`, `openai`, `anthropic`, `google`, `mistral`, `deepseek`, `groq`, `nvidia`, `tinyfish`, `tavily`, `brave`, `serper`.

---

## config_backup

Full settings export, import, and factory reset.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | Yes | `export`, `import`, or `reset` |
| `config_json` | string or object | For `import` | Full settings JSON (string or parsed object) |

**`export`** returns indented JSON of all settings.

**`import`** accepts `config_json` as a JSON string or object.

**`reset`** restores factory defaults (irreversible).

Admin REST endpoints (`/api/settings/export` with bearer token) remain available for manual admin use when MCP is unavailable.

---

## Error conventions

- Validation errors: plain text starting with `Error: ...`
- API/network failures: JSON `{"status": "error", "message": "..."}`
- Provider test failures: JSON `{"success": false, "message": "..."}`

---

## REST fallback

When MCP is unavailable, use [`skills/the-ai-counsel-api/SKILL.md`](../../skills/the-ai-counsel-api/SKILL.md) for equivalent REST endpoints. Preset CRUD is now available via `council_settings` / `advisor_settings` MCP actions — REST `PUT /api/settings` remains the fallback.
