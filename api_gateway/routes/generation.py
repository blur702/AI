from fastapi import APIRouter

from ..middleware.response import unified_response
from ..models.schemas import (
    AudioGenerationRequest,
    ImageGenerationRequest,
    MusicGenerationRequest,
    VideoGenerationRequest,
)
from ..services.job_queue import JobQueueManager


router = APIRouter(prefix="/generate", tags=["generation"])
queue_manager = JobQueueManager()


@router.post("/image")
@unified_response
async def generate_image(payload: ImageGenerationRequest) -> dict:
    job_id = await queue_manager.create_job(
        "comfyui",
        payload.dict(),
    )
    return {"job_id": job_id, "status": "pending"}


@router.post("/video")
@unified_response
async def generate_video(payload: VideoGenerationRequest) -> dict:
    job_id = await queue_manager.create_job(
        "wan2gp",
        payload.dict(),
    )
    return {"job_id": job_id, "status": "pending"}


@router.post("/audio")
@unified_response
async def generate_audio(payload: AudioGenerationRequest) -> dict:
    engine = payload.engine.lower()
    service = "stable_audio" if engine == "stable_audio" else "audiocraft"
    job_id = await queue_manager.create_job(service, payload.dict())
    return {"job_id": job_id, "status": "pending"}


@router.post("/music")
@unified_response
async def generate_music(payload: MusicGenerationRequest) -> dict:
    engine = payload.engine.lower()
    if engine == "yue":
        service = "yue"
    elif engine == "diffrhythm":
        service = "diffrhythm"
    else:
        service = "musicgpt"
    job_id = await queue_manager.create_job(service, payload.dict())
    return {"job_id": job_id, "status": "pending"}

