"""Entry point for The AI Counsel MCP server."""

import argparse
import asyncio

from .server import create_server, run_stdio, run_sse


def main():
    parser = argparse.ArgumentParser(
        description="The AI Counsel MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Local backend, stdio transport (for Claude Code / Gemini CLI)
  python -m the_ai_counsel_mcp

  # Remote backend, stdio transport
  python -m the_ai_counsel_mcp --base-url https://yourserver.com:8001

  # Standalone SSE transport fallback (Note: SSE is built into the main uvicorn app at /mcp/sse on port 8001!)
  python -m the_ai_counsel_mcp --transport sse --port 8002
        """,
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8001",
        help="Base URL of The AI Counsel backend (default: http://localhost:8001)",
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
