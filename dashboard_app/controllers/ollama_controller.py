from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from dashboard_app.controllers.vram_controller import VRAMMonitor

OLLAMA_BASE_URL = "http://127.0.0.1:11434"


@dataclass
class OllamaModel:
    name: str
    size: int | None = None
    modified_at: str | None = None
    digest: str | None = None
    details: dict[str, Any] | None = None
    loaded: bool = False


class OllamaController:
    """High-level helper for interacting with a local Ollama instance."""

    def __init__(self, base_url: str = OLLAMA_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def list_models(self) -> list[OllamaModel]:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5.0)
            resp.raise_for_status()
        except Exception:
            return []

        data = resp.json()
        models: list[OllamaModel] = []
        for m in data.get("models", []):
            models.append(
                OllamaModel(
                    name=m.get("name", ""),
                    size=m.get("size"),
                    modified_at=m.get("modified_at"),
                    digest=m.get("digest"),
                    details=m.get("details"),
                )
            )
        return models

    def list_models_with_status(self, vram_monitor: VRAMMonitor) -> list[OllamaModel]:
        """List all models, marking which are currently loaded in VRAM."""
        all_models = self.list_models()
        loaded = vram_monitor.get_loaded_models()
        loaded_names = {m.get("name") for m in loaded if m.get("name")}

        for model in all_models:
            model.loaded = model.name in loaded_names
        return all_models

    def load_model(self, model: str, keep_alive: int = -1) -> bool:
        payload = {
            "model": model,
            "prompt": "",
            "keep_alive": keep_alive,
            "stream": False,
        }
        try:
            resp = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=60.0)
            return resp.status_code == 200
        except Exception:
            return False

    def unload_model(self, model: str) -> bool:
        payload = {
            "model": model,
            "prompt": "",
            "keep_alive": 0,
            "stream": False,
        }
        try:
            resp = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=30.0)
            return resp.status_code == 200
        except Exception:
            return False
