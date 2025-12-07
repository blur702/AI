"""
Brevo MCP Proxy Server.

This module provides a FastMCP proxy that bridges Brevo's remote SSE-based
MCP server to local STDIO transport for use with VS Code, Claude Desktop,
and other MCP clients.

The proxy forwards all MCP requests to Brevo's hosted infrastructure,
providing access to 26+ services including:
- Email campaigns and transactional emails
- Contact and list management
- CRM (deals, companies, tasks, notes)
- SMS and WhatsApp campaigns
- Analytics and reporting
- Domain and sender configuration

Usage:
    python -m mcp_servers.brevo.main

Architecture:
    VS Code/Claude Desktop
            |
            | STDIO (JSON-RPC)
            v
       MCP Proxy (this server)
            |
            | HTTPS/SSE
            v
      Brevo Hosted MCP Server
"""

from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP

from . import settings

# Configure logging to stderr (critical for STDIO transport)
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
    force=True,
)

logger = logging.getLogger("mcp_servers.brevo")


def create_proxy() -> FastMCP:
    """
    Create and configure the Brevo MCP proxy server.

    Returns:
        FastMCP proxy instance configured to forward requests to Brevo.
    """
    # Validate settings before creating proxy
    settings.validate()

    brevo_url = settings.brevo_mcp_url
    logger.info("Creating Brevo MCP proxy")
    logger.debug("Brevo MCP URL: %s", brevo_url.replace(settings.BREVO_MCP_TOKEN, "***"))

    # Create proxy using FastMCP's proxy functionality
    # This bridges Brevo's SSE transport to local STDIO
    proxy = FastMCP.as_proxy(brevo_url, name="Brevo")

    logger.info("Brevo MCP proxy created successfully")
    return proxy


# Create the proxy instance
proxy = create_proxy()


if __name__ == "__main__":
    logger.info("Starting Brevo MCP proxy server")
    proxy.run()
