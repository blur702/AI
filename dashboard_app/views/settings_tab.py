from __future__ import annotations

from tkinter import ttk


class SettingsTab(ttk.Frame):
    """Settings and ingestion controls tab (UI scaffold)."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        ttk.Label(
            self,
            text=(
                "Ingestion controls require the dashboard backend API "
                "to be running.\nThis tab currently provides a placeholder "
                "for future integration."
            ),
            style="Muted.TLabel",
            wraplength=600,
            justify="left",
        ).pack(anchor="w", padx=8, pady=8)
