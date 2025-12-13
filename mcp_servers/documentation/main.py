"""
MCP Codebase Search Server.

Provides semantic search over documentation and code stored in Weaviate using FastMCP.
Uses STDIO transport for communication with VS Code/Claude Desktop.

Tools:
    - search_documentation: Search markdown documentation
    - search_code: Search code entities (functions, classes, styles, etc.)
    - search_codebase: Combined search across docs and code
    - search_drupal_api: Search Drupal 11.x API reference (16k+ entities)
    - search_drupal_module_docs: Search Drupal module READMEs and documentation
    - search_drupal_twig: Search Drupal Twig templates (880+ templates)
    - search_congressional: Search House member press releases and voting records
    - search_mdn: Search MDN JavaScript and Web API documentation

Usage:
    python -m mcp_servers.documentation.main
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, List, Dict, Optional, Union

import httpx
from mcp.server.fastmcp import FastMCP

# Import shared connection utilities from api_gateway
# Add project root to sys.path to enable imports from api_gateway
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from api_gateway.services.weaviate_connection import (  # noqa: E402
    WeaviateConnection,
    DOCUMENTATION_COLLECTION_NAME,
    CODE_ENTITY_COLLECTION_NAME,
    DRUPAL_API_COLLECTION_NAME,
)
from api_gateway.config import settings as api_settings  # noqa: E402
from mcp_servers.documentation import settings  # noqa: E402

# Additional collection names not in weaviate_connection
CONGRESSIONAL_COLLECTION_NAME = "CongressionalData"
MDN_JS_COLLECTION_NAME = "MDNJavaScript"
MDN_WEBAPI_COLLECTION_NAME = "MDNWebAPIs"
DRUPAL_MODULE_DOCS_COLLECTION_NAME = "DrupalModuleDocs"
DRUPAL_TWIG_COLLECTION_NAME = "DrupalTwigTemplates"


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
SearchResult = Dict[str, Any]
SearchResponse = Union[List[SearchResult], Dict[str, str]]

# Valid entity types for code search filtering
VALID_ENTITY_TYPES = {"function", "method", "class", "variable", "interface", "type", "style", "animation", "struct", "trait", "enum", "impl", "constant", "static"}
VALID_LANGUAGES = {"python", "typescript", "javascript", "css", "rust"}


def _get_embedding(text: str) -> List[float]:
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
        return {"error": "invalid_entity_type", "message": f"Valid types: {', '.join(sorted(VALID_ENTITY_TYPES))}"}
    if language and language not in VALID_LANGUAGES:
        return {"error": "invalid_language", "message": f"Valid languages: {', '.join(sorted(VALID_LANGUAGES))}"}

    logger.info(
        "Searching code: query=%r, limit=%d, entity_type=%s, service=%s, language=%s",
        query, limit, entity_type, service_name, language
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
            results: List[SearchResult] = []
            for obj in response.objects:
                props = obj.properties
                line_start = props.get("line_start", 0)
                file_path = props.get("file_path", "")
                file_ref = f"{file_path}:{line_start}" if line_start else file_path

                # Truncate source code for response
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
                    "service_name": props.get("service_name", "core"),
                })

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

    results: List[SearchResult] = []
    errors: List[str] = []

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


@mcp.tool()
def search_drupal_api(
    query: str,
    limit: int = 10,
    entity_type: Optional[str] = None,
) -> SearchResponse:
    """
    Search Drupal 11.x API reference using semantic similarity.

    Searches the DrupalAPI collection for classes, interfaces, functions,
    hooks, and other PHP entities from the Drupal core API.

    Args:
        query: Search query text (e.g., "entity storage interface")
        limit: Maximum number of results (1-100, default: 10)
        entity_type: Filter by type: class, interface, trait, function, method, hook, constant

    Returns:
        On success: List of matching Drupal API entities with:
            - entity_type: Type (class/interface/function/hook/etc.)
            - name: Entity name
            - full_name: Fully qualified name with namespace
            - namespace: PHP namespace
            - signature: Declaration signature
            - description: Documentation description
            - file_path: Path in Drupal source with line number
            - source_url: Link to api.drupal.org
            - deprecated: Deprecation notice if any

        On error: Dict with "error" key describing the failure
    """
    if not isinstance(limit, int) or limit < MIN_LIMIT or limit > MAX_LIMIT:
        return {"error": "invalid_limit", "message": f"limit must be {MIN_LIMIT}-{MAX_LIMIT}"}

    logger.info("Searching Drupal API: query=%r, limit=%d, entity_type=%s", query, limit, entity_type)

    try:
        query_vector = _get_embedding(query)

        with WeaviateConnection(custom_logger=logger) as client:
            if not client.collections.exists(DRUPAL_API_COLLECTION_NAME):
                return {"error": "collection_not_found"}

            collection = client.collections.get(DRUPAL_API_COLLECTION_NAME)

            # Build filter if entity_type specified
            combined_filter = None
            if entity_type:
                from weaviate.classes.query import Filter
                combined_filter = Filter.by_property("entity_type").equal(entity_type)

            response = collection.query.near_vector(
                near_vector=query_vector,
                limit=limit,
                filters=combined_filter,
            )

            results: List[SearchResult] = []
            for obj in response.objects:
                props = obj.properties
                line_num = props.get("line_number", 0)
                file_path = props.get("file_path", "")
                file_ref = f"{file_path}:{line_num}" if line_num else file_path

                results.append({
                    "entity_type": props.get("entity_type", ""),
                    "name": props.get("name", ""),
                    "full_name": props.get("full_name", ""),
                    "namespace": props.get("namespace", ""),
                    "signature": props.get("signature", ""),
                    "description": props.get("description", "")[:500] + "..." if len(props.get("description", "")) > 500 else props.get("description", ""),
                    "file_path": file_ref,
                    "source_url": props.get("source_url", ""),
                    "deprecated": props.get("deprecated", ""),
                })

            logger.info("Found %d Drupal API results for query=%r", len(results), query)
            return results

    except Exception as exc:
        logger.exception("Drupal API search failed: %s", exc)
        return {"error": "search_failed", "message": str(exc)}


@mcp.tool()
def search_drupal_module_docs(
    query: str,
    limit: int = 10,
    module_type: Optional[str] = None,
    module_name: Optional[str] = None,
) -> SearchResponse:
    """
    Search Drupal module documentation (READMEs, markdown files) from installed modules.

    Searches the DrupalModuleDocs collection for documentation from contrib
    and core Drupal modules installed on the remote server.

    Args:
        query: Search query text (e.g., "how to configure webform")
        limit: Maximum number of results (1-100, default: 10)
        module_type: Filter by type: "contrib", "core", or "custom"
        module_name: Filter by specific module name (e.g., "webform", "views")

    Returns:
        On success: List of matching documentation with:
            - title: Section/header title
            - content: Documentation content
            - file_path: Path to source file
            - section: Header level (h1, h2, etc.)
            - module_name: Name of the module
            - module_type: Type (contrib/core/custom)

        On error: Dict with "error" key describing the failure
    """
    if not isinstance(limit, int) or limit < MIN_LIMIT or limit > MAX_LIMIT:
        return {"error": "invalid_limit", "message": f"limit must be {MIN_LIMIT}-{MAX_LIMIT}"}

    if module_type and module_type not in ("contrib", "core", "custom"):
        return {"error": "invalid_module_type", "message": "module_type must be 'contrib', 'core', or 'custom'"}

    logger.info(
        "Searching Drupal module docs: query=%r, limit=%d, module_type=%s, module_name=%s",
        query, limit, module_type, module_name
    )

    try:
        query_vector = _get_embedding(query)

        with WeaviateConnection(custom_logger=logger) as client:
            if not client.collections.exists(DRUPAL_MODULE_DOCS_COLLECTION_NAME):
                return {"error": "collection_not_found"}

            collection = client.collections.get(DRUPAL_MODULE_DOCS_COLLECTION_NAME)

            # Build filters
            from weaviate.classes.query import Filter
            filters = []
            if module_type:
                filters.append(Filter.by_property("module_type").equal(module_type))
            if module_name:
                filters.append(Filter.by_property("module_name").equal(module_name))

            combined_filter = None
            if filters:
                combined_filter = filters[0]
                for f in filters[1:]:
                    combined_filter = combined_filter & f

            response = collection.query.near_vector(
                near_vector=query_vector,
                limit=limit,
                filters=combined_filter,
            )

            results: List[SearchResult] = []
            for obj in response.objects:
                props = obj.properties
                content = props.get("content", "")
                if len(content) > 500:
                    content = content[:500] + "..."

                results.append({
                    "title": props.get("title", ""),
                    "content": content,
                    "file_path": props.get("file_path", ""),
                    "section": props.get("section", ""),
                    "module_name": props.get("module_name", ""),
                    "module_type": props.get("module_type", ""),
                })

            logger.info("Found %d Drupal module docs for query=%r", len(results), query)
            return results

    except Exception as exc:
        logger.exception("Drupal module docs search failed: %s", exc)
        return {"error": "search_failed", "message": str(exc)}


@mcp.tool()
def search_drupal_twig(
    query: str,
    limit: int = 10,
    template_type: Optional[str] = None,
    source_type: Optional[str] = None,
    source_name: Optional[str] = None,
) -> SearchResponse:
    """
    Search Drupal Twig templates from core, contrib modules, and custom themes.

    Searches the DrupalTwigTemplates collection for .html.twig template files.
    Useful for finding how to render specific elements or override templates.

    Args:
        query: Search query text (e.g., "render article title", "node teaser view")
        limit: Maximum number of results (1-100, default: 10)
        template_type: Filter by type: "page", "node", "block", "field", "views", "form", "menu", "region", "other"
        source_type: Filter by source: "core_theme", "core_module", "contrib_module", "custom_theme"
        source_name: Filter by theme/module name (e.g., "olivero", "webform", "views")

    Returns:
        On success: List of matching templates with:
            - template_name: Filename (e.g., "node.html.twig")
            - content: Template code (truncated)
            - file_path: Full path on server
            - source_type: Where it comes from
            - source_name: Theme/module name
            - template_type: Type of template
            - description: Extracted documentation

        On error: Dict with "error" key describing the failure
    """
    if not isinstance(limit, int) or limit < MIN_LIMIT or limit > MAX_LIMIT:
        return {"error": "invalid_limit", "message": f"limit must be {MIN_LIMIT}-{MAX_LIMIT}"}

    valid_template_types = {"page", "node", "block", "field", "views", "form", "comment", "user", "taxonomy", "menu", "region", "html", "maintenance", "status", "table", "pager", "media", "other"}
    if template_type and template_type not in valid_template_types:
        return {"error": "invalid_template_type", "message": f"Valid types: {', '.join(sorted(valid_template_types))}"}

    valid_source_types = {"core_theme", "core_module", "contrib_module", "custom_theme", "other"}
    if source_type and source_type not in valid_source_types:
        return {"error": "invalid_source_type", "message": f"Valid source types: {', '.join(sorted(valid_source_types))}"}

    logger.info(
        "Searching Drupal Twig: query=%r, limit=%d, template_type=%s, source_type=%s, source_name=%s",
        query, limit, template_type, source_type, source_name
    )

    try:
        query_vector = _get_embedding(query)

        with WeaviateConnection(custom_logger=logger) as client:
            if not client.collections.exists(DRUPAL_TWIG_COLLECTION_NAME):
                return {"error": "collection_not_found"}

            collection = client.collections.get(DRUPAL_TWIG_COLLECTION_NAME)

            # Build filters
            from weaviate.classes.query import Filter
            filters = []
            if template_type:
                filters.append(Filter.by_property("template_type").equal(template_type))
            if source_type:
                filters.append(Filter.by_property("source_type").equal(source_type))
            if source_name:
                filters.append(Filter.by_property("source_name").equal(source_name))

            combined_filter = None
            if filters:
                combined_filter = filters[0]
                for f in filters[1:]:
                    combined_filter = combined_filter & f

            response = collection.query.near_vector(
                near_vector=query_vector,
                limit=limit,
                filters=combined_filter,
            )

            results: List[SearchResult] = []
            for obj in response.objects:
                props = obj.properties
                content = props.get("content", "")
                if len(content) > 800:
                    content = content[:800] + "..."

                results.append({
                    "template_name": props.get("template_name", ""),
                    "content": content,
                    "file_path": props.get("file_path", ""),
                    "source_type": props.get("source_type", ""),
                    "source_name": props.get("source_name", ""),
                    "template_type": props.get("template_type", ""),
                    "description": props.get("description", ""),
                })

            logger.info("Found %d Drupal Twig templates for query=%r", len(results), query)
            return results

    except Exception as exc:
        logger.exception("Drupal Twig search failed: %s", exc)
        return {"error": "search_failed", "message": str(exc)}


@mcp.tool()
def search_congressional(
    query: str,
    limit: int = 10,
    state: Optional[str] = None,
    party: Optional[str] = None,
) -> SearchResponse:
    """
    Search Congressional data (House members, press releases, voting records).

    Searches the CongressionalData collection for content from House
    member websites including press releases and policy positions.

    Args:
        query: Search query text (e.g., "infrastructure bill support")
        limit: Maximum number of results (1-100, default: 10)
        state: Filter by state abbreviation (e.g., "CA", "TX", "NY")
        party: Filter by party ("Republican", "Democrat")

    Returns:
        On success: List of matching congressional content with:
            - member_name: Representative's name
            - state: State abbreviation
            - district: District number
            - party: Political party
            - title: Content title
            - content_text: Content snippet (truncated)
            - url: Source URL
            - policy_topics: Related policy topics

        On error: Dict with "error" key describing the failure
    """
    if not isinstance(limit, int) or limit < MIN_LIMIT or limit > MAX_LIMIT:
        return {"error": "invalid_limit", "message": f"limit must be {MIN_LIMIT}-{MAX_LIMIT}"}

    logger.info("Searching Congressional data: query=%r, limit=%d, state=%s, party=%s", query, limit, state, party)

    try:
        query_vector = _get_embedding(query)

        with WeaviateConnection(custom_logger=logger) as client:
            if not client.collections.exists(CONGRESSIONAL_COLLECTION_NAME):
                return {"error": "collection_not_found"}

            collection = client.collections.get(CONGRESSIONAL_COLLECTION_NAME)

            # Build filters
            from weaviate.classes.query import Filter
            filters = []
            if state:
                filters.append(Filter.by_property("state").equal(state.upper()))
            if party:
                filters.append(Filter.by_property("party").equal(party))

            combined_filter = None
            if filters:
                combined_filter = filters[0]
                for f in filters[1:]:
                    combined_filter = combined_filter & f

            response = collection.query.near_vector(
                near_vector=query_vector,
                limit=limit,
                filters=combined_filter,
            )

            results: List[SearchResult] = []
            for obj in response.objects:
                props = obj.properties
                content = props.get("content_text", "")
                if len(content) > 500:
                    content = content[:500] + "..."

                results.append({
                    "member_name": props.get("member_name", ""),
                    "state": props.get("state", ""),
                    "district": props.get("district", ""),
                    "party": props.get("party", ""),
                    "title": props.get("title", ""),
                    "content_text": content,
                    "url": props.get("url", ""),
                    "policy_topics": props.get("policy_topics", []),
                })

            logger.info("Found %d Congressional results for query=%r", len(results), query)
            return results

    except Exception as exc:
        logger.exception("Congressional search failed: %s", exc)
        return {"error": "search_failed", "message": str(exc)}


@mcp.tool()
def search_mdn(
    query: str,
    limit: int = 10,
    collection: Optional[str] = None,
) -> SearchResponse:
    """
    Search MDN Web Docs (JavaScript and Web APIs documentation).

    Searches MDN documentation for JavaScript language features and
    Web APIs. Can search both or filter to one collection.

    Args:
        query: Search query text (e.g., "fetch API async await")
        limit: Maximum number of results (1-100, default: 10)
        collection: Filter to "javascript" or "webapi", or None for both

    Returns:
        On success: List of matching MDN documentation with:
            - title: Article title
            - url: MDN URL
            - content: Content snippet (truncated)
            - section_type: Type of documentation section
            - source: "javascript" or "webapi"

        On error: Dict with "error" key describing the failure
    """
    if not isinstance(limit, int) or limit < MIN_LIMIT or limit > MAX_LIMIT:
        return {"error": "invalid_limit", "message": f"limit must be {MIN_LIMIT}-{MAX_LIMIT}"}

    if collection and collection not in ("javascript", "webapi"):
        return {"error": "invalid_collection", "message": "collection must be 'javascript' or 'webapi'"}

    logger.info("Searching MDN: query=%r, limit=%d, collection=%s", query, limit, collection)

    try:
        query_vector = _get_embedding(query)
        results: List[SearchResult] = []

        # Determine which collections to search
        collections_to_search = []
        if collection == "javascript" or collection is None:
            collections_to_search.append((MDN_JS_COLLECTION_NAME, "javascript"))
        if collection == "webapi" or collection is None:
            collections_to_search.append((MDN_WEBAPI_COLLECTION_NAME, "webapi"))

        # Split limit if searching both
        per_collection_limit = limit if len(collections_to_search) == 1 else limit // 2

        with WeaviateConnection(custom_logger=logger) as client:
            for col_name, source_name in collections_to_search:
                if not client.collections.exists(col_name):
                    logger.warning("Collection %s not found", col_name)
                    continue

                col = client.collections.get(col_name)
                response = col.query.near_vector(
                    near_vector=query_vector,
                    limit=per_collection_limit,
                )

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

            logger.info("Found %d MDN results for query=%r", len(results), query)
            return results

    except Exception as exc:
        logger.exception("MDN search failed: %s", exc)
        return {"error": "search_failed", "message": str(exc)}


if __name__ == "__main__":
    mcp.run()
