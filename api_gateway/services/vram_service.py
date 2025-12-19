"""
VRAM monitoring and management service.

Provides GPU status, loaded model tracking, and VRAM conflict detection
for AI services that require GPU resources.
"""

import importlib.util
from typing import Any

import httpx

from ..config import settings
from ..utils.exceptions import ServiceUnavailableError, VRAMConflictError
from ..utils.logger import logger


def _load_vram_manager():
    """Load the vram_manager module dynamically from configured path."""
    spec = importlib.util.spec_from_file_location("vram_manager", settings.VRAM_MANAGER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError("Unable to load vram_manager module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_vram_manager = _load_vram_manager()


class VRAMService:
    """
    GPU resource monitoring and management service.

    Provides static methods for checking GPU status, loaded models,
    and ensuring services have sufficient VRAM before execution.
    """

    @staticmethod
    def get_gpu_status() -> dict[str, Any]:
        """
        Get current GPU status including VRAM usage and processes.

        Returns:
            Dictionary with GPU info:
                - total_vram: Total GPU memory in MB
                - used_vram: Currently used GPU memory in MB
                - free_vram: Available GPU memory in MB
                - utilization: GPU utilization percentage
                - processes: List of GPU processes with PID, name, memory

        Raises:
            RuntimeError: If nvidia-smi is unavailable or GPU not detected
        """
        info = _vram_manager.get_gpu_info()
        return info

    @staticmethod
    def get_loaded_models() -> list[dict[str, Any]]:
        """
        Get list of currently loaded Ollama models in VRAM.

        Returns:
            List of model dictionaries with:
                - name: Model name (e.g., "llama2:latest")
                - size: Model size in bytes
                - modified: Last modified timestamp
        """
        return _vram_manager.get_ollama_models()

    @staticmethod
    async def ensure_service_ready(service_name: str) -> None:
        """
        Prepare GPU resources and verify service availability before job execution.

        For GPU-intensive services (comfyui, wan2gp, yue, diffrhythm, stable_audio, musicgen),
        this will:
        1. Check for conflicting GPU processes
        2. Stop any loaded Ollama models to free VRAM
        3. Verify service health via HTTP endpoint

        Args:
            service_name: Service identifier (e.g., "comfyui", "ollama")

        Raises:
            VRAMConflictError: If GPU is busy with another process
            ServiceUnavailableError: If service is not responding
        """
        gpu_intensive = [
            "comfyui",
            "wan2gp",
            "yue",
            "diffrhythm",
            "stable_audio",
            "musicgen",
        ]
        if service_name in gpu_intensive:
            processes = _vram_manager.get_gpu_processes()
            if processes:
                logger.warning(f"GPU conflict detected for service {service_name}: {processes}")
                raise VRAMConflictError("GPU is currently busy with another service")

            models = _vram_manager.get_ollama_models()
            for model in models:
                name = model.get("name")
                if name:
                    logger.info(f"Stopping Ollama model {name} to free VRAM")
                    _vram_manager.stop_ollama_model(name)

        if service_name == "ollama":
            logger.debug("Ensuring Ollama service is reachable")

        service_url = settings.SERVICES.get(service_name)
        if service_url and not await VRAMService.check_service_health(service_url):
            raise ServiceUnavailableError(
                f"Service {service_name} at {service_url} is not responding"
            )

    @staticmethod
    async def check_service_health(service_url: str) -> bool:
        """
        Check if a service is responding to HTTP requests.

        Args:
            service_url: Service HTTP endpoint (e.g., "http://localhost:8188")

        Returns:
            True if service responds with status < 500, False otherwise
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(service_url, timeout=5)
            return response.status_code < 500
        except Exception:  # noqa: BLE001
            logger.warning(f"Health check failed for {service_url}")
            return False
