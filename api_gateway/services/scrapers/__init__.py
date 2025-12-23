"""
Grocery Service Scrapers.

Contains Playwright-based scrapers for extracting product data from
grocery delivery services. Each scraper extends BaseGroceryScraper
and implements service-specific extraction logic.

Available Scrapers:
    - AmazonFreshScraper: Amazon Fresh product scraping
    - (Future) InstacartScraper, DoorDashScraper, SafewayScraper

Usage:
    from api_gateway.services.scrapers import get_scraper

    scraper = get_scraper("amazon_fresh")
    products = await scraper.scrape_products("organic milk", "20024")
"""

from .scraper_factory import get_scraper

__all__ = ["get_scraper"]
