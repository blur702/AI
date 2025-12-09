"""
API Client for AI Dashboard

Provides a simple interface to communicate with the dashboard backend API.
Includes connection pooling and retry mechanisms for improved reliability.
"""

import logging
import os
import time
from typing import Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Default credentials (can be overridden via environment variables)
DEFAULT_AUTH_USERNAME = "admin"
DEFAULT_AUTH_PASSWORD = "admin"


class DashboardAPI:
    """
    Client for the AI Dashboard API.

    Features:
        - Connection pooling via requests.Session
        - Automatic retries with exponential backoff
        - HTTP Basic Authentication support
        - Detailed error logging

    Args:
        base_url: Full URL to the dashboard backend including port
                  (e.g., "http://localhost:80").
                  Defaults to "http://localhost" (port 80).
        timeout: Request timeout in seconds. Defaults to 10.
        max_retries: Maximum number of retry attempts. Defaults to 3.
        auth: Optional tuple of (username, password) for HTTP Basic Auth.
              If not provided, reads from environment variables
              DASHBOARD_AUTH_USERNAME and DASHBOARD_AUTH_PASSWORD,
              or falls back to defaults.
    """

    def __init__(
        self,
        base_url: str = "http://localhost",
        timeout: int = 10,
        max_retries: int = 3,
        auth: Optional[Tuple[str, str]] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

        # Set up authentication
        if auth:
            self._auth = HTTPBasicAuth(auth[0], auth[1])
        else:
            username = os.environ.get(
                "DASHBOARD_AUTH_USERNAME", DEFAULT_AUTH_USERNAME
            )
            password = os.environ.get(
                "DASHBOARD_AUTH_PASSWORD", DEFAULT_AUTH_PASSWORD
            )
            self._auth = HTTPBasicAuth(username, password)

        # Create session with connection pooling
        self._session = requests.Session()
        self._session.auth = self._auth

        # Configure retry strategy with exponential backoff
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=0.5,  # 0.5, 1.0, 2.0 seconds
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )

        # Mount adapter for both HTTP and HTTPS
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=10,
        )
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

        # Track last error for diagnostics
        self._last_error: Optional[str] = None
        self._last_error_time: Optional[float] = None

    @property
    def last_error(self) -> Optional[str]:
        """Return the last error message, if any."""
        return self._last_error

    @property
    def last_error_time(self) -> Optional[float]:
        """Return the timestamp of the last error, if any."""
        return self._last_error_time

    def _record_error(self, message: str) -> None:
        """Record an error with timestamp for diagnostics."""
        self._last_error = message
        self._last_error_time = time.time()
        logger.error(message)

    def _clear_error(self) -> None:
        """Clear the last recorded error."""
        self._last_error = None
        self._last_error_time = None

    def _get(self, endpoint: str) -> Optional[dict]:
        """Make a GET request to the API.

        Args:
            endpoint: API endpoint path (e.g., "/api/services").

        Returns:
            Parsed JSON response as dict, or None on failure.
        """
        url = f"{self.base_url}{endpoint}"
        try:
            response = self._session.get(url, timeout=self.timeout)
            response.raise_for_status()
            self._clear_error()
            return response.json()
        except requests.exceptions.Timeout:
            self._record_error(f"Request timeout: GET {endpoint}")
            return None
        except requests.exceptions.ConnectionError as e:
            self._record_error(f"Connection error: GET {endpoint} - {e}")
            return None
        except requests.exceptions.HTTPError as e:
            self._record_error(
                f"HTTP error: GET {endpoint} - {e.response.status_code}"
            )
            return None
        except requests.exceptions.RequestException as e:
            self._record_error(f"Request failed: GET {endpoint} - {e}")
            return None
        except ValueError as e:
            self._record_error(f"Invalid JSON response: GET {endpoint} - {e}")
            return None

    def _post(self, endpoint: str, data: Optional[dict] = None) -> Optional[dict]:
        """Make a POST request to the API.

        Args:
            endpoint: API endpoint path (e.g., "/api/services/ollama/start").
            data: Optional JSON payload.

        Returns:
            Parsed JSON response as dict, or None on failure.
        """
        url = f"{self.base_url}{endpoint}"
        try:
            response = self._session.post(
                url,
                json=data or {},
                timeout=self.timeout,
            )
            response.raise_for_status()
            self._clear_error()
            return response.json()
        except requests.exceptions.Timeout:
            self._record_error(f"Request timeout: POST {endpoint}")
            return None
        except requests.exceptions.ConnectionError as e:
            self._record_error(f"Connection error: POST {endpoint} - {e}")
            return None
        except requests.exceptions.HTTPError as e:
            self._record_error(
                f"HTTP error: POST {endpoint} - {e.response.status_code}"
            )
            return None
        except requests.exceptions.RequestException as e:
            self._record_error(f"Request failed: POST {endpoint} - {e}")
            return None
        except ValueError as e:
            self._record_error(f"Invalid JSON response: POST {endpoint} - {e}")
            return None

    def is_available(self) -> bool:
        """Check if the dashboard API is available.

        Returns:
            True if the API responds with status 200, False otherwise.
        """
        try:
            response = self._session.get(
                f"{self.base_url}/api/services",
                timeout=5,
            )
            if response.status_code == 200:
                self._clear_error()
                return True
            self._record_error(
                f"Dashboard unavailable: status {response.status_code}"
            )
            return False
        except requests.exceptions.RequestException as e:
            self._record_error(f"Dashboard unreachable: {e}")
            return False

    def get_services(self) -> list:
        """Get list of all services with their status.

        Returns:
            List of service dictionaries, or empty list on failure.
        """
        result = self._get("/api/services")
        if result and "services" in result:
            return result["services"]
        return []

    def start_service(self, service_id: str) -> bool:
        """Start a service by ID.

        Args:
            service_id: The unique identifier of the service.

        Returns:
            True if the service was started successfully, False otherwise.
        """
        logger.info("Starting service: %s", service_id)
        result = self._post(f"/api/services/{service_id}/start")
        success = result is not None and result.get("success", False)
        if success:
            logger.info("Service started successfully: %s", service_id)
        else:
            logger.warning("Failed to start service: %s", service_id)
        return success

    def stop_service(self, service_id: str) -> bool:
        """Stop a service by ID.

        Args:
            service_id: The unique identifier of the service.

        Returns:
            True if the service was stopped successfully, False otherwise.
        """
        logger.info("Stopping service: %s", service_id)
        result = self._post(f"/api/services/{service_id}/stop")
        success = result is not None and result.get("success", False)
        if success:
            logger.info("Service stopped successfully: %s", service_id)
        else:
            logger.warning("Failed to stop service: %s", service_id)
        return success

    def get_resource_summary(self) -> Optional[dict]:
        """Get GPU info, loaded models, and service summary.

        Returns:
            Resource summary dict, or None on failure.
        """
        return self._get("/api/resources/summary")

    def get_vram_status(self) -> Optional[dict]:
        """Get GPU VRAM status.

        Returns:
            Dict with GPU memory info (used_mb, total_mb, etc.), or None.
        """
        result = self._get("/api/vram/status")
        if result and "gpu" in result:
            return result["gpu"]
        return None

    def get_loaded_models(self) -> list:
        """Get list of Ollama models currently loaded in VRAM.

        Returns:
            List of model dictionaries, or empty list on failure.
        """
        result = self._get("/api/models/ollama/loaded")
        if result and "models" in result:
            return result["models"]
        return []

    def unload_model(self, model_name: str) -> bool:
        """Unload an Ollama model from VRAM.

        Args:
            model_name: Name of the model to unload.

        Returns:
            True if the model was unloaded successfully, False otherwise.
        """
        logger.info("Unloading model: %s", model_name)
        result = self._post("/api/models/ollama/unload", {"model_name": model_name})
        success = result is not None and result.get("success", False)
        if success:
            logger.info("Model unloaded successfully: %s", model_name)
        else:
            logger.warning("Failed to unload model: %s", model_name)
        return success

    def unload_all_models(self) -> int:
        """Unload all Ollama models from VRAM.

        Returns:
            Count of models successfully unloaded.
        """
        models = self.get_loaded_models()
        unloaded = 0
        for model in models:
            name = model.get("name")
            if not name:
                # Skip models without a valid name
                continue
            if self.unload_model(name):
                unloaded += 1
        logger.info("Unloaded %d model(s)", unloaded)
        return unloaded

    def close(self) -> None:
        """Close the session and release resources."""
        self._session.close()
