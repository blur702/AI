"""
Job tracking and monitoring endpoints for async generation tasks.

Provides REST and WebSocket interfaces for querying job status, listing jobs,
canceling in-progress jobs, and receiving real-time updates via WebSocket.
All generation requests (image, video, audio, music) return job IDs that can
be monitored through these endpoints.
"""
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
    """
    Retrieve all jobs from the database.

    Note: Currently returns all jobs regardless of API key. Future versions
    will filter by the authenticated API key for multi-tenant support.

    Returns:
        List[Job]: All job records from the database.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Job))
        return result.scalars().all()


def to_status_response(job: Job) -> JobStatusResponse:
    """
    Convert a Job database model to a JobStatusResponse schema.

    Handles conversion of JobStatus enum to string value and ensures
    all fields are properly formatted for API responses.

    Args:
        job: Job database model instance.

    Returns:
        JobStatusResponse: Pydantic model ready for JSON serialization.
    """
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
    """
    Get the current status of a specific job.

    Retrieves detailed information about a job including its current status
    (pending, running, completed, failed), result data, error messages, and
    timestamps.

    Args:
        job_id: UUID of the job to query.

    Returns:
        dict: Contains 'job' object with status, result, error, and timestamps.

    Raises:
        HTTPException: 404 if job_id not found.
    """
    job = await queue_manager.get_job(job_id)
    return {"job": to_status_response(job).dict()}


@router.get("")
@unified_response
async def list_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> dict:
    """
    List all jobs with pagination support.

    Returns a paginated list of all jobs in the system. Supports offset-based
    pagination via skip and limit parameters.

    Args:
        skip: Number of records to skip (default: 0).
        limit: Maximum number of records to return (default: 50, max: 100).

    Returns:
        dict: Contains 'jobs' array with job status objects.
    """
    jobs = await get_jobs_for_key()
    sliced = jobs[skip : skip + limit]
    response = JobListResponse(jobs=[to_status_response(j) for j in sliced])
    return {"jobs": [job.dict() for job in response.jobs]}


@router.delete("/{job_id}")
@unified_response
async def cancel_job(job_id: str) -> dict:
    """
    Cancel a pending or running job.

    Attempts to cancel the specified job. If the job is pending, it will be
    marked as failed. If already running, cancellation depends on service support.
    Completed jobs cannot be cancelled.

    Args:
        job_id: UUID of the job to cancel.

    Returns:
        dict: Contains 'cancelled': True if cancellation was initiated.

    Raises:
        HTTPException: 404 if job_id not found.
    """
    await queue_manager.cancel_job(job_id)
    return {"cancelled": True}


@router.websocket("/ws/jobs/{job_id}")
async def job_updates_ws(websocket: WebSocket, job_id: str) -> None:
    """
    WebSocket endpoint for real-time job status updates.

    Establishes a WebSocket connection that sends job status updates whenever
    the job state changes. Automatically closes when the job reaches a terminal
    state (completed or failed) or when the client disconnects.

    Args:
        websocket: WebSocket connection instance managed by FastAPI.
        job_id: UUID of the job to monitor.

    Raises:
        WebSocketDisconnect: When client closes the connection.
        HTTPException: 404 if job_id not found during initial lookup.
    """
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

