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
    async with AsyncSessionLocal() as session:
        yield session


@router.post("/keys")
@unified_response
async def create_api_key(
    payload: CreateAPIKeyRequest, session: AsyncSession = Depends(get_session)
) -> dict:
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
    api_key = await session.get(APIKey, key)
    if api_key:
        api_key.is_active = False
        await session.commit()
    return {"success": True}

