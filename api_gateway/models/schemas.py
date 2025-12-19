"""
Pydantic schemas for API request/response models.

Defines data transfer objects for API Gateway endpoints including
generation requests, job status responses, and unified response format.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UnifiedError(BaseModel):
    """Error object within unified response."""

    code: str
    message: str


class UnifiedResponse(BaseModel):
    """Standard API response format with success/error handling."""

    success: bool
    data: dict[str, Any] | None = None
    error: UnifiedError | None = None
    job_id: str | None = None
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
    result: dict[str, Any] | None = None
    error: str | None = None
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
    model: str | None = None
    width: int | None = 512
    height: int | None = 512
    steps: int | None = 30


class VideoGenerationRequest(BaseModel):
    """
    Request model for video generation via Wan2GP.

    Attributes:
        prompt: Text description of desired video
        duration: Video duration in seconds (default: 10)
        model: Model identifier (defaults to configured default)
    """

    prompt: str
    duration: int | None = 10
    model: str | None = None


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
    duration: int | None = 10


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
    duration: int | None = 30


class TTSRequest(BaseModel):
    """
    Request model for text-to-speech synthesis via AllTalk.

    Attributes:
        text: Text to synthesize into speech
        voice: Voice identifier (defaults to configured default voice)
        speed: Playback speed multiplier (0.5-2.0, default: 1.0)
    """

    text: str
    voice: str | None = None
    speed: float | None = Field(default=1.0, ge=0.5, le=2.0)


class LLMRequest(BaseModel):
    """
    Request model for LLM text generation via Ollama.

    Attributes:
        prompt: Text prompt for the language model
        model: Model identifier (e.g., "llama3.2", defaults to configured default)
        temperature: Sampling temperature (0.0-1.0, default: 0.7, higher=more random)
    """

    prompt: str
    model: str | None = None
    temperature: float | None = Field(default=0.7, ge=0.0, le=1.0)


class JobListResponse(BaseModel):
    """
    Response model for listing multiple jobs.

    Attributes:
        jobs: List of job status objects
    """

    jobs: list[JobStatusResponse]


# -----------------------------------------------------------------------------
# Congressional Data Schemas
# -----------------------------------------------------------------------------


class CongressionalMemberInfo(BaseModel):
    """
    Information about a congressional member.

    Attributes:
        name: Full name of the member
        state: State represented (e.g., "CA", "TX")
        district: Congressional district number
        party: Political party ("D", "R", "I")
        chamber: "House" or "Senate"
        website_url: Member's official website URL
        rss_feed_url: Member's RSS feed URL
    """

    name: str
    state: str
    district: str
    party: str
    chamber: str
    website_url: str = ""
    rss_feed_url: str = ""


class CongressionalMemberResponse(BaseModel):
    """
    Response model for listing congressional members.

    Attributes:
        members: List of congressional member info objects
    """

    members: list[CongressionalMemberInfo]


class CongressionalQueryRequest(BaseModel):
    """
    Request model for querying congressional content.

    Attributes:
        query: Semantic search query text
        member_name: Filter by specific member name
        party: Filter by party ("D", "R", "I")
        state: Filter by state code
        topic: Filter by topic
        date_from: Filter by minimum scrape date
        date_to: Filter by maximum scrape date
        limit: Maximum number of results (default: 10)
    """

    query: str
    member_name: str | None = None
    party: str | None = None
    state: str | None = None
    topic: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    limit: int = Field(default=10, ge=1, le=100)


class CongressionalQueryResult(BaseModel):
    """
    Single result from congressional content query.

    Attributes:
        member_name: Name of the congressional member
        state: State the member represents
        district: Congressional district
        party: Political party
        chamber: House or Senate
        title: Page or article title
        content_text: Content snippet
        url: Source URL
        scraped_at: ISO timestamp of scrape time
    """

    member_name: str
    state: str
    district: str
    party: str
    chamber: str
    title: str
    content_text: str
    url: str
    scraped_at: str


class CongressionalQueryResponse(BaseModel):
    """
    Response model for congressional content query.

    Attributes:
        results: List of query results
        total_results: Total number of results returned
    """

    results: list[CongressionalQueryResult]
    total_results: int


class CongressionalScrapeRequest(BaseModel):
    """
    Request model for starting a congressional scrape job.

    Attributes:
        max_members: Maximum number of members to scrape (None = all)
        max_pages_per_member: Maximum pages to scrape per member (default: 5)
        dry_run: If True, don't write to database
    """

    max_members: int | None = None
    max_pages_per_member: int | None = 5
    dry_run: bool = False


class CongressionalScrapeStatusResponse(BaseModel):
    """
    Response model for congressional scrape job status.

    Attributes:
        status: Current job status (idle, running, completed, failed, cancelled)
        stats: Scrape statistics (members_processed, pages_scraped, etc.)
        started_at: Timestamp when scrape started
        completed_at: Timestamp when scrape completed
        error: Error message if job failed
    """

    status: str
    stats: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class CongressionalChatRequest(BaseModel):
    """
    Request model for congressional chat/RAG queries.

    Attributes:
        message: Natural language question about congressional data
        member_filter: Optional filter to focus on one member
        conversation_id: Optional ID to continue a conversation
    """

    message: str = Field(..., min_length=1, max_length=2000)
    member_filter: str | None = None
    conversation_id: str | None = None


class CongressionalChatSource(BaseModel):
    """
    A source document referenced in the chat response.

    Attributes:
        member_name: Name of the congressional member
        title: Document title
        content_preview: Short preview of the content
        url: Source URL
        party: Political party
        state: State code
    """

    member_name: str
    title: str
    content_preview: str
    url: str
    party: str
    state: str


class CongressionalChatResponse(BaseModel):
    """
    Response model for congressional chat/RAG queries.

    Attributes:
        answer: Generated natural language answer
        sources: List of source documents used
        conversation_id: ID for conversation continuity
        model: LLM model used for generation
    """

    answer: str
    sources: list[CongressionalChatSource]
    conversation_id: str
    model: str
