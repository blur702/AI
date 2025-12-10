from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional


class ResourcePanel(ttk.LabelFrame):
    """Collapsible panel showing GPU and service stats."""

    def __init__(
        self,
        master,
        on_toggle: Optional[Callable[[bool], None]] = None,
        **kwargs,
    ):
        super().__init__(master, text="Resources", **kwargs)
        self._expanded = True
        self._on_toggle = on_toggle
        self._unload_callback: Optional[Callable[[str], None]] = None
        self._auto_stop_callback: Optional[Callable[[bool], None]] = None
        self._timeout_callback: Optional[Callable[[int], None]] = None

        # Header row with toggle button.
        header_frame = ttk.Frame(self)
        header_frame.grid(row=0, column=0, sticky="we")
        header_label = ttk.Label(
            header_frame, text="GPU & Services", style="Header.TLabel"
        )
        header_label.pack(side="left")
        self.toggle_btn = ttk.Button(
            header_frame, text="Hide", width=6, command=self.toggle
        )
        self.toggle_btn.pack(side="right")

        # VRAM summary
        self.vram_label = ttk.Label(self, text="GPU: n/a", style="Muted.TLabel")
        self.vram_label.grid(row=1, column=0, sticky="w")

        self.vram_bar = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.vram_bar.grid(row=2, column=0, sticky="we", pady=(2, 4))

        # Loaded models
        models_frame = ttk.Frame(self)
        models_frame.grid(row=3, column=0, sticky="nsew", pady=(2, 0))
        ttk.Label(models_frame, text="Loaded Models:").pack(anchor="w")
        self.models_tree = ttk.Treeview(
            models_frame,
            columns=("name", "size"),
            show="headings",
            height=4,
        )
        self.models_tree.heading("name", text="Name")
        self.models_tree.heading("size", text="Size")
        self.models_tree.column("name", width=200, anchor="w")
        self.models_tree.column("size", width=80, anchor="e")
        self.models_tree.pack(side="left", fill="x", expand=True)
        unload_btn = ttk.Button(
            models_frame, text="Unload Selected", command=self._on_unload_clicked
        )
        unload_btn.pack(side="left", padx=(4, 0))

        # GPU processes
        procs_frame = ttk.Frame(self)
        procs_frame.grid(row=4, column=0, sticky="nsew", pady=(2, 0))
        ttk.Label(procs_frame, text="GPU Processes:").pack(anchor="w")
        self.processes_tree = ttk.Treeview(
            procs_frame,
            columns=("pid", "name", "mem"),
            show="headings",
            height=4,
        )
        self.processes_tree.heading("pid", text="PID")
        self.processes_tree.heading("name", text="Name")
        self.processes_tree.heading("mem", text="Mem (MB)")
        self.processes_tree.column("pid", width=60, anchor="e")
        self.processes_tree.column("name", width=160, anchor="w")
        self.processes_tree.column("mem", width=80, anchor="e")
        self.processes_tree.pack(fill="x", expand=True)

        # Auto-stop controls
        controls_frame = ttk.Frame(self)
        controls_frame.grid(row=5, column=0, sticky="we", pady=(4, 0))
        self.auto_stop_var = tk.BooleanVar(value=False)
        self.auto_stop_check = ttk.Checkbutton(
            controls_frame,
            text="Auto-stop idle GPU services",
            variable=self.auto_stop_var,
            command=self._on_auto_stop_changed,
        )
        self.auto_stop_check.pack(side="left")

        ttk.Label(controls_frame, text="Idle timeout (min):").pack(
            side="left", padx=(8, 2)
        )
        self.timeout_var = tk.IntVar(value=30)
        self.timeout_combo = ttk.Combobox(
            controls_frame,
            textvariable=self.timeout_var,
            values=[5, 15, 30, 60, 120],
            width=5,
            state="readonly",
        )
        self.timeout_combo.pack(side="left")
        self.timeout_combo.bind("<<ComboboxSelected>>", self._on_timeout_changed)

        self.columnconfigure(0, weight=1)

    # ------------------------------------------------------------------ #
    # Public callbacks registration
    # ------------------------------------------------------------------ #

    def add_model_unload_callback(self, callback: Callable[[str], None]) -> None:
        self._unload_callback = callback

    def add_auto_stop_callback(self, callback: Callable[[bool], None]) -> None:
        self._auto_stop_callback = callback

    def add_timeout_callback(self, callback: Callable[[int], None]) -> None:
        self._timeout_callback = callback

    # ------------------------------------------------------------------ #
    # Expand / collapse
    # ------------------------------------------------------------------ #

    def set_expanded(self, expanded: bool) -> None:
        """Expand or collapse the resource panel contents."""
        self._expanded = bool(expanded)
        widgets = [
            self.vram_label,
            self.vram_bar,
            self.models_tree.master,
            self.processes_tree.master,
            self.auto_stop_check.master,
        ]
        if self._expanded:
            self.toggle_btn.configure(text="Hide")
            # Re-grid main sections (positions fixed in __init__)
            self.vram_label.grid(row=1, column=0, sticky="w")
            self.vram_bar.grid(row=2, column=0, sticky="we", pady=(2, 4))
            self.models_tree.master.grid(row=3, column=0, sticky="nsew", pady=(2, 0))
            self.processes_tree.master.grid(row=4, column=0, sticky="nsew", pady=(2, 0))
            self.auto_stop_check.master.grid(row=5, column=0, sticky="we", pady=(4, 0))
        else:
            self.toggle_btn.configure(text="Show")
            for w in widgets:
                w.grid_remove()

        if self._on_toggle is not None:
            try:
                self._on_toggle(self._expanded)
            except Exception:
                pass

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    # ------------------------------------------------------------------ #
    # Internal UI event handlers
    # ------------------------------------------------------------------ #

    def _on_unload_clicked(self) -> None:
        if self._unload_callback is None:
            return
        selection = self.models_tree.selection()
        if not selection:
            return
        row_id = selection[0]
        name = self.models_tree.set(row_id, "name")
        if name:
            try:
                self._unload_callback(name)
            except Exception:
                pass

    def _on_auto_stop_changed(self) -> None:
        if self._auto_stop_callback is not None:
            try:
                self._auto_stop_callback(bool(self.auto_stop_var.get()))
            except Exception:
                pass

    def _on_timeout_changed(self, _event) -> None:
        if self._timeout_callback is not None:
            try:
                self._timeout_callback(int(self.timeout_var.get()))
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Data update
    # ------------------------------------------------------------------ #

    def update_from_data(
        self,
        gpu_stats: Dict[str, Any] | None = None,
        models: List[Dict[str, Any]] | None = None,
        processes: List[Dict[str, Any]] | None = None,
        auto_stop_enabled: Optional[bool] = None,
        idle_timeout_minutes: Optional[int] = None,
    ) -> None:
        if gpu_stats:
            agg = gpu_stats.get("aggregate", gpu_stats)
            total = agg.get("total_mb") or agg.get("total_vram")
            used = agg.get("used_mb") or agg.get("used_vram")
            if total and used is not None:
                pct = min(100, max(0, int(used * 100 / total)))
                self.vram_bar["value"] = pct
                label = f"GPU: {used:.0f} / {total:.0f} MB ({pct}%)"
                gpus = gpu_stats.get("gpus") or []
                if isinstance(gpus, list) and len(gpus) > 1:
                    label += f" • {len(gpus)} GPUs"
                self.vram_label.configure(text=label)

        if models is not None:
            for row in self.models_tree.get_children():
                self.models_tree.delete(row)
            for m in models:
                name = m.get("name", "")
                size = m.get("size_mb") or m.get("size")
                size_text = f"{size:.1f}" if isinstance(size, (int, float)) else ""
                self.models_tree.insert("", "end", values=(name, size_text))

        if processes is not None:
            for row in self.processes_tree.get_children():
                self.processes_tree.delete(row)
            for p in processes:
                pid = p.get("pid") or p.get("id")
                name = p.get("name", "")
                mem = p.get("memory_mb") or p.get("memory")
                mem_text = f"{mem:.1f}" if isinstance(mem, (int, float)) else ""
                self.processes_tree.insert("", "end", values=(pid, name, mem_text))

        if auto_stop_enabled is not None:
            self.auto_stop_var.set(bool(auto_stop_enabled))

        if idle_timeout_minutes is not None:
            self.timeout_var.set(int(idle_timeout_minutes))
