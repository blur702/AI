"""
DrupalAPIEntity schema definition for Weaviate.

Stores Drupal 11.x API reference entities (classes, interfaces, traits, functions,
methods, hooks, namespaces, constants) with semantic search capability using manual
Ollama vectorization.

Features:
- Stable UUID generation for incremental updates (uuid5 with Drupal API namespace)
- Content hash (SHA256) for change detection during re-scrapes
- Timestamp tracking for scrape freshness monitoring
- Entity type aggregation for statistics and filtering

This module provides:
- DrupalAPIEntity dataclass for representing Drupal API entities
- Collection lifecycle management functions (create, delete, check, stats)
- Helper functions for uuid and content_hash generation

Usage:
    from api_gateway.services.drupal_api_schema import (
        DrupalAPIEntity,
        create_drupal_api_collection,
        delete_drupal_api_collection,
        collection_exists,
        get_collection_stats,
        compute_content_hash,
        generate_stable_uuid,
    )

    with WeaviateConnection() as client:
        create_drupal_api_collection(client)
        stats = get_collection_stats(client)
        print(f"Drupal API entities: {stats['object_count']}")

Integration Notes:
- Used by drupal_scraper.py to generate entities from api.drupal.org
- Used by drupal_ingestion.py to insert/update entities in Weaviate
- Supports incremental updates via uuid/content_hash comparison
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any, Dict

import weaviate
from weaviate.classes.aggregate import GroupByAggregate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances

from ..utils.logger import get_logger
from .weaviate_connection import DRUPAL_API_COLLECTION_NAME


logger = get_logger("api_gateway.drupal_api_schema")

# Drupal API-specific UUID namespace for stable entity identification.
# Derived from NAMESPACE_URL to ensure uniqueness from other UUID5 namespaces.
DRUPAL_API_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "drupal-api-ns")


def compute_content_hash(
    signature: str,
    parameters: str,
    return_type: str,
    description: str,
) -> str:
    """
    Compute SHA256 hash of canonical entity fields for change detection.

    Used during incremental updates to detect if an entity's content has changed
    since the last scrape. Only fields that represent the "semantic content" of
    the entity are included (not metadata like timestamps or URLs).

    Args:
        signature: Full function/method signature or class declaration
        parameters: JSON string of parameter list
        return_type: Return type annotation
        description: Parsed docblock/description content

    Returns:
        64-character lowercase hexadecimal SHA256 hash string.

    Example:
        >>> hash = compute_content_hash(
        ...     signature="public function id(): string|int",
        ...     parameters='[{"name": "none"}]',
        ...     return_type="string|int",
        ...     description="Returns the entity identifier.",
        ... )
        >>> len(hash)
        64
    """
    canonical = f"{signature}|{parameters}|{return_type}|{description}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_stable_uuid(source_url: str, full_name: str) -> str:
    """
    Generate stable UUID5 for entity using Drupal API namespace.

    Creates a deterministic UUID based on the entity's source URL and fully
    qualified name. This ensures the same entity always gets the same UUID
    across multiple scrapes, enabling upsert operations.

    Uses DRUPAL_API_UUID_NAMESPACE (derived from uuid.NAMESPACE_URL with seed
    "drupal-api-ns") to ensure UUIDs are unique to this project and don't
    collide with other UUID5 implementations using standard namespaces.

    Args:
        source_url: Full URL to the api.drupal.org page
        full_name: Fully qualified entity name (e.g., "Drupal\\Core\\Entity\\EntityInterface")

    Returns:
        36-character UUID string in standard format (8-4-4-4-12).

    Example:
        >>> entity_uuid = generate_stable_uuid(
        ...     source_url="https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21Entity%21EntityInterface.php/interface/EntityInterface/11.x",
        ...     full_name="Drupal\\Core\\Entity\\EntityInterface",
        ... )
        >>> len(entity_uuid)
        36
    """
    seed = f"{source_url}|{full_name}"
    return str(uuid.uuid5(DRUPAL_API_UUID_NAMESPACE, seed))


@dataclass
class DrupalAPIEntity:
    """
    Represents a Drupal API entity for indexing in Weaviate.

    Captures comprehensive metadata from api.drupal.org pages including
    classes, interfaces, traits, functions, methods, hooks, namespaces,
    and constants from the Drupal 11.x codebase.

    Attributes:
        entity_type: Type of entity (class/interface/trait/function/method/hook/namespace/constant)
        name: Simple entity name (e.g., "EntityInterface")
        full_name: Fully qualified name with namespace (e.g., "Drupal\\Core\\Entity\\EntityInterface")
        namespace: PHP namespace (e.g., "Drupal\\Core\\Entity")
        file_path: Relative path in Drupal source (e.g., "core/lib/Drupal/Core/Entity.php")
        line_number: Line number in source file (1-indexed)
        signature: Full signature/declaration (e.g., "interface EntityInterface extends ...")
        parameters: JSON string of parameter list for functions/methods
        return_type: Return type annotation
        description: Parsed description/docblock content
        deprecated: Deprecation notice text (empty string if not deprecated)
        see_also: JSON array of related API references
        related_topics: JSON array of related topics/tags
        source_url: Full URL to api.drupal.org page
        language: Always "php" for Drupal entities
        content_hash: SHA256 hash of canonical fields for change detection
        scraped_at: ISO 8601 datetime string of when entity was scraped
        uuid: Stable UUID5 generated from namespace + source_url|full_name

    Example:
        >>> entity = DrupalAPIEntity(
        ...     entity_type="interface",
        ...     name="EntityInterface",
        ...     full_name="Drupal\\Core\\Entity\\EntityInterface",
        ...     namespace="Drupal\\Core\\Entity",
        ...     file_path="core/lib/Drupal/Core/Entity/EntityInterface.php",
        ...     line_number=15,
        ...     signature="interface EntityInterface extends AccessibleInterface",
        ...     parameters="[]",
        ...     return_type="",
        ...     description="Defines a common interface for all entity objects.",
        ...     deprecated="",
        ...     see_also='["EntityStorageInterface", "ContentEntityInterface"]',
        ...     related_topics='["entity_api", "content_entity"]',
        ...     source_url="https://api.drupal.org/api/drupal/.../EntityInterface/11.x",
        ...     language="php",
        ...     content_hash="a3f5b8c...",
        ...     scraped_at="2025-12-08T10:30:00Z",
        ...     uuid="550e8400-e29b-41d4-a716-446655440000",
        ... )
    """

    entity_type: str
    name: str
    full_name: str
    namespace: str
    file_path: str
    line_number: int
    signature: str
    parameters: str
    return_type: str
    description: str
    deprecated: str
    see_also: str
    related_topics: str
    source_url: str
    language: str
    content_hash: str
    scraped_at: str
    uuid: str

    def to_properties(self) -> Dict[str, Any]:
        """
        Convert to a dictionary suitable for Weaviate insertion.

        Returns:
            Dictionary with all entity fields as key-value pairs,
            ready for insertion into the DrupalAPI collection.
        """
        return {
            "entity_type": self.entity_type,
            "name": self.name,
            "full_name": self.full_name,
            "namespace": self.namespace,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "signature": self.signature,
            "parameters": self.parameters,
            "return_type": self.return_type,
            "description": self.description,
            "deprecated": self.deprecated,
            "see_also": self.see_also,
            "related_topics": self.related_topics,
            "source_url": self.source_url,
            "language": self.language,
            "content_hash": self.content_hash,
            "scraped_at": self.scraped_at,
            "uuid": self.uuid,
        }


def create_drupal_api_collection(
    client: weaviate.WeaviateClient,
    force_reindex: bool = False,
) -> None:
    """
    Create (or recreate) the DrupalAPI collection.

    When `force_reindex` is True, deletes any existing collection first.
    Uses manual vectorization (Configure.Vectorizer.none()) to compute
    embeddings via Python/Ollama before insertion.

    Args:
        client: Connected Weaviate client
        force_reindex: If True, delete existing collection before creating (default: False)

    Raises:
        WeaviateBaseError: If collection creation fails
    """
    exists = client.collections.exists(DRUPAL_API_COLLECTION_NAME)

    if exists and force_reindex:
        logger.info(
            "Deleting existing collection '%s' for reindexing",
            DRUPAL_API_COLLECTION_NAME,
        )
        client.collections.delete(DRUPAL_API_COLLECTION_NAME)
        exists = False

    if not exists:
        logger.info("Creating collection '%s'", DRUPAL_API_COLLECTION_NAME)
        # Use manual vectorization (none) - vectors computed via Python/Ollama
        client.collections.create(
            name=DRUPAL_API_COLLECTION_NAME,
            vectorizer_config=Configure.Vectorizer.none(),
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
            properties=[
                Property(name="entity_type", data_type=DataType.TEXT),
                Property(name="name", data_type=DataType.TEXT),
                Property(name="full_name", data_type=DataType.TEXT),
                Property(name="namespace", data_type=DataType.TEXT),
                Property(name="file_path", data_type=DataType.TEXT),
                Property(name="line_number", data_type=DataType.INT),
                Property(name="signature", data_type=DataType.TEXT),
                Property(name="parameters", data_type=DataType.TEXT),
                Property(name="return_type", data_type=DataType.TEXT),
                Property(name="description", data_type=DataType.TEXT),
                Property(name="deprecated", data_type=DataType.TEXT),
                Property(name="see_also", data_type=DataType.TEXT),
                Property(name="related_topics", data_type=DataType.TEXT),
                Property(name="source_url", data_type=DataType.TEXT),
                Property(name="language", data_type=DataType.TEXT),
                Property(name="content_hash", data_type=DataType.TEXT),
                Property(name="scraped_at", data_type=DataType.TEXT),
                Property(name="uuid", data_type=DataType.TEXT),
            ],
        )
        logger.info("Collection '%s' created successfully", DRUPAL_API_COLLECTION_NAME)
    else:
        logger.info("Collection '%s' already exists", DRUPAL_API_COLLECTION_NAME)


def delete_drupal_api_collection(client: weaviate.WeaviateClient) -> bool:
    """
    Delete the DrupalAPI collection if it exists.

    Args:
        client: Connected Weaviate client

    Returns:
        True if collection was deleted, False if it didn't exist.

    Raises:
        weaviate.exceptions.WeaviateBaseError: If deletion fails due to Weaviate error
        Exception: Re-raises unexpected exceptions after logging
    """
    try:
        if client.collections.exists(DRUPAL_API_COLLECTION_NAME):
            logger.info("Deleting collection '%s'", DRUPAL_API_COLLECTION_NAME)
            client.collections.delete(DRUPAL_API_COLLECTION_NAME)
            logger.info("Collection '%s' deleted successfully", DRUPAL_API_COLLECTION_NAME)
            return True

        logger.info("Collection '%s' does not exist, nothing to delete", DRUPAL_API_COLLECTION_NAME)
        return False

    except weaviate.exceptions.WeaviateBaseError as exc:
        error_msg = f"Weaviate error while deleting collection '{DRUPAL_API_COLLECTION_NAME}': {exc}"
        logger.error(error_msg, exc_info=True)
        raise
    except Exception as exc:
        error_msg = f"Unexpected error while deleting collection '{DRUPAL_API_COLLECTION_NAME}': {exc}"
        logger.error(error_msg, exc_info=True)
        raise


def collection_exists(client: weaviate.WeaviateClient) -> bool:
    """
    Check if the DrupalAPI collection exists.

    Args:
        client: Connected Weaviate client

    Returns:
        True if collection exists, False otherwise.
    """
    exists = client.collections.exists(DRUPAL_API_COLLECTION_NAME)
    logger.debug("Collection '%s' exists: %s", DRUPAL_API_COLLECTION_NAME, exists)
    return exists


def get_collection_stats(client: weaviate.WeaviateClient) -> Dict[str, Any]:
    """
    Return basic statistics for the DrupalAPI collection.

    Provides total object count and breakdown by entity_type using
    Weaviate's GroupByAggregate functionality.

    Args:
        client: Connected Weaviate client

    Returns:
        Dictionary with statistics:
        - exists: Whether the collection exists
        - object_count: Total number of Drupal API entities (0 if collection doesn't exist)
        - entity_counts: Breakdown by entity_type (empty dict if collection doesn't exist)

    Raises:
        Exception: If stats retrieval fails

    Example:
        >>> with WeaviateConnection() as client:
        ...     stats = get_collection_stats(client)
        ...     print(stats)
        {'exists': True, 'object_count': 15234, 'entity_counts': {'class': 2341, 'function': 5678, ...}}
    """
    try:
        if not client.collections.exists(DRUPAL_API_COLLECTION_NAME):
            logger.info("Collection '%s' does not exist", DRUPAL_API_COLLECTION_NAME)
            return {"exists": False, "object_count": 0, "entity_counts": {}}

        collection = client.collections.get(DRUPAL_API_COLLECTION_NAME)
        agg = collection.aggregate.over_all(total_count=True)
        total = agg.total_count or 0

        # Aggregate counts by entity_type
        entity_counts: Dict[str, int] = {}
        grouped_agg = collection.aggregate.over_all(
            group_by=GroupByAggregate(prop="entity_type"),
            total_count=True,
        )
        for group in grouped_agg.groups:
            entity_type = group.grouped_by.value
            count = group.total_count or 0
            if entity_type:
                entity_counts[str(entity_type)] = int(count)

        logger.info(
            "Collection '%s' statistics: %d total objects, entity_counts=%s",
            DRUPAL_API_COLLECTION_NAME,
            total,
            entity_counts,
        )

        return {
            "exists": True,
            "object_count": int(total),
            "entity_counts": entity_counts,
        }
    except Exception as e:
        logger.exception("Failed to get stats for collection '%s': %s", DRUPAL_API_COLLECTION_NAME, e)
        raise
