# Migrating from LLM Council Plus

This guide covers upgrading from the original **LLM Council Plus** (`jacob-bd/llm-council-plus`) to **The AI Counsel** (`jacob-bd/the-ai-counsel`).

The AI Counsel is a rebrand and continuation of LLM Council Plus. All features, data formats, and configuration schemas are fully compatible — your existing settings and conversations carry over without modification.

---

## What Changed

| Area | Old | New |
|------|-----|-----|
| Product name | LLM Council Plus | The AI Counsel |
| GitHub repo | `jacob-bd/llm-council-plus` | `jacob-bd/the-ai-counsel` |
| Python package | `llm_council_mcp` | `the_ai_counsel_mcp` |
| MCP CLI script | `llm-council-mcp` | `the-ai-counsel-mcp` |
| Docker Compose service | `llm-council-plus` | `the-ai-counsel` |
| Skill directory | `skills/llm-council-api/` | `skills/the-ai-counsel-api/` |
| JS runtime config | `__LLM_COUNCIL_CONFIG__` | `__AI_COUNSEL_CONFIG__` |

**What did NOT change:**

- **Data format** — `data/settings.json` and `data/conversations/*.json` are identical in schema. No migration script needed.
- **Environment variables** — `LLM_COUNCIL_BIND_HOST`, `LLM_COUNCIL_BIND_PORT`, `LLM_COUNCIL_ADMIN_TOKEN` all work as before.
- **Port** — Backend still runs on `8001`.
- **API surface** — All `/api/*` endpoints are unchanged. New endpoints were added (see CHANGELOG).

---

## Docker Migration

If you're running LLM Council Plus as a Docker container:

```bash
# 1. Stop the old container
cd ~/llm-council-plus        # your old project directory
docker compose down

# 2. Clone the new repo
git clone https://github.com/jacob-bd/the-ai-counsel.git ~/the-ai-counsel
cd ~/the-ai-counsel

# 3. Copy your data (settings, conversations, API keys — everything)
cp -r ~/llm-council-plus/data ~/the-ai-counsel/data

# 4. Copy your .env file if you have one
cp ~/llm-council-plus/.env ~/the-ai-counsel/.env 2>/dev/null || true

# 5. Build and start
docker compose up -d --build
```

Open **http://localhost:8001** (or your server IP). All your conversations, API keys, council presets, advisor presets, and system prompts will be there.

### Cleanup (optional)

Once you've confirmed everything works:

```bash
# Remove old container image
docker rmi $(docker images --filter reference='*llm-council*' -q) 2>/dev/null || true

# Keep ~/llm-council-plus/data as a backup, or delete the old directory entirely
```

---

## Local Development Migration

If you're running from source (not Docker):

```bash
# 1. Clone the new repo
git clone https://github.com/jacob-bd/the-ai-counsel.git ~/the-ai-counsel
cd ~/the-ai-counsel

# 2. Copy your data directory
cp -r ~/llm-council-plus/data ~/the-ai-counsel/data

# 3. Install dependencies
uv sync
npm install --prefix frontend

# 4. Start
./start.sh
```

---

## MCP Server Migration

If you registered the old MCP server with Claude Code or Gemini CLI, update the registration:

### Claude Code

```bash
# Remove old registration
claude mcp remove llm-council

# Add new registration
claude mcp add the-ai-counsel -- uv run --directory ~/the-ai-counsel python -m the_ai_counsel_mcp
```

### Gemini CLI

```bash
# Remove old registration
gemini mcp remove llm-council

# Add new registration
gemini mcp add the-ai-counsel -- uv run --directory ~/the-ai-counsel python -m the_ai_counsel_mcp
```

After re-registering, verify with a health check:

```bash
# MCP tool prefix changes from mcp__llm-council-plus__ to mcp__the-ai-counsel__
curl http://localhost:8001/api/health
# → {"status":"ok","mcp":{"tools":10}}
```

---

## Skill Symlink Migration

If you installed the agent skill via symlink:

```bash
# Remove old symlink
rm -f ~/.claude/skills/llm-council-api

# Create new symlink
ln -s ~/the-ai-counsel/skills/the-ai-counsel-api ~/.claude/skills/the-ai-counsel-api
```

---

## FAQ

**Q: Will I lose my conversations?**
No. Copy `data/conversations/` to the new project and they appear immediately.

**Q: Will I lose my API keys and settings?**
No. Copy the whole `data/` directory. Non-secret settings stay in `settings.json`; from v0.11.0 secrets live in `credentials.json` (auto-migrated from legacy inline keys on first launch). See [`CREDENTIALS.md`](CREDENTIALS.md).

**Q: Do I need to reconfigure anything?**
No. The settings schema is unchanged. The only thing that changes is the product name in the UI.

**Q: Can I run both side by side?**
Yes, as long as they use different ports. The new repo defaults to 8001 — if the old one is still running on 8001, either stop it first or change the port via `LLM_COUNCIL_BIND_PORT` or Docker port mapping.

**Q: What about the old repo?**
The `jacob-bd/llm-council-plus` repo will remain available with a notice pointing to the new repo. It will not receive further updates.


## Credential storage upgrade (subscription OAuth / keystore)

On first launch after this release, plaintext API keys in `data/settings.json` are moved into `data/credentials.json` (or the OS keystore if you switch storage mode under Settings → LLM API Keys on a desktop install). Docker deployments always use the file store — OS keystore is not available in containers. Admin settings export now includes a `credentials` object; legacy exports with inline `*_api_key` fields still import correctly.
