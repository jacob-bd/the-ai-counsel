# Docker Deployment

This guide covers running The AI Counsel as a single Docker container — suitable for home servers, VPS instances, and any environment where you want a persistent, auto-restarting deployment.

---

## Quick Start

Pull the prebuilt image from GitHub Container Registry — no build step, no clone required:

```bash
mkdir -p data
docker run -d --restart unless-stopped --name the-ai-counsel \
  -p 8001:8001 -v ./data:/app/data \
  ghcr.io/jacob-bd/the-ai-counsel:latest
```

Then open **http://localhost:8001** and configure your API keys in Settings.

Every push to `main` that passes the test suite publishes a fresh `:latest` image. When a matching release tag such as `v0.12.0` is pushed, the workflow also publishes `ghcr.io/jacob-bd/the-ai-counsel:0.12.0`, so you can pin to, or roll back to, a specific release instead of always tracking `latest`. Manually starting the workflow runs the tests for the selected ref but does not publish an image.

> **One-time setup for maintainers:** GHCR creates a package as **private** the first time a workflow pushes to it. Until someone makes it public, the `docker pull`/`docker run` command above fails for anyone else with `denied: requested access to the resource is denied`. After the `docker-publish.yml` workflow's first successful run, go to the package on GitHub (your profile or org → **Packages** → `the-ai-counsel`) → **Package settings** → and either set visibility to **Public**, or link the package to this repository so its collaborators inherit access. This is a one-time step; it does not need to be repeated on later pushes.

### Build from source instead

If you're modifying the code, want to build for an architecture without a published image, or just prefer building locally:

```bash
git clone https://github.com/jacob-bd/the-ai-counsel.git
cd the-ai-counsel
docker compose up -d --build
```

The first build takes a few minutes (Python deps + frontend compile). Subsequent builds reuse the cache and are much faster.

The rest of this guide uses `docker compose` commands (`logs`, `exec`, restarts) for consistency with that setup. If you're running the prebuilt image via `docker run` instead, swap `docker compose <cmd>` for `docker <cmd> the-ai-counsel` (the `--name` given above), e.g. `docker logs -f the-ai-counsel` instead of `docker compose logs -f`.

---

## How It Works

The container runs everything in one process:

- The **React frontend** is compiled at build time and served as static files by the FastAPI backend.
- The **FastAPI backend** listens on port `8001` and serves both the UI and all `/api/*` routes.
- A **startup script** (`docker-entrypoint.sh`) injects the runtime API URL into the frontend config before uvicorn starts.

---

## Persistent Storage

All user data lives in `/app/data` inside the container, which is mounted to `./data` on the host:

```yaml
volumes:
  - ./data:/app/data
```

This covers:

| Path inside container | Host path | Contents |
|---|---|---|
| `/app/data/settings.json` | `./data/settings.json` | Non-secret config (council, prompts, toggles) |
| `/app/data/credentials.json` | `./data/credentials.json` | API keys and OAuth tokens (file storage mode) |
| `/app/data/conversations/` | `./data/conversations/` | Full conversation history |

**Your data survives:**
- Container restarts
- Image upgrades, whether rebuilt (`docker compose up -d --build`) or re-pulled (`docker pull` + recreate, see [Upgrading](#upgrading))
- `docker compose down` and back up, or `docker stop`/`docker rm` and back up

**Your data is lost only if you delete `./data/` on the host.** Never do this unless you intend to wipe everything.

> ⚠️ Secrets live in `./data/credentials.json` (plain text, mode `0600` when possible). OS keystore mode is **not available in containers** — Docker always uses file storage on the data volume. Keep `./data` out of version control (already in `.gitignore`).

---

## Environment Variables

Set these in a `.env` file in the project root, or inline in `docker-compose.yml`.

| Variable | Default | Description |
|---|---|---|
| `PORT_BACKEND` | `8001` | Port the backend listens on, and the host port published by `docker-compose.yml`. |
| `PORT_FRONTEND` | `5173` | Vite dev/preview server port. Not used by the container, which serves the built frontend from the backend port. |
| `BACKEND_HOST` | *(empty)* | Full URL of the backend, e.g. `https://api.example.com`. Leave empty when frontend and API share the same domain/port. |
| `FRONTEND_HOST` | *(empty)* | Comma-separated allowed CORS origins, e.g. `https://council.example.com`. Leave empty when serving both from the same origin. |
| `LLM_COUNCIL_ADMIN_TOKEN` | *(empty)* | Required for remote access to settings export/import/reset. When unset, those admin endpoints only accept direct loopback clients and reject proxied external clients. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint. **Must be changed when using Docker** — see below. |
| `FRONTEND_DIST_DIR` | `/app/frontend/dist` | Path to the compiled frontend. Do not change unless you know what you're doing. |

`PORT_BACKEND` sets the port uvicorn listens on in both the local `python -m backend.main` dev launcher and the container (the entrypoint passes it to uvicorn, and `docker-compose.yml` publishes the same port on the host). When `BACKEND_HOST` is empty, the UI calls the API on the same origin as the page, so changing `PORT_BACKEND` at runtime does not require rebuilding the image. `LLM_COUNCIL_BIND_HOST` controls the bind address for the dev launcher only; `LLM_COUNCIL_BIND_PORT` still works as a legacy override for `PORT_BACKEND`.

### Example `.env`

```env
# Leave both empty when accessing via http://YOUR_HOST_IP:8001
BACKEND_HOST=
FRONTEND_HOST=

# Required if using local Ollama with Docker
OLLAMA_BASE_URL=http://host.docker.internal:11434

# Required if you need Backup & Reset admin actions from another device or via a reverse proxy
LLM_COUNCIL_ADMIN_TOKEN=replace-with-a-long-random-token
```

---

## Using Ollama with Docker

Ollama runs on your host machine at `localhost:11434`. From inside the container, `localhost` refers to the container itself — not your Mac/Linux host — so Ollama will be unreachable.

**Fix:** Set `OLLAMA_BASE_URL` to the Docker host gateway:

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

`host.docker.internal` is automatically resolved to your host machine by Docker Desktop (macOS and Windows). On Linux hosts, add this to the `docker-compose.yml` service:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

---

## Reverse Proxy / Custom Domain

Point your reverse proxy (nginx, Caddy, Traefik) to `http://127.0.0.1:8001`.

### Caddy example

```caddy
council.example.com {
    reverse_proxy 127.0.0.1:8001
}
```

### nginx example

```nginx
server {
    listen 80;
    server_name council.example.com;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # Required for SSE (streaming responses)
        proxy_buffering off;
        proxy_cache off;
    }
}
```

> **Important:** Disable proxy buffering (`proxy_buffering off`) — the app uses Server-Sent Events for real-time streaming. Buffered proxies will cause the UI to hang until a response completes.

When using a reverse proxy with a custom domain, `BACKEND_HOST` and `FRONTEND_HOST` can stay empty as long as the frontend and API are on the same domain.

If you split them (e.g., API on `api.example.com`, UI on `council.example.com`), set both:

```env
BACKEND_HOST=https://api.example.com
FRONTEND_HOST=https://council.example.com
```

Settings export/import/reset are admin endpoints because settings exports include plaintext API keys. If you need to use those Backup & Reset actions through a reverse proxy or from another device, set `LLM_COUNCIL_ADMIN_TOKEN` and send `Authorization: Bearer <token>` with those requests. Without the token, proxied external clients are rejected even though the reverse proxy connects to the backend over `127.0.0.1`.

---

## Upgrading

**Prebuilt image:** pull the new `:latest` and recreate the container. Your data (mounted at `./data`) is untouched.

```bash
docker pull ghcr.io/jacob-bd/the-ai-counsel:latest
docker stop the-ai-counsel && docker rm the-ai-counsel
docker run -d --restart unless-stopped --name the-ai-counsel \
  -p 8001:8001 -v ./data:/app/data \
  ghcr.io/jacob-bd/the-ai-counsel:latest
```

To pin to a known-good release instead of always tracking `latest`, use a version tag (e.g. `ghcr.io/jacob-bd/the-ai-counsel:0.12.0`) in place of `:latest` above.

**Built from source:** pull the latest code and rebuild.

```bash
git pull
docker compose up -d --build
```

Docker layer caching means only changed layers rebuild. A typical upgrade (Python deps unchanged) takes under 30 seconds.

### Migrating from LLM Council Plus

If you're upgrading from the original `llm-council-plus` repo, see the full **[Migration Guide](MIGRATION.md)** — it covers Docker, local dev, MCP server re-registration, and skill symlinks. Your `data/` directory copies over; on first launch after v0.11.0, any legacy keys in `settings.json` are moved into `credentials.json` automatically.

---

## Persistence After Reboots

The `docker-compose.yml` sets `restart: unless-stopped`, so the container restarts automatically after a system reboot — as long as Docker itself starts at boot.

- **Docker Desktop (macOS/Windows):** Enable "Start Docker Desktop when you log in" in Docker Desktop preferences.
- **Linux (Docker Engine):** Enable the Docker daemon: `sudo systemctl enable docker`

---

## Security Notes

- The container runs as a non-root user (`appuser`) for reduced attack surface.
- A healthcheck polls `/api/health` every 30 seconds. Docker will report the container as `unhealthy` if the backend stops responding, and `restart: unless-stopped` will restart it.
- API keys and OAuth tokens are stored in plain text in `./data/credentials.json` (file mode only in Docker). See [`CREDENTIALS.md`](CREDENTIALS.md). Do not expose port `8001` to the public internet without authentication (use a reverse proxy with auth, or restrict access via firewall).

---

## Troubleshooting

### View logs

```bash
docker compose logs -f
```

### Check container health

```bash
docker inspect --format='{{.State.Health.Status}}' the-ai-counsel-app-1
```

### Open a shell inside the container

```bash
docker compose exec app bash
```

### Confirm the container is running as non-root

```bash
docker compose exec app whoami
# → appuser
```

### The frontend loads but API calls fail (CORS errors)

You are likely accessing the app from a different origin than the one Docker is binding to. Either:
- Access via `http://YOUR_HOST_IP:8001` (not `localhost` from another machine)
- Or set `FRONTEND_HOST` and `BACKEND_HOST` appropriately for your split-origin setup

### Settings won't save / Permission denied on `/app/data/settings.json`

Docker creates the `./data` directory as root when the container first starts. On older images (before this was fixed in the entrypoint), `appuser` inside the container couldn't write to it.

If you're running an older image, fix it manually:

```bash
chmod 777 ./data
docker compose restart   # or: docker restart the-ai-counsel
```

Upgrading to the latest image (see [Upgrading](#upgrading)) fixes this permanently — the entrypoint now corrects ownership automatically on every startup.

### Streaming responses don't work behind nginx

Add `proxy_buffering off;` and `proxy_cache off;` to your nginx location block — see the nginx example above.
