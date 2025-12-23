"""
Scraper Factory for Grocery Services.

Provides centralized instantiation and management of grocery scrapers.
Uses singleton pattern to reuse browser contexts across requests.

Usage:
    from api_gateway.services.scrapers import get_scraper

    scraper = get_scraper("amazon_fresh")
    if scraper:
        products = await scraper.scrape_products("milk", "20024")
"""

from typing import TYPE_CHECKING

from api_gateway.config import settings
from api_gateway.utils.logger import get_logger

if TYPE_CHECKING:
    from .base_grocery_scraper import BaseGroceryScraper

logger = get_logger("api_gateway.services.scrapers.factory")

# Registry of available scrapers
# Maps service name to scraper class
_SCRAPER_REGISTRY: dict[str, type["BaseGroceryScraper"]] = {}

# Singleton instances for reusing browser contexts
_SCRAPER_INSTANCES: dict[str, "BaseGroceryScraper"] = {}


def _register_scrapers() -> None:
    """
    Register all available scraper classes.

    Called lazily on first get_scraper() call to avoid import
    issues during module initialization.
    """
    global _SCRAPER_REGISTRY

    if _SCRAPER_REGISTRY:
        return  # Already registered

    try:
        from .amazon_fresh_scraper import AmazonFreshScraper

        _SCRAPER_REGISTRY["amazon_fresh"] = AmazonFreshScraper
        logger.debug("Registered AmazonFreshScraper")
    except ImportError as e:
        logger.warning("Failed to register AmazonFreshScraper: %s", e)

    try:
        from .instacart_scraper import InstacartScraper

        _SCRAPER_REGISTRY["instacart"] = InstacartScraper
        logger.debug("Registered InstacartScraper")
    except ImportError as e:
        logger.warning("Failed to register InstacartScraper: %s", e)

    try:
        from .doordash_scraper import DoorDashScraper

        _SCRAPER_REGISTRY["doordash"] = DoorDashScraper
        logger.debug("Registered DoorDashScraper")
    except ImportError as e:
        logger.warning("Failed to register DoorDashScraper: %s", e)

    try:
        from .safeway_scraper import SafewayScraper

        _SCRAPER_REGISTRY["safeway"] = SafewayScraper
        logger.debug("Registered SafewayScraper")
    except ImportError as e:
        logger.warning("Failed to register SafewayScraper: %s", e)


def get_scraper(service_name: str) -> "BaseGroceryScraper | None":
    """
    Get or create a scraper instance for the specified service.

    Uses singleton pattern - returns existing instance if available,
    creates new one otherwise. Browser contexts are reused across requests.

    Args:
        service_name: Key in settings.GROCERY_SERVICES (e.g., "amazon_fresh")

    Returns:
        Scraper instance or None if service not implemented/configured
    """
    # Ensure scrapers are registered
    _register_scrapers()

    # Check if service is configured
    if service_name not in settings.GROCERY_SERVICES:
        logger.warning("Grocery service '%s' not in configuration", service_name)
        return None

    # Check if scraper is implemented
    if service_name not in _SCRAPER_REGISTRY:
        logger.info("Scraper not implemented for '%s'", service_name)
        return None

    # Return existing instance or create new one
    if service_name not in _SCRAPER_INSTANCES:
        scraper_class = _SCRAPER_REGISTRY[service_name]
        try:
            _SCRAPER_INSTANCES[service_name] = scraper_class()
            logger.info("Created new scraper instance for '%s'", service_name)
        except Exception as e:
            logger.error("Failed to create scraper for '%s': %s", service_name, e)
            return None

    return _SCRAPER_INSTANCES[service_name]


def get_available_scrapers() -> list[str]:
    """
    Get list of service names with implemented scrapers.

    Returns:
        List of service names that have scrapers available
    """
    _register_scrapers()
    return list(_SCRAPER_REGISTRY.keys())


def get_configured_services() -> list[str]:
    """
    Get list of all configured grocery services.

    Returns:
        List of service names from GROCERY_SERVICES config
    """
    return list(settings.GROCERY_SERVICES.keys())


async def close_all_scrapers() -> None:
"""
Close all active scraper instances.
Should be called during application shutdown to clean up
browser contexts and other resources.

Note: This clears scraper instances but preserves the registry.
Calling get_scraper() after this will create fresh instances.
"""
Note: This clears scraper instances but preserves the registry.
Calling get_scraper() after this will create fresh instances.
"""

Note: This clears scraper instances but preserves the registry.
Calling get_scraper() after this will create fresh instances.
"""
global _SCRAPER_INSTANCES

for service_name, scraper in list(_SCRAPER_INSTANCES.items()):
try:
if hasattr(scraper, "close"):
await scraper.close()
logger.info("Closed scraper for '%s'", service_name)
except Exception as e:
logger.warning("Error closing scraper '%s': %s", service_name, e)

_SCRAPER_INSTANCES.clear()
logger.info("All scrapers closed")
Note: This clears scraper instances but preserves the registry.
Calling get_scraper() after this will create fresh instances.
"""
Note: This clears scraper instances but preserves the registry.
Calling get_scraper() after this will create fresh instances.
"""
Note: This clears scraper instances but preserves the registry.
Calling get_scraper() after this will create fresh instances.
"""
Note: This clears scraper instances but preserves the registry.
Calling get_scraper() after this will create fresh instances.
"""

async def scrape_service(
    service_name: str,
    query: str,
    location: str,
) -> list:
    """
    Convenience function to scrape products from a service.

    Args:
        service_name: Grocery service to scrape
        query: Product search query
        location: Zip code for delivery

    Returns:
        List of Product model instances, empty list if scraper unavailable
    """
    scraper = get_scraper(service_name)
    if not scraper:
        return []

    try:
        return await scraper.scrape_products(query, location)
    except Exception as e:
        logger.error("Error scraping '%s' for '%s': %s", service_name, query, e)
        return []
