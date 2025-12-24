"""
Scraper Performance Metrics Module.

Provides comprehensive performance tracking for scrapers including:
- Scrape duration tracking
- Success/failure rates
- Cache hit statistics
- Browser pool usage metrics

Usage:
    from api_gateway.services.scrapers.metrics import get_scraper_metrics

    metrics = get_scraper_metrics()
    metrics.record_scrape_start("instacart")
    # ... perform scrape ...
    metrics.record_scrape_end("instacart", success=True)
"""

import time
from collections import deque
from dataclasses import dataclass
from threading import Lock

from api_gateway.config import settings
from api_gateway.utils.logger import get_logger

logger = get_logger("api_gateway.services.scrapers.metrics")


@dataclass
class ScrapeRecord:
    """Record of a single scrape operation."""

    service_name: str
    timestamp: float
    duration_seconds: float
    success: bool
    cache_hit: bool = False
    cache_layer: str | None = None
    browser_pool_hit: bool = False
    products_found: int = 0
    error_type: str | None = None


@dataclass
class ServiceMetrics:
    """Aggregated metrics for a single service."""

    total_scrapes: int = 0
    successful_scrapes: int = 0
    failed_scrapes: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_hits_redis: int = 0
    cache_hits_postgres: int = 0
    cache_hits_memory: int = 0
    browser_pool_hits: int = 0
    browser_pool_misses: int = 0
    total_duration_seconds: float = 0.0
    min_duration_seconds: float = float("inf")
    max_duration_seconds: float = 0.0
    total_products_found: int = 0

    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_scrapes == 0:
            return 0.0
        return round((self.successful_scrapes / self.total_scrapes) * 100, 1)

    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate as percentage."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return round((self.cache_hits / total) * 100, 1)

    def browser_pool_hit_rate(self) -> float:
        """Calculate browser pool hit rate as percentage."""
        total = self.browser_pool_hits + self.browser_pool_misses
        if total == 0:
            return 0.0
        return round((self.browser_pool_hits / total) * 100, 1)

    def avg_duration_seconds(self) -> float:
        """Calculate average scrape duration."""
        if self.total_scrapes == 0:
            return 0.0
        return round(self.total_duration_seconds / self.total_scrapes, 2)

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "total_scrapes": self.total_scrapes,
            "successful_scrapes": self.successful_scrapes,
            "failed_scrapes": self.failed_scrapes,
            "success_rate": self.success_rate(),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": self.cache_hit_rate(),
            "cache_breakdown": {
                "redis": self.cache_hits_redis,
                "postgres": self.cache_hits_postgres,
                "memory": self.cache_hits_memory,
            },
            "browser_pool_hits": self.browser_pool_hits,
            "browser_pool_misses": self.browser_pool_misses,
            "browser_pool_hit_rate": self.browser_pool_hit_rate(),
            "duration": {
                "avg_seconds": self.avg_duration_seconds(),
                "min_seconds": self.min_duration_seconds if self.min_duration_seconds != float("inf") else 0,
                "max_seconds": self.max_duration_seconds,
                "total_seconds": round(self.total_duration_seconds, 2),
            },
            "total_products_found": self.total_products_found,
        }


class ScraperMetrics:
    """
    Comprehensive metrics tracking for scraper performance.

    Tracks per-service metrics with a sliding window of recent records
    for detailed analysis. Thread-safe for concurrent access.
    """

    _instance: "ScraperMetrics | None" = None
    _lock: Lock = Lock()

    def __new__(cls) -> "ScraperMetrics":
        """Singleton pattern for global metrics instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize metrics tracking."""
        if self._initialized:
            return

        # Configuration
        price_settings = settings.PRICE_COMPARISON_SETTINGS
        self._window_size = price_settings.get("metrics_sliding_window_size", 1000)
        self._persistence_enabled = price_settings.get("metrics_persistence_enabled", False)

        # Per-service aggregated metrics
        self._service_metrics: dict[str, ServiceMetrics] = {}

        # Sliding window of recent records per service
        self._recent_records: dict[str, deque[ScrapeRecord]] = {}

        # Active scrapes (for timing)
        self._active_scrapes: dict[str, dict] = {}

        # Thread safety
        self._metrics_lock = Lock()

        self._initialized = True
        logger.info("Scraper metrics initialized (window_size=%d)", self._window_size)

    def _ensure_service(self, service_name: str) -> None:
        """Ensure metrics structures exist for a service."""
        if service_name not in self._service_metrics:
            self._service_metrics[service_name] = ServiceMetrics()
        if service_name not in self._recent_records:
            self._recent_records[service_name] = deque(maxlen=self._window_size)

    def record_scrape_start(self, service_name: str, scrape_id: str | None = None) -> str:
        """
        Record the start of a scrape operation.

        Args:
            service_name: The service being scraped
            scrape_id: Optional unique ID for this scrape

        Returns:
            Scrape ID for use with record_scrape_end
        """
        if scrape_id is None:
            scrape_id = f"{service_name}_{time.time()}"

        with self._metrics_lock:
            self._active_scrapes[scrape_id] = {
                "service_name": service_name,
                "start_time": time.time(),
            }

        return scrape_id

    def record_scrape_end(
        self,
        scrape_id: str,
        success: bool,
        products_found: int = 0,
        error_type: str | None = None,
        browser_pool_hit: bool = False,
    ) -> None:
        """
        Record the end of a scrape operation.

        Args:
            scrape_id: The ID returned from record_scrape_start
            success: Whether the scrape succeeded
            products_found: Number of products found
            error_type: Type of error if failed
            browser_pool_hit: Whether browser context was from pool
        """
        with self._metrics_lock:
            if scrape_id not in self._active_scrapes:
                logger.warning("Unknown scrape_id: %s", scrape_id)
                return

            scrape_info = self._active_scrapes.pop(scrape_id)
            service_name = scrape_info["service_name"]
            duration = time.time() - scrape_info["start_time"]

            self._ensure_service(service_name)
            metrics = self._service_metrics[service_name]

            # Update aggregated metrics
            metrics.total_scrapes += 1
            if success:
                metrics.successful_scrapes += 1
            else:
                metrics.failed_scrapes += 1

            metrics.total_duration_seconds += duration
            metrics.min_duration_seconds = min(metrics.min_duration_seconds, duration)
            metrics.max_duration_seconds = max(metrics.max_duration_seconds, duration)
            metrics.total_products_found += products_found

            if browser_pool_hit:
                metrics.browser_pool_hits += 1
            else:
                metrics.browser_pool_misses += 1

            # Add to recent records
            record = ScrapeRecord(
                service_name=service_name,
                timestamp=time.time(),
                duration_seconds=duration,
                success=success,
                browser_pool_hit=browser_pool_hit,
                products_found=products_found,
                error_type=error_type,
            )
            self._recent_records[service_name].append(record)

    def record_scrape_duration(
        self,
        service_name: str,
        duration_seconds: float,
        success: bool = True,
        products_found: int = 0,
        error_type: str | None = None,
    ) -> None:
        """
        Record a scrape duration directly (alternative to start/end pattern).

        Args:
            service_name: The service that was scraped
            duration_seconds: How long the scrape took
            success: Whether the scrape succeeded
            products_found: Number of products found
            error_type: Type of error if failed
        """
        with self._metrics_lock:
            self._ensure_service(service_name)
            metrics = self._service_metrics[service_name]

            metrics.total_scrapes += 1
            if success:
                metrics.successful_scrapes += 1
            else:
                metrics.failed_scrapes += 1

            metrics.total_duration_seconds += duration_seconds
            metrics.min_duration_seconds = min(metrics.min_duration_seconds, duration_seconds)
            metrics.max_duration_seconds = max(metrics.max_duration_seconds, duration_seconds)
            metrics.total_products_found += products_found

            record = ScrapeRecord(
                service_name=service_name,
                timestamp=time.time(),
                duration_seconds=duration_seconds,
                success=success,
                products_found=products_found,
                error_type=error_type,
            )
            self._recent_records[service_name].append(record)

    def record_cache_hit(self, service_name: str, cache_layer: str) -> None:
        """
        Record a cache hit.

        Args:
            service_name: The service for which cache was hit
            cache_layer: Which cache layer hit (redis, postgres, memory)
        """
        with self._metrics_lock:
            self._ensure_service(service_name)
            metrics = self._service_metrics[service_name]

            metrics.cache_hits += 1

            if cache_layer == "redis":
                metrics.cache_hits_redis += 1
            elif cache_layer == "postgres":
                metrics.cache_hits_postgres += 1
            elif cache_layer == "memory":
                metrics.cache_hits_memory += 1

    def record_cache_miss(self, service_name: str) -> None:
        """
        Record a cache miss.

        Args:
            service_name: The service for which cache was missed
        """
        with self._metrics_lock:
            self._ensure_service(service_name)
            self._service_metrics[service_name].cache_misses += 1

    def record_browser_pool_hit(self, service_name: str, hit: bool) -> None:
        """
        Record browser pool hit or miss.

        Args:
            service_name: The service using browser pool
            hit: True if context was from pool, False if newly created
        """
        with self._metrics_lock:
            self._ensure_service(service_name)
            metrics = self._service_metrics[service_name]

            if hit:
                metrics.browser_pool_hits += 1
            else:
                metrics.browser_pool_misses += 1

    def get_metrics_summary(self, service_name: str) -> dict:
        """
        Get aggregated metrics for a specific service.

        Args:
            service_name: The service to get metrics for

        Returns:
            Dictionary of aggregated metrics
        """
        with self._metrics_lock:
            if service_name not in self._service_metrics:
                return ServiceMetrics().to_dict()
            return self._service_metrics[service_name].to_dict()

    def get_all_metrics(self) -> dict:
        """
        Get metrics for all services.

        Returns:
            Dictionary with per-service metrics and global aggregates
        """
        with self._metrics_lock:
            result = {
                "services": {},
                "global": {
                    "total_scrapes": 0,
                    "successful_scrapes": 0,
                    "failed_scrapes": 0,
                    "total_cache_hits": 0,
                    "total_cache_misses": 0,
                    "total_products_found": 0,
                },
            }

            for service_name, metrics in self._service_metrics.items():
                result["services"][service_name] = metrics.to_dict()
                result["global"]["total_scrapes"] += metrics.total_scrapes
                result["global"]["successful_scrapes"] += metrics.successful_scrapes
                result["global"]["failed_scrapes"] += metrics.failed_scrapes
                result["global"]["total_cache_hits"] += metrics.cache_hits
                result["global"]["total_cache_misses"] += metrics.cache_misses
                result["global"]["total_products_found"] += metrics.total_products_found

            # Calculate global rates
            total = result["global"]["total_scrapes"]
            if total > 0:
                result["global"]["success_rate"] = round(
                    (result["global"]["successful_scrapes"] / total) * 100, 1
                )
            else:
                result["global"]["success_rate"] = 0.0

            cache_total = result["global"]["total_cache_hits"] + result["global"]["total_cache_misses"]
            if cache_total > 0:
                result["global"]["cache_hit_rate"] = round(
                    (result["global"]["total_cache_hits"] / cache_total) * 100, 1
                )
            else:
                result["global"]["cache_hit_rate"] = 0.0

            return result

    def get_recent_records(self, service_name: str, limit: int = 100) -> list[dict]:
        """
        Get recent scrape records for a service.

        Args:
            service_name: The service to get records for
            limit: Maximum number of records to return

        Returns:
            List of recent scrape records as dictionaries
        """
        with self._metrics_lock:
            if service_name not in self._recent_records:
                return []

            records = list(self._recent_records[service_name])[-limit:]
            return [
                {
                    "timestamp": r.timestamp,
                    "duration_seconds": round(r.duration_seconds, 3),
                    "success": r.success,
                    "cache_hit": r.cache_hit,
                    "cache_layer": r.cache_layer,
                    "browser_pool_hit": r.browser_pool_hit,
                    "products_found": r.products_found,
                    "error_type": r.error_type,
                }
                for r in records
            ]

    def reset_metrics(self, service_name: str | None = None) -> None:
        """
        Reset metrics for a service or all services.

        Args:
            service_name: Service to reset, or None for all services
        """
        with self._metrics_lock:
            if service_name:
                if service_name in self._service_metrics:
                    self._service_metrics[service_name] = ServiceMetrics()
                if service_name in self._recent_records:
                    self._recent_records[service_name].clear()
            else:
                self._service_metrics.clear()
                self._recent_records.clear()
                self._active_scrapes.clear()


# Global metrics instance
_scraper_metrics: ScraperMetrics | None = None


def get_scraper_metrics() -> ScraperMetrics:
    """Get the global scraper metrics instance."""
    global _scraper_metrics
    if _scraper_metrics is None:
        _scraper_metrics = ScraperMetrics()
    return _scraper_metrics
