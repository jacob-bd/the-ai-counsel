"""MCP server setup for The AI Counsel."""

from mcp.server.fastmcp import FastMCP

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
        instructions=(
            "The AI Counsel — 10 MCP tools with action parameters. "
            "Run: council_deliberate (stage1|stage2|stage3|full), model_chat (quick|multi_turn), "
            "advisor_debate, run_iterative_debate. "
            "Config: council_settings, advisor_settings (each: get|update|list_presets|"
            "save_preset|delete_preset|set_default_preset), personas (list|get|update|reset), "
            "conversations (list|get|progress), providers (list_models|health|test|set_api_key|set_search), "
            "config_backup (export|import|reset). "
            "Provider model IDs use a `provider:model` prefix. Supported prefixes include "
            "openrouter, ollama, groq, openai, anthropic, google, mistral, deepseek, nvidia, "
            "custom, opencode-zen, and opencode-go. "
            "Deliberation, debate, advisor, and model_chat results include a top-level `cost_report` "
            "(total_cost, total_tokens, by_model, known_cost_calls, unknown_cost_calls, free_calls). "
            "council_deliberate, model_chat, advisor_debate, and run_iterative_debate accept optional "
            "`documents`; pass extracted text or base64 source files, which are extracted before model calls. "
            "Prefer these MCP tools over curl. Full REST reference: skills/the-ai-counsel-api/SKILL.md."
        ),
        host=host,
        port=port,
    )

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
