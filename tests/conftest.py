"""
Pytest configuration and fixtures for API Gateway tests.
"""

import asyncio
from unittest.mock import MagicMock

import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_product():
    """Create a mock Product model instance."""

    def _create_product(
        id: str = "test-id",
        name: str = "Test Product",
        service: str = "test_service",
        price: str = "$5.99",
        size: str = "16 oz",
        brand: str = "Test Brand",
        url: str = "https://example.com/product",
        image_url: str = "https://example.com/image.jpg",
        availability: bool = True,
    ):
        product = MagicMock()
        product.id = id
        product.name = name
        product.service = service
        product.price = price
        product.size = size
        product.brand = brand
        product.url = url
        product.image_url = image_url
        product.availability = availability
        return product

    return _create_product


@pytest.fixture
def sample_products(mock_product):
    """Create a sample list of products for testing."""
    return [
        mock_product(
            id="prod_1",
            name="Horizon Organic Whole Milk",
            service="amazon_fresh",
            price="$6.99",
            size="64 oz",
            brand="Horizon",
        ),
        mock_product(
            id="prod_2",
            name="Organic Valley Whole Milk",
            service="instacart",
            price="$7.49",
            size="64 oz",
            brand="Organic Valley",
        ),
        mock_product(
            id="prod_3",
            name="Great Value Whole Milk",
            service="safeway",
            price="$3.99",
            size="1 gal",
            brand="Great Value",
        ),
    ]


@pytest.fixture
def mock_ollama_response():
    """Create a mock Ollama API response."""

    def _create_response(
        response_text: str = '{"brand": "Test", "size": "16 oz", "is_organic": false, "product_type": "milk", "confidence": 0.8}'
    ):
        return {"response": response_text}

    return _create_response
