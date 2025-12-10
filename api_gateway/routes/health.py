"""
Health check endpoint for API Gateway.

Provides system health status including database connectivity and GPU status.
Used by monitoring systems and load balancers to verify service availability.
"""
from datetime import datetime, timezone

from fastapi import APIRouter

from ..middleware.response import unified_response
from ..models.database import engine
from ..services.vram_service import VRAMService


router = APIRouter(tags=["health"])


@router.get("/health")
@unified_response
async def health() -> dict:
    """
    Comprehensive health check for API Gateway and dependencies.

    Verifies connectivity to critical services (PostgreSQL database, GPU) and
    returns overall system health status. Used by monitoring systems and load
    balancers to determine service availability.

    Returns:
        dict: Contains:
            - status: "healthy" if all services operational, "degraded" otherwise
            - services: Boolean flags for database and GPU availability
            - gpu: GPU status object with VRAM usage (if available)
            - timestamp: ISO 8601 UTC timestamp of the health check
    """
    db_ok = False
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda _: None)
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False

    gpu_status = None
    gpu_ok = False
    try:
        gpu_status = VRAMService.get_gpu_status()
        gpu_ok = True
    except Exception:  # noqa: BLE001
        gpu_status = None
        gpu_ok = False

    status = "healthy" if db_ok and gpu_ok else "degraded"
    return {
        "status": status,
        "services": {
            "database": db_ok,
            "gpu_ok": gpu_ok,
        },
        "gpu": gpu_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
