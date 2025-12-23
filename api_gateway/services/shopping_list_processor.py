"""
Shopping List Processor Service for Async Bulk Processing.

Processes shopping lists item by item with real-time progress updates.
Designed to be used as an internal job queue service, yielding progress
updates that the JobWorker broadcasts via WebSocket.

Progress Update Format:
    {
        "status": "processing",
        "progress": {
            "items_completed": 3,
            "total_items": 10,
            "current_item": "bread",
            "percentage": 30
        },
        "list_id": "uuid",
        "items": [
            {"query": "milk", "quantity": 1, "status": "completed", "comparison_id": "..."},
            {"query": "eggs", "quantity": 2, "status": "completed", "comparison_id": "..."},
            ...
        ],
        "total_stats": {
            "service_totals": {"amazon_fresh": 15.99, "instacart": 17.50},
            "cheapest_service": "amazon_fresh",
            "potential_savings": 1.51,
            "items_processed": 3,
            "items_failed": 0
        }
    }

Final Result Format:
    {
        "status": "completed",
        "list_id": "uuid",
        "name": "My Shopping List",
        "items": [...],
        "total_stats": {...}
    }
"""

import uuid
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import select

from ..config import settings
from ..models.database import AsyncSessionLocal, ShoppingList
from ..utils.logger import get_logger
from . import comparison_manager
from .product_matcher import parse_price  # After making it public

logger = get_logger("api_gateway.services.shopping_list_processor")


async def process_shopping_list_job(
    job_data: dict[str, Any],
    job_id: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Process a shopping list asynchronously with progress updates.

    This is an async generator that yields progress updates after each item
    is processed. The JobWorker consumes these updates and broadcasts them
    via WebSocket.

    Args:
        job_data: Job request data containing:
            - items: List of {"query": str, "quantity": int}
            - session_token: User session token
            - list_name: Name for the shopping list
            - location: ZIP code (optional, defaults to config)
        job_id: Job ID for logging

    Yields:
        Progress updates with status, items processed, and running totals

    Returns:
        Final result with completed status and aggregate statistics
    """
    items = job_data.get("items", [])
    session_token = job_data.get("session_token", "")
    list_name = job_data.get("list_name", "Shopping List")
    location = job_data.get("location", settings.DEFAULT_LOCATION.get("zip_code", "20024"))

    # Validate items
    max_items = settings.SHOPPING_LIST_SETTINGS.get("max_items", 100)
    if len(items) > max_items:
        yield {
            "status": "error",
            "error": f"Too many items. Maximum allowed: {max_items}",
        }
        return

    if not items:
        yield {
            "status": "error",
            "error": "No items provided",
        }
        return

    # Create shopping list record
    list_id = str(uuid.uuid4())
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

    logger.info(
        "Processing shopping list %s (job %s) with %d items",
        list_id,
        job_id,
        len(items),
    )

    # Initialize tracking
    processed_items: list[dict[str, Any]] = []
    service_totals: dict[str, float] = {}
    all_services: set[str] = set()
    items_failed = 0
    total_items = len(items)

    # Process each item sequentially
    for idx, item in enumerate(items):
        query = item.get("query", "").strip()
        quantity = item.get("quantity", 1)

        if not query:
            processed_items.append({
                "query": query,
                "quantity": quantity,
                "status": "error",
                "error": "Empty query",
                "comparison_id": None,
            })
            items_failed += 1
            continue

        logger.info("Processing item %d/%d: %s", idx + 1, total_items, query)

        try:
            # Create comparison for this item
            comparison = await comparison_manager.create_comparison(
                query=query,
                location=location,
            )

            comparison_id = comparison.get("comparison_id")
            item_status = "completed" if comparison_id else "error"

            # Calculate per-service costs for this item
            for group in comparison.get("groups", []):
                for product in group.get("products", []):
                    service = product.get("service")
                    if service:
                        all_services.add(service)
                        # Get price value
                        price = product.get("price")
                        if isinstance(price, (int, float)):
                            price_value = float(price)
                        elif isinstance(price, str):
                            price_value = product_matcher._parse_price(price)
                        else:
                            price_value = None

if price_value is not None:
if service not in service_totals:
service_totals[service] = 0.0
service_totals[service] += price_value * quantity

            processed_items.append({
                "query": query,
                "quantity": quantity,
                "status": item_status,
                "comparison_id": comparison_id,
                "services_found": comparison.get("services_scraped", []),
            })

            if item_status == "error":
                items_failed += 1

        except Exception as e:
            logger.error("Failed to process item '%s': %s", query, e)
            processed_items.append({
                "query": query,
                "quantity": quantity,
                "status": "error",
                "error": str(e),
                "comparison_id": None,
            })
            items_failed += 1

        # Calculate running statistics
        items_completed = idx + 1
        current_stats = _calculate_stats(
            service_totals,
            items_completed,
            items_failed,
        )

        # Yield progress update
        yield {
            "status": "processing",
            "progress": {
                "items_completed": items_completed,
                "total_items": total_items,
                "current_item": query,
                "percentage": int((items_completed / total_items) * 100),
            },
            "list_id": list_id,
            "items": processed_items.copy(),
            "total_stats": current_stats,
        }

        # Update database with current progress
        await _update_shopping_list(list_id, processed_items, current_stats, "processing")

    # Calculate final statistics
    final_stats = _calculate_stats(
        service_totals,
        len(processed_items),
        items_failed,
    )

    # Update database with final results
    await _update_shopping_list(list_id, processed_items, final_stats, "completed")

    logger.info(
        "Shopping list %s complete: %d items processed, %d failed, potential savings: $%.2f",
        list_id,
        len(processed_items),
        items_failed,
        final_stats.get("potential_savings", 0),
    )

    # Yield final result
    yield {
        "status": "completed",
        "list_id": list_id,
        "name": list_name,
        "items": processed_items,
        "total_stats": final_stats,
    }


def _calculate_stats(
    service_totals: dict[str, float],
    items_processed: int,
    items_failed: int,
) -> dict[str, Any]:
    """
    Calculate aggregate statistics from service totals.

    Args:
        service_totals: Dict mapping service name to total cost
        items_processed: Number of items processed
        items_failed: Number of items that failed

    Returns:
        Statistics dict with totals, cheapest service, and savings
    """
    if service_totals:
        cheapest_service = min(service_totals, key=lambda k: service_totals[k])
        most_expensive = max(service_totals, key=lambda k: service_totals[k])
        potential_savings = service_totals[most_expensive] - service_totals[cheapest_service]
    else:
        cheapest_service = None
        most_expensive = None
        potential_savings = 0.0

    return {
        "service_totals": {k: round(v, 2) for k, v in service_totals.items()},
        "cheapest_service": cheapest_service,
        "most_expensive_service": most_expensive,
        "potential_savings": round(potential_savings, 2),
        "items_processed": items_processed,
        "items_failed": items_failed,
    }


async def _update_shopping_list(
    list_id: str,
    items: list[dict[str, Any]],
    stats: dict[str, Any],
    status: str,
) -> None:
    """
    Update shopping list record in database.

    Args:
        list_id: Shopping list UUID
        items: Processed items list
        stats: Aggregate statistics
        status: Current status (processing, completed)
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ShoppingList).where(ShoppingList.id == list_id)
        )
        shopping_list = result.scalar_one_or_none()
        if shopping_list:
            shopping_list.items_json = items
            shopping_list.total_stats = stats
            shopping_list.status = status
            await session.commit()
