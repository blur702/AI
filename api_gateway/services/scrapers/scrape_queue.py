"""
Scrape Request Queue with Throttling.

Implements a priority-based request queue for managing scrape operations
with global throttling to prevent overwhelming services.

Features:
- Priority-based processing (user requests > cache warming)
- Global throttle: maximum scrapes per minute across all services
- Queue depth tracking and metrics
- Async result waiting with timeouts

Usage:
    queue = get_scrape_queue()
    request_id = await queue.enqueue_scrape("instacart", "milk", "20024", priority=1)
    result = await queue.wait_for_result(request_id, timeout=60)
"""

import asyncio
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from api_gateway.config import settings
from api_gateway.utils.logger import get_logger

logger = get_logger("api_gateway.services.scrapers.scrape_queue")


class ScrapePriority(IntEnum):
    """Priority levels for scrape requests."""

    LOW = 0  # Cache warming, background tasks
    NORMAL = 1  # Standard API requests
    HIGH = 2  # User-initiated real-time requests


@dataclass(order=True)
class ScrapeRequest:
    """A scrape request in the queue."""

    priority: int
    timestamp: float = field(compare=False)
    request_id: str = field(compare=False)
    service_name: str = field(compare=False)
    query: str = field(compare=False)
    location: str = field(compare=False)
    result_future: asyncio.Future = field(compare=False, repr=False)

    def __post_init__(self):
        """Invert priority for max-heap behavior (higher priority first)."""
        self.priority = -self.priority


@dataclass
class QueueMetrics:
    """Metrics for the scrape queue."""

    total_enqueued: int = 0
    total_processed: int = 0
    total_failed: int = 0
    total_throttled: int = 0
    current_queue_depth: int = 0
    avg_wait_time_seconds: float = 0.0
    requests_last_minute: int = 0
    last_process_time: float = 0.0

    def to_dict(self) -> dict:
        """Convert metrics to dictionary."""
        return {
            "total_enqueued": self.total_enqueued,
            "total_processed": self.total_processed,
            "total_failed": self.total_failed,
            "total_throttled": self.total_throttled,
            "current_queue_depth": self.current_queue_depth,
            "avg_wait_time_seconds": round(self.avg_wait_time_seconds, 3),
            "requests_last_minute": self.requests_last_minute,
            "processing_rate_per_minute": (
                self.total_processed / max(1, (time.time() - self.last_process_time) / 60)
                if self.last_process_time > 0
                else 0
            ),
        }


class ScrapeQueue:
    """
    Priority-based scrape request queue with global throttling.

    Implements:
    - Priority queue using asyncio.PriorityQueue
    - Global throttling (max requests per minute)
    - Queue depth limits
    - Async result waiting
    - Comprehensive metrics
    """

    _instance: "ScrapeQueue | None" = None
    _lock: asyncio.Lock | None = None

    def __new__(cls) -> "ScrapeQueue":
        """Singleton pattern for global queue instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize the scrape queue."""
        if self._initialized:
            return

        # Configuration from settings
        price_settings = settings.PRICE_COMPARISON_SETTINGS
        self._enabled = price_settings.get("scrape_queue_enabled", True)
        self._max_per_minute = price_settings.get("scrape_queue_max_per_minute", 10)
        self._max_queue_size = price_settings.get("scrape_queue_max_size", 100)

        # Priority queue for requests
        self._queue: asyncio.PriorityQueue[ScrapeRequest] = asyncio.PriorityQueue(
            maxsize=self._max_queue_size
        )

        # Pending results tracking
        self._pending_results: dict[str, asyncio.Future] = {}

        # Throttling state
        self._request_timestamps: list[float] = []
        self._throttle_lock = asyncio.Lock()

        # Metrics
        self._metrics = QueueMetrics()
        self._wait_times: list[float] = []  # Sliding window for avg calculation

        # Background processor task
        self._processor_task: asyncio.Task | None = None
        self._scrape_handler: Callable[
            [str, str, str], Coroutine[Any, Any, list]
        ] | None = None

        self._initialized = True
        logger.info(
            "Scrape queue initialized: enabled=%s, max_per_minute=%d, max_size=%d",
            self._enabled,
            self._max_per_minute,
            self._max_queue_size,
        )

    def set_scrape_handler(
        self,
        handler: Callable[[str, str, str], Coroutine[Any, Any, list]],
    ) -> None:
        """
        Set the scrape handler function.

        Args:
            handler: Async function that takes (service_name, query, location)
                    and returns list of products
        """
        self._scrape_handler = handler
        logger.debug("Scrape handler set")

    async def start_processor(self) -> None:
        """Start the background queue processor."""
        if not self._enabled:
            logger.info("Scrape queue disabled, processor not started")
            return

        if self._processor_task is not None and not self._processor_task.done():
            logger.warning("Processor already running")
            return

        self._processor_task = asyncio.create_task(self._process_queue())
        logger.info("Queue processor started")

    async def stop_processor(self) -> None:
        """Stop the background queue processor."""
        if self._processor_task is not None:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
            self._processor_task = None
            logger.info("Queue processor stopped")

    async def enqueue_scrape(
        self,
        service_name: str,
        query: str,
        location: str,
        priority: int = ScrapePriority.NORMAL,
    ) -> str:
        """
        Enqueue a scrape request.

        Args:
            service_name: Service to scrape
            query: Search query
            location: Zip code
            priority: Request priority (higher = processed first)

        Returns:
            Request ID for tracking

        Raises:
            asyncio.QueueFull: If queue is at max capacity
        """
        if not self._enabled:
            raise RuntimeError("Scrape queue is disabled")

        request_id = str(uuid.uuid4())
        result_future: asyncio.Future = asyncio.get_event_loop().create_future()

        request = ScrapeRequest(
            priority=priority,
            timestamp=time.time(),
            request_id=request_id,
            service_name=service_name,
            query=query,
            location=location,
            result_future=result_future,
        )

        try:
            self._queue.put_nowait(request)
            self._pending_results[request_id] = result_future
            self._metrics.total_enqueued += 1
            self._metrics.current_queue_depth = self._queue.qsize()

            logger.debug(
                "Enqueued scrape request %s: %s/%s (priority=%d, depth=%d)",
                request_id,
                service_name,
                query,
                priority,
                self._queue.qsize(),
            )

            return request_id

        except asyncio.QueueFull:
            logger.warning(
                "Queue full, rejecting request for %s/%s",
                service_name,
                query,
            )
            raise

    async def wait_for_result(
        self,
        request_id: str,
        timeout: float = 120.0,
    ) -> list:
        """
        Wait for a scrape result.

        Args:
            request_id: Request ID from enqueue_scrape
            timeout: Maximum wait time in seconds

        Returns:
            List of products from scrape

        Raises:
            asyncio.TimeoutError: If timeout exceeded
            KeyError: If request_id not found
        """
        if request_id not in self._pending_results:
            raise KeyError(f"Unknown request ID: {request_id}")

        future = self._pending_results[request_id]

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        finally:
            # Clean up
            self._pending_results.pop(request_id, None)

    async def _check_throttle(self) -> bool:
        """
        Check if we're within throttle limits.

        Returns:
            True if request can proceed, False if throttled
        """
        async with self._throttle_lock:
            now = time.time()
            one_minute_ago = now - 60.0

            # Remove timestamps older than 1 minute
            self._request_timestamps = [
                ts for ts in self._request_timestamps if ts > one_minute_ago
            ]

            self._metrics.requests_last_minute = len(self._request_timestamps)

            if len(self._request_timestamps) >= self._max_per_minute:
                self._metrics.total_throttled += 1
                return False

            self._request_timestamps.append(now)
            return True

    async def _process_queue(self) -> None:
        """Background task to process the queue."""
        logger.info("Queue processor starting")

        while True:
            try:
                # Get next request from queue
                request = await self._queue.get()
                self._metrics.current_queue_depth = self._queue.qsize()

                # Calculate wait time
                wait_time = time.time() - request.timestamp
                self._wait_times.append(wait_time)
                if len(self._wait_times) > 100:
                    self._wait_times = self._wait_times[-100:]
                self._metrics.avg_wait_time_seconds = (
                    sum(self._wait_times) / len(self._wait_times)
                )

                # Check throttle
                while not await self._check_throttle():
                    logger.debug(
                        "Throttled, waiting before processing %s",
                        request.request_id,
                    )
                    await asyncio.sleep(1.0)

                # Process the request
                try:
                    if self._scrape_handler is None:
                        raise RuntimeError("No scrape handler configured")

                    logger.debug(
                        "Processing request %s: %s/%s",
                        request.request_id,
                        request.service_name,
                        request.query,
                    )

                    result = await self._scrape_handler(
                        request.service_name,
                        request.query,
                        request.location,
                    )

                    # Set result on future
                    if not request.result_future.done():
                        request.result_future.set_result(result)

                    self._metrics.total_processed += 1
                    self._metrics.last_process_time = time.time()

                    logger.debug(
                        "Completed request %s with %d products",
                        request.request_id,
                        len(result) if result else 0,
                    )

                except Exception as e:
                    logger.error(
                        "Failed to process request %s: %s",
                        request.request_id,
                        e,
                    )
                    self._metrics.total_failed += 1

                    # Set exception on future
                    if not request.result_future.done():
                        request.result_future.set_exception(e)

                finally:
                    self._queue.task_done()

            except asyncio.CancelledError:
                logger.info("Queue processor cancelled")
                break
            except Exception as e:
                logger.error("Queue processor error: %s", e)
                await asyncio.sleep(1.0)

    async def direct_scrape(
        self,
        service_name: str,
        query: str,
        location: str,
    ) -> list:
        """
        Perform a direct scrape without queuing.

        Used when queue is disabled or for fallback.

        Args:
            service_name: Service to scrape
            query: Search query
            location: Zip code

        Returns:
            List of products
        """
        if self._scrape_handler is None:
            raise RuntimeError("No scrape handler configured")

        return await self._scrape_handler(service_name, query, location)

    def is_enabled(self) -> bool:
        """Check if queue is enabled."""
        return self._enabled

    def get_metrics(self) -> dict:
        """Get queue metrics."""
        return self._metrics.to_dict()

    def get_queue_depth(self) -> int:
        """Get current queue depth."""
        return self._queue.qsize()

    async def clear_queue(self) -> int:
        """
        Clear all pending requests from the queue.

        Returns:
            Number of requests cleared
        """
        cleared = 0
        while not self._queue.empty():
            try:
                request = self._queue.get_nowait()
                if not request.result_future.done():
                    request.result_future.cancel()
                self._queue.task_done()
                cleared += 1
            except asyncio.QueueEmpty:
                break

        self._metrics.current_queue_depth = 0
        logger.info("Cleared %d requests from queue", cleared)
        return cleared


# Global queue instance
_scrape_queue: ScrapeQueue | None = None


def get_scrape_queue() -> ScrapeQueue:
    """Get the global scrape queue instance."""
    global _scrape_queue
    if _scrape_queue is None:
        _scrape_queue = ScrapeQueue()
    return _scrape_queue


async def init_scrape_queue(
    handler: Callable[[str, str, str], Coroutine[Any, Any, list]],
) -> ScrapeQueue:
    """
    Initialize the scrape queue with a handler and start the processor.

    Args:
        handler: Async function that performs the actual scrape

    Returns:
        Initialized ScrapeQueue instance
    """
    queue = get_scrape_queue()
    queue.set_scrape_handler(handler)
    await queue.start_processor()
    return queue


async def shutdown_scrape_queue() -> None:
    """Shutdown the scrape queue and processor."""
    global _scrape_queue
    if _scrape_queue is not None:
        await _scrape_queue.stop_processor()
        await _scrape_queue.clear_queue()
        _scrape_queue = None
        logger.info("Scrape queue shutdown complete")
