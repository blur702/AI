"""
Async job queue management for long-running generation tasks.

Provides job creation, status tracking, and background processing
for AI generation requests that may take extended time to complete.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select

from ..config import settings
from ..models.database import AsyncSessionLocal, ErrorSeverity, Job, JobStatus
from ..utils.error_logger import log_error, log_exception, mark_job_errors_resolved
from ..utils.exceptions import JobNotFoundError, JobTimeoutError, ServiceUnavailableError
from ..utils.logger import logger
from .vram_service import VRAMService


class JobQueueManager:
    """
    Manages job lifecycle in the database.

    Provides CRUD operations for async jobs with status tracking
    and error handling.
    """

    async def create_job(
        self,
        service: str,
        request_data: dict[str, Any],
        timeout_seconds: int = 300,
    ) -> str:
        """
        Create a new async job in the database.

        Args:
            service: Service name (e.g., "comfyui", "wan2gp", "stable_audio")
            request_data: Service-specific request payload
            timeout_seconds: Maximum execution time before job is marked as failed (default: 300)

        Returns:
            Job ID (UUID string) for tracking status

        Raises:
            DatabaseError: If job creation fails
        """
        async with AsyncSessionLocal() as session:
            job = Job(
                service=service,
                status=JobStatus.pending,
                request_data=request_data,
                timeout_seconds=timeout_seconds,
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            logger.info(f"Job created: {job.id} for service {service}")
            return job.id

    async def get_job(self, job_id: str) -> Job:
        """
        Retrieve a job by ID.

        Args:
            job_id: UUID string of the job to retrieve

        Returns:
            Job instance with current status, result, and metadata

        Raises:
            JobNotFoundError: If job_id does not exist in database
        """
        async with AsyncSessionLocal() as session:
            job = await session.get(Job, job_id)
            if not job:
                raise JobNotFoundError(f"Job {job_id} not found")
            return job

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """
        Update job status and optionally set result or error.

        Args:
            job_id: UUID string of the job to update
            status: New status (pending, running, completed, failed)
            result: Service response data if status is completed
            error: Error message if status is failed

        Raises:
            JobNotFoundError: If job_id does not exist in database
        """
        async with AsyncSessionLocal() as session:
            job = await session.get(Job, job_id)
            if not job:
                raise JobNotFoundError(f"Job {job_id} not found")
            job.status = status
            job.result = result
            job.error = error
            job.updated_at = datetime.now(UTC)
            await session.commit()
            logger.info(f"Job {job_id} updated to {status}")

    async def get_pending_jobs(self) -> list[Job]:
        """
        Retrieve all jobs with pending status, ordered by creation time.

        Returns:
            List of Job instances awaiting processing (oldest first)
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Job).where(Job.status == JobStatus.pending).order_by(Job.created_at)
            )
            return result.scalars().all()

    async def cancel_job(self, job_id: str) -> None:
        """
        Cancel a pending or running job by marking it as failed.

        Args:
            job_id: UUID string of the job to cancel

        Raises:
            JobNotFoundError: If job_id does not exist in database
        """
        await self.update_job_status(job_id, JobStatus.failed, error="Job cancelled")


class JobWorker:
    """
    Background worker that processes async jobs from the queue.

    Polls the database for pending jobs and executes them sequentially,
    updating status and triggering events for WebSocket notifications.
    """

    def __init__(self) -> None:
        """Initialize worker with queue manager and event tracking."""
        self._running = False
        self._task: asyncio.Task | None = None
        self.queue_manager = JobQueueManager()
        self._job_events: dict[str, asyncio.Event] = {}

    async def start(self) -> None:
        """
        Start the background worker task.

        Idempotent - does nothing if already running. Creates an asyncio task
        that polls for pending jobs every 2 seconds.
        """
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Job worker started")

    async def stop(self) -> None:
        """
        Stop the background worker gracefully.

        Sets running flag to False and waits for current task to complete.
        Does not interrupt jobs in progress.
        """
        self._running = False
        if self._task:
            await self._task
        logger.info("Job worker stopped")

    def get_event(self, job_id: str) -> asyncio.Event:
        """
        Get or create an asyncio event for a job.

        Used for WebSocket notifications - clients can await this event
        to be notified when job status changes.

        Args:
            job_id: UUID string of the job

        Returns:
            asyncio.Event that is set when job status updates
        """
        if job_id not in self._job_events:
            self._job_events[job_id] = asyncio.Event()
        return self._job_events[job_id]

    async def _run(self) -> None:
        """
        Main worker loop that polls for pending jobs.

        Runs continuously while worker is active, checking for pending jobs
        every 2 seconds and processing them sequentially.
        """
        async with httpx.AsyncClient() as client:
            while self._running:
                pending_jobs = await self.queue_manager.get_pending_jobs()
                for job in pending_jobs:
                    await self._process_job(job, client)
                await asyncio.sleep(2)

    async def _process_job(self, job: Job, client: httpx.AsyncClient) -> None:
        """
        Execute a single job by forwarding request to the target service.

        Handles VRAM management, timeout enforcement, status updates, and
        event notifications for WebSocket clients.

        Args:
            job: Job instance to process
            client: Reusable HTTP client for service requests

        Raises:
            JobTimeoutError: If job exceeds configured timeout
            ServiceUnavailableError: If service returns 5xx status
            VRAMConflictError: If GPU resources are insufficient
        """
        logger.info(f"Processing job {job.id} for service {job.service}")
        await self.queue_manager.update_job_status(job.id, JobStatus.running)
        event = self.get_event(job.id)
        event.set()
        event.clear()

        service_url = settings.SERVICES.get(job.service)
        if not service_url:
            await self.queue_manager.update_job_status(
                job.id, JobStatus.failed, error="Unknown service"
            )
            # Persist a structured error record linked to this job.
            try:
                await log_error(
                    service=job.service,
                    message="Unknown service in job queue",
                    severity=ErrorSeverity.error,
                    context={"job_id": job.id, "service_url": None},
                    job_id=job.id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Failed to record unknown-service error: {exc}")
            event.set()
            return

        try:
            await VRAMService.ensure_service_ready(job.service)
            timeout = job.timeout_seconds

            async def execute() -> dict[str, Any]:
                response = await client.post(
                    service_url,
                    json=job.request_data,
                    timeout=timeout,
                )
                if response.status_code >= 500:
                    raise ServiceUnavailableError(
                        f"Service {job.service} responded with {response.status_code}"
                    )
                return response.json()

            start = datetime.now(UTC)
            result = await asyncio.wait_for(execute(), timeout=timeout)
            elapsed = (datetime.now(UTC) - start).total_seconds()
            logger.info(f"Job {job.id} completed in {elapsed:.2f}s")
            await self.queue_manager.update_job_status(job.id, JobStatus.completed, result=result)
            # Any prior errors for this job are now considered resolved.
            try:
                await mark_job_errors_resolved(
                    job.id,
                    resolution="Job completed successfully after previous failures",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Failed to mark job errors resolved: {exc}")
        except TimeoutError as exc:
            await self.queue_manager.update_job_status(
                job.id, JobStatus.failed, error="Job timeout"
            )
            try:
                await log_exception(
                    service=job.service,
                    exc=JobTimeoutError(f"Job {job.id} exceeded timeout"),
                    severity=ErrorSeverity.error,
                    context={"job_id": job.id, "service_url": service_url},
                    job_id=job.id,
                )
            except Exception as log_exc:  # noqa: BLE001
                logger.warning(f"Failed to record timeout error: {log_exc}")
            raise JobTimeoutError(f"Job {job.id} exceeded timeout") from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"Job {job.id} failed")
            await self.queue_manager.update_job_status(job.id, JobStatus.failed, error=str(exc))
            try:
                await log_exception(
                    service=job.service,
                    exc=exc,
                    severity=ErrorSeverity.error,
                    context={"job_id": job.id, "service_url": service_url},
                    job_id=job.id,
                )
            except Exception as log_exc:  # noqa: BLE001
                logger.warning(f"Failed to record job failure error: {log_exc}")
        finally:
            event.set()
