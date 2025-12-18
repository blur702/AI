"""
Database models and connection setup for API Gateway.

Defines SQLAlchemy ORM models for:
    - Job: Async job tracking for generation tasks
    - APIKey: API key authentication and tracking
    - Todo: Task management for LLM use
    - Error: Error tracking and monitoring

Uses PostgreSQL with asyncpg driver for async operations.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, JSON, String, Text, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from ..config import settings


Base = declarative_base()


class JobStatus(str, enum.Enum):
    """
    Status values for async job tracking.

    Attributes:
        pending: Job created but not yet started
        running: Job currently executing
        completed: Job finished successfully
        failed: Job encountered an error and could not complete
    """

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class TodoStatus(str, enum.Enum):
    """
    Status values for task management.

    Attributes:
        pending: Task not yet started
        in_progress: Task currently being worked on
        completed: Task finished
    """

    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"


class ErrorSeverity(str, enum.Enum):
    """
    Severity levels for error tracking.

    Attributes:
        info: Informational message, not an error
        warning: Warning condition that should be reviewed
        error: Error condition that prevented an operation from completing
        critical: Critical failure requiring immediate attention
    """

    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"


class Job(Base):
    """
    Async job tracking for long-running generation tasks.

    Tracks status, input parameters, results, and errors for async operations
    like image/video/audio generation. Used by API Gateway to manage background
    tasks and provide polling endpoints for clients.

    Attributes:
        id: UUID primary key
        service: Service name (e.g., "comfyui", "stable_audio")
        status: Current job status (pending/running/completed/failed)
        request_data: Original request parameters as JSON
        result: Job output data as JSON (e.g., file paths, URLs)
        error: Error message if job failed
        created_at: Timestamp when job was created
        updated_at: Timestamp when job was last updated
        timeout_seconds: Maximum execution time before job is considered failed
    """

    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    service = Column(String, nullable=False)
    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.pending)
    request_data = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )
    timeout_seconds = Column(Integer, default=300, nullable=False)


class APIKey(Base):
    """
    API key authentication and usage tracking.

    Stores API keys for client authentication. Keys are indexed for fast lookup
    during authentication middleware processing.

    Attributes:
        key: API key string (primary key, indexed)
        name: Human-readable name for the key
        created_at: Timestamp when key was created
        last_used_at: Timestamp of most recent authentication
        is_active: Whether the key is currently valid for authentication
    """

    __tablename__ = "api_keys"

    key = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)


class Todo(Base):
    """
    Task management for LLM-based todo tracking.

    Provides structured storage for tasks with status, priority, and tagging.
    Designed for LLM agents to track and manage their own work items.

    Attributes:
        id: UUID primary key
        title: Short task description
        description: Detailed task description
        status: Current task status (pending/in_progress/completed)
        priority: Task priority (0=low, higher=more urgent)
        due_date: Optional deadline
        tags: Array of tags as JSON (e.g., ["bug", "feature", "docs"])
        created_at: Timestamp when task was created
        updated_at: Timestamp when task was last modified
        completed_at: Timestamp when task was marked complete
    """

    __tablename__ = "todos"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(TodoStatus), nullable=False, default=TodoStatus.pending)
    priority = Column(Integer, default=0, nullable=False)
    due_date = Column(DateTime, nullable=True)
    tags = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at = Column(DateTime, nullable=True)


class Error(Base):
    """
    Error tracking and monitoring for all services.

    Captures exceptions, stack traces, and contextual information for debugging.
    Indexed by service and created_at for efficient querying. Job_id links errors
    to specific async operations.

    Attributes:
        id: UUID primary key
        service: Service that raised the error (indexed)
        severity: Error severity level (info/warning/error/critical)
        message: Error message
        resolution: Optional human-readable explanation of how the error was fixed
        stack_trace: Full exception traceback
        context: Additional context as JSON (e.g., file paths, input parameters)
        job_id: Related job ID if error occurred during async operation (indexed)
        created_at: Timestamp when error occurred (indexed)
        resolved: Whether the error has been addressed
        ready_for_review: Whether the error has been triaged and is ready for human review
        resolved_at: Timestamp when error was marked resolved
    """

    __tablename__ = "errors"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    service = Column(String(100), nullable=False, index=True)
    severity = Column(Enum(ErrorSeverity), nullable=False, default=ErrorSeverity.error)
    message = Column(Text, nullable=False)
    resolution = Column(Text, nullable=True)
    stack_trace = Column(Text, nullable=True)
    context = Column(JSON, nullable=True)
    job_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    resolved = Column(Boolean, default=False, nullable=False)
    ready_for_review = Column(Boolean, default=False, nullable=False)
    resolved_at = Column(DateTime, nullable=True)


# PostgreSQL connection pool configuration
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=settings.DB_POOL_RECYCLE,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def _add_column_if_not_exists(conn, column_sql: str) -> None:
    """
    Add column to errors table, ignoring if already exists.

    Args:
        conn: Database connection
        column_sql: SQL column definition (e.g., "resolution TEXT")
    """
    try:
        await conn.execute(text(f"ALTER TABLE errors ADD COLUMN {column_sql}"))
    except Exception as exc:  # noqa: BLE001
        # If the column already exists, swallow the error; otherwise re-raise.
        # SQLite uses "duplicate column name", PostgreSQL uses "already exists"
        msg = str(exc).lower()
        if "duplicate column" not in msg and not ("column" in msg and "already exists" in msg):
            raise


async def init_db() -> None:
    """
    Initialize database schema by creating all tables.

    Runs CREATE TABLE statements for all models defined in this module.
    Safe to call multiple times (uses CREATE TABLE IF NOT EXISTS).
    Should be called once at application startup.
    """
    async with engine.begin() as conn:
        # Ensure all tables exist
        await conn.run_sync(Base.metadata.create_all)

        # Backwards-compatible migrations for errors table columns.
        # Use ADD COLUMN and ignore duplicate-column errors so this is
        # safe to run repeatedly across SQLite and PostgreSQL.
        await _add_column_if_not_exists(conn, "resolution TEXT")
        await _add_column_if_not_exists(conn, "ready_for_review BOOLEAN NOT NULL DEFAULT FALSE")

