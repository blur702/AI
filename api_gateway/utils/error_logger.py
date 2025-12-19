"""
Centralized helpers for writing errors and their resolutions to PostgreSQL.

This module uses the Error model defined in api_gateway.models.database
to persist error details, stack traces, contextual metadata, and resolution
information. It is intended to be used by both request handlers and background
workers so all failures are captured consistently.
"""

from __future__ import annotations

import traceback
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from ..models.database import AsyncSessionLocal, Error, ErrorSeverity
from .logger import logger


async def log_error(
    service: str,
    message: str,
    *,
    severity: ErrorSeverity = ErrorSeverity.error,
    stack_trace: str | None = None,
    context: dict[str, Any] | None = None,
    job_id: str | None = None,
) -> Error:
    """
    Persist an error record to the database.

    Args:
        service: Name of the component or service emitting the error.
        message: Human-readable error message.
        severity: Error severity level (default: error).
        stack_trace: Optional traceback string.
        context: Optional structured context (request info, params, etc.).
        job_id: Optional related job identifier.

    Returns:
        The newly created Error ORM instance.
    """
    async with AsyncSessionLocal() as session:
        error = Error(
            service=service,
            severity=severity,
            message=message,
            stack_trace=stack_trace,
            context=context,
            job_id=job_id,
        )
        session.add(error)
        await session.commit()
        await session.refresh(error)
        logger.info(
            "Recorded error in database",
            extra={
                "service": service,
                "severity": severity.value,
                "job_id": job_id,
                "error_id": error.id,
            },
        )
        return error


async def log_exception(
    service: str,
    exc: Exception,
    *,
    severity: ErrorSeverity = ErrorSeverity.error,
    context: dict[str, Any] | None = None,
    job_id: str | None = None,
) -> Error:
    """
    Convenience wrapper to log an exception with full traceback.
    """
    stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    message = str(exc)
    return await log_error(
        service=service,
        message=message,
        severity=severity,
        stack_trace=stack,
        context=context,
        job_id=job_id,
    )


async def mark_error_resolved(
    error_id: str,
    *,
    resolution: str | None = None,
) -> Error | None:
    """
    Mark a single Error row as resolved and optionally store a resolution note.
    """
    async with AsyncSessionLocal() as session:
        error = await session.get(Error, error_id)
        if error is None:
            return None

        error.resolved = True
        error.resolved_at = datetime.now(UTC)
        if resolution:
            error.resolution = resolution

        await session.commit()
        await session.refresh(error)
        logger.info(
            "Marked error as resolved",
            extra={"error_id": error.id, "job_id": error.job_id},
        )
        return error


async def mark_job_errors_resolved(
    job_id: str,
    *,
    resolution: str = "Job completed successfully",
) -> int:
    """
    Mark all unresolved errors associated with a given job_id as resolved.

    Args:
        job_id: Identifier of the job whose errors should be resolved.
        resolution: Human-readable explanation of how the issue was fixed.

    Returns:
        Number of Error rows updated.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Error).where(Error.job_id == job_id, Error.resolved.is_(False))
        )
        errors = list(result.scalars())
        if not errors:
            return 0

        now = datetime.now(UTC)
        for error in errors:
            error.resolved = True
            error.resolved_at = now
            error.resolution = resolution

        await session.commit()
        logger.info(
            "Marked %s error(s) resolved for job",
            len(errors),
            extra={"job_id": job_id},
        )
        return len(errors)
