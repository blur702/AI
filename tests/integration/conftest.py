"""
Integration test fixtures for grocery price comparison app.

Provides real component instances for testing full workflows:
- Database sessions with rollback
- Redis test database with cleanup
- Browser pool for scraping tests
- VPN manager for rotation tests
- Cache manager for multi-layer caching
- Scraper instances with test mode
"""

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set test environment before imports
os.environ["TESTING"] = "true"
os.environ["TEST_MODE"] = "true"

# Import application components
try:
    from api_gateway.models.database import (  # noqa: F401
        Base,
        Comparison,
        Product,
        SavedSelection,
        ShoppingList,
    )
    from api_gateway.services.cache_manager import CacheManager
    from api_gateway.services.comparison_manager import ComparisonManager
    from api_gateway.services.product_matcher import ProductMatcher
    from api_gateway.services.scrapers.browser_pool import BrowserPool
    from api_gateway.services.scrapers.scraper_factory import ScraperFactory
    from api_gateway.services.shopping_list_processor import ShoppingListProcessor
    from api_gateway.services.vpn_manager import VPNManager
    HAS_APP_IMPORTS = True
except ImportError as e:
    HAS_APP_IMPORTS = False
    IMPORT_ERROR = str(e)


# Test configuration
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ai_gateway:ai_gateway@localhost:5432/ai_gateway_test"
)
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")
TEST_REDIS_DB = 15  # Use separate database for tests


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def integration_test_config():
    """Configuration for integration tests."""
    return {
        "database_url": TEST_DATABASE_URL,
        "redis_url": TEST_REDIS_URL,
        "redis_db": TEST_REDIS_DB,
        "browser_pool_size": 2,
        "scraper_timeout": 30,
        "cache_ttl_seconds": 300,
        "vpn_enabled": os.getenv("VPN_ENABLED", "false").lower() == "true",
        "llm_enabled": os.getenv("LLM_ENABLED", "true").lower() == "true",
        "ollama_endpoint": os.getenv("OLLAMA_API_ENDPOINT", "http://localhost:11434"),
        "test_zip_code": "20024",
        "rate_limit_delay": 0.5,  # Faster for tests
    }


# ============================================================================
# DATABASE FIXTURES
# ============================================================================

@pytest_asyncio.fixture(scope="session")
async def test_db_engine(integration_test_config):
    """Create async database engine for tests."""
    if not HAS_APP_IMPORTS:
        pytest.skip(f"App imports not available: {IMPORT_ERROR}")

    engine = create_async_engine(
        integration_test_config["database_url"],
        echo=False,
        pool_size=5,
        max_overflow=10,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture
async def test_db_session(test_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create database session with automatic rollback after each test."""
    async_session = async_sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        async with session.begin():
            yield session
            # Rollback to clean up test data
            await session.rollback()


@pytest_asyncio.fixture
async def clean_db_session(test_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create database session that commits (for tests that need persistence)."""
    async_session = async_sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.commit()


# ============================================================================
# REDIS FIXTURES
# ============================================================================

@pytest_asyncio.fixture(scope="session")
async def test_redis_client(integration_test_config):
    """Create Redis client for test database."""
    try:
        import redis.asyncio as redis

        client = redis.from_url(
            integration_test_config["redis_url"],
            db=integration_test_config["redis_db"],
            decode_responses=True,
        )

        # Test connection
        await client.ping()

        yield client

        # Cleanup: flush test database
        await client.flushdb()
        await client.close()
    except Exception as e:
        pytest.skip(f"Redis not available: {e}")


@pytest_asyncio.fixture
async def clean_redis(test_redis_client):
    """Ensure Redis is clean before each test."""
    await test_redis_client.flushdb()
    yield test_redis_client
    await test_redis_client.flushdb()


# ============================================================================
# BROWSER POOL FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def test_browser_pool(integration_test_config):
    """Create browser pool for scraping tests."""
    if not HAS_APP_IMPORTS:
        pytest.skip(f"App imports not available: {IMPORT_ERROR}")

    pool = BrowserPool(
        max_browsers=integration_test_config["browser_pool_size"],
        headless=True,
    )

    try:
        await pool.initialize()
        yield pool
    finally:
        await pool.cleanup()


@pytest_asyncio.fixture
async def mock_browser_pool():
    """Mock browser pool for tests that don't need real browsers."""
    pool = MagicMock()
    pool.acquire_context = AsyncMock()
    pool.release_context = AsyncMock()
    pool.cleanup = AsyncMock()

    # Create mock browser context
    mock_context = MagicMock()
    mock_page = MagicMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    mock_page.query_selector_all = AsyncMock(return_value=[])
    mock_page.close = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.close = AsyncMock()

    pool.acquire_context.return_value = mock_context

    yield pool


# ============================================================================
# VPN FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def test_vpn_manager(integration_test_config):
    """Create VPN manager for rotation tests."""
    if not HAS_APP_IMPORTS:
        pytest.skip(f"App imports not available: {IMPORT_ERROR}")

    if not integration_test_config["vpn_enabled"]:
        pytest.skip("VPN not enabled for tests")

    vpn = VPNManager(
        rotation_frequency=2,  # Rotate every 2 requests for testing
        fallback_enabled=True,
        circuit_breaker_threshold=3,
    )

    yield vpn

    await vpn.disconnect()


@pytest_asyncio.fixture
async def mock_vpn_manager():
    """Mock VPN manager for tests that don't need real VPN."""
    vpn = MagicMock()
    vpn.connect = AsyncMock(return_value=True)
    vpn.disconnect = AsyncMock()
    vpn.rotate = AsyncMock(return_value=True)
    vpn.get_current_ip = AsyncMock(return_value="192.168.1.1")
    vpn.is_connected = MagicMock(return_value=True)
    vpn.request_count = 0

    yield vpn


# ============================================================================
# CACHE FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def test_cache_manager(test_redis_client, test_db_session, integration_test_config):
    """Create cache manager with real Redis and database."""
    if not HAS_APP_IMPORTS:
        pytest.skip(f"App imports not available: {IMPORT_ERROR}")

    cache = CacheManager(
        redis_client=test_redis_client,
        db_session=test_db_session,
        default_ttl=integration_test_config["cache_ttl_seconds"],
    )

    yield cache


@pytest_asyncio.fixture
async def mock_cache_manager():
    """Mock cache manager for isolated tests."""
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    cache.delete = AsyncMock()
    cache.invalidate_pattern = AsyncMock(return_value=0)
    cache.get_stats = AsyncMock(return_value={"hits": 0, "misses": 0})

    yield cache


# ============================================================================
# SCRAPER FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def test_scraper_factory(test_browser_pool, mock_vpn_manager, integration_test_config):
    """Create scraper factory with real browser pool."""
    if not HAS_APP_IMPORTS:
        pytest.skip(f"App imports not available: {IMPORT_ERROR}")

    factory = ScraperFactory(
        browser_pool=test_browser_pool,
        vpn_manager=mock_vpn_manager,
        rate_limit_delay=integration_test_config["rate_limit_delay"],
        test_mode=True,
    )

    yield factory


@pytest_asyncio.fixture
async def mock_scraper():
    """Mock scraper for isolated tests."""
    scraper = MagicMock()
    scraper.scrape = AsyncMock(return_value=[
        {
            "name": "Organic Milk 1 Gallon",
            "price": 5.99,
            "unit_price": "5.99/gal",
            "size": "1 gallon",
            "brand": "Organic Valley",
            "in_stock": True,
            "url": "https://example.com/milk",
            "image_url": "https://example.com/milk.jpg",
        },
        {
            "name": "Whole Milk 1 Gallon",
            "price": 4.29,
            "unit_price": "4.29/gal",
            "size": "1 gallon",
            "brand": "Store Brand",
            "in_stock": True,
            "url": "https://example.com/milk2",
            "image_url": "https://example.com/milk2.jpg",
        },
    ])
    scraper.service_name = "instacart"
    scraper.close = AsyncMock()

    yield scraper


# ============================================================================
# COMPARISON MANAGER FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def test_comparison_manager(
    test_db_session,
    test_cache_manager,
    test_scraper_factory,
    integration_test_config,
):
    """Create comparison manager with real components."""
    if not HAS_APP_IMPORTS:
        pytest.skip(f"App imports not available: {IMPORT_ERROR}")

    manager = ComparisonManager(
        db_session=test_db_session,
        cache_manager=test_cache_manager,
        scraper_factory=test_scraper_factory,
        llm_enabled=integration_test_config["llm_enabled"],
        ollama_endpoint=integration_test_config["ollama_endpoint"],
    )

    yield manager


@pytest_asyncio.fixture
async def mock_comparison_manager():
    """Mock comparison manager for isolated tests."""
    manager = MagicMock()
    manager.search = AsyncMock(return_value={
        "comparison_id": str(uuid.uuid4()),
        "query": "milk",
        "groups": [],
        "services_scraped": ["instacart"],
        "from_cache": False,
    })
    manager.get_comparison = AsyncMock(return_value=None)
    manager.save_selection = AsyncMock()
    manager.delete_selection = AsyncMock()

    yield manager


# ============================================================================
# SHOPPING LIST FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def test_shopping_list_processor(
    test_db_session,
    test_comparison_manager,
    integration_test_config,
):
    """Create shopping list processor with real components."""
    if not HAS_APP_IMPORTS:
        pytest.skip(f"App imports not available: {IMPORT_ERROR}")

    processor = ShoppingListProcessor(
        db_session=test_db_session,
        comparison_manager=test_comparison_manager,
    )

    yield processor


@pytest_asyncio.fixture
async def mock_shopping_list_processor():
    """Mock shopping list processor for isolated tests."""
    processor = MagicMock()

    async def mock_process(items, **kwargs):
        for i, item in enumerate(items):
            yield {
                "status": "processing",
                "current_item": item,
                "completed": i,
                "total": len(items),
                "percentage": ((i + 1) / len(items)) * 100,
            }
        yield {
            "status": "completed",
            "items_processed": len(items),
            "items_failed": 0,
            "service_totals": {"instacart": 25.99, "safeway": 23.49},
            "cheapest_service": "safeway",
        }

    processor.process_list = mock_process

    yield processor


# ============================================================================
# PRODUCT MATCHER FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def test_product_matcher(integration_test_config):
    """Create product matcher with real LLM connection."""
    if not HAS_APP_IMPORTS:
        pytest.skip(f"App imports not available: {IMPORT_ERROR}")

    if not integration_test_config["llm_enabled"]:
        pytest.skip("LLM not enabled for tests")

    matcher = ProductMatcher(
        ollama_endpoint=integration_test_config["ollama_endpoint"],
    )

    yield matcher


@pytest_asyncio.fixture
async def mock_product_matcher():
    """Mock product matcher for tests without LLM."""
    matcher = MagicMock()
    matcher.extract_attributes = AsyncMock(return_value={
        "brand": "Organic Valley",
        "size": "1 gallon",
        "size_oz": 128,
        "organic": True,
        "product_type": "milk",
        "confidence": 0.95,
    })
    matcher.calculate_similarity = AsyncMock(return_value=0.85)
    matcher.group_products = AsyncMock(return_value=[
        {
            "group_name": "Organic Milk",
            "products": [],
            "reasoning": "Similar organic milk products",
        }
    ])

    yield matcher


# ============================================================================
# TEST DATA FACTORIES
# ============================================================================

@pytest.fixture
def product_factory():
    """Factory for creating test products."""
    def create_product(
        name: str = "Test Product",
        price: float = 5.99,
        service: str = "instacart",
        **kwargs
    ) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "name": name,
            "price": price,
            "unit_price": f"{price}/unit",
            "size": kwargs.get("size", "1 unit"),
            "brand": kwargs.get("brand", "Test Brand"),
            "service": service,
            "in_stock": kwargs.get("in_stock", True),
            "url": kwargs.get("url", f"https://example.com/{name.lower().replace(' ', '-')}"),
            "image_url": kwargs.get("image_url", "https://example.com/image.jpg"),
            "scraped_at": datetime.utcnow().isoformat(),
        }

    return create_product


@pytest.fixture
def comparison_factory(product_factory):
    """Factory for creating test comparisons."""
    def create_comparison(
        query: str = "test product",
        zip_code: str = "20024",
        services: list[str] = None,
        products_per_service: int = 2,
        **kwargs
    ) -> dict:
        services = services or ["instacart", "amazon_fresh", "safeway"]
        products = []

        for service in services:
            for i in range(products_per_service):
                products.append(product_factory(
                    name=f"{query.title()} {i + 1}",
                    price=4.99 + (i * 0.50),
                    service=service,
                ))

        return {
            "id": str(uuid.uuid4()),
            "query": query,
            "zip_code": zip_code,
            "products": products,
            "services_scraped": services,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
            "from_cache": False,
            **kwargs,
        }

    return create_comparison


@pytest.fixture
def shopping_list_factory():
    """Factory for creating test shopping lists."""
    def create_shopping_list(
        items: list[str] = None,
        list_name: str = "Test Shopping List",
        **kwargs
    ) -> dict:
        items = items or ["milk", "bread", "eggs", "butter", "cheese"]

        return {
            "id": str(uuid.uuid4()),
            "name": list_name,
            "items": [{"query": item, "quantity": 1} for item in items],
            "created_at": datetime.utcnow().isoformat(),
            "status": "pending",
            **kwargs,
        }

    return create_shopping_list


# ============================================================================
# CLEANUP UTILITIES
# ============================================================================

@pytest_asyncio.fixture
async def cleanup_products(test_db_session):
    """Clean up products after test."""
    product_ids = []

    yield product_ids

    if product_ids:
        for product_id in product_ids:
            await test_db_session.execute(
                text("DELETE FROM products WHERE id = :id"),
                {"id": product_id}
            )


@pytest_asyncio.fixture
async def cleanup_comparisons(test_db_session):
    """Clean up comparisons after test."""
    comparison_ids = []

    yield comparison_ids

    if comparison_ids:
        for comparison_id in comparison_ids:
            await test_db_session.execute(
                text("DELETE FROM comparisons WHERE id = :id"),
                {"id": comparison_id}
            )


# ============================================================================
# API CLIENT FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def mock_api_client():
    """Mock API client for testing API response flows."""

    class MockAPIClient:
        def __init__(self):
            self.headers = {"X-API-Key": "test-api-key"}
            self._mock_data = {}

        async def get(self, path: str, **kwargs) -> dict:
            """Perform mock GET request."""
            # Default responses based on path patterns
            if "/health" in path:
                return {
                    "status_code": 200,
                    "data": {"status": "healthy"},
                    "headers": {"X-API-Version": "1.0.0"},
                }
            elif "/results/" in path:
                # Extract comparison_id from path
                comparison_id = path.split("/")[-1]
                if comparison_id in self._mock_data:
                    return {
                        "status_code": 200,
                        "data": self._mock_data[comparison_id],
                        "headers": {},
                    }
                return {
                    "status_code": 404,
                    "error": {"code": "NOT_FOUND", "message": "Comparison not found"},
                    "headers": {},
                }
            return {
                "status_code": 200,
                "data": {},
                "headers": {},
            }

        async def post(self, path: str, json: dict = None, **kwargs) -> dict:
            """Perform mock POST request."""
            # Validate required fields for search
            if "/search" in path:
                if not json or "query" not in json:
                    return {
                        "status_code": 400,
                        "error": {
                            "code": "VALIDATION_ERROR",
                            "message": "Missing required field: query",
                        },
                        "headers": {},
                    }
                if "zip_code" in json:
                    zip_code = json["zip_code"]
                    if not zip_code.isdigit() or len(zip_code) != 5:
                        return {
                            "status_code": 400,
                            "error": {
                                "code": "VALIDATION_ERROR",
                                "message": "Invalid zip code format",
                            },
                            "headers": {},
                        }

                comparison_id = str(uuid.uuid4())
                result = {
                    "comparison_id": comparison_id,
                    "query": json.get("query"),
                    "zip_code": json.get("zip_code", "20024"),
                    "products": [
                        {
                            "name": f"Product from {service}",
                            "price": 5.99,
                            "service": service,
                        }
                        for service in json.get("services", ["instacart", "safeway"])
                    ],
                }
                self._mock_data[comparison_id] = result
                return {
                    "status_code": 200,
                    "data": result,
                    "headers": {"X-API-Version": "1.0.0"},
                }

            elif "/shopping-list" in path:
                if not json or "items" not in json:
                    return {
                        "status_code": 400,
                        "error": {
                            "code": "VALIDATION_ERROR",
                            "message": "Missing required field: items",
                        },
                        "headers": {},
                    }
                return {
                    "status_code": 202,
                    "data": {
                        "list_id": str(uuid.uuid4()),
                        "items": json.get("items"),
                        "status": "processing",
                    },
                    "headers": {},
                }

            return {
                "status_code": 200,
                "data": {},
                "headers": {},
            }

    yield MockAPIClient()


# ============================================================================
# LLM SERVICE FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def mock_llm_service():
    """Mock LLM service for testing LLM integration."""

    class MockLLMService:
        def __init__(self):
            self.model = "llama3.2"
            self.temperature = 0.3
            self.max_tokens = 1024
            self.timeout = 30.0

        async def group_products(self, products: list[dict]) -> list[dict]:
            """Group products by similarity."""
            # Simple grouping by first word of product name
            groups = {}
            for product in products:
                name = product.get("name", "")
                # Check for plant-based vs dairy
                if any(kw in name.lower() for kw in ["almond", "oat", "soy", "coconut"]):
                    key = "Plant-Based"
                else:
                    # Use first significant word
                    words = name.split()
                    key = words[0] if words else "Other"
                    # Normalize common product types
                    if any(kw in name.lower() for kw in ["milk", "2%", "whole"]):
                        key = "Dairy Milk"

                if key not in groups:
                    groups[key] = {
                        "group_name": key,
                        "products": [],
                        "best_value": None,
                    }
                groups[key]["products"].append(product)

            # Identify best value in each group
            result = []
            for group in groups.values():
                if group["products"]:
                    best = min(group["products"], key=lambda p: p.get("price", float("inf")))
                    group["best_value"] = best
                result.append(group)

            return result

        async def analyze_products(self, products: list[dict]) -> dict:
            """Analyze products and identify best value."""
            if not products:
                return {"products": [], "best_value": None}

            best_value = min(products, key=lambda p: p.get("price", float("inf")))
            return {
                "products": products,
                "best_value": best_value,
                "price_range": {
                    "min": min(p.get("price", 0) for p in products),
                    "max": max(p.get("price", 0) for p in products),
                },
            }

        async def get_insights(self, products: list[dict]) -> dict:
            """Get insights about products."""
            insights = []
            if len(products) >= 2:
                prices = [p.get("price", 0) for p in products]
                price_diff = max(prices) - min(prices)
                if price_diff > 0:
                    pct_diff = (price_diff / min(prices)) * 100
                    insights.append(
                        f"Price varies by {pct_diff:.0f}% across products"
                    )
            return {"insights": insights}

    yield MockLLMService()


# ============================================================================
# HELPER FIXTURES
# ============================================================================

@pytest.fixture
def assert_eventually():
    """Helper for asserting conditions that may take time."""
    async def _assert_eventually(
        condition_fn,
        timeout: float = 10.0,
        interval: float = 0.5,
        message: str = "Condition not met within timeout",
    ):
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                result = await condition_fn() if asyncio.iscoroutinefunction(condition_fn) else condition_fn()
                if result:
                    return result
            except Exception:
                pass
            await asyncio.sleep(interval)
        raise AssertionError(message)

    return _assert_eventually


@pytest.fixture
def measure_time():
    """Helper for measuring execution time."""
    class TimeMeasurer:
        def __init__(self):
            self.start_time = None
            self.end_time = None

        def __enter__(self):
            self.start_time = asyncio.get_event_loop().time()
            return self

        def __exit__(self, *args):
            self.end_time = asyncio.get_event_loop().time()

        @property
        def elapsed(self) -> float:
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return 0.0

    return TimeMeasurer
