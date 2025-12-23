"""
DoorDash Scraper using Playwright.

Scrapes product data from DoorDash convenience/grocery stores with:
- Location-aware searches (DC 20024 default)
- JavaScript rendering for dynamic content
- Enhanced stealth browser configuration (DoorDash has aggressive bot detection)
- Rate limiting and retry logic

Usage:
    scraper = DoorDashScraper()
    products = await scraper.scrape_products("organic milk", "20024")
"""

import asyncio
import hashlib
import random
import re
import time
from typing import Any

from api_gateway.config import settings
from api_gateway.utils.logger import get_logger

from .base_grocery_scraper import BaseGroceryScraper, ScrapedProduct

logger = get_logger("api_gateway.services.scrapers.doordash")

# Playwright import with graceful fallback
try:
    from playwright.async_api import (
        Browser,
        BrowserContext,
        Page,
        Playwright,
    )
    from playwright.async_api import TimeoutError as PlaywrightTimeout
    from playwright.async_api import (
        async_playwright,
    )

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Browser = None  # type: ignore[misc, assignment]
    BrowserContext = None  # type: ignore[misc, assignment]
    Page = None  # type: ignore[misc, assignment]
    Playwright = None  # type: ignore[misc, assignment]
    PlaywrightTimeout = Exception  # type: ignore[misc, assignment]
    logger.warning(
        "Playwright not installed. Run: pip install playwright && playwright install chromium"
    )


class DoorDashScraper(BaseGroceryScraper):
    """
    Playwright-based scraper for DoorDash convenience/grocery products.

    Uses browser automation to handle JavaScript-rendered content
    and location selection for delivery availability.

    Note: DoorDash has aggressive bot detection, so extra stealth measures are used.
    """

    def __init__(self):
        """Initialize DoorDash scraper with enhanced stealth browser settings."""
        super().__init__(service_name="doordash")

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._initialized = False

        # Stealth settings
        self.viewport = {"width": 1920, "height": 1080}
        self.timeout_ms = settings.PRICE_COMPARISON_SETTINGS.get("timeout_seconds", 30) * 1000

        # Preferred store types for grocery items
        self.preferred_stores = ["7-Eleven", "CVS", "Walgreens", "Safeway", "Grocery"]

    async def _ensure_browser(self) -> "BrowserContext":
        """
        Ensure Playwright browser is initialized.

        Uses enhanced stealth configuration for DoorDash's bot detection.
        """
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright not available. Install with: pip install playwright && playwright install chromium"
            )

        if self._context is not None:
            return self._context

        self.logger.info("Launching Playwright browser for DoorDash")

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )

        # Create context with enhanced stealth settings
        self._context = await self._browser.new_context(
            viewport=self.viewport,
            user_agent=self.get_user_agent(),
            locale="en-US",
            timezone_id="America/New_York",
            permissions=["geolocation"],
            geolocation={"latitude": 38.8786, "longitude": -76.9947},  # DC 20024
            java_script_enabled=True,
        )

        # Add enhanced stealth scripts for DoorDash
        await self._context.add_init_script("""
            // Override webdriver detection
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            // Override plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            // Override platform
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32'
            });
            // Override hardware concurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8
            });
            // Override device memory
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });
            // Chrome specific
            window.chrome = {
                runtime: {}
            };
        """)

        self._initialized = True
        return self._context

    async def _set_location(self, page: "Page", zip_code: str) -> bool:
        """
        Set delivery location on DoorDash.

        Args:
            page: Playwright page instance
            zip_code: Zip code for delivery location

        Returns:
            True if location was set successfully
        """
        try:
            self.logger.info("Setting DoorDash location to %s", zip_code)

            # Navigate to DoorDash homepage
            await page.goto(self.base_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            await self._random_delay(2, 4)

            # Look for address input on homepage
            address_selectors = [
                "input[data-anchor-id='AddressAutocompleteInput']",
                "input[placeholder*='address']",
                "input[placeholder*='Enter your address']",
                "[data-testid='AddressAutocompleteInput']",
                "input[aria-label*='address']",
            ]

            for selector in address_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=5000)
                    if element:
                        await element.click()
                        await self._random_delay(0.5, 1)
                        await element.fill("")
                        await self._type_with_delay(element, f"{zip_code}")
                        await self._random_delay(1, 2)

                        # Wait for suggestions and press Enter
                        await page.keyboard.press("Enter")
                        await self._random_delay(2, 4)

except Exception:
self.logger.debug("Selector %s not found, trying next", selector)
continue
    async def _navigate_to_grocery(self, page: "Page") -> bool:
        """
        Navigate to grocery/convenience section on DoorDash.

        Args:
            page: Playwright page instance
except Exception:
self.logger.debug("Selector %s not found, trying next", selector)
continue
self.logger.debug("Selector %s not found, trying next", selector)
continue
self.logger.debug("Selector %s not found, trying next", selector)
continue
        Returns:
            True if navigation was successful
        """
        try:
            # Use search_url directly if absolute, otherwise join with base_url
            if self.search_url.startswith("http"):
                convenience_url = self.search_url
            else:
                convenience_url = f"{self.base_url}{self.search_url}"
            self.logger.info("Navigating to grocery/convenience: %s", convenience_url)

            await page.goto(convenience_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            await self._random_delay(2, 4)

            return True

        except Exception as e:
            self.logger.warning("Could not navigate to grocery section: %s", e)
            return False

    async def _select_grocery_store(self, page: "Page") -> bool:
        """
        Select a grocery/convenience store from the list.

        Args:
            page: Playwright page instance

        Returns:
            True if a store was selected
        """
        try:
            # Look for store cards
            store_selectors = [
                "[data-testid='StoreCard']",
                "[data-anchor-id='StoreCard']",
                ".store-card",
                "[class*='StoreCard']",
            ]

            for selector in store_selectors:
                try:
                    stores = await page.query_selector_all(selector)
                    if stores:
                        # Try to find a preferred store
                        for store in stores:
                            store_text = await store.text_content()
                            if store_text:
                                for preferred in self.preferred_stores:
                                    if preferred.lower() in store_text.lower():
                                        await store.click()
                                        await self._random_delay(2, 4)
                                        self.logger.info("Selected store: %s", preferred)
                                        return True

                        # If no preferred store, select the first one
                        if stores:
                            await stores[0].click()
                            await self._random_delay(2, 4)
                            self.logger.info("Selected first available store")
                            return True
                except Exception:
                    continue

            return False

        except Exception as e:
            self.logger.warning("Could not select store: %s", e)
            return False

    async def _search_products(self, page: "Page", query: str) -> None:
        """
        Perform product search on DoorDash.

        Args:
            page: Playwright page instance
            query: Product search query
        """
        self.logger.info("Searching for: %s", query)

        # Look for search input within the store page
        search_selectors = [
            "input[data-anchor-id='SearchInput']",
            "input[placeholder*='Search']",
            "input[aria-label*='Search']",
            "[data-testid='SearchInput']",
            "input[type='search']",
        ]

        for selector in search_selectors:
            try:
                search_input = await page.wait_for_selector(selector, timeout=5000)
                if search_input:
                    await search_input.click()
                    await self._random_delay(0.5, 1)
                    await search_input.fill("")
                    await self._type_with_delay(search_input, query)
                    await self._random_delay(0.5, 1)
                    await page.keyboard.press("Enter")
                    await self._random_delay(2, 4)
                    return
            except Exception:
                continue

        self.logger.warning("Could not find search input, trying URL-based search")

        # Fallback: try URL-based search
        current_url = page.url
        if "?" in current_url:
            search_url = f"{current_url}&query={query.replace(' ', '%20')}"
        else:
            search_url = f"{current_url}?query={query.replace(' ', '%20')}"

        await page.goto(search_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        await self._random_delay(2, 4)

    async def _extract_products(self, page: "Page") -> list[ScrapedProduct]:
        """
        Extract product data from search results page.

        Args:
            page: Playwright page instance

        Returns:
            List of ScrapedProduct instances
        """
        products = []
        max_products = settings.PRICE_COMPARISON_SETTINGS.get("max_products_per_service", 10)

        # Get all product cards
        product_selectors = [
            "[data-testid='ItemCard']",
            "[data-anchor-id='ItemCard']",
            "[class*='ItemCard']",
            "[class*='StoreItem']",
            ".item-card",
        ]

        product_cards = []
        for selector in product_selectors:
            product_cards = await page.query_selector_all(selector)
            if product_cards:
                break

        self.logger.info("Found %d product cards", len(product_cards))

        for i, card in enumerate(product_cards[:max_products]):
            try:
                product = await self._extract_single_product(card, page)
                if product:
                    products.append(product)
                    self.logger.debug("Extracted product %d: %s", i + 1, product.name[:50])
            except Exception as e:
                self.logger.warning("Failed to extract product %d: %s", i + 1, e)
                continue

        return products

    async def _extract_single_product(
        self, card: Any, page: "Page"
    ) -> ScrapedProduct | None:
        """
        Extract data from a single product card.

        Args:
            card: Playwright element handle for product card
            page: Parent page instance

        Returns:
            ScrapedProduct instance or None if extraction fails
        """
        try:
            # Extract product name
            name = None
            name_selectors = [
                "[data-testid='ItemName']",
                "[class*='ItemName']",
                ".item-name",
                "h3",
                "span[class*='name']",
            ]
            for selector in name_selectors:
                elem = await card.query_selector(selector)
                if elem:
                    name = await elem.text_content()
                    if name:
                        name = name.strip()
                        break

            if not name:
                # Try to get any text content
                name = await card.text_content()
                if name:
                    name = name.strip()[:100]

            if not name:
                return None

            # Extract price
            price = None
            price_selectors = [
                "[data-testid='ItemPrice']",
                "[class*='ItemPrice']",
                "[class*='Price']",
                ".price",
                "span:has-text('$')",
            ]
            for selector in price_selectors:
                elem = await card.query_selector(selector)
                if elem:
                    price_text = await elem.text_content()
                    if price_text and "$" in price_text:
                        price = self._normalize_price(price_text.strip())
                        break

            if not price:
                price = "Price unavailable"

            # Extract product URL
            url = None
            link_elem = await card.query_selector("a")
            if link_elem:
                href = await link_elem.get_attribute("href")
                if href:
                    if href.startswith("/"):
                        url = f"https://www.doordash.com{href}"
                    else:
                        url = href

            if not url:
                # Generate unique fallback URL based on product name to avoid upsert collisions
                name_hash = hashlib.md5(name.encode()).hexdigest()[:12]
                url = f"https://www.doordash.com/convenience/item/{name_hash}"

            # Extract image URL
            image_url = None
            img_elem = await card.query_selector("img")
            if img_elem:
                image_url = await img_elem.get_attribute("src")
                if not image_url:
                    image_url = await img_elem.get_attribute("data-src")

            # Extract brand
            brand = self._extract_brand_from_name(name)

            # Extract size from product name
            size = self._extract_size_from_name(name)

            # Check availability (DoorDash usually shows "Add" button for available items)
            availability = True
            unavailable_selectors = [
                ":text('Sold out')",
                ":text('Unavailable')",
                "[data-testid='sold-out']",
            ]
            for selector in unavailable_selectors:
                unavailable_elem = await card.query_selector(selector)
                if unavailable_elem:
                    availability = False
                    break

            return ScrapedProduct(
                name=name,
                price=price,
                url=url,
                size=size,
                brand=brand,
                image_url=image_url,
                availability=availability,
                extra_data={
                    "scraped_from": "doordash_search",
                },
            )

        except Exception as e:
            self.logger.debug("Error extracting product: %s", e)
            return None

    def _normalize_price(self, price_text: str) -> str:
        """
        Normalize price string to consistent format.

        Args:
            price_text: Raw price text from page

        Returns:
            Normalized price string (e.g., "$3.99")
        """
        price = price_text.strip()

        # Handle "2 for $5" format
        if "for" in price.lower():
            return price

        # Extract price value
        match = re.search(r"\$[\d,]+\.?\d*", price)
        if match:
            return match.group()

        match = re.search(r"[\d,]+\.?\d*", price)
        if match:
            return f"${match.group()}"

        return price

    def _extract_brand_from_name(self, name: str) -> str | None:
        """Extract brand from product name."""
        parts = name.split()
        if len(parts) >= 2:
            potential_brand = parts[0]
            skip_words = {"organic", "fresh", "natural", "whole", "pure", "real", "100%"}
            if potential_brand.lower() not in skip_words:
                return potential_brand
        return None

    def _extract_size_from_name(self, name: str) -> str | None:
        """Extract size/weight from product name."""
        patterns = [
            r"(\d+\.?\d*)\s*(gal|gallon|oz|ounce|fl oz|lb|lbs|pound|ct|count|pk|pack|qt|quart|l|liter|ml|g|kg)\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, name, re.IGNORECASE)
            if match:
                return match.group(0)

        return None

    async def _random_delay(self, min_sec: float, max_sec: float) -> None:
        """Add random delay to appear more human-like."""
        await asyncio.sleep(random.uniform(min_sec, max_sec))

    async def _type_with_delay(self, element: Any, text: str) -> None:
        """Type text with random delays between characters."""
        for char in text:
            await element.type(char, delay=random.randint(50, 150))

    async def scrape_products(self, query: str, location: str) -> list:
        """
        Scrape products from DoorDash.

        Args:
            query: Product search query
            location: Zip code for delivery

        Returns:
            List of Product model instances stored in database
        """
        if not PLAYWRIGHT_AVAILABLE:
            self.logger.error("Playwright not available")
            await self.log_error(
                "Playwright not installed",
                context={"query": query, "location": location},
                severity="error",
            )
            raise RuntimeError(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )

        start_time = time.time()
        page = None

        async def _do_scrape() -> list:
            """Inner function for retry logic."""
            nonlocal page

            # Apply rate limiting
            await self.rate_limit()

            # Initialize browser with retry
            context = await self._ensure_browser()
            page = await context.new_page()

            try:
                # Set location
                await self._set_location(page, location)

                # Navigate to grocery/convenience section
                await self._navigate_to_grocery(page)

                # Try to select a grocery store
                await self._select_grocery_store(page)

                # Apply rate limiting before search
                await self.rate_limit()

                # Search for products
                await self._search_products(page, query)

                # Extract products
                scraped_products = await self._extract_products(page)

                if not scraped_products:
                    self.logger.warning("No products found for query: %s", query)
                    raise ValueError(f"No products found for query: {query}")

                return scraped_products

            finally:
                if page:
                    try:
                        await page.close()
                        page = None
                    except Exception:
                        pass

        try:
            # Wrap entire scrape flow in retry logic
            scraped_products = await self.retry_with_backoff(_do_scrape)

            # Store products in database
            stored_products = await self.store_products(scraped_products)

            duration = time.time() - start_time
            self.logger.info(
                "Scraped %d products for '%s' in %.2fs",
                len(stored_products),
                query,
                duration,
            )

            return stored_products

        except PlaywrightTimeout as e:
            self.logger.error("Timeout scraping DoorDash after retries: %s", e)
            await self.log_error(
                f"Timeout during scrape after retries: {query}",
                context={"query": query, "location": location},
                severity="error",
            )
            raise RuntimeError(f"DoorDash scrape timed out: {e}") from e

        except ValueError as e:
            self.logger.error("No products found after retries: %s", e)
            await self.log_error(
                f"No products found after retries: {query}",
                context={"query": query, "location": location},
                severity="warning",
            )
            raise RuntimeError(f"DoorDash scrape found no products: {e}") from e

        except Exception as e:  # noqa: BLE001
            self.logger.error("Error scraping DoorDash after retries: %s", e)
            await self.log_error(
                f"Scrape failed after retries: {str(e)[:200]}",
                context={"query": query, "location": location},
                severity="error",
            )
            raise RuntimeError(f"DoorDash scrape failed: {e}") from e

        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass

    async def close(self) -> None:
        """Clean up Playwright resources."""
        try:
            if self._context:
                await self._context.close()
                self._context = None

            if self._browser:
                await self._browser.close()
                self._browser = None

            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

            self._initialized = False
            self.logger.info("DoorDash scraper closed")

        except Exception as e:
            self.logger.warning("Error closing scraper: %s", e)
