"""
Price Comparison API Routes.

Endpoints for grocery product price comparison across multiple services.
"""

from fastapi import APIRouter, Query
from sqlalchemy import select

from ..config import settings
from ..middleware.response import unified_response
from ..models.database import AsyncSessionLocal, Product, SavedSelection
from ..models.schemas import (
    BulkUploadRequest,
    ProductSearchRequest,
)
from ..services import comparison_manager
from ..services.job_queue import JobQueueManager
from ..services.model_selector import ensure_model_available_async
from ..services.scrapers.scraper_factory import (
    get_available_scrapers,
    get_configured_services,
)
from ..utils.logger import get_logger
from ..utils.session_validator import validate_session_token

logger = get_logger("api_gateway.routes.price_comparison")

# Job queue manager for async processing
job_queue = JobQueueManager()

router = APIRouter(prefix="/price-comparison", tags=["price-comparison"])


@router.post("/search")
@unified_response
async def search_products(payload: ProductSearchRequest) -> dict:
    """
    Search for a product across multiple grocery delivery services.

    Scrapes Amazon Fresh, Instacart, DoorDash, Safeway for the specified
    product and uses LLM to group comparable items.

    Args:
        payload: Search request with product query and optional filters

    Returns:
        Comparison results with grouped products and LLM analysis
    """
    # Ensure suitable model is available (async to avoid blocking event loop)
    model = await ensure_model_available_async()
    logger.info("Product search: %s (model: %s)", payload.query, model)

    # Determine which services to scrape
    if payload.services:
        # Use specified services
        services_to_scrape = [s for s in payload.services if s in get_configured_services()]
    else:
        # Default to all available scrapers
        services_to_scrape = get_available_scrapers()

    if not services_to_scrape:
        return {
            "query": payload.query,
            "location": payload.location,
            "model": model,
            "status": "error",
            "message": "No scrapers available for requested services",
            "services_scraped": [],
            "groups": [],
            "llm_analysis": None,
            "errors": [],
        }

    logger.info("Scraping services: %s", services_to_scrape)

    try:
        # Use comparison manager to handle scraping, grouping, and LLM analysis
        results = await comparison_manager.create_comparison(
            query=payload.query,
            location=payload.location,
            services=services_to_scrape,
        )

        # Transform response to match ProductSearchResponse schema
        # Include similarity_score, attributes, and group reasoning
        response_groups = []
        for group in results.get("groups", []):
            group_products = []
            for product in group.get("products", []):
                group_products.append(
                    {
                        "id": product.get("id"),
                        "service": product.get("service"),
                        "name": product.get("name"),
                        "price": product.get("price"),
                        "size": product.get("size"),
                        "brand": product.get("brand"),
                        "url": product.get("url"),
                        "image_url": product.get("image_url"),
                        "availability": product.get("availability", True),
                        "similarity_score": product.get("similarity_score", 0.0),
                        "attributes": product.get("attributes"),
                    }
                )
            response_groups.append(
                {
                    "representative_name": group.get("representative_name", ""),
                    "reasoning": group.get("reasoning", ""),
                    "products": group_products,
                }
            )

        return {
            "query": results.get("query", payload.query),
            "comparison_id": results.get("comparison_id"),
            "location": results.get("location", payload.location),
            "model_used": results.get("model_used", model),
            "status": results.get("status", "completed"),
            "services_scraped": results.get("services_scraped", []),
            "groups": response_groups,
            "llm_analysis": results.get("llm_analysis"),
            "from_cache": results.get("from_cache", False),
            "errors": results.get("errors", []),
        }

    except Exception as e:
        logger.error("Product search failed: %s", e)
        return {
            "query": payload.query,
            "location": payload.location,
            "model_used": model,
            "status": "error",
            "message": f"Search failed: {str(e)}",
            "services_scraped": [],
            "groups": [],
            "llm_analysis": None,
            "errors": [str(e)],
        }


@router.post("/bulk-upload")
@unified_response
async def bulk_upload(payload: BulkUploadRequest) -> dict:
    """
    Upload a shopping list for batch price comparison.

    Creates an async job that processes items sequentially with real-time
    progress updates via WebSocket. Connect to /api/jobs/ws/jobs/{job_id}
    to receive progress updates.

    Args:
        payload: List of items with quantities

    Returns:
        Response with job_id for tracking progress via WebSocket
    """
    logger.info("Bulk upload: %d items", len(payload.items))

    # Validate item count
    max_items = settings.SHOPPING_LIST_SETTINGS.get("max_items", 100)
    if len(payload.items) > max_items:
        return {
            "list_id": None,
            "job_id": None,
            "status": "error",
            "message": f"Too many items. Maximum allowed: {max_items}",
        }

    if not payload.items:
        return {
            "list_id": None,
            "job_id": None,
            "status": "error",
            "message": "No items provided",
        }

    try:
        # Prepare job data
        job_data = {
            "items": [{"query": item.query, "quantity": item.quantity} for item in payload.items],
            "session_token": payload.session_token or "",
            "list_name": payload.name or "Shopping List",
            "location": settings.DEFAULT_LOCATION.get("zip_code", "20024"),
        }

        # Calculate timeout based on number of items
        timeout_per_item = settings.SHOPPING_LIST_SETTINGS.get("timeout_per_item", 60)
        total_timeout = len(payload.items) * timeout_per_item + 60  # Extra buffer

        # Create async job for shopping list processing
        job_id = await job_queue.create_job(
            service="shopping_list_processor",
            request_data=job_data,
            timeout_seconds=min(total_timeout, 3600),  # Max 1 hour
        )

        logger.info("Created shopping list job %s with %d items", job_id, len(payload.items))

        return {
            "list_id": None,  # Will be set when processing starts
            "job_id": job_id,
            "status": "pending",
            "message": "Processing started. Connect to WebSocket for progress updates.",
            "websocket_url": f"/api/jobs/ws/jobs/{job_id}",
            "total_items": len(payload.items),
        }

    except Exception as e:
        logger.error("Bulk upload failed: %s", e)
        return {
            "list_id": None,
            "job_id": None,
            "status": "error",
            "message": f"Failed to create job: {str(e)}",
        }


@router.get("/comparison/{comparison_id}")
@unified_response
async def get_comparison(comparison_id: str) -> dict:
    """
    Retrieve a comparison by ID.

    Args:
        comparison_id: UUID of the comparison

    Returns:
        Comparison results with grouped products and LLM analysis
    """
    logger.info("Fetching comparison: %s", comparison_id)

    try:
        result = await comparison_manager.get_comparison_by_id(comparison_id)
        if not result:
            return {
                "status": "error",
                "message": f"Comparison {comparison_id} not found",
            }

        # Transform to response format with similarity_score, attributes, and reasoning
        response_groups = []
        for group in result.get("groups", []):
            group_products = []
            for product in group.get("products", []):
                group_products.append(
                    {
                        "id": product.get("id"),
                        "service": product.get("service"),
                        "name": product.get("name"),
                        "price": product.get("price"),
                        "size": product.get("size"),
                        "brand": product.get("brand"),
                        "url": product.get("url"),
                        "image_url": product.get("image_url"),
                        "availability": product.get("availability", True),
                        "similarity_score": product.get("similarity_score", 0.0),
                        "attributes": product.get("attributes"),
                    }
                )
            response_groups.append(
                {
                    "representative_name": group.get("representative_name", ""),
                    "reasoning": group.get("reasoning", ""),
                    "products": group_products,
                }
            )

        return {
            "comparison_id": result.get("comparison_id"),
            "query": result.get("query"),
            "location": result.get("location"),
            "groups": response_groups,
            "llm_analysis": result.get("llm_analysis"),
            "model_used": result.get("model_used"),
            "created_at": result.get("created_at"),
            "expires_at": result.get("expires_at"),
            "status": "completed",
        }

    except Exception as e:
        logger.error("Failed to fetch comparison %s: %s", comparison_id, e)
        return {
            "status": "error",
            "message": f"Failed to fetch comparison: {str(e)}",
        }


@router.get("/shopping-list/{list_id}")
@unified_response
async def get_shopping_list(list_id: str) -> dict:
    """
    Retrieve a shopping list by ID.

    Args:
        list_id: UUID of the shopping list

    Returns:
        Shopping list with items and aggregate statistics
    """
    logger.info("Fetching shopping list: %s", list_id)

    try:
        result = await comparison_manager.get_shopping_list(list_id)
        if not result:
            return {
                "status": "error",
                "message": f"Shopping list {list_id} not found",
            }

        return {
            "list_id": result.get("list_id"),
            "name": result.get("name"),
            "items": result.get("items", []),
            "total_stats": result.get("total_stats", {}),
            "status": result.get("status"),
            "created_at": result.get("created_at"),
            "updated_at": result.get("updated_at"),
        }

    except Exception as e:
        logger.error("Failed to fetch shopping list %s: %s", list_id, e)
        return {
            "status": "error",
            "message": f"Failed to fetch shopping list: {str(e)}",
        }


@router.get("/saved")
@unified_response
async def get_saved_selections(
    session_token: str = Query(..., description="Session token from dashboard"),
) -> dict:
    """
    Retrieve user's saved product selections with best-price aggregation.

    Args:
        session_token: Dashboard session token for user identification

    Returns:
        List of saved products with details, best-price alternatives, and aggregated totals
    """
    # Validate session token
    is_valid, result = await validate_session_token(session_token)
    if not is_valid:
        logger.warning("Invalid session token: %s", result)
        return {
            "selections": [],
            "total_items": 0,
            "status": "error",
            "message": result,
        }

    logger.info("Fetching saved selections for session: %s", session_token[:8])

    try:
        async with AsyncSessionLocal() as db_session:
            # Query saved selections with joined product data
            result = await db_session.execute(
                select(SavedSelection, Product)
                .outerjoin(Product, SavedSelection.product_id == Product.id)
                .where(SavedSelection.session_token == session_token)
                .order_by(SavedSelection.created_at.desc())
            )
            rows = result.all()

            selections = []
            # Track totals by service for best-price aggregation
            service_totals: dict[str, float] = {}
            best_price_totals: dict[str, float] = {}
            total_potential_savings = 0.0

            for selection, product in rows:
                selection_data = {
                    "selection_id": selection.id,
                    "product": None,
                    "quantity": selection.quantity,
                    "notes": selection.notes,
                    "created_at": (
                        selection.created_at.isoformat() if selection.created_at else None
                    ),
                    "best_alternatives": [],
                }

                if product:
                    # Parse price string to float for calculations
                    try:
                        price_str = product.price.replace("$", "").replace(",", "").strip()
                        price_value = float(price_str)
                    except (ValueError, AttributeError):
                        price_value = 0.0

                    selection_data["product"] = {
                        "id": product.id,
                        "service": product.service,
                        "name": product.name,
                        "price": price_value,
                        "size": product.size,
                        "brand": product.brand,
                        "url": product.url,
                        "image_url": product.image_url,
                        "availability": product.availability,
                    }

                    item_total = price_value * selection.quantity

                    # Add to service totals
                    if product.service not in service_totals:
                        service_totals[product.service] = 0.0
                    service_totals[product.service] += item_total

                    # Find best alternatives for this product (similar products from other services)
                    # Query products with similar names from different services
                    similar_query = await db_session.execute(
                        select(Product)
                        .where(Product.service != product.service)
                        .where(Product.name.ilike(f"%{product.name[:20]}%"))
                        .order_by(Product.price)
                        .limit(5)
                    )
                    similar_products = similar_query.scalars().all()

                    best_price_for_item = price_value
                    best_service_for_item = product.service

                    for similar in similar_products:
                        try:
                            similar_price_str = (
                                similar.price.replace("$", "").replace(",", "").strip()
                            )
                            similar_price = float(similar_price_str)
                        except (ValueError, AttributeError):
                            continue

                        if similar_price < best_price_for_item:
                            best_price_for_item = similar_price
                            best_service_for_item = similar.service

                        selection_data["best_alternatives"].append(
                            {
                                "service": similar.service,
                                "name": similar.name,
                                "price": similar_price,
                                "savings": round(price_value - similar_price, 2),
                            }
                        )

                    # Track best price totals by service
                    if best_service_for_item not in best_price_totals:
                        best_price_totals[best_service_for_item] = 0.0
                    best_price_totals[best_service_for_item] += (
                        best_price_for_item * selection.quantity
                    )

                    # Calculate potential savings
                    if best_price_for_item < price_value:
                        total_potential_savings += (
                            price_value - best_price_for_item
                        ) * selection.quantity

                selections.append(selection_data)

            # Determine cheapest service for entire cart
            cheapest_service = None
            cheapest_total = None
            if service_totals:
                cheapest_service = min(service_totals, key=lambda k: service_totals[k])
                cheapest_total = service_totals[cheapest_service]

            # Calculate most expensive service
            most_expensive_service = None
            most_expensive_total = None
            if service_totals:
                most_expensive_service = max(service_totals, key=lambda k: service_totals[k])
                most_expensive_total = service_totals[most_expensive_service]

            return {
                "selections": selections,
                "total_items": len(selections),
                "aggregation": {
                    "service_totals": {k: round(v, 2) for k, v in service_totals.items()},
                    "cheapest_service": cheapest_service,
                    "cheapest_total": round(cheapest_total, 2) if cheapest_total else None,
                    "most_expensive_service": most_expensive_service,
                    "most_expensive_total": (
                        round(most_expensive_total, 2) if most_expensive_total else None
                    ),
                    "potential_savings": round(total_potential_savings, 2),
                    "recommended_service": cheapest_service,
                },
            }

    except Exception as e:
        logger.error("Failed to fetch saved selections: %s", e)
        return {
            "selections": [],
            "total_items": 0,
            "status": "error",
            "message": f"Failed to fetch selections: {str(e)}",
        }


@router.post("/save")
@unified_response
async def save_selection(
    session_token: str = Query(..., description="Session token"),
    product_id: str = Query(..., description="Product ID to save"),
    quantity: int = Query(1, ge=1, description="Quantity"),
) -> dict:
    """
    Save a product selection to user's cart.

    Args:
        session_token: Dashboard session token
        product_id: ID of product to save
        quantity: Quantity to save

    Returns:
        Confirmation with saved selection details
    """
    # Validate session token
    is_valid, result = await validate_session_token(session_token)
    if not is_valid:
        logger.warning("Invalid session token for save: %s", result)
        return {
            "saved": False,
            "status": "error",
            "message": result,
        }

    logger.info("Saving selection: product=%s, qty=%d", product_id, quantity)

    try:
        async with AsyncSessionLocal() as session:
            # Verify product exists
            product = await session.get(Product, product_id)
            if not product:
                return {
                    "saved": False,
                    "status": "error",
                    "message": f"Product {product_id} not found",
                }

            # Check if already saved (update quantity if exists)
            existing_result = await session.execute(
                select(SavedSelection).where(
                    SavedSelection.session_token == session_token,
                    SavedSelection.product_id == product_id,
                )
            )
            existing = existing_result.scalar_one_or_none()

            if existing:
                # Update quantity
                existing.quantity = quantity
                await session.commit()
                await session.refresh(existing)
                selection_id = existing.id
                logger.info("Updated existing selection %s with qty=%d", selection_id, quantity)
            else:
                # Create new selection
                selection = SavedSelection(
                    session_token=session_token,
                    product_id=product_id,
                    quantity=quantity,
                )
                session.add(selection)
                await session.commit()
                await session.refresh(selection)
                selection_id = selection.id
                logger.info("Created new selection %s", selection_id)

            # Parse price for response
            try:
                price_str = product.price.replace("$", "").replace(",", "").strip()
                price_value = float(price_str)
            except (ValueError, AttributeError):
                price_value = 0.0

            return {
                "saved": True,
                "selection_id": selection_id,
                "product": {
                    "id": product.id,
                    "service": product.service,
                    "name": product.name,
                    "price": price_value,
                },
                "quantity": quantity,
            }

    except Exception as e:
        logger.error("Failed to save selection: %s", e)
        return {
            "saved": False,
            "status": "error",
            "message": f"Failed to save selection: {str(e)}",
        }


@router.delete("/saved/{selection_id}")
@unified_response
async def delete_selection(
    selection_id: str,
    session_token: str = Query(..., description="Session token"),
) -> dict:
    """
    Delete a saved product selection.

    Args:
        selection_id: ID of saved selection to delete
        session_token: Dashboard session token for authorization

    Returns:
        Confirmation of deletion
    """
    # Validate session token
    is_valid, result = await validate_session_token(session_token)
    if not is_valid:
        logger.warning("Invalid session token for delete: %s", result)
        return {
            "deleted": False,
            "status": "error",
            "message": result,
        }

    logger.info("Deleting selection: %s", selection_id)

    try:
        async with AsyncSessionLocal() as session:
            # Find selection and verify ownership
            result = await session.execute(
                select(SavedSelection).where(SavedSelection.id == selection_id)
            )
            selection = result.scalar_one_or_none()

            if not selection:
                return {
                    "deleted": False,
                    "status": "error",
                    "message": f"Selection {selection_id} not found",
                }

            # Verify session token matches (authorization check)
            if selection.session_token != session_token:
                logger.warning(
                    "Unauthorized delete attempt: selection %s, token mismatch",
                    selection_id,
                )
                return {
                    "deleted": False,
                    "status": "error",
                    "message": "Not authorized to delete this selection",
                }

            # Delete the selection
            await session.delete(selection)
            await session.commit()

            logger.info("Deleted selection %s", selection_id)

            return {
                "deleted": True,
                "selection_id": selection_id,
            }

    except Exception as e:
        logger.error("Failed to delete selection %s: %s", selection_id, e)
        return {
            "deleted": False,
            "status": "error",
            "message": f"Failed to delete selection: {str(e)}",
        }
