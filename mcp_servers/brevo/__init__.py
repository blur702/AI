"""
Brevo MCP Proxy Server configuration.

This module provides settings for connecting to Brevo's hosted MCP server,
which provides access to email marketing, CRM, SMS, WhatsApp, and other
Brevo services through the Model Context Protocol.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


class Settings:
    """Configuration settings for Brevo MCP proxy server."""

    # Brevo MCP Token (API Key for MCP access)
    BREVO_MCP_TOKEN: str = os.getenv("BREVO_MCP_TOKEN", "")

    # Brevo MCP Base URL
    BREVO_MCP_BASE_URL: str = os.getenv("BREVO_MCP_BASE_URL", "https://mcp.brevo.com")

    # Logging level
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    @property
    def brevo_mcp_url(self) -> str:
        """Construct the full Brevo MCP endpoint URL."""
        return f"{self.BREVO_MCP_BASE_URL}/brevo/mcp/{self.BREVO_MCP_TOKEN}"

    def validate(self) -> None:
        """Validate required settings are configured."""
        if not self.BREVO_MCP_TOKEN:
            raise ValueError(
                "BREVO_MCP_TOKEN environment variable is required. "
                "Set it in the .env file or environment."
            )


settings = Settings()
