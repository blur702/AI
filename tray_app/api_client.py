"""
API Client for AI Dashboard

Provides a simple interface to communicate with the dashboard backend API.
"""

import requests
from typing import Optional


class DashboardAPI:
    """
    Client for the AI Dashboard API.
    
    Args:
        base_url: Full URL to the dashboard backend including port (e.g., "http://localhost:80").
                  Defaults to "http://localhost" (port 80).
    """

    def __init__(self, base_url: str = "http://localhost"):
        self.base_url = base_url.rstrip("/")
        self.timeout = 5  # seconds

    def _get(self, endpoint: str) -> Optional[dict]:
        """Make a GET request to the API."""
        try:
            response = requests.get(
                f"{self.base_url}{endpoint}",
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            return None

    def _post(self, endpoint: str, data: Optional[dict] = None) -> Optional[dict]:
        """Make a POST request to the API."""
        try:
            response = requests.post(
                f"{self.base_url}{endpoint}",
                json=data or {},
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            return None

    def is_available(self) -> bool:
        """Check if the dashboard API is available."""
        try:
            response = requests.get(
                f"{self.base_url}/api/services",
                timeout=2
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_services(self) -> list:
        """Get list of all services with their status."""
        result = self._get("/api/services")
        if result and "services" in result:
            return result["services"]
        return []

    def start_service(self, service_id: str) -> bool:
        """Start a service by ID."""
        result = self._post(f"/api/services/{service_id}/start")
        return result is not None and result.get("success", False)

    def stop_service(self, service_id: str) -> bool:
        """Stop a service by ID."""
        result = self._post(f"/api/services/{service_id}/stop")
        return result is not None and result.get("success", False)

    def get_resource_summary(self) -> Optional[dict]:
        """Get GPU info, loaded models, and service summary."""
        return self._get("/api/resources/summary")

    def get_vram_status(self) -> Optional[dict]:
        """Get GPU VRAM status."""
        result = self._get("/api/vram/status")
        if result and "gpu" in result:
            return result["gpu"]
        return None

    def get_loaded_models(self) -> list:
        """Get list of Ollama models currently loaded in VRAM."""
        result = self._get("/api/models/ollama/loaded")
        if result and "models" in result:
            return result["models"]
        return []

    def unload_model(self, model_name: str) -> bool:
        """Unload an Ollama model from VRAM."""
        result = self._post("/api/models/ollama/unload", {"model_name": model_name})
        return result is not None and result.get("success", False)

    def unload_all_models(self) -> int:
        """Unload all Ollama models from VRAM. Returns count of models unloaded."""
        models = self.get_loaded_models()
        unloaded = 0
        for model in models:
            name = model.get("name")
            if not name:
                # Skip models without a valid name
                continue
            if self.unload_model(name):
                unloaded += 1
        return unloaded
