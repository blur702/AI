"""
Claude Code conversation schema for Weaviate.

Stores Claude Code conversation turns (user prompts + assistant responses)
with semantic embeddings for retrieval and context.

This collection is separate from talking head ConversationMemory and is
specifically for storing Claude Code interactions for later retrieval.

Usage:
    # Store a conversation turn
    python -m api_gateway.services.claude_conversation_schema store \
        --session-id "abc123" \
        --user-message "How do I create a new service?" \
        --assistant-response "To create a new service..."

    # Search conversations
    python -m api_gateway.services.claude_conversation_schema search \
        --query "creating services"

    # Get collection stats
    python -m api_gateway.services.claude_conversation_schema stats
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import weaviate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances
from weaviate.classes.query import MetadataQuery

from ..utils.embeddings import get_embedding
from ..utils.logger import get_logger
from .weaviate_connection import WeaviateConnection

logger = get_logger("api_gateway.claude_conversation_schema")

CLAUDE_CONVERSATION_COLLECTION_NAME = "ClaudeConversation"


@dataclass
class ClaudeConversationTurn:
    """
    Represents a single Claude Code conversation turn.

    Attributes:
        session_id: Unique session identifier (from Claude Code)
        timestamp: ISO 8601 timestamp of the message
        user_message: User's prompt/question (VECTORIZED)
        assistant_response: Claude's response (VECTORIZED)
        tool_calls: JSON array of tools called during response
        file_paths: JSON array of files referenced
        tags: JSON array of topic tags for categorization
    """

    session_id: str
    timestamp: str
    user_message: str
    assistant_response: str
    tool_calls: Optional[str] = None  # JSON array
    file_paths: Optional[str] = None  # JSON array
    tags: Optional[str] = None  # JSON array

    def to_properties(self) -> Dict[str, Any]:
        """Convert to dictionary for Weaviate insertion."""
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "user_message": self.user_message,
            "assistant_response": self.assistant_response,
            "tool_calls": self.tool_calls or "[]",
            "file_paths": self.file_paths or "[]",
            "tags": self.tags or "[]",
        }


def get_conversation_text_for_embedding(turn: ClaudeConversationTurn) -> str:
    """
    Build text representation for embedding.

    Combines user_message and assistant_response for semantic search.

    Args:
        turn: ClaudeConversationTurn instance

    Returns:
        Combined text for embedding
    """
    parts = [turn.user_message, turn.assistant_response]
    return "\n\n".join(part for part in parts if part)


def create_claude_conversation_collection(
    client: weaviate.WeaviateClient,
    force_reindex: bool = False,
) -> None:
    """
    Create (or recreate) the ClaudeConversation collection.

    Uses manual vectorization via Ollama API.

    Args:
        client: Connected Weaviate client
        force_reindex: If True, delete existing collection before creating
    """
    exists = client.collections.exists(CLAUDE_CONVERSATION_COLLECTION_NAME)

    if exists and force_reindex:
        logger.info(
            "Deleting existing collection '%s' for reindexing",
            CLAUDE_CONVERSATION_COLLECTION_NAME,
        )
        client.collections.delete(CLAUDE_CONVERSATION_COLLECTION_NAME)
        exists = False

    if not exists:
        logger.info("Creating collection '%s'", CLAUDE_CONVERSATION_COLLECTION_NAME)
        client.collections.create(
            name=CLAUDE_CONVERSATION_COLLECTION_NAME,
            vectorizer_config=Configure.Vectorizer.none(),
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE
            ),
            properties=[
                Property(name="session_id", data_type=DataType.TEXT),
                Property(name="timestamp", data_type=DataType.TEXT),
                Property(name="user_message", data_type=DataType.TEXT),
                Property(name="assistant_response", data_type=DataType.TEXT),
                Property(name="tool_calls", data_type=DataType.TEXT),
                Property(name="file_paths", data_type=DataType.TEXT),
                Property(name="tags", data_type=DataType.TEXT),
            ],
        )
        logger.info(
            "Collection '%s' created successfully",
            CLAUDE_CONVERSATION_COLLECTION_NAME,
        )
    else:
        logger.info(
            "Collection '%s' already exists", CLAUDE_CONVERSATION_COLLECTION_NAME
        )


def insert_conversation_turn(
    client: weaviate.WeaviateClient,
    turn: ClaudeConversationTurn,
) -> str:
    """
    Insert a conversation turn with computed embedding.

    Args:
        client: Connected Weaviate client
        turn: ClaudeConversationTurn instance

    Returns:
        UUID of inserted object as string

    Raises:
        Exception: If collection doesn't exist or insertion fails
    """
    # Ensure collection exists
    if not client.collections.exists(CLAUDE_CONVERSATION_COLLECTION_NAME):
        create_claude_conversation_collection(client)

    collection = client.collections.get(CLAUDE_CONVERSATION_COLLECTION_NAME)
    text = get_conversation_text_for_embedding(turn)
    vector = get_embedding(text)
    result = collection.data.insert(properties=turn.to_properties(), vector=vector)
    logger.debug(
        "Inserted ClaudeConversationTurn for session '%s' with UUID %s",
        turn.session_id,
        result,
    )
    return str(result)


def search_conversations(
    client: weaviate.WeaviateClient,
    query: str,
    limit: int = 10,
    session_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search conversations by semantic similarity.

    Args:
        client: Connected Weaviate client
        query: Search query text
        limit: Maximum results to return
        session_id: Optional filter by session

    Returns:
        List of matching conversation turns with metadata
    """
    if not client.collections.exists(CLAUDE_CONVERSATION_COLLECTION_NAME):
        logger.warning("Collection '%s' does not exist", CLAUDE_CONVERSATION_COLLECTION_NAME)
        return []

    collection = client.collections.get(CLAUDE_CONVERSATION_COLLECTION_NAME)
    query_vector = get_embedding(query)

    # Build filter if session_id provided
    filters = None
    if session_id:
        from weaviate.classes.query import Filter
        filters = Filter.by_property("session_id").equal(session_id)

    results = collection.query.near_vector(
        near_vector=query_vector,
        limit=limit,
        filters=filters,
        return_metadata=MetadataQuery(distance=True),
    )

    conversations = []
    for obj in results.objects:
        conv = {
            "uuid": str(obj.uuid),
            "session_id": obj.properties.get("session_id"),
            "timestamp": obj.properties.get("timestamp"),
            "user_message": obj.properties.get("user_message"),
            "assistant_response": obj.properties.get("assistant_response"),
            "tool_calls": obj.properties.get("tool_calls"),
            "file_paths": obj.properties.get("file_paths"),
            "tags": obj.properties.get("tags"),
            "distance": obj.metadata.distance if obj.metadata else None,
        }
        conversations.append(conv)

    return conversations


def get_conversation_stats(client: weaviate.WeaviateClient) -> Dict[str, Any]:
    """
    Get statistics for ClaudeConversation collection.

    Returns:
        - exists: Whether collection exists
        - object_count: Total number of conversation turns
        - session_count: Number of unique sessions
    """
    if not client.collections.exists(CLAUDE_CONVERSATION_COLLECTION_NAME):
        return {"exists": False, "object_count": 0, "session_count": 0}

    collection = client.collections.get(CLAUDE_CONVERSATION_COLLECTION_NAME)
    agg = collection.aggregate.over_all(total_count=True)
    total = agg.total_count or 0

    # Count unique sessions
    from weaviate.classes.aggregate import GroupByAggregate
    session_count = 0
    try:
        grouped = collection.aggregate.over_all(
            group_by=GroupByAggregate(prop="session_id"),
            total_count=True,
        )
        session_count = len(grouped.groups)
    except Exception as e:
        logger.warning("Failed to count sessions: %s", e)

    return {
        "exists": True,
        "object_count": int(total),
        "session_count": session_count,
    }


def store_from_stdin() -> None:
    """
    Store a conversation turn from stdin JSON.

    Expected JSON format:
    {
        "session_id": "...",
        "user_message": "...",
        "assistant_response": "...",
        "tool_calls": [...],
        "file_paths": [...],
        "tags": [...]
    }
    """
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON input: %s", e)
        sys.exit(1)

    session_id = data.get("session_id", str(uuid.uuid4()))
    user_message = data.get("user_message", "")
    assistant_response = data.get("assistant_response", "")

    if not user_message and not assistant_response:
        logger.warning("Empty conversation turn, skipping")
        sys.exit(0)

    turn = ClaudeConversationTurn(
        session_id=session_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_message=user_message,
        assistant_response=assistant_response,
        tool_calls=json.dumps(data.get("tool_calls", [])),
        file_paths=json.dumps(data.get("file_paths", [])),
        tags=json.dumps(data.get("tags", [])),
    )

    try:
        with WeaviateConnection() as client:
            result_uuid = insert_conversation_turn(client, turn)
            print(json.dumps({"success": True, "uuid": result_uuid}))
    except Exception as e:
        logger.exception("Failed to store conversation: %s", e)
        print(json.dumps({"success": False, "error": str(e)}))
        sys.exit(1)


def main(argv: Optional[List[str]] = None) -> None:
    """CLI interface for Claude conversation management."""
    parser = argparse.ArgumentParser(
        description="Claude Code conversation storage for Weaviate.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # store command
    store_parser = subparsers.add_parser("store", help="Store a conversation turn")
    store_parser.add_argument("--session-id", help="Session ID")
    store_parser.add_argument("--user-message", required=True, help="User message")
    store_parser.add_argument("--assistant-response", required=True, help="Assistant response")
    store_parser.add_argument("--tool-calls", help="JSON array of tool calls")
    store_parser.add_argument("--file-paths", help="JSON array of file paths")
    store_parser.add_argument("--tags", help="JSON array of tags")

    # store-stdin command
    subparsers.add_parser("store-stdin", help="Store conversation from stdin JSON")

    # search command
    search_parser = subparsers.add_parser("search", help="Search conversations")
    search_parser.add_argument("--query", "-q", required=True, help="Search query")
    search_parser.add_argument("--limit", "-n", type=int, default=10, help="Max results")
    search_parser.add_argument("--session-id", help="Filter by session")

    # stats command
    subparsers.add_parser("stats", help="Show collection statistics")

    # create command
    create_parser = subparsers.add_parser("create", help="Create collection")
    create_parser.add_argument("--force", action="store_true", help="Force recreate")

    # delete command
    subparsers.add_parser("delete", help="Delete collection")

    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    if args.command == "store-stdin":
        store_from_stdin()
        return

    try:
        with WeaviateConnection() as client:
            if args.command == "store":
                turn = ClaudeConversationTurn(
                    session_id=args.session_id or str(uuid.uuid4()),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    user_message=args.user_message,
                    assistant_response=args.assistant_response,
                    tool_calls=args.tool_calls,
                    file_paths=args.file_paths,
                    tags=args.tags,
                )
                result = insert_conversation_turn(client, turn)
                print(f"Stored conversation turn: {result}")

            elif args.command == "search":
                results = search_conversations(
                    client,
                    args.query,
                    limit=args.limit,
                    session_id=args.session_id,
                )
                print(f"\n=== Found {len(results)} conversations ===\n")
                for r in results:
                    print(f"Session: {r['session_id']}")
                    print(f"Time: {r['timestamp']}")
                    print(f"User: {r['user_message'][:100]}...")
                    print(f"Response: {r['assistant_response'][:100]}...")
                    print(f"Distance: {r['distance']:.4f}" if r['distance'] else "")
                    print("-" * 40)

            elif args.command == "stats":
                stats = get_conversation_stats(client)
                print("\n=== Claude Conversation Stats ===")
                print(f"Exists: {stats['exists']}")
                print(f"Total turns: {stats['object_count']}")
                print(f"Sessions: {stats['session_count']}")

            elif args.command == "create":
                create_claude_conversation_collection(client, force_reindex=args.force)
                print("Collection created/verified")

            elif args.command == "delete":
                if client.collections.exists(CLAUDE_CONVERSATION_COLLECTION_NAME):
                    client.collections.delete(CLAUDE_CONVERSATION_COLLECTION_NAME)
                    print("Collection deleted")
                else:
                    print("Collection does not exist")

    except Exception as e:
        logger.exception("Command failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
