"""
API Key authentication middleware for FastAPI.

Validates X-API-Key header against stored API keys in the database.
Certain paths (health, metrics, docs) are public and bypass authentication.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..models.database import APIKey, AsyncSessionLocal
from ..utils.exceptions import InvalidAPIKeyError
from ..utils.logger import logger


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Middleware for API key authentication.

    Checks for X-API-Key header on protected endpoints and validates
    against the database. Updates last_used_at timestamp on successful auth.

    Attributes:
        PUBLIC_PATHS: Endpoints that don't require authentication.
        PUBLIC_PREFIXES: Path prefixes that allow unauthenticated GET requests.
    """

    # Endpoints that don't require authentication
    PUBLIC_PATHS = {"/health", "/metrics", "/docs", "/openapi.json", "/redoc"}
    # Path prefixes that are public (read-only endpoints)
    PUBLIC_PREFIXES = ("/jobs", "/llm/models")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and validate API key authentication.

        Skips authentication for public endpoints (health, metrics, docs) and
        read-only GET requests on certain prefixes. For protected endpoints,
        validates X-API-Key header against database and updates last_used_at.

        Args:
            request: Incoming FastAPI request
            call_next: Next middleware/handler in chain

        Returns:
            Response from downstream handler

        Raises:
            InvalidAPIKeyError: If API key is missing, invalid, or inactive
        """
        # Skip auth for public endpoints
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)

        # Skip auth for GET requests on public prefixes (read-only)
        if request.method == "GET" and any(
            request.url.path.startswith(p) for p in self.PUBLIC_PREFIXES
        ):
            return await call_next(request)

        api_key_value = request.headers.get("X-API-Key")
        if not api_key_value:
            raise InvalidAPIKeyError("Missing API key")

        async with AsyncSessionLocal() as session:
            api_key = await session.get(APIKey, api_key_value)
            if not api_key or not api_key.is_active:
                raise InvalidAPIKeyError("Invalid or inactive API key")

            api_key.last_used_at = datetime.now(UTC)
            await session.commit()

        request.state.api_key = api_key_value
        # Log only the first 8 characters of the API key for security
        masked_key = f"{api_key_value[:8]}..." if len(api_key_value) > 8 else "***"
        logger.debug(f"Authenticated request with API key: {masked_key}")
        response = await call_next(request)
        return response
