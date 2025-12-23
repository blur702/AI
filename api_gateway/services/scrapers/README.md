# Grocery Service Scrapers

Playwright-based scrapers for extracting product data from grocery delivery services.

## Overview

This module provides a robust scraping infrastructure for comparing prices across grocery delivery services. Each scraper extends the `BaseGroceryScraper` abstract class and implements service-specific extraction logic.

## Architecture

## Architecture

````text
scrapers/
├── __init__.py              # Package exports
├── base_grocery_scraper.py  # Abstract base class
├── amazon_fresh_scraper.py  # Amazon Fresh implementation
├── scraper_factory.py       # Scraper instantiation
├── README.md                # This file
## Architecture
```text
scrapers/
├── __init__.py              # Package exports
├── base_grocery_scraper.py  # Abstract base class
├── amazon_fresh_scraper.py  # Amazon Fresh implementation
├── scraper_factory.py       # Scraper instantiation
├── README.md                # This file
└── tests/
└── test_amazon_fresh_scraper.py
```
```text
scrapers/
├── __init__.py              # Package exports
├── base_grocery_scraper.py  # Abstract base class
├── amazon_fresh_scraper.py  # Amazon Fresh implementation
├── scraper_factory.py       # Scraper instantiation
├── README.md                # This file
└── tests/
└── test_amazon_fresh_scraper.py
```
```text
scrapers/
├── __init__.py              # Package exports
├── base_grocery_scraper.py  # Abstract base class
├── amazon_fresh_scraper.py  # Amazon Fresh implementation
├── scraper_factory.py       # Scraper instantiation
├── README.md                # This file
└── tests/
└── test_amazon_fresh_scraper.py
````

└── test_amazon_fresh_scraper.py

````

## Available Scrapers

| Service      | Class                | Status      |
| ------------ | -------------------- | ----------- |
| Amazon Fresh | `AmazonFreshScraper` | Implemented |
| Instacart    | `InstacartScraper`   | Planned     |
| DoorDash     | `DoorDashScraper`    | Planned     |
| Safeway      | `SafewayScraper`     | Planned     |

## Installation

### 1. Install Playwright Python Package

```bash
pip install playwright
````

### 2. Install Browser Binaries

```bash
playwright install chromium
```

**Note:** This downloads ~200MB of browser binaries. For Docker deployments, use `playwright install-deps chromium` to install system dependencies.

## Usage

### Basic Usage

```python
from api_gateway.services.scrapers import get_scraper

# Get scraper instance (singleton pattern)
scraper = get_scraper("amazon_fresh")

# Scrape products
products = await scraper.scrape_products("organic milk", "20024")

# Products are automatically stored in database
for product in products:
    print(f"{product.name}: {product.price}")
```

### From API Routes

```python
from api_gateway.services.scrapers.scraper_factory import (
    get_available_scrapers,
    scrape_service,
)

# Get list of available scrapers
available = get_available_scrapers()  # ["amazon_fresh"]

# Scrape a specific service
products = await scrape_service("amazon_fresh", "milk", "20024")
```

### Cleanup

```python
from api_gateway.services.scrapers.scraper_factory import close_all_scrapers

# Close all browser contexts (call on application shutdown)
await close_all_scrapers()
```

## Configuration

Scrapers are configured via `settings.GROCERY_SERVICES` in `api_gateway/config.py`:

```python
GROCERY_SERVICES = {
    "amazon_fresh": {
        "name": "Amazon Fresh",
        "base_url": "https://www.amazon.com/alm/storefront",
        "search_url": "https://www.amazon.com/s",
        "requires_auth": True,
        "rate_limit_delay": 2.0,  # Seconds between requests
        "max_retries": 3,         # Retry attempts on failure
    },
    # ... other services
}
```

### Required Configuration Keys

| Key                | Type  | Description                      |
| ------------------ | ----- | -------------------------------- |
| `name`             | str   | Human-readable service name      |
| `base_url`         | str   | Service homepage URL             |
| `search_url`       | str   | Product search endpoint          |
| `rate_limit_delay` | float | Minimum seconds between requests |
| `max_retries`      | int   | Maximum retry attempts           |

### Optional Configuration Keys

| Key             | Type | Description                      |
| --------------- | ---- | -------------------------------- |
| `requires_auth` | bool | Whether authentication is needed |

## Adding a New Scraper

### 1. Create Scraper Class

```python
# api_gateway/services/scrapers/instacart_scraper.py

from .base_grocery_scraper import BaseGroceryScraper, ScrapedProduct

class InstacartScraper(BaseGroceryScraper):
    def __init__(self):
        super().__init__(service_name="instacart")

    async def scrape_products(self, query: str, location: str) -> list:
        # 1. Initialize browser
        context = await self._ensure_browser()
        page = await context.new_page()

        try:
            # 2. Set location
            await self._set_location(page, location)

            # 3. Search products
            await self._search_products(page, query)

            # 4. Extract product data
            scraped = await self._extract_products(page)

            # 5. Store in database
            return await self.store_products(scraped)
        finally:
            await page.close()
```

### 2. Register in Factory

```python
# api_gateway/services/scrapers/scraper_factory.py

def _register_scrapers() -> None:
    # ... existing registrations ...

    try:
        from .instacart_scraper import InstacartScraper
        _SCRAPER_REGISTRY["instacart"] = InstacartScraper
    except ImportError as e:
        logger.warning("Failed to register InstacartScraper: %s", e)
```

### 3. Add Tests

```python
# api_gateway/services/scrapers/tests/test_instacart_scraper.py

class TestInstacartScraperInitialization:
    def test_scraper_initialization(self):
        scraper = InstacartScraper()
        assert scraper.service_name == "instacart"
```

## Rate Limiting & Politeness

### Default Behavior

- **Base delay:** 2 seconds between requests (configurable)
- **Jitter:** ±20% randomization on delay
- **Extended pause:** 5-15 seconds every 10 requests
- **User-Agent rotation:** Changes every 10 requests

### Stealth Features

The scraper uses several techniques to avoid detection:

1. **Realistic viewport:** 1920x1080
2. **Custom User-Agents:** Rotating pool of common browsers
3. **Geolocation spoofing:** Set to DC area coordinates
4. **Anti-detection scripts:** Override `navigator.webdriver`
5. **Random delays:** Variable typing speed and mouse movements

### Best Practices

1. **Respect robots.txt:** Don't scrape disallowed paths
2. **Handle rate limits gracefully:** Back off on 429 responses
3. **Cache results:** Use `scraped_at` timestamp for freshness
4. **Don't overload:** Limit concurrent scrapers per service

## Error Handling

### Automatic Retry

Failed requests are automatically retried with exponential backoff:

| Attempt | Wait Time            |
| ------- | -------------------- |
| 1       | Immediate            |
| 2       | 2 seconds            |
| 3       | 4 seconds            |
| ...     | min(2^n, 60) seconds |

### Error Logging

Errors are logged to the PostgreSQL `errors` table via `error_tracker.py`:

```python
await scraper.log_error(
    message="Scrape failed",
    context={"query": "milk", "location": "20024"},
    severity="error"  # info, warning, error, critical
)
```

## Troubleshooting

### Playwright Installation Issues

### Playwright Installation Issues

**Error:** `playwright._impl._errors.Error: Executable doesn't exist`
**Solution:**

```bash
playwright install chromium
```

**On Linux/Docker:**

### Database Errors

**Symptoms:** Products not saving, duplicate key errors
**Debug:**

```bash
python -m api_gateway.services.error_tracker list --service "scraper.amazon_fresh"
```

### Database Errors

**Symptoms:** Products not saving, duplicate key errors
**Debug:**

```bash
python -m api_gateway.services.error_tracker list --service "scraper.amazon_fresh"
```

### Database Errors

**Symptoms:** Products not saving, duplicate key errors
**Debug:**

```bash
python -m api_gateway.services.error_tracker list --service "scraper.amazon_fresh"
```

### Database Errors

**Symptoms:** Products not saving, duplicate key errors
**Debug:**

```bash
python -m api_gateway.services.error_tracker list --service "scraper.amazon_fresh"
```

```bash
playwright install-deps chromium
playwright install chromium
```

**Error:** `playwright._impl._errors.Error: Executable doesn't exist`
**Solution:**

```bash
playwright install chromium
```

**On Linux/Docker:**

```bash
playwright install-deps chromium
playwright install chromium
```

### Location Detection Fails

**Symptoms:** Wrong location shown, no products found

**Possible causes:**

1. Amazon detected automation
2. Location modal selectors changed
3. Network issues

**Debug steps:**

1. Enable debug logging: `LOG_LEVEL=DEBUG`
2. Check browser screenshots (add `await page.screenshot(...)`)
3. Verify location modal HTML structure

### Rate Limiting / Blocking

**Symptoms:** 503 errors, CAPTCHA pages, empty results

**Solutions:**

1. Increase `rate_limit_delay` in config
2. Rotate IP addresses (proxy support planned)
3. Reduce concurrent scrapers

### Database Errors

### Database Errors

**Symptoms:** Products not saving, duplicate key errors
**Debug:**

```bash
python -m api_gateway.services.error_tracker list --service "scraper.amazon_fresh"
```

## Performance

### Metrics

The scraper logs the following metrics:

- Total products found
- Products successfully stored
- Scrape duration (seconds)
- Retry count
- Rate limit pauses

### Benchmarks

| Operation           | Typical Time |
| ------------------- | ------------ |
| Browser launch      | 2-5 seconds  |
| Location set        | 3-8 seconds  |
| Product search      | 5-15 seconds |
| Extract 10 products | 2-5 seconds  |
| Database storage    | <1 second    |

**Total:** ~15-30 seconds per search query

## Database Schema

Products are stored in the `products` table:

| Column         | Type         | Description            |
| -------------- | ------------ | ---------------------- |
| `id`           | UUID         | Primary key            |
| `service`      | VARCHAR(50)  | Service name (indexed) |
| `name`         | VARCHAR(500) | Product name           |
| `price`        | VARCHAR(50)  | Price string           |
| `size`         | VARCHAR(100) | Size/weight            |
| `brand`        | VARCHAR(200) | Brand name             |
| `url`          | TEXT         | Product page URL       |
| `image_url`    | TEXT         | Product image URL      |
| `availability` | BOOLEAN      | In stock status        |
| `extra_data`   | JSON         | Service-specific data  |
| `scraped_at`   | TIMESTAMP    | When scraped (indexed) |
| `created_at`   | TIMESTAMP    | Record creation time   |
