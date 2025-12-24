"""
Base Grocery Scraper with Anti-Ban Features.

Provides a robust foundation for scraping grocery delivery sites with:
- Variable rate limiting with randomized jitter
- Rotating User-Agent strings
- Exponential backoff on failures
- Playwright browser automation for JavaScript rendering
- Database storage via AsyncSessionLocal
- Error tracking integration

Usage:
    class MyGroceryScraper(BaseGroceryScraper):
        def __init__(self):
            super().__init__(service_name="my_service")

        async def scrape_products(self, query: str, location: str) -> list[Product]:
            # Implement scraping logic
            ...
"""

import asyncio
import random
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from api_gateway.config import settings
from api_gateway.models.database import AsyncSessionLocal, Product
from api_gateway.services.error_tracker import store_error
from api_gateway.utils.logger import get_logger

# Rotating User-Agent strings (common browsers)
USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Firefox on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Safari on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]


@dataclass
class ScrapedProduct:
    """Intermediate representation of a scraped product before database storage."""

    name: str
    price: str
    url: str
    size: str | None = None
    brand: str | None = None
    image_url: str | None = None
    availability: bool = True
    extra_data: dict[str, Any] = field(default_factory=dict)


class BaseGroceryScraper(ABC):
    """
    Abstract base class for grocery service scrapers.

    Provides common functionality for rate limiting, retries, User-Agent rotation,
    and database storage. Subclasses must implement scrape_products().
    """

    def __init__(self, service_name: str):
        """
        Initialize the scraper with service-specific configuration.

        Args:
            service_name: Key in settings.GROCERY_SERVICES (e.g., "amazon_fresh")
        """
        self.service_name = service_name
        self.logger = get_logger(f"api_gateway.services.scrapers.{service_name}")

        # Load service configuration
        if service_name not in settings.GROCERY_SERVICES:
            raise ValueError(f"Unknown grocery service: {service_name}")

        self.config = settings.GROCERY_SERVICES[service_name]
        self.base_delay = self.config.get("rate_limit_delay", 2.0)
        self.max_retries = self.config.get("max_retries", 3)
        self.base_url = self.config.get("base_url", "")
        self.search_url = self.config.get("search_url", "")

        # State tracking
        self._request_count = 0
        self._current_user_agent = random.choice(USER_AGENTS)
        self._last_request_time = 0.0

    def get_user_agent(self) -> str:
        """Get current User-Agent, rotating every 10 requests."""
        if self._request_count > 0 and self._request_count % 10 == 0:
            self._current_user_agent = random.choice(USER_AGENTS)
            self.logger.debug("Rotated User-Agent after %d requests", self._request_count)
        return self._current_user_agent

    async def rate_limit(self) -> None:
        """
        Apply rate limiting with jitter between requests.

        Base delay from config + random jitter (±20%).
        Every 10 requests, adds a longer pause (5-15s).
        """
        # Calculate delay with jitter (±20%)
        jitter = self.base_delay * 0.2 * (random.random() * 2 - 1)
        delay = self.base_delay + jitter

        # Every 10 requests, add a longer pause
        if self._request_count > 0 and self._request_count % 10 == 0:
            extra_pause = random.uniform(5.0, 15.0)
            delay += extra_pause
            self.logger.info(
                "Adding extended pause of %.1fs after %d requests",
                extra_pause,
                self._request_count,
            )

        # Ensure minimum time between requests
        elapsed = asyncio.get_event_loop().time() - self._last_request_time
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)

        self._last_request_time = asyncio.get_event_loop().time()
        self._request_count += 1

    async def retry_with_backoff(
        self,
        coro_func,
        *args,
        max_retries: int | None = None,
        **kwargs,
    ) -> Any:
        """
        Execute coroutine with exponential backoff on failure.

        Args:
            coro_func: Async function to execute
            *args: Arguments to pass to the function
            max_retries: Override default max retries
            **kwargs: Keyword arguments to pass to the function

        Returns:
            Result of the coroutine

        Raises:
            Exception: If all retries exhausted
        """
        retries = max_retries or self.max_retries
        last_error = None

        for attempt in range(retries):
            try:
                return await coro_func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    # Exponential backoff: 2^attempt seconds, max 60s
                    backoff = min(2 ** (attempt + 1), 60)
                    self.logger.warning(
                        "Attempt %d/%d failed: %s. Retrying in %ds...",
                        attempt + 1,
                        retries,
                        str(e)[:100],
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                else:
                    self.logger.error(
                        "All %d attempts failed for %s: %s",
                        retries,
                        self.service_name,
                        str(e),
                    )

        raise last_error  # type: ignore[misc]

    async def store_products(self, products: list[ScrapedProduct]) -> list[Product]:
        """
        Store scraped products in the database.

        Uses upsert logic - updates existing products if URL matches,
        otherwise inserts new records.

        Args:
            products: List of ScrapedProduct instances to store

        Returns:
            List of stored Product model instances with IDs
        """
        if not products:
            return []

        stored = []
        async with AsyncSessionLocal() as session:
            for scraped in products:
                try:
                    # Check for existing product by URL
                    result = await session.execute(
                        select(Product).where(Product.url == scraped.url)
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        # Update existing product
                        existing.name = scraped.name
                        existing.price = scraped.price
                        existing.size = scraped.size
                        existing.brand = scraped.brand
                        existing.image_url = scraped.image_url
                        existing.availability = scraped.availability
                        existing.extra_data = scraped.extra_data
                        existing.scraped_at = datetime.now(UTC)
                        stored.append(existing)
                        self.logger.debug("Updated existing product: %s", scraped.name[:50])
                    else:
                        # Insert new product
                        product = Product(
                            id=str(uuid.uuid4()),
                            service=self.service_name,
                            name=scraped.name,
                            price=scraped.price,
                            size=scraped.size,
                            brand=scraped.brand,
                            url=scraped.url,
                            image_url=scraped.image_url,
                            availability=scraped.availability,
                            extra_data=scraped.extra_data,
                            scraped_at=datetime.now(UTC),
                        )
                        session.add(product)
                        stored.append(product)
                        self.logger.debug("Inserted new product: %s", scraped.name[:50])

                except Exception as e:
                    self.logger.error("Failed to store product %s: %s", scraped.name[:50], e)
                    await self.log_error(
                        f"Database storage failed for product: {scraped.name[:100]}",
                        context={"url": scraped.url, "error": str(e)},
                    )

            await session.commit()

        self.logger.info(
            "Stored %d products for %s",
            len(stored),
            self.service_name,
        )
        return stored

    async def log_error(
        self,
        message: str,
        context: dict[str, Any] | None = None,
        severity: str = "error",
    ) -> None:
        """
        Log an error to the error tracking system.

        Args:
            message: Error message
            context: Additional context dict
            severity: Error severity (info, warning, error, critical)
        """
        try:
            ctx = context or {}
            ctx["service_name"] = self.service_name
            await store_error(
                service=f"scraper.{self.service_name}",
                message=message,
                severity=severity,
                stack_trace=None,
            )
        except Exception as e:
            self.logger.warning("Failed to log error to tracker: %s", e)

    @abstractmethod
    async def scrape_products(self, query: str, location: str) -> list[Product]:
        """
        Scrape products from the grocery service.

        Must be implemented by subclasses. Should:
        1. Navigate to the service's search page
        2. Set delivery location
        3. Search for the query
        4. Extract product data
        5. Store products using self.store_products()

        Args:
            query: Product search query (e.g., "organic milk")
            location: Zip code for delivery location (e.g., "20024")

        Returns:
            List of Product model instances that were stored
        """
        pass

    async def close(self) -> None:
        """
        Clean up resources.

        Override in subclasses to close browser contexts, etc.
        """
        # Default implementation does nothing; subclasses override as needed
        return
