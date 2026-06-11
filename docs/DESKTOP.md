# Desktop wrapper

The AI Counsel can run inside an Electron desktop shell. The wrapper starts the existing backend and frontend development servers, waits for both services to become reachable, then loads the React UI in a desktop window.

This is a thin launcher layer. It does not add a second backend, does not depend on Notion2API, and does not change where The AI Counsel stores settings or conversations.

## Prerequisites

- Python 3.10+
- Node.js 18+
- `uv`
- npm

## Windows quick start

From the repository root:

```bat
desktop-start.bat
```

The batch launcher installs missing root Electron dependencies, installs missing frontend dependencies, and runs:

```bash
npm run desktop:start
```

## Manual start

```bash
uv sync
npm install
npm install --prefix frontend
npm run desktop:start
```

## Runtime behavior

The wrapper launches:

| Service | Command | Default URL |
| --- | --- | --- |
| Backend | `uv run python -m backend.main` | `http://127.0.0.1:8001` |
| Frontend | `npm run dev -- --host 127.0.0.1` from `frontend/` | `http://127.0.0.1:5173` |

The Electron window loads the frontend URL after `/api/health` and the Vite UI respond.

## Environment overrides

```bash
AI_COUNSEL_BACKEND_URL=http://127.0.0.1:8001
AI_COUNSEL_FRONTEND_URL=http://127.0.0.1:5173
LLM_COUNCIL_BIND_HOST=127.0.0.1
```

The wrapper passes `VITE_API_URL` to the frontend process so the browser UI talks to the selected backend URL.

## Logs

Desktop wrapper logs are written under Electron's user data directory:

```text
%APPDATA%\The AI Counsel\logs\
```

The tray/menu item **Open Logs** opens that folder.

## Packaging

Portable Windows build:

```bash
npm run desktop:build
```

Development directory build:

```bash
npm run desktop:pack
```

The packaging config includes `backend/`, `frontend/`, `pyproject.toml`, and `uv.lock`. A packaged build still expects `uv` and Node/npm to be available unless the runtime is later bundled more deeply.

## Porting notes from Notion2Council

Carried over conceptually:

- Electron desktop shell
- tray/menu lifecycle
- background stack start/stop
- health-check wait before loading UI
- separate desktop logs

Intentionally not carried over:

- Notion2API process orchestration
- Notion endpoint diagnostics
- Notion-specific storage reset behavior
- custom prompt/config files from the wrapper repo

Those pieces are specific to Notion2Council and would make The AI Counsel wrapper harder to maintain.
