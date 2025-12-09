"""
Authentication routes for API key management.

Provides endpoints for creating, listing, and deactivating API keys used for
authenticating requests to the API Gateway. Keys are stored in PostgreSQL
and validated via middleware on protected routes.
"""
import secrets
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..middleware.response import unified_response
from ..models.database import APIKey, AsyncSessionLocal
from ..models.schemas import CreateAPIKeyRequest


router = APIRouter(prefix="/auth", tags=["auth"])


async def get_session() -> AsyncSession:
    """
    Dependency that provides a database session for route handlers.

    Yields:
        AsyncSession: Active PostgreSQL database session with automatic cleanup.
    """
    async with AsyncSessionLocal() as session:
        yield session


@router.post("/keys")
@unified_response
async def create_api_key(
    payload: CreateAPIKeyRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    """
    Create a new API key for authenticating requests.

    Generates a cryptographically secure 32-byte URL-safe token and stores it
    in the database with the provided name. The key value is only returned once
    at creation time and should be stored securely by the client.

    Args:
        payload: Request containing the name for the new API key.
        session: Database session injected by FastAPI dependency.

    Returns:
        dict: Contains key (token string), name, and created_at timestamp.
    """
    key_value = secrets.token_urlsafe(32)
    api_key = APIKey(
        key=key_value,
        name=payload.name,
        created_at=datetime.now(timezone.utc),
    )
    session.add(api_key)
    await session.commit()

    return {
        "key": key_value,
        "name": api_key.name,
        "created_at": api_key.created_at.isoformat(),
    }


@router.get("/keys")
@unified_response
async def list_api_keys(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    List all API keys with metadata (excludes actual key values).

    Returns metadata for all API keys in the system including name, creation time,
    last usage time, and active status. The actual key tokens are never returned
    after initial creation for security.

    Args:
        session: Database session injected by FastAPI dependency.

    Returns:
        dict: Contains 'keys' array with name, created_at, last_used_at, and is_active
              for each key.
    """
    result = await session.execute(select(APIKey))
    items: List[APIKey] = result.scalars().all()
    keys = [
        {
            "name": item.name,
            "created_at": item.created_at.isoformat(),
            "last_used_at": item.last_used_at.isoformat() if item.last_used_at else None,
            "is_active": item.is_active,
        }
        for item in items
    ]
    return {"keys": keys}


@router.delete("/keys/{key}")
@unified_response
async def deactivate_api_key(
    key: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """
    Deactivate an API key to prevent further use.

    Marks the specified API key as inactive in the database. The key record
    is retained for audit purposes but will fail authentication checks.
    Silently succeeds even if the key doesn't exist.

    Args:
        key: The API key token to deactivate.
        session: Database session injected by FastAPI dependency.

    Returns:
        dict: Contains 'success': True regardless of whether key was found.
    """
    api_key = await session.get(APIKey, key)
    if api_key:
        api_key.is_active = False
        await session.commit()
    return {"success": True}

