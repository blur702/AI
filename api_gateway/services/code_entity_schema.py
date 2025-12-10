"""
CodeEntity schema definition for Weaviate.

Defines the CodeEntity collection schema for storing comprehensive code metadata
(classes, functions, variables, interfaces, types, styles) with semantic search
capability using the `text2vec-ollama` vectorizer.

This module provides:
- CodeEntity dataclass for representing code entities
- Collection lifecycle management functions (create, delete, check, stats)

Usage:
    from api_gateway.services.code_entity_schema import (
        CodeEntity,
        create_code_entity_collection,
        delete_code_entity_collection,
        collection_exists,
        get_collection_stats,
    )

    with WeaviateConnection() as client:
        create_code_entity_collection(client)
        # ... insert entities, query, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import weaviate
from weaviate.classes.aggregate import GroupByAggregate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances

from ..utils.logger import get_logger
from .weaviate_connection import CODE_ENTITY_COLLECTION_NAME


logger = get_logger("api_gateway.code_entity_schema")


@dataclass
class CodeEntity:
    """
    Represents a code entity for indexing in Weaviate.

    Attributes:
        entity_type: Type of code entity (class/function/variable/interface/type/style)
        name: Simple name of the entity
        full_name: Fully qualified name with namespace/module path
        file_path: Relative path from workspace root
        line_start: Starting line number (1-indexed)
        line_end: Ending line number (1-indexed)
        signature: Function/method signature or declaration
        parameters: Parameter list (JSON string for functions/methods)
        return_type: Return type annotation
        docstring: Documentation string/JSDoc/comment
        decorators: Decorator/annotation list (JSON array string)
        modifiers: Access modifiers, async, static, export, etc.
        parent_entity: Parent class/module/namespace name
        language: Source language (python/typescript/javascript/css)
        source_code: Full source code of the entity
        dependencies: Import dependencies (JSON array string)
        relationships: Cross-references to other entities (JSON object string)
        service_name: Name of the AI service (e.g., "comfyui", "alltalk", "yue") or "core" for main project
    """

    entity_type: str
    name: str
    full_name: str
    file_path: str
    line_start: int
    line_end: int
    signature: str
    parameters: str
    return_type: str
    docstring: str
    decorators: str
    modifiers: str
    parent_entity: str
    language: str
    source_code: str
    dependencies: str
    relationships: str
    service_name: str = "core"

    def to_properties(self) -> Dict[str, Any]:
        """Convert to a dictionary suitable for Weaviate insertion."""
        return {
            "entity_type": self.entity_type,
            "name": self.name,
            "full_name": self.full_name,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "signature": self.signature,
            "parameters": self.parameters,
            "return_type": self.return_type,
            "docstring": self.docstring,
            "decorators": self.decorators,
            "modifiers": self.modifiers,
            "parent_entity": self.parent_entity,
            "language": self.language,
            "source_code": self.source_code,
            "dependencies": self.dependencies,
            "relationships": self.relationships,
            "service_name": self.service_name,
        }


def create_code_entity_collection(
    client: weaviate.WeaviateClient,
    force_reindex: bool = False,
) -> None:
    """
    Create (or recreate) the CodeEntity collection.

    When `force_reindex` is True, deletes any existing collection first.

    Args:
        client: Connected Weaviate client
        force_reindex: If True, delete existing collection before creating
    """
    exists = client.collections.exists(CODE_ENTITY_COLLECTION_NAME)

    if exists and force_reindex:
        logger.info(
            "Deleting existing collection '%s' for reindexing",
            CODE_ENTITY_COLLECTION_NAME,
        )
        client.collections.delete(CODE_ENTITY_COLLECTION_NAME)
        exists = False

    if not exists:
        logger.info("Creating collection '%s'", CODE_ENTITY_COLLECTION_NAME)
        # Use manual vectorization (none) to avoid Weaviate's text2vec-ollama connection issues
        # Vectors will be computed via Python and provided during insertion
        client.collections.create(
            name=CODE_ENTITY_COLLECTION_NAME,
            vectorizer_config=Configure.Vectorizer.none(),
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
            properties=[
                Property(name="entity_type", data_type=DataType.TEXT),
                Property(name="name", data_type=DataType.TEXT),
                Property(name="full_name", data_type=DataType.TEXT),
                Property(name="file_path", data_type=DataType.TEXT),
                Property(name="line_start", data_type=DataType.INT),
                Property(name="line_end", data_type=DataType.INT),
                Property(name="signature", data_type=DataType.TEXT),
                Property(name="parameters", data_type=DataType.TEXT),
                Property(name="return_type", data_type=DataType.TEXT),
                Property(name="docstring", data_type=DataType.TEXT),
                Property(name="decorators", data_type=DataType.TEXT),
                Property(name="modifiers", data_type=DataType.TEXT),
                Property(name="parent_entity", data_type=DataType.TEXT),
                Property(name="language", data_type=DataType.TEXT),
                Property(name="source_code", data_type=DataType.TEXT),
                Property(name="dependencies", data_type=DataType.TEXT),
                Property(name="relationships", data_type=DataType.TEXT),
                Property(name="service_name", data_type=DataType.TEXT),
            ],
        )
        logger.info("Collection '%s' created successfully", CODE_ENTITY_COLLECTION_NAME)
    else:
        logger.info("Collection '%s' already exists", CODE_ENTITY_COLLECTION_NAME)


def delete_code_entity_collection(client: weaviate.WeaviateClient) -> bool:
    """
    Delete the CodeEntity collection if it exists.

    Args:
        client: Connected Weaviate client

    Returns:
        True if collection was deleted, False if it didn't exist.
    
    Raises:
        Exception: Re-raises exceptions from Weaviate operations after logging.
    """
    try:
        if client.collections.exists(CODE_ENTITY_COLLECTION_NAME):
            logger.info("Deleting collection '%s'", CODE_ENTITY_COLLECTION_NAME)
            client.collections.delete(CODE_ENTITY_COLLECTION_NAME)
            logger.info("Collection '%s' deleted successfully", CODE_ENTITY_COLLECTION_NAME)
            return True

        logger.info("Collection '%s' does not exist, nothing to delete", CODE_ENTITY_COLLECTION_NAME)
        return False
    
    except weaviate.exceptions.WeaviateBaseError as exc:
        error_msg = f"Weaviate error while deleting collection '{CODE_ENTITY_COLLECTION_NAME}': {exc}"
        logger.error(error_msg, exc_info=True)
        raise
    except Exception as exc:
        error_msg = f"Unexpected error while deleting collection '{CODE_ENTITY_COLLECTION_NAME}': {exc}"
        logger.error(error_msg, exc_info=True)
        raise


def collection_exists(client: weaviate.WeaviateClient) -> bool:
    """
    Check if the CodeEntity collection exists.

    Args:
        client: Connected Weaviate client

    Returns:
        True if collection exists, False otherwise.
    """
    exists = client.collections.exists(CODE_ENTITY_COLLECTION_NAME)
    logger.debug("Collection '%s' exists: %s", CODE_ENTITY_COLLECTION_NAME, exists)
    return exists


def get_collection_stats(client: weaviate.WeaviateClient) -> Dict[str, Any]:
    """
    Return basic statistics for the CodeEntity collection.

    Args:
        client: Connected Weaviate client

    Returns:
        Dictionary with statistics:
        - exists: Whether the collection exists
        - object_count: Total number of code entities (0 if collection doesn't exist)
        - entity_counts: Breakdown by entity_type (empty dict if collection doesn't exist)

    Raises:
        Exception: If stats retrieval fails
    """
    try:
        if not client.collections.exists(CODE_ENTITY_COLLECTION_NAME):
            logger.info("Collection '%s' does not exist", CODE_ENTITY_COLLECTION_NAME)
            return {"exists": False, "object_count": 0, "entity_counts": {}}

        collection = client.collections.get(CODE_ENTITY_COLLECTION_NAME)
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
            CODE_ENTITY_COLLECTION_NAME,
            total,
            entity_counts,
        )

        return {
            "exists": True,
            "object_count": int(total),
            "entity_counts": entity_counts,
        }
    except Exception as e:
        logger.exception("Failed to get stats for collection '%s': %s", CODE_ENTITY_COLLECTION_NAME, e)
        raise
