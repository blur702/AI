"""
Congressional scraper worker process.

Standalone worker that scrapes an assigned subset of House members.
Writes heartbeat files and checkpoints for supervisor monitoring.

Usage:
    python -m api_gateway.services.congressional_worker \
        --worker-id 0 \
        --start-index 0 \
        --end-index 22
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


from ..utils.embeddings import get_embedding
from ..utils.logger import get_logger
from .congressional_schema import (
    create_congressional_data_collection,
)
from .congressional_scraper import (
    CongressionalDocScraper,
    MemberInfo,
    ScrapeConfig,
)
from .topic_classifier import classify_text
from .weaviate_connection import (
    CONGRESSIONAL_DATA_COLLECTION_NAME,
    WeaviateConnection,
)

logger = get_logger("api_gateway.congressional_worker")

HOUSE_FEED_URL = "https://housegovfeeds.house.gov/feeds/Member/Json"
DEFAULT_CONFIG_PATH = Path("D:/AI/data/scraper/congressional/congressional_parallel_config.json")


@dataclass
class WorkerConfig:
    """Configuration for a single worker."""

    worker_id: int
    start_index: int
    end_index: int
    heartbeat_dir: Path
    checkpoint_dir: Path
    log_dir: Path
    request_delay: float = 2.0
    batch_size: int = 10
    batch_delay: float = 5.0
    max_pages_per_member: int = 5
    checkpoint_interval: int = 5


@dataclass
class WorkerCheckpoint:
    """Checkpoint for resuming worker from crash."""

    worker_id: int
    members_completed: List[str] = field(default_factory=list)
    current_member_index: int = 0
    pages_scraped: int = 0
    pages_inserted: int = 0
    pages_updated: int = 0
    errors: int = 0
    last_member_name: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkerCheckpoint":
        return cls(**data)


@dataclass
class Heartbeat:
    """Heartbeat data written periodically."""

    worker_id: int
    pid: int
    started_at: str
    last_heartbeat: str
    current_member: str = ""
    members_processed: int = 0
    members_total: int = 0
    pages_scraped: int = 0
    status: str = "starting"  # starting, running, completed, failed
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CongressionalWorker:
    """Worker process that scrapes assigned members."""

    def __init__(self, config: WorkerConfig):
        self.config = config
        self.checkpoint: Optional[WorkerCheckpoint] = None
        self.heartbeat: Optional[Heartbeat] = None
        self._stop_flag = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._members: List[Dict[str, Any]] = []

    def _load_checkpoint(self) -> Optional[WorkerCheckpoint]:
        """Load checkpoint from disk if exists."""
        checkpoint_path = self.config.checkpoint_dir / f"worker_{self.config.worker_id}_checkpoint.json"
        if checkpoint_path.exists():
            try:
                data = json.loads(checkpoint_path.read_text())
                checkpoint = WorkerCheckpoint.from_dict(data)
                logger.info(
                    "Loaded checkpoint for worker %d: %d members completed",
                    self.config.worker_id,
                    len(checkpoint.members_completed),
                )
                return checkpoint
            except Exception as e:
                logger.warning("Failed to load checkpoint: %s", e)
        return None

    def _save_checkpoint(self) -> None:
        """Save current checkpoint to disk."""
        if not self.checkpoint:
            return
        self.checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
        checkpoint_path = self.config.checkpoint_dir / f"worker_{self.config.worker_id}_checkpoint.json"
        checkpoint_path.write_text(json.dumps(self.checkpoint.to_dict(), indent=2))

    def _delete_checkpoint(self) -> None:
        """Delete checkpoint on successful completion."""
        checkpoint_path = self.config.checkpoint_dir / f"worker_{self.config.worker_id}_checkpoint.json"
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            logger.info("Deleted checkpoint for worker %d", self.config.worker_id)

    def _write_heartbeat(self) -> None:
        """Write heartbeat to disk."""
        if not self.heartbeat:
            return
        self.heartbeat.last_heartbeat = datetime.now(timezone.utc).isoformat()
        heartbeat_path = self.config.heartbeat_dir / f"worker_{self.config.worker_id}.json"
        heartbeat_path.write_text(json.dumps(self.heartbeat.to_dict(), indent=2))

    def _delete_heartbeat(self) -> None:
        """Delete heartbeat file on shutdown."""
        heartbeat_path = self.config.heartbeat_dir / f"worker_{self.config.worker_id}.json"
        if heartbeat_path.exists():
            heartbeat_path.unlink()

    def _heartbeat_loop(self) -> None:
        """Background thread that writes heartbeat every 30 seconds."""
        while not self._stop_flag.is_set():
            try:
                self._write_heartbeat()
            except Exception as e:
                logger.warning("Heartbeat write failed: %s", e)
            self._stop_flag.wait(30)

    def _start_heartbeat_thread(self) -> None:
        """Start the heartbeat background thread."""
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name=f"heartbeat-worker-{self.config.worker_id}",
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat_thread(self) -> None:
        """Stop the heartbeat thread."""
        self._stop_flag.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5)

    def _fetch_members(self) -> List[MemberInfo]:
        """Fetch member list using the scraper's method."""
        logger.info("Fetching member list...")
        scrape_config = ScrapeConfig(
            request_delay=self.config.request_delay,
            batch_size=self.config.batch_size,
        )
        with CongressionalDocScraper(scrape_config) as scraper:
            members = scraper.fetch_member_feed()
        # Sort by name for deterministic ordering
        members.sort(key=lambda m: m.name)
        logger.info("Fetched %d total members", len(members))
        return members

    def _get_assigned_members(self) -> List[MemberInfo]:
        """Get this worker's assigned subset of members."""
        if not self._members:
            self._members = self._fetch_members()

        assigned = self._members[self.config.start_index:self.config.end_index]
        logger.info(
            "Worker %d assigned members %d-%d (%d members)",
            self.config.worker_id,
            self.config.start_index,
            self.config.end_index,
            len(assigned),
        )
        return assigned

    def run(self) -> int:
        """
        Run the worker. Returns exit code.

        0 = success
        1 = error
        """
        # Initialize heartbeat
        self.heartbeat = Heartbeat(
            worker_id=self.config.worker_id,
            pid=os.getpid(),
            started_at=datetime.now(timezone.utc).isoformat(),
            last_heartbeat=datetime.now(timezone.utc).isoformat(),
            status="starting",
        )
        self._write_heartbeat()

        # Start heartbeat thread
        self._start_heartbeat_thread()

        # Load checkpoint or create new
        self.checkpoint = self._load_checkpoint() or WorkerCheckpoint(
            worker_id=self.config.worker_id,
        )

        try:
            # Get assigned members
            assigned_members = self._get_assigned_members()
            self.heartbeat.members_total = len(assigned_members)
            self.heartbeat.status = "running"

            # Create scraper config
            scrape_config = ScrapeConfig(
                request_delay=self.config.request_delay,
                batch_size=self.config.batch_size,
                batch_delay=self.config.batch_delay,
                max_pages_per_member=self.config.max_pages_per_member,
                max_members=len(assigned_members),
            )

            # Connect to Weaviate
            with WeaviateConnection() as client:
                create_congressional_data_collection(client)
                collection = client.collections.get(CONGRESSIONAL_DATA_COLLECTION_NAME)

                # Process each assigned member
                members_processed = 0
                for idx, member in enumerate(assigned_members):
                    if self._stop_flag.is_set():
                        logger.info("Worker %d received stop signal", self.config.worker_id)
                        break

                    member_name = member.name

                    # Skip if already completed (checkpoint resume)
                    if member_name in self.checkpoint.members_completed:
                        logger.debug("Skipping already completed member: %s", member_name)
                        continue

                    # Update heartbeat
                    self.heartbeat.current_member = member_name
                    self.heartbeat.members_processed = members_processed

                    logger.info(
                        "Worker %d processing member %d/%d: %s",
                        self.config.worker_id,
                        idx + 1,
                        len(assigned_members),
                        member_name,
                    )

                    try:
                        # Scrape this member using existing scraper
                        pages_scraped, pages_inserted, pages_updated, errors = self._scrape_member(
                            member, scrape_config, collection
                        )

                        # Update checkpoint
                        self.checkpoint.members_completed.append(member_name)
                        self.checkpoint.current_member_index = idx + 1
                        self.checkpoint.pages_scraped += pages_scraped
                        self.checkpoint.pages_inserted += pages_inserted
                        self.checkpoint.pages_updated += pages_updated
                        self.checkpoint.errors += errors
                        self.checkpoint.last_member_name = member_name

                        # Update heartbeat stats
                        self.heartbeat.pages_scraped = self.checkpoint.pages_scraped

                        members_processed += 1

                        # Save checkpoint periodically
                        if members_processed % self.config.checkpoint_interval == 0:
                            self._save_checkpoint()
                            logger.info(
                                "Worker %d checkpoint saved: %d/%d members",
                                self.config.worker_id,
                                members_processed,
                                len(assigned_members),
                            )

                    except Exception as e:
                        logger.exception("Error processing member %s: %s", member_name, e)
                        self.checkpoint.errors += 1

                # Final checkpoint save
                self._save_checkpoint()

            # Success
            self.heartbeat.status = "completed"
            self.heartbeat.members_processed = members_processed
            self._write_heartbeat()

            # Delete checkpoint on success
            self._delete_checkpoint()

            logger.info(
                "Worker %d completed: %d members, %d pages scraped, %d inserted, %d errors",
                self.config.worker_id,
                members_processed,
                self.checkpoint.pages_scraped,
                self.checkpoint.pages_inserted,
                self.checkpoint.errors,
            )
            return 0

        except Exception as e:
            logger.exception("Worker %d failed: %s", self.config.worker_id, e)
            self.heartbeat.status = "failed"
            self.heartbeat.error = str(e)
            self._write_heartbeat()
            self._save_checkpoint()
            return 1

        finally:
            self._stop_heartbeat_thread()

    def _scrape_member(
        self,
        member: MemberInfo,
        scrape_config: ScrapeConfig,
        collection,
    ) -> tuple[int, int, int, int]:
        """
        Scrape a single member's website.

        Returns: (pages_scraped, pages_inserted, pages_updated, errors)
        """
        pages_scraped = 0
        pages_inserted = 0
        pages_updated = 0
        errors = 0

        if not member.website_url:
            logger.warning("No website URL for member: %s", member.name)
            return pages_scraped, pages_inserted, pages_updated, errors

        # Create scraper instance and scrape this member
        with CongressionalDocScraper(scrape_config) as scraper:
            try:
                # Scrape member pages using the new single-member method
                for data in scraper.scrape_single_member(member):
                    pages_scraped += 1

                    try:
                        # Classify topics
                        try:
                            classification = classify_text(data.title, data.content_text)
                            data.policy_topics = classification.topics
                        except Exception as clf_exc:
                            logger.warning("Classification failed: %s", clf_exc)
                            data.policy_topics = []

                        # Get embedding
                        vector = get_embedding(data.content_text)

                        # Check if exists
                        try:
                            existing = collection.query.fetch_object_by_id(data.uuid)
                        except Exception:
                            existing = None

                        if existing and getattr(existing, "properties", None):
                            props = existing.properties or {}
                            if props.get("content_hash") == data.content_hash:
                                continue  # Unchanged

                            collection.data.update(
                                uuid=data.uuid,
                                properties=data.to_properties(),
                                vector=vector,
                            )
                            pages_updated += 1
                        else:
                            collection.data.insert(
                                uuid=data.uuid,
                                properties=data.to_properties(),
                                vector=vector,
                            )
                            pages_inserted += 1

                    except Exception as e:
                        logger.warning("Failed to upsert page: %s", e)
                        errors += 1

            except Exception as e:
                logger.warning("Failed to scrape member %s: %s", member.name, e)
                errors += 1

        return pages_scraped, pages_inserted, pages_updated, errors

    def stop(self) -> None:
        """Signal the worker to stop gracefully."""
        self._stop_flag.set()


def _signal_handler(worker: CongressionalWorker):
    """Create a signal handler for graceful shutdown."""
    def handler(signum, frame):
        logger.info("Received signal %d, stopping worker", signum)
        worker.stop()
    return handler


def load_config_from_file(config_path: Path) -> Dict[str, Any]:
    """Load configuration from JSON file."""
    if config_path.exists():
        return json.loads(config_path.read_text())
    return {}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Congressional scraper worker")
    parser.add_argument("--worker-id", type=int, required=True, help="Worker ID (0-19)")
    parser.add_argument("--start-index", type=int, required=True, help="Start index in member list")
    parser.add_argument("--end-index", type=int, required=True, help="End index in member list")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Config file path")
    parser.add_argument("--request-delay", type=float, help="Request delay override")
    parser.add_argument("--max-pages", type=int, help="Max pages per member override")

    args = parser.parse_args()

    # Load config from file
    file_config = load_config_from_file(args.config)
    paths_config = file_config.get("paths", {})
    worker_config = file_config.get("worker", {})

    # Build worker config
    config = WorkerConfig(
        worker_id=args.worker_id,
        start_index=args.start_index,
        end_index=args.end_index,
        heartbeat_dir=Path(paths_config.get("heartbeat_dir", "D:/AI/data/scraper/congressional/heartbeats")),
        checkpoint_dir=Path(paths_config.get("checkpoint_dir", "D:/AI/data/scraper/congressional/checkpoints")),
        log_dir=Path(paths_config.get("log_dir", "D:/AI/logs/congressional_scraper")),
        request_delay=args.request_delay or worker_config.get("request_delay", 2.0),
        batch_size=worker_config.get("batch_size", 10),
        batch_delay=worker_config.get("batch_delay", 5.0),
        max_pages_per_member=args.max_pages or worker_config.get("max_pages_per_member", 5),
        checkpoint_interval=worker_config.get("checkpoint_interval", 5),
    )

    # Create worker
    worker = CongressionalWorker(config)

    # Set up signal handlers
    signal.signal(signal.SIGINT, _signal_handler(worker))
    signal.signal(signal.SIGTERM, _signal_handler(worker))

    # Run
    logger.info("Starting worker %d (members %d-%d)", config.worker_id, config.start_index, config.end_index)
    exit_code = worker.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
