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
    job_id: str
    service: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CreateAPIKeyRequest(BaseModel):
    name: str


class CreateAPIKeyResponse(BaseModel):
    key: str
    name: str
    created_at: datetime


class ImageGenerationRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    width: Optional[int] = 512
    height: Optional[int] = 512
    steps: Optional[int] = 30


class VideoGenerationRequest(BaseModel):
    prompt: str
    duration: Optional[int] = 10
    model: Optional[str] = None


class AudioGenerationRequest(BaseModel):
    prompt: str
    engine: str
    duration: Optional[int] = 10


class MusicGenerationRequest(BaseModel):
    prompt: str
    engine: str
    duration: Optional[int] = 30


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None
    speed: Optional[float] = Field(default=1.0, ge=0.5, le=2.0)


class LLMRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=1.0)


class JobListResponse(BaseModel):
    jobs: List[JobStatusResponse]

