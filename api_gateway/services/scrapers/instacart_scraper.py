"""
Instacart Scraper using Playwright.

Scrapes product data from Instacart with:
- Location-aware searches (DC 20024 default)
- JavaScript rendering for dynamic content
- Stealth browser configuration
- Rate limiting and retry logic

Usage:
    scraper = InstacartScraper()
    products = await scraper.scrape_products("organic milk", "20024")
"""

import asyncio
import random
import re
import time
from typing import Any

from api_gateway.config import settings
from api_gateway.utils.logger import get_logger

from .base_grocery_scraper import BaseGroceryScraper, ScrapedProduct

logger = get_logger("api_gateway.services.scrapers.instacart")

# Playwright import with graceful fallback
try:
    from playwright.async_api import (
        Browser,
        BrowserContext,
        Page,
        Playwright,
        async_playwright,
    )
    from playwright.async_api import TimeoutError as PlaywrightTimeout

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


class InstacartScraper(BaseGroceryScraper):
    """
    Playwright-based scraper for Instacart products.

    Uses browser automation to handle JavaScript-rendered content
    and location selection for delivery availability.
    """

    def __init__(self):
        """Initialize Instacart scraper with stealth browser settings."""
        super().__init__(service_name="instacart")

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._initialized = False

        # Stealth settings
        self.viewport = {"width": 1920, "height": 1080}
        self.timeout_ms = settings.PRICE_COMPARISON_SETTINGS.get("timeout_seconds", 30) * 1000

    async def _ensure_browser(self) -> "BrowserContext":
        """
        Ensure Playwright browser is initialized.

        Lazy initialization to avoid starting browser until needed.
        Uses stealth configuration to avoid bot detection.
        """
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright not available. Install with: pip install playwright && playwright install chromium"
            )

        if self._context is not None:
            return self._context

        self.logger.info("Launching Playwright browser for Instacart")

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        # Create context with stealth settings
        self._context = await self._browser.new_context(
            viewport=self.viewport,
            user_agent=self.get_user_agent(),
            locale="en-US",
            timezone_id="America/New_York",
            permissions=["geolocation"],
            geolocation={"latitude": 38.8786, "longitude": -76.9947},  # DC 20024
            java_script_enabled=True,
        )

        # Add stealth scripts to avoid detection
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
        """)

        self._initialized = True
        return self._context

    async def _set_location(self, page: "Page", zip_code: str) -> bool:
        """
        Set delivery location on Instacart.

        Args:
            page: Playwright page instance
            zip_code: Zip code for delivery location

        Returns:
            True if location was set successfully
        """
        try:
            self.logger.info("Setting Instacart location to %s", zip_code)

            # Navigate to Instacart homepage
            await page.goto(self.base_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            await self._random_delay(2, 4)

            # Look for location/address input element
            location_selectors = [
                "[data-testid='address-input']",
                "input[placeholder*='address']",
                "input[placeholder*='zip']",
                "[aria-label*='address']",
                "button:has-text('Enter zip code')",
                "[data-testid='store-selector-button']",
            ]

            for selector in location_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        await element.click()
                        await self._random_delay(1, 2)
                        break
                except Exception:
                    continue

            # Wait for address input modal
            zip_input_selectors = [
                "input[data-testid='postalCode-input']",
                "input[name='postalCode']",
                "input[placeholder*='zip']",
                "input[placeholder*='postal']",
                "input[aria-label*='zip']",
            ]

            for selector in zip_input_selectors:
                try:
                    zip_input = await page.wait_for_selector(selector, timeout=5000)
                    if zip_input:
                        await zip_input.fill("")
                        await self._type_with_delay(zip_input, zip_code)
                        await self._random_delay(0.5, 1)

                        # Press Enter or click submit
                        await page.keyboard.press("Enter")
                        await self._random_delay(2, 4)

                        # Handle store selection if it appears
                        await self._select_store(page)

                        self.logger.info("Location set to %s", zip_code)
                        return True
                except Exception:
                    continue

            self.logger.warning("Could not set location, continuing with default")
            return False

        except Exception as e:
            self.logger.error("Error setting location: %s", e)
            return False

    async def _select_store(self, page: "Page") -> None:
        """
        Select a store if Instacart shows store picker.

        Args:
            page: Playwright page instance
        """
        try:
            # Wait briefly for store selection modal
            await self._random_delay(1, 2)

            # Look for store options and select the first available
            store_selectors = [
                "[data-testid='store-card']",
                "[data-testid='retailer-card']",
                ".store-card",
                "[role='button']:has-text('Shop')",
            ]

            for selector in store_selectors:
                try:
                    store = await page.wait_for_selector(selector, timeout=3000)
                    if store:
                        await store.click()
                        await self._random_delay(1, 2)
                        self.logger.info("Selected store")
                        return
                except Exception:
                    continue

        except Exception as e:
            self.logger.debug("No store selection needed or failed: %s", e)

    async def _search_products(self, page: "Page", query: str) -> None:
        """
        Perform product search on Instacart.

        Args:
            page: Playwright page instance
            query: Product search query
        """
        # Construct search URL
        encoded_query = query.replace(" ", "%20")
        search_url = f"{self.search_url}?search_term={encoded_query}"

        self.logger.info("Searching for: %s", query)
        await page.goto(search_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        await self._random_delay(2, 4)

        # Wait for product grid to load
        product_grid_selectors = [
            "[data-testid='product-card']",
            "[data-testid='item-card']",
            ".product-card",
            "[class*='ProductCard']",
        ]

        for selector in product_grid_selectors:
            try:
                await page.wait_for_selector(selector, timeout=self.timeout_ms)
                return
            except Exception:
                continue

        self.logger.warning("No product grid found, checking for search results")

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
            "[data-testid='product-card']",
            "[data-testid='item-card']",
            "[class*='ProductCard']",
            ".product-card",
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
                "[data-testid='product-title']",
                "[class*='ProductName']",
                ".product-title",
                "h3",
                "[class*='ItemName']",
            ]
            for selector in name_selectors:
                elem = await card.query_selector(selector)
                if elem:
                    name = await elem.text_content()
                    if name:
                        name = name.strip()
                        break

            if not name:
                return None

            # Extract price
            price = None
            price_selectors = [
                "[data-testid='product-price']",
                "[class*='ProductPrice']",
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
                        url = f"https://www.instacart.com{href}"
                    else:
                        url = href

            if not url:
                # Generate a placeholder URL
                url = f"https://www.instacart.com/search/{name.replace(' ', '%20')}"

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

            # Check availability
            availability = True
            unavailable_selectors = [
                ":text('Out of stock')",
                ":text('Unavailable')",
                "[data-testid='out-of-stock']",
            ]
            for selector in unavailable_selectors:
                unavailable_elem = await card.query_selector(selector)
                if unavailable_elem:
                    availability = False
                    break

            # Get product ID from card attributes
            product_id = await card.get_attribute("data-product-id")
            if not product_id:
                product_id = await card.get_attribute("data-testid")

            return ScrapedProduct(
                name=name,
                price=price,
                url=url,
                size=size,
                brand=brand,
                image_url=image_url,
                availability=availability,
                extra_data={
                    "product_id": product_id,
                    "scraped_from": "instacart_search",
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
        # Remove extra whitespace
        price = price_text.strip()

        # Handle "2 for $5" format
        if "for" in price.lower():
            return price

        # Extract price value
        match = re.search(r"\$[\d,]+\.?\d*", price)
        if match:
            return match.group()

        # Try to extract just numbers and format
        match = re.search(r"[\d,]+\.?\d*", price)
        if match:
            return f"${match.group()}"

        return price

    def _extract_brand_from_name(self, name: str) -> str | None:
        """
        Extract brand from product name.

        Args:
            name: Product name

        Returns:
            Brand name or None
        """
        parts = name.split()
        if len(parts) >= 2:
            potential_brand = parts[0]
            skip_words = {"organic", "fresh", "natural", "whole", "pure", "real", "100%"}
            if potential_brand.lower() not in skip_words:
                return potential_brand
        return None

    def _extract_size_from_name(self, name: str) -> str | None:
        """
        Extract size/weight from product name.

        Args:
            name: Product name

        Returns:
            Size string or None
        """
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
        Scrape products from Instacart.

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
            self.logger.error("Timeout scraping Instacart after retries: %s", e)
            await self.log_error(
                f"Timeout during scrape after retries: {query}",
                context={"query": query, "location": location},
                severity="error",
            )
            raise RuntimeError(f"Instacart scrape timed out: {e}") from e

        except ValueError as e:
            self.logger.error("No products found after retries: %s", e)
            await self.log_error(
                f"No products found after retries: {query}",
                context={"query": query, "location": location},
                severity="warning",
            )
            raise RuntimeError(f"Instacart scrape found no products: {e}") from e

        except Exception as e:  # noqa: BLE001
            self.logger.error("Error scraping Instacart after retries: %s", e)
            await self.log_error(
                f"Scrape failed after retries: {str(e)[:200]}",
                context={"query": query, "location": location},
                severity="error",
            )
            raise RuntimeError(f"Instacart scrape failed: {e}") from e

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
            self.logger.info("Instacart scraper closed")

        except Exception as e:
            self.logger.warning("Error closing scraper: %s", e)
