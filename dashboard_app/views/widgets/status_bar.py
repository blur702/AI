from __future__ import annotations

from tkinter import ttk


class StatusBar(ttk.Frame):
    """Simple status bar shown at the bottom of the main window."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.label = ttk.Label(self, style="StatusBar.TLabel", anchor="w")
        self.label.pack(fill="x", padx=4, pady=2)

    def set_status(self, text: str) -> None:
        self.label.configure(text=text)

