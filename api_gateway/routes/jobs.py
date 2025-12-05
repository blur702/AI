from typing import List

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from ..middleware.response import unified_response
from ..models.database import AsyncSessionLocal, Job, JobStatus
from ..models.schemas import JobListResponse, JobStatusResponse
from ..services.job_queue import JobQueueManager, JobWorker


router = APIRouter(prefix="/jobs", tags=["jobs"])
queue_manager = JobQueueManager()
worker = JobWorker()


async def get_jobs_for_key() -> List[Job]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Job))
        return result.scalars().all()


def to_status_response(job: Job) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=job.id,
        service=job.service,
        status=job.status.value if isinstance(job.status, JobStatus) else job.status,
        result=job.result,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/{job_id}")
@unified_response
async def get_job_status(job_id: str) -> dict:
    job = await queue_manager.get_job(job_id)
    return {"job": to_status_response(job).dict()}


@router.get("")
@unified_response
async def list_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> dict:
    jobs = await get_jobs_for_key()
    sliced = jobs[skip : skip + limit]
    response = JobListResponse(jobs=[to_status_response(j) for j in sliced])
    return {"jobs": [job.dict() for job in response.jobs]}


@router.delete("/{job_id}")
@unified_response
async def cancel_job(job_id: str) -> dict:
    await queue_manager.cancel_job(job_id)
    return {"cancelled": True}


@router.websocket("/ws/jobs/{job_id}")
async def job_updates_ws(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    event = worker.get_event(job_id)
    try:
        job = await queue_manager.get_job(job_id)
        await websocket.send_json(to_status_response(job).dict())
        while True:
            await event.wait()
            job = await queue_manager.get_job(job_id)
            await websocket.send_json(to_status_response(job).dict())
            if job.status in (JobStatus.completed, JobStatus.failed):
                break
            event.clear()
    except WebSocketDisconnect:
        return
    finally:
        await websocket.close()

