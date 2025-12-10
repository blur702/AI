from __future__ import annotations

from tkinter import ttk
from typing import Callable, Dict, Any


class ServiceCard(ttk.Frame):
    """Card-like widget representing a single service."""

    def __init__(
        self,
        master,
        status: Dict[str, Any],
        on_start: Callable[[str], None],
        on_stop: Callable[[str], None],
        on_open: Callable[[Dict[str, Any]], None] | None = None,
        **kwargs,
    ):
        super().__init__(master, style="Card.TFrame", padding=8, **kwargs)
        self.service_id = status["service_id"]
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_open = on_open

        self.name_label = ttk.Label(self, text=status["name"], style="Header.TLabel")
        self.name_label.grid(row=0, column=0, sticky="w")

        self.status_label = ttk.Label(self, text="", width=14)
        self.status_label.grid(row=0, column=1, sticky="e", padx=(8, 0))

        section = status.get("section") or "Main"
        port = status.get("port") or 0
        self.desc_label = ttk.Label(
            self,
            text=f"Port {port} • {section}",
            style="Muted.TLabel",
        )
        self.desc_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=2, column=0, columnspan=2, sticky="we", pady=(8, 0))

        self.start_btn = ttk.Button(
            btn_frame, text="Start", command=lambda: self._on_start(self.service_id)
        )
        self.start_btn.pack(side="left")

        self.stop_btn = ttk.Button(
            btn_frame, text="Stop", command=lambda: self._on_stop(self.service_id)
        )
        self.stop_btn.pack(side="left", padx=(4, 0))

        if on_open is not None:
            self.open_btn = ttk.Button(
                btn_frame, text="Open", command=lambda: on_open(status)
            )
            self.open_btn.pack(side="left", padx=(4, 0))
        else:
            self.open_btn = None

        self.columnconfigure(0, weight=1)
        self.update_status(status)

    def update_status(self, status: Dict[str, Any]) -> None:
        """Refresh the visual state based on latest status dict."""
        state = (status.get("status") or "stopped").lower()
        style = "StatusStopped.TLabel"
        text = state.capitalize()

        if state == "running":
            style = "StatusRunning.TLabel"
        elif state in {"error"}:
            style = "StatusError.TLabel"
            if status.get("error"):
                text = "Error"

        idle_seconds = status.get("idle_seconds") or 0.0
        if state == "running" and idle_seconds:
            mins = int(idle_seconds // 60)
            text = f"Running ({mins}m idle)" if mins else "Running"

        # Indicate GPU-intensive services in the description.
        try:
            from dashboard.backend.services_config import GPU_INTENSIVE_SERVICES

            if status.get("service_id") in GPU_INTENSIVE_SERVICES:
                current = self.desc_label.cget("text")
                if "[GPU]" not in current:
                    self.desc_label.configure(text=f"{current} • [GPU]")
        except Exception:
            pass

        self.status_label.configure(text=text, style=style)

        if state in {"running", "starting"}:
            self.start_btn.state(["disabled"])
            self.stop_btn.state(["!disabled"])
        else:
            self.start_btn.state(["!disabled"])
            self.stop_btn.state(["disabled"])
