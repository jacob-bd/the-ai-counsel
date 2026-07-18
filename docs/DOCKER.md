# Docker Deployment

This guide covers running The AI Counsel as a single Docker container — suitable for home servers, VPS instances, and any environment where you want a persistent, auto-restarting deployment.

---

## Quick Start

```bash
git clone https://github.com/jacob-bd/the-ai-counsel.git
cd the-ai-counsel
docker compose up -d --build
```

Then open **http://localhost:8001** and configure your API keys in Settings.

The first build takes a few minutes (Python deps + frontend compile). Subsequent builds reuse the cache and are much faster.

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
- Image rebuilds (`docker compose up -d --build`)
- `docker compose down` and back up

**Your data is lost only if you delete `./data/` on the host.** Never do this unless you intend to wipe everything.

> ⚠️ Secrets live in `./data/credentials.json` (plain text, mode `0600` when possible). OS keystore mode is **not available in containers** — Docker always uses file storage on the data volume. Keep `./data` out of version control (already in `.gitignore`).

---

## Environment Variables

Set these in a `.env` file in the project root, or inline in `docker-compose.yml`.

| Variable | Default | Description |
|---|---|---|
| `BACKEND_HOST` | *(empty)* | Full URL of the backend, e.g. `https://api.example.com`. Leave empty when frontend and API share the same domain/port. |
| `FRONTEND_HOST` | *(empty)* | Comma-separated allowed CORS origins, e.g. `https://council.example.com`. Leave empty when serving both from the same origin. |
| `LLM_COUNCIL_ADMIN_TOKEN` | *(empty)* | Required for remote access to settings export/import/reset. When unset, those admin endpoints only accept direct loopback clients and reject proxied external clients. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint. **Must be changed when using Docker** — see below. |
| `FRONTEND_DIST_DIR` | `/app/frontend/dist` | Path to the compiled frontend. Do not change unless you know what you're doing. |

`LLM_COUNCIL_BIND_HOST` and `LLM_COUNCIL_BIND_PORT` apply only to the local `python -m backend.main` dev launcher. Docker starts uvicorn directly with `--host 0.0.0.0 --port 8001`, so use Docker port publishing or reverse proxy settings instead of those variables for container deployments.

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

Pull the latest code and rebuild. Your data is untouched.

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
docker compose restart
```

Rebuilding from the latest image (`docker compose up -d --build`) fixes this permanently — the entrypoint now corrects ownership automatically on every startup.

### Streaming responses don't work behind nginx

Add `proxy_buffering off;` and `proxy_cache off;` to your nginx location block — see the nginx example above.
