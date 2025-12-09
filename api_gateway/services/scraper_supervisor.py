"""
Scraper Supervisor - Monitors, restarts, and resumes scraping jobs.

A flexible system for managing long-running scraping tasks with:
- Health monitoring and automatic restart on failure
- Resume from last checkpoint
- Scheduled task integration (Windows Task Scheduler)
- Support for multiple scraper types via registry

Usage:
    # Run supervisor daemon
    python -m api_gateway.services.scraper_supervisor run

    # Check job status
    python -m api_gateway.services.scraper_supervisor status

    # Start a new job
    python -m api_gateway.services.scraper_supervisor start drupal --limit 1000

    # Resume a failed job
    python -m api_gateway.services.scraper_supervisor resume drupal

    # Install Windows scheduled task
    python -m api_gateway.services.scraper_supervisor install-task --interval 5
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..utils.logger import get_logger

logger = get_logger("api_gateway.scraper_supervisor")

# Default paths
SUPERVISOR_DATA_DIR = Path(os.environ.get("SCRAPER_DATA_DIR", "D:/AI/data/scraper"))
JOBS_FILE = SUPERVISOR_DATA_DIR / "jobs.json"
CHECKPOINTS_DIR = SUPERVISOR_DATA_DIR / "checkpoints"


class JobStatus(str, Enum):
    """Status of a scraper job."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobCheckpoint:
    """Checkpoint for resumable scraping."""
    job_id: str
    scraper_type: str
    last_entity_type: str = ""
    last_entity_name: str = ""
    last_page: int = 0
    entities_processed: int = 0
    entities_inserted: int = 0
    errors: int = 0
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobCheckpoint":
        return cls(**data)


@dataclass
class ScraperJob:
    """Configuration and state for a scraper job."""
    job_id: str
    scraper_type: str
    status: JobStatus = JobStatus.PENDING
    config: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    last_heartbeat: str = ""
    pid: Optional[int] = None
    error_message: str = ""
    retry_count: int = 0
    max_retries: int = 3

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScraperJob":
        data["status"] = JobStatus(data.get("status", "pending"))
        return cls(**data)


class JobRegistry:
    """Persists and manages scraper jobs."""

    def __init__(self, jobs_file: Path = JOBS_FILE):
        self.jobs_file = jobs_file
        self.jobs_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _load(self) -> Dict[str, ScraperJob]:
        """Load jobs from JSON file."""
        if not self.jobs_file.exists():
            return {}
        try:
            with open(self.jobs_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {k: ScraperJob.from_dict(v) for k, v in data.items()}
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON in jobs file: %s", e)
            return {}
        except OSError as e:
            logger.warning("Failed to read jobs file: %s", e)
            return {}
        except Exception as e:
            logger.warning("Unexpected error loading jobs file: %s", e)
            return {}

    def _save(self, jobs: Dict[str, ScraperJob]) -> None:
        """Save jobs to JSON file."""
        try:
            with open(self.jobs_file, "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in jobs.items()}, f, indent=2)
        except OSError as e:
            logger.error("Failed to write jobs file: %s", e)
            raise
        except Exception as e:
            logger.error("Unexpected error saving jobs file: %s", e)
            raise

    def get(self, job_id: str) -> Optional[ScraperJob]:
        with self._lock:
            jobs = self._load()
            return jobs.get(job_id)

    def get_all(self) -> List[ScraperJob]:
        with self._lock:
            jobs = self._load()
            return list(jobs.values())

    def get_by_type(self, scraper_type: str) -> Optional[ScraperJob]:
        """Get the most recent job for a scraper type."""
        with self._lock:
            jobs = self._load()
            type_jobs = [j for j in jobs.values() if j.scraper_type == scraper_type]
            if type_jobs:
                return sorted(type_jobs, key=lambda j: j.created_at, reverse=True)[0]
            return None

    def save(self, job: ScraperJob) -> None:
        with self._lock:
            jobs = self._load()
            jobs[job.job_id] = job
            self._save(jobs)

    def delete(self, job_id: str) -> bool:
        with self._lock:
            jobs = self._load()
            if job_id in jobs:
                del jobs[job_id]
                self._save(jobs)
                return True
            return False


class CheckpointManager:
    """Manages checkpoints for resumable scraping."""

    def __init__(self, checkpoints_dir: Path = CHECKPOINTS_DIR):
        self.checkpoints_dir = checkpoints_dir
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, job_id: str) -> Path:
        return self.checkpoints_dir / f"{job_id}.json"

    def save(self, checkpoint: JobCheckpoint) -> None:
        """Save checkpoint to JSON file."""
        checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
        path = self._get_path(checkpoint.job_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(checkpoint.to_dict(), f, indent=2)
            logger.debug("Saved checkpoint for job %s", checkpoint.job_id)
        except OSError as e:
            logger.error("Failed to write checkpoint for %s: %s", checkpoint.job_id, e)
            raise
        except Exception as e:
            logger.error("Unexpected error saving checkpoint for %s: %s", checkpoint.job_id, e)
            raise

    def load(self, job_id: str) -> Optional[JobCheckpoint]:
        """Load checkpoint from JSON file."""
        path = self._get_path(job_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return JobCheckpoint.from_dict(data)
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON in checkpoint for %s: %s", job_id, e)
            return None
        except OSError as e:
            logger.warning("Failed to read checkpoint for %s: %s", job_id, e)
            return None
        except Exception as e:
            logger.warning("Unexpected error loading checkpoint for %s: %s", job_id, e)
            return None

    def delete(self, job_id: str) -> bool:
        path = self._get_path(job_id)
        if path.exists():
            path.unlink()
            return True
        return False


# Scraper type registry - maps type names to runner functions
ScraperRunner = Callable[[ScraperJob, Optional[JobCheckpoint], CheckpointManager], Dict[str, Any]]
SCRAPER_REGISTRY: Dict[str, ScraperRunner] = {}


def register_scraper(scraper_type: str) -> Callable[[ScraperRunner], ScraperRunner]:
    """Decorator to register a scraper runner function."""
    def decorator(func: ScraperRunner) -> ScraperRunner:
        SCRAPER_REGISTRY[scraper_type] = func
        return func
    return decorator


@register_scraper("drupal")
def run_drupal_scraper(
    job: ScraperJob,
    checkpoint: Optional[JobCheckpoint],
    checkpoint_manager: CheckpointManager,
) -> Dict[str, Any]:
    """Run the Drupal API scraper with checkpoint support."""
    from .drupal_api_schema import (
        create_drupal_api_collection,
        get_collection_stats,
    )
    from .drupal_scraper import (
        DrupalAPIScraper,
        ScrapeConfig,
        ENTITY_LISTINGS,
        get_entity_text_for_embedding,
    )
    from ..utils.embeddings import get_embedding
    from .weaviate_connection import DRUPAL_API_COLLECTION_NAME, WeaviateConnection

    config = job.config
    scrape_config = ScrapeConfig(
        request_delay=config.get("request_delay", 2.0),
        batch_size=config.get("batch_size", 10),
        batch_delay=config.get("batch_delay", 5.0),
        max_entities=config.get("max_entities"),
        dry_run=config.get("dry_run", False),
    )

    # Initialize checkpoint if resuming
    if checkpoint:
        entities_processed = checkpoint.entities_processed
        entities_inserted = checkpoint.entities_inserted
        errors = checkpoint.errors
        start_entity_type = checkpoint.last_entity_type
        start_after_name = checkpoint.last_entity_name
        logger.info(
            "Resuming from checkpoint: type=%s, after=%s, processed=%d",
            start_entity_type, start_after_name, entities_processed,
        )
    else:
        entities_processed = 0
        entities_inserted = 0
        errors = 0
        start_entity_type = ""
        start_after_name = ""
        checkpoint = JobCheckpoint(
            job_id=job.job_id,
            scraper_type="drupal",
        )

    # Track which entity type we're currently processing
    skip_until_type = start_entity_type if start_entity_type else None
    skip_until_name = start_after_name if start_after_name else None

    try:
        with WeaviateConnection() as client:
            # Create collection if needed (won't delete existing)
            create_drupal_api_collection(client, force_reindex=False)
            collection = client.collections.get(DRUPAL_API_COLLECTION_NAME)

            # Get existing UUIDs to skip duplicates
            logger.info("Loading existing entity UUIDs for deduplication...")
            existing_uuids = set()
            try:
                for obj in collection.iterator(include_vector=False):
                    props = obj.properties
                    if props and "uuid" in props:
                        existing_uuids.add(props["uuid"])
            except Exception as e:
                logger.warning("Could not load existing UUIDs: %s", e)
            logger.info("Found %d existing entities", len(existing_uuids))

            with DrupalAPIScraper(config=scrape_config) as scraper:
                for listing_path, entity_type in ENTITY_LISTINGS.items():
                    # Skip entity types until we reach the resume point
                    if skip_until_type:
                        if entity_type != skip_until_type:
                            logger.info("Skipping entity type %s (resuming from %s)", entity_type, skip_until_type)
                            continue
                        skip_until_type = None  # Found our type, now look for name

                    logger.info("Processing entity type: %s", entity_type)

                    for entity in scraper.scrape_listing(listing_path, entity_type):
                        # Skip entities until we pass the resume point
                        if skip_until_name:
                            if entity.name == skip_until_name:
                                skip_until_name = None  # Found it, start processing next
                            logger.debug("Skipping %s (resuming after %s)", entity.name, start_after_name)
                            continue

                        # Increment counter only for entities actually processed (after skip point)
                        entities_processed += 1

                        # Check max entities limit
                        if scrape_config.max_entities and entities_processed >= scrape_config.max_entities:
                            logger.info("Reached max entities limit: %d", scrape_config.max_entities)
                            break

                        # Skip if already in collection
                        if entity.uuid in existing_uuids:
                            logger.debug("Skipping existing entity: %s", entity.full_name)
                            continue

                        # Insert into Weaviate
                        if not scrape_config.dry_run:
                            try:
                                text = get_entity_text_for_embedding(entity)
                                vector = get_embedding(text)
                                collection.data.insert(
                                    entity.to_properties(),
                                    uuid=entity.uuid,
                                    vector=vector,
                                )
                                entities_inserted += 1
                                existing_uuids.add(entity.uuid)

                            except Exception as e:
                                errors += 1
                                logger.warning("Failed to insert %s: %s", entity.full_name, e)

                        # Update checkpoint every 10 entities
                        if entities_processed % 10 == 0:
                            checkpoint.last_entity_type = entity_type
                            checkpoint.last_entity_name = entity.name
                            checkpoint.entities_processed = entities_processed
                            checkpoint.entities_inserted = entities_inserted
                            checkpoint.errors = errors
                            checkpoint_manager.save(checkpoint)
                            logger.info(
                                "Checkpoint: processed=%d, inserted=%d, errors=%d",
                                entities_processed, entities_inserted, errors,
                            )

                    # Check limit after each entity type
                    if scrape_config.max_entities and entities_processed >= scrape_config.max_entities:
                        break

        return {
            "success": True,
            "entities_processed": entities_processed,
            "entities_inserted": entities_inserted,
            "errors": errors,
        }

    except Exception as e:
        logger.exception("Drupal scraper failed: %s", e)
        # Save checkpoint on failure
        checkpoint.entities_processed = entities_processed
        checkpoint.entities_inserted = entities_inserted
        checkpoint.errors = errors
        checkpoint_manager.save(checkpoint)

        return {
            "success": False,
            "error": str(e),
            "entities_processed": entities_processed,
            "entities_inserted": entities_inserted,
            "errors": errors,
        }


@register_scraper("mdn_javascript")
def run_mdn_javascript_scraper(
    job: ScraperJob,
    checkpoint: Optional[JobCheckpoint],
    checkpoint_manager: CheckpointManager,
) -> Dict[str, Any]:
    """Run the MDN JavaScript documentation scraper with checkpoint support."""
    from .mdn_schema import (
        create_mdn_javascript_collection,
        get_mdn_javascript_stats,
    )
    from .mdn_javascript_scraper import (
        MDNJavaScriptScraper,
        ScrapeConfig,
        get_doc_text_for_embedding,
    )
    from ..utils.embeddings import get_embedding
    from .weaviate_connection import MDN_JAVASCRIPT_COLLECTION_NAME, WeaviateConnection

    config = job.config
    scrape_config = ScrapeConfig(
        request_delay=config.get("request_delay", 1.0),
        batch_size=config.get("batch_size", 20),
        batch_delay=config.get("batch_delay", 3.0),
        max_entities=config.get("max_entities"),
        dry_run=config.get("dry_run", False),
    )

    # Initialize checkpoint if resuming
    if checkpoint:
        entities_processed = checkpoint.entities_processed
        entities_inserted = checkpoint.entities_inserted
        errors = checkpoint.errors
        skip_until_name = checkpoint.last_entity_name if checkpoint.last_entity_name else None
        logger.info(
            "Resuming from checkpoint: processed=%d, inserted=%d, skip_until=%s",
            entities_processed, entities_inserted, skip_until_name,
        )
    else:
        entities_processed = 0
        entities_inserted = 0
        errors = 0
        skip_until_name = None
        checkpoint = JobCheckpoint(
            job_id=job.job_id,
            scraper_type="mdn_javascript",
        )

    try:
        with WeaviateConnection() as client:
            # Create collection if needed
            create_mdn_javascript_collection(client, force_reindex=False)
            collection = client.collections.get(MDN_JAVASCRIPT_COLLECTION_NAME)

            # Get existing URLs to skip duplicates
            logger.info("Loading existing document URLs for deduplication...")
            existing_urls = set()
            try:
                for obj in collection.iterator(include_vector=False):
                    props = obj.properties
                    if props and "url" in props:
                        existing_urls.add(props["url"])
            except Exception as e:
                logger.warning("Could not load existing URLs: %s", e)
            logger.info("Found %d existing documents", len(existing_urls))

            with MDNJavaScriptScraper(config=scrape_config) as scraper:
                for doc in scraper.scrape_all():
                    # Skip entities until we pass the resume point
                    if skip_until_name:
                        if doc.title == skip_until_name:
                            skip_until_name = None  # Found it, start processing next
                        logger.debug("Skipping %s (resuming after %s)", doc.title, checkpoint.last_entity_name)
                        continue

                    entities_processed += 1

                    # Check max entities limit
                    if scrape_config.max_entities and entities_processed >= scrape_config.max_entities:
                        logger.info("Reached max entities limit: %d", scrape_config.max_entities)
                        break

                    # Skip if already in collection
                    if doc.url in existing_urls:
                        logger.debug("Skipping existing doc: %s", doc.title)
                        continue

                    # Insert into Weaviate
                    if not scrape_config.dry_run:
                        try:
                            text = get_doc_text_for_embedding(doc)
                            vector = get_embedding(text)
                            collection.data.insert(
                                doc.to_properties(),
                                uuid=doc.uuid,
                                vector=vector,
                            )
                            entities_inserted += 1
                            existing_urls.add(doc.url)

                        except Exception as e:
                            errors += 1
                            logger.warning("Failed to insert %s: %s", doc.title, e)

                    # Update checkpoint every 10 entities
                    if entities_processed % 10 == 0:
                        checkpoint.last_entity_name = doc.title
                        checkpoint.entities_processed = entities_processed
                        checkpoint.entities_inserted = entities_inserted
                        checkpoint.errors = errors
                        checkpoint_manager.save(checkpoint)
                        logger.info(
                            "Checkpoint: processed=%d, inserted=%d, errors=%d",
                            entities_processed, entities_inserted, errors,
                        )

        return {
            "success": True,
            "entities_processed": entities_processed,
            "entities_inserted": entities_inserted,
            "errors": errors,
        }

    except Exception as e:
        logger.exception("MDN JavaScript scraper failed: %s", e)
        checkpoint.entities_processed = entities_processed
        checkpoint.entities_inserted = entities_inserted
        checkpoint.errors = errors
        checkpoint_manager.save(checkpoint)

        return {
            "success": False,
            "error": str(e),
            "entities_processed": entities_processed,
            "entities_inserted": entities_inserted,
            "errors": errors,
        }


@register_scraper("mdn_webapis")
def run_mdn_webapis_scraper(
    job: ScraperJob,
    checkpoint: Optional[JobCheckpoint],
    checkpoint_manager: CheckpointManager,
) -> Dict[str, Any]:
    """Run the MDN Web APIs documentation scraper with checkpoint support."""
    from .mdn_schema import (
        create_mdn_webapis_collection,
        get_mdn_webapis_stats,
    )
    from .mdn_webapis_scraper import (
        MDNWebAPIsScraper,
        ScrapeConfig,
        get_doc_text_for_embedding,
    )
    from ..utils.embeddings import get_embedding
    from .weaviate_connection import MDN_WEBAPIS_COLLECTION_NAME, WeaviateConnection

    config = job.config
    scrape_config = ScrapeConfig(
        request_delay=config.get("request_delay", 1.0),
        batch_size=config.get("batch_size", 20),
        batch_delay=config.get("batch_delay", 3.0),
        max_entities=config.get("max_entities"),
        dry_run=config.get("dry_run", False),
        section_filter=config.get("section_filter"),
    )

    # Initialize checkpoint if resuming
    if checkpoint:
        entities_processed = checkpoint.entities_processed
        entities_inserted = checkpoint.entities_inserted
        errors = checkpoint.errors
        skip_until_name = checkpoint.last_entity_name if checkpoint.last_entity_name else None
        skip_until_type = checkpoint.last_entity_type if checkpoint.last_entity_type else None
        logger.info(
            "Resuming from checkpoint: processed=%d, inserted=%d, skip_until=%s [%s]",
            entities_processed, entities_inserted, skip_until_name, skip_until_type,
        )
    else:
        entities_processed = 0
        entities_inserted = 0
        errors = 0
        skip_until_name = None
        skip_until_type = None
        checkpoint = JobCheckpoint(
            job_id=job.job_id,
            scraper_type="mdn_webapis",
        )

    try:
        with WeaviateConnection() as client:
            # Create collection if needed
            create_mdn_webapis_collection(client, force_reindex=False)
            collection = client.collections.get(MDN_WEBAPIS_COLLECTION_NAME)

            # Get existing URLs to skip duplicates
            logger.info("Loading existing document URLs for deduplication...")
            existing_urls = set()
            try:
                for obj in collection.iterator(include_vector=False):
                    props = obj.properties
                    if props and "url" in props:
                        existing_urls.add(props["url"])
            except Exception as e:
                logger.warning("Could not load existing URLs: %s", e)
            logger.info("Found %d existing documents", len(existing_urls))

            with MDNWebAPIsScraper(config=scrape_config) as scraper:
                for doc in scraper.scrape_all():
                    # Skip entities until we pass the resume point
                    if skip_until_name:
                        # Match both name and type if type was recorded
                        if doc.title == skip_until_name:
                            if skip_until_type is None or doc.section_type == skip_until_type:
                                skip_until_name = None  # Found it, start processing next
                                skip_until_type = None
                        logger.debug("Skipping %s [%s] (resuming after %s [%s])",
                                   doc.title, doc.section_type,
                                   checkpoint.last_entity_name, checkpoint.last_entity_type)
                        continue

                    entities_processed += 1

                    # Check max entities limit
                    if scrape_config.max_entities and entities_processed >= scrape_config.max_entities:
                        logger.info("Reached max entities limit: %d", scrape_config.max_entities)
                        break

                    # Skip if already in collection
                    if doc.url in existing_urls:
                        logger.debug("Skipping existing doc: %s", doc.title)
                        continue

                    # Insert into Weaviate
                    if not scrape_config.dry_run:
                        try:
                            text = get_doc_text_for_embedding(doc)
                            vector = get_embedding(text)
                            collection.data.insert(
                                doc.to_properties(),
                                uuid=doc.uuid,
                                vector=vector,
                            )
                            entities_inserted += 1
                            existing_urls.add(doc.url)

                        except Exception as e:
                            errors += 1
                            logger.warning("Failed to insert %s: %s", doc.title, e)

                    # Update checkpoint every 10 entities
                    if entities_processed % 10 == 0:
                        checkpoint.last_entity_name = doc.title
                        checkpoint.last_entity_type = doc.section_type
                        checkpoint.entities_processed = entities_processed
                        checkpoint.entities_inserted = entities_inserted
                        checkpoint.errors = errors
                        checkpoint_manager.save(checkpoint)
                        logger.info(
                            "Checkpoint [%s]: processed=%d, inserted=%d, errors=%d",
                            doc.section_type, entities_processed, entities_inserted, errors,
                        )

        return {
            "success": True,
            "entities_processed": entities_processed,
            "entities_inserted": entities_inserted,
            "errors": errors,
        }

    except Exception as e:
        logger.exception("MDN Web APIs scraper failed: %s", e)
        checkpoint.entities_processed = entities_processed
        checkpoint.entities_inserted = entities_inserted
        checkpoint.errors = errors
        checkpoint_manager.save(checkpoint)

        return {
            "success": False,
            "error": str(e),
            "entities_processed": entities_processed,
            "entities_inserted": entities_inserted,
            "errors": errors,
        }


class ScraperSupervisor:
    """
    Supervisor daemon that monitors and manages scraper jobs.

    Features:
    - Monitors running jobs for heartbeat/liveness
    - Automatically restarts failed jobs (up to max_retries)
    - Resumes from checkpoints
    - Handles graceful shutdown
    """

    def __init__(
        self,
        registry: Optional[JobRegistry] = None,
        checkpoint_manager: Optional[CheckpointManager] = None,
        check_interval: int = 30,
        heartbeat_timeout: int = 300,
    ):
        self.registry = registry or JobRegistry()
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.check_interval = check_interval  # seconds
        self.heartbeat_timeout = heartbeat_timeout  # seconds
        self._running = False
        self._current_thread: Optional[threading.Thread] = None

    def start_job(
        self,
        scraper_type: str,
        config: Optional[Dict[str, Any]] = None,
        job_id: Optional[str] = None,
    ) -> ScraperJob:
        """Start a new scraper job."""
        if scraper_type not in SCRAPER_REGISTRY:
            raise ValueError(f"Unknown scraper type: {scraper_type}")

        job_id = job_id or f"{scraper_type}_{int(time.time())}"
        job = ScraperJob(
            job_id=job_id,
            scraper_type=scraper_type,
            status=JobStatus.PENDING,
            config=config or {},
        )
        self.registry.save(job)
        logger.info("Created job: %s", job_id)
        return job

    def run_job(self, job: ScraperJob, resume: bool = False) -> Dict[str, Any]:
        """Run a job synchronously."""
        if job.scraper_type not in SCRAPER_REGISTRY:
            raise ValueError(f"Unknown scraper type: {job.scraper_type}")

        runner = SCRAPER_REGISTRY[job.scraper_type]
        checkpoint = self.checkpoint_manager.load(job.job_id) if resume else None

        # Update job status
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc).isoformat()
        job.pid = os.getpid()
        self.registry.save(job)

        try:
            result = runner(job, checkpoint, self.checkpoint_manager)

            if result.get("success"):
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.now(timezone.utc).isoformat()
                # Clean up checkpoint on success
                self.checkpoint_manager.delete(job.job_id)
            else:
                job.status = JobStatus.FAILED
                job.error_message = result.get("error", "Unknown error")
                job.retry_count += 1

            self.registry.save(job)
            return result

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            job.retry_count += 1
            self.registry.save(job)
            raise

    def resume_job(self, job_id: str) -> Dict[str, Any]:
        """Resume a failed or paused job."""
        job = self.registry.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        if job.status not in (JobStatus.FAILED, JobStatus.PAUSED, JobStatus.PENDING):
            raise ValueError(f"Cannot resume job in status: {job.status}")

        return self.run_job(job, resume=True)

    def _check_job_health(self, job: ScraperJob) -> bool:
        """Check if a running job is still alive."""
        if job.status != JobStatus.RUNNING:
            return True

        # Check PID
        if job.pid:
            try:
                os.kill(job.pid, 0)  # Signal 0 just checks if process exists
            except OSError:
                logger.warning("Job %s process (PID %d) not found", job.job_id, job.pid)
                return False

        # Check heartbeat
        if job.last_heartbeat:
            last_beat = datetime.fromisoformat(job.last_heartbeat.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - last_beat).total_seconds()
            if age > self.heartbeat_timeout:
                logger.warning(
                    "Job %s heartbeat timeout (last: %.0fs ago)",
                    job.job_id, age,
                )
                return False

        return True

    def _maybe_restart_job(self, job: ScraperJob) -> None:
        """Restart a failed job if retries remain."""
        if job.retry_count >= job.max_retries:
            logger.error(
                "Job %s exceeded max retries (%d), not restarting",
                job.job_id, job.max_retries,
            )
            return

        logger.info(
            "Restarting job %s (retry %d/%d)",
            job.job_id, job.retry_count + 1, job.max_retries,
        )

        # Start in a separate thread to not block supervisor
        thread = threading.Thread(
            target=self.run_job,
            args=(job, True),  # resume=True
            daemon=True,
        )
        thread.start()

    def run_once(self) -> None:
        """Single pass of supervisor checks."""
        jobs = self.registry.get_all()

        for job in jobs:
            if job.status == JobStatus.RUNNING:
                if not self._check_job_health(job):
                    job.status = JobStatus.FAILED
                    job.error_message = "Process died or heartbeat timeout"
                    self.registry.save(job)
                    self._maybe_restart_job(job)

            elif job.status == JobStatus.FAILED:
                if job.retry_count < job.max_retries:
                    self._maybe_restart_job(job)

    def run_daemon(self) -> None:
        """Run supervisor as a daemon, checking jobs periodically."""
        self._running = True
        logger.info("Supervisor daemon starting (check_interval=%ds)", self.check_interval)

        def handle_signal(signum, frame):
            logger.info("Received signal %d, shutting down", signum)
            self._running = False

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        while self._running:
            try:
                self.run_once()
            except Exception as e:
                logger.exception("Supervisor check failed: %s", e)

            # Sleep in small increments for responsiveness
            for _ in range(self.check_interval):
                if not self._running:
                    break
                time.sleep(1)

        logger.info("Supervisor daemon stopped")

    def get_status(self) -> Dict[str, Any]:
        """Get status of all jobs."""
        jobs = self.registry.get_all()
        return {
            "jobs": [j.to_dict() for j in jobs],
            "summary": {
                "total": len(jobs),
                "running": sum(1 for j in jobs if j.status == JobStatus.RUNNING),
                "completed": sum(1 for j in jobs if j.status == JobStatus.COMPLETED),
                "failed": sum(1 for j in jobs if j.status == JobStatus.FAILED),
                "pending": sum(1 for j in jobs if j.status == JobStatus.PENDING),
            },
        }


def install_windows_task(interval_minutes: int = 5) -> None:
    """
    Install a Windows Scheduled Task to run the supervisor check.

    Args:
        interval_minutes: Interval in minutes between health checks (default: 5)

    Raises:
        subprocess.CalledProcessError: If task creation fails
    """
    task_name = "ScraperSupervisor"
    python_exe = sys.executable
    script_path = Path(__file__).resolve()
    working_dir = script_path.parent.parent.parent  # D:\AI

    # Build the command to run (cd to working directory first so module can find resources)
    cmd = f'cd /d "{working_dir}" && "{python_exe}" -m api_gateway.services.scraper_supervisor check'

    # Create the scheduled task using schtasks
    schtasks_cmd = [
        "schtasks", "/create",
        "/tn", task_name,
        "/tr", cmd,
        "/sc", "MINUTE",
        "/mo", str(interval_minutes),
        "/f",  # Force overwrite if exists
    ]

    try:
        result = subprocess.run(schtasks_cmd, capture_output=True, text=True, check=True, timeout=30)
        logger.info("Scheduled task created: %s", task_name)
        print(f"Created scheduled task '{task_name}' to run every {interval_minutes} minutes")
        print(f"Command: {cmd}")
    except subprocess.TimeoutExpired as e:
        logger.error("Timeout creating scheduled task after 30 seconds")
        print("Error: Task creation timed out")
        raise
    except subprocess.CalledProcessError as e:
        logger.error("Failed to create scheduled task: %s", e.stderr)
        print(f"Error creating task: {e.stderr}")
        raise


def uninstall_windows_task() -> None:
    """
    Remove the Windows Scheduled Task.

    Raises:
        subprocess.CalledProcessError: If task removal fails
    """
    task_name = "ScraperSupervisor"

    try:
        subprocess.run(
            ["schtasks", "/delete", "/tn", task_name, "/f"],
            capture_output=True, text=True, check=True, timeout=30,
        )
        logger.info("Scheduled task removed: %s", task_name)
        print(f"Removed scheduled task '{task_name}'")
    except subprocess.TimeoutExpired as e:
        logger.error("Timeout removing scheduled task after 30 seconds")
        print("Error: Task removal timed out")
        raise
    except subprocess.CalledProcessError as e:
        logger.error("Failed to remove scheduled task: %s", e.stderr)
        print(f"Error removing task: {e.stderr}")
        raise


def main(argv: Optional[List[str]] = None) -> None:
    """
    CLI entry point for scraper supervisor.

    Args:
        argv: Optional command line arguments (for testing)
    """
    parser = argparse.ArgumentParser(
        description="Scraper Supervisor - Monitor and manage scraping jobs",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # run - start supervisor daemon
    run_parser = subparsers.add_parser("run", help="Run supervisor daemon")
    run_parser.add_argument(
        "--check-interval", type=int, default=30,
        help="Seconds between health checks (default: 30)",
    )

    # check - single health check pass
    subparsers.add_parser("check", help="Run a single health check")

    # status - show job status
    subparsers.add_parser("status", help="Show status of all jobs")

    # start - start a new job
    start_parser = subparsers.add_parser("start", help="Start a new scraper job")
    start_parser.add_argument("scraper_type", choices=list(SCRAPER_REGISTRY.keys()))
    start_parser.add_argument("--limit", type=int, help="Max entities to scrape")
    start_parser.add_argument("--section", type=str, choices=["css", "html", "webapi"], help="Section filter for mdn_webapis")
    start_parser.add_argument("--dry-run", action="store_true", help="Don't insert into DB")
    start_parser.add_argument("--foreground", "-f", action="store_true", help="Run in foreground")

    # resume - resume a failed job
    resume_parser = subparsers.add_parser("resume", help="Resume a failed job")
    resume_parser.add_argument("job_id_or_type", help="Job ID or scraper type to resume")
    resume_parser.add_argument("--foreground", "-f", action="store_true", help="Run in foreground")

    # install-task - install Windows scheduled task
    install_parser = subparsers.add_parser("install-task", help="Install Windows scheduled task")
    install_parser.add_argument(
        "--interval", type=int, default=5,
        help="Minutes between checks (default: 5)",
    )

    # uninstall-task
    subparsers.add_parser("uninstall-task", help="Remove Windows scheduled task")

    args = parser.parse_args(argv)
    supervisor = ScraperSupervisor()

    if args.command == "run":
        supervisor.run_daemon()

    elif args.command == "check":
        supervisor.run_once()
        print("Health check completed")

    elif args.command == "status":
        status = supervisor.get_status()
        print(f"\n=== Scraper Jobs Status ===")
        print(f"Total: {status['summary']['total']}")
        print(f"  Running: {status['summary']['running']}")
        print(f"  Completed: {status['summary']['completed']}")
        print(f"  Failed: {status['summary']['failed']}")
        print(f"  Pending: {status['summary']['pending']}")

        if status["jobs"]:
            print("\n--- Jobs ---")
            for job in status["jobs"]:
                checkpoint = supervisor.checkpoint_manager.load(job["job_id"])
                progress = ""
                if checkpoint:
                    progress = f" (processed: {checkpoint.entities_processed}, inserted: {checkpoint.entities_inserted})"
                print(f"  [{job['status']}] {job['job_id']}: {job['scraper_type']}{progress}")
                if job.get("error_message"):
                    print(f"           Error: {job['error_message']}")

    elif args.command == "start":
        config = {
            "max_entities": args.limit,
            "dry_run": args.dry_run,
        }
        # Add section filter for mdn_webapis
        if hasattr(args, 'section') and args.section:
            config["section_filter"] = args.section
        job = supervisor.start_job(args.scraper_type, config)
        print(f"Created job: {job.job_id}")

        if args.foreground:
            print("Running in foreground...")
            result = supervisor.run_job(job, resume=False)
            print(f"Result: {result}")
        else:
            print("Job is pending. Run 'check' or 'run' to start it.")

    elif args.command == "resume":
        # Check if it's a job ID or scraper type
        job = supervisor.registry.get(args.job_id_or_type)
        if not job:
            job = supervisor.registry.get_by_type(args.job_id_or_type)

        if not job:
            print(f"No job found for: {args.job_id_or_type}")
            return

        print(f"Resuming job: {job.job_id}")

        if args.foreground:
            result = supervisor.resume_job(job.job_id)
            print(f"Result: {result}")
        else:
            # Mark as pending so daemon picks it up
            job.status = JobStatus.PENDING
            supervisor.registry.save(job)
            print("Job marked for resume. Run 'check' or 'run' to restart it.")

    elif args.command == "install-task":
        install_windows_task(args.interval)

    elif args.command == "uninstall-task":
        uninstall_windows_task()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
