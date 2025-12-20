"""
MCP CodeRabbit Server configuration.

Provides settings for connecting to GitHub API and managing CodeRabbit reviews.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Configuration settings for the MCP CodeRabbit server."""

    # GitHub settings
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
    GITHUB_REPO: str = os.getenv("GITHUB_REPO", "blur702/AI")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Project root for applying fixes
    PROJECT_ROOT: str = os.getenv("PROJECT_ROOT", os.getcwd())


settings = Settings()
