from __future__ import annotations

import logging
import queue
import threading
from tkinter import StringVar, ttk
from typing import Dict, List

from dashboard_app.controllers.ollama_controller import OllamaController, OllamaModel
from dashboard_app.controllers.vram_controller import VRAMMonitor


logger = logging.getLogger(__name__)


class ModelsTab(ttk.Frame):
    """Ollama models management tab."""

    def __init__(
        self,
        master,
        controller: OllamaController,
        vram_monitor: VRAMMonitor,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.controller = controller
        self.vram_monitor = vram_monitor
        self._queue: queue.Queue[List[OllamaModel]] = queue.Queue()
        self._loading = False
        self._row_loaded: Dict[str, bool] = {}

        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=8, pady=8)

        self.refresh_btn = ttk.Button(controls, text="Refresh", command=self.refresh)
        self.refresh_btn.pack(side="left")

        ttk.Label(controls, text="Filter:").pack(side="left", padx=(8, 2))
        self.filter_var = StringVar()
        self.filter_entry = ttk.Entry(controls, textvariable=self.filter_var, width=30)
        self.filter_entry.pack(side="left")
        self.filter_entry.bind("<KeyRelease>", lambda _e: self.refresh())

        self.unload_btn = ttk.Button(
            controls, text="Unload Selected", command=self._on_unload_selected
        )
        self.unload_btn.pack(side="left", padx=(8, 0))

        self.tree = ttk.Treeview(
            self,
            columns=("name", "status", "size", "modified"),
            show="headings",
            height=15,
        )
        self.tree.heading("name", text="Name")
        self.tree.heading("status", text="Status")
        self.tree.heading("size", text="Size")
        self.tree.heading("modified", text="Last Modified")
        self.tree.column("name", width=260, anchor="w")
        self.tree.column("status", width=80, anchor="center")
        self.tree.column("size", width=100, anchor="e")
        self.tree.column("modified", width=180, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.refresh()

    def refresh(self) -> None:
        """Trigger a background refresh of the models list."""
        if self._loading:
            return
        self._loading = True
        self.refresh_btn.state(["disabled"])

        def worker() -> None:
            models = self.controller.list_models_with_status(self.vram_monitor)
            self._queue.put(models)

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self._process_queue)

    def _process_queue(self) -> None:
        try:
            models = self._queue.get_nowait()
        except queue.Empty:
            # Keep polling until the worker delivers results.
            self.after(100, self._process_queue)
            return

        flt = self.filter_var.get().strip().lower()

        for row in self.tree.get_children():
            self.tree.delete(row)
        self._row_loaded.clear()

        for m in models:
            if flt and flt not in m.name.lower():
                continue
            size = f"{m.size / (1024**2):.1f} MB" if m.size else "n/a"
            status_text = "LOADED" if m.loaded else ""
            row_id = self.tree.insert(
                "",
                "end",
                values=(m.name, status_text, size, m.modified_at or ""),
            )
            self._row_loaded[row_id] = bool(m.loaded)

        self._loading = False
        self.refresh_btn.state(["!disabled"])

    def _on_unload_selected(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        row_id = selection[0]
        if not self._row_loaded.get(row_id):
            return
        name = self.tree.set(row_id, "name")
        if name:
            # Prefer HTTP API unload; fall back to CLI via VRAMMonitor.
            ok = self.controller.unload_model(name)
            if not ok:
                logger.info(
                    "HTTP unload failed for model %s; falling back to CLI", name
                )
                self.vram_monitor.unload_model(name)
            self.refresh()
