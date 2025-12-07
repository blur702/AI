"""
Talking Head schema definitions for Weaviate.

Defines three collections for the talking head system:
- TalkingHeadProfiles: Avatar configurations and personality settings
- ConversationMemory: Chat history with semantic search
- VoiceClones: Voice cloning profiles and metadata

All collections use text2vec-ollama vectorizer for semantic search.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import weaviate
from weaviate.classes.aggregate import GroupByAggregate
from weaviate.classes.config import Configure, DataType, Property

from ..config import settings
from ..utils.logger import get_logger
from .weaviate_connection import (
    TALKING_HEAD_PROFILES_COLLECTION_NAME,
    CONVERSATION_MEMORY_COLLECTION_NAME,
    VOICE_CLONES_COLLECTION_NAME,
    WeaviateConnection,
)

logger = get_logger("api_gateway.talking_head_schema")


# =============================================================================
# Dataclass Definitions
# =============================================================================


@dataclass
class TalkingHeadProfile:
    """
    Represents an avatar profile for talking head generation.

    Attributes:
        avatar_id: Unique identifier for the avatar
        avatar_name: Display name of the avatar
        avatar_type: Type of avatar (sadtalker/live2d/vrm)
        reference_image_path: Path to reference image (for SadTalker)
        voice_profile_id: Reference to VoiceClones collection
        personality_prompt: System prompt defining personality (VECTORIZED)
        memory_context: Long-term memory summary (VECTORIZED)
        created_at: ISO 8601 timestamp of creation
        last_used: ISO 8601 timestamp of last use
    """

    avatar_id: str
    avatar_name: str
    avatar_type: str
    reference_image_path: str
    voice_profile_id: str
    personality_prompt: str
    memory_context: str
    created_at: str
    last_used: str

    def to_properties(self) -> Dict[str, Any]:
        """Convert to dictionary for Weaviate insertion."""
        return {
            "avatar_id": self.avatar_id,
            "avatar_name": self.avatar_name,
            "avatar_type": self.avatar_type,
            "reference_image_path": self.reference_image_path,
            "voice_profile_id": self.voice_profile_id,
            "personality_prompt": self.personality_prompt,
            "memory_context": self.memory_context,
            "created_at": self.created_at,
            "last_used": self.last_used,
        }


@dataclass
class ConversationMessage:
    """
    Represents a single conversation turn for memory storage.

    Attributes:
        conversation_id: Unique conversation session identifier
        avatar_id: Reference to TalkingHeadProfiles
        user_id: User identifier (for multi-user support)
        timestamp: ISO 8601 timestamp of message
        user_message: User's input text (VECTORIZED)
        avatar_response: Avatar's response text (VECTORIZED)
        emotion_tags: JSON array of emotion labels (e.g., ["happy", "excited"])
        context_summary: Brief summary of conversation context (VECTORIZED)
    """

    conversation_id: str
    avatar_id: str
    user_id: str
    timestamp: str
    user_message: str
    avatar_response: str
    emotion_tags: str  # JSON array string
    context_summary: str

    def to_properties(self) -> Dict[str, Any]:
        """Convert to dictionary for Weaviate insertion."""
        return {
            "conversation_id": self.conversation_id,
            "avatar_id": self.avatar_id,
            "user_id": self.user_id,
            "timestamp": self.timestamp,
            "user_message": self.user_message,
            "avatar_response": self.avatar_response,
            "emotion_tags": self.emotion_tags,
            "context_summary": self.context_summary,
        }


@dataclass
class VoiceClone:
    """
    Represents a voice cloning profile.

    Attributes:
        voice_id: Unique identifier for the voice
        voice_name: Display name of the voice
        reference_audio_path: Path to reference audio file
        model_checkpoint_path: Path to trained model checkpoint
        description: Text description of voice characteristics (VECTORIZED)
        language: Language code (e.g., "en", "zh", "ja")
        created_at: ISO 8601 timestamp of creation
    """

    voice_id: str
    voice_name: str
    reference_audio_path: str
    model_checkpoint_path: str
    description: str
    language: str
    created_at: str

    def to_properties(self) -> Dict[str, Any]:
        """Convert to dictionary for Weaviate insertion."""
        return {
            "voice_id": self.voice_id,
            "voice_name": self.voice_name,
            "reference_audio_path": self.reference_audio_path,
            "model_checkpoint_path": self.model_checkpoint_path,
            "description": self.description,
            "language": self.language,
            "created_at": self.created_at,
        }


# =============================================================================
# Collection Creation Functions
# =============================================================================


def create_talking_head_profiles_collection(
    client: weaviate.WeaviateClient,
    force_reindex: bool = False,
) -> None:
    """
    Create (or recreate) the TalkingHeadProfiles collection.

    Vectorizes: personality_prompt, memory_context

    Args:
        client: Connected Weaviate client
        force_reindex: If True, delete existing collection before creating
    """
    exists = client.collections.exists(TALKING_HEAD_PROFILES_COLLECTION_NAME)

    if exists and force_reindex:
        logger.info(
            "Deleting existing collection '%s' for reindexing",
            TALKING_HEAD_PROFILES_COLLECTION_NAME,
        )
        client.collections.delete(TALKING_HEAD_PROFILES_COLLECTION_NAME)
        exists = False

    if not exists:
        logger.info("Creating collection '%s'", TALKING_HEAD_PROFILES_COLLECTION_NAME)
        # Using Weaviate default vector index (HNSW with cosine distance).
        # This matches the Documentation collection pattern in doc_ingestion.py.
        client.collections.create(
            name=TALKING_HEAD_PROFILES_COLLECTION_NAME,
            vectorizer_config=Configure.Vectorizer.text2vec_ollama(
                api_endpoint=settings.OLLAMA_API_ENDPOINT,
                model=settings.OLLAMA_EMBEDDING_MODEL,
            ),
            properties=[
                Property(name="avatar_id", data_type=DataType.TEXT),
                Property(name="avatar_name", data_type=DataType.TEXT),
                Property(name="avatar_type", data_type=DataType.TEXT),
                Property(name="reference_image_path", data_type=DataType.TEXT),
                Property(name="voice_profile_id", data_type=DataType.TEXT),
                Property(name="personality_prompt", data_type=DataType.TEXT),  # Vectorized
                Property(name="memory_context", data_type=DataType.TEXT),  # Vectorized
                Property(name="created_at", data_type=DataType.TEXT),
                Property(name="last_used", data_type=DataType.TEXT),
            ],
        )
        logger.info(
            "Collection '%s' created successfully", TALKING_HEAD_PROFILES_COLLECTION_NAME
        )
    else:
        logger.info(
            "Collection '%s' already exists", TALKING_HEAD_PROFILES_COLLECTION_NAME
        )


def create_conversation_memory_collection(
    client: weaviate.WeaviateClient,
    force_reindex: bool = False,
) -> None:
    """
    Create (or recreate) the ConversationMemory collection.

    Vectorizes: user_message, avatar_response, context_summary

    Args:
        client: Connected Weaviate client
        force_reindex: If True, delete existing collection before creating
    """
    exists = client.collections.exists(CONVERSATION_MEMORY_COLLECTION_NAME)

    if exists and force_reindex:
        logger.info(
            "Deleting existing collection '%s' for reindexing",
            CONVERSATION_MEMORY_COLLECTION_NAME,
        )
        client.collections.delete(CONVERSATION_MEMORY_COLLECTION_NAME)
        exists = False

    if not exists:
        logger.info("Creating collection '%s'", CONVERSATION_MEMORY_COLLECTION_NAME)
        # Using Weaviate default vector index (HNSW with cosine distance).
        # This matches the Documentation collection pattern in doc_ingestion.py.
        client.collections.create(
            name=CONVERSATION_MEMORY_COLLECTION_NAME,
            vectorizer_config=Configure.Vectorizer.text2vec_ollama(
                api_endpoint=settings.OLLAMA_API_ENDPOINT,
                model=settings.OLLAMA_EMBEDDING_MODEL,
            ),
            properties=[
                Property(name="conversation_id", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="avatar_id", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="user_id", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="timestamp", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="user_message", data_type=DataType.TEXT),  # Vectorized
                Property(name="avatar_response", data_type=DataType.TEXT),  # Vectorized
                Property(name="emotion_tags", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="context_summary", data_type=DataType.TEXT),  # Vectorized
            ],
        )
        logger.info(
            "Collection '%s' created successfully", CONVERSATION_MEMORY_COLLECTION_NAME
        )
    else:
        logger.info(
            "Collection '%s' already exists", CONVERSATION_MEMORY_COLLECTION_NAME
        )


def create_voice_clones_collection(
    client: weaviate.WeaviateClient,
    force_reindex: bool = False,
) -> None:
    """
    Create (or recreate) the VoiceClones collection.

    Vectorizes: description

    Args:
        client: Connected Weaviate client
        force_reindex: If True, delete existing collection before creating
    """
    exists = client.collections.exists(VOICE_CLONES_COLLECTION_NAME)

    if exists and force_reindex:
        logger.info(
            "Deleting existing collection '%s' for reindexing",
            VOICE_CLONES_COLLECTION_NAME,
        )
        client.collections.delete(VOICE_CLONES_COLLECTION_NAME)
        exists = False

    if not exists:
        logger.info("Creating collection '%s'", VOICE_CLONES_COLLECTION_NAME)
        # Using Weaviate default vector index (HNSW with cosine distance).
        # This matches the Documentation collection pattern in doc_ingestion.py.
        client.collections.create(
            name=VOICE_CLONES_COLLECTION_NAME,
            vectorizer_config=Configure.Vectorizer.text2vec_ollama(
                api_endpoint=settings.OLLAMA_API_ENDPOINT,
                model=settings.OLLAMA_EMBEDDING_MODEL,
            ),
            properties=[
                Property(name="voice_id", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="voice_name", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="reference_audio_path", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="model_checkpoint_path", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="description", data_type=DataType.TEXT),  # Vectorized
                Property(name="language", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="created_at", data_type=DataType.TEXT, skip_vectorization=True),
            ],
        )
        logger.info(
            "Collection '%s' created successfully", VOICE_CLONES_COLLECTION_NAME
        )
    else:
        logger.info("Collection '%s' already exists", VOICE_CLONES_COLLECTION_NAME)


# =============================================================================
# Collection Delete Functions
# =============================================================================


def delete_talking_head_profiles_collection(client: weaviate.WeaviateClient) -> bool:
    """Delete TalkingHeadProfiles collection if it exists."""
    try:
        if client.collections.exists(TALKING_HEAD_PROFILES_COLLECTION_NAME):
            logger.info(
                "Deleting collection '%s'", TALKING_HEAD_PROFILES_COLLECTION_NAME
            )
            client.collections.delete(TALKING_HEAD_PROFILES_COLLECTION_NAME)
            logger.info(
                "Collection '%s' deleted successfully",
                TALKING_HEAD_PROFILES_COLLECTION_NAME,
            )
            return True
        logger.info(
            "Collection '%s' does not exist", TALKING_HEAD_PROFILES_COLLECTION_NAME
        )
        return False
    except Exception as exc:
        logger.error(
            "Failed to delete collection '%s': %s",
            TALKING_HEAD_PROFILES_COLLECTION_NAME,
            exc,
        )
        raise


def delete_conversation_memory_collection(client: weaviate.WeaviateClient) -> bool:
    """Delete ConversationMemory collection if it exists."""
    try:
        if client.collections.exists(CONVERSATION_MEMORY_COLLECTION_NAME):
            logger.info(
                "Deleting collection '%s'", CONVERSATION_MEMORY_COLLECTION_NAME
            )
            client.collections.delete(CONVERSATION_MEMORY_COLLECTION_NAME)
            logger.info(
                "Collection '%s' deleted successfully",
                CONVERSATION_MEMORY_COLLECTION_NAME,
            )
            return True
        logger.info(
            "Collection '%s' does not exist", CONVERSATION_MEMORY_COLLECTION_NAME
        )
        return False
    except Exception as exc:
        logger.error(
            "Failed to delete collection '%s': %s",
            CONVERSATION_MEMORY_COLLECTION_NAME,
            exc,
        )
        raise


def delete_voice_clones_collection(client: weaviate.WeaviateClient) -> bool:
    """Delete VoiceClones collection if it exists."""
    try:
        if client.collections.exists(VOICE_CLONES_COLLECTION_NAME):
            logger.info("Deleting collection '%s'", VOICE_CLONES_COLLECTION_NAME)
            client.collections.delete(VOICE_CLONES_COLLECTION_NAME)
            logger.info(
                "Collection '%s' deleted successfully", VOICE_CLONES_COLLECTION_NAME
            )
            return True
        logger.info("Collection '%s' does not exist", VOICE_CLONES_COLLECTION_NAME)
        return False
    except Exception as exc:
        logger.error(
            "Failed to delete collection '%s': %s", VOICE_CLONES_COLLECTION_NAME, exc
        )
        raise


# =============================================================================
# Collection Exists Functions
# =============================================================================


def talking_head_profiles_collection_exists(client: weaviate.WeaviateClient) -> bool:
    """Check if TalkingHeadProfiles collection exists."""
    exists = client.collections.exists(TALKING_HEAD_PROFILES_COLLECTION_NAME)
    logger.debug(
        "Collection '%s' exists: %s", TALKING_HEAD_PROFILES_COLLECTION_NAME, exists
    )
    return exists


def conversation_memory_collection_exists(client: weaviate.WeaviateClient) -> bool:
    """Check if ConversationMemory collection exists."""
    exists = client.collections.exists(CONVERSATION_MEMORY_COLLECTION_NAME)
    logger.debug(
        "Collection '%s' exists: %s", CONVERSATION_MEMORY_COLLECTION_NAME, exists
    )
    return exists


def voice_clones_collection_exists(client: weaviate.WeaviateClient) -> bool:
    """Check if VoiceClones collection exists."""
    exists = client.collections.exists(VOICE_CLONES_COLLECTION_NAME)
    logger.debug("Collection '%s' exists: %s", VOICE_CLONES_COLLECTION_NAME, exists)
    return exists


# =============================================================================
# Collection Stats Functions
# =============================================================================


def get_talking_head_profiles_stats(client: weaviate.WeaviateClient) -> Dict[str, Any]:
    """
    Get statistics for TalkingHeadProfiles collection.

    Returns:
        - exists: Whether collection exists
        - object_count: Total number of profiles
        - avatar_type_counts: Breakdown by avatar_type
    """
    try:
        if not client.collections.exists(TALKING_HEAD_PROFILES_COLLECTION_NAME):
            logger.info(
                "Collection '%s' does not exist", TALKING_HEAD_PROFILES_COLLECTION_NAME
            )
            return {"exists": False, "object_count": 0, "avatar_type_counts": {}}

        collection = client.collections.get(TALKING_HEAD_PROFILES_COLLECTION_NAME)
        agg = collection.aggregate.over_all(total_count=True)
        total = agg.total_count or 0

        # Aggregate by avatar_type
        avatar_type_counts: Dict[str, int] = {}
        grouped_agg = collection.aggregate.over_all(
            group_by=GroupByAggregate(prop="avatar_type"),
            total_count=True,
        )
        for group in grouped_agg.groups:
            avatar_type = group.grouped_by.value
            count = group.total_count or 0
            if avatar_type:
                avatar_type_counts[str(avatar_type)] = int(count)

        logger.info(
            "Collection '%s' stats: %d total, types=%s",
            TALKING_HEAD_PROFILES_COLLECTION_NAME,
            total,
            avatar_type_counts,
        )

        return {
            "exists": True,
            "object_count": int(total),
            "avatar_type_counts": avatar_type_counts,
        }
    except Exception as e:
        logger.exception(
            "Failed to get stats for '%s': %s", TALKING_HEAD_PROFILES_COLLECTION_NAME, e
        )
        raise


def get_conversation_memory_stats(client: weaviate.WeaviateClient) -> Dict[str, Any]:
    """
    Get statistics for ConversationMemory collection.

    Returns:
        - exists: Whether collection exists
        - object_count: Total number of messages
        - conversation_counts: Breakdown by conversation_id
    """
    try:
        if not client.collections.exists(CONVERSATION_MEMORY_COLLECTION_NAME):
            logger.info(
                "Collection '%s' does not exist", CONVERSATION_MEMORY_COLLECTION_NAME
            )
            return {"exists": False, "object_count": 0, "conversation_counts": {}}

        collection = client.collections.get(CONVERSATION_MEMORY_COLLECTION_NAME)
        agg = collection.aggregate.over_all(total_count=True)
        total = agg.total_count or 0

        # Aggregate by conversation_id
        conversation_counts: Dict[str, int] = {}
        grouped_agg = collection.aggregate.over_all(
            group_by=GroupByAggregate(prop="conversation_id"),
            total_count=True,
        )
        for group in grouped_agg.groups:
            conv_id = group.grouped_by.value
            count = group.total_count or 0
            if conv_id:
                conversation_counts[str(conv_id)] = int(count)

        logger.info(
            "Collection '%s' stats: %d total messages",
            CONVERSATION_MEMORY_COLLECTION_NAME,
            total,
        )

        return {
            "exists": True,
            "object_count": int(total),
            "conversation_counts": conversation_counts,
        }
    except Exception as e:
        logger.exception(
            "Failed to get stats for '%s': %s", CONVERSATION_MEMORY_COLLECTION_NAME, e
        )
        raise


def get_voice_clones_stats(client: weaviate.WeaviateClient) -> Dict[str, Any]:
    """
    Get statistics for VoiceClones collection.

    Returns:
        - exists: Whether collection exists
        - object_count: Total number of voice profiles
        - language_counts: Breakdown by language
    """
    try:
        if not client.collections.exists(VOICE_CLONES_COLLECTION_NAME):
            logger.info(
                "Collection '%s' does not exist", VOICE_CLONES_COLLECTION_NAME
            )
            return {"exists": False, "object_count": 0, "language_counts": {}}

        collection = client.collections.get(VOICE_CLONES_COLLECTION_NAME)
        agg = collection.aggregate.over_all(total_count=True)
        total = agg.total_count or 0

        # Aggregate by language
        language_counts: Dict[str, int] = {}
        grouped_agg = collection.aggregate.over_all(
            group_by=GroupByAggregate(prop="language"),
            total_count=True,
        )
        for group in grouped_agg.groups:
            language = group.grouped_by.value
            count = group.total_count or 0
            if language:
                language_counts[str(language)] = int(count)

        logger.info(
            "Collection '%s' stats: %d total, languages=%s",
            VOICE_CLONES_COLLECTION_NAME,
            total,
            language_counts,
        )

        return {
            "exists": True,
            "object_count": int(total),
            "language_counts": language_counts,
        }
    except Exception as e:
        logger.exception(
            "Failed to get stats for '%s': %s", VOICE_CLONES_COLLECTION_NAME, e
        )
        raise


# =============================================================================
# Convenience Functions
# =============================================================================


def create_all_talking_head_collections(
    client: weaviate.WeaviateClient,
    force_reindex: bool = False,
) -> None:
    """
    Create all three talking head collections.

    Args:
        client: Connected Weaviate client
        force_reindex: If True, delete existing collections before creating
    """
    logger.info(
        "Creating all talking head collections (force_reindex=%s)", force_reindex
    )
    create_talking_head_profiles_collection(client, force_reindex)
    create_conversation_memory_collection(client, force_reindex)
    create_voice_clones_collection(client, force_reindex)
    logger.info("All talking head collections created successfully")


def delete_all_talking_head_collections(
    client: weaviate.WeaviateClient,
) -> Dict[str, bool]:
    """
    Delete all three talking head collections.

    Returns:
        Dictionary with deletion status for each collection
    """
    logger.info("Deleting all talking head collections")
    results = {
        "profiles": delete_talking_head_profiles_collection(client),
        "conversations": delete_conversation_memory_collection(client),
        "voices": delete_voice_clones_collection(client),
    }
    logger.info("Deletion results: %s", results)
    return results


def get_all_talking_head_stats(client: weaviate.WeaviateClient) -> Dict[str, Any]:
    """
    Get statistics for all three talking head collections.

    Returns:
        Dictionary with stats for each collection
    """
    return {
        "profiles": get_talking_head_profiles_stats(client),
        "conversations": get_conversation_memory_stats(client),
        "voices": get_voice_clones_stats(client),
    }


# =============================================================================
# CLI Interface
# =============================================================================


def main(argv: Optional[List[str]] = None) -> None:
    """CLI interface for talking head schema management."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Talking head schema management for Weaviate.",
    )
    parser.add_argument(
        "command",
        choices=["create", "delete", "stats", "reindex"],
        help="Operation to perform",
    )
    parser.add_argument(
        "--collection",
        choices=["profiles", "conversations", "voices", "all"],
        default="all",
        help="Which collection to operate on (default: all)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    logger.info("WEAVIATE_URL=%s", settings.WEAVIATE_URL)

    try:
        with WeaviateConnection() as client:
            if args.command == "create":
                if args.collection == "all":
                    create_all_talking_head_collections(client)
                elif args.collection == "profiles":
                    create_talking_head_profiles_collection(client)
                elif args.collection == "conversations":
                    create_conversation_memory_collection(client)
                elif args.collection == "voices":
                    create_voice_clones_collection(client)

            elif args.command == "reindex":
                if args.collection == "all":
                    create_all_talking_head_collections(client, force_reindex=True)
                elif args.collection == "profiles":
                    create_talking_head_profiles_collection(client, force_reindex=True)
                elif args.collection == "conversations":
                    create_conversation_memory_collection(client, force_reindex=True)
                elif args.collection == "voices":
                    create_voice_clones_collection(client, force_reindex=True)

            elif args.command == "delete":
                if args.collection == "all":
                    results = delete_all_talking_head_collections(client)
                    logger.info("Deletion results: %s", results)
                elif args.collection == "profiles":
                    delete_talking_head_profiles_collection(client)
                elif args.collection == "conversations":
                    delete_conversation_memory_collection(client)
                elif args.collection == "voices":
                    delete_voice_clones_collection(client)

            elif args.command == "stats":
                if args.collection == "all":
                    stats = get_all_talking_head_stats(client)
                    print("\n=== Talking Head Collection Stats ===")
                    for name, s in stats.items():
                        print(f"\n{name.upper()}:")
                        print(f"  Exists: {s['exists']}")
                        print(f"  Object Count: {s['object_count']}")
                        if "avatar_type_counts" in s:
                            print(f"  Avatar Types: {s['avatar_type_counts']}")
                        if "conversation_counts" in s:
                            print(f"  Conversations: {len(s['conversation_counts'])}")
                        if "language_counts" in s:
                            print(f"  Languages: {s['language_counts']}")
                elif args.collection == "profiles":
                    stats = get_talking_head_profiles_stats(client)
                    print(f"Profiles stats: {stats}")
                elif args.collection == "conversations":
                    stats = get_conversation_memory_stats(client)
                    print(f"Conversations stats: {stats}")
                elif args.collection == "voices":
                    stats = get_voice_clones_stats(client)
                    print(f"Voices stats: {stats}")

    except Exception as exc:
        logger.exception("Command failed: %s", exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
