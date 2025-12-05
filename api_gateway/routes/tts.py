from fastapi import APIRouter

from ..middleware.response import unified_response
from ..models.schemas import TTSRequest
from ..services.job_queue import JobQueueManager


router = APIRouter(prefix="/tts", tags=["tts"])
queue_manager = JobQueueManager()


@router.post("")
@unified_response
async def text_to_speech(payload: TTSRequest) -> dict:
    job_id = await queue_manager.create_job("alltalk", payload.dict())
    return {"job_id": job_id, "status": "pending"}

