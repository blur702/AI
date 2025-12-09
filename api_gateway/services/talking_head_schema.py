"""
Talking Head schema definitions for Weaviate.

Defines three collections for the talking head system:
- TalkingHeadProfiles: Avatar configurations and personality settings
- ConversationMemory: Chat history with semantic search
- VoiceClones: Voice cloning profiles and metadata

All collections use manual vectorization via Ollama API for semantic search.
Use the insertion helper functions (insert_talking_head_profile, insert_conversation_message,
insert_voice_clone) to ensure embeddings are computed consistently.

Example insertion pattern:
    profile = TalkingHeadProfile(...)
    insert_talking_head_profile(client, profile)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

import weaviate
from weaviate.classes.aggregate import GroupByAggregate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances

from ..config import settings
from ..utils.embeddings import get_embedding
from ..utils.logger import get_logger
from .weaviate_connection import (
    TALKING_HEAD_PROFILES_COLLECTION_NAME,
    CONVERSATION_MEMORY_COLLECTION_NAME,
    VOICE_CLONES_COLLECTION_NAME,
    WeaviateConnection,
)

logger = get_logger("api_gateway.talking_head_schema")


# =============================================================================
# Text Representation Functions
# =============================================================================


def get_profile_text_for_embedding(profile: "TalkingHeadProfile") -> str:
    """
    Build text representation of a TalkingHeadProfile for embedding.

    Combines avatar_name, personality_prompt, and memory_context.

    Args:
        profile: TalkingHeadProfile instance

    Returns:
        Combined text for embedding

    Raises:
        ValueError: If all profile text fields are empty
    """
    parts = [profile.avatar_name, profile.personality_prompt, profile.memory_context]
    text = "\n\n".join(part for part in parts if part)
    if not text:
        raise ValueError("Cannot generate embedding: all profile text fields are empty")
    return text


def get_conversation_text_for_embedding(message: "ConversationMessage") -> str:
    """
    Build text representation of a ConversationMessage for embedding.

    Combines user_message, avatar_response, and context_summary.

    Args:
        message: ConversationMessage instance

    Returns:
        Combined text for embedding

    Raises:
        ValueError: If all conversation text fields are empty
    """
    parts = [message.user_message, message.avatar_response, message.context_summary]
    text = "\n\n".join(part for part in parts if part)
    if not text:
        raise ValueError("Cannot generate embedding: all conversation text fields are empty")
    return text


def get_voice_text_for_embedding(voice: "VoiceClone") -> str:
    """
    Build text representation of a VoiceClone for embedding.

    Combines voice_name and description.

    Args:
        voice: VoiceClone instance

    Returns:
        Combined text for embedding

    Raises:
        ValueError: If all voice text fields are empty
    """
    parts = [voice.voice_name, voice.description]
    text = "\n\n".join(part for part in parts if part)
    if not text:
        raise ValueError("Cannot generate embedding: all voice text fields are empty")
    return text


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
        """
        Convert to dictionary for Weaviate insertion.

        Returns:
            Dictionary with all fields formatted for Weaviate insertion
        """
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
        """
        Convert to dictionary for Weaviate insertion.

        Returns:
            Dictionary with all fields formatted for Weaviate insertion
        """
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
        """
        Convert to dictionary for Weaviate insertion.

        Returns:
            Dictionary with all fields formatted for Weaviate insertion
        """
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

    Uses manual vectorization. Call get_embedding() before insertion.

    Args:
        client: Connected Weaviate client
        force_reindex: If True, delete existing collection before creating

    Raises:
        WeaviateBaseError: If collection creation fails
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
        client.collections.create(
            name=TALKING_HEAD_PROFILES_COLLECTION_NAME,
            vectorizer_config=Configure.Vectorizer.none(),
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE
            ),
            properties=[
                Property(name="avatar_id", data_type=DataType.TEXT),
                Property(name="avatar_name", data_type=DataType.TEXT),
                Property(name="avatar_type", data_type=DataType.TEXT),
                Property(name="reference_image_path", data_type=DataType.TEXT),
                Property(name="voice_profile_id", data_type=DataType.TEXT),
                Property(name="personality_prompt", data_type=DataType.TEXT),
                Property(name="memory_context", data_type=DataType.TEXT),
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

    Uses manual vectorization. Call get_embedding() before insertion.

    Args:
        client: Connected Weaviate client
        force_reindex: If True, delete existing collection before creating

    Raises:
        WeaviateBaseError: If collection creation fails
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
        client.collections.create(
            name=CONVERSATION_MEMORY_COLLECTION_NAME,
            vectorizer_config=Configure.Vectorizer.none(),
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE
            ),
            properties=[
                Property(name="conversation_id", data_type=DataType.TEXT),
                Property(name="avatar_id", data_type=DataType.TEXT),
                Property(name="user_id", data_type=DataType.TEXT),
                Property(name="timestamp", data_type=DataType.TEXT),
                Property(name="user_message", data_type=DataType.TEXT),
                Property(name="avatar_response", data_type=DataType.TEXT),
                Property(name="emotion_tags", data_type=DataType.TEXT),
                Property(name="context_summary", data_type=DataType.TEXT),
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

    Uses manual vectorization. Call get_embedding() before insertion.

    Args:
        client: Connected Weaviate client
        force_reindex: If True, delete existing collection before creating

    Raises:
        WeaviateBaseError: If collection creation fails
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
        client.collections.create(
            name=VOICE_CLONES_COLLECTION_NAME,
            vectorizer_config=Configure.Vectorizer.none(),
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE
            ),
            properties=[
                Property(name="voice_id", data_type=DataType.TEXT),
                Property(name="voice_name", data_type=DataType.TEXT),
                Property(name="reference_audio_path", data_type=DataType.TEXT),
                Property(name="model_checkpoint_path", data_type=DataType.TEXT),
                Property(name="description", data_type=DataType.TEXT),
                Property(name="language", data_type=DataType.TEXT),
                Property(name="created_at", data_type=DataType.TEXT),
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
    """
    Delete TalkingHeadProfiles collection if it exists.

    Args:
        client: Connected Weaviate client

    Returns:
        True if collection was deleted, False if it didn't exist

    Raises:
        Exception: If deletion fails due to Weaviate error
    """
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
    """
    Delete ConversationMemory collection if it exists.

    Args:
        client: Connected Weaviate client

    Returns:
        True if collection was deleted, False if it didn't exist

    Raises:
        Exception: If deletion fails due to Weaviate error
    """
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
    """
    Delete VoiceClones collection if it exists.

    Args:
        client: Connected Weaviate client

    Returns:
        True if collection was deleted, False if it didn't exist

    Raises:
        Exception: If deletion fails due to Weaviate error
    """
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
    """
    Check if TalkingHeadProfiles collection exists.

    Args:
        client: Connected Weaviate client

    Returns:
        True if collection exists, False otherwise
    """
    exists = client.collections.exists(TALKING_HEAD_PROFILES_COLLECTION_NAME)
    logger.debug(
        "Collection '%s' exists: %s", TALKING_HEAD_PROFILES_COLLECTION_NAME, exists
    )
    return exists


def conversation_memory_collection_exists(client: weaviate.WeaviateClient) -> bool:
    """
    Check if ConversationMemory collection exists.

    Args:
        client: Connected Weaviate client

    Returns:
        True if collection exists, False otherwise
    """
    exists = client.collections.exists(CONVERSATION_MEMORY_COLLECTION_NAME)
    logger.debug(
        "Collection '%s' exists: %s", CONVERSATION_MEMORY_COLLECTION_NAME, exists
    )
    return exists


def voice_clones_collection_exists(client: weaviate.WeaviateClient) -> bool:
    """
    Check if VoiceClones collection exists.

    Args:
        client: Connected Weaviate client

    Returns:
        True if collection exists, False otherwise
    """
    exists = client.collections.exists(VOICE_CLONES_COLLECTION_NAME)
    logger.debug("Collection '%s' exists: %s", VOICE_CLONES_COLLECTION_NAME, exists)
    return exists


# =============================================================================
# Collection Stats Functions
# =============================================================================


def get_talking_head_profiles_stats(client: weaviate.WeaviateClient) -> Dict[str, Any]:
    """
    Get statistics for TalkingHeadProfiles collection.

    Args:
        client: Connected Weaviate client

    Returns:
        Dictionary with statistics:
        - exists: Whether collection exists
        - object_count: Total number of profiles
        - avatar_type_counts: Breakdown by avatar_type

    Raises:
        Exception: If stats retrieval fails
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

    Args:
        client: Connected Weaviate client

    Returns:
        Dictionary with statistics:
        - exists: Whether collection exists
        - object_count: Total number of messages
        - conversation_counts: Breakdown by conversation_id

    Raises:
        Exception: If stats retrieval fails
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

    Args:
        client: Connected Weaviate client

    Returns:
        Dictionary with statistics:
        - exists: Whether collection exists
        - object_count: Total number of voice profiles
        - language_counts: Breakdown by language

    Raises:
        Exception: If stats retrieval fails
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
# Insertion Helper Functions
# =============================================================================


def insert_talking_head_profile(
    client: weaviate.WeaviateClient,
    profile: TalkingHeadProfile,
) -> UUID:
    """
    Insert a TalkingHeadProfile into the collection with computed embedding.

    Computes the embedding from the profile's text representation and inserts
    the profile into the TalkingHeadProfiles collection.

    Args:
        client: Connected Weaviate client
        profile: TalkingHeadProfile instance to insert

    Returns:
        UUID of the inserted object

    Raises:
        ValueError: If required fields are empty or invalid
        Exception: If the collection doesn't exist or insertion fails
    """
    # Validate required fields
    if not profile.avatar_id or not profile.avatar_id.strip():
        raise ValueError("avatar_id cannot be empty")
    if not profile.avatar_name or not profile.avatar_name.strip():
        raise ValueError("avatar_name cannot be empty")
    if not profile.avatar_type or not profile.avatar_type.strip():
        raise ValueError("avatar_type cannot be empty")

    collection = client.collections.get(TALKING_HEAD_PROFILES_COLLECTION_NAME)
    text = get_profile_text_for_embedding(profile)
    vector = get_embedding(text)
    result = collection.data.insert(properties=profile.to_properties(), vector=vector)
    logger.debug(
        "Inserted TalkingHeadProfile '%s' with UUID %s",
        profile.avatar_name,
        result,
    )
    return result


def insert_conversation_message(
    client: weaviate.WeaviateClient,
    message: ConversationMessage,
) -> UUID:
    """
    Insert a ConversationMessage into the collection with computed embedding.

    Computes the embedding from the message's text representation and inserts
    the message into the ConversationMemory collection.

    Args:
        client: Connected Weaviate client
        message: ConversationMessage instance to insert

    Returns:
        UUID of the inserted object

    Raises:
        ValueError: If required fields are empty or invalid
        Exception: If the collection doesn't exist or insertion fails
    """
    # Validate required fields
    if not message.conversation_id or not message.conversation_id.strip():
        raise ValueError("conversation_id cannot be empty")
    if not message.avatar_id or not message.avatar_id.strip():
        raise ValueError("avatar_id cannot be empty")
    if not message.user_id or not message.user_id.strip():
        raise ValueError("user_id cannot be empty")
    if not message.timestamp or not message.timestamp.strip():
        raise ValueError("timestamp cannot be empty")

    collection = client.collections.get(CONVERSATION_MEMORY_COLLECTION_NAME)
    text = get_conversation_text_for_embedding(message)
    vector = get_embedding(text)
    result = collection.data.insert(properties=message.to_properties(), vector=vector)
    logger.debug(
        "Inserted ConversationMessage for conversation '%s' with UUID %s",
        message.conversation_id,
        result,
    )
    return result


def insert_voice_clone(
    client: weaviate.WeaviateClient,
    voice: VoiceClone,
) -> UUID:
    """
    Insert a VoiceClone into the collection with computed embedding.

    Computes the embedding from the voice's text representation and inserts
    the voice clone into the VoiceClones collection.

    Args:
        client: Connected Weaviate client
        voice: VoiceClone instance to insert

    Returns:
        UUID of the inserted object

    Raises:
        ValueError: If required fields are empty or invalid
        Exception: If the collection doesn't exist or insertion fails
    """
    # Validate required fields
    if not voice.voice_id or not voice.voice_id.strip():
        raise ValueError("voice_id cannot be empty")
    if not voice.voice_name or not voice.voice_name.strip():
        raise ValueError("voice_name cannot be empty")
    if not voice.language or not voice.language.strip():
        raise ValueError("language cannot be empty")

    collection = client.collections.get(VOICE_CLONES_COLLECTION_NAME)
    text = get_voice_text_for_embedding(voice)
    vector = get_embedding(text)
    result = collection.data.insert(properties=voice.to_properties(), vector=vector)
    logger.debug(
        "Inserted VoiceClone '%s' with UUID %s",
        voice.voice_name,
        result,
    )
    return result


# =============================================================================
# Convenience Functions
# =============================================================================


def create_all_talking_head_collections(
    client: weaviate.WeaviateClient,
    force_reindex: bool = False,
) -> None:
    """
    Create all three talking head collections.

    Creates TalkingHeadProfiles, ConversationMemory, and VoiceClones collections.

    Args:
        client: Connected Weaviate client
        force_reindex: If True, delete existing collections before creating

    Raises:
        WeaviateBaseError: If any collection creation fails
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

    Deletes TalkingHeadProfiles, ConversationMemory, and VoiceClones collections.

    Args:
        client: Connected Weaviate client

    Returns:
        Dictionary with deletion status for each collection:
        - profiles: True if deleted, False if didn't exist
        - conversations: True if deleted, False if didn't exist
        - voices: True if deleted, False if didn't exist

    Raises:
        Exception: If any deletion fails
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

    Args:
        client: Connected Weaviate client

    Returns:
        Dictionary with stats for each collection:
        - profiles: TalkingHeadProfiles stats
        - conversations: ConversationMemory stats
        - voices: VoiceClones stats

    Raises:
        Exception: If stats retrieval fails for any collection
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
    """
    CLI interface for talking head schema management.

    Provides commands to create, delete, and get stats for talking head collections.

    Args:
        argv: Optional command line arguments (for testing)

    Raises:
        SystemExit: On command failure
    """
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
