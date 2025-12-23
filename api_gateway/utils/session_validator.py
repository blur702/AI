"""
Session Token Validation Utility.

Validates session tokens against the dashboard backend's session store.
Used by price comparison endpoints to ensure requests are authenticated.
"""

import httpx

from ..config import settings
from .logger import get_logger

logger = get_logger("api_gateway.utils.session_validator")

# Dashboard backend URL (same machine, different port)
DASHBOARD_URL = f"http://127.0.0.1:{settings.DASHBOARD_PORT}"


async def validate_session_token(token: str | None) -> tuple[bool, str | None]:
    """
    Validate a session token against the dashboard backend.

    Args:
        token: Session token to validate

    Returns:
        Tuple of (is_valid, username or error_message)
    """
    if not token:
        return False, "No session token provided"

if response.status_code == 200:
data = response.json()
if data.get("valid"):
return True, data.get("username")
return False, "Invalid or expired session token"
if response.status_code >= 500:
logger.error("Dashboard backend error: %s", response.status_code)
return False, "Authentication service error"

return False, "Invalid or expired session token"

    except httpx.ConnectError:
        logger.error("Failed to connect to dashboard backend for token validation")
        return False, "Authentication service unavailable"
    except Exception:
        logger.exception("Session validation error")
        return False, "Validation error"
