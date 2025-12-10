"""
LLM generation routes for Ollama integration.

Provides endpoints for text generation and model listing via the Ollama API.
"""
import asyncio

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
    """
    Submit an LLM text generation request to Ollama.

    Creates an async job for text generation using the specified model
    and prompt. The job is queued for background processing.

    Args:
        payload: LLM request containing model name, prompt, and options.

    Returns:
        Dictionary with job_id for status polling and initial status.
    """
    await VRAMService.ensure_service_ready("ollama")
    job_id = await queue_manager.create_job("ollama", payload.dict())
    return {"job_id": job_id, "status": "pending"}


@router.get("/models")
@unified_response
async def list_models() -> dict:
    """
    List currently loaded Ollama models.

    Returns the models that are currently loaded in GPU memory
    and available for immediate inference.

    Returns:
        Dictionary containing list of loaded model names.
    """
    # Run sync subprocess call in thread pool to avoid blocking event loop
    models = await asyncio.to_thread(VRAMService.get_loaded_models)
    return {"models": models}

