from __future__ import annotations

from tkinter import Tk
from tkinter import ttk


# Color palette
PRIMARY = "#1976d2"
SECONDARY = "#dc004e"
SUCCESS = "#2e7d32"
WARNING = "#ed6c02"
ERROR = "#d32f2f"
BG_DARK = "#121212"
SURFACE_DARK = "#1e1e1e"
TEXT_PRIMARY = "#ffffff"
TEXT_MUTED = "#bbbbbb"


def apply_style(root: Tk, theme: str = "dark") -> None:
    """Configure ttk styles for the dashboard app."""
    style = ttk.Style(root)

    # Use the built-in "clam" theme as a base for better ttk support.
    try:
        style.theme_use("clam")
    except Exception:
        pass

    if theme == "dark":
        root.configure(bg=BG_DARK)
        style.configure(
            "TFrame",
            background=BG_DARK,
        )
        style.configure(
            "Card.TFrame",
            background=SURFACE_DARK,
            relief="ridge",
            borderwidth=1,
        )
        style.configure(
            "TLabel",
            background=BG_DARK,
            foreground=TEXT_PRIMARY,
        )
        style.configure(
            "Muted.TLabel",
            background=BG_DARK,
            foreground=TEXT_MUTED,
        )
        style.configure(
            "Header.TLabel",
            background=BG_DARK,
            foreground=TEXT_PRIMARY,
            font=("Segoe UI Semibold", 12),
        )
        style.configure(
            "StatusBar.TLabel",
            background=SURFACE_DARK,
            foreground=TEXT_MUTED,
        )
        style.configure(
            "TButton",
            padding=6,
        )
        style.map(
            "TButton",
            background=[("active", PRIMARY)],
            foreground=[("active", TEXT_PRIMARY)],
        )

        # Status chips
        style.configure(
            "StatusRunning.TLabel",
            background=SUCCESS,
            foreground="white",
        )
        style.configure(
            "StatusStopped.TLabel",
            background="#555555",
            foreground="white",
        )
        style.configure(
            "StatusError.TLabel",
            background=ERROR,
            foreground="white",
        )

