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

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from ..config import settings


Base = declarative_base()


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class TodoStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"


class ErrorSeverity(str, enum.Enum):
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"


class Job(Base):
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
    __tablename__ = "api_keys"

    key = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)


class Todo(Base):
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
    __tablename__ = "errors"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    service = Column(String(100), nullable=False, index=True)
    severity = Column(Enum(ErrorSeverity), nullable=False, default=ErrorSeverity.error)
    message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    context = Column(JSON, nullable=True)
    job_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    resolved = Column(Boolean, default=False, nullable=False)
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


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

