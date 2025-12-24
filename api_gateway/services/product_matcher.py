"""
Product Matcher Service for LLM-Powered Grocery Comparison.

Uses Ollama LLM to extract product attributes, calculate similarity scores,
and group comparable products across different grocery services.
"""

import asyncio
import json
import re
from dataclasses import dataclass, field

import httpx

from ..config import settings
from ..models.database import Product
from ..utils.logger import get_logger
from .model_selector import ensure_model_available_async

logger = get_logger("api_gateway.services.product_matcher")

# Ollama API endpoint
OLLAMA_ENDPOINT = settings.OLLAMA_API_ENDPOINT


@dataclass
class ProductAttributes:
    """Extracted attributes from a product for comparison."""

    brand: str | None = None
    size: str | None = None
    size_oz: float | None = None  # Normalized size in oz
    unit_price: float | None = None  # Price per oz
    is_organic: bool = False
    product_type: str | None = None
    confidence: float = 0.5


@dataclass
class ProductMatch:
    """Product with extracted attributes and similarity score."""

    product_id: str
    product: Product
    attributes: ProductAttributes
    similarity_score: float = 0.0


@dataclass
class ProductGroup:
    """Group of similar products across services."""

    products: list[ProductMatch] = field(default_factory=list)
    representative_name: str = ""
    reasoning: str = ""


# Track if model has been warmed up this session
# Track which models have been warmed up this session
_warmed_up_models: set[str] = set()
async def ensure_model_ready(model: str, warmup_timeout: float = 300.0) -> bool:
global _warmed_up_models
if model in _warmed_up_models:
return True
...
if await _warmup_model(model, timeout=warmup_timeout):
_warmed_up_models.add(model)
# Track which models have been warmed up this session
# Track which models have been warmed up this session
_warmed_up_models: set[str] = set()

async def _check_ollama_health(timeout: float = 5.0) -> bool:
async def ensure_model_ready(model: str, warmup_timeout: float = 300.0) -> bool:
global _warmed_up_models

if model in _warmed_up_models:
return True
if await _warmup_model(model, timeout=warmup_timeout):
_warmed_up_models.add(model)
return True
def parse_price(price_str: str) -> float | None:
return None

# Backwards-compatible alias for older callers
_parse_price = parse_price
# Track which models have been warmed up this session
_warmed_up_models: set[str] = set()
async def _check_ollama_health(timeout: float = 5.0) -> bool:
"""Check if Ollama API is responsive."""
# Track which models have been warmed up this session
_warmed_up_models: set[str] = set()

async def _check_ollama_health(timeout: float = 5.0) -> bool:
async def ensure_model_ready(model: str, warmup_timeout: float = 300.0) -> bool:
global _warmed_up_models

if model in _warmed_up_models:
return True
if await _warmup_model(model, timeout=warmup_timeout):
_warmed_up_models.add(model)
return True
def parse_price(price_str: str) -> float | None:
return None

# Backwards-compatible alias for older callers
_parse_price = parse_price
# Track which models have been warmed up this session
_warmed_up_models: set[str] = set()
async def _check_ollama_health(timeout: float = 5.0) -> bool:
"""Check if Ollama API is responsive."""
# Track which models have been warmed up this session
_warmed_up_models: set[str] = set()

async def _check_ollama_health(timeout: float = 5.0) -> bool:
async def ensure_model_ready(model: str, warmup_timeout: float = 300.0) -> bool:
global _warmed_up_models

if model in _warmed_up_models:
return True
if await _warmup_model(model, timeout=warmup_timeout):
_warmed_up_models.add(model)
return True
def parse_price(price_str: str) -> float | None:
return None

# Backwards-compatible alias for older callers
_parse_price = parse_price
# Track which models have been warmed up this session
_warmed_up_models: set[str] = set()
async def _check_ollama_health(timeout: float = 5.0) -> bool:
"""Check if Ollama API is responsive."""


async def _check_ollama_health(timeout: float = 5.0) -> bool:
    """Check if Ollama API is responsive."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{OLLAMA_ENDPOINT}/api/tags")
            return response.status_code == 200
    except Exception:
        return False


async def _warmup_model(model: str, timeout: float = 300.0) -> bool:
    """
    Warm up the LLM model by loading it into memory.

    Args:
        model: Model name to warm up
        timeout: Maximum time to wait for model loading

    Returns:
        True if model is ready, False otherwise
    """
    logger.info("Warming up model %s for product matching...", model)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{OLLAMA_ENDPOINT}/api/generate",
                json={
                    "model": model,
                    "prompt": "Reply with just 'ready'",
                    "stream": False,
                    "options": {"num_predict": 10},
                },
            )
            if response.status_code == 200:
                logger.info("Model %s is ready for product matching", model)
                return True
            else:
                logger.error("Model warmup failed: %s", response.text)
                return False
    except httpx.TimeoutException:
        logger.error("Model warmup timed out after %.0fs", timeout)
        return False
    except Exception as e:
        logger.error("Model warmup error: %s", e)
        return False


async def ensure_model_ready(model: str, warmup_timeout: float = 300.0) -> bool:
    """
    Ensure the LLM model is loaded and ready.

    Only warms up once per session to avoid repeated delays.

    Returns:
        True if model is ready, False otherwise
    """
    global _model_warmed_up

    if _model_warmed_up:
        return True

    if not await _check_ollama_health():
        logger.error("Ollama is not running at %s", OLLAMA_ENDPOINT)
        return False

    if await _warmup_model(model, timeout=warmup_timeout):
        _model_warmed_up = True
        return True

    return False


def _parse_price(price_str: str) -> float | None:
    """Extract numeric price from price string like '$3.99' or '2 for $5'."""
    if not price_str:
        return None

    # Handle "X for $Y" format
    match = re.search(r"(\d+)\s*for\s*\$?([\d.]+)", price_str, re.IGNORECASE)
    if match:
        count = int(match.group(1))
        total = float(match.group(2))
        return total / count if count > 0 else None

    # Handle standard "$X.XX" format
    match = re.search(r"\$?([\d.]+)", price_str)
    if match:
        return float(match.group(1))

    return None


def _normalize_size_to_oz(size_str: str) -> float | None:
    """
    Convert size string to ounces for comparison.

    Handles: oz, lb, gal, qt, pt, ml, l, count
    """
    if not size_str:
        return None

    size_lower = size_str.lower().strip()

    # Extract number and unit
    match = re.search(r"([\d.]+)\s*([a-zA-Z]+)", size_lower)
    if not match:
        # Try just number (assume oz)
        match = re.search(r"([\d.]+)", size_lower)
        if match:
            return float(match.group(1))
        return None

    value = float(match.group(1))
    unit = match.group(2).lower()

    # Conversion factors to oz
    conversions = {
        "oz": 1.0,
        "fl oz": 1.0,
        "floz": 1.0,
        "lb": 16.0,
        "lbs": 16.0,
        "pound": 16.0,
        "pounds": 16.0,
        "gal": 128.0,
        "gallon": 128.0,
        "gallons": 128.0,
        "qt": 32.0,
        "quart": 32.0,
        "quarts": 32.0,
        "pt": 16.0,
        "pint": 16.0,
        "pints": 16.0,
        "ml": 0.033814,
        "l": 33.814,
        "liter": 33.814,
        "liters": 33.814,
        "g": 0.035274,
        "gram": 0.035274,
        "grams": 0.035274,
        "kg": 35.274,
        "ct": 1.0,  # Count - treat as 1 oz per item
        "count": 1.0,
        "pack": 1.0,
        "pk": 1.0,
    }

    return value * conversions.get(unit, 1.0)


async def extract_product_attributes(
    product: Product,
    model: str,
    timeout: float = 60.0,
) -> ProductAttributes:
    """
    Extract structured attributes from a product using LLM.

    Args:
        product: Product model instance
        model: Ollama model name to use
        timeout: Request timeout in seconds

    Returns:
        ProductAttributes with extracted data
    """
    # Build prompt for attribute extraction
    prompt = f"""Extract product attributes from this grocery item.

PRODUCT:
Name: {product.name}
Price: {product.price}
Size: {product.size or 'Not specified'}
Brand: {product.brand or 'Not specified'}

INSTRUCTIONS:
1. Identify the brand (extract from name if not specified)
2. Determine the size with unit
3. Check if the product is organic (look for "organic" in name)
4. Classify the product type (e.g., "milk", "eggs", "bread", "chicken", "cereal")
5. Rate your confidence in these extractions (0.0-1.0)

Respond ONLY with valid JSON in this exact format:
{{"brand": "Brand Name", "size": "16 oz", "is_organic": false, "product_type": "milk", "confidence": 0.85}}

JSON response:"""

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{OLLAMA_ENDPOINT}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,  # Low temperature for consistent extraction
                        "num_predict": 200,
                    },
                },
            )
            response.raise_for_status()

            result = response.json()
            text = result.get("response", "").strip()

            # Parse JSON from response (handle markdown code blocks)
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            data = json.loads(text)

            # Calculate normalized size and unit price
            size_str = data.get("size") or product.size
            size_oz = _normalize_size_to_oz(size_str) if size_str else None
            price_value = _parse_price(product.price)
            unit_price = (price_value / size_oz) if (price_value and size_oz) else None

            return ProductAttributes(
                brand=data.get("brand") or product.brand,
                size=size_str,
                size_oz=size_oz,
                unit_price=unit_price,
                is_organic=data.get("is_organic", False),
                product_type=data.get("product_type"),
                confidence=float(data.get("confidence", 0.5)),
            )

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse attribute JSON: %s", e)
    except httpx.HTTPError as e:
        logger.error("Ollama request failed: %s", e)
    except TimeoutError:
        logger.error("Attribute extraction timed out")
    except Exception as e:
        logger.error("Attribute extraction failed: %s", e)

    # Fallback: extract basic attributes without LLM
    size_oz = _normalize_size_to_oz(product.size) if product.size else None
    price_value = _parse_price(product.price)
    is_organic = "organic" in product.name.lower() if product.name else False

    return ProductAttributes(
        brand=product.brand,
        size=product.size,
        size_oz=size_oz,
        unit_price=(price_value / size_oz) if (price_value and size_oz) else None,
        is_organic=is_organic,
        product_type=None,
        confidence=0.3,  # Lower confidence for fallback
    )


def calculate_similarity(attr1: ProductAttributes, attr2: ProductAttributes) -> float:
    """
    Calculate similarity score between two products.

    Weights: product_type (0.4), size (0.3), organic (0.2), brand (0.1)

    Returns:
        Similarity score from 0.0 to 1.0
    """
    score = 0.0

    # Product type match (0.4 weight)
    if attr1.product_type and attr2.product_type:
        if attr1.product_type.lower() == attr2.product_type.lower():
            score += 0.4
        elif (
            attr1.product_type.lower() in attr2.product_type.lower()
            or attr2.product_type.lower() in attr1.product_type.lower()
        ):
            score += 0.2  # Partial match

    # Size similarity (0.3 weight) - within 20% difference
    if attr1.size_oz and attr2.size_oz:
        size_diff = abs(attr1.size_oz - attr2.size_oz) / max(attr1.size_oz, attr2.size_oz)
        if size_diff <= 0.1:  # Within 10%
            score += 0.3
        elif size_diff <= 0.2:  # Within 20%
            score += 0.2
        elif size_diff <= 0.3:  # Within 30%
            score += 0.1

    # Organic match (0.2 weight)
    if attr1.is_organic == attr2.is_organic:
        score += 0.2

    # Brand similarity (0.1 weight)
    if attr1.brand and attr2.brand:
        brand1 = attr1.brand.lower().strip()
        brand2 = attr2.brand.lower().strip()
        if brand1 == brand2:
            score += 0.1
        elif brand1 in brand2 or brand2 in brand1:
            score += 0.05  # Partial match

    return min(score, 1.0)


async def group_similar_products(
    products: list[Product],
    model: str,
    similarity_threshold: float = 0.7,
) -> list[ProductGroup]:
    """
    Group similar products across services using LLM-extracted attributes.

    Args:
        products: List of Product model instances
        model: Ollama model name for attribute extraction
        similarity_threshold: Minimum similarity score to group products

    Returns:
        List of ProductGroup instances
    """
    if not products:
        return []

    logger.info("Grouping %d products with threshold %.2f", len(products), similarity_threshold)

    # Extract attributes for all products concurrently
    attribute_tasks = [extract_product_attributes(p, model) for p in products]
    attributes_list = await asyncio.gather(*attribute_tasks, return_exceptions=True)

    # Build ProductMatch instances
    matches: list[ProductMatch] = []
    for product, attrs in zip(products, attributes_list, strict=False):
        if isinstance(attrs, Exception):
            logger.warning("Failed to extract attributes for %s: %s", product.name[:50], attrs)
            attrs = ProductAttributes(confidence=0.2)

        matches.append(
            ProductMatch(
                product_id=product.id,
                product=product,
                attributes=attrs,
            )
        )

    # Build similarity matrix and cluster products
    groups: list[ProductGroup] = []
    grouped_ids: set[str] = set()

    # Sort by confidence to process most reliable extractions first
    matches.sort(key=lambda m: m.attributes.confidence, reverse=True)

    for i, match1 in enumerate(matches):
        if match1.product_id in grouped_ids:
            continue

        # Start a new group with this product
        group = ProductGroup(
            products=[match1],
            representative_name=match1.product.name,
        )
        grouped_ids.add(match1.product_id)

        # Find similar products
        for match2 in matches[i + 1 :]:
            if match2.product_id in grouped_ids:
                continue

            similarity = calculate_similarity(match1.attributes, match2.attributes)
            if similarity >= similarity_threshold:
                match2.similarity_score = similarity
                group.products.append(match2)
                grouped_ids.add(match2.product_id)

        # Generate group reasoning
        if len(group.products) > 1:
            services = {p.product.service for p in group.products}
            group.reasoning = (
                f"Grouped {len(group.products)} similar products across {', '.join(services)}. "
                f"Product type: {match1.attributes.product_type or 'unknown'}, "
                f"Organic: {'Yes' if match1.attributes.is_organic else 'No'}"
            )
        else:
            group.reasoning = "Single product, no similar matches found"

        groups.append(group)

    logger.info("Created %d product groups from %d products", len(groups), len(products))
    return groups


async def compare_products(
    products: list[Product],
    query: str,
    location: str,
    model_override: str | None = None,
) -> dict:
    """
    Main comparison function that groups products and generates LLM analysis.

    Args:
        products: List of Product model instances to compare
        query: Original search query
        location: Zip code for location context
        model_override: Optional specific model to use

    Returns:
        Dict with groups, llm_analysis, and model_used
    """
    if not products:
        return {
            "groups": [],
            "llm_analysis": {
                "best_value_group": None,
                "reasoning": "No products found to compare",
                "price_insights": [],
                "recommendations": [],
            },
            "model_used": None,
        }

    # Get the best available model
    try:
        model = await ensure_model_available_async(model_override)
    except RuntimeError as e:
        logger.error("No Ollama models available: %s", e)
        return {
            "groups": [
                ProductGroup(
                    products=[
                        ProductMatch(
                            product_id=p.id,
                            product=p,
                            attributes=ProductAttributes(),
                        )
                        for p in products
                    ],
                    representative_name=query,
                    reasoning="LLM unavailable - showing all products ungrouped",
                )
            ],
            "llm_analysis": {
                "best_value_group": 0,
                "reasoning": "LLM unavailable for analysis",
                "price_insights": [],
                "recommendations": [],
                "error": str(e),
            },
            "model_used": None,
        }

    # Ensure model is warmed up
    if not await ensure_model_ready(model):
        logger.warning("Model warmup failed, proceeding with cold model")

    # Get similarity threshold from config
    threshold = settings.PRICE_COMPARISON_SETTINGS.get("similarity_threshold", 0.7)

    # Group similar products
    groups = await group_similar_products(products, model, similarity_threshold=threshold)

    if not groups:
        return {
            "groups": [],
            "llm_analysis": {
                "best_value_group": None,
                "reasoning": "No product groups created",
                "price_insights": [],
                "recommendations": [],
            },
            "model_used": model,
        }

    # Generate LLM analysis for best value
    llm_analysis = await _generate_comparison_analysis(groups, query, model)

    return {
        "groups": groups,
        "llm_analysis": llm_analysis,
        "model_used": model,
    }


async def _generate_comparison_analysis(
    groups: list[ProductGroup],
    query: str,
    model: str,
    timeout: float = 90.0,
) -> dict:
    """
    Generate LLM analysis comparing product groups for best value.

    Returns:
        Dict with best_value_group, reasoning, price_insights, recommendations
    """
    # Build prompt with group summaries
    group_summaries = []
    for i, group in enumerate(groups):
        products_info = []
        for match in group.products[:5]:  # Limit to 5 per group for prompt size
            p = match.product
            unit_price = match.attributes.unit_price
            products_info.append(
                f"  - {p.name[:60]} | {p.service} | {p.price} | "
                f"Size: {p.size or 'N/A'} | "
                f"Unit price: ${unit_price:.3f}/oz" if unit_price else f"  - {p.name[:60]} | {p.service} | {p.price}"
            )

        group_summaries.append(f"Group {i + 1} ({len(group.products)} products):\n" + "\n".join(products_info))
products_info.append(
(
f"  - {p.name[:60]} | {p.service} | {p.price} | "
f"Size: {p.size or 'N/A'} | "
f"Unit price: ${unit_price:.3f}/oz"
)
if unit_price
else f"  - {p.name[:60]} | {p.service} | {p.price}"
)
    prompt = f"""Analyze these grocery product groups for '{query}' and identify the best value.

PRODUCT GROUPS:
{chr(10).join(group_summaries)}

INSTRUCTIONS:
1. Identify which group offers the best overall value considering price, size, and availability
2. Provide reasoning for your recommendation
3. List key price insights (unit price comparisons, deals, etc.)
4. Give 1-2 specific recommendations for the shopper

Respond ONLY with valid JSON in this exact format:
{{"best_value_group": 1, "reasoning": "Group 1 offers...", "price_insights": ["Insight 1", "Insight 2"], "recommendations": ["Buy X from Y for best price"]}}

JSON response:"""

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{OLLAMA_ENDPOINT}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 500,
                    },
                },
            )
            response.raise_for_status()

            result = response.json()
            text = result.get("response", "").strip()

            # Parse JSON from response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            analysis = json.loads(text)

            # Ensure required fields exist
            return {
                "best_value_group": analysis.get("best_value_group"),
                "reasoning": analysis.get("reasoning", ""),
                "price_insights": analysis.get("price_insights", []),
                "recommendations": analysis.get("recommendations", []),
            }

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse analysis JSON: %s", e)
    except httpx.HTTPError as e:
        logger.error("Ollama analysis request failed: %s", e)
    except TimeoutError:
        logger.error("Comparison analysis timed out")
    except Exception as e:
        logger.error("Comparison analysis failed: %s", e)

    # Fallback analysis
    best_group = 0
    if groups:
        # Find group with lowest average unit price
        best_avg_price = float("inf")
        for i, group in enumerate(groups):
            prices = [m.attributes.unit_price for m in group.products if m.attributes.unit_price]
            if prices:
                avg_price = sum(prices) / len(prices)
                if avg_price < best_avg_price:
                    best_avg_price = avg_price
                    best_group = i

    return {
        "best_value_group": best_group,
        "reasoning": "Analysis based on calculated unit prices (LLM analysis unavailable)",
        "price_insights": ["Compare unit prices to find best value"],
        "recommendations": ["Check availability before purchasing"],
    }
