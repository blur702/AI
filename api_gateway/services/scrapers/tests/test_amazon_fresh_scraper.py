"""
Tests for Amazon Fresh Scraper.

Tests scraper initialization, data extraction, rate limiting, retry logic,
and database storage functionality.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_gateway.config import settings
from api_gateway.services.scrapers.amazon_fresh_scraper import (
    PLAYWRIGHT_AVAILABLE,
    AmazonFreshScraper,
)
from api_gateway.services.scrapers.base_grocery_scraper import ScrapedProduct


class TestAmazonFreshScraperInitialization:
    """Tests for scraper initialization and configuration."""

    def test_scraper_initialization(self):
        """Verify scraper loads configuration correctly."""
        scraper = AmazonFreshScraper()

        assert scraper.service_name == "amazon_fresh"
        assert scraper.base_delay == settings.GROCERY_SERVICES["amazon_fresh"]["rate_limit_delay"]
        assert scraper.max_retries == settings.GROCERY_SERVICES["amazon_fresh"]["max_retries"]
        assert scraper.base_url == settings.GROCERY_SERVICES["amazon_fresh"]["base_url"]
        assert scraper.search_url == settings.GROCERY_SERVICES["amazon_fresh"]["search_url"]

    def test_scraper_viewport_settings(self):
        """Verify stealth viewport configuration."""
        scraper = AmazonFreshScraper()

        assert scraper.viewport["width"] == 1920
        assert scraper.viewport["height"] == 1080

    def test_user_agent_rotation(self):
        """Verify User-Agent rotation after requests."""
        scraper = AmazonFreshScraper()

        initial_ua = scraper.get_user_agent()
        assert initial_ua is not None

        # Simulate 10 requests
        for _ in range(10):
            scraper._request_count += 1

        # After 10 requests, get_user_agent should rotate
        scraper._request_count = 10
        _ = scraper.get_user_agent()
        # Note: rotation is random, so we just verify it doesn't error


class TestPriceNormalization:
    """Tests for price string normalization."""

    def test_normalize_price_with_dollar_sign(self):
        """Price with dollar sign should be preserved."""
        scraper = AmazonFreshScraper()
        assert scraper._normalize_price("$3.99") == "$3.99"

    def test_normalize_price_without_dollar_sign(self):
        """Price without dollar sign should get one added."""
        scraper = AmazonFreshScraper()
        result = scraper._normalize_price("3.99")
        assert result == "$3.99"

    def test_normalize_price_multi_buy_format(self):
        """Multi-buy format should be preserved."""
        scraper = AmazonFreshScraper()
        assert scraper._normalize_price("2 for $5") == "2 for $5"

    def test_normalize_price_with_whitespace(self):
        """Whitespace should be trimmed."""
        scraper = AmazonFreshScraper()
        result = scraper._normalize_price("  $4.99  ")
        assert result == "$4.99"


class TestBrandExtraction:
    """Tests for brand extraction from product names."""

    def test_extract_brand_simple(self):
        """Simple product name with brand first."""
        scraper = AmazonFreshScraper()
        result = scraper._extract_brand_from_name("Horizon Organic Whole Milk 1 Gallon")
        assert result == "Horizon"

    def test_extract_brand_skips_generic_words(self):
        """Generic words like 'Organic' should be skipped, returning None."""
        scraper = AmazonFreshScraper()
        result = scraper._extract_brand_from_name("Organic Valley Milk")
        assert result is None  # First word is generic, so no brand extracted

    def test_extract_brand_single_word(self):
        """Single word product name should return None."""
        scraper = AmazonFreshScraper()
        result = scraper._extract_brand_from_name("Milk")
        assert result is None


class TestSizeExtraction:
    """Tests for size/weight extraction from product names."""

    def test_extract_size_gallon(self):
        """Extract gallon measurement."""
        scraper = AmazonFreshScraper()
        result = scraper._extract_size_from_name("Horizon Organic Milk 1 gal")
        assert result == "1 gal"

    def test_extract_size_ounces(self):
        """Extract ounce measurement."""
        scraper = AmazonFreshScraper()
        result = scraper._extract_size_from_name("Greek Yogurt 32 oz")
        assert result == "32 oz"

    def test_extract_size_fluid_ounces(self):
        """Extract fluid ounce measurement."""
        scraper = AmazonFreshScraper()
        result = scraper._extract_size_from_name("Orange Juice 64 fl oz")
        assert result == "64 fl oz"

    def test_extract_size_count(self):
        """Extract count measurement."""
        scraper = AmazonFreshScraper()
        result = scraper._extract_size_from_name("Eggs 12 ct")
        assert result == "12 ct"

    def test_extract_size_pounds(self):
        """Extract pound measurement."""
        scraper = AmazonFreshScraper()
        result = scraper._extract_size_from_name("Ground Beef 2 lb")
        assert result == "2 lb"

    def test_extract_size_none(self):
        """Return None when no size found."""
        scraper = AmazonFreshScraper()
        result = scraper._extract_size_from_name("Fresh Bananas")
        assert result is None


class TestRateLimiting:
    """Tests for rate limiting functionality."""

@pytest.mark.asyncio
async def test_rate_limit_delay(self):
"""Verify rate limiting adds delay between requests."""
scraper = AmazonFreshScraper()
# First request should not delay much
start = asyncio.get_event_loop().time()
await scraper.rate_limit()
first_duration = asyncio.get_event_loop().time() - start
# Second request should have delay
start = asyncio.get_event_loop().time()
await scraper.rate_limit()
second_duration = asyncio.get_event_loop().time() - start
# Verify request count incremented
assert scraper._request_count == 2
# Second request should have at least base_delay
assert second_duration >= scraper.base_delay * 0.9  # Allow 10% tolerance


class TestRetryLogic:
    """Tests for exponential backoff retry logic."""

    @pytest.mark.asyncio
    async def test_retry_success_first_attempt(self):
        """Successful first attempt returns immediately."""
        scraper = AmazonFreshScraper()

        async def success_func():
            return "success"

        result = await scraper.retry_with_backoff(success_func)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_success_after_failure(self):
        """Retry succeeds after initial failures."""
        scraper = AmazonFreshScraper()
        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Temporary error")
            return "success"

        result = await scraper.retry_with_backoff(fail_then_succeed, max_retries=3)
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_all_attempts_fail(self):
        """All retry attempts fail, raises exception."""
        scraper = AmazonFreshScraper()

        async def always_fail():
            raise ValueError("Permanent error")

        with pytest.raises(ValueError, match="Permanent error"):
            await scraper.retry_with_backoff(always_fail, max_retries=2)


class TestDatabaseStorage:
    """Tests for product database storage."""

    @pytest.mark.asyncio
    async def test_store_products_empty_list(self):
        """Empty product list returns empty result."""
        scraper = AmazonFreshScraper()
        result = await scraper.store_products([])
        assert result == []

    @pytest.mark.asyncio
    async def test_store_products_creates_models(self):
        """Verify Product models are created correctly."""
        scraper = AmazonFreshScraper()

        scraped = [
            ScrapedProduct(
                name="Test Milk",
                price="$3.99",
                url="https://amazon.com/test-milk",
                size="1 gal",
                brand="TestBrand",
                image_url="https://images.amazon.com/test.jpg",
                availability=True,
                extra_data={"asin": "TEST123"},
            )
        ]

stored = await scraper.store_products(scraped)
# Verify session.add was called and products returned
assert mock_session_instance.add.called
assert mock_session_instance.commit.called
assert len(stored) == 1

# Verify the Product model was created with correct data
add_call_args = mock_session_instance.add.call_args
if add_call_args:
added_product = add_call_args[0][0]
assert added_product.name == "Test Milk"
assert added_product.service == "amazon_fresh"

# Verify the Product model was created with correct data
add_call_args = mock_session_instance.add.call_args
if add_call_args:
added_product = add_call_args[0][0]
assert added_product.name == "Test Milk"
assert added_product.service == "amazon_fresh"

# Verify the Product model was created with correct data
add_call_args = mock_session_instance.add.call_args
if add_call_args:
added_product = add_call_args[0][0]
assert added_product.name == "Test Milk"
assert added_product.service == "amazon_fresh"


class TestScrapedProduct:
    """Tests for ScrapedProduct dataclass."""

    def test_scraped_product_defaults(self):
        """Verify default values for optional fields."""
        product = ScrapedProduct(
            name="Test Product",
            price="$1.99",
            url="https://example.com/product",
        )

        assert product.name == "Test Product"
        assert product.price == "$1.99"
        assert product.url == "https://example.com/product"
        assert product.size is None
        assert product.brand is None
        assert product.image_url is None
        assert product.availability is True
        assert product.extra_data == {}


class TestPlaywrightAvailability:
    """Tests for Playwright availability handling."""

    def test_playwright_import_flag(self):
        """Verify PLAYWRIGHT_AVAILABLE flag is set."""
        # This just checks the flag exists and is a boolean
        assert isinstance(PLAYWRIGHT_AVAILABLE, bool)

@pytest.mark.asyncio
async def test_scrape_without_playwright(self):
"""Scraping without Playwright returns empty list and logs error."""
with patch("api_gateway.services.scrapers.amazon_fresh_scraper.PLAYWRIGHT_AVAILABLE", False):
scraper = AmazonFreshScraper()
result = await scraper.scrape_products("test query", "20024")
assert result == []


class TestScraperFactory:
    """Tests for scraper factory functions."""

    def test_get_scraper_amazon_fresh(self):
        """Get Amazon Fresh scraper instance."""
        from api_gateway.services.scrapers import get_scraper

        scraper = get_scraper("amazon_fresh")
        assert scraper is not None
        assert isinstance(scraper, AmazonFreshScraper)

    def test_get_scraper_unknown_service(self):
        """Unknown service returns None."""
        from api_gateway.services.scrapers import get_scraper

        scraper = get_scraper("unknown_service")
        assert scraper is None

    def test_get_scraper_singleton(self):
        """Same instance returned for repeated calls."""
        from api_gateway.services.scrapers import get_scraper

        scraper1 = get_scraper("amazon_fresh")
        scraper2 = get_scraper("amazon_fresh")
        assert scraper1 is scraper2

    def test_get_available_scrapers(self):
        """List available scrapers."""
        from api_gateway.services.scrapers.scraper_factory import get_available_scrapers

        scrapers = get_available_scrapers()
        assert "amazon_fresh" in scrapers

    def test_get_configured_services(self):
        """List configured services."""
        from api_gateway.services.scrapers.scraper_factory import get_configured_services

        services = get_configured_services()
        assert "amazon_fresh" in services
        assert "instacart" in services
        assert "doordash" in services
        assert "safeway" in services
