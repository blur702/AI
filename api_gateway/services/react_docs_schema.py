"""
React Ecosystem documentation schema for Weaviate.

This module defines the Weaviate collection schema for storing documentation
from React and popular React ecosystem libraries:

- React (react.dev)
- React Router (reactrouter.com)
- Redux / Redux Toolkit (redux.js.org, redux-toolkit.js.org)
- TanStack Query (tanstack.com/query)
- Next.js (nextjs.org/docs)
- Zustand (docs.pmnd.rs/zustand)
- React Hook Form (react-hook-form.com)

Features:
- Stable UUID5 generation for entity identification
- SHA256 content hashing for incremental updates
- Manual vectorization with HNSW index and cosine distance
- Package/library field for filtering by specific library

CLI usage:
    python -m api_gateway.services.react_docs_schema status
    python -m api_gateway.services.react_docs_schema create
    python -m api_gateway.services.react_docs_schema delete
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
from .weaviate_connection import REACT_ECOSYSTEM_COLLECTION_NAME, WeaviateConnection

logger = get_logger("api_gateway.react_docs_schema")


# -----------------------------------------------------------------------------
# UUID Namespace
# -----------------------------------------------------------------------------

REACT_ECOSYSTEM_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "react-ecosystem-ns")
"""
UUID5 namespace for React ecosystem documentation entities.

Derived from uuid.NAMESPACE_URL with a fixed seed to ensure deterministic
but globally unique identifiers for all React ecosystem documentation.
"""


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------


def compute_react_content_hash(
    title: str,
    content: str,
    package: str,
) -> str:
    """
    Compute SHA256 hash for React ecosystem doc content.

    Used for change detection during incremental updates.

    Args:
        title: Page title
        content: Main content text
        package: Library name (e.g., "react", "react-router")

    Returns:
        64-character SHA256 hexdigest
    """
    title_norm = (title or "").strip()
    content_norm = (content or "").strip()
    package_norm = (package or "").strip()

    canonical = f"{title_norm}|{content_norm}|{package_norm}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_react_uuid(url: str, title: str) -> str:
    """
    Generate stable UUID5 for React ecosystem documentation.

    Args:
        url: Full URL of the documentation page
        title: Page title

    Returns:
        UUID string in standard format
    """
    url_norm = (url or "").strip()
    title_norm = (title or "").strip()
    seed = f"{url_norm}|{title_norm}"
    return str(uuid.uuid5(REACT_ECOSYSTEM_UUID_NAMESPACE, seed))


# -----------------------------------------------------------------------------
# Dataclass
# -----------------------------------------------------------------------------


@dataclass
class ReactEcosystemDoc:
    """
    Represents a React ecosystem documentation page.

    Attributes:
        title: Page title
        url: Full URL
        content: Main content text
        package: Library name (react, react-router, redux, etc.)
        section: Section type (reference, guide, tutorial, api)
        breadcrumb: Navigation breadcrumb path
        code_examples: Code snippets from the page
        scraped_at: ISO 8601 datetime
        content_hash: SHA256 hash for change detection
        uuid: Stable UUID5 identifier
    """

    title: str
    url: str
    content: str
    package: str
    section: str
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
            "package": self.package,
            "section": self.section,
            "breadcrumb": self.breadcrumb,
            "code_examples": self.code_examples[:5000],
            "scraped_at": self.scraped_at,
            "content_hash": self.content_hash,
            "uuid": self.uuid,
        }


# -----------------------------------------------------------------------------
# Collection Lifecycle Functions
# -----------------------------------------------------------------------------


def create_react_ecosystem_collection(
    client: weaviate.WeaviateClient,
    force_reindex: bool = False,
) -> None:
    """
    Create the ReactEcosystem collection in Weaviate.

    Uses manual vectorization with HNSW index and cosine distance.

    Args:
        client: Weaviate client connection
        force_reindex: If True, delete existing collection first
    """
    try:
        exists = client.collections.exists(REACT_ECOSYSTEM_COLLECTION_NAME)

        if exists and force_reindex:
            logger.info(
                "Deleting existing collection '%s' for reindexing",
                REACT_ECOSYSTEM_COLLECTION_NAME,
            )
            client.collections.delete(REACT_ECOSYSTEM_COLLECTION_NAME)
            exists = False

        if not exists:
            logger.info("Creating collection '%s'", REACT_ECOSYSTEM_COLLECTION_NAME)
            client.collections.create(
                name=REACT_ECOSYSTEM_COLLECTION_NAME,
                vectorizer_config=Configure.Vectorizer.none(),
                vector_index_config=Configure.VectorIndex.hnsw(
                    distance_metric=VectorDistances.COSINE,
                ),
                properties=[
                    Property(name="title", data_type=DataType.TEXT),
                    Property(name="url", data_type=DataType.TEXT),
                    Property(name="content", data_type=DataType.TEXT),
                    Property(name="package", data_type=DataType.TEXT),
                    Property(name="section", data_type=DataType.TEXT),
                    Property(name="breadcrumb", data_type=DataType.TEXT),
                    Property(name="code_examples", data_type=DataType.TEXT),
                    Property(name="scraped_at", data_type=DataType.TEXT),
                    Property(name="content_hash", data_type=DataType.TEXT),
                    Property(name="uuid", data_type=DataType.TEXT),
                ],
            )
            logger.info(
                "Collection '%s' created successfully",
                REACT_ECOSYSTEM_COLLECTION_NAME,
            )
        else:
            logger.info(
                "Collection '%s' already exists",
                REACT_ECOSYSTEM_COLLECTION_NAME,
            )
    except WeaviateBaseError as exc:
        logger.error(
            "Weaviate error creating collection '%s': %s",
            REACT_ECOSYSTEM_COLLECTION_NAME,
            exc,
        )
        raise
    except Exception as exc:
        logger.exception(
            "Unexpected error creating collection '%s': %s",
            REACT_ECOSYSTEM_COLLECTION_NAME,
            exc,
        )
        raise


def delete_react_ecosystem_collection(client: weaviate.WeaviateClient) -> bool:
    """
    Delete the ReactEcosystem collection.

    Returns:
        True if deleted, False if it didn't exist
    """
    try:
        if client.collections.exists(REACT_ECOSYSTEM_COLLECTION_NAME):
            logger.info("Deleting collection '%s'", REACT_ECOSYSTEM_COLLECTION_NAME)
            client.collections.delete(REACT_ECOSYSTEM_COLLECTION_NAME)
            logger.info("Collection '%s' deleted", REACT_ECOSYSTEM_COLLECTION_NAME)
            return True
        logger.info("Collection '%s' does not exist", REACT_ECOSYSTEM_COLLECTION_NAME)
        return False
    except WeaviateBaseError as exc:
        logger.error("Failed to delete collection: %s", exc)
        raise


def react_ecosystem_collection_exists(client: weaviate.WeaviateClient) -> bool:
    """Check if the ReactEcosystem collection exists."""
    return client.collections.exists(REACT_ECOSYSTEM_COLLECTION_NAME)


def get_react_ecosystem_stats(client: weaviate.WeaviateClient) -> dict[str, Any]:
    """
    Get statistics for the ReactEcosystem collection.

    Returns:
        Dict with exists, object_count, and package_counts
    """
    if not client.collections.exists(REACT_ECOSYSTEM_COLLECTION_NAME):
        return {
            "exists": False,
            "object_count": 0,
            "package_counts": {},
        }

    collection = client.collections.get(REACT_ECOSYSTEM_COLLECTION_NAME)

    # Total count
    agg = collection.aggregate.over_all(total_count=True)
    total = agg.total_count or 0

    # Breakdown by package
    package_counts: dict[str, int] = {}
    try:
        group_agg = collection.aggregate.over_all(
            group_by=GroupByAggregate(prop="package"),
            total_count=True,
        )
        for group in group_agg.groups:
            pkg = group.grouped_by.value
            count = group.total_count or 0
            if pkg:
                package_counts[pkg] = count
    except Exception as exc:
        logger.warning("Failed to get package breakdown: %s", exc)

    logger.info(
        "Collection '%s' stats: %d objects, packages: %s",
        REACT_ECOSYSTEM_COLLECTION_NAME,
        total,
        package_counts,
    )

    return {
        "exists": True,
        "object_count": total,
        "package_counts": package_counts,
    }


# -----------------------------------------------------------------------------
# CLI Entry Point
# -----------------------------------------------------------------------------


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Manage ReactEcosystem Weaviate collection")
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
            stats = get_react_ecosystem_stats(client)
            print("\nReactEcosystem Collection Status")
            print("=" * 40)
            print(f"Exists: {stats['exists']}")
            print(f"Total objects: {stats['object_count']}")
            if stats["package_counts"]:
                print("\nBy package:")
                for pkg, count in sorted(stats["package_counts"].items()):
                    print(f"  {pkg}: {count}")

        elif args.command == "create":
            create_react_ecosystem_collection(client, force_reindex=args.force)
            print("Collection created successfully")

        elif args.command == "delete":
            deleted = delete_react_ecosystem_collection(client)
            if deleted:
                print("Collection deleted")
            else:
                print("Collection did not exist")


if __name__ == "__main__":
    main()
