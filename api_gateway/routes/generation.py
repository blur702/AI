"""
AI generation endpoints for image, video, audio, and music creation.

Provides unified interface for submitting generation jobs to various backend
services (ComfyUI, Wan2GP, Stable Audio, AudioCraft, YuE, DiffRhythm, MusicGPT).
All requests return immediately with a job_id for async tracking via /jobs endpoints.
"""
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
    """
    Submit an image generation job to ComfyUI.

    Creates an async job that will be processed by ComfyUI using the specified
    workflow and parameters. The job runs in the background and can be monitored
    via the returned job_id.

    Args:
        payload: Image generation parameters including workflow, prompt, and settings.

    Returns:
        dict: Contains job_id (UUID) and status ("pending").
    """
    job_id = await queue_manager.create_job(
        "comfyui",
        payload.dict(),
    )
    return {"job_id": job_id, "status": "pending"}


@router.post("/video")
@unified_response
async def generate_video(payload: VideoGenerationRequest) -> dict:
    """
    Submit a video generation job to Wan2GP.

    Creates an async job for video generation using Wan2GP. The job processes
    in the background and can be tracked via the returned job_id.

    Args:
        payload: Video generation parameters including prompt and duration settings.

    Returns:
        dict: Contains job_id (UUID) and status ("pending").
    """
    job_id = await queue_manager.create_job(
        "wan2gp",
        payload.dict(),
    )
    return {"job_id": job_id, "status": "pending"}


@router.post("/audio")
@unified_response
async def generate_audio(payload: AudioGenerationRequest) -> dict:
    """
    Submit an audio generation job to Stable Audio or AudioCraft.

    Routes the request to the appropriate backend service based on the specified
    engine. Supports both Stable Audio and AudioCraft for audio synthesis.

    Args:
        payload: Audio generation parameters including engine selection and prompt.

    Returns:
        dict: Contains job_id (UUID) and status ("pending").
    """
    engine = payload.engine.lower()
    service = "stable_audio" if engine == "stable_audio" else "audiocraft"
    job_id = await queue_manager.create_job(service, payload.dict())
    return {"job_id": job_id, "status": "pending"}


@router.post("/music")
@unified_response
async def generate_music(payload: MusicGenerationRequest) -> dict:
    """
    Submit a music generation job to YuE, DiffRhythm, or MusicGPT.

    Routes the request to the specified music generation engine. Each service
    provides different approaches to music synthesis and composition.

    Args:
        payload: Music generation parameters including engine selection and musical prompt.

    Returns:
        dict: Contains job_id (UUID) and status ("pending").
    """
    engine = payload.engine.lower()
    if engine == "yue":
        service = "yue"
    elif engine == "diffrhythm":
        service = "diffrhythm"
    else:
        service = "musicgpt"
    job_id = await queue_manager.create_job(service, payload.dict())
    return {"job_id": job_id, "status": "pending"}

