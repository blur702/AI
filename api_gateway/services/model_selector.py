"""
Ollama Model Selection Service for Price Comparison.

Automatically selects the best available Ollama model for product comparison
tasks based on capabilities and availability. Uses cached model list with
periodic refresh to avoid blocking the event loop.
"""

import asyncio
import subprocess
import time
from threading import Lock

from ..utils.logger import get_logger

logger = get_logger("api_gateway.services.model_selector")

# Model preference order for product comparison (structured output tasks)
# Priority: qwen2.5 > llama3.1 > mistral, then fallbacks
PREFERRED_MODELS = [
    "qwen2.5",  # Best for structured output and instruction following
    "llama3.1",  # 128K context, strong capabilities
    "mistral",  # Efficient general-purpose model
    "qwen2",  # Fallback to Qwen 2
    "llama3.2",  # Latest Llama with good performance
    "llama3",  # Solid fallback
    "qwen",  # Original Qwen
]

# Cache for available models
_model_cache: list[str] = []
_cache_timestamp: float = 0.0
_cache_lock = Lock()
CACHE_TTL_SECONDS = 300  # 5 minutes


def _fetch_ollama_models_sync() -> list[str]:
    """
    Synchronously fetch list of available Ollama models.

    This is the blocking subprocess call that should only be run
    in a background thread or during cache refresh.

    Returns:
        List of model names (e.g., ["qwen2.5:latest", "llama3.1:8b"])
    """
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning("ollama list failed: %s", result.stderr)
            return []

        models = []
        for line in result.stdout.strip().split("\n")[1:]:  # Skip header
            parts = line.split()
            if parts:
                models.append(parts[0])  # Model name is first column
        return models
    except subprocess.TimeoutExpired:
        logger.error("ollama list timed out")
        return []
    except FileNotFoundError:
        logger.error("ollama command not found")
        return []
    except Exception as e:
        logger.error("Failed to list Ollama models: %s", e)
        return []


def get_cached_models() -> list[str]:
    """
    Get cached list of available models, refreshing if stale.

    Thread-safe access to the model cache. Returns cached list if
    still valid, otherwise returns empty list (async refresh recommended).

    Returns:
        List of cached model names, or empty list if cache is empty/stale
    """
    global _model_cache, _cache_timestamp
    with _cache_lock:
        if time.time() - _cache_timestamp < CACHE_TTL_SECONDS and _model_cache:
            return _model_cache.copy()
        return []


def _update_cache(models: list[str]) -> None:
    """Update the model cache with new data."""
    global _model_cache, _cache_timestamp
    with _cache_lock:
        _model_cache = models
        _cache_timestamp = time.time()
        logger.debug("Model cache updated with %d models", len(models))


async def refresh_model_cache() -> list[str]:
    """
    Refresh the model cache asynchronously.

    Runs the blocking subprocess call in a background thread to avoid
    blocking the event loop.

    Returns:
        List of available model names
    """
    models = await asyncio.to_thread(_fetch_ollama_models_sync)
    _update_cache(models)
    return models


async def get_available_ollama_models_async() -> list[str]:
    """
    Get list of available Ollama models without blocking the event loop.

    Returns cached models if available and fresh, otherwise refreshes
    the cache in a background thread.

    Returns:
        List of model names (e.g., ["qwen2.5:latest", "llama3.1:8b"])
    """
    cached = get_cached_models()
    if cached:
        return cached

    # Cache is stale or empty, refresh it
    return await refresh_model_cache()


def get_available_ollama_models() -> list[str]:
    """
    Get list of available Ollama models (sync version for non-async contexts).

    Returns cached models if available, otherwise fetches synchronously.
    Prefer using get_available_ollama_models_async() in async contexts.

    Returns:
        List of model names (e.g., ["qwen2.5:latest", "llama3.1:8b"])
    """
    cached = get_cached_models()
    if cached:
        return cached

    # Cache is stale or empty, refresh synchronously
    models = _fetch_ollama_models_sync()
    _update_cache(models)
    return models


async def select_best_model_async() -> str | None:
    """
    Select the best available Ollama model for product comparison (async).

    Checks available models against preference list and returns the
    highest-priority match. Falls back to any available model if
    none of the preferred models are found.

    Returns:
        Model name string (e.g., "qwen2.5:latest") or None if no models available
    """
    available = await get_available_ollama_models_async()
    if not available:
        logger.error("No Ollama models available")
        return None

    # Try preferred models in order
    for preferred in PREFERRED_MODELS:
        for model in available:
            # Match family name (e.g., "qwen2.5" matches "qwen2.5:latest")
            if model.lower().startswith(preferred.lower()):
                logger.info("Selected model for price comparison: %s", model)
                return model

    # Fallback to first available model
    fallback = available[0]
    logger.warning("No preferred models found, using fallback: %s", fallback)
    return fallback


def select_best_model() -> str | None:
    """
    Select the best available Ollama model for product comparison (sync).

    Checks available models against preference list and returns the
    highest-priority match. Falls back to any available model if
    none of the preferred models are found.

    Prefer using select_best_model_async() in async contexts.

    Returns:
        Model name string (e.g., "qwen2.5:latest") or None if no models available
    """
    available = get_available_ollama_models()
    if not available:
        logger.error("No Ollama models available")
        return None

    # Try preferred models in order
    for preferred in PREFERRED_MODELS:
        for model in available:
            # Match family name (e.g., "qwen2.5" matches "qwen2.5:latest")
            if model.lower().startswith(preferred.lower()):
                logger.info("Selected model for price comparison: %s", model)
                return model

    # Fallback to first available model
    fallback = available[0]
    logger.warning("No preferred models found, using fallback: %s", fallback)
    return fallback


async def ensure_model_available_async(model_name: str | None = None) -> str:
    """
    Ensure a suitable model is available, with optional override (async).

    Args:
        model_name: Optional specific model to use (overrides auto-selection)

    Returns:
        Model name to use

    Raises:
        RuntimeError: If no models are available
    """
    if model_name:
        # Verify specified model exists
        available = await get_available_ollama_models_async()
        if model_name in available:
            return model_name
        # Check if model name matches as prefix (e.g., "qwen2.5" matches "qwen2.5:latest")
        for model in available:
            if model.lower().startswith(model_name.lower()):
                logger.info("Found matching model: %s for requested %s", model, model_name)
                return model
        logger.warning("Requested model %s not found, auto-selecting", model_name)

    selected = await select_best_model_async()
    if not selected:
        raise RuntimeError("No Ollama models available for price comparison")
    return selected


def ensure_model_available(model_name: str | None = None) -> str:
    """
    Ensure a suitable model is available, with optional override (sync).

    Prefer using ensure_model_available_async() in async contexts.

    Args:
        model_name: Optional specific model to use (overrides auto-selection)

    Returns:
        Model name to use

    Raises:
        RuntimeError: If no models are available
    """
    if model_name:
        # Verify specified model exists
        available = get_available_ollama_models()
        if model_name in available:
            return model_name
        # Check if model name matches as prefix (e.g., "qwen2.5" matches "qwen2.5:latest")
        for model in available:
            if model.lower().startswith(model_name.lower()):
                logger.info("Found matching model: %s for requested %s", model, model_name)
                return model
        logger.warning("Requested model %s not found, auto-selecting", model_name)

    selected = select_best_model()
    if not selected:
        raise RuntimeError("No Ollama models available for price comparison")
    return selected
