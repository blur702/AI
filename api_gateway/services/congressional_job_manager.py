import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

from ..utils.logger import get_logger
from .congressional_scraper import (
    ScrapeConfig,
    scrape_congressional_data,
)

logger = get_logger("api_gateway.congressional_job_manager")


@dataclass
class _JobState:
    status: str = "idle"  # idle/pending/running/completed/failed/cancelled
    stats: dict[str, Any] = field(
        default_factory=lambda: {
            "members_processed": 0,
            "pages_scraped": 0,
            "pages_updated": 0,
            "pages_inserted": 0,
            "errors": 0,
            "cancelled": False,
        }
    )
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    cancel_flag: bool = False
    pause_flag: bool = False
    thread: threading.Thread | None = None


class CongressionalJobManager:
    """Singleton manager for congressional scraping jobs."""

    _instance: Optional["CongressionalJobManager"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._state = _JobState()
        self._state_lock = threading.Lock()

    @classmethod
    def instance(cls) -> "CongressionalJobManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _progress_callback(
        self,
        phase: str,
        current: int,
        total: int,
        message: str,
    ) -> None:
        with self._state_lock:
            self._state.stats["last_phase"] = phase
            self._state.stats["last_message"] = message
            self._state.stats["current"] = current
            self._state.stats["total"] = total

    def _check_cancelled(self) -> bool:
        with self._state_lock:
            return self._state.cancel_flag

    def _check_paused(self) -> bool:
        with self._state_lock:
            return self._state.pause_flag

    def _run_scrape(self, config: ScrapeConfig) -> None:
        with self._state_lock:
            self._state.status = "running"
            self._state.started_at = datetime.now(UTC)
            self._state.completed_at = None
            self._state.error = None
            self._state.stats = {
                "members_processed": 0,
                "pages_scraped": 0,
                "pages_updated": 0,
                "pages_inserted": 0,
                "errors": 0,
                "cancelled": False,
            }

        try:
            stats = scrape_congressional_data(
                config=config,
                progress_callback=self._progress_callback,
                check_cancelled=self._check_cancelled,
                check_paused=self._check_paused,
            )
            with self._state_lock:
                self._state.stats.update(stats)
                if stats.get("cancelled"):
                    self._state.status = "cancelled"
                else:
                    self._state.status = "completed"
                self._state.completed_at = datetime.now(UTC)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Congressional scrape failed: %s", exc)
            with self._state_lock:
                self._state.status = "failed"
                self._state.error = str(exc)
                self._state.completed_at = datetime.now(UTC)

    def start_scrape(self, config: ScrapeConfig) -> _JobState:
        with self._state_lock:
            if self._state.status in {"running", "pending"}:
                raise RuntimeError("Scrape already running")

            self._state.status = "pending"
            self._state.cancel_flag = False
            self._state.pause_flag = False
            self._state.error = None
            self._state.started_at = datetime.now(UTC)
            self._state.completed_at = None

            thread = threading.Thread(
                target=self._run_scrape,
                args=(config,),
                name="CongressionalScrapeThread",
                daemon=True,
            )
            self._state.thread = thread
            thread.start()

        return self.get_status()

    def get_status(self) -> _JobState:
        with self._state_lock:
            # Return a shallow copy to avoid external mutation
            # Don't expose internal thread reference
            return _JobState(
                status=self._state.status,
                stats=dict(self._state.stats),
                started_at=self._state.started_at,
                completed_at=self._state.completed_at,
                error=self._state.error,
                cancel_flag=self._state.cancel_flag,
                pause_flag=self._state.pause_flag,
                thread=None,
            )

    def cancel_scrape(self) -> None:
        with self._state_lock:
            self._state.cancel_flag = True

    def pause_scrape(self) -> None:
        with self._state_lock:
            self._state.pause_flag = True

    def resume_scrape(self) -> None:
        with self._state_lock:
            self._state.pause_flag = False
