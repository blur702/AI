"""
CongressionalData schema definition for Weaviate.

Stores congressional member website content and RSS feed entries with semantic
search capability using manual Ollama vectorization.

Features:
- Stable UUID generation for incremental updates (uuid5 with Congressional namespace)
- Content hash (SHA256) for change detection during re-scrapes
- Timestamp tracking for scrape freshness monitoring
- Member/party/state aggregation for statistics and filtering

This module provides:
- CongressionalData dataclass for representing congressional content
- Collection lifecycle management functions (create, delete, check, stats)
- Helper functions for uuid and content_hash generation

Usage:
    from api_gateway.services.congressional_schema import (
        CongressionalData,
        create_congressional_data_collection,
        compute_congressional_content_hash,
        generate_congressional_uuid,
        get_congressional_stats,
    )

    with WeaviateConnection() as client:
        create_congressional_data_collection(client)
        stats = get_congressional_stats(client)
        print(f"Congressional documents: {stats['object_count']}")
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any

import weaviate
from weaviate.classes.aggregate import GroupByAggregate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances

from ..utils.logger import get_logger
from .weaviate_connection import CONGRESSIONAL_DATA_COLLECTION_NAME

logger = get_logger("api_gateway.congressional_schema")

# Congressional-specific UUID namespace for stable entity identification.
CONGRESSIONAL_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "congressional-data-ns")


def compute_congressional_content_hash(
    member_name: str,
    content_text: str,
    title: str,
    url: str,
) -> str:
    """
    Compute SHA256 hash of canonical content fields for change detection.

    Used during incremental updates to detect if content has changed
    since the last scrape.

    Args:
        member_name: Congressional member's name
        content_text: Main content text from the page
        title: Page title
        url: Source URL

    Returns:
        64-character lowercase hexadecimal SHA256 hash string.
    """
    canonical = f"{member_name}|{title}|{content_text}|{url}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_congressional_uuid(member_name: str, url: str) -> str:
    """
    Generate a stable UUID5 for a congressional document.

    Uses the member name and URL to create a deterministic UUID that
    remains consistent across scrapes for the same content.

    Args:
        member_name: Congressional member's name
        url: Source URL of the content

    Returns:
        UUID string in standard format (e.g., "550e8400-e29b-41d4-a716-446655440000")
    """
    canonical = f"{member_name}|{url}"
    return str(uuid.uuid5(CONGRESSIONAL_UUID_NAMESPACE, canonical))


@dataclass
class CongressionalData:
    """
    Represents a congressional document (webpage or RSS entry).

    Attributes:
        member_name: Name of the congressional member
        state: State the member represents (e.g., "CA", "TX")
        district: Congressional district number (e.g., "12", "At-Large")
        party: Political party ("D", "R", "I")
        chamber: "House" or "Senate"
        title: Page or article title
        topic: Inferred topic from URL path
        content_text: Main content text (truncated to 10000 chars)
        url: Source URL
        rss_feed_url: Member's RSS feed URL (if available)
        content_hash: SHA256 hash for change detection
        scraped_at: ISO timestamp of when content was scraped
        uuid: Stable UUID for this document
        policy_topics: LLM-classified policy topics (healthcare, immigration, etc.)
    """

    member_name: str
    state: str
    district: str
    party: str
    chamber: str
    title: str
    topic: str
    content_text: str
    url: str
    rss_feed_url: str = ""
    content_hash: str = ""
    scraped_at: str = ""
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    policy_topics: list[str] = field(default_factory=list)

    def to_properties(self) -> dict[str, Any]:
        """
        Convert to Weaviate properties dict for insertion/update.

        Returns:
            Dictionary of property names to values.
        """
        return {
            "member_name": self.member_name,
            "state": self.state,
            "district": self.district,
            "party": self.party,
            "chamber": self.chamber,
            "title": self.title,
            "topic": self.topic,
            "content_text": self.content_text,
            "url": self.url,
            "rss_feed_url": self.rss_feed_url,
            "content_hash": self.content_hash,
            "scraped_at": self.scraped_at,
            "policy_topics": self.policy_topics,
        }


def create_congressional_data_collection(
    client: weaviate.WeaviateClient,
    force_reindex: bool = False,
) -> None:
    """
    Create the CongressionalData collection in Weaviate if it doesn't exist.

    Uses manual vectorization (vectors provided at insert time via Ollama embeddings)
    with cosine distance for semantic similarity search.

    Args:
        client: Active Weaviate client connection
        force_reindex: If True, delete existing collection before creating

    Raises:
        weaviate.exceptions.WeaviateException: If collection creation fails
    """
    if force_reindex and client.collections.exists(CONGRESSIONAL_DATA_COLLECTION_NAME):
        logger.warning(
            "Force reindex requested - deleting existing '%s' collection",
            CONGRESSIONAL_DATA_COLLECTION_NAME,
        )
        client.collections.delete(CONGRESSIONAL_DATA_COLLECTION_NAME)

    if client.collections.exists(CONGRESSIONAL_DATA_COLLECTION_NAME):
        logger.info(
            "Collection '%s' already exists",
            CONGRESSIONAL_DATA_COLLECTION_NAME,
        )
        return

    logger.info("Creating collection '%s'", CONGRESSIONAL_DATA_COLLECTION_NAME)

    client.collections.create(
        name=CONGRESSIONAL_DATA_COLLECTION_NAME,
        vectorizer_config=Configure.Vectorizer.none(),
        vector_index_config=Configure.VectorIndex.hnsw(
            distance_metric=VectorDistances.COSINE,
        ),
        properties=[
            Property(
                name="member_name",
                data_type=DataType.TEXT,
                description="Name of the congressional member",
            ),
            Property(
                name="state",
                data_type=DataType.TEXT,
                description="State the member represents",
            ),
            Property(
                name="district",
                data_type=DataType.TEXT,
                description="Congressional district number",
            ),
            Property(
                name="party",
                data_type=DataType.TEXT,
                description="Political party (D, R, I)",
            ),
            Property(
                name="chamber",
                data_type=DataType.TEXT,
                description="House or Senate",
            ),
            Property(
                name="title",
                data_type=DataType.TEXT,
                description="Page or article title",
            ),
            Property(
                name="topic",
                data_type=DataType.TEXT,
                description="Inferred topic from URL",
            ),
            Property(
                name="content_text",
                data_type=DataType.TEXT,
                description="Main content text",
            ),
            Property(
                name="url",
                data_type=DataType.TEXT,
                description="Source URL",
            ),
            Property(
                name="rss_feed_url",
                data_type=DataType.TEXT,
                description="Member RSS feed URL",
            ),
            Property(
                name="content_hash",
                data_type=DataType.TEXT,
                description="SHA256 hash for change detection",
            ),
            Property(
                name="scraped_at",
                data_type=DataType.TEXT,
                description="ISO timestamp of scrape time",
            ),
            Property(
                name="policy_topics",
                data_type=DataType.TEXT_ARRAY,
                description="LLM-classified policy topics (healthcare, immigration, etc.)",
            ),
        ],
    )

    logger.info("Collection '%s' created successfully", CONGRESSIONAL_DATA_COLLECTION_NAME)


def delete_congressional_data_collection(client: weaviate.WeaviateClient) -> bool:
    """
    Delete the CongressionalData collection if it exists.

    Args:
        client: Active Weaviate client connection

    Returns:
        True if collection was deleted, False if it didn't exist
    """
    if not client.collections.exists(CONGRESSIONAL_DATA_COLLECTION_NAME):
        logger.info(
            "Collection '%s' does not exist, nothing to delete",
            CONGRESSIONAL_DATA_COLLECTION_NAME,
        )
        return False

    client.collections.delete(CONGRESSIONAL_DATA_COLLECTION_NAME)
    logger.info("Collection '%s' deleted", CONGRESSIONAL_DATA_COLLECTION_NAME)
    return True


def _aggregate_by_property(collection, prop_name: str) -> dict[str, int]:
    """
    Aggregate counts grouped by a property.

    Args:
        collection: Weaviate collection to aggregate
        prop_name: Property name to group by

    Returns:
        Dictionary mapping property values to their counts.
    """
    counts: dict[str, int] = {}
    try:
        group_agg = collection.aggregate.over_all(
            group_by=GroupByAggregate(prop=prop_name),
            total_count=True,
        )
        for group in group_agg.groups:
            value = group.grouped_by.value
            count = group.total_count or 0
            if value:
                counts[str(value)] = int(count)
    except Exception as exc:
        logger.warning("Failed to get %s breakdown: %s", prop_name, exc)
    return counts


def get_congressional_stats(client: weaviate.WeaviateClient) -> dict[str, Any]:
    """
    Get statistics for the CongressionalData collection.

    Returns aggregated counts by member, party, state, and chamber.

    Args:
        client: Active Weaviate client connection

    Returns:
        Dictionary containing:
        - exists: Whether the collection exists
        - object_count: Total number of documents
        - member_counts: Dict of member_name -> count
        - party_counts: Dict of party -> count
        - state_counts: Dict of state -> count
        - chamber_counts: Dict of chamber -> count
    """
    stats: dict[str, Any] = {
        "exists": False,
        "object_count": 0,
        "member_counts": {},
        "party_counts": {},
        "state_counts": {},
        "chamber_counts": {},
    }

    if not client.collections.exists(CONGRESSIONAL_DATA_COLLECTION_NAME):
        return stats

    stats["exists"] = True
    collection = client.collections.get(CONGRESSIONAL_DATA_COLLECTION_NAME)

    # Get total count
    try:
        agg_result = collection.aggregate.over_all(total_count=True)
        stats["object_count"] = agg_result.total_count or 0
    except Exception as exc:
        logger.warning("Failed to get total count: %s", exc)

    # Get breakdowns by property using helper
    stats["member_counts"] = _aggregate_by_property(collection, "member_name")
    stats["party_counts"] = _aggregate_by_property(collection, "party")
    stats["state_counts"] = _aggregate_by_property(collection, "state")
    stats["chamber_counts"] = _aggregate_by_property(collection, "chamber")

    return stats


def migrate_add_policy_topics(client: weaviate.WeaviateClient) -> bool:
    """
    Add policy_topics property to existing CongressionalData collection.

    This is a migration function to add the new property without recreating
    the collection. Safe to call multiple times - will skip if property exists.

    Args:
        client: Active Weaviate client connection

    Returns:
        True if migration was applied or property already exists, False on error
    """
    if not client.collections.exists(CONGRESSIONAL_DATA_COLLECTION_NAME):
        logger.info("Collection does not exist, skipping migration")
        return True

    collection = client.collections.get(CONGRESSIONAL_DATA_COLLECTION_NAME)

    # Check if property already exists
    try:
        config = collection.config.get()
        existing_props = [p.name for p in config.properties]
        if "policy_topics" in existing_props:
            logger.info("policy_topics property already exists")
            return True
    except Exception as exc:
        logger.warning("Could not check existing properties: %s", exc)

    # Add the new property
    try:
        collection.config.add_property(
            Property(
                name="policy_topics",
                data_type=DataType.TEXT_ARRAY,
                description="LLM-classified policy topics (healthcare, immigration, etc.)",
            )
        )
        logger.info("Added policy_topics property to %s", CONGRESSIONAL_DATA_COLLECTION_NAME)
        return True
    except Exception as exc:
        logger.error("Failed to add policy_topics property: %s", exc)
        return False
