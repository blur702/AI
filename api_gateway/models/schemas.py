"""
Pydantic schemas for API request/response models.

Defines data transfer objects for API Gateway endpoints including
generation requests, job status responses, and unified response format.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class UnifiedError(BaseModel):
    """Error object within unified response."""

    code: str
    message: str


class UnifiedResponse(BaseModel):
    """Standard API response format with success/error handling."""

    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[UnifiedError] = None
    job_id: Optional[str] = None
    timestamp: str


class JobStatusResponse(BaseModel):
    """
    Response model for job status queries.

    Attributes:
        job_id: Unique job identifier
        service: Service handling the job (e.g., "comfyui", "stable_audio")
        status: Current job status (pending/running/completed/failed)
        result: Job output data if completed successfully
        error: Error message if job failed
        created_at: Timestamp when job was created
        updated_at: Timestamp when job was last updated
    """

    job_id: str
    service: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CreateAPIKeyRequest(BaseModel):
    """
    Request model for creating a new API key.

    Attributes:
        name: Human-readable name for the API key (e.g., "Mobile App", "Production Server")
    """

    name: str


class CreateAPIKeyResponse(BaseModel):
    """
    Response model for API key creation.

    Attributes:
        key: The generated API key string (should be stored securely by client)
        name: Human-readable name for the key
        created_at: Timestamp when key was created
    """

    key: str
    name: str
    created_at: datetime


class ImageGenerationRequest(BaseModel):
    """
    Request model for image generation via ComfyUI.

    Attributes:
        prompt: Text description of desired image
        model: Model identifier (defaults to configured default)
        width: Image width in pixels (default: 512)
        height: Image height in pixels (default: 512)
        steps: Number of diffusion steps (default: 30, higher=better quality but slower)
    """

    prompt: str
    model: Optional[str] = None
    width: Optional[int] = 512
    height: Optional[int] = 512
    steps: Optional[int] = 30


class VideoGenerationRequest(BaseModel):
    """
    Request model for video generation via Wan2GP.

    Attributes:
        prompt: Text description of desired video
        duration: Video duration in seconds (default: 10)
        model: Model identifier (defaults to configured default)
    """

    prompt: str
    duration: Optional[int] = 10
    model: Optional[str] = None


class AudioGenerationRequest(BaseModel):
    """
    Request model for audio generation.

    Attributes:
        prompt: Text description of desired audio
        engine: Audio generation engine ("stable_audio" or "audiocraft")
        duration: Audio duration in seconds (default: 10)
    """

    prompt: str
    engine: str
    duration: Optional[int] = 10


class MusicGenerationRequest(BaseModel):
    """
    Request model for music generation.

    Attributes:
        prompt: Text description of desired music style/content
        engine: Music generation engine ("yue", "diffrhythm", or "musicgen")
        duration: Music duration in seconds (default: 30)
    """

    prompt: str
    engine: str
    duration: Optional[int] = 30


class TTSRequest(BaseModel):
    """
    Request model for text-to-speech synthesis via AllTalk.

    Attributes:
        text: Text to synthesize into speech
        voice: Voice identifier (defaults to configured default voice)
        speed: Playback speed multiplier (0.5-2.0, default: 1.0)
    """

    text: str
    voice: Optional[str] = None
    speed: Optional[float] = Field(default=1.0, ge=0.5, le=2.0)


class LLMRequest(BaseModel):
    """
    Request model for LLM text generation via Ollama.

    Attributes:
        prompt: Text prompt for the language model
        model: Model identifier (e.g., "llama3.2", defaults to configured default)
        temperature: Sampling temperature (0.0-1.0, default: 0.7, higher=more random)
    """

    prompt: str
    model: Optional[str] = None
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=1.0)


class JobListResponse(BaseModel):
    """
    Response model for listing multiple jobs.

    Attributes:
        jobs: List of job status objects
    """

    jobs: List[JobStatusResponse]

