"""
Unified response middleware for API Gateway.

Provides a decorator that wraps endpoint responses in a standard format
with success/error handling and consistent JSON structure.
"""
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Awaitable, Callable, Dict

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from ..models.schemas import UnifiedError, UnifiedResponse
from ..utils.exceptions import (
    InvalidAPIKeyError,
    JobNotFoundError,
    JobTimeoutError,
    ServiceUnavailableError,
    VRAMConflictError,
)
from ..utils.logger import logger


# Import RateLimitExceededError conditionally to avoid circular imports
def _get_rate_limit_error():
    """Lazily import RateLimitExceededError to avoid circular imports."""
    try:
        from ..routes.congressional import RateLimitExceededError
        return RateLimitExceededError
    except ImportError:
        return None


def unified_response(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """
    Decorator that wraps endpoint results in a unified response format.

    Catches known exceptions and returns appropriate error responses.
    Successful responses are wrapped with success=True and the result in data field.

    Args:
        func: Async endpoint function to wrap

    Returns:
        Wrapped function that returns JSONResponse with unified format
    """
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> JSONResponse:
        """
        Wrapper function that executes endpoint and formats response.

        Catches exceptions and converts them to unified error responses.
        Successful results are wrapped with success=True and timestamp.

        Args:
            *args: Positional arguments passed to wrapped function
            **kwargs: Keyword arguments passed to wrapped function

        Returns:
            JSONResponse with UnifiedResponse format
        """
        now = datetime.now(timezone.utc).isoformat()
        try:
            result = await func(*args, **kwargs)
            payload: Dict[str, Any] = {
                "success": True,
                "data": result if isinstance(result, dict) else result,
                "error": None,
                "job_id": getattr(result, "job_id", None)
                if not isinstance(result, dict)
                else result.get("job_id"),
                "timestamp": now,
            }
            return JSONResponse(content=UnifiedResponse(**payload).dict())
        except (
            ServiceUnavailableError,
            VRAMConflictError,
            JobNotFoundError,
            InvalidAPIKeyError,
            JobTimeoutError,
        ) as exc:
            code = getattr(exc, "code", "ERROR")
            message = getattr(exc, "message", str(exc))
            logger.error(f"{code}: {message}")
            error = UnifiedError(code=code, message=message)
            status_code = 401 if code == "INVALID_API_KEY" else 400
            return JSONResponse(
                status_code=status_code,
                content=UnifiedResponse(
                    success=False,
                    data=None,
                    error=error,
                    job_id=None,
                    timestamp=now,
                ).dict(),
            )
        except HTTPException as exc:
            logger.error(f"HTTPException: {exc.detail}")
            error = UnifiedError(code="HTTP_ERROR", message=str(exc.detail))
            return JSONResponse(
                status_code=exc.status_code,
                content=UnifiedResponse(
                    success=False, data=None, error=error, job_id=None, timestamp=now
                ).dict(),
            )
        except Exception as exc:  # noqa: BLE001
            # Check for RateLimitExceededError (imported lazily to avoid circular imports)
            RateLimitExceededError = _get_rate_limit_error()
            if RateLimitExceededError and isinstance(exc, RateLimitExceededError):
                code = getattr(exc, "code", "RATE_LIMIT_EXCEEDED")
                message = getattr(exc, "message", str(exc))
                retry_after = getattr(exc, "retry_after", 60)
                logger.warning(f"{code}: {message}")
                error = UnifiedError(code=code, message=message)
                return JSONResponse(
                    status_code=429,
                    content=UnifiedResponse(
                        success=False,
                        data=None,
                        error=error,
                        job_id=None,
                        timestamp=now,
                    ).dict(),
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(retry_after),
                    },
                )
            # Unhandled exception
            logger.exception("Unhandled exception")
            error = UnifiedError(code="INTERNAL_ERROR", message=str(exc))
            return JSONResponse(
                status_code=500,
                content=UnifiedResponse(
                    success=False, data=None, error=error, job_id=None, timestamp=now
                ).dict(),
            )

    return wrapper

