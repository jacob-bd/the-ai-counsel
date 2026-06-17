# SSE Setup (Zero Local Installation)

This guide covers connecting your local AI agent (Claude Code, Gemini CLI, etc.) to the built-in MCP server running inside your Council backend container. 

The MCP server is now integrated directly into the main FastAPI application. There is no need to expose a second port (`8002`) or run a separate background process. All communications go through your existing web port (`8001`).

If you want to run the MCP server locally and point it at a remote backend, see [SETUP-LOCAL.md](SETUP-LOCAL.md) instead. If you are unsure which to choose, see [CHOOSING-TRANSPORT.md](CHOOSING-TRANSPORT.md).

---

## Prerequisites

- The AI Counsel running in a container (see [docs/DOCKER.md](../DOCKER.md))
- Port `8001` accessible from your client machine (or via VPN/reverse proxy)

---

## Step 1: Register in Claude Code

Because the SSE server is hosted directly under `/mcp`, you can register it with a single command pointing to your server's main port (`8001`):

```bash
claude mcp add --transport sse the-ai-counsel http://yourserver.com:8001/mcp/sse
```

Replace `yourserver.com` with your server's IP address or domain.

For Gemini CLI:
```bash
gemini mcp add the-ai-counsel --url http://yourserver.com:8001/mcp/sse
```

---

## Step 2: Security

The MCP server has no built-in authentication. Before exposing port `8001` publicly, protect it with one of these approaches:

**Firewall rule (simplest):** Restrict port `8001` to your IP address only. On most cloud providers this is done in the security group or firewall panel.

**VPN:** Run the server on a VPN-only network and connect your client to the VPN before using the MCP tools.

**Reverse proxy with authentication:**
You can protect the REST API and the `/mcp` endpoints using standard HTTP Basic Auth at your reverse proxy (e.g. Nginx):

```nginx
# nginx example — protect /mcp with basic auth
location /mcp {
    auth_basic "Council MCP";
    auth_basic_user_file /etc/nginx/.htpasswd;
    proxy_pass http://localhost:8001;
    proxy_set_header Connection '';
    proxy_buffering off;
}
```

> [!WARNING]
> Do not expose port `8001` to the public internet without one of these protections. Anyone with the URL can invoke council tools, access your conversation logs, and consume your LLM API quota.

---

## Step 3: Verify it works

Ask your AI:

> "Check the council health"

A successful response confirms the MCP server reached the backend (via `providers` → `health`):

```json
{
  "backend": "reachable",
  "configured_providers": ["openrouter", "anthropic"]
}
```

Confirm `"mcp": {"tools": 10}` in `GET /api/health`.

---

## Troubleshooting

**"Connection refused" on port 8001**
- Confirm the The AI Counsel container is running: `docker ps`
- Verify firewall rules allow inbound traffic on `8001`.

**Tools return errors but health check passes**
- The MCP server is running but the Council backend may not have API keys configured.
- Open the Council web UI at port `8001` and confirm provider keys are set in Settings.

**SSE connection drops after a few seconds**
- If behind a reverse proxy, enable `proxy_buffering off` and increase timeouts (see nginx example above).
- Some load balancers close idle SSE connections; configure keepalive or use a WebSocket-capable proxy.
