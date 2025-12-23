"""
Unit tests for the Product Matcher service.

Tests LLM-powered product attribute extraction, similarity calculation,
and product grouping logic.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_gateway.services.product_matcher import (
    ProductAttributes,
    _normalize_size_to_oz,
    _parse_price,
    calculate_similarity,
    compare_products,
    extract_product_attributes,
    group_similar_products,
)

# --- Helper Functions Tests ---


class TestParsePrice:
    """Tests for the _parse_price helper function."""

    def test_standard_price(self):
        """Test parsing standard price format."""
        assert _parse_price("$3.99") == 3.99
        assert _parse_price("$12.50") == 12.50
        assert _parse_price("$0.99") == 0.99

    def test_price_without_dollar_sign(self):
        """Test parsing price without dollar sign."""
        assert _parse_price("3.99") == 3.99
        assert _parse_price("12.50") == 12.50

    def test_multi_buy_price(self):
        """Test parsing 'X for $Y' format."""
        assert _parse_price("2 for $5") == 2.5
        assert _parse_price("3 for $10") == pytest.approx(3.33, rel=0.01)
        assert _parse_price("4 for $12.00") == 3.0

    def test_invalid_price(self):
        """Test handling of invalid price strings."""
        assert _parse_price("") is None
        assert _parse_price("N/A") is None
        assert _parse_price("Price varies") is None

    def test_none_price(self):
        """Test handling of None input."""
        assert _parse_price(None) is None


class TestNormalizeSizeToOz:
    """Tests for the _normalize_size_to_oz helper function."""

    def test_oz_size(self):
        """Test parsing ounce sizes."""
        assert _normalize_size_to_oz("16 oz") == 16.0
        assert _normalize_size_to_oz("32oz") == 32.0
        assert _normalize_size_to_oz("8.5 oz") == 8.5

    def test_lb_size(self):
        """Test parsing pound sizes."""
        assert _normalize_size_to_oz("1 lb") == 16.0
        assert _normalize_size_to_oz("2 lbs") == 32.0
        assert _normalize_size_to_oz("0.5 lb") == 8.0

    def test_gallon_size(self):
        """Test parsing gallon sizes."""
        assert _normalize_size_to_oz("1 gal") == 128.0
        assert _normalize_size_to_oz("0.5 gallon") == 64.0

    def test_quart_pint_size(self):
        """Test parsing quart and pint sizes."""
        assert _normalize_size_to_oz("1 qt") == 32.0
        assert _normalize_size_to_oz("1 pint") == 16.0

    def test_ml_liter_size(self):
        """Test parsing metric liquid sizes."""
        assert _normalize_size_to_oz("1 l") == pytest.approx(33.814, rel=0.01)
        assert _normalize_size_to_oz("500 ml") == pytest.approx(16.907, rel=0.01)

    def test_invalid_size(self):
        """Test handling of invalid size strings."""
        assert _normalize_size_to_oz("") is None
        assert _normalize_size_to_oz(None) is None


# --- Similarity Calculation Tests ---


class TestCalculateSimilarity:
    """Tests for the calculate_similarity function."""

    def test_identical_products(self):
        """Test similarity of identical products."""
        attr1 = ProductAttributes(
            brand="Brand A",
            size="16 oz",
            size_oz=16.0,
            is_organic=True,
            product_type="milk",
        )
        attr2 = ProductAttributes(
            brand="Brand A",
            size="16 oz",
            size_oz=16.0,
            is_organic=True,
            product_type="milk",
        )
        similarity = calculate_similarity(attr1, attr2)
        assert similarity == 1.0

    def test_completely_different_products(self):
        """Test similarity of completely different products."""
        attr1 = ProductAttributes(
            brand="Brand A",
            size="16 oz",
            size_oz=16.0,
            is_organic=True,
            product_type="milk",
        )
        attr2 = ProductAttributes(
            brand="Brand B",
            size="32 oz",
            size_oz=32.0,
            is_organic=False,
            product_type="bread",
        )
        similarity = calculate_similarity(attr1, attr2)
        # Should be low since product type, organic status, and size all differ
        assert similarity < 0.3

    def test_same_product_different_brands(self):
        """Test similarity of same product type from different brands."""
        attr1 = ProductAttributes(
            brand="Horizon",
            size="64 oz",
            size_oz=64.0,
            is_organic=True,
            product_type="milk",
        )
        attr2 = ProductAttributes(
            brand="Organic Valley",
            size="64 oz",
            size_oz=64.0,
            is_organic=True,
            product_type="milk",
        )
        similarity = calculate_similarity(attr1, attr2)
        # Should be high - same type, size, organic status
        assert similarity >= 0.9

    def test_similar_sizes_within_threshold(self):
        """Test that similar sizes (within 10%) score well."""
        attr1 = ProductAttributes(
            size_oz=16.0,
            product_type="juice",
        )
        attr2 = ProductAttributes(
            size_oz=15.5,  # ~3% smaller
            product_type="juice",
        )
        similarity = calculate_similarity(attr1, attr2)
        # Should score full size points for within 10%
        assert similarity >= 0.6  # product_type + size

    def test_organic_vs_conventional(self):
        """Test that organic and conventional products score differently."""
        attr_organic = ProductAttributes(
            product_type="milk",
            size_oz=64.0,
            is_organic=True,
        )
        attr_conventional = ProductAttributes(
            product_type="milk",
            size_oz=64.0,
            is_organic=False,
        )
        similarity = calculate_similarity(attr_organic, attr_conventional)
        # Should miss the organic match weight (0.2)
        assert similarity == pytest.approx(0.7, abs=0.05)


# --- Product Grouping Tests ---


class TestGroupSimilarProducts:
    """Tests for the group_similar_products function."""

    @pytest.mark.asyncio
    async def test_group_similar_products_basic(self):
        """Test basic product grouping."""
        # Create mock products
        products = []
        for i, (name, service, price, size) in enumerate([
            ("Organic Milk 1 Gallon", "amazon_fresh", "$5.99", "1 gal"),
            ("Organic Whole Milk", "instacart", "$6.49", "128 oz"),
            ("Regular Milk 1 Gallon", "safeway", "$3.99", "1 gal"),
        ]):
            product = MagicMock()
            product.id = f"prod_{i}"
            product.name = name
            product.service = service
            product.price = price
            product.size = size
            product.brand = "Test Brand"
            products.append(product)

        # Mock the attribute extraction to return consistent results
        mock_attrs = [
            ProductAttributes(
                brand="Test Brand",
                size="1 gal",
                size_oz=128.0,
                is_organic=True,
                product_type="milk",
                confidence=0.9,
            ),
            ProductAttributes(
                brand="Test Brand",
                size="128 oz",
                size_oz=128.0,
                is_organic=True,
                product_type="milk",
                confidence=0.9,
            ),
            ProductAttributes(
                brand="Test Brand",
                size="1 gal",
                size_oz=128.0,
                is_organic=False,
                product_type="milk",
                confidence=0.9,
            ),
        ]

        with patch(
            "api_gateway.services.product_matcher.extract_product_attributes",
            side_effect=mock_attrs,
        ):
            groups = await group_similar_products(products, "test-model", similarity_threshold=0.7)

        # Should create groups based on similarity
        assert len(groups) >= 1
        # All products should be assigned to groups
        total_grouped = sum(len(g.products) for g in groups)
        assert total_grouped == 3

    @pytest.mark.asyncio
    async def test_empty_products_list(self):
        """Test grouping with empty products list."""
        groups = await group_similar_products([], "test-model")
        assert groups == []


# --- Main Compare Function Tests ---


class TestCompareProducts:
    """Tests for the main compare_products function."""

    @pytest.mark.asyncio
    async def test_compare_no_products(self):
        """Test comparison with no products."""
        result = await compare_products([], "milk", "20024")

        assert result["groups"] == []
        assert result["llm_analysis"]["best_value_group"] is None
        assert result["model_used"] is None

    @pytest.mark.asyncio
    async def test_compare_with_model_error(self):
        """Test graceful handling when no models available."""
        products = [MagicMock(id="1", name="Test", price="$5.99", size="16 oz", brand="Test")]

        with patch(
            "api_gateway.services.product_matcher.ensure_model_available_async",
            side_effect=RuntimeError("No models available"),
        ):
            result = await compare_products(products, "milk", "20024")

        # Should return ungrouped products with error
        assert "error" in result["llm_analysis"]
        assert result["model_used"] is None


# --- Attribute Extraction Tests ---


class TestExtractProductAttributes:
    """Tests for the extract_product_attributes function."""

    @pytest.mark.asyncio
    async def test_extract_attributes_success(self):
        """Test successful attribute extraction with mocked LLM."""
        product = MagicMock()
        product.name = "Horizon Organic Whole Milk"
        product.price = "$6.99"
        product.size = "64 oz"
        product.brand = "Horizon"

        mock_response = {
            "response": '{"brand": "Horizon", "size": "64 oz", "is_organic": true, "product_type": "milk", "confidence": 0.95}'
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.return_value.json.return_value = mock_response
            mock_instance.post.return_value.raise_for_status = MagicMock()

            attrs = await extract_product_attributes(product, "test-model")

        assert attrs.brand == "Horizon"
        assert attrs.is_organic is True
        assert attrs.product_type == "milk"
        assert attrs.confidence == 0.95

    @pytest.mark.asyncio
    async def test_extract_attributes_fallback(self):
        """Test fallback attribute extraction when LLM fails."""
        product = MagicMock()
        product.name = "Organic Valley Milk"
        product.price = "$5.99"
        product.size = "32 oz"
        product.brand = "Organic Valley"

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.side_effect = Exception("Connection error")

            attrs = await extract_product_attributes(product, "test-model")

        # Should use fallback extraction
        assert attrs.brand == "Organic Valley"
        assert attrs.is_organic is True  # "Organic" is in name
        assert attrs.size_oz == 32.0
        assert attrs.confidence == 0.3  # Lower confidence for fallback

    @pytest.mark.asyncio
    async def test_extract_attributes_json_in_code_block(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        product = MagicMock()
        product.name = "Test Milk"
        product.price = "$4.99"
        product.size = "16 oz"
        product.brand = None

        mock_response = {
            "response": '```json\n{"brand": "Generic", "size": "16 oz", "is_organic": false, "product_type": "milk", "confidence": 0.8}\n```'
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.return_value.json.return_value = mock_response
            mock_instance.post.return_value.raise_for_status = MagicMock()

            attrs = await extract_product_attributes(product, "test-model")

        assert attrs.brand == "Generic"
        assert attrs.product_type == "milk"


# --- Integration Tests ---


class TestIntegration:
    """Integration tests that test multiple components together."""

    @pytest.mark.asyncio
    async def test_full_comparison_pipeline(self):
        """Test the full comparison pipeline with mocked external calls."""
        # Create test products
        products = []
        for i, (name, service, price, size, _is_organic) in enumerate([
            ("Organic Milk", "amazon", "$6.99", "64 oz", True),
            ("Organic Milk", "instacart", "$7.49", "64 oz", True),
            ("Regular Milk", "safeway", "$4.99", "64 oz", False),
        ]):
            product = MagicMock()
            product.id = f"prod_{i}"
            product.name = name
            product.service = service
            product.price = price
            product.size = size
            product.brand = "Test"
            products.append(product)

        # Mock model selection
        with patch(
            "api_gateway.services.product_matcher.ensure_model_available_async",
            return_value="test-model",
        ):
            with patch(
                "api_gateway.services.product_matcher.ensure_model_ready",
                return_value=True,
            ):
                # Mock attribute extraction
                mock_attrs = [
                    ProductAttributes(
                        brand="Test",
                        size_oz=64.0,
                        is_organic=True,
                        product_type="milk",
                        confidence=0.9,
                    ),
                    ProductAttributes(
                        brand="Test",
                        size_oz=64.0,
                        is_organic=True,
                        product_type="milk",
                        confidence=0.9,
                    ),
                    ProductAttributes(
                        brand="Test",
                        size_oz=64.0,
                        is_organic=False,
                        product_type="milk",
                        confidence=0.9,
                    ),
                ]

                with patch(
                    "api_gateway.services.product_matcher.extract_product_attributes",
                    side_effect=mock_attrs,
                ):
                    with patch(
                        "api_gateway.services.product_matcher._generate_comparison_analysis",
                        return_value={
                            "best_value_group": 0,
                            "reasoning": "Test reasoning",
                            "price_insights": ["Test insight"],
                            "recommendations": ["Test recommendation"],
                        },
                    ):
                        result = await compare_products(products, "milk", "20024")

        assert result["model_used"] == "test-model"
        assert len(result["groups"]) >= 1
        assert result["llm_analysis"]["best_value_group"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
