import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import select

from ..config import settings
from ..models.database import AsyncSessionLocal, Job, JobStatus
from ..utils.exceptions import JobNotFoundError, JobTimeoutError, ServiceUnavailableError
from ..utils.logger import logger
from .vram_service import VRAMService


class JobQueueManager:
    async def create_job(
        self,
        service: str,
        request_data: Dict[str, Any],
        timeout_seconds: int = 300,
    ) -> str:
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
        async with AsyncSessionLocal() as session:
            job = await session.get(Job, job_id)
            if not job:
                raise JobNotFoundError(f"Job {job_id} not found")
            return job

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        async with AsyncSessionLocal() as session:
            job = await session.get(Job, job_id)
            if not job:
                raise JobNotFoundError(f"Job {job_id} not found")
            job.status = status
            job.result = result
            job.error = error
            job.updated_at = datetime.utcnow()
            await session.commit()
            logger.info(f"Job {job_id} updated to {status}")

    async def get_pending_jobs(self) -> List[Job]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Job).where(Job.status == JobStatus.pending).order_by(Job.created_at)
            )
            return result.scalars().all()

    async def cancel_job(self, job_id: str) -> None:
        await self.update_job_status(job_id, JobStatus.failed, error="Job cancelled")


class JobWorker:
    def __init__(self) -> None:
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.queue_manager = JobQueueManager()
        self._job_events: Dict[str, asyncio.Event] = {}

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Job worker started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            await self._task
        logger.info("Job worker stopped")

    def get_event(self, job_id: str) -> asyncio.Event:
        if job_id not in self._job_events:
            self._job_events[job_id] = asyncio.Event()
        return self._job_events[job_id]

    async def _run(self) -> None:
        async with httpx.AsyncClient() as client:
            while self._running:
                pending_jobs = await self.queue_manager.get_pending_jobs()
                for job in pending_jobs:
                    await self._process_job(job, client)
                await asyncio.sleep(2)

    async def _process_job(self, job: Job, client: httpx.AsyncClient) -> None:
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
            event.set()
            return

        try:
            await VRAMService.ensure_service_ready(job.service)
            timeout = job.timeout_seconds

            async def execute() -> Dict[str, Any]:
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

            start = datetime.utcnow()
            result = await asyncio.wait_for(execute(), timeout=timeout)
            elapsed = (datetime.utcnow() - start).total_seconds()
            logger.info(f"Job {job.id} completed in {elapsed:.2f}s")
            await self.queue_manager.update_job_status(
                job.id, JobStatus.completed, result=result
            )
        except asyncio.TimeoutError as exc:
            await self.queue_manager.update_job_status(
                job.id, JobStatus.failed, error="Job timeout"
            )
            raise JobTimeoutError(f"Job {job.id} exceeded timeout") from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"Job {job.id} failed")
            await self.queue_manager.update_job_status(
                job.id, JobStatus.failed, error=str(exc)
            )
        finally:
            event.set()

