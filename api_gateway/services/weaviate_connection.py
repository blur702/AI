"""
Shared Weaviate connection utilities.

Provides a reusable context manager for Weaviate client connections,
used by both doc_ingestion and MCP documentation search server.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import urlparse

import weaviate

from ..config import settings


logger = logging.getLogger(__name__)


class WeaviateConnection:
    """
    Context manager for Weaviate client connection.

    Uses connection settings from api_gateway.config.settings:
    - WEAVIATE_URL: HTTP endpoint (e.g., http://localhost:8080)
    - WEAVIATE_GRPC_PORT: gRPC port (e.g., 50051)

    Usage:
        with WeaviateConnection() as client:
            collection = client.collections.get("Documentation")
            results = collection.query.near_text(query="example")
    """

    def __init__(self, custom_logger: Optional[logging.Logger] = None) -> None:
        """
        Initialize connection manager.

        Args:
            custom_logger: Optional logger to use instead of module logger.
                          Useful for MCP server which logs to stderr.
        """
        self.client: Optional[weaviate.WeaviateClient] = None
        self._logger = custom_logger or logger

    def __enter__(self) -> weaviate.WeaviateClient:
        parsed = urlparse(settings.WEAVIATE_URL)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8080

        self._logger.info(
            "Connecting to Weaviate at %s (host=%s, http_port=%s, grpc_port=%s)",
            settings.WEAVIATE_URL,
            host,
            port,
            settings.WEAVIATE_GRPC_PORT,
        )

        self.client = weaviate.connect_to_local(
            host=host,
            port=port,
            grpc_port=settings.WEAVIATE_GRPC_PORT,
        )
        if not self.client.is_ready():
            self._logger.warning("Weaviate did not report ready() == True")
        return self.client

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.client is not None:
            self._logger.info("Closing Weaviate client")
            self.client.close()


# Collection name constant - shared between ingestion and search
DOCUMENTATION_COLLECTION_NAME = "Documentation"
