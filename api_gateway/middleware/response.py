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


def unified_response(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> JSONResponse:
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
            logger.exception("Unhandled exception")
            error = UnifiedError(code="INTERNAL_ERROR", message=str(exc))
            return JSONResponse(
                status_code=500,
                content=UnifiedResponse(
                    success=False, data=None, error=error, job_id=None, timestamp=now
                ).dict(),
            )

    return wrapper

