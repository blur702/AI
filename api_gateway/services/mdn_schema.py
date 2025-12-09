"""
MDN documentation schema for Weaviate.

This module defines the Weaviate collection schemas for storing MDN (Mozilla Developer Network)
documentation. It provides two separate collections:

1. **MDNJavaScript** - JavaScript language documentation including:
   - Reference pages (Array, Object, String methods, etc.)
   - Guides and tutorials
   - Operators and statements

2. **MDNWebAPIs** - Web platform API documentation including:
   - CSS properties and selectors
   - HTML elements and attributes
   - Web APIs (DOM, Fetch, WebSocket, etc.)

Features:
- Stable UUID5 generation for entity identification (url|title seed)
- SHA256 content hashing for incremental updates and change detection
- Manual vectorization supporting snowflake-arctic-embed-l (1024 dimensions)
- HNSW index with cosine distance for semantic search

Integration:
- Used by mdn_javascript_scraper.py for JavaScript docs
- Used by mdn_webapis_scraper.py for CSS/HTML/Web API docs
- Managed by scraper_supervisor.py for background scraping

CLI usage (from project root):
    python -m api_gateway.services.mdn_schema status
    python -m api_gateway.services.mdn_schema create --collection javascript
    python -m api_gateway.services.mdn_schema create --collection webapis
    python -m api_gateway.services.mdn_schema delete --collection javascript
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any, Dict

import weaviate
from weaviate.classes.aggregate import GroupByAggregate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances
from weaviate.exceptions import WeaviateBaseError

from ..utils.logger import get_logger
from .weaviate_connection import MDN_JAVASCRIPT_COLLECTION_NAME, MDN_WEBAPIS_COLLECTION_NAME


logger = get_logger("api_gateway.mdn_schema")


# -----------------------------------------------------------------------------
# UUID Namespaces
# -----------------------------------------------------------------------------
# UUID5 namespaces for deterministic entity identification.
# Derived from uuid.NAMESPACE_URL to ensure globally unique seeds.

MDN_JAVASCRIPT_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "mdn-javascript-ns")
MDN_WEBAPIS_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "mdn-webapis-ns")


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def compute_mdn_content_hash(title: str, content: str, section_type: str) -> str:
    """
    Compute SHA256 hash of MDN document content for change detection.

    This hash is used to detect when document content has changed during
    incremental updates. Only the semantic content fields are included,
    not metadata like scraped_at.

    Args:
        title: Page title (e.g., "Array.prototype.map()")
        content: Main content text (description, examples, syntax)
        section_type: Section category (e.g., "Reference", "Guide")

    Returns:
        SHA256 hexdigest string (64 characters)

    Example:
        >>> hash = compute_mdn_content_hash(
        ...     title="Array.prototype.map()",
        ...     content="The map() method creates a new array...",
        ...     section_type="Reference"
        ... )
        >>> len(hash)
        64
    """
    # Normalize fields: strip whitespace, use empty string for None
    title_norm = (title or "").strip()
    content_norm = (content or "").strip()
    section_type_norm = (section_type or "").strip()

    # Concatenate with pipe separator for canonical representation
    canonical = f"{title_norm}|{content_norm}|{section_type_norm}"

    # Compute SHA256 hash
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_mdn_javascript_uuid(url: str, title: str) -> str:
    """
    Generate stable UUID5 for MDN JavaScript documentation entity.

    Uses the MDN_JAVASCRIPT_UUID_NAMESPACE with a seed combining URL and title
    to create deterministic UUIDs. This allows:
    - Detecting existing entities during incremental scraping
    - Consistent entity references across scraper runs
    - Deduplication without database queries

    Args:
        url: Full MDN URL (e.g., "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/...")
        title: Page title (e.g., "Array.prototype.map()")

    Returns:
        UUID string in standard format (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)

    Example:
        >>> uuid = generate_mdn_javascript_uuid(
        ...     url="https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/map",
        ...     title="Array.prototype.map()"
        ... )
        >>> len(uuid)
        36
    """
    # Normalize inputs
    url_norm = (url or "").strip()
    title_norm = (title or "").strip()

    # Create seed with pipe separator
    seed = f"{url_norm}|{title_norm}"

    # Generate UUID5 from namespace and seed
    return str(uuid.uuid5(MDN_JAVASCRIPT_UUID_NAMESPACE, seed))


def generate_mdn_webapis_uuid(url: str, title: str) -> str:
    """
    Generate stable UUID5 for MDN Web APIs documentation entity.

    Uses the MDN_WEBAPIS_UUID_NAMESPACE with a seed combining URL and title
    to create deterministic UUIDs. This allows:
    - Detecting existing entities during incremental scraping
    - Consistent entity references across scraper runs
    - Deduplication without database queries

    Args:
        url: Full MDN URL (e.g., "https://developer.mozilla.org/en-US/docs/Web/CSS/...")
        title: Page title (e.g., "display")

    Returns:
        UUID string in standard format (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)

    Example:
        >>> uuid = generate_mdn_webapis_uuid(
        ...     url="https://developer.mozilla.org/en-US/docs/Web/CSS/display",
        ...     title="display"
        ... )
        >>> len(uuid)
        36
    """
    # Normalize inputs
    url_norm = (url or "").strip()
    title_norm = (title or "").strip()

    # Create seed with pipe separator
    seed = f"{url_norm}|{title_norm}"

    # Generate UUID5 from namespace and seed
    return str(uuid.uuid5(MDN_WEBAPIS_UUID_NAMESPACE, seed))


# -----------------------------------------------------------------------------
# Dataclasses
# -----------------------------------------------------------------------------

@dataclass
class MDNJavaScriptDoc:
    """
    Represents an MDN JavaScript documentation page.

    This dataclass stores JavaScript language reference and guide content
    from MDN. It includes both content fields and metadata for change
    tracking and identification.

    Attributes:
        title: Page title (e.g., "Array.prototype.map()")
        url: Full MDN URL
        content: Main content text (description, examples, syntax)
        section_type: Section category (e.g., "Reference", "Guide", "Tutorial")
        last_modified: ISO 8601 datetime from MDN page metadata
        scraped_at: ISO 8601 datetime when scraped
        content_hash: SHA256 hash for change detection
        uuid: Stable UUID5 for entity identification

    Example:
        >>> doc = MDNJavaScriptDoc(
        ...     title="Array.prototype.map()",
        ...     url="https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/map",
        ...     content="The map() method creates a new array populated with the results...",
        ...     section_type="Reference",
        ...     last_modified="2024-01-15T10:30:00Z",
        ...     scraped_at="2024-12-09T00:00:00Z",
        ...     content_hash="abc123...",
        ...     uuid="550e8400-e29b-41d4-a716-446655440000"
        ... )
    """

    title: str
    url: str
    content: str
    section_type: str
    last_modified: str
    scraped_at: str
    content_hash: str
    uuid: str

    def to_properties(self) -> Dict[str, Any]:
        """
        Convert to Weaviate properties dict for insertion.

        Returns:
            Dict with all fields formatted for Weaviate insertion.
        """
        return {
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "section_type": self.section_type,
            "last_modified": self.last_modified,
            "scraped_at": self.scraped_at,
            "content_hash": self.content_hash,
            "uuid": self.uuid,
        }


@dataclass
class MDNWebAPIDoc:
    """
    Represents an MDN Web APIs documentation page.

    This dataclass stores CSS, HTML, and Web API reference content from MDN.
    It includes both content fields and metadata for change tracking and
    identification.

    Attributes:
        title: Page title (e.g., "display", "HTMLElement", "fetch()")
        url: Full MDN URL
        content: Main content text (description, examples, syntax)
        section_type: Section category (e.g., "CSS", "HTML", "WebAPI")
        last_modified: ISO 8601 datetime from MDN page metadata
        scraped_at: ISO 8601 datetime when scraped
        content_hash: SHA256 hash for change detection
        uuid: Stable UUID5 for entity identification

    Example:
        >>> doc = MDNWebAPIDoc(
        ...     title="display",
        ...     url="https://developer.mozilla.org/en-US/docs/Web/CSS/display",
        ...     content="The display CSS property sets whether an element is treated...",
        ...     section_type="CSS",
        ...     last_modified="2024-01-10T08:15:00Z",
        ...     scraped_at="2024-12-09T00:00:00Z",
        ...     content_hash="def456...",
        ...     uuid="550e8400-e29b-41d4-a716-446655440001"
        ... )
    """

    title: str
    url: str
    content: str
    section_type: str
    last_modified: str
    scraped_at: str
    content_hash: str
    uuid: str

    def to_properties(self) -> Dict[str, Any]:
        """
        Convert to Weaviate properties dict for insertion.

        Returns:
            Dict with all fields formatted for Weaviate insertion.
        """
        return {
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "section_type": self.section_type,
            "last_modified": self.last_modified,
            "scraped_at": self.scraped_at,
            "content_hash": self.content_hash,
            "uuid": self.uuid,
        }


# -----------------------------------------------------------------------------
# MDNJavaScript Collection Lifecycle Functions
# -----------------------------------------------------------------------------

def create_mdn_javascript_collection(
    client: weaviate.WeaviateClient,
    force_reindex: bool = False,
) -> None:
    """
    Create the MDNJavaScript collection in Weaviate.

    Creates a collection with manual vectorization (none) to support
    snowflake-arctic-embed-l embeddings (1024 dimensions). Uses HNSW
    index with cosine distance for semantic search.

    Args:
        client: Weaviate client connection
        force_reindex: If True, delete existing collection first

    Raises:
        WeaviateBaseError: If collection creation fails
    """
    exists = client.collections.exists(MDN_JAVASCRIPT_COLLECTION_NAME)

    if exists and force_reindex:
        logger.info(
            "Deleting existing collection '%s' for reindexing",
            MDN_JAVASCRIPT_COLLECTION_NAME,
        )
        client.collections.delete(MDN_JAVASCRIPT_COLLECTION_NAME)
        exists = False

    if not exists:
        logger.info("Creating collection '%s'", MDN_JAVASCRIPT_COLLECTION_NAME)
        client.collections.create(
            name=MDN_JAVASCRIPT_COLLECTION_NAME,
            vectorizer_config=Configure.Vectorizer.none(),
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
            properties=[
                Property(name="title", data_type=DataType.TEXT),
                Property(name="url", data_type=DataType.TEXT),
                Property(name="content", data_type=DataType.TEXT),
                Property(name="section_type", data_type=DataType.TEXT),
                Property(name="last_modified", data_type=DataType.TEXT),
                Property(name="scraped_at", data_type=DataType.TEXT),
                Property(name="content_hash", data_type=DataType.TEXT),
                Property(name="uuid", data_type=DataType.TEXT),
            ],
        )
        logger.info(
            "Collection '%s' created successfully",
            MDN_JAVASCRIPT_COLLECTION_NAME,
        )
    else:
        logger.info(
            "Collection '%s' already exists",
            MDN_JAVASCRIPT_COLLECTION_NAME,
        )


def delete_mdn_javascript_collection(client: weaviate.WeaviateClient) -> bool:
    """
    Delete the MDNJavaScript collection from Weaviate.

    Args:
        client: Weaviate client connection

    Returns:
        True if collection was deleted, False if it didn't exist
    """
    try:
        if client.collections.exists(MDN_JAVASCRIPT_COLLECTION_NAME):
            logger.info("Deleting collection '%s'", MDN_JAVASCRIPT_COLLECTION_NAME)
            client.collections.delete(MDN_JAVASCRIPT_COLLECTION_NAME)
            logger.info(
                "Collection '%s' deleted successfully",
                MDN_JAVASCRIPT_COLLECTION_NAME,
            )
            return True
        else:
            logger.info(
                "Collection '%s' does not exist, nothing to delete",
                MDN_JAVASCRIPT_COLLECTION_NAME,
            )
            return False
    except WeaviateBaseError as e:
        logger.error(
            "Failed to delete collection '%s': %s",
            MDN_JAVASCRIPT_COLLECTION_NAME,
            e,
        )
        raise
    except Exception as e:
        logger.exception(
            "Unexpected error deleting collection '%s': %s",
            MDN_JAVASCRIPT_COLLECTION_NAME,
            e,
        )
        raise


def mdn_javascript_collection_exists(client: weaviate.WeaviateClient) -> bool:
    """
    Check if the MDNJavaScript collection exists.

    Args:
        client: Weaviate client connection

    Returns:
        True if collection exists, False otherwise
    """
    return client.collections.exists(MDN_JAVASCRIPT_COLLECTION_NAME)


def get_mdn_javascript_stats(client: weaviate.WeaviateClient) -> Dict[str, Any]:
    """
    Get statistics for the MDNJavaScript collection.

    Returns object count and breakdown by section_type.

    Args:
        client: Weaviate client connection

    Returns:
        Dict with:
        - exists: Whether collection exists
        - object_count: Total number of objects
        - section_counts: Dict mapping section_type to count

    Example:
        >>> stats = get_mdn_javascript_stats(client)
        >>> print(stats)
        {
            "exists": True,
            "object_count": 1500,
            "section_counts": {
                "Reference": 1200,
                "Guide": 250,
                "Tutorial": 50
            }
        }
    """
    if not client.collections.exists(MDN_JAVASCRIPT_COLLECTION_NAME):
        logger.info(
            "Collection '%s' does not exist",
            MDN_JAVASCRIPT_COLLECTION_NAME,
        )
        return {
            "exists": False,
            "object_count": 0,
            "section_counts": {},
        }

    collection = client.collections.get(MDN_JAVASCRIPT_COLLECTION_NAME)

    # Get total count
    agg = collection.aggregate.over_all(total_count=True)
    total_count = agg.total_count or 0

    # Get breakdown by section_type
    section_counts: Dict[str, int] = {}
    try:
        group_agg = collection.aggregate.over_all(
            group_by=GroupByAggregate(prop="section_type"),
            total_count=True,
        )
        for group in group_agg.groups:
            section_type = group.grouped_by.value
            count = group.total_count or 0
            if section_type:
                section_counts[section_type] = count
    except Exception as e:
        logger.warning(
            "Failed to get section_type breakdown for '%s': %s",
            MDN_JAVASCRIPT_COLLECTION_NAME,
            e,
        )

    logger.info(
        "Collection '%s' stats: %d objects, %d section types",
        MDN_JAVASCRIPT_COLLECTION_NAME,
        total_count,
        len(section_counts),
    )

    return {
        "exists": True,
        "object_count": total_count,
        "section_counts": section_counts,
    }


# -----------------------------------------------------------------------------
# MDNWebAPIs Collection Lifecycle Functions
# -----------------------------------------------------------------------------

def create_mdn_webapis_collection(
    client: weaviate.WeaviateClient,
    force_reindex: bool = False,
) -> None:
    """
    Create the MDNWebAPIs collection in Weaviate.

    Creates a collection with manual vectorization (none) to support
    snowflake-arctic-embed-l embeddings (1024 dimensions). Uses HNSW
    index with cosine distance for semantic search.

    Args:
        client: Weaviate client connection
        force_reindex: If True, delete existing collection first

    Raises:
        WeaviateBaseError: If collection creation fails
    """
    exists = client.collections.exists(MDN_WEBAPIS_COLLECTION_NAME)

    if exists and force_reindex:
        logger.info(
            "Deleting existing collection '%s' for reindexing",
            MDN_WEBAPIS_COLLECTION_NAME,
        )
        client.collections.delete(MDN_WEBAPIS_COLLECTION_NAME)
        exists = False

    if not exists:
        logger.info("Creating collection '%s'", MDN_WEBAPIS_COLLECTION_NAME)
        client.collections.create(
            name=MDN_WEBAPIS_COLLECTION_NAME,
            vectorizer_config=Configure.Vectorizer.none(),
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
            properties=[
                Property(name="title", data_type=DataType.TEXT),
                Property(name="url", data_type=DataType.TEXT),
                Property(name="content", data_type=DataType.TEXT),
                Property(name="section_type", data_type=DataType.TEXT),
                Property(name="last_modified", data_type=DataType.TEXT),
                Property(name="scraped_at", data_type=DataType.TEXT),
                Property(name="content_hash", data_type=DataType.TEXT),
                Property(name="uuid", data_type=DataType.TEXT),
            ],
        )
        logger.info(
            "Collection '%s' created successfully",
            MDN_WEBAPIS_COLLECTION_NAME,
        )
    else:
        logger.info(
            "Collection '%s' already exists",
            MDN_WEBAPIS_COLLECTION_NAME,
        )


def delete_mdn_webapis_collection(client: weaviate.WeaviateClient) -> bool:
    """
    Delete the MDNWebAPIs collection from Weaviate.

    Args:
        client: Weaviate client connection

    Returns:
        True if collection was deleted, False if it didn't exist
    """
    try:
        if client.collections.exists(MDN_WEBAPIS_COLLECTION_NAME):
            logger.info("Deleting collection '%s'", MDN_WEBAPIS_COLLECTION_NAME)
            client.collections.delete(MDN_WEBAPIS_COLLECTION_NAME)
            logger.info(
                "Collection '%s' deleted successfully",
                MDN_WEBAPIS_COLLECTION_NAME,
            )
            return True
        else:
            logger.info(
                "Collection '%s' does not exist, nothing to delete",
                MDN_WEBAPIS_COLLECTION_NAME,
            )
            return False
    except WeaviateBaseError as e:
        logger.error(
            "Failed to delete collection '%s': %s",
            MDN_WEBAPIS_COLLECTION_NAME,
            e,
        )
        raise
    except Exception as e:
        logger.exception(
            "Unexpected error deleting collection '%s': %s",
            MDN_WEBAPIS_COLLECTION_NAME,
            e,
        )
        raise


def mdn_webapis_collection_exists(client: weaviate.WeaviateClient) -> bool:
    """
    Check if the MDNWebAPIs collection exists.

    Args:
        client: Weaviate client connection

    Returns:
        True if collection exists, False otherwise
    """
    return client.collections.exists(MDN_WEBAPIS_COLLECTION_NAME)


def get_mdn_webapis_stats(client: weaviate.WeaviateClient) -> Dict[str, Any]:
    """
    Get statistics for the MDNWebAPIs collection.

    Returns object count and breakdown by section_type.

    Args:
        client: Weaviate client connection

    Returns:
        Dict with:
        - exists: Whether collection exists
        - object_count: Total number of objects
        - section_counts: Dict mapping section_type to count

    Example:
        >>> stats = get_mdn_webapis_stats(client)
        >>> print(stats)
        {
            "exists": True,
            "object_count": 3000,
            "section_counts": {
                "CSS": 800,
                "HTML": 500,
                "WebAPI": 1700
            }
        }
    """
    if not client.collections.exists(MDN_WEBAPIS_COLLECTION_NAME):
        logger.info(
            "Collection '%s' does not exist",
            MDN_WEBAPIS_COLLECTION_NAME,
        )
        return {
            "exists": False,
            "object_count": 0,
            "section_counts": {},
        }

    collection = client.collections.get(MDN_WEBAPIS_COLLECTION_NAME)

    # Get total count
    agg = collection.aggregate.over_all(total_count=True)
    total_count = agg.total_count or 0

    # Get breakdown by section_type
    section_counts: Dict[str, int] = {}
    try:
        group_agg = collection.aggregate.over_all(
            group_by=GroupByAggregate(prop="section_type"),
            total_count=True,
        )
        for group in group_agg.groups:
            section_type = group.grouped_by.value
            count = group.total_count or 0
            if section_type:
                section_counts[section_type] = count
    except Exception as e:
        logger.warning(
            "Failed to get section_type breakdown for '%s': %s",
            MDN_WEBAPIS_COLLECTION_NAME,
            e,
        )

    logger.info(
        "Collection '%s' stats: %d objects, %d section types",
        MDN_WEBAPIS_COLLECTION_NAME,
        total_count,
        len(section_counts),
    )

    return {
        "exists": True,
        "object_count": total_count,
        "section_counts": section_counts,
    }


# -----------------------------------------------------------------------------
# Module Exports
# -----------------------------------------------------------------------------
#
# This module exports the following:
#
# Constants:
#   - MDN_JAVASCRIPT_UUID_NAMESPACE: UUID5 namespace for JavaScript docs
#   - MDN_WEBAPIS_UUID_NAMESPACE: UUID5 namespace for Web APIs docs
#   - MDN_JAVASCRIPT_COLLECTION_NAME: Collection name (from weaviate_connection)
#   - MDN_WEBAPIS_COLLECTION_NAME: Collection name (from weaviate_connection)
#
# Helper Functions:
#   - compute_mdn_content_hash(title, content, section_type) -> str
#   - generate_mdn_javascript_uuid(url, title) -> str
#   - generate_mdn_webapis_uuid(url, title) -> str
#
# Dataclasses:
#   - MDNJavaScriptDoc: JavaScript documentation entity
#   - MDNWebAPIDoc: Web APIs documentation entity
#
# MDNJavaScript Collection Lifecycle:
#   - create_mdn_javascript_collection(client, force_reindex=False)
#   - delete_mdn_javascript_collection(client) -> bool
#   - mdn_javascript_collection_exists(client) -> bool
#   - get_mdn_javascript_stats(client) -> Dict[str, Any]
#
# MDNWebAPIs Collection Lifecycle:
#   - create_mdn_webapis_collection(client, force_reindex=False)
#   - delete_mdn_webapis_collection(client) -> bool
#   - mdn_webapis_collection_exists(client) -> bool
#   - get_mdn_webapis_stats(client) -> Dict[str, Any]
