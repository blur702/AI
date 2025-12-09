"""
Text-to-Speech routes for AllTalk TTS integration.

Provides endpoints for converting text to speech audio via AllTalk.
"""
from fastapi import APIRouter

from ..middleware.response import unified_response
from ..models.schemas import TTSRequest
from ..services.job_queue import JobQueueManager


router = APIRouter(prefix="/tts", tags=["tts"])
queue_manager = JobQueueManager()


@router.post("")
@unified_response
async def text_to_speech(payload: TTSRequest) -> dict:
    """
    Submit a text-to-speech synthesis request to AllTalk.

    Creates an async job for TTS synthesis using the specified text,
    voice, and audio settings. The job is queued for background processing.

    Args:
        payload: TTS request containing text, voice selection, and options.

    Returns:
        Dictionary with job_id for status polling and initial status.
    """
    job_id = await queue_manager.create_job("alltalk", payload.dict())
    return {"job_id": job_id, "status": "pending"}

