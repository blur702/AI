"""
MCP Documentation Search Server configuration.

Provides settings for connecting to Weaviate and configuring the search service.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Configuration settings for the MCP Documentation Search server."""

    WEAVIATE_URL: str = os.getenv("WEAVIATE_URL", "http://localhost:8080")
    WEAVIATE_GRPC_HOST: str = os.getenv("WEAVIATE_GRPC_HOST", "localhost")

    @staticmethod
    def _parse_grpc_port() -> int:
        """Parse and validate WEAVIATE_GRPC_PORT as an integer."""
        port_str = os.getenv("WEAVIATE_GRPC_PORT", "50051")
        try:
            return int(port_str)
        except ValueError:
            import sys

            print(
                f"Warning: Invalid WEAVIATE_GRPC_PORT '{port_str}', using default 50051",
                file=sys.stderr,
            )
            return 50051

    WEAVIATE_GRPC_PORT: int = _parse_grpc_port.__func__()
    OLLAMA_EMBEDDING_MODEL: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "snowflake-arctic-embed:l")
    OLLAMA_API_ENDPOINT: str = os.getenv("OLLAMA_API_ENDPOINT", "http://127.0.0.1:11434")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
