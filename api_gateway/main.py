import asyncio
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
    lines = [
        "# HELP api_gateway_up API Gateway up status",
        "# TYPE api_gateway_up gauge",
        "api_gateway_up 1",
    ]
    return PlainTextResponse("\n".join(lines))


@app.on_event("startup")
async def on_startup() -> None:
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
    from .models.schemas import UnifiedError, UnifiedResponse

    logger.exception("Global exception handler caught an error")
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
    uvicorn.run("api_gateway.main:app", host="0.0.0.0", port=settings.API_PORT, reload=False)


if __name__ == "__main__":
    run()
