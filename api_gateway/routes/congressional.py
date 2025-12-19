"""
Congressional data API routes.

Provides endpoints for querying, searching, and managing congressional data
including member information, press releases, and voting records.

All endpoints require API key authentication via X-API-Key header and are
subject to rate limiting (60 requests per minute per API key by default).
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from weaviate.classes.aggregate import GroupByAggregate
from weaviate.classes.query import Filter

from ..middleware.response import unified_response
from ..models.database import APIKey, AsyncSessionLocal
from ..models.schemas import (
    CongressionalChatRequest,
    CongressionalChatResponse,
    CongressionalChatSource,
    CongressionalMemberInfo,
    CongressionalMemberResponse,
    CongressionalQueryRequest,
    CongressionalQueryResponse,
    CongressionalQueryResult,
    CongressionalScrapeRequest,
    CongressionalScrapeStatusResponse,
    UnifiedResponse,
)
from ..services.congressional_job_manager import CongressionalJobManager
from ..services.congressional_schema import get_congressional_stats
from ..services.weaviate_connection import (
    CONGRESSIONAL_DATA_COLLECTION_NAME,
    WeaviateConnection,
)
from ..utils.embeddings import get_embedding
from ..utils.exceptions import InvalidAPIKeyError
from ..utils.logger import get_logger

# -----------------------------------------------------------------------------
# Rate Limiting Exception
# -----------------------------------------------------------------------------


class RateLimitExceededError(Exception):
    """Raised when API rate limit is exceeded."""

    code = "RATE_LIMIT_EXCEEDED"

    def __init__(self, message: str, retry_after: int = 60):
        """Initialize with error message and retry-after seconds."""
        self.message = message
        self.retry_after = retry_after
        super().__init__(message)


# -----------------------------------------------------------------------------
# OpenAPI Security Scheme
# -----------------------------------------------------------------------------

api_key_header = APIKeyHeader(
    name="X-API-Key",
    description="API key for authentication. Obtain from /auth/keys endpoint.",
    auto_error=False,
)


# -----------------------------------------------------------------------------
# Rate Limiting State
# -----------------------------------------------------------------------------

# In-memory rate limiting (requests per minute per API key)
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_REQUESTS = 60  # requests per window
RATE_LIMIT_WINDOW = 60  # window in seconds


def _cleanup_rate_limit_store(api_key: str) -> None:
    """Remove expired timestamps from rate limit store."""
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW
    _rate_limit_store[api_key] = [ts for ts in _rate_limit_store[api_key] if ts > cutoff]


def _get_rate_limit_remaining(api_key: str) -> int:
    """Get remaining requests in current window."""
    _cleanup_rate_limit_store(api_key)
    return max(0, RATE_LIMIT_REQUESTS - len(_rate_limit_store[api_key]))


def _get_rate_limit_reset(api_key: str) -> int:
    """Get seconds until rate limit window resets."""
    if not _rate_limit_store[api_key]:
        return RATE_LIMIT_WINDOW
    oldest = min(_rate_limit_store[api_key])
    return max(1, int(oldest + RATE_LIMIT_WINDOW - time.time()))


# -----------------------------------------------------------------------------
# Authentication Dependency
# -----------------------------------------------------------------------------


async def verify_api_key(
    request: Request,
    x_api_key: str | None = Depends(api_key_header),
) -> str:
    """
    Validate API key from X-API-Key header.

    Checks the provided API key against the database and ensures it is active.
    Updates the last_used_at timestamp on successful authentication.

    Args:
        request: FastAPI request object
        x_api_key: API key from header (injected by Depends)

    Returns:
        The validated API key string

    Raises:
        InvalidAPIKeyError: If API key is missing, invalid, or inactive
    """
    if not x_api_key:
        raise InvalidAPIKeyError("Missing API key. Provide X-API-Key header.")

    async with AsyncSessionLocal() as session:
        api_key = await session.get(APIKey, x_api_key)
        if not api_key:
            raise InvalidAPIKeyError("Invalid API key")
        if not api_key.is_active:
            raise InvalidAPIKeyError("API key is inactive")

        # Update last used timestamp
        api_key.last_used_at = datetime.now(UTC)
        await session.commit()

    # Store in request state for downstream use
    request.state.api_key = x_api_key
    return x_api_key


# -----------------------------------------------------------------------------
# Rate Limiting Dependency
# -----------------------------------------------------------------------------


async def check_rate_limit(
    request: Request,
    api_key: str = Depends(verify_api_key),
) -> str:
    """
    Check and enforce rate limiting for the authenticated API key.

    Tracks requests per API key using a sliding window algorithm.
    Returns rate limit headers in the response.

    Args:
        request: FastAPI request object
        api_key: Validated API key from verify_api_key dependency

    Returns:
        The API key string (for dependency chaining)

    Raises:
        RateLimitExceededError: If rate limit is exceeded (429)
    """
    _cleanup_rate_limit_store(api_key)

    remaining = _get_rate_limit_remaining(api_key)
    reset = _get_rate_limit_reset(api_key)

    # Store rate limit info for response headers
    request.state.rate_limit_remaining = remaining
    request.state.rate_limit_reset = reset

    if remaining <= 0:
        raise RateLimitExceededError(
            f"Rate limit exceeded. Retry after {reset} seconds.",
            retry_after=reset,
        )

    # Record this request
    _rate_limit_store[api_key].append(time.time())
    request.state.rate_limit_remaining = remaining - 1

    return api_key


# -----------------------------------------------------------------------------
# Response Models for OpenAPI Documentation
# -----------------------------------------------------------------------------


class CongressionalStatsResponse(BaseModel):
    """Response model for collection statistics."""

    total_documents: int = Field(..., description="Total documents in collection")
    total_members: int = Field(..., description="Number of unique members indexed")
    parties: dict[str, int] = Field(..., description="Document count by party")
    states: dict[str, int] = Field(..., description="Document count by state")
    last_updated: str | None = Field(None, description="ISO timestamp of last update")


class ScrapeStartResponse(BaseModel):
    """Response model for scrape job start."""

    status: str = Field(..., description="Job status (running, idle, etc.)")
    stats: dict[str, Any] = Field(default_factory=dict, description="Scrape statistics")
    started_at: str | None = Field(None, description="ISO timestamp of job start")
    completed_at: str | None = Field(None, description="ISO timestamp of job completion")
    error: str | None = Field(None, description="Error message if job failed")


class CancelResponse(BaseModel):
    """Response model for cancel operation."""

    cancelled: bool = Field(..., description="Whether cancellation was requested")


class PauseResponse(BaseModel):
    """Response model for pause operation."""

    paused: bool = Field(..., description="Whether pause was requested")


class ResumeResponse(BaseModel):
    """Response model for resume operation."""

    resumed: bool = Field(..., description="Whether resume was requested")


# -----------------------------------------------------------------------------
# Example Payloads for OpenAPI Documentation
# -----------------------------------------------------------------------------

QUERY_REQUEST_EXAMPLE = {
    "query": "climate change legislation",
    "party": "D",
    "state": "CA",
    "limit": 10,
}

CHAT_REQUEST_EXAMPLE = {
    "message": "What has Representative Smith said about healthcare reform?",
    "member_filter": "Smith",
}

SCRAPE_REQUEST_EXAMPLE = {
    "max_members": 10,
    "max_pages_per_member": 5,
    "dry_run": False,
}


# -----------------------------------------------------------------------------
# Router Configuration
# -----------------------------------------------------------------------------

router = APIRouter(
    prefix="/congressional",
    tags=["Congressional Data"],
    responses={
        401: {
            "description": "Authentication failed - invalid or missing API key",
            "model": UnifiedResponse,
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "data": None,
                        "error": {"code": "INVALID_API_KEY", "message": "Invalid API key"},
                        "job_id": None,
                        "timestamp": "2024-01-15T10:30:00Z",
                    }
                }
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "model": UnifiedResponse,
            "headers": {
                "X-RateLimit-Remaining": {
                    "description": "Requests remaining in current window",
                    "schema": {"type": "integer"},
                },
                "X-RateLimit-Reset": {
                    "description": "Seconds until rate limit resets",
                    "schema": {"type": "integer"},
                },
                "Retry-After": {
                    "description": "Seconds to wait before retrying",
                    "schema": {"type": "integer"},
                },
            },
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "data": None,
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": "Rate limit exceeded. Retry after 60 seconds.",
                        },
                        "job_id": None,
                        "timestamp": "2024-01-15T10:30:00Z",
                    }
                }
            },
        },
        500: {
            "description": "Internal server error",
            "model": UnifiedResponse,
        },
    },
)

logger = get_logger("api_gateway.routes.congressional")
job_manager = CongressionalJobManager.instance()


# -----------------------------------------------------------------------------
# Scrape Management Endpoints
# -----------------------------------------------------------------------------


@router.post(
    "/scrape",
    summary="Start congressional scraping job",
    description="""
Start a background job to scrape congressional member websites.

The scraper crawls official House/Senate member websites to index:
- Press releases
- Policy statements
- Voting records
- Member biographies

Jobs run asynchronously. Use `/scrape/status` to monitor progress.
""",
    response_description="Scrape job status and initial statistics",
    responses={
        200: {
            "model": UnifiedResponse,
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "status": "running",
                            "stats": {"members_processed": 0, "pages_scraped": 0},
                            "started_at": "2024-01-15T10:30:00Z",
                            "completed_at": None,
                            "error": None,
                        },
                        "error": None,
                        "job_id": None,
                        "timestamp": "2024-01-15T10:30:00Z",
                    }
                }
            },
        },
        409: {
            "description": "Scrape job already running",
            "model": UnifiedResponse,
        },
    },
)
@unified_response
async def start_congressional_scrape(
    payload: CongressionalScrapeRequest,
    api_key: str = Depends(check_rate_limit),
) -> dict[str, Any]:
    """Start a background congressional scraping job."""
    from ..services.congressional_scraper import ScrapeConfig

    cfg = ScrapeConfig(
        max_members=payload.max_members,
        max_pages_per_member=payload.max_pages_per_member or 5,
        dry_run=payload.dry_run,
    )

    try:
        state = job_manager.start_scrape(cfg)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "status": state.status,
        "stats": state.stats,
        "started_at": state.started_at.isoformat() if state.started_at else None,
        "completed_at": (state.completed_at.isoformat() if state.completed_at else None),
        "error": state.error,
    }


@router.get(
    "/scrape/status",
    summary="Get scrape job status",
    description="Returns the current status and statistics of the congressional scraping job.",
    response_description="Current scrape job status and statistics",
    responses={
        200: {
            "model": UnifiedResponse,
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "status": "running",
                            "stats": {
                                "members_processed": 50,
                                "pages_scraped": 245,
                                "errors": 3,
                            },
                            "started_at": "2024-01-15T10:30:00Z",
                            "completed_at": None,
                            "error": None,
                        },
                        "error": None,
                        "job_id": None,
                        "timestamp": "2024-01-15T10:35:00Z",
                    }
                }
            },
        },
    },
)
@unified_response
async def get_congressional_scrape_status(
    api_key: str = Depends(check_rate_limit),
) -> dict[str, Any]:
    """Get current status of the congressional scraping job."""
    state = job_manager.get_status()
    resp = CongressionalScrapeStatusResponse(
        status=state.status,
        stats=state.stats,
        started_at=state.started_at,
        completed_at=state.completed_at,
        error=state.error,
    )
    return resp.dict()


@router.post(
    "/scrape/cancel",
    summary="Cancel scrape job",
    description="Request cancellation of the currently running scrape job. The job will stop at the next safe checkpoint.",
    response_description="Cancellation confirmation",
)
@unified_response
async def cancel_congressional_scrape(
    api_key: str = Depends(check_rate_limit),
) -> dict[str, Any]:
    """Request cancellation of the current congressional scraping job."""
    job_manager.cancel_scrape()
    return {"cancelled": True}


@router.post(
    "/scrape/pause",
    summary="Pause scrape job",
    description="Pause the currently running scrape job. Use `/scrape/resume` to continue.",
    response_description="Pause confirmation",
)
@unified_response
async def pause_congressional_scrape(
    api_key: str = Depends(check_rate_limit),
) -> dict[str, Any]:
    """Pause the current congressional scraping job."""
    job_manager.pause_scrape()
    return {"paused": True}


@router.post(
    "/scrape/resume",
    summary="Resume scrape job",
    description="Resume a previously paused scrape job.",
    response_description="Resume confirmation",
)
@unified_response
async def resume_congressional_scrape(
    api_key: str = Depends(check_rate_limit),
) -> dict[str, Any]:
    """Resume a paused congressional scraping job."""
    job_manager.resume_scrape()
    return {"resumed": True}


# -----------------------------------------------------------------------------
# Member Listing Endpoint
# -----------------------------------------------------------------------------


@router.get(
    "/members",
    summary="List congressional members",
    description="""
List all congressional members currently indexed in the database.

Returns member information including:
- Name and party affiliation
- State and district
- Chamber (House/Senate)
- Official website and RSS feed URLs
""",
    response_description="List of congressional members",
    responses={
        200: {
            "model": UnifiedResponse,
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "members": [
                                {
                                    "name": "John Smith",
                                    "state": "CA",
                                    "district": "12",
                                    "party": "D",
                                    "chamber": "House",
                                    "website_url": "https://smith.house.gov",
                                    "rss_feed_url": "https://smith.house.gov/rss",
                                }
                            ]
                        },
                        "error": None,
                        "job_id": None,
                        "timestamp": "2024-01-15T10:30:00Z",
                    }
                }
            },
        },
    },
)
@unified_response
async def list_congressional_members(
    api_key: str = Depends(check_rate_limit),
) -> dict[str, Any]:
    """List unique congressional members present in the index."""
    with WeaviateConnection() as client:
        if not client.collections.exists(CONGRESSIONAL_DATA_COLLECTION_NAME):
            return CongressionalMemberResponse(members=[]).dict()

        collection = client.collections.get(CONGRESSIONAL_DATA_COLLECTION_NAME)

        members: list[CongressionalMemberInfo] = []

        try:
            agg = collection.aggregate.over_all(
                group_by=GroupByAggregate(prop="member_name"),
                total_count=True,
            )
            for group in agg.groups:
                member_name = group.grouped_by.value
                if not member_name:
                    continue

                res = collection.query.near_text(
                    query=member_name,
                    limit=1,
                    filters=Filter.by_property("member_name").equal(member_name),
                )
                if not res.objects:
                    continue

                props = res.objects[0].properties or {}
                members.append(
                    CongressionalMemberInfo(
                        name=props.get("member_name", ""),
                        state=props.get("state", ""),
                        district=props.get("district", ""),
                        party=props.get("party", ""),
                        chamber=props.get("chamber", ""),
                        website_url=props.get("url", ""),
                        rss_feed_url=props.get("rss_feed_url", ""),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to list congressional members: %s", exc)
            return CongressionalMemberResponse(members=[]).dict()

    return CongressionalMemberResponse(members=members).dict()


# -----------------------------------------------------------------------------
# Query Endpoint
# -----------------------------------------------------------------------------


@router.post(
    "/query",
    summary="Search congressional content",
    description="""
Perform semantic search over indexed congressional content.

Supports filtering by:
- **member_name**: Specific member's content only
- **party**: Political party (D, R, I)
- **state**: State code (CA, TX, NY, etc.)
- **topic**: Content topic/category
- **date_from/date_to**: Date range filters

Results are ranked by semantic similarity to the query.
""",
    response_description="Search results with relevance ranking",
    responses={
        200: {
            "model": UnifiedResponse,
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "results": [
                                {
                                    "member_name": "Jane Doe",
                                    "state": "NY",
                                    "district": "7",
                                    "party": "D",
                                    "chamber": "House",
                                    "title": "Press Release: Climate Action",
                                    "content_text": "Today I introduced legislation...",
                                    "url": "https://doe.house.gov/press/climate",
                                    "scraped_at": "2024-01-10T15:30:00Z",
                                }
                            ],
                            "total_results": 1,
                        },
                        "error": None,
                        "job_id": None,
                        "timestamp": "2024-01-15T10:30:00Z",
                    }
                }
            },
        },
        400: {
            "description": "Invalid request (empty query)",
            "model": UnifiedResponse,
        },
    },
)
@unified_response
async def query_congressional_content(
    payload: CongressionalQueryRequest,
    api_key: str = Depends(check_rate_limit),
) -> dict[str, Any]:
    """Perform semantic search over congressional content."""
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query text must not be empty")

    query_vector = await asyncio.to_thread(get_embedding, payload.query)

    with WeaviateConnection() as client:
        if not client.collections.exists(CONGRESSIONAL_DATA_COLLECTION_NAME):
            return CongressionalQueryResponse(results=[], total_results=0).dict()

        collection = client.collections.get(CONGRESSIONAL_DATA_COLLECTION_NAME)

        filters: list[Filter] = []

        if payload.member_name:
            filters.append(
                Filter.by_property("member_name").equal(payload.member_name),
            )
        if payload.party:
            filters.append(Filter.by_property("party").equal(payload.party))
        if payload.state:
            filters.append(Filter.by_property("state").equal(payload.state))
        if payload.topic:
            filters.append(Filter.by_property("topic").equal(payload.topic))

        date_from = payload.date_from.isoformat() if payload.date_from else None
        date_to = payload.date_to.isoformat() if payload.date_to else None

        if date_from is not None:
            filters.append(
                Filter.by_property("scraped_at").greater_than_equal(date_from),
            )
        if date_to is not None:
            filters.append(
                Filter.by_property("scraped_at").less_than_equal(date_to),
            )

        combined_filter: Filter | None = None
        for f in filters:
            combined_filter = f if combined_filter is None else combined_filter & f

        try:
            res = collection.query.near_vector(
                near_vector=query_vector,
                limit=payload.limit,
                filters=combined_filter,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Congressional query failed: %s", exc)
            raise HTTPException(
                status_code=500,
                detail="Failed to query congressional collection",
            ) from exc

        results: list[CongressionalQueryResult] = []
        for obj in res.objects or []:
            props: dict[str, Any] = obj.properties or {}
            results.append(
                CongressionalQueryResult(
                    member_name=props.get("member_name", ""),
                    state=props.get("state", ""),
                    district=props.get("district", ""),
                    party=props.get("party", ""),
                    chamber=props.get("chamber", ""),
                    title=props.get("title", ""),
                    content_text=props.get("content_text", ""),
                    url=props.get("url", ""),
                    scraped_at=props.get("scraped_at", ""),
                )
            )

    return CongressionalQueryResponse(
        results=results,
        total_results=len(results),
    ).dict()


# -----------------------------------------------------------------------------
# Chat/RAG Endpoint
# -----------------------------------------------------------------------------


@router.post(
    "/chat",
    summary="Chat with congressional data (RAG)",
    description="""
Ask natural language questions about congressional data using RAG (Retrieval-Augmented Generation).

The system will:
1. Search relevant documents from the congressional index
2. Use an LLM to generate a natural language answer
3. Return the answer with source citations

Optionally filter to a specific member's content using `member_filter`.
""",
    response_description="Generated answer with source documents",
    responses={
        200: {
            "model": UnifiedResponse,
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "answer": "Representative Smith has advocated for healthcare reform...",
                            "sources": [
                                {
                                    "member_name": "John Smith",
                                    "title": "Healthcare Reform Statement",
                                    "content_preview": "Today I announced my support...",
                                    "url": "https://smith.house.gov/healthcare",
                                    "party": "D",
                                    "state": "CA",
                                }
                            ],
                            "conversation_id": "abc123",
                            "model": "llama3.2",
                        },
                        "error": None,
                        "job_id": None,
                        "timestamp": "2024-01-15T10:30:00Z",
                    }
                }
            },
        },
        400: {
            "description": "Invalid request (empty message)",
            "model": UnifiedResponse,
        },
    },
)
@unified_response
async def chat_with_congressional_data(
    payload: CongressionalChatRequest,
    api_key: str = Depends(check_rate_limit),
) -> dict[str, Any]:
    """Chat with congressional data using RAG (Retrieval-Augmented Generation)."""
    import uuid

    from ..services.congressional_rag import answer_question

    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message must not be empty")

    # Generate conversation ID if not provided
    conversation_id = payload.conversation_id or str(uuid.uuid4())

    try:
        # Run RAG pipeline in thread pool to avoid blocking
        response = await asyncio.to_thread(
            answer_question,
            question=payload.message,
            member_filter=payload.member_filter,
        )

        # Convert sources to response format
        sources = [
            CongressionalChatSource(
                member_name=src.member_name,
                title=src.title,
                content_preview=src.content_preview,
                url=src.url,
                party=src.party,
                state=src.state,
            )
            for src in response.sources
        ]

        return CongressionalChatResponse(
            answer=response.answer,
            sources=sources,
            conversation_id=conversation_id,
            model=response.model,
        ).dict()

    except Exception as exc:
        logger.exception("Congressional chat failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate response: {str(exc)}",
        ) from exc


# -----------------------------------------------------------------------------
# Statistics Endpoint
# -----------------------------------------------------------------------------


@router.get(
    "/stats",
    summary="Get collection statistics",
    description="""
Return statistics for the CongressionalData collection including:
- Total document count
- Number of unique members indexed
- Document counts by party and state
- Last update timestamp
""",
    response_description="Collection statistics",
    responses={
        200: {
            "model": UnifiedResponse,
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "total_documents": 15234,
                            "total_members": 441,
                            "parties": {"D": 7500, "R": 7600, "I": 134},
                            "states": {"CA": 1200, "TX": 950, "NY": 800},
                            "last_updated": "2024-01-15T08:00:00Z",
                        },
                        "error": None,
                        "job_id": None,
                        "timestamp": "2024-01-15T10:30:00Z",
                    }
                }
            },
        },
    },
)
@unified_response
async def get_congressional_collection_stats(
    api_key: str = Depends(check_rate_limit),
) -> dict[str, Any]:
    """Return basic statistics for the CongressionalData collection."""
    with WeaviateConnection() as client:
        stats = get_congressional_stats(client)
    return stats
