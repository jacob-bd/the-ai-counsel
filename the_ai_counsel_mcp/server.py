"""MCP server setup for The AI Counsel."""

from mcp.server.fastmcp import FastMCP

from . import __version__
from .tools import advisors as advisors_tools
from .tools import config_backup as config_backup_tools
from .tools import conversations as conversations_tools
from .tools import council as council_tools
from .tools import deliberation as deliberation_tools
from .tools import providers as providers_tools


def create_server(
    base_url: str = "http://localhost:8001",
    host: str = "0.0.0.0",
    port: int = 8002,
) -> FastMCP:
    """Create and configure The AI Counsel MCP server."""
    server = FastMCP(
        name="the-ai-counsel",
        # Keep this short: MCP clients re-send the whole instructions block on every
        # reconnect, and agent harnesses that spawn a fresh process per turn pay for it
        # each time. Only cross-cutting facts belong here — per-tool actions, arguments
        # and result shapes are already carried by each tool's own description.
        instructions=(
            "The AI Counsel — multi-model deliberation, debate and chat tools. "
            "Model IDs are `provider:model`; supported prefixes: openrouter, ollama, groq, "
            "openai, anthropic, google, mistral, deepseek, nvidia, custom, opencode-zen, opencode-go. "
            "Deliberation, debate and chat tools accept an optional `documents` list; pass extracted "
            "text or base64 source files, which are extracted before model calls. "
            "Prefer these tools over curl. Full REST reference: skills/the-ai-counsel-api/SKILL.md."
        ),
        host=host,
        port=port,
    )
    # FastMCP 1.27 exposes the protocol version on its underlying Server rather
    # than accepting it as a constructor argument.
    server._mcp_server.version = __version__

    server.base_url = base_url  # type: ignore[attr-defined]

    deliberation_tools.register(server, base_url)
    council_tools.register(server, base_url)
    advisors_tools.register(server, base_url)
    conversations_tools.register(server, base_url)
    providers_tools.register(server, base_url)
    config_backup_tools.register(server, base_url)

    return server


async def run_stdio(server: FastMCP) -> None:
    """Run the MCP server using stdio transport (for Claude Code / Gemini CLI)."""
    await server.run_stdio_async()


async def run_sse(server: FastMCP, host: str = "0.0.0.0", port: int = 8002) -> None:
    """Run the MCP server using SSE transport (HTTP server mode)."""
    await server.run_sse_async()
