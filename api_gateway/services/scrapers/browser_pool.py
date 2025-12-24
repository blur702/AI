"""
Browser Context Pool Manager for Playwright-based scrapers.

Provides a pool of reusable browser contexts to reduce browser launch overhead
and improve scraping performance. Implements context health checking, pool
size limits, and usage metrics tracking.

Usage:
    pool = BrowserContextPool()
    context = await pool.acquire_context("instacart")
    # ... use context for scraping ...
    await pool.release_context("instacart", context)
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from api_gateway.config import settings
from api_gateway.utils.logger import get_logger

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Playwright

logger = get_logger("api_gateway.services.scrapers.browser_pool")

# Playwright import with graceful fallback
try:
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning(
        "Playwright not installed. Run: pip install playwright && playwright install chromium"
    )


@dataclass
class PooledContext:
    """A browser context with metadata for pool management."""

    context: "BrowserContext"
    created_at: float
    last_used_at: float
    use_count: int = 0
    healthy: bool = True


@dataclass
class PoolMetrics:
    """Metrics for browser pool usage."""

    total_acquisitions: int = 0
    pool_hits: int = 0
    pool_misses: int = 0
    contexts_created: int = 0
    contexts_closed: int = 0
    health_check_failures: int = 0
    active_contexts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert metrics to dictionary."""
        return {
            "total_acquisitions": self.total_acquisitions,
            "pool_hits": self.pool_hits,
            "pool_misses": self.pool_misses,
            "hit_rate": (
                round(self.pool_hits / self.total_acquisitions * 100, 1)
                if self.total_acquisitions > 0
                else 0
            ),
            "contexts_created": self.contexts_created,
            "contexts_closed": self.contexts_closed,
            "health_check_failures": self.health_check_failures,
            "active_contexts": dict(self.active_contexts),
        }


class BrowserContextPool:
    """
    Pool manager for Playwright browser contexts.

    Maintains a pool of reusable browser contexts per service to reduce
    the overhead of launching new browsers. Implements:
    - Configurable pool size per service
    - Context health checking
    - Maximum context age enforcement
    - Usage metrics tracking
    - Thread-safe acquisition/release
    """

    _instance: "BrowserContextPool | None" = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __new__(cls) -> "BrowserContextPool":
        """Singleton pattern to ensure one pool across all scrapers."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize the browser pool."""
        if self._initialized:
            return

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

        # Pool of available contexts per service
        self._available_pools: dict[str, list[PooledContext]] = {}
        # Currently in-use contexts per service (stores PooledContext to preserve metadata)
        self._in_use: dict[str, dict[BrowserContext, PooledContext]] = {}
        # Locks for thread-safe access
        self._service_locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

        # Configuration from settings
        price_settings = settings.PRICE_COMPARISON_SETTINGS
        self._pool_size = price_settings.get("browser_pool_size", 3)
        self._max_age_minutes = price_settings.get("browser_pool_max_age_minutes", 30)
        self._health_check_enabled = price_settings.get("browser_pool_health_check_enabled", True)

        # Metrics tracking
        self._metrics = PoolMetrics()

        # Browser launch args
        self._browser_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-translate",
            "--disable-notifications",
            "--no-first-run",
            "--no-default-browser-check",
        ]

        self._initialized = True
        logger.info(
            "Browser pool initialized: pool_size=%d, max_age=%d min, health_check=%s",
            self._pool_size,
            self._max_age_minutes,
            self._health_check_enabled,
        )

    async def _ensure_browser(self) -> "Browser":
        """Ensure Playwright browser is initialized."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright not available. Install with: pip install playwright && playwright install chromium"
            )

        if self._browser is not None and self._browser.is_connected():
            return self._browser

        async with self._global_lock:
            # Double-check after acquiring lock
            if self._browser is not None and self._browser.is_connected():
                return self._browser

            logger.info("Launching shared Playwright browser")
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=self._browser_args,
            )
            logger.info("Shared browser launched successfully")
            return self._browser

    def _get_service_lock(self, service_name: str) -> asyncio.Lock:
        """Get or create a lock for a specific service."""
        if service_name not in self._service_locks:
            self._service_locks[service_name] = asyncio.Lock()
        return self._service_locks[service_name]

    async def _create_context(self, service_name: str) -> PooledContext:
        """Create a new browser context for a service."""
        browser = await self._ensure_browser()

        # Get service-specific configuration
        settings.GROCERY_SERVICES.get(service_name, {})

        # Randomize viewport slightly for fingerprint diversity
        import random
        viewport = {
            "width": random.choice([1920, 1366, 1536, 1440]),
            "height": random.choice([1080, 768, 864, 900]),
        }

        # Common user agents
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]

        context = await browser.new_context(
            viewport=viewport,
            user_agent=random.choice(user_agents),
            locale="en-US",
            timezone_id="America/New_York",
            java_script_enabled=True,
        )

        now = time.time()
        pooled = PooledContext(
            context=context,
            created_at=now,
            last_used_at=now,
            use_count=0,
            healthy=True,
        )

        self._metrics.contexts_created += 1
        logger.debug("Created new context for %s (total created: %d)", service_name, self._metrics.contexts_created)

        return pooled

    async def _check_context_health(self, pooled: PooledContext) -> bool:
        """Check if a context is healthy and usable."""
        if not self._health_check_enabled:
            return True

        try:
            # Check if context is still connected
            pages = pooled.context.pages
            if pages:
                # Try to evaluate simple JS on an existing page
                page = pages[0]
                await page.evaluate("1 + 1")
            return True
        except Exception as e:
            logger.debug("Context health check failed: %s", e)
            self._metrics.health_check_failures += 1
            return False

    def _is_context_expired(self, pooled: PooledContext) -> bool:
        """Check if a context has exceeded its maximum age."""
        age_seconds = time.time() - pooled.created_at
        max_age_seconds = self._max_age_minutes * 60
        return age_seconds > max_age_seconds

    async def acquire_context(self, service_name: str) -> tuple["BrowserContext", bool]:
        """
        Acquire a browser context for a service.

        Attempts to get a context from the pool first. If none available,
        creates a new one if under the pool size limit.

        Args:
            service_name: The service requesting the context

        Returns:
            Tuple of (browser context, is_pool_hit) where is_pool_hit indicates
            whether the context was reused from the pool (True) or newly created (False)

        Raises:
            RuntimeError: If Playwright is not available
        """
        lock = self._get_service_lock(service_name)

        async with lock:
            self._metrics.total_acquisitions += 1

            # Initialize pool structures for this service if needed
            if service_name not in self._available_pools:
                self._available_pools[service_name] = []
            if service_name not in self._in_use:
                self._in_use[service_name] = {}

            available = self._available_pools[service_name]

            # Try to get from pool
            while available:
                pooled = available.pop(0)

                # Check if expired
                if self._is_context_expired(pooled):
                    logger.debug("Closing expired context for %s", service_name)
                    try:
                        await pooled.context.close()
                    except Exception:
                        pass
                    self._metrics.contexts_closed += 1
                    continue

                # Check health
                if not await self._check_context_health(pooled):
                    logger.debug("Closing unhealthy context for %s", service_name)
                    try:
                        await pooled.context.close()
                    except Exception:
                        pass
                    self._metrics.contexts_closed += 1
                    continue

                # Found a healthy context
                pooled.last_used_at = time.time()
                pooled.use_count += 1
                # Store PooledContext to preserve original created_at
                self._in_use[service_name][pooled.context] = pooled
                self._metrics.pool_hits += 1
                self._metrics.active_contexts[service_name] = len(self._in_use[service_name])

                logger.debug(
                    "Pool hit for %s (use_count=%d, active=%d)",
                    service_name,
                    pooled.use_count,
                    len(self._in_use[service_name]),
                )
                return (pooled.context, True)  # Pool hit

            # No available context, check if we can create a new one
            total_for_service = len(self._in_use[service_name])
            if total_for_service >= self._pool_size:
                # Wait for a context to be released
                logger.warning(
                    "Pool exhausted for %s (limit=%d), waiting for release",
                    service_name,
                    self._pool_size,
                )
                # Release lock and wait a bit, then retry
                await asyncio.sleep(0.5)
                # Recursive call will re-acquire lock
                return await self.acquire_context(service_name)

            # Create new context
            self._metrics.pool_misses += 1
            pooled = await self._create_context(service_name)
            pooled.use_count = 1
            # Store PooledContext to preserve original created_at
            self._in_use[service_name][pooled.context] = pooled
            self._metrics.active_contexts[service_name] = len(self._in_use[service_name])

            logger.debug(
                "Pool miss for %s, created new context (active=%d)",
                service_name,
                len(self._in_use[service_name]),
            )
            return (pooled.context, False)  # Pool miss

    async def release_context(
        self, service_name: str, context: "BrowserContext", healthy: bool = True
    ) -> None:
        """
        Release a browser context back to the pool.

        Args:
            service_name: The service returning the context
            context: The browser context to release
            healthy: Whether the context is still healthy for reuse
        """
        lock = self._get_service_lock(service_name)

        async with lock:
            if service_name not in self._in_use:
                return

            if context not in self._in_use[service_name]:
                logger.warning("Attempted to release unknown context for %s", service_name)
                return

            # Retrieve the original PooledContext to preserve created_at
            original_pooled = self._in_use[service_name].pop(context)
            self._metrics.active_contexts[service_name] = len(self._in_use[service_name])

            if healthy:
                # Return to pool for reuse
                if service_name not in self._available_pools:
                    self._available_pools[service_name] = []

                # Close any open pages before returning to pool
                try:
                    for page in context.pages:
                        await page.close()
                except Exception:
                    pass

                # Preserve original created_at so max-age enforcement works correctly
                original_pooled.last_used_at = time.time()
                original_pooled.healthy = True
                self._available_pools[service_name].append(original_pooled)
                logger.debug(
                    "Context returned to pool for %s (available=%d, age=%.1fs)",
                    service_name,
                    len(self._available_pools[service_name]),
                    time.time() - original_pooled.created_at,
                )
            else:
                # Close unhealthy context
                try:
                    await context.close()
                except Exception:
                    pass
                self._metrics.contexts_closed += 1
                logger.debug("Closed unhealthy context for %s", service_name)

    async def close_all(self) -> None:
        """Close all browser contexts and the browser itself."""
        logger.info("Closing browser pool...")

        # Close all available contexts
        for _service_name, pool in self._available_pools.items():
            for pooled in pool:
                try:
                    await pooled.context.close()
                    self._metrics.contexts_closed += 1
                except Exception:
                    pass
            pool.clear()

        # Close all in-use contexts
        for _service_name, context_map in self._in_use.items():
            for context in list(context_map.keys()):
                try:
                    await context.close()
                    self._metrics.contexts_closed += 1
                except Exception:
                    pass
            context_map.clear()

        # Close browser
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        # Stop playwright
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        self._metrics.active_contexts.clear()
        logger.info("Browser pool closed (total contexts closed: %d)", self._metrics.contexts_closed)

    def get_metrics(self) -> dict:
        """Get pool usage metrics."""
        return self._metrics.to_dict()

    def get_pool_status(self) -> dict:
        """Get current pool status."""
        status = {
            "browser_connected": self._browser is not None and self._browser.is_connected(),
            "pool_size_limit": self._pool_size,
            "max_age_minutes": self._max_age_minutes,
            "health_check_enabled": self._health_check_enabled,
            "services": {},
        }

        for service_name in set(list(self._available_pools.keys()) + list(self._in_use.keys())):
            available = len(self._available_pools.get(service_name, []))
            in_use = len(self._in_use.get(service_name, {}))
            status["services"][service_name] = {
                "available": available,
                "in_use": in_use,
                "total": available + in_use,
            }

        return status


# Global pool instance
_browser_pool: BrowserContextPool | None = None


def get_browser_pool() -> BrowserContextPool:
    """Get the global browser pool instance."""
    global _browser_pool
    if _browser_pool is None:
        _browser_pool = BrowserContextPool()
    return _browser_pool


async def close_browser_pool() -> None:
    """Close the global browser pool."""
    global _browser_pool
    if _browser_pool is not None:
        await _browser_pool.close_all()
        _browser_pool = None
