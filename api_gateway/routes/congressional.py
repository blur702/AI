from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from weaviate.classes.aggregate import GroupByAggregate
from weaviate.classes.query import Filter

from ..middleware.response import unified_response
from ..models.schemas import (
    CongressionalMemberInfo,
    CongressionalMemberResponse,
    CongressionalQueryRequest,
    CongressionalQueryResponse,
    CongressionalQueryResult,
    CongressionalScrapeRequest,
    CongressionalScrapeStatusResponse,
)
from ..services.congressional_job_manager import CongressionalJobManager
from ..services.congressional_schema import get_congressional_stats
from ..services.weaviate_connection import (
    CONGRESSIONAL_DATA_COLLECTION_NAME,
    WeaviateConnection,
)
from ..utils.embeddings import get_embedding
from ..utils.logger import get_logger


router = APIRouter(prefix="/congressional", tags=["congressional"])
logger = get_logger("api_gateway.routes.congressional")
job_manager = CongressionalJobManager.instance()


@router.post("/scrape")
@unified_response
async def start_congressional_scrape(
    payload: CongressionalScrapeRequest,
) -> Dict[str, Any]:
    """
    Start a background congressional scraping job.
    """
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
        "completed_at": (
            state.completed_at.isoformat() if state.completed_at else None
        ),
        "error": state.error,
    }


@router.get("/scrape/status")
@unified_response
async def get_congressional_scrape_status() -> Dict[str, Any]:
    """
    Get current status of the congressional scraping job.
    """
    state = job_manager.get_status()
    resp = CongressionalScrapeStatusResponse(
        status=state.status,
        stats=state.stats,
        started_at=state.started_at,
        completed_at=state.completed_at,
        error=state.error,
    )
    return resp.dict()


@router.post("/scrape/cancel")
@unified_response
async def cancel_congressional_scrape() -> Dict[str, Any]:
    """
    Request cancellation of the current congressional scraping job.
    """
    job_manager.cancel_scrape()
    return {"cancelled": True}


@router.post("/scrape/pause")
@unified_response
async def pause_congressional_scrape() -> Dict[str, Any]:
    """
    Pause the current congressional scraping job.
    """
    job_manager.pause_scrape()
    return {"paused": True}


@router.post("/scrape/resume")
@unified_response
async def resume_congressional_scrape() -> Dict[str, Any]:
    """
    Resume a paused congressional scraping job.
    """
    job_manager.resume_scrape()
    return {"resumed": True}


@router.get("/members")
@unified_response
async def list_congressional_members() -> Dict[str, Any]:
    """
    List unique congressional members present in the index.
    """
    with WeaviateConnection() as client:
        if not client.collections.exists(CONGRESSIONAL_DATA_COLLECTION_NAME):
            return CongressionalMemberResponse(members=[]).dict()

        collection = client.collections.get(CONGRESSIONAL_DATA_COLLECTION_NAME)

        members: List[CongressionalMemberInfo] = []

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


@router.post("/query")
@unified_response
async def query_congressional_content(
    payload: CongressionalQueryRequest,
) -> Dict[str, Any]:
    """
    Perform semantic search over congressional content.
    """
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query text must not be empty")

    query_vector = await asyncio.to_thread(get_embedding, payload.query)

    with WeaviateConnection() as client:
        if not client.collections.exists(CONGRESSIONAL_DATA_COLLECTION_NAME):
            return CongressionalQueryResponse(results=[], total_results=0).dict()

        collection = client.collections.get(CONGRESSIONAL_DATA_COLLECTION_NAME)

        filters: List[Filter] = []

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

        combined_filter: Optional[Filter] = None
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

        results: List[CongressionalQueryResult] = []
        for obj in res.objects or []:
            props: Dict[str, Any] = obj.properties or {}
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


@router.get("/stats")
@unified_response
async def get_congressional_collection_stats() -> Dict[str, Any]:
    """
    Return basic statistics for the CongressionalData collection.
    """
    with WeaviateConnection() as client:
        stats = get_congressional_stats(client)
    return stats
