"""Entry point for The AI Counsel MCP server."""

import argparse
import asyncio
import os

from dotenv import load_dotenv

from .server import create_server, default_base_url, run_stdio, run_sse


def main():
    # Pick up PORT_BACKEND from the repo .env when run standalone.
    load_dotenv()
    backend_base_url = default_base_url()
    parser = argparse.ArgumentParser(
        description="The AI Counsel MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  # Local backend, stdio transport (for Claude Code / Gemini CLI)
  python -m the_ai_counsel_mcp

  # Remote backend, stdio transport
  python -m the_ai_counsel_mcp --base-url https://yourserver.com:{os.getenv('PORT_BACKEND', '8001')}

  # Standalone SSE transport fallback (Note: SSE is built into the main uvicorn app
  # at /mcp/sse on the backend port, {os.getenv('PORT_BACKEND', '8001')} by default!)
  python -m the_ai_counsel_mcp --transport sse --port 8002
        """,
    )
    parser.add_argument(
        "--base-url",
        default=backend_base_url,
        help=f"Base URL of The AI Counsel backend (default: {backend_base_url}, follows PORT_BACKEND)",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport mode: stdio (default) or sse",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8002,
        help="Port for SSE transport (default: 8002)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host for SSE transport (default: 0.0.0.0)",
    )
    args = parser.parse_args()

    server = create_server(
        base_url=args.base_url,
        host=args.host,
        port=args.port,
    )

    if args.transport == "sse":
        asyncio.run(run_sse(server, host=args.host, port=args.port))
    else:
        asyncio.run(run_stdio(server))


if __name__ == "__main__":
    main()
