"""
Comparison Manager Service for Price Comparison Orchestration.

Coordinates scraping, product matching, caching, and database persistence
for grocery price comparison operations.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from ..config import settings
from ..models.database import AsyncSessionLocal, Comparison, Product, ShoppingList
from ..models.schemas import BulkUploadItem
from ..utils.logger import get_logger
from . import product_matcher
from .scrapers import get_scraper
from .scrapers.scraper_factory import get_available_scrapers

logger = get_logger("api_gateway.services.comparison_manager")


async def get_cached_comparison(
    query: str,
    location: str,
    cache_ttl_hours: int | None = None,
) -> dict | None:
    """
    Check for cached comparison results.

    Args:
        query: Search query string
        location: Zip code
        cache_ttl_hours: Override cache TTL from config

    Returns:
        Cached comparison dict with full product details or None if not found/expired
    """
    # Note: cache_ttl_hours parameter is available for future use with dynamic TTL
    # Currently we rely on the expires_at field set during comparison creation

    async with AsyncSessionLocal() as session:
        # Find comparison that matches query/location and hasn't expired
        now = datetime.now(UTC)
        result = await session.execute(
            select(Comparison)
            .where(Comparison.query == query.lower().strip())
            .where(Comparison.location == location)
            .where(Comparison.expires_at > now)
            .order_by(Comparison.created_at.desc())
            .limit(1)
        )
        cached = result.scalar_one_or_none()

        if cached:
            logger.info("Cache hit for '%s' at %s", query, location)

            # Reconstruct full response with product details (same as get_comparison_by_id)
            products_json = cached.products_json or []
            product_ids = []
            for group in products_json:
                for product_data in group.get("products", []):
                    product_ids.append(product_data.get("product_id"))

            # Query all products at once
            products_result = await session.execute(
                select(Product).where(Product.id.in_(product_ids))
            )
            products_map = {p.id: p for p in products_result.scalars().all()}

            # Extract services from products
            services_scraped = list({p.service for p in products_map.values()})

            # Build response with full product details
            response_groups = []
            for group in products_json:
                group_products = []
                for product_data in group.get("products", []):
                    product = products_map.get(product_data.get("product_id"))
                    if product:
                        group_products.append({
                            "id": product.id,
                            "service": product.service,
                            "name": product.name,
                            "price": product.price,
                            "size": product.size,
                            "brand": product.brand,
                            "url": product.url,
                            "image_url": product.image_url,
                            "availability": product.availability,
                            "similarity_score": product_data.get("similarity_score", 0),
                            "attributes": product_data.get("attributes", {}),
                        })

                response_groups.append({
                    "representative_name": group.get("representative_name", ""),
                    "reasoning": group.get("reasoning", ""),
                    "products": group_products,
                })

            return {
                "comparison_id": cached.id,
                "query": cached.query,
                "location": cached.location,
                "status": "completed",
                "services_scraped": services_scraped,
                "groups": response_groups,
                "llm_analysis": cached.llm_analysis,
                "model_used": cached.model_used,
                "created_at": cached.created_at.isoformat(),
                "expires_at": cached.expires_at.isoformat() if cached.expires_at else None,
                "from_cache": True,
                "errors": None,
            }

    return None


async def _scrape_service(
    service_name: str,
    query: str,
    location: str,
) -> tuple[str, list[Product], str | None]:
    """
    Scrape a single service and return results with error info.

    Returns:
        Tuple of (service_name, list of Products, error message or None)
    """
    scraper = get_scraper(service_name)
    if not scraper:
        return (service_name, [], f"Scraper not available for {service_name}")

    try:
        products = await scraper.scrape_products(query, location)
        return (service_name, products, None)
    except Exception as e:
        logger.error("Error scraping %s: %s", service_name, e)
        return (service_name, [], str(e))


async def create_comparison(
    query: str,
    location: str,
    services: list[str] | None = None,
    skip_cache: bool = False,
) -> dict:
    """
    Create a product comparison by scraping services and using LLM analysis.

    Args:
        query: Product search query
        location: Zip code for location-based results
        services: Specific services to scrape (default: all available)
        skip_cache: If True, bypass cache check

    Returns:
        Comparison results dict with groups, llm_analysis, model_used
    """
    query_normalized = query.lower().strip()

    # Check cache first
    if not skip_cache:
        cached = await get_cached_comparison(query_normalized, location)
        if cached:
            return cached

    # Determine which services to scrape
    services_to_scrape = services or get_available_scrapers()
    if not services_to_scrape:
        return {
            "comparison_id": None,
            "query": query,
            "location": location,
            "status": "error",
            "message": "No scrapers available",
            "groups": [],
            "llm_analysis": None,
            "model_used": None,
        }

    logger.info("Creating comparison for '%s' at %s using %s", query, location, services_to_scrape)

    # Run scrapers concurrently
    results = await asyncio.gather(
        *[_scrape_service(s, query, location) for s in services_to_scrape],
        return_exceptions=True,
    )

    # Collect products and errors
    all_products: list[Product] = []
    services_scraped: list[str] = []
    errors: list[str] = []

    for result in results:
        if isinstance(result, Exception):
            errors.append(str(result))
            continue

        service_name, products, error = result
        if error:
            errors.append(error)
        else:
            services_scraped.append(service_name)
            all_products.extend(products)

    if not all_products:
        return {
            "comparison_id": None,
            "query": query,
            "location": location,
            "status": "error",
            "message": "No products found from any service",
            "services_scraped": services_scraped,
            "groups": [],
            "llm_analysis": None,
            "model_used": None,
            "errors": errors,
        }

    logger.info("Scraped %d products from %d services", len(all_products), len(services_scraped))

    # Run LLM comparison
    comparison_results = await product_matcher.compare_products(
        products=all_products,
        query=query,
        location=location,
    )

    # Prepare data for database storage
    groups = comparison_results.get("groups", [])
    llm_analysis = comparison_results.get("llm_analysis", {})
    model_used = comparison_results.get("model_used")

    # Serialize groups to JSON-compatible format
    products_json = []
    for group in groups:
        group_data = {
            "representative_name": group.representative_name,
            "reasoning": group.reasoning,
            "products": [
                {
                    "product_id": match.product_id,
                    "similarity_score": match.similarity_score,
                    "attributes": {
                        "brand": match.attributes.brand,
                        "size": match.attributes.size,
                        "size_oz": match.attributes.size_oz,
                        "unit_price": match.attributes.unit_price,
                        "is_organic": match.attributes.is_organic,
                        "product_type": match.attributes.product_type,
                        "confidence": match.attributes.confidence,
                    },
                }
                for match in group.products
            ],
        }
        products_json.append(group_data)

    # Store comparison in database
    comparison_id = str(uuid.uuid4())
    cache_ttl = settings.PRICE_COMPARISON_SETTINGS.get("cache_ttl_hours", 2)
    expires_at = datetime.now(UTC) + timedelta(hours=cache_ttl)

    async with AsyncSessionLocal() as session:
        comparison = Comparison(
            id=comparison_id,
            query=query_normalized,
            location=location,
            products_json=products_json,
            llm_analysis=llm_analysis,
            model_used=model_used,
            expires_at=expires_at,
        )
        session.add(comparison)
        await session.commit()

    logger.info(
        "Created comparison %s with %d groups, %d total products",
        comparison_id,
        len(groups),
        len(all_products),
    )

    # Build response with full product details
    response_groups = []
    for group in groups:
        group_products = []
        for match in group.products:
            product = match.product
            group_products.append({
                "id": product.id,
                "service": product.service,
                "name": product.name,
                "price": product.price,
                "size": product.size,
                "brand": product.brand,
                "url": product.url,
                "image_url": product.image_url,
                "availability": product.availability,
                "similarity_score": match.similarity_score,
                "attributes": {
                    "brand": match.attributes.brand,
                    "size": match.attributes.size,
                    "size_oz": match.attributes.size_oz,
                    "unit_price": match.attributes.unit_price,
                    "is_organic": match.attributes.is_organic,
                    "product_type": match.attributes.product_type,
                    "confidence": match.attributes.confidence,
                },
            })
        response_groups.append({
            "representative_name": group.representative_name,
            "reasoning": group.reasoning,
            "products": group_products,
        })

    return {
        "comparison_id": comparison_id,
        "query": query,
        "location": location,
        "status": "completed",
        "services_scraped": services_scraped,
        "groups": response_groups,
        "llm_analysis": llm_analysis,
        "model_used": model_used,
        "errors": errors if errors else None,
        "from_cache": False,
    }


async def get_comparison_by_id(comparison_id: str) -> dict | None:
    """
    Retrieve a comparison by ID with full product details.

    Args:
        comparison_id: UUID of the comparison

    Returns:
        Comparison dict with full product details or None if not found
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Comparison).where(Comparison.id == comparison_id)
        )
        comparison = result.scalar_one_or_none()

        if not comparison:
            return None

        # Fetch full product details for all products in the comparison
        products_json = comparison.products_json or []
        product_ids = []
        for group in products_json:
            for product_data in group.get("products", []):
                product_ids.append(product_data.get("product_id"))

        # Query all products at once
        products_result = await session.execute(
            select(Product).where(Product.id.in_(product_ids))
        )
        products_map = {p.id: p for p in products_result.scalars().all()}

        # Build response with full product details
        response_groups = []
        for group in products_json:
            group_products = []
            for product_data in group.get("products", []):
                product = products_map.get(product_data.get("product_id"))
                if product:
                    group_products.append({
                        "id": product.id,
                        "service": product.service,
                        "name": product.name,
                        "price": product.price,
                        "size": product.size,
                        "brand": product.brand,
                        "url": product.url,
                        "image_url": product.image_url,
                        "availability": product.availability,
                        "similarity_score": product_data.get("similarity_score", 0),
                        "attributes": product_data.get("attributes", {}),
                    })

            response_groups.append({
                "representative_name": group.get("representative_name", ""),
                "reasoning": group.get("reasoning", ""),
                "products": group_products,
            })

        return {
            "comparison_id": comparison.id,
            "query": comparison.query,
            "location": comparison.location,
            "groups": response_groups,
            "llm_analysis": comparison.llm_analysis,
            "model_used": comparison.model_used,
            "created_at": comparison.created_at.isoformat(),
            "expires_at": comparison.expires_at.isoformat() if comparison.expires_at else None,
        }


async def process_shopping_list(
    items: list[BulkUploadItem],
    session_token: str,
    list_name: str,
) -> dict:
    """
    Process a shopping list by comparing all items across services.

    Args:
        items: List of BulkUploadItem (query + quantity)
        session_token: User's session token
        list_name: Name for the shopping list

    Returns:
        Dict with list_id, items with comparison_ids, and aggregate statistics
    """
    list_id = str(uuid.uuid4())

    # Create shopping list record with processing status
    async with AsyncSessionLocal() as session:
        shopping_list = ShoppingList(
            id=list_id,
            session_token=session_token,
            name=list_name,
            items_json=[],
            status="processing",
        )
        session.add(shopping_list)
        await session.commit()

    logger.info("Processing shopping list %s with %d items", list_id, len(items))

    # Process each item
    processed_items = []
    service_totals: dict[str, float] = {}
    all_services: set[str] = set()

    for item in items:
        try:
            comparison = await create_comparison(
                query=item.query,
                location=settings.DEFAULT_LOCATION.get("zip_code", "20024"),
            )

            # Calculate per-service costs for this item
            for group in comparison.get("groups", []):
                for product in group.get("products", []):
                    service = product.get("service")
                    if service:
                        all_services.add(service)
                        # Parse price and multiply by quantity
                        price_str = product.get("price", "")
                        price_value = product_matcher._parse_price(price_str)
                        if price_value:
                            if service not in service_totals:
                                service_totals[service] = 0.0
                            service_totals[service] += price_value * item.quantity

            processed_items.append({
                "query": item.query,
                "quantity": item.quantity,
                "comparison_id": comparison.get("comparison_id"),
                "status": comparison.get("status", "completed"),
            })

        except Exception as e:
            logger.error("Failed to process item '%s': %s", item.query, e)
            processed_items.append({
                "query": item.query,
                "quantity": item.quantity,
                "comparison_id": None,
                "status": "error",
                "error": str(e),
            })

    # Calculate aggregate statistics
    if service_totals:
        cheapest_service = min(service_totals, key=service_totals.get)
        most_expensive_service = max(service_totals, key=service_totals.get)
        potential_savings = service_totals[most_expensive_service] - service_totals[cheapest_service]
    else:
        cheapest_service = None
        most_expensive_service = None
        potential_savings = 0.0

    total_stats = {
        "service_totals": service_totals,
        "cheapest_service": cheapest_service,
        "most_expensive_service": most_expensive_service,
        "potential_savings": round(potential_savings, 2),
        "items_processed": len(processed_items),
        "items_failed": sum(1 for i in processed_items if i.get("status") == "error"),
    }

    # Update shopping list with results
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ShoppingList).where(ShoppingList.id == list_id)
        )
        shopping_list = result.scalar_one_or_none()
        if shopping_list:
            shopping_list.items_json = processed_items
            shopping_list.total_stats = total_stats
            shopping_list.status = "completed"
            await session.commit()

    logger.info(
        "Shopping list %s complete: %d items, potential savings: $%.2f",
        list_id,
        len(processed_items),
        potential_savings,
    )

    return {
        "list_id": list_id,
        "name": list_name,
        "items": processed_items,
        "total_stats": total_stats,
        "status": "completed",
    }


async def get_shopping_list(list_id: str) -> dict | None:
    """
    Retrieve a shopping list by ID.

    Args:
        list_id: UUID of the shopping list

    Returns:
        Shopping list dict or None if not found
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ShoppingList).where(ShoppingList.id == list_id)
        )
        shopping_list = result.scalar_one_or_none()

        if not shopping_list:
            return None

        return {
            "list_id": shopping_list.id,
            "name": shopping_list.name,
            "items": shopping_list.items_json,
            "total_stats": shopping_list.total_stats,
            "status": shopping_list.status,
            "created_at": shopping_list.created_at.isoformat(),
            "updated_at": shopping_list.updated_at.isoformat(),
        }
