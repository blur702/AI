"""
MCP Codebase Search Server.

Provides semantic search over documentation and code stored in Weaviate using FastMCP.
Uses STDIO transport for communication with VS Code/Claude Desktop.

Tools:
    - search_documentation: Search markdown documentation
    - search_code: Search code entities (functions, classes, styles, etc.)
    - search_codebase: Combined search across docs and code

Usage:
    python -m mcp_servers.documentation.main
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Union

import httpx
from mcp.server.fastmcp import FastMCP

# Import shared connection utilities from api_gateway
# Add project root to sys.path to enable imports from api_gateway
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from api_gateway.config import settings as api_settings  # noqa: E402
from api_gateway.services.weaviate_connection import (  # noqa: E402
    CODE_ENTITY_COLLECTION_NAME,
    DOCUMENTATION_COLLECTION_NAME,
    WeaviateConnection,
)
from mcp_servers.documentation import settings  # noqa: E402

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
mcp = FastMCP("Codebase Search")


# Type aliases for search results
SearchResult = dict[str, Any]
SearchResponse = Union[list[SearchResult], dict[str, str]]

# Valid entity types for code search filtering
VALID_ENTITY_TYPES = {
    "function",
    "method",
    "class",
    "variable",
    "interface",
    "type",
    "style",
    "animation",
    "struct",
    "trait",
    "enum",
    "impl",
    "constant",
    "static",
}
VALID_LANGUAGES = {"python", "typescript", "javascript", "css", "rust"}


def _get_embedding(text: str) -> list[float]:
    """Get embedding vector from Ollama for semantic search."""
    url = f"{api_settings.OLLAMA_API_ENDPOINT}/api/embeddings"
    response = httpx.post(
        url,
        json={"model": api_settings.OLLAMA_EMBEDDING_MODEL, "prompt": text},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["embedding"]


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

            # Execute the query using near_vector (manual vectorization)
            try:
                query_vector = _get_embedding(query)
                collection = client.collections.get(DOCUMENTATION_COLLECTION_NAME)
                response = collection.query.near_vector(
                    near_vector=query_vector,
                    limit=limit,
                )
            except Exception as exc:
                error_msg = f"Query execution failed: {exc}"
                logger.exception(error_msg)
                return {"error": "query_failed", "message": str(exc)}

            # Build results
            results: list[SearchResult] = []
            for obj in response.objects:
                results.append(
                    {
                        "title": obj.properties.get("title", ""),
                        "content": obj.properties.get("content", ""),
                        "file_path": obj.properties.get("file_path", ""),
                        "section": obj.properties.get("section", ""),
                    }
                )

            logger.info("Found %d results for query=%r", len(results), query)
            return results

    except Exception as exc:
        error_msg = f"Failed to connect to Weaviate: {exc}"
        logger.exception(error_msg)
        return {"error": "connection_failed", "message": str(exc)}


@mcp.tool()
def search_code(
    query: str,
    limit: int = 10,
    entity_type: str | None = None,
    service_name: str | None = None,
    language: str | None = None,
) -> SearchResponse:
    """
    Search code entities using semantic similarity.

    Searches the CodeEntity collection in Weaviate for functions, classes,
    methods, variables, interfaces, types, styles, and animations that
    semantically match the query.

    Args:
        query: Search query text (e.g., "function that handles authentication")
        limit: Maximum number of results (1-100, default: 10)
        entity_type: Filter by type: function, method, class, variable, interface, type, style, animation
        service_name: Filter by service: core, alltalk, audiocraft, comfyui, diffrhythm, musicgpt, stable_audio, wan2gp, yue
        language: Filter by language: python, typescript, javascript, css

    Returns:
        On success: List of matching code entities with:
            - entity_type: Type of code entity
            - name: Entity name
            - full_name: Fully qualified name
            - signature: Function/class signature
            - file_path: Source file path with line number (e.g., "api_gateway/app.py:42")
            - docstring: Documentation string
            - source_code: Source code snippet (truncated to 500 chars)
            - service_name: Service the entity belongs to

        On error: Dict with "error" key describing the failure
    """
    # Validate limit
    if not isinstance(limit, int) or limit < MIN_LIMIT or limit > MAX_LIMIT:
        return {"error": "invalid_limit", "message": f"limit must be {MIN_LIMIT}-{MAX_LIMIT}"}

    # Validate filters
    if entity_type and entity_type not in VALID_ENTITY_TYPES:
        return {
            "error": "invalid_entity_type",
            "message": f"Valid types: {', '.join(sorted(VALID_ENTITY_TYPES))}",
        }
    if language and language not in VALID_LANGUAGES:
        return {
            "error": "invalid_language",
            "message": f"Valid languages: {', '.join(sorted(VALID_LANGUAGES))}",
        }

    logger.info(
        "Searching code: query=%r, limit=%d, entity_type=%s, service=%s, language=%s",
        query,
        limit,
        entity_type,
        service_name,
        language,
    )

    try:
        # Get embedding for semantic search
        try:
            query_vector = _get_embedding(query)
        except Exception as exc:
            logger.exception("Failed to get embedding: %s", exc)
            return {"error": "embedding_failed", "message": str(exc)}

        with WeaviateConnection(custom_logger=logger) as client:
            if not client.collections.exists(CODE_ENTITY_COLLECTION_NAME):
                logger.warning("Collection '%s' does not exist", CODE_ENTITY_COLLECTION_NAME)
                return {"error": "collection_not_found"}

            collection = client.collections.get(CODE_ENTITY_COLLECTION_NAME)

            # Build filters if specified
            from weaviate.classes.query import Filter

            filters = []
            if entity_type:
                filters.append(Filter.by_property("entity_type").equal(entity_type))
            if service_name:
                filters.append(Filter.by_property("service_name").equal(service_name))
            if language:
                filters.append(Filter.by_property("language").equal(language))

            # Combine filters with AND
            combined_filter = None
            if filters:
                combined_filter = filters[0]
                for f in filters[1:]:
                    combined_filter = combined_filter & f

            # Execute vector search
            try:
                response = collection.query.near_vector(
                    near_vector=query_vector,
                    limit=limit,
                    filters=combined_filter,
                )
            except Exception as exc:
                logger.exception("Query failed: %s", exc)
                return {"error": "query_failed", "message": str(exc)}

            # Build results
            results: list[SearchResult] = []
            for obj in response.objects:
                props = obj.properties
                line_start = props.get("line_start", 0)
                file_path = props.get("file_path", "")
                file_ref = f"{file_path}:{line_start}" if line_start else file_path

                # Truncate source code for response
                source_code = props.get("source_code", "")
                if len(source_code) > 500:
                    source_code = source_code[:500] + "..."

                results.append(
                    {
                        "entity_type": props.get("entity_type", ""),
                        "name": props.get("name", ""),
                        "full_name": props.get("full_name", ""),
                        "signature": props.get("signature", ""),
                        "file_path": file_ref,
                        "docstring": props.get("docstring", ""),
                        "source_code": source_code,
                        "service_name": props.get("service_name", "core"),
                    }
                )

            logger.info("Found %d code results for query=%r", len(results), query)
            return results

    except Exception as exc:
        logger.exception("Failed to connect to Weaviate: %s", exc)
        return {"error": "connection_failed", "message": str(exc)}


@mcp.tool()
def search_codebase(query: str, limit: int = 10) -> SearchResponse:
    """
    Search across both documentation and code using semantic similarity.

    Performs a unified search across the Documentation and CodeEntity
    collections, returning combined results. Useful for questions like
    "how does X work?" that may have answers in both docs and code.

    Args:
        query: Search query text
        limit: Maximum total results (1-100, default: 10). Results are split
               roughly evenly between docs and code.

    Returns:
        On success: List of results, each with:
            - source: "documentation" or "code"
            - Plus all fields from the respective search tool

        On error: Dict with "error" key describing the failure
    """
    if not isinstance(limit, int) or limit < MIN_LIMIT or limit > MAX_LIMIT:
        return {"error": "invalid_limit", "message": f"limit must be {MIN_LIMIT}-{MAX_LIMIT}"}

    logger.info("Searching codebase: query=%r, limit=%d", query, limit)

    # Split limit between docs and code
    doc_limit = limit // 2
    code_limit = limit - doc_limit

    results: list[SearchResult] = []
    errors: list[str] = []

    # Search documentation
    doc_results = search_documentation(query, limit=doc_limit)
    if isinstance(doc_results, dict) and "error" in doc_results:
        errors.append(f"docs: {doc_results.get('error')}")
    elif isinstance(doc_results, list):
        for r in doc_results:
            r["source"] = "documentation"
            results.append(r)

    # Search code
    code_results = search_code(query, limit=code_limit)
    if isinstance(code_results, dict) and "error" in code_results:
        errors.append(f"code: {code_results.get('error')}")
    elif isinstance(code_results, list):
        for r in code_results:
            r["source"] = "code"
            results.append(r)

    # If all searches failed, return error
    if not results and errors:
        return {"error": "search_failed", "message": "; ".join(errors)}

    logger.info("Found %d combined results for query=%r", len(results), query)
    return results


if __name__ == "__main__":
    mcp.run()
