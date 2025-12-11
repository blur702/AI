"""
Congressional website content schema for Weaviate.

This module defines the Weaviate collection schema for storing content scraped
from U.S. congressional member websites (House and Senate). Documents are
attributed to individual members and include metadata about their state,
district, and party, along with the original source URLs and RSS feeds.

Features:
- Stable UUID5 generation for entity identification across scrapes
- SHA256 content hashing for change detection during incremental updates
- Manual vectorization with HNSW index and cosine distance

Integration:
- Intended for use by congressional content scrapers that ingest member
  website pages, press releases, and RSS feeds into Weaviate.
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
from .weaviate_connection import CONGRESSIONAL_DATA_COLLECTION_NAME


logger = get_logger("api_gateway.services.congressional_schema")


# -----------------------------------------------------------------------------
# UUID Namespace
# -----------------------------------------------------------------------------

CONGRESSIONAL_DATA_UUID_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "congressional-data-ns",
)
"""
UUID5 namespace for congressional website entities.

Derived from uuid.NAMESPACE_URL with a fixed seed string to ensure deterministic
but globally unique identifiers for all congressional content entities. The same
document scraped multiple times will receive the same UUID, enabling upserts
and incremental updates.
"""


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def compute_congressional_content_hash(
    member_name: str,
    content_text: str,
    title: str,
    url: str,
) -> str:
    """
    Compute SHA256 hash of canonical congressional content fields.

    Used during incremental updates to detect if a member's page or press
    release content has changed since the last scrape. Only semantic content
    fields are included, not timestamps or other mutable metadata.

    Args:
        member_name: Full name of the congressional member
        content_text: Main body text of the page or article
        title: Page or article title
        url: Source URL for the content

    Returns:
        64-character lowercase hexadecimal SHA256 hash string.
    """
    member_norm = (member_name or "").strip()
    content_norm = (content_text or "").strip()
    title_norm = (title or "").strip()
    url_norm = (url or "").strip()

    canonical = f"{member_norm}|{content_norm}|{title_norm}|{url_norm}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_congressional_uuid(
    member_name: str,
    url: str,
    scraped_at: str = "",
) -> str:
    """
    Generate stable UUID5 for congressional website content.

    The UUID is derived from a deterministic seed combining only stable
    identifiers: the member name and content URL. The scraped_at parameter
    is accepted for API compatibility but ignored in UUID computation to
    ensure the same document produces identical UUIDs across re-scrapes.

    This matches the stability guarantees provided by generate_stable_uuid()
    in drupal_api_schema.py and generate_python_docs_uuid() in python_docs_schema.py.

    Args:
        member_name: Full name of the congressional member
        url: Source URL for the content
        scraped_at: Ignored. Kept for API compatibility.

    Returns:
        UUID string in standard 8-4-4-4-12 format.
    """
    member_norm = (member_name or "").strip()
    url_norm = (url or "").strip()
    # Only use stable identifiers (member_name, url) - NOT scraped_at
    # This ensures identical UUIDs for the same content across re-scrapes

    seed = f"{member_norm}|{url_norm}"
    return str(uuid.uuid5(CONGRESSIONAL_DATA_UUID_NAMESPACE, seed))


# -----------------------------------------------------------------------------
# Dataclass Definition
# -----------------------------------------------------------------------------


@dataclass
class CongressionalData:
    """
    Represents a unit of congressional website content for indexing.

    Each instance corresponds to a single document (e.g., web page, press
    release, RSS entry) attributed to a specific member of Congress.
    """

    # Member information
    member_name: str
    state: str
    district: str
    party: str
    chamber: str  # "House" or "Senate"

    # Content fields
    content_text: str
    title: str
    url: str

    # Metadata
    rss_feed_url: str
    content_hash: str
    scraped_at: str  # ISO 8601 datetime string

    # Stable identifier - stored as property for query convenience
    # (Weaviate objects have built-in UUIDs but this enables filtering by string)
    uuid: str

    def to_properties(self) -> Dict[str, Any]:
        """
        Convert dataclass to a properties dict for Weaviate insertion.

        Returns:
            Dictionary suitable for use as the `properties` payload when
            creating or updating objects in the CongressionalData collection.
        """
        return {
            "member_name": self.member_name,
            "state": self.state,
            "district": self.district,
            "party": self.party,
            "chamber": self.chamber,
            "content_text": self.content_text,
            "title": self.title,
            "url": self.url,
            "rss_feed_url": self.rss_feed_url,
            "content_hash": self.content_hash,
            "scraped_at": self.scraped_at,
            "uuid": self.uuid,
        }


# -----------------------------------------------------------------------------
# Collection Lifecycle
# -----------------------------------------------------------------------------


def create_congressional_data_collection(
    client: weaviate.WeaviateClient,
    force_reindex: bool = False,
) -> None:
    """
    Create the CongressionalData collection in Weaviate.

    If the collection already exists and `force_reindex` is True, the existing
    collection is deleted and recreated. Manual vectorization is used, with
    HNSW index and cosine distance for semantic search.

    Args:
        client: Connected Weaviate client
        force_reindex: Whether to drop and recreate the collection if it exists

    Raises:
        WeaviateBaseError: If collection creation or deletion fails.
        Exception: Re-raises unexpected exceptions after logging.
    """
    try:
        exists = client.collections.exists(CONGRESSIONAL_DATA_COLLECTION_NAME)

        if exists and force_reindex:
            logger.info(
                "Force reindex requested; deleting existing collection '%s'",
                CONGRESSIONAL_DATA_COLLECTION_NAME,
            )
            client.collections.delete(CONGRESSIONAL_DATA_COLLECTION_NAME)
            exists = False

        if not exists:
            logger.info(
                "Creating collection '%s'",
                CONGRESSIONAL_DATA_COLLECTION_NAME,
            )
            client.collections.create(
                name=CONGRESSIONAL_DATA_COLLECTION_NAME,
                vectorizer_config=Configure.Vectorizer.none(),
                vector_index_config=Configure.VectorIndex.hnsw(
                    distance_metric=VectorDistances.COSINE,
                ),
                properties=[
                    Property(name="member_name", data_type=DataType.TEXT),
                    Property(name="state", data_type=DataType.TEXT),
                    Property(name="district", data_type=DataType.TEXT),
                    Property(name="party", data_type=DataType.TEXT),
                    Property(name="chamber", data_type=DataType.TEXT),
                    Property(name="content_text", data_type=DataType.TEXT),
                    Property(name="title", data_type=DataType.TEXT),
                    Property(name="url", data_type=DataType.TEXT),
                    Property(name="rss_feed_url", data_type=DataType.TEXT),
                    Property(name="content_hash", data_type=DataType.TEXT),
                    Property(name="scraped_at", data_type=DataType.TEXT),
                    # Stored as TEXT property for query convenience (e.g., filtering by
                    # UUID string). Weaviate objects have built-in UUIDs, but storing
                    # here allows simpler cross-collection lookups without extra joins.
                    Property(name="uuid", data_type=DataType.TEXT),
                ],
            )
            logger.info(
                "Collection '%s' created successfully",
                CONGRESSIONAL_DATA_COLLECTION_NAME,
            )
        else:
            logger.info(
                "Collection '%s' already exists; skipping creation",
                CONGRESSIONAL_DATA_COLLECTION_NAME,
            )
    except WeaviateBaseError as exc:
        logger.error(
            "Weaviate error while creating collection '%s': %s",
            CONGRESSIONAL_DATA_COLLECTION_NAME,
            exc,
        )
        raise
    except Exception as exc:
        logger.exception(
            "Unexpected error while creating collection '%s': %s",
            CONGRESSIONAL_DATA_COLLECTION_NAME,
            exc,
        )
        raise


def delete_congressional_data_collection(
    client: weaviate.WeaviateClient,
) -> bool:
    """
    Delete the CongressionalData collection if it exists.

    Args:
        client: Connected Weaviate client

    Returns:
        True if the collection was deleted, False if it did not exist.

    Raises:
        WeaviateBaseError: If deletion fails due to Weaviate error.
        Exception: Re-raises unexpected exceptions after logging.
    """
    try:
        if client.collections.exists(CONGRESSIONAL_DATA_COLLECTION_NAME):
            logger.info(
                "Deleting collection '%s'",
                CONGRESSIONAL_DATA_COLLECTION_NAME,
            )
            client.collections.delete(CONGRESSIONAL_DATA_COLLECTION_NAME)
            logger.info(
                "Collection '%s' deleted successfully",
                CONGRESSIONAL_DATA_COLLECTION_NAME,
            )
            return True

        logger.info(
            "Collection '%s' does not exist; nothing to delete",
            CONGRESSIONAL_DATA_COLLECTION_NAME,
        )
        return False
    except WeaviateBaseError as exc:
        logger.error(
            "Weaviate error while deleting collection '%s': %s",
            CONGRESSIONAL_DATA_COLLECTION_NAME,
            exc,
        )
        raise
    except Exception as exc:
        logger.exception(
            "Unexpected error while deleting collection '%s': %s",
            CONGRESSIONAL_DATA_COLLECTION_NAME,
            exc,
        )
        raise


def congressional_collection_exists(
    client: weaviate.WeaviateClient,
) -> bool:
    """
    Check if the CongressionalData collection exists.

    Args:
        client: Connected Weaviate client

    Returns:
        True if collection exists, False otherwise.
    """
    exists = client.collections.exists(CONGRESSIONAL_DATA_COLLECTION_NAME)
    logger.debug(
        "Collection '%s' exists: %s",
        CONGRESSIONAL_DATA_COLLECTION_NAME,
        exists,
    )
    return exists


def get_congressional_stats(
    client: weaviate.WeaviateClient,
) -> Dict[str, Any]:
    """
    Return basic statistics for the CongressionalData collection.

    Provides total object count and breakdown by member_name, party, and
    chamber using Weaviate's GroupByAggregate functionality.

    Args:
        client: Connected Weaviate client

    Returns:
        Dictionary with statistics:
        - exists: Whether the collection exists
        - object_count: Total number of documents
        - member_counts: Breakdown by member_name
        - party_counts: Breakdown by party
        - chamber_counts: Breakdown by chamber
    """
    if not client.collections.exists(CONGRESSIONAL_DATA_COLLECTION_NAME):
        logger.info(
            "Collection '%s' does not exist",
            CONGRESSIONAL_DATA_COLLECTION_NAME,
        )
        return {
            "exists": False,
            "object_count": 0,
            "member_counts": {},
            "party_counts": {},
            "chamber_counts": {},
        }

    try:
        collection = client.collections.get(CONGRESSIONAL_DATA_COLLECTION_NAME)

        # Total object count
        agg = collection.aggregate.over_all(total_count=True)
        total = agg.total_count or 0

        # Breakdown by member_name
        member_counts: Dict[str, int] = {}
        try:
            member_group_agg = collection.aggregate.over_all(
                group_by=GroupByAggregate(prop="member_name"),
                total_count=True,
            )
            for group in member_group_agg.groups:
                name = group.grouped_by.value
                count = group.total_count or 0
                if name:
                    member_counts[str(name)] = int(count)
        except Exception as exc:
            logger.warning(
                "Failed to get member_name breakdown for '%s': %s",
                CONGRESSIONAL_DATA_COLLECTION_NAME,
                exc,
            )

        # Breakdown by party
        party_counts: Dict[str, int] = {}
        try:
            party_group_agg = collection.aggregate.over_all(
                group_by=GroupByAggregate(prop="party"),
                total_count=True,
            )
            for group in party_group_agg.groups:
                party = group.grouped_by.value
                count = group.total_count or 0
                if party:
                    party_counts[str(party)] = int(count)
        except Exception as exc:
            logger.warning(
                "Failed to get party breakdown for '%s': %s",
                CONGRESSIONAL_DATA_COLLECTION_NAME,
                exc,
            )

        # Breakdown by chamber
        chamber_counts: Dict[str, int] = {}
        try:
            chamber_group_agg = collection.aggregate.over_all(
                group_by=GroupByAggregate(prop="chamber"),
                total_count=True,
            )
            for group in chamber_group_agg.groups:
                chamber = group.grouped_by.value
                count = group.total_count or 0
                if chamber:
                    chamber_counts[str(chamber)] = int(count)
        except Exception as exc:
            logger.warning(
                "Failed to get chamber breakdown for '%s': %s",
                CONGRESSIONAL_DATA_COLLECTION_NAME,
                exc,
            )

        logger.info(
            "Collection '%s' statistics: %d total objects",
            CONGRESSIONAL_DATA_COLLECTION_NAME,
            total,
        )

        return {
            "exists": True,
            "object_count": int(total),
            "member_counts": member_counts,
            "party_counts": party_counts,
            "chamber_counts": chamber_counts,
        }
    except Exception as exc:
        logger.exception(
            "Failed to get stats for collection '%s': %s",
            CONGRESSIONAL_DATA_COLLECTION_NAME,
            exc,
        )
        raise

