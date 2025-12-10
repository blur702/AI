from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


try:
    # Trust existing vram_manager.py layout.
    import vram_manager  # type: ignore
except Exception:  # pragma: no cover - defensive import
    vram_manager = None  # type: ignore[assignment]


class VRAMMonitor:
    """Background VRAM monitor that wraps vram_manager functions.

    Periodically polls GPU stats, loaded models, and GPU processes, caching the
    latest values for fast, thread-safe access from the UI.
    """

    def __init__(self, poll_interval: int = 3) -> None:
        self._lock = threading.Lock()
        self._gpu_stats: Dict[str, Any] = {}
        self._loaded_models: List[Dict[str, Any]] = []
        self._gpu_processes: List[Dict[str, Any]] = []
        self._poll_interval = poll_interval
        self._stop_flag = False
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ #
    # Thread management
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag = False
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_flag = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _poll_loop(self) -> None:
        if vram_manager is None:
            logger.info("VRAMMonitor disabled: vram_manager module not available")
            return

        while not self._stop_flag:
            try:
                gpu = {}
                models: List[Dict[str, Any]] = []
                procs: List[Dict[str, Any]] = []

                # Map backend function names to desktop expectations.
                try:
                    # get_gpu_info() -> dict with name, total_mb, used_mb, free_mb, utilization
                    gpu = vram_manager.get_gpu_info()  # type: ignore[assignment]
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug("get_gpu_info failed: %s", exc)

                try:
                    # get_ollama_models() -> list of loaded models from `ollama ps`
                    models = vram_manager.get_ollama_models()  # type: ignore[assignment]
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug("get_ollama_models failed: %s", exc)

                try:
                    procs = vram_manager.get_gpu_processes()  # type: ignore[assignment]
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug("get_gpu_processes failed: %s", exc)

                with self._lock:
                    self._gpu_stats = gpu or {}
                    self._loaded_models = models or []
                    self._gpu_processes = procs or []
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("VRAMMonitor polling error: %s", exc)

            time.sleep(self._poll_interval)

    # ------------------------------------------------------------------ #
    # Public accessors
    # ------------------------------------------------------------------ #

    def get_gpu_stats(self) -> Dict[str, Any]:
        """Return cached GPU info (full structure including aggregate/gpus)."""
        with self._lock:
            return dict(self._gpu_stats)

    def get_loaded_models(self) -> List[Dict[str, Any]]:
        """Return cached loaded Ollama models (from ollama ps)."""
        with self._lock:
            return list(self._loaded_models)

    def get_gpu_processes(self) -> List[Dict[str, Any]]:
        """Return cached processes using the GPU."""
        with self._lock:
            return list(self._gpu_processes)

    def unload_model(self, model_name: str) -> bool:
        """Unload a single Ollama model via vram_manager.stop_ollama_model."""
        if vram_manager is None:
            return False
        try:
            success, error = vram_manager.stop_ollama_model(model_name)  # type: ignore[arg-type]
            if not success and error:
                logger.warning("CLI unload of model %s failed: %s", model_name, error)
            return bool(success)
        except Exception as exc:
            logger.warning("Failed to unload model %s: %s", model_name, exc)
            return False
