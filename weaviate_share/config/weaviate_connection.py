"""
Shared Weaviate connection utilities.

Provides a reusable context manager for Weaviate client connections,
used by both doc_ingestion and MCP documentation search server.
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Optional, Type
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
        """
        Enter context manager and establish Weaviate connection.

        Parses WEAVIATE_URL from settings to extract host and port,
        then creates a local Weaviate client with HTTP and gRPC endpoints.

        Returns:
            Connected WeaviateClient instance ready for queries

        Raises:
            ConnectionError: If unable to connect to Weaviate
        """
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

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """
        Exit context manager and close client connection.

        Args:
            exc_type: Exception type if an exception occurred
            exc_val: Exception value if an exception occurred
            exc_tb: Exception traceback if an exception occurred
        """
        if self.client is not None:
            self._logger.info("Closing Weaviate client")
            self.client.close()


# Collection name constants - shared between ingestion and search
DOCUMENTATION_COLLECTION_NAME = "Documentation"
CODE_ENTITY_COLLECTION_NAME = "CodeEntity"
DRUPAL_API_COLLECTION_NAME = "DrupalAPI"  # Drupal 11.x API reference collection
PYTHON_DOCS_COLLECTION_NAME = "PythonDocs"  # Python documentation collection (3.13 and 3.12)

# MDN documentation collections
MDN_JAVASCRIPT_COLLECTION_NAME = "MDNJavaScript"
MDN_WEBAPIS_COLLECTION_NAME = "MDNWebAPIs"

# Talking head collections
TALKING_HEAD_PROFILES_COLLECTION_NAME = "TalkingHeadProfiles"
CONVERSATION_MEMORY_COLLECTION_NAME = "ConversationMemory"
VOICE_CLONES_COLLECTION_NAME = "VoiceClones"

# AI/ML library documentation collections
PYTORCH_DOCS_COLLECTION_NAME = "PyTorchDocs"
TENSORFLOW_DOCS_COLLECTION_NAME = "TensorFlowDocs"
SKLEARN_DOCS_COLLECTION_NAME = "ScikitLearnDocs"

# Web framework documentation collections
DJANGO_DOCS_COLLECTION_NAME = "DjangoDocs"
FLASK_DOCS_COLLECTION_NAME = "FlaskDocs"
FASTAPI_DOCS_COLLECTION_NAME = "FastAPIDocs"

# Image processing library documentation collections
PILLOW_DOCS_COLLECTION_NAME = "PillowDocs"
OPENCV_DOCS_COLLECTION_NAME = "OpenCVDocs"

# Web scraping library documentation collections
BS4_DOCS_COLLECTION_NAME = "BeautifulSoupDocs"
SCRAPY_DOCS_COLLECTION_NAME = "ScrapyDocs"

# IDE/Editor documentation collections
VSCODE_DOCS_COLLECTION_NAME = "VSCodeDocs"

# React ecosystem documentation collections
REACT_ECOSYSTEM_COLLECTION_NAME = "ReactEcosystem"  # React, React Router, Redux, etc.

# TypeScript documentation collection
TYPESCRIPT_DOCS_COLLECTION_NAME = "TypeScriptDocs"  # TypeScript language documentation

# PHP documentation collection
PHP_DOCS_COLLECTION_NAME = "PHPDocs"  # PHP language documentation from php.net

# Congressional data collection
CONGRESSIONAL_DATA_COLLECTION_NAME = "CongressionalData"  # US Congress member websites
