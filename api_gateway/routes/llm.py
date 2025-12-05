from fastapi import APIRouter

from ..middleware.response import unified_response
from ..models.schemas import LLMRequest
from ..services.job_queue import JobQueueManager
from ..services.vram_service import VRAMService


router = APIRouter(prefix="/llm", tags=["llm"])
queue_manager = JobQueueManager()


@router.post("/generate")
@unified_response
async def generate_llm(payload: LLMRequest) -> dict:
    await VRAMService.ensure_service_ready("ollama")
    job_id = await queue_manager.create_job("ollama", payload.dict())
    return {"job_id": job_id, "status": "pending"}


@router.get("/models")
@unified_response
async def list_models() -> dict:
    models = VRAMService.get_loaded_models()
    return {"models": models}

