from datetime import datetime
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..models.database import APIKey, AsyncSessionLocal
from ..utils.exceptions import InvalidAPIKeyError
from ..utils.logger import logger


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        api_key_value = request.headers.get("X-API-Key")
        if not api_key_value:
            raise InvalidAPIKeyError("Missing API key")

        async with AsyncSessionLocal() as session:
            api_key = await session.get(APIKey, api_key_value)
            if not api_key or not api_key.is_active:
                raise InvalidAPIKeyError("Invalid or inactive API key")

            api_key.last_used_at = datetime.utcnow()
            await session.commit()

        request.state.api_key = api_key_value
        logger.debug(f"Authenticated request with API key: {api_key_value}")
        response = await call_next(request)
        return response

