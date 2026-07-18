# Credentials & Secrets

How The AI Counsel stores API keys, OAuth tokens, and related secrets (v0.11.0+).

## Where secrets live

| Mode | Location | When to use |
|------|----------|-------------|
| **Encrypted file** (default) | `data/credentials.json` (mode `0600` when possible) | Docker, servers, most installs |
| **OS keystore** | macOS Keychain / Windows Credential Manager / libsecret — service name **`the-ai-counsel`** | Desktop only |

Choose the mode under **Settings → LLM API Keys → Where secrets are stored**. Switching modes **migrates** Counsel’s secrets between file and the `the-ai-counsel` keystore entry, then removes them from the old location.

**`settings.json` never holds API keys** after upgrade. Non-secret config (council, prompts, toggles) stays in `data/settings.json`. On first launch after the credentials release, any legacy plaintext keys in `settings.json` are moved into the credential store automatically.

## What is stored

- LLM API keys (OpenRouter, Groq, OpenCode, OpenAI, Anthropic, Google, …)
- Search provider keys (Tavily, Brave, Serper, TinyFish)
- Custom endpoint API key
- Subscription OAuth blobs (xAI SuperGrok, ChatGPT Plus/Pro, GitHub Copilot)

Secrets are never returned by `GET /api/settings` — only `*_api_key_set` / `*_oauth_connected` booleans.

## Disconnect vs Reset

| Action | Where | What it does |
|--------|-------|----------------|
| **Disconnect** (per provider) | LLM API Keys / Search / OAuth | Clears that secret; ignores env override for that id until you save a new key; disables that source |
| **Disconnect All Providers** | Backup & Reset → Danger Zone | Clears **all** stored secrets + OAuth; disables all provider toggles; keeps council models, prompts, and other settings |
| **Reset to Defaults** | Backup & Reset → Danger Zone | Resets UI/config defaults; **does not** replace Disconnect All for wiping keys (prefer Disconnect All when testing a clean credential slate) |

Admin endpoints that wipe or export secrets (`export` / `import` / `reset` / `disconnect-all-providers`) require loopback or `Authorization: Bearer $LLM_COUNCIL_ADMIN_TOKEN`.

## Environment variables

Process env vars such as `OPENCODE_API_KEY` / `OPENROUTER_API_KEY` can still supply keys when nothing is stored. After **Disconnect**, Counsel adds that secret id to `disabled_secret_ids` so the env value is ignored until you save a new key in Settings (or clear the disable list via a fresh save).

Preference when resolving a key for Retest / providers:

1. Not in `disabled_secret_ids`
2. Value in credential store (file or OS keystore)
3. Else matching env override (if any)

## Import from relay-ai

Desktop only (not available in Docker/containers).

1. **Settings → General → Import from relay-ai** → Discover → select → Import  
2. Counsel **copies** secrets out of the Keychain service **`relay-ai`** into Counsel’s active store (`credentials.json` or service **`the-ai-counsel`**).
3. Claude Code / Antigravity entries are never imported.
4. Import **auto-enables** the matching provider toggles and shows a green success confirmation.

### File → Keychain after import

If you import while on **Encrypted file**, then switch storage to **OS keystore**:

- Secrets move into Keychain service **`the-ai-counsel`** (Counsel account ids like `api:anthropic`).
- The original **`relay-ai`** Keychain entries are **not** modified or deleted.
- Having the same key material in both services is expected (two apps, two copies). Counsel never writes into the `relay-ai` service.

## Docker

Containers **always** use file storage on the data volume (`./data/credentials.json`). OS keystore mode is disabled in containers. Mount `./data` persistently and keep it out of git.

## Backup / restore

- Admin **export** includes a `credentials` object (plaintext secrets) — treat the file as sensitive.
- Legacy exports with inline `*_api_key` fields still import; keys are routed into the credential store.
- Ordinary **Export Config** from the UI (council JSON) does **not** include API keys.

## Related docs

- Setup: [`QUICKSTART.md`](QUICKSTART.md)
- Docker: [`DOCKER.md`](DOCKER.md)
- Migration from older installs: [`MIGRATION.md`](MIGRATION.md)
- Agent API reference: [`../skills/the-ai-counsel-api/SKILL.md`](../skills/the-ai-counsel-api/SKILL.md)
