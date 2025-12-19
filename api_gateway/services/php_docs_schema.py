"""
PHP documentation schema for Weaviate.

This module defines the Weaviate collection schema for storing documentation
from the official PHP website (php.net).

Covers:
- Language Reference (types, variables, functions, classes, etc.)
- Function Reference (core functions, extensions)
- Features (error handling, output buffering, etc.)
- Security
- FAQ

Features:
- Stable UUID5 generation for entity identification
- SHA256 content hashing for incremental updates
- Manual vectorization with HNSW index and cosine distance
- Section field for filtering by documentation area

CLI usage:
    python -m api_gateway.services.php_docs_schema status
    python -m api_gateway.services.php_docs_schema create
    python -m api_gateway.services.php_docs_schema delete
"""

from __future__ import annotations

import argparse
import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

import weaviate
from weaviate.classes.aggregate import GroupByAggregate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances
from weaviate.exceptions import WeaviateBaseError

from ..utils.logger import get_logger
from .weaviate_connection import PHP_DOCS_COLLECTION_NAME, WeaviateConnection

logger = get_logger("api_gateway.php_docs_schema")


# -----------------------------------------------------------------------------
# UUID Namespace
# -----------------------------------------------------------------------------

PHP_DOCS_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "php-docs-ns")
"""
UUID5 namespace for PHP documentation entities.

Derived from uuid.NAMESPACE_URL with a fixed seed to ensure deterministic
but globally unique identifiers for all PHP documentation.
"""


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------


def compute_php_content_hash(
    title: str,
    content: str,
    section: str,
) -> str:
    """
    Compute SHA256 hash for PHP doc content.

    Used for change detection during incremental updates.

    Args:
        title: Page title
        content: Main content text
        section: Documentation section (language-ref, function-ref, etc.)

    Returns:
        64-character SHA256 hexdigest
    """
    title_norm = (title or "").strip()
    content_norm = (content or "").strip()
    section_norm = (section or "").strip()

    canonical = f"{title_norm}|{content_norm}|{section_norm}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_php_uuid(url: str, title: str) -> str:
    """
    Generate stable UUID5 for PHP documentation.

    Args:
        url: Full URL of the documentation page
        title: Page title

    Returns:
        UUID string in standard format
    """
    url_norm = (url or "").strip()
    title_norm = (title or "").strip()
    seed = f"{url_norm}|{title_norm}"
    return str(uuid.uuid5(PHP_DOCS_UUID_NAMESPACE, seed))


# -----------------------------------------------------------------------------
# Dataclass
# -----------------------------------------------------------------------------


@dataclass
class PHPDoc:
    """
    Represents a PHP documentation page.

    Attributes:
        title: Page title
        url: Full URL
        content: Main content text
        section: Documentation section (language-ref, function-ref, features, etc.)
        subsection: More specific categorization within section
        breadcrumb: Navigation breadcrumb path
        code_examples: Code snippets from the page
        scraped_at: ISO 8601 datetime
        content_hash: SHA256 hash for change detection
        uuid: Stable UUID5 identifier
    """

    title: str
    url: str
    content: str
    section: str
    subsection: str
    breadcrumb: str
    code_examples: str
    scraped_at: str
    content_hash: str
    uuid: str

    def to_properties(self) -> dict[str, Any]:
        """Convert to Weaviate properties dict."""
        return {
            "title": self.title,
            "url": self.url,
            "content": self.content[:10000],  # Truncate for storage
            "section": self.section,
            "subsection": self.subsection,
            "breadcrumb": self.breadcrumb,
            "code_examples": self.code_examples[:5000],
            "scraped_at": self.scraped_at,
            "content_hash": self.content_hash,
            "uuid": self.uuid,
        }


# -----------------------------------------------------------------------------
# Collection Lifecycle Functions
# -----------------------------------------------------------------------------


def create_php_docs_collection(
    client: weaviate.WeaviateClient,
    force_reindex: bool = False,
) -> None:
    """
    Create the PHPDocs collection in Weaviate.

    Uses manual vectorization with HNSW index and cosine distance.

    Args:
        client: Weaviate client connection
        force_reindex: If True, delete existing collection first
    """
    try:
        exists = client.collections.exists(PHP_DOCS_COLLECTION_NAME)

        if exists and force_reindex:
            logger.info(
                "Deleting existing collection '%s' for reindexing",
                PHP_DOCS_COLLECTION_NAME,
            )
            client.collections.delete(PHP_DOCS_COLLECTION_NAME)
            exists = False

        if not exists:
            logger.info("Creating collection '%s'", PHP_DOCS_COLLECTION_NAME)
            client.collections.create(
                name=PHP_DOCS_COLLECTION_NAME,
                vectorizer_config=Configure.Vectorizer.none(),
                vector_index_config=Configure.VectorIndex.hnsw(
                    distance_metric=VectorDistances.COSINE,
                ),
                properties=[
                    Property(name="title", data_type=DataType.TEXT),
                    Property(name="url", data_type=DataType.TEXT),
                    Property(name="content", data_type=DataType.TEXT),
                    Property(name="section", data_type=DataType.TEXT),
                    Property(name="subsection", data_type=DataType.TEXT),
                    Property(name="breadcrumb", data_type=DataType.TEXT),
                    Property(name="code_examples", data_type=DataType.TEXT),
                    Property(name="scraped_at", data_type=DataType.TEXT),
                    Property(name="content_hash", data_type=DataType.TEXT),
                    Property(name="uuid", data_type=DataType.TEXT),
                ],
            )
            logger.info(
                "Collection '%s' created successfully",
                PHP_DOCS_COLLECTION_NAME,
            )
        else:
            logger.info(
                "Collection '%s' already exists",
                PHP_DOCS_COLLECTION_NAME,
            )
    except WeaviateBaseError as exc:
        logger.error(
            "Weaviate error creating collection '%s': %s",
            PHP_DOCS_COLLECTION_NAME,
            exc,
        )
        raise
    except Exception as exc:
        logger.exception(
            "Unexpected error creating collection '%s': %s",
            PHP_DOCS_COLLECTION_NAME,
            exc,
        )
        raise


def delete_php_docs_collection(client: weaviate.WeaviateClient) -> bool:
    """
    Delete the PHPDocs collection.

    Returns:
        True if deleted, False if it didn't exist
    """
    try:
        if client.collections.exists(PHP_DOCS_COLLECTION_NAME):
            logger.info("Deleting collection '%s'", PHP_DOCS_COLLECTION_NAME)
            client.collections.delete(PHP_DOCS_COLLECTION_NAME)
            logger.info("Collection '%s' deleted", PHP_DOCS_COLLECTION_NAME)
            return True
        logger.info("Collection '%s' does not exist", PHP_DOCS_COLLECTION_NAME)
        return False
    except WeaviateBaseError as exc:
        logger.error("Failed to delete collection: %s", exc)
        raise


def php_docs_collection_exists(client: weaviate.WeaviateClient) -> bool:
    """Check if the PHPDocs collection exists."""
    return client.collections.exists(PHP_DOCS_COLLECTION_NAME)


def get_php_docs_stats(client: weaviate.WeaviateClient) -> dict[str, Any]:
    """
    Get statistics for the PHPDocs collection.

    Returns:
        Dict with exists, object_count, and section_counts
    """
    if not client.collections.exists(PHP_DOCS_COLLECTION_NAME):
        return {
            "exists": False,
            "object_count": 0,
            "section_counts": {},
        }

    collection = client.collections.get(PHP_DOCS_COLLECTION_NAME)

    # Total count
    agg = collection.aggregate.over_all(total_count=True)
    total = agg.total_count or 0

    # Breakdown by section
    section_counts: dict[str, int] = {}
    try:
        group_agg = collection.aggregate.over_all(
            group_by=GroupByAggregate(prop="section"),
            total_count=True,
        )
        for group in group_agg.groups:
            section = group.grouped_by.value
            count = group.total_count or 0
            if section:
                section_counts[section] = count
    except Exception as exc:
        logger.warning("Failed to get section breakdown: %s", exc)

    logger.info(
        "Collection '%s' stats: %d objects, sections: %s",
        PHP_DOCS_COLLECTION_NAME,
        total,
        section_counts,
    )

    return {
        "exists": True,
        "object_count": total,
        "section_counts": section_counts,
    }


# -----------------------------------------------------------------------------
# CLI Entry Point
# -----------------------------------------------------------------------------


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Manage PHPDocs Weaviate collection")
    parser.add_argument(
        "command",
        choices=["status", "create", "delete"],
        help="Command to execute",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reindex when creating",
    )

    args = parser.parse_args()

    with WeaviateConnection() as client:
        if args.command == "status":
            stats = get_php_docs_stats(client)
            print("\nPHPDocs Collection Status")
            print("=" * 40)
            print(f"Exists: {stats['exists']}")
            print(f"Total objects: {stats['object_count']}")
            if stats["section_counts"]:
                print("\nBy section:")
                for section, count in sorted(stats["section_counts"].items()):
                    print(f"  {section}: {count}")

        elif args.command == "create":
            create_php_docs_collection(client, force_reindex=args.force)
            print("Collection created successfully")

        elif args.command == "delete":
            deleted = delete_php_docs_collection(client)
            if deleted:
                print("Collection deleted")
            else:
                print("Collection did not exist")


if __name__ == "__main__":
    main()
