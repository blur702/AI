"""
Shared embedding utility for Weaviate collections.

Provides a centralized function to generate embeddings via Ollama API,
used by all ingestion services (doc_ingestion, code_ingestion, talking_head_schema).
"""

from __future__ import annotations

import httpx

from ..config import settings


def get_embedding(text: str) -> list[float]:
    """
    Generate embedding vector for text using Ollama API.

    Uses the configured OLLAMA_API_ENDPOINT and OLLAMA_EMBEDDING_MODEL
    from settings to ensure consistent embedding generation across all services.

    Args:
        text: Text to embed

    Returns:
        Embedding vector as list of floats

    Raises:
        httpx.HTTPStatusError: If the Ollama API returns an error response
        httpx.TimeoutException: If the request times out (30s default)
    """
    response = httpx.post(
        f"{settings.OLLAMA_API_ENDPOINT}/api/embeddings",
        json={"model": settings.OLLAMA_EMBEDDING_MODEL, "prompt": text},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["embedding"]
