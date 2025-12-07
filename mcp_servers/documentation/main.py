"""
MCP Documentation Search Server.

Provides semantic search over documentation stored in Weaviate using FastMCP.
Uses STDIO transport for communication with VS Code/Claude Desktop.

Usage:
    python -m mcp_servers.documentation.main
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import List, Dict, Union

from mcp.server.fastmcp import FastMCP

# Import shared connection utilities from api_gateway
# Add project root to sys.path to enable imports from api_gateway
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from api_gateway.services.weaviate_connection import (
    WeaviateConnection,
    DOCUMENTATION_COLLECTION_NAME,
)
from mcp_servers.documentation import settings


# Limit validation constants
MIN_LIMIT = 1
MAX_LIMIT = 100


# Configure logging to stderr only (critical for STDIO transport)
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
    force=True,
)
logger = logging.getLogger("mcp.documentation")


# Create FastMCP server instance
mcp = FastMCP("Documentation Search")


# Type alias for search results
SearchResult = Dict[str, str]
SearchResponse = Union[List[SearchResult], Dict[str, str]]


@mcp.tool()
def search_documentation(query: str, limit: int = 10) -> SearchResponse:
    """
    Search documentation using semantic similarity.

    Searches the Documentation collection in Weaviate for content
    semantically similar to the query. Returns matching documentation
    chunks with their metadata.

    Args:
        query: Search query text
        limit: Maximum number of results (1-100, default: 10)

    Returns:
        On success: List of matching documentation chunks with:
            - title: Section/header title
            - content: Section content
            - file_path: Source file path relative to workspace
            - section: Header level (h1, h2, etc.)

        On error: Dict with "error" key describing the failure:
            - {"error": "collection_not_found"} - Documentation not ingested
            - {"error": "connection_failed", "message": "..."} - Weaviate unreachable
            - {"error": "query_failed", "message": "..."} - Query execution error
            - {"error": "invalid_limit", "message": "..."} - Limit out of range
    """
    # Validate limit parameter
    if not isinstance(limit, int) or limit < MIN_LIMIT or limit > MAX_LIMIT:
        error_msg = f"limit must be an integer between {MIN_LIMIT} and {MAX_LIMIT}, got {limit}"
        logger.warning("Invalid limit parameter: %s", error_msg)
        return {"error": "invalid_limit", "message": error_msg}

    logger.info("Searching documentation: query=%r, limit=%d", query, limit)

    # Attempt connection to Weaviate
    try:
        with WeaviateConnection(custom_logger=logger) as client:
            # Check if collection exists (benign condition - return empty list)
            if not client.collections.exists(DOCUMENTATION_COLLECTION_NAME):
                logger.warning(
                    "Collection '%s' does not exist. Run doc_ingestion first.",
                    DOCUMENTATION_COLLECTION_NAME,
                )
                return {"error": "collection_not_found"}

            # Execute the query
            try:
                collection = client.collections.get(DOCUMENTATION_COLLECTION_NAME)
                response = collection.query.near_text(
                    query=query,
                    limit=limit,
                )
            except Exception as exc:
                error_msg = f"Query execution failed: {exc}"
                logger.exception(error_msg)
                return {"error": "query_failed", "message": str(exc)}

            # Build results
            results: List[SearchResult] = []
            for obj in response.objects:
                results.append({
                    "title": obj.properties.get("title", ""),
                    "content": obj.properties.get("content", ""),
                    "file_path": obj.properties.get("file_path", ""),
                    "section": obj.properties.get("section", ""),
                })

            logger.info("Found %d results for query=%r", len(results), query)
            return results

    except Exception as exc:
        error_msg = f"Failed to connect to Weaviate: {exc}"
        logger.exception(error_msg)
        return {"error": "connection_failed", "message": str(exc)}


if __name__ == "__main__":
    mcp.run()
