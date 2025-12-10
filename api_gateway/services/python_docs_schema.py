"""
Python documentation schema for Weaviate.

This module defines the Weaviate collection schema for storing Python
language documentation across multiple versions (currently 3.13 and 3.12).

The collection stores normalized documentation sections from the official
Python docs, including:

- Language reference pages
- Standard library reference
- Tutorials and how-to guides
- High-level topic overviews

Features:
- Stable UUID5 generation for entity identification (url|title|version seed)
- SHA256 content hashing for incremental updates and change detection
- Manual vectorization supporting snowflake-arctic-embed-l (1024 dimensions)
- HNSW index with cosine distance for semantic search

Integration:
- Used by python_docs_scraper.py for Python docs ingestion
- Managed by scraper_supervisor.py for background scraping and reindexing
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
from .weaviate_connection import PYTHON_DOCS_COLLECTION_NAME


logger = get_logger("api_gateway.python_docs_schema")


# -----------------------------------------------------------------------------
# UUID Namespace
# -----------------------------------------------------------------------------
# UUID5 namespace for deterministic entity identification.
# Derived from uuid.NAMESPACE_URL to ensure a globally unique seed.

PYTHON_DOCS_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "python-docs-ns")


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def compute_python_content_hash(
    title: str,
    content: str,
    version: str,
    section_type: str,
) -> str:
    """
    Compute SHA256 hash of Python documentation content for change detection.

    This hash is used to detect when document content has changed during
    incremental updates. Only the semantic content fields are included,
    not metadata like scraped_at.

    Args:
        title: Page title (e.g., "list.append()")
        content: Main content text (description, examples, syntax)
        version: Python version (e.g., "3.13", "3.12")
        section_type: Section category (e.g., "Library", "Tutorial", "Reference")

    Returns:
        SHA256 hexdigest string (64 characters)

    Example:
        >>> hash_value = compute_python_content_hash(
        ...     title="list.append()",
        ...     content="Append object to the end of the list.",
        ...     version="3.13",
        ...     section_type="Reference",
        ... )
        >>> len(hash_value)
        64
    """
    # Normalize fields: strip whitespace, use empty string for None
    title_norm = (title or "").strip()
    content_norm = (content or "").strip()
    version_norm = (version or "").strip()
    section_type_norm = (section_type or "").strip()

    # Concatenate with pipe separator for canonical representation
    canonical = (
        f"{title_norm}|{content_norm}|{version_norm}|{section_type_norm}"
    )

    # Compute SHA256 hash
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_python_docs_uuid(url: str, title: str, version: str) -> str:
    """
    Generate stable UUID5 for Python documentation entity.

    Uses the PYTHON_DOCS_UUID_NAMESPACE with a seed combining URL, title,
    and version to create deterministic UUIDs. This allows:
    - Detecting existing entities during incremental scraping
    - Consistent entity references across scraper runs
    - Deduplication without database queries
    - Parallel storage of multiple Python versions

    Args:
        url: Full Python docs URL
        title: Page title (e.g., "list.append()")
        version: Python version (e.g., "3.13", "3.12")

    Returns:
        UUID string in standard format (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)

    Example:
        >>> uuid_str = generate_python_docs_uuid(
        ...     url="https://docs.python.org/3/library/stdtypes.html#list.append",
        ...     title="list.append()",
        ...     version="3.13",
        ... )
        >>> len(uuid_str)
        36
    """
    # Normalize inputs
    url_norm = (url or "").strip()
    title_norm = (title or "").strip()
    version_norm = (version or "").strip()

    # Create seed with pipe separator
    seed = f"{url_norm}|{title_norm}|{version_norm}"

    # Generate UUID5 from namespace and seed
    return str(uuid.uuid5(PYTHON_DOCS_UUID_NAMESPACE, seed))


# -----------------------------------------------------------------------------
# Dataclasses
# -----------------------------------------------------------------------------

@dataclass
class PythonDoc:
    """
    Represents a Python documentation page.

    This dataclass stores Python language and standard library documentation
    content from the official Python docs. It includes both content fields
    and metadata for change tracking and identification.

    Attributes:
        title: Page title (e.g., "list.append()")
        url: Full Python docs URL
        content: Main content text (description, examples, syntax)
        version: Python version (e.g., "3.13", "3.12")
        section_type: Section category (e.g., "Library", "Tutorial",
            "Reference", "Language")
        last_modified: ISO 8601 datetime from page metadata
        scraped_at: ISO 8601 datetime when scraped
        content_hash: SHA256 hash for change detection
        uuid: Stable UUID5 for entity identification

    Example:
        >>> doc = PythonDoc(
        ...     title="list.append()",
        ...     url="https://docs.python.org/3/library/stdtypes.html#list.append",
        ...     content="Append object to the end of the list.",
        ...     version="3.13",
        ...     section_type="Reference",
        ...     last_modified="2024-01-15T10:30:00Z",
        ...     scraped_at="2024-12-09T00:00:00Z",
        ...     content_hash="abc123...",
        ...     uuid="550e8400-e29b-41d4-a716-446655440000",
        ... )
    """

    title: str
    url: str
    content: str
    version: str
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
            "version": self.version,
            "section_type": self.section_type,
            "last_modified": self.last_modified,
            "scraped_at": self.scraped_at,
            "content_hash": self.content_hash,
            "uuid": self.uuid,
        }


# -----------------------------------------------------------------------------
# PythonDocs Collection Lifecycle Functions
# -----------------------------------------------------------------------------

def create_python_docs_collection(
    client: weaviate.WeaviateClient,
    force_reindex: bool = False,
) -> None:
    """
    Create the PythonDocs collection in Weaviate.

    Creates a collection with manual vectorization (none) to support
    snowflake-arctic-embed-l embeddings (1024 dimensions). Uses HNSW
    index with cosine distance for semantic search.

    Args:
        client: Weaviate client connection
        force_reindex: If True, delete existing collection first

    Raises:
        WeaviateBaseError: If collection creation fails
    """
    exists = client.collections.exists(PYTHON_DOCS_COLLECTION_NAME)

    if exists and force_reindex:
        logger.info(
            "Deleting existing collection '%s' for reindexing",
            PYTHON_DOCS_COLLECTION_NAME,
        )
        client.collections.delete(PYTHON_DOCS_COLLECTION_NAME)
        exists = False

    if not exists:
        logger.info("Creating collection '%s'", PYTHON_DOCS_COLLECTION_NAME)
        client.collections.create(
            name=PYTHON_DOCS_COLLECTION_NAME,
            vectorizer_config=Configure.Vectorizer.none(),
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
            properties=[
                Property(name="title", data_type=DataType.TEXT),
                Property(name="url", data_type=DataType.TEXT),
                Property(name="content", data_type=DataType.TEXT),
                Property(name="version", data_type=DataType.TEXT),
                Property(name="section_type", data_type=DataType.TEXT),
                Property(name="last_modified", data_type=DataType.TEXT),
                Property(name="scraped_at", data_type=DataType.TEXT),
                Property(name="content_hash", data_type=DataType.TEXT),
                Property(name="uuid", data_type=DataType.TEXT),
            ],
        )
        logger.info(
            "Collection '%s' created successfully",
            PYTHON_DOCS_COLLECTION_NAME,
        )
    else:
        logger.info(
            "Collection '%s' already exists",
            PYTHON_DOCS_COLLECTION_NAME,
        )


def delete_python_docs_collection(client: weaviate.WeaviateClient) -> bool:
    """
    Delete the PythonDocs collection from Weaviate.

    Args:
        client: Weaviate client connection

    Returns:
        True if collection was deleted, False if it didn't exist
    """
    try:
        if client.collections.exists(PYTHON_DOCS_COLLECTION_NAME):
            logger.info("Deleting collection '%s'", PYTHON_DOCS_COLLECTION_NAME)
            client.collections.delete(PYTHON_DOCS_COLLECTION_NAME)
            logger.info(
                "Collection '%s' deleted successfully",
                PYTHON_DOCS_COLLECTION_NAME,
            )
            return True
        logger.info(
            "Collection '%s' does not exist, nothing to delete",
            PYTHON_DOCS_COLLECTION_NAME,
        )
        return False
    except WeaviateBaseError as e:
        logger.error(
            "Failed to delete collection '%s': %s",
            PYTHON_DOCS_COLLECTION_NAME,
            e,
        )
        raise
    except Exception as e:
        logger.exception(
            "Unexpected error deleting collection '%s': %s",
            PYTHON_DOCS_COLLECTION_NAME,
            e,
        )
        raise


def python_docs_collection_exists(client: weaviate.WeaviateClient) -> bool:
    """
    Check if the PythonDocs collection exists.

    Args:
        client: Weaviate client connection

    Returns:
        True if collection exists, False otherwise
    """
    return client.collections.exists(PYTHON_DOCS_COLLECTION_NAME)


def get_python_docs_stats(client: weaviate.WeaviateClient) -> Dict[str, Any]:
    """
    Get statistics for the PythonDocs collection.

    Returns object count and breakdown by version and section_type.

    Args:
        client: Weaviate client connection

    Returns:
        Dict with:
        - exists: Whether collection exists
        - object_count: Total number of objects
        - version_counts: Dict mapping version to count
        - section_counts: Dict mapping section_type to count

    Example:
        >>> stats = get_python_docs_stats(client)
        >>> print(stats)
        {
            "exists": True,
            "object_count": 5000,
            "version_counts": {
                "3.13": 2600,
                "3.12": 2400
            },
            "section_counts": {
                "Library": 3000,
                "Reference": 1500,
                "Tutorial": 500
            }
        }
    """
    if not client.collections.exists(PYTHON_DOCS_COLLECTION_NAME):
        logger.info(
            "Collection '%s' does not exist",
            PYTHON_DOCS_COLLECTION_NAME,
        )
        return {
            "exists": False,
            "object_count": 0,
            "version_counts": {},
            "section_counts": {},
        }

    collection = client.collections.get(PYTHON_DOCS_COLLECTION_NAME)

    # Get total count
    agg = collection.aggregate.over_all(total_count=True)
    total_count = agg.total_count or 0

    # Get breakdown by version
    version_counts: Dict[str, int] = {}
    try:
        version_group_agg = collection.aggregate.over_all(
            group_by=GroupByAggregate(prop="version"),
            total_count=True,
        )
        for group in version_group_agg.groups:
            version = group.grouped_by.value
            count = group.total_count or 0
            if version:
                version_counts[version] = count
    except Exception as e:
        logger.warning(
            "Failed to get version breakdown for '%s': %s",
            PYTHON_DOCS_COLLECTION_NAME,
            e,
        )

    # Get breakdown by section_type
    section_counts: Dict[str, int] = {}
    try:
        section_group_agg = collection.aggregate.over_all(
            group_by=GroupByAggregate(prop="section_type"),
            total_count=True,
        )
        for group in section_group_agg.groups:
            section_type = group.grouped_by.value
            count = group.total_count or 0
            if section_type:
                section_counts[section_type] = count
    except Exception as e:
        logger.warning(
            "Failed to get section_type breakdown for '%s': %s",
            PYTHON_DOCS_COLLECTION_NAME,
            e,
        )

    logger.info(
        "Collection '%s' stats: %d objects, %d versions, %d section types",
        PYTHON_DOCS_COLLECTION_NAME,
        total_count,
        len(version_counts),
        len(section_counts),
    )

    return {
        "exists": True,
        "object_count": total_count,
        "version_counts": version_counts,
        "section_counts": section_counts,
    }


# -----------------------------------------------------------------------------
# Module Exports
# -----------------------------------------------------------------------------
#
# This module exports the following:
#
# Constants:
#   - PYTHON_DOCS_UUID_NAMESPACE: UUID5 namespace for Python docs
#   - PYTHON_DOCS_COLLECTION_NAME: Collection name (from weaviate_connection)
#
# Helper Functions:
#   - compute_python_content_hash(title, content, version, section_type) -> str
#   - generate_python_docs_uuid(url, title, version) -> str
#
# Dataclasses:
#   - PythonDoc: Python documentation entity
#
# PythonDocs Collection Lifecycle:
#   - create_python_docs_collection(client, force_reindex=False)
#   - delete_python_docs_collection(client) -> bool
#   - python_docs_collection_exists(client) -> bool
#   - get_python_docs_stats(client) -> Dict[str, Any]

