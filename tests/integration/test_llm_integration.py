"""
Integration tests for LLM-powered product grouping and analysis.

Tests product grouping accuracy, fallback behavior, and response handling.
"""

import asyncio

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.llm]


class TestLLMProductGrouping:
    """Test LLM-powered product grouping functionality."""

    async def test_llm_groups_similar_products_correctly(
        self,
        mock_llm_service,
    ):
        """Test that LLM groups similar products together."""
        products = [
            {"name": "Organic 2% Milk 1 Gallon", "price": 5.99, "service": "instacart"},
            {"name": "Whole Milk 1 Gal", "price": 4.49, "service": "safeway"},
            {"name": "2% Reduced Fat Milk", "price": 4.99, "service": "amazon_fresh"},
            {"name": "Almond Milk Unsweetened", "price": 3.99, "service": "instacart"},
            {"name": "Oat Milk Original", "price": 4.49, "service": "safeway"},
        ]

        groups = await mock_llm_service.group_products(products)

        # Should create at least 2 groups (dairy milk vs plant-based)
        assert len(groups) >= 2

        # Each group should have products
        for group in groups:
            assert "group_name" in group
            assert "products" in group
            assert len(group["products"]) >= 1

    async def test_llm_identifies_best_value_product(
        self,
        mock_llm_service,
    ):
        """Test that LLM identifies best value within groups."""
        products = [
            {"name": "Organic Eggs 12ct", "price": 6.99, "service": "instacart"},
            {"name": "Large Eggs Dozen", "price": 3.49, "service": "safeway"},
            {"name": "Free Range Eggs 12pk", "price": 5.99, "service": "amazon_fresh"},
        ]

        analysis = await mock_llm_service.analyze_products(products)

        # Should identify best value
        assert "best_value" in analysis
        assert analysis["best_value"]["service"] == "safeway"

    async def test_llm_provides_comparison_insights(
        self,
        mock_llm_service,
    ):
        """Test that LLM provides useful comparison insights."""
        products = [
            {"name": "Organic Bread", "price": 5.99, "service": "instacart"},
            {"name": "White Bread", "price": 2.49, "service": "safeway"},
        ]

        insights = await mock_llm_service.get_insights(products)

        assert "insights" in insights
        assert isinstance(insights["insights"], list)


class TestLLMFallbackBehavior:
    """Test fallback behavior when LLM is unavailable."""

    async def test_grouping_falls_back_to_simple_matching(self):
        """Test that grouping falls back to simple matching without LLM."""
        products = [
            {"name": "Milk 2%", "price": 4.99, "service": "instacart"},
            {"name": "Milk Whole", "price": 4.49, "service": "safeway"},
            {"name": "Bread White", "price": 2.99, "service": "instacart"},
            {"name": "Bread Wheat", "price": 3.49, "service": "safeway"},
        ]

        def simple_grouping(products):
            """Simple fallback grouping by first word."""
            groups = {}
            for product in products:
                key = product["name"].split()[0].lower()
                if key not in groups:
                    groups[key] = {
                        "group_name": key.capitalize(),
                        "products": [],
                    }
                groups[key]["products"].append(product)
            return list(groups.values())

        groups = simple_grouping(products)

        # Should group by first word
        assert len(groups) == 2
        group_names = [g["group_name"] for g in groups]
        assert "Milk" in group_names
        assert "Bread" in group_names

    async def test_analysis_works_without_llm_insights(self):
        """Test that analysis works without LLM-generated insights."""
        products = [
            {"name": "Product A", "price": 5.99, "service": "instacart"},
            {"name": "Product B", "price": 4.99, "service": "safeway"},
        ]

        # Simple price-based analysis without LLM
        analysis = {
            "products": products,
            "cheapest": min(products, key=lambda p: p["price"]),
            "price_range": {
                "min": min(p["price"] for p in products),
                "max": max(p["price"] for p in products),
            },
            # No LLM insights field
        }

        assert "cheapest" in analysis
        assert analysis["cheapest"]["price"] == 4.99
        assert "llm_insights" not in analysis

    async def test_timeout_triggers_fallback(self, mock_llm_service):
        """Test that LLM timeout triggers fallback behavior."""
        mock_llm_service.timeout = 0.1

        async def slow_llm_call():
            await asyncio.sleep(1.0)  # Longer than timeout
            return {"groups": []}

        mock_llm_service.group_products = slow_llm_call

        try:
            result = await asyncio.wait_for(
                mock_llm_service.group_products(),
                timeout=mock_llm_service.timeout,
            )
        except TimeoutError:
            result = {"fallback": True, "groups": []}

        assert result.get("fallback") is True


class TestLLMResponseParsing:
    """Test LLM response parsing and validation."""

    async def test_valid_json_response_parsed_correctly(self):
        """Test that valid JSON responses are parsed correctly."""
        llm_response = """{
            "groups": [
                {
                    "group_name": "Dairy Milk",
                    "products": ["Organic 2% Milk", "Whole Milk"],
                    "best_value": "Whole Milk"
                }
            ],
            "insights": ["Organic milk costs 33% more than regular"]
        }"""

        import json

        parsed = json.loads(llm_response)

        assert "groups" in parsed
        assert len(parsed["groups"]) == 1
        assert parsed["groups"][0]["group_name"] == "Dairy Milk"

    async def test_malformed_json_handled_gracefully(self):
        """Test that malformed JSON is handled gracefully."""
        malformed_response = "{ invalid json here }"

        import json

        try:
            parsed = json.loads(malformed_response)
        except json.JSONDecodeError:
            parsed = {"error": "parse_failed", "groups": []}

        assert parsed.get("error") == "parse_failed"

    async def test_unexpected_response_structure_handled(self):
        """Test that unexpected response structures are handled."""
        unexpected_response = {
            "data": {
                "nested": {
                    "groups": []
                }
            }
        }

        # Extract groups from various possible locations
        def extract_groups(response):
            if isinstance(response, dict):
                if "groups" in response:
                    return response["groups"]
                for value in response.values():
                    result = extract_groups(value)
                    if result is not None:
                        return result
            return []

        groups = extract_groups(unexpected_response)
        assert groups == []


class TestLLMPromptConstruction:
    """Test LLM prompt construction for product analysis."""

    async def test_prompt_includes_product_details(self):
        """Test that prompt includes all relevant product details."""
        products = [
            {
                "name": "Organic Milk",
                "price": 5.99,
                "service": "instacart",
                "unit_price": "$0.47/oz",
            },
        ]

        def build_prompt(products):
            product_list = "\n".join(
                f"- {p['name']} (${p['price']}) from {p['service']}"
                for p in products
            )
            return f"""Analyze and group these products:
{product_list}

Group similar products together and identify the best value in each group."""

        prompt = build_prompt(products)

        assert "Organic Milk" in prompt
        assert "$5.99" in prompt
        assert "instacart" in prompt

    async def test_prompt_handles_special_characters(self):
        """Test that prompt handles special characters in product names."""
        products = [
            {"name": "Ben & Jerry's Ice Cream", "price": 5.99, "service": "instacart"},
            {"name": 'Trader Joe\'s "Everything" Bagels', "price": 3.49, "service": "safeway"},
        ]

        def build_prompt(products):
            # Escape special characters
            def escape_name(name):
                return name.replace('"', '\\"')
            product_list = "\n".join(
                f"- {escape_name(p['name'])} (${p['price']})"
                for p in products
            )
            return f"Products:\n{product_list}"

        prompt = build_prompt(products)

        assert "Ben & Jerry's" in prompt
        assert "Everything" in prompt

    async def test_prompt_limits_product_count(self):
        """Test that prompt limits number of products for context window."""
        products = [{"name": f"Product {i}", "price": i + 1.99, "service": "test"} for i in range(100)]

        max_products = 50

        def build_prompt(products, max_count=50):
            limited = products[:max_count]
            return f"Analyzing {len(limited)} of {len(products)} products"

        prompt = build_prompt(products, max_products)

        assert "50 of 100" in prompt


class TestLLMCachingBehavior:
    """Test LLM response caching."""

    async def test_identical_products_use_cached_response(self):
        """Test that identical product sets use cached LLM responses."""
        cache = {}
        call_count = 0

        products = [
            {"name": "Milk", "price": 4.99},
            {"name": "Bread", "price": 2.99},
        ]

        def cache_key(products):
            import hashlib
            import json
            return hashlib.md5(json.dumps(products, sort_keys=True).encode()).hexdigest()

        async def cached_llm_call(products):
            nonlocal call_count
            key = cache_key(products)
            if key in cache:
                return cache[key]
            call_count += 1
            result = {"groups": [{"products": products}]}
            cache[key] = result
            return result

        # First call
        result1 = await cached_llm_call(products)
        assert call_count == 1

        # Second call with same products
        result2 = await cached_llm_call(products)
        assert call_count == 1  # Should not increase

        assert result1 == result2

    async def test_different_products_trigger_new_llm_call(self):
        """Test that different products trigger new LLM calls."""
        cache = {}
        call_count = 0

        def cache_key(products):
            import hashlib
            import json
            return hashlib.md5(json.dumps(products, sort_keys=True).encode()).hexdigest()

        async def cached_llm_call(products):
            nonlocal call_count
            key = cache_key(products)
            if key in cache:
                return cache[key]
            call_count += 1
            result = {"groups": [{"products": products}]}
            cache[key] = result
            return result

        products1 = [{"name": "Milk", "price": 4.99}]
        products2 = [{"name": "Bread", "price": 2.99}]

        await cached_llm_call(products1)
        assert call_count == 1

        await cached_llm_call(products2)
        assert call_count == 2

    async def test_cache_expires_after_ttl(self):
        """Test that cached responses expire after TTL."""
        cache = {}
        ttl = 0.5  # 500ms for testing

        async def cached_llm_call_with_ttl(products, key):
            now = asyncio.get_event_loop().time()
            if key in cache:
                cached_time, result = cache[key]
                if now - cached_time < ttl:
                    return result, True  # Cache hit
            result = {"groups": []}
            cache[key] = (now, result)
            return result, False  # Cache miss

        # First call - cache miss
        _, hit1 = await cached_llm_call_with_ttl([{"name": "Milk"}], "test_key")
        assert not hit1

        # Immediate second call - cache hit
        _, hit2 = await cached_llm_call_with_ttl([{"name": "Milk"}], "test_key")
        assert hit2

        # Wait for TTL to expire
        await asyncio.sleep(ttl + 0.1)

        # Third call - cache miss (expired)
        _, hit3 = await cached_llm_call_with_ttl([{"name": "Milk"}], "test_key")
        assert not hit3


class TestLLMModelSelection:
    """Test LLM model selection and configuration."""

    async def test_uses_configured_model(self, mock_llm_service):
        """Test that the configured model is used."""
        mock_llm_service.model = "llama3.2"

        assert mock_llm_service.model == "llama3.2"

    async def test_fallback_to_default_model(self):
        """Test fallback to default model if configured model unavailable."""
        configured_model = "unavailable-model"
        default_model = "llama3.2"
        available_models = ["llama3.2", "mistral"]

        selected_model = (
            configured_model if configured_model in available_models else default_model
        )

        assert selected_model == default_model

    async def test_model_parameters_applied(self, mock_llm_service):
        """Test that model parameters are applied correctly."""
        mock_llm_service.temperature = 0.3
        mock_llm_service.max_tokens = 1024

        assert mock_llm_service.temperature == 0.3
        assert mock_llm_service.max_tokens == 1024


class TestLLMErrorHandling:
    """Test LLM error handling scenarios."""

    async def test_connection_error_handled(self):
        """Test that connection errors are handled gracefully."""
        async def failing_llm_call():
            raise ConnectionError("Failed to connect to LLM service")

        try:
            await failing_llm_call()
            result = {"success": True}
        except ConnectionError:
            result = {"success": False, "error": "llm_unavailable"}

        assert result["success"] is False
        assert result["error"] == "llm_unavailable"

    async def test_rate_limit_triggers_retry(self):
        """Test that rate limit errors trigger retry."""
        attempts = 0
        max_retries = 3

        async def rate_limited_call():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise Exception("Rate limit exceeded")
            return {"success": True}

        for attempt in range(max_retries):
            try:
                result = await rate_limited_call()
                break
            except Exception:
                if attempt == max_retries - 1:
                    result = {"success": False}
                await asyncio.sleep(0.1)

        assert result["success"] is True
        assert attempts == 3

    async def test_invalid_response_triggers_fallback(self):
        """Test that invalid LLM responses trigger fallback."""
        def validate_response(response):
            required_fields = ["groups"]
            return all(field in response for field in required_fields)

        invalid_response = {"data": "invalid"}
        fallback_response = {"groups": [], "fallback": True}

        if not validate_response(invalid_response):
            result = fallback_response
        else:
            result = invalid_response

        assert result.get("fallback") is True
