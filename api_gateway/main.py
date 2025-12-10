"""
AI API Gateway - FastAPI Unified Interface.

Central REST/WebSocket interface for external clients (mobile apps, integrations)
to access AI generation services. Provides unified endpoints for image, video,
audio, music generation, TTS, and LLM text generation.

Features:
- API key authentication via X-API-Key header
- Async job management with status polling and WebSocket updates
- CORS support for cross-origin requests
- Request/response logging with timing
- Prometheus metrics endpoint

Endpoints:
    POST /generate/image - ComfyUI image generation
    POST /generate/video - Wan2GP video generation
    POST /generate/audio - Stable Audio / AudioCraft
    POST /generate/music - YuE / DiffRhythm / MusicGPT
    POST /tts - AllTalk text-to-speech
    POST /llm/generate - Ollama text generation
    GET /jobs/{job_id} - Poll job status
    GET /ws/jobs/{job_id} - WebSocket job updates
    GET /health - Health check
    GET /metrics - Prometheus metrics

Usage:
    python -m api_gateway.main
    # or via start_gateway.bat
"""
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from .config import settings
from .routes import health as health_routes
from .utils.logger import logger


app = FastAPI(title="AI API Gateway", version="1.0.0")

# Core middleware (CORS, logging) is always enabled. Later-phase middleware
# such as API key auth can be added conditionally once stable.
try:
    from .middleware.auth import APIKeyMiddleware

    app.add_middleware(APIKeyMiddleware)
except Exception as exc:  # noqa: BLE001
    logger.warning(f"API key middleware disabled due to initialization error: {exc}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

worker = None


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """
    HTTP middleware for request/response logging with timing.

    Logs incoming request details (method, path, headers, body size) and outgoing
    response details (status code, duration). Redacts X-API-Key header for security.

    Args:
        request: Incoming FastAPI request
        call_next: Next middleware/handler in chain

    Returns:
        Response from downstream handler
    """
    start = datetime.utcnow()
    body = await request.body()
    redacted_headers = {
        k: v for k, v in request.headers.items() if k.lower() != "x-api-key"
    }
    logger.info(
        f"Request {request.method} {request.url.path} "
        f"headers={redacted_headers} body_size={len(body)}"
    )
    response = await call_next(request)
    duration = (datetime.utcnow() - start).total_seconds()
    logger.info(
        f"Response {request.method} {request.url.path} "
        f"status={response.status_code} duration={duration:.4f}s"
    )
    return response


@app.get("/metrics")
async def metrics() -> PlainTextResponse:
    """
    Prometheus metrics endpoint.

    Returns basic gateway health metrics in Prometheus text format.
    Currently exports api_gateway_up gauge (1 = running).

    Returns:
        PlainTextResponse with Prometheus-formatted metrics
    """
    lines = [
        "# HELP api_gateway_up API Gateway up status",
        "# TYPE api_gateway_up gauge",
        "api_gateway_up 1",
    ]
    return PlainTextResponse("\n".join(lines))


@app.on_event("startup")
async def on_startup() -> None:
    """
    Application startup event handler.

    Initializes database schema and starts background job worker.
    Failures are logged but don't prevent the gateway from starting,
    allowing graceful degradation of optional features.

    Raises:
        Exceptions are caught and logged; startup always succeeds
    """
    global worker
    # Initialize database (later-phase). Failure here should not prevent
    # the base gateway from starting.
    try:
        from .models.database import init_db

        await init_db()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Database initialization failed: {exc}")

    # Start job worker if available; otherwise log and continue.
    try:
        from .services.job_queue import JobWorker as _JobWorker

        worker = _JobWorker()
        await worker.start()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Job worker initialization failed: {exc}")

    logger.info("API Gateway startup sequence completed")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """
    Application shutdown event handler.

    Gracefully stops background job worker. Failures are logged but don't
    prevent shutdown from completing.

    Raises:
        Exceptions are caught and logged; shutdown always succeeds
    """
    global worker
    if worker is not None:
        try:
            await worker.stop()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Job worker shutdown failed: {exc}")

    logger.info("API Gateway shutdown sequence completed")


# Routers for later-phase features are registered defensively so problems in
# those modules do not prevent the base app from running.
try:
    from .routes import auth as auth_routes

    app.include_router(auth_routes.router)
except Exception as exc:  # noqa: BLE001
    logger.warning(f"Auth routes disabled due to initialization error: {exc}")

try:
    from .routes import generation as generation_routes

    app.include_router(generation_routes.router)
except Exception as exc:  # noqa: BLE001
    logger.warning(f"Generation routes disabled due to initialization error: {exc}")

try:
    from .routes import tts as tts_routes

    app.include_router(tts_routes.router)
except Exception as exc:  # noqa: BLE001
    logger.warning(f"TTS routes disabled due to initialization error: {exc}")

try:
    from .routes import llm as llm_routes

    app.include_router(llm_routes.router)
except Exception as exc:  # noqa: BLE001
    logger.warning(f"LLM routes disabled due to initialization error: {exc}")

try:
    from .routes import jobs as jobs_routes

    app.include_router(jobs_routes.router)
except Exception as exc:  # noqa: BLE001
    logger.warning(f"Job routes disabled due to initialization error: {exc}")

# Health is part of the foundational phase and is expected to be present.
app.include_router(health_routes.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for unhandled errors.

    Catches all exceptions that weren't handled by route-specific handlers
    and returns a unified error response with 500 status code.

    Args:
        request: Request that caused the exception
        exc: Exception that was raised

    Returns:
        JSONResponse with unified error format and 500 status
    """
    from .models.schemas import UnifiedError, UnifiedResponse
    from .models.database import ErrorSeverity
    from .utils.error_logger import log_exception

    logger.exception("Global exception handler caught an error")

    # Best-effort persistence of the error to PostgreSQL.
    try:
        context = {
            "path": request.url.path,
            "method": request.method,
            "client": request.client.host if request.client else None,
        }
        await log_exception(
            service="api_gateway",
            exc=exc,
            severity=ErrorSeverity.critical,
            context=context,
            job_id=None,
        )
    except Exception as db_exc:  # noqa: BLE001
        logger.warning(f"Failed to record error in database: {db_exc}")

    error = UnifiedError(code="INTERNAL_ERROR", message=str(exc))
    payload = UnifiedResponse(
        success=False,
        data=None,
        error=error,
        job_id=None,
        timestamp=datetime.utcnow().isoformat(),
    )
    return JSONResponse(status_code=500, content=payload.dict())


def run() -> None:
    """
    Start the API Gateway server with uvicorn.

    Binds to all interfaces (0.0.0.0) on the configured API_PORT.
    Auto-reload is disabled for production use.
    """
    uvicorn.run("api_gateway.main:app", host="0.0.0.0", port=settings.API_PORT, reload=False)


if __name__ == "__main__":
    run()
