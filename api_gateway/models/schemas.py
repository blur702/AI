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


# -----------------------------------------------------------------------------
# Price Comparison Schemas
# -----------------------------------------------------------------------------


class ProductSearchRequest(BaseModel):
    """
    Request model for product search.

    Attributes:
        query: Product to search for
        services: Specific services to search (default: all)
        location: Zip code for location-based results
    """

    query: str = Field(..., min_length=1, max_length=200, description="Product to search for")
    services: list[str] | None = Field(
        None, description="Specific services to search (default: all)"
    )
    location: str = Field("20024", description="Zip code for location-based results")


class ProductAttributes(BaseModel):
    """
    LLM-extracted product attributes for comparison.

    Attributes:
        brand: Extracted brand name
        size: Original size string
        size_oz: Normalized size in ounces
        unit_price: Price per ounce
        is_organic: Whether product is organic
        product_type: Product category (e.g., "milk", "bread")
        confidence: LLM confidence in extraction (0.0-1.0)
    """

    brand: str | None = None
    size: str | None = None
    size_oz: float | None = None
    unit_price: float | None = None
    is_organic: bool = False
    product_type: str | None = None
    confidence: float = 0.5


class ProductInfo(BaseModel):
    """
    Individual product information with similarity data.

    Attributes:
        id: Product UUID
        service: Service name (e.g., "amazon_fresh")
        name: Product display name
        price: Price string (e.g., "$3.99")
        size: Product size (e.g., "1 gal")
        brand: Brand name
        url: Product page URL
        image_url: Product image URL
        availability: Whether product is in stock
        similarity_score: Similarity to group representative (0.0-1.0)
        attributes: LLM-extracted product attributes
    """

    id: str
    service: str
    name: str
    price: str
    size: str | None = None
    brand: str | None = None
    url: str
    image_url: str | None = None
    availability: bool = True
    similarity_score: float = 0.0
    attributes: ProductAttributes | None = None


class ProductGroup(BaseModel):
    """
    Group of similar products with reasoning.

    Attributes:
        representative_name: Name of the representative product for this group
        reasoning: LLM explanation for why products are grouped together
        products: List of products in this group
    """

    representative_name: str = ""
    reasoning: str = ""
    products: list[ProductInfo] = []


class ProductSearchResponse(BaseModel):
    """
    Response model for product search.

    Attributes:
        query: Original search query
        comparison_id: UUID of the comparison record
        location: Zip code for location-based results
        status: Search status (completed, error, partial)
        services_scraped: List of services that were successfully scraped
        groups: Products grouped by similarity with reasoning
        llm_analysis: LLM's comparison insights (best value, recommendations)
        model_used: Which Ollama model performed analysis
        from_cache: Whether results came from cache
        errors: List of errors encountered during search
    """

    query: str
    comparison_id: str | None = None
    location: str | None = None
    status: str = "completed"
    services_scraped: list[str] = []
    groups: list[ProductGroup] = []
    llm_analysis: dict[str, Any] | None = None
    model_used: str | None = None
    from_cache: bool = False
    errors: list[str] | None = None


class BulkUploadItem(BaseModel):
    """
    Single item in a bulk upload request.

    Attributes:
        query: Product search query
        quantity: Number of items needed
    """

    query: str = Field(..., min_length=1, max_length=200)
    quantity: int = Field(1, ge=1)


class BulkUploadRequest(BaseModel):
    """
    Request model for bulk shopping list upload.

    Attributes:
        items: List of items with quantities
        name: Name for this list
        session_token: Session token for user identification
    """

    items: list[BulkUploadItem] = Field(..., description="List of items with quantities")
    name: str = Field("Shopping List", description="Name for this list")
    session_token: str = Field(..., description="Session token")


class BulkUploadResponse(BaseModel):
    """
    Response model for bulk upload.

    Attributes:
        list_id: UUID of the shopping list
        job_id: UUID of the processing job
        status: Current processing status
    """

    list_id: str
    job_id: str
    status: str


class SavedSelectionInfo(BaseModel):
    """
    Information about a saved product selection.

    Attributes:
        id: Selection UUID
        product: Product information
        quantity: Quantity saved
        notes: User notes
        created_at: When selection was saved
    """

    id: str
    product: ProductInfo
    quantity: int = 1
    notes: str | None = None
    created_at: datetime


class SavedSelectionsResponse(BaseModel):
    """
    Response model for saved selections.

    Attributes:
        selections: List of saved product selections
        total_items: Total number of items saved
    """

    selections: list[SavedSelectionInfo]
    total_items: int
