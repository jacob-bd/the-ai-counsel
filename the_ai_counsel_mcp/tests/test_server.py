"""Tests for MCP server metadata."""

from the_ai_counsel_mcp import __version__
from the_ai_counsel_mcp.server import create_server


def test_mcp_initialization_advertises_app_version():
    """The MCP handshake reports The AI Counsel version, not the SDK version."""
    server = create_server()

    initialization = server._mcp_server.create_initialization_options()

    assert initialization.server_version == __version__
