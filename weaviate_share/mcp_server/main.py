"""
MCP Codebase Search Server (Standalone Version).

Provides semantic search over documentation and code stored in Weaviate.
Uses STDIO transport for communication with Claude Code/VS Code.

Tools:
    - search_documentation: Search markdown documentation
    - search_code: Search code entities (functions, classes, styles, etc.)
    - search_codebase: Combined search across docs and code
    - search_drupal_api: Search Drupal 11.x API reference (16k+ entities)
    - search_congressional: Search House member press releases and voting records
    - search_mdn: Search MDN JavaScript and Web API documentation

Usage:
    python main.py
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, List, Optional, Union

import httpx
import weaviate
from mcp.server.fastmcp import FastMCP

# Configuration from environment variables (with sensible defaults)
WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "localhost")
WEAVIATE_HTTP_PORT = int(os.getenv("WEAVIATE_HTTP_PORT", "8080"))
WEAVIATE_GRPC_PORT = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))
OLLAMA_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "snowflake-arctic-embed:l")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Collection names
DOCUMENTATION_COLLECTION = "Documentation"
CODE_ENTITY_COLLECTION = "CodeEntity"
DRUPAL_API_COLLECTION = "DrupalAPI"
CONGRESSIONAL_COLLECTION = "CongressionalData"
MDN_JS_COLLECTION = "MDNJavaScript"
MDN_WEBAPI_COLLECTION = "MDNWebAPIs"

# Limit validation
MIN_LIMIT = 1
MAX_LIMIT = 100

# Configure logging to stderr (required for STDIO transport)
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
    force=True,
)
logger = logging.getLogger("mcp.search")

# Create FastMCP server instance
mcp = FastMCP("Codebase Search")

# Type aliases
SearchResult = Dict[str, Any]
SearchResponse = Union[List[SearchResult], Dict[str, str]]

# Valid filter values
VALID_ENTITY_TYPES = {"function", "method", "class", "variable", "interface", "type", "style", "animation", "struct", "trait", "enum", "impl", "constant", "static"}
VALID_LANGUAGES = {"python", "typescript", "javascript", "css", "rust"}


def _get_weaviate_client():
    """Create a Weaviate client connection."""
    return weaviate.connect_to_local(
        host=WEAVIATE_HOST,
        port=WEAVIATE_HTTP_PORT,
        grpc_port=WEAVIATE_GRPC_PORT,
    )


def _get_embedding(text: str) -> List[float]:
    """Get embedding vector from Ollama for semantic search."""
    url = f"{OLLAMA_ENDPOINT}/api/embeddings"
    response = httpx.post(
        url,
        json={"model": EMBEDDING_MODEL, "prompt": text},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["embedding"]


@mcp.tool()
def search_documentation(query: str, limit: int = 10) -> SearchResponse:
    """
    Search documentation using semantic similarity.

    Args:
        query: Search query text
        limit: Maximum number of results (1-100, default: 10)

    Returns:
        List of matching documentation chunks with title, content, file_path, section
    """
    if not isinstance(limit, int) or limit < MIN_LIMIT or limit > MAX_LIMIT:
        return {"error": "invalid_limit", "message": f"limit must be {MIN_LIMIT}-{MAX_LIMIT}"}

    logger.info("Searching documentation: query=%r, limit=%d", query, limit)

    try:
        query_vector = _get_embedding(query)

        with _get_weaviate_client() as client:
            if not client.collections.exists(DOCUMENTATION_COLLECTION):
                return {"error": "collection_not_found"}

            collection = client.collections.get(DOCUMENTATION_COLLECTION)
            response = collection.query.near_vector(near_vector=query_vector, limit=limit)

            results: List[SearchResult] = []
            for obj in response.objects:
                results.append({
                    "title": obj.properties.get("title", ""),
                    "content": obj.properties.get("content", ""),
                    "file_path": obj.properties.get("file_path", ""),
                    "section": obj.properties.get("section", ""),
                })

            logger.info("Found %d results", len(results))
            return results

    except Exception as exc:
        logger.exception("Search failed: %s", exc)
        return {"error": "search_failed", "message": str(exc)}


@mcp.tool()
def search_code(
    query: str,
    limit: int = 10,
    entity_type: Optional[str] = None,
    service_name: Optional[str] = None,
    language: Optional[str] = None,
) -> SearchResponse:
    """
    Search code entities using semantic similarity.

    Args:
        query: Search query text (e.g., "function that handles authentication")
        limit: Maximum number of results (1-100, default: 10)
        entity_type: Filter by type: function, method, class, variable, interface, style, animation
        service_name: Filter by service name
        language: Filter by language: python, typescript, javascript, css, rust

    Returns:
        List of matching code entities with name, signature, file_path, source_code
    """
    if not isinstance(limit, int) or limit < MIN_LIMIT or limit > MAX_LIMIT:
        return {"error": "invalid_limit", "message": f"limit must be {MIN_LIMIT}-{MAX_LIMIT}"}

    if entity_type and entity_type not in VALID_ENTITY_TYPES:
        return {"error": "invalid_entity_type", "message": f"Valid: {', '.join(sorted(VALID_ENTITY_TYPES))}"}
    if language and language not in VALID_LANGUAGES:
        return {"error": "invalid_language", "message": f"Valid: {', '.join(sorted(VALID_LANGUAGES))}"}

    logger.info("Searching code: query=%r, limit=%d", query, limit)

    try:
        query_vector = _get_embedding(query)

        with _get_weaviate_client() as client:
            if not client.collections.exists(CODE_ENTITY_COLLECTION):
                return {"error": "collection_not_found"}

            collection = client.collections.get(CODE_ENTITY_COLLECTION)

            # Build filters
            from weaviate.classes.query import Filter
            filters = []
            if entity_type:
                filters.append(Filter.by_property("entity_type").equal(entity_type))
            if service_name:
                filters.append(Filter.by_property("service_name").equal(service_name))
            if language:
                filters.append(Filter.by_property("language").equal(language))

            combined_filter = None
            if filters:
                combined_filter = filters[0]
                for f in filters[1:]:
                    combined_filter = combined_filter & f

            response = collection.query.near_vector(
                near_vector=query_vector, limit=limit, filters=combined_filter
            )

            results: List[SearchResult] = []
            for obj in response.objects:
                props = obj.properties
                line_start = props.get("line_start", 0)
                file_path = props.get("file_path", "")
                file_ref = f"{file_path}:{line_start}" if line_start else file_path

                source_code = props.get("source_code", "")
                if len(source_code) > 500:
                    source_code = source_code[:500] + "..."

                results.append({
                    "entity_type": props.get("entity_type", ""),
                    "name": props.get("name", ""),
                    "full_name": props.get("full_name", ""),
                    "signature": props.get("signature", ""),
                    "file_path": file_ref,
                    "docstring": props.get("docstring", ""),
                    "source_code": source_code,
                    "service_name": props.get("service_name", ""),
                })

            logger.info("Found %d results", len(results))
            return results

    except Exception as exc:
        logger.exception("Search failed: %s", exc)
        return {"error": "search_failed", "message": str(exc)}


@mcp.tool()
def search_codebase(query: str, limit: int = 10) -> SearchResponse:
    """
    Search across both documentation and code.

    Args:
        query: Search query text
        limit: Maximum total results (1-100, default: 10)

    Returns:
        Combined list from docs and code, each with a 'source' field
    """
    if not isinstance(limit, int) or limit < MIN_LIMIT or limit > MAX_LIMIT:
        return {"error": "invalid_limit", "message": f"limit must be {MIN_LIMIT}-{MAX_LIMIT}"}

    logger.info("Searching codebase: query=%r, limit=%d", query, limit)

    doc_limit = limit // 2
    code_limit = limit - doc_limit
    results: List[SearchResult] = []
    errors: List[str] = []

    doc_results = search_documentation(query, limit=doc_limit)
    if isinstance(doc_results, dict) and "error" in doc_results:
        errors.append(f"docs: {doc_results.get('error')}")
    elif isinstance(doc_results, list):
        for r in doc_results:
            r["source"] = "documentation"
            results.append(r)

    code_results = search_code(query, limit=code_limit)
    if isinstance(code_results, dict) and "error" in code_results:
        errors.append(f"code: {code_results.get('error')}")
    elif isinstance(code_results, list):
        for r in code_results:
            r["source"] = "code"
            results.append(r)

    if not results and errors:
        return {"error": "search_failed", "message": "; ".join(errors)}

    return results


@mcp.tool()
def search_drupal_api(
    query: str,
    limit: int = 10,
    entity_type: Optional[str] = None,
) -> SearchResponse:
    """
    Search Drupal 11.x API reference.

    Args:
        query: Search query text (e.g., "entity storage interface")
        limit: Maximum number of results (1-100, default: 10)
        entity_type: Filter by type: class, interface, trait, function, method, hook, constant

    Returns:
        List of matching Drupal API entities with name, namespace, signature, source_url
    """
    if not isinstance(limit, int) or limit < MIN_LIMIT or limit > MAX_LIMIT:
        return {"error": "invalid_limit", "message": f"limit must be {MIN_LIMIT}-{MAX_LIMIT}"}

    logger.info("Searching Drupal API: query=%r, limit=%d", query, limit)

    try:
        query_vector = _get_embedding(query)

        with _get_weaviate_client() as client:
            if not client.collections.exists(DRUPAL_API_COLLECTION):
                return {"error": "collection_not_found"}

            collection = client.collections.get(DRUPAL_API_COLLECTION)

            combined_filter = None
            if entity_type:
                from weaviate.classes.query import Filter
                combined_filter = Filter.by_property("entity_type").equal(entity_type)

            response = collection.query.near_vector(
                near_vector=query_vector, limit=limit, filters=combined_filter
            )

            results: List[SearchResult] = []
            for obj in response.objects:
                props = obj.properties
                line_num = props.get("line_number", 0)
                file_path = props.get("file_path", "")
                file_ref = f"{file_path}:{line_num}" if line_num else file_path

                desc = props.get("description", "")
                if len(desc) > 500:
                    desc = desc[:500] + "..."

                results.append({
                    "entity_type": props.get("entity_type", ""),
                    "name": props.get("name", ""),
                    "full_name": props.get("full_name", ""),
                    "namespace": props.get("namespace", ""),
                    "signature": props.get("signature", ""),
                    "description": desc,
                    "file_path": file_ref,
                    "source_url": props.get("source_url", ""),
                    "deprecated": props.get("deprecated", ""),
                })

            logger.info("Found %d results", len(results))
            return results

    except Exception as exc:
        logger.exception("Search failed: %s", exc)
        return {"error": "search_failed", "message": str(exc)}


@mcp.tool()
def search_congressional(
    query: str,
    limit: int = 10,
    state: Optional[str] = None,
    party: Optional[str] = None,
    topic: Optional[str] = None,
) -> SearchResponse:
    """
    Search Congressional data (House members, press releases, voting records).

    Args:
        query: Search query text (e.g., "infrastructure bill support", "HR 3668 vote")
        limit: Maximum number of results (1-100, default: 10)
        state: Filter by state abbreviation (e.g., "CA", "TX", "NY")
        party: Filter by party ("Republican", "Democrat")
        topic: Filter by topic (e.g., "votes" for roll call votes, "news", "press")

    Returns:
        List of matching content with member_name, state, party, title, url.
        For votes (topic="votes"), content includes bill info and all member votes as JSON.
    """
    if not isinstance(limit, int) or limit < MIN_LIMIT or limit > MAX_LIMIT:
        return {"error": "invalid_limit", "message": f"limit must be {MIN_LIMIT}-{MAX_LIMIT}"}

    logger.info("Searching Congressional: query=%r, limit=%d, topic=%r", query, limit, topic)

    try:
        query_vector = _get_embedding(query)

        with _get_weaviate_client() as client:
            if not client.collections.exists(CONGRESSIONAL_COLLECTION):
                return {"error": "collection_not_found"}

            collection = client.collections.get(CONGRESSIONAL_COLLECTION)

            from weaviate.classes.query import Filter
            filters = []
            if state:
                filters.append(Filter.by_property("state").equal(state.upper()))
            if party:
                filters.append(Filter.by_property("party").equal(party))
            if topic:
                filters.append(Filter.by_property("topic").equal(topic.lower()))

            combined_filter = None
            if filters:
                combined_filter = filters[0]
                for f in filters[1:]:
                    combined_filter = combined_filter & f

            response = collection.query.near_vector(
                near_vector=query_vector, limit=limit, filters=combined_filter
            )

            results: List[SearchResult] = []
            for obj in response.objects:
                props = obj.properties
                content = props.get("content_text", "")
                obj_topic = props.get("topic", "")
                # Allow longer content for votes (they contain member votes JSON)
                max_content = 10000 if obj_topic == "votes" else 500
                if len(content) > max_content:
                    content = content[:max_content] + "..."

                results.append({
                    "member_name": props.get("member_name", ""),
                    "state": props.get("state", ""),
                    "district": props.get("district", ""),
                    "party": props.get("party", ""),
                    "title": props.get("title", ""),
                    "topic": obj_topic,
                    "content_text": content,
                    "url": props.get("url", ""),
                    "policy_topics": props.get("policy_topics", []),
                })

            logger.info("Found %d results", len(results))
            return results

    except Exception as exc:
        logger.exception("Search failed: %s", exc)
        return {"error": "search_failed", "message": str(exc)}


@mcp.tool()
def search_mdn(
    query: str,
    limit: int = 10,
    collection: Optional[str] = None,
) -> SearchResponse:
    """
    Search MDN Web Docs (JavaScript and Web APIs).

    Args:
        query: Search query text (e.g., "fetch API async await")
        limit: Maximum number of results (1-100, default: 10)
        collection: Filter to "javascript" or "webapi", or None for both

    Returns:
        List of matching MDN docs with title, url, content, source
    """
    if not isinstance(limit, int) or limit < MIN_LIMIT or limit > MAX_LIMIT:
        return {"error": "invalid_limit", "message": f"limit must be {MIN_LIMIT}-{MAX_LIMIT}"}

    if collection and collection not in ("javascript", "webapi"):
        return {"error": "invalid_collection", "message": "Must be 'javascript' or 'webapi'"}

    logger.info("Searching MDN: query=%r, limit=%d", query, limit)

    try:
        query_vector = _get_embedding(query)
        results: List[SearchResult] = []

        collections_to_search = []
        if collection == "javascript" or collection is None:
            collections_to_search.append((MDN_JS_COLLECTION, "javascript"))
        if collection == "webapi" or collection is None:
            collections_to_search.append((MDN_WEBAPI_COLLECTION, "webapi"))

        per_limit = limit if len(collections_to_search) == 1 else limit // 2

        with _get_weaviate_client() as client:
            for col_name, source_name in collections_to_search:
                if not client.collections.exists(col_name):
                    continue

                col = client.collections.get(col_name)
                response = col.query.near_vector(near_vector=query_vector, limit=per_limit)

                for obj in response.objects:
                    props = obj.properties
                    content = props.get("content", "")
                    if len(content) > 500:
                        content = content[:500] + "..."

                    results.append({
                        "title": props.get("title", ""),
                        "url": props.get("url", ""),
                        "content": content,
                        "section_type": props.get("section_type", ""),
                        "source": source_name,
                    })

            logger.info("Found %d results", len(results))
            return results

    except Exception as exc:
        logger.exception("Search failed: %s", exc)
        return {"error": "search_failed", "message": str(exc)}


if __name__ == "__main__":
    mcp.run()
