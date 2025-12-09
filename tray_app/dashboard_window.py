"""
Graphical Dashboard Window for AI Tray App

A popup window that displays service status, VRAM usage, and loaded models
in a compact, visually appealing format.
"""

import tkinter as tk
from typing import Callable, Optional

# Color scheme
COLORS = {
    "bg": "#1e1e2e",           # Dark background
    "card_bg": "#2a2a3e",      # Card background
    "text": "#cdd6f4",         # Primary text
    "text_dim": "#6c7086",     # Dimmed text
    "green": "#a6e3a1",        # Running/success
    "red": "#f38ba8",          # Stopped/error
    "orange": "#fab387",       # Warning/starting
    "blue": "#89b4fa",         # Info/accent
    "border": "#45475a",       # Border color
}


class DashboardWindow:
    """Popup dashboard window showing service status and VRAM info."""

    def __init__(
        self,
        on_start_service: Callable[[str, str], None],
        on_stop_service: Callable[[str, str], None],
        on_unload_model: Callable[[str], None],
        on_open_dashboard: Callable[[], None],
    ) -> None:
        """Initialize the dashboard window.

        Args:
            on_start_service: Callback for starting a service (id, name).
            on_stop_service: Callback for stopping a service (id, name).
            on_unload_model: Callback for unloading a model (name).
            on_open_dashboard: Callback for opening the web dashboard.
        """
        self.on_start_service = on_start_service
        self.on_stop_service = on_stop_service
        self.on_unload_model = on_unload_model
        self.on_open_dashboard = on_open_dashboard

        self.window: Optional[tk.Tk] = None
        self.services: list = []
        self.gpu_info: Optional[dict] = None
        self.loaded_models: list = []
        self.api_available = False

    def update_data(
        self,
        services: list,
        gpu_info: Optional[dict],
        loaded_models: list,
        api_available: bool,
    ) -> None:
        """Update the dashboard data.

        Args:
            services: List of service dictionaries.
            gpu_info: GPU/VRAM info dictionary.
            loaded_models: List of loaded model dictionaries.
            api_available: Whether the API is available.
        """
        self.services = services
        self.gpu_info = gpu_info
        self.loaded_models = loaded_models
        self.api_available = api_available

        # Refresh display if window is open
        if self.window and self.window.winfo_exists():
            self._refresh_display()

    def show(self) -> None:
        """Show the dashboard window."""
        if self.window and self.window.winfo_exists():
            self.window.lift()
            self.window.focus_force()
            return

        self._create_window()

    def hide(self) -> None:
        """Hide the dashboard window."""
        if self.window:
            self.window.withdraw()

    def _create_window(self) -> None:
        """Create the dashboard window."""
        self.window = tk.Tk()
        self.window.title("AI Services Dashboard")
        self.window.configure(bg=COLORS["bg"])
        self.window.overrideredirect(True)  # Remove window decorations

        # Set window size and position (near system tray)
        width = 400
        height = 500
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        x = screen_width - width - 20
        y = screen_height - height - 60  # Above taskbar
        self.window.geometry(f"{width}x{height}+{x}+{y}")

        # Make window stay on top
        self.window.attributes("-topmost", True)

        # Add border effect
        self.window.configure(highlightbackground=COLORS["border"], highlightthickness=1)

        # Close on losing focus
        self.window.bind("<FocusOut>", self._on_focus_out)
        self.window.bind("<Escape>", lambda e: self.hide())

        # Create main frame
        self.main_frame = tk.Frame(self.window, bg=COLORS["bg"])
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self._create_header()
        self._create_vram_section()
        self._create_services_section()
        self._create_models_section()
        self._create_footer()

        self.window.focus_force()

    def _on_focus_out(self, event: tk.Event) -> None:
        """Handle focus out event."""
        # Only hide if focus went to a different window
        if event.widget == self.window:
            self.window.after(100, self._check_focus)

    def _check_focus(self) -> None:
        """Check if window still has focus."""
        if self.window and self.window.winfo_exists():
            try:
                focused = self.window.focus_get()
                if focused is None:
                    self.hide()
            except tk.TclError:
                pass

    def _create_header(self) -> None:
        """Create the header section."""
        header = tk.Frame(self.main_frame, bg=COLORS["bg"])
        header.pack(fill=tk.X, pady=(0, 10))

        # Title
        title = tk.Label(
            header,
            text="AI Services",
            font=("Segoe UI", 16, "bold"),
            fg=COLORS["text"],
            bg=COLORS["bg"],
        )
        title.pack(side=tk.LEFT)

        # Status indicator
        status_color = COLORS["green"] if self.api_available else COLORS["red"]
        status_text = "Connected" if self.api_available else "Offline"
        status = tk.Label(
            header,
            text=f"● {status_text}",
            font=("Segoe UI", 10),
            fg=status_color,
            bg=COLORS["bg"],
        )
        status.pack(side=tk.RIGHT)

    def _create_vram_section(self) -> None:
        """Create the VRAM usage section."""
        vram_frame = tk.Frame(self.main_frame, bg=COLORS["card_bg"])
        vram_frame.pack(fill=tk.X, pady=(0, 10))

        # Add padding inside the card
        inner = tk.Frame(vram_frame, bg=COLORS["card_bg"])
        inner.pack(fill=tk.X, padx=10, pady=8)

        # VRAM label
        vram_label = tk.Label(
            inner,
            text="GPU VRAM",
            font=("Segoe UI", 10),
            fg=COLORS["text_dim"],
            bg=COLORS["card_bg"],
        )
        vram_label.pack(anchor=tk.W)

        if self.gpu_info:
            used_mb = self.gpu_info.get("used_mb", 0)
            total_mb = self.gpu_info.get("total_mb", 1)
            percent = int((used_mb / total_mb) * 100) if total_mb > 0 else 0

            # Progress bar frame
            progress_frame = tk.Frame(inner, bg=COLORS["card_bg"])
            progress_frame.pack(fill=tk.X, pady=(5, 0))

            # Create custom progress bar
            bar_width = 360
            bar_height = 8
            canvas = tk.Canvas(
                progress_frame,
                width=bar_width,
                height=bar_height,
                bg=COLORS["border"],
                highlightthickness=0,
            )
            canvas.pack(side=tk.LEFT)

            # Fill based on usage
            fill_color = COLORS["green"]
            if percent > 80:
                fill_color = COLORS["red"]
            elif percent > 60:
                fill_color = COLORS["orange"]

            fill_width = int(bar_width * (percent / 100))
            canvas.create_rectangle(0, 0, fill_width, bar_height, fill=fill_color, outline="")

            # VRAM text
            used_gb = used_mb / 1024
            total_gb = total_mb / 1024
            vram_text = tk.Label(
                inner,
                text=f"{used_gb:.1f} GB / {total_gb:.1f} GB ({percent}%)",
                font=("Segoe UI", 11),
                fg=COLORS["text"],
                bg=COLORS["card_bg"],
            )
            vram_text.pack(anchor=tk.W, pady=(5, 0))
        else:
            no_vram = tk.Label(
                inner,
                text="VRAM info unavailable",
                font=("Segoe UI", 10),
                fg=COLORS["text_dim"],
                bg=COLORS["card_bg"],
            )
            no_vram.pack(anchor=tk.W)

    def _create_services_section(self) -> None:
        """Create the services section."""
        # Section header
        header = tk.Label(
            self.main_frame,
            text="Services",
            font=("Segoe UI", 11, "bold"),
            fg=COLORS["text"],
            bg=COLORS["bg"],
        )
        header.pack(anchor=tk.W, pady=(5, 5))

        # Scrollable frame for services
        services_canvas = tk.Canvas(
            self.main_frame,
            bg=COLORS["bg"],
            highlightthickness=0,
            height=150,
        )
        services_canvas.pack(fill=tk.X)

        services_frame = tk.Frame(services_canvas, bg=COLORS["bg"])
        services_canvas.create_window((0, 0), window=services_frame, anchor=tk.NW)

        if not self.services:
            no_services = tk.Label(
                services_frame,
                text="No services available",
                font=("Segoe UI", 10),
                fg=COLORS["text_dim"],
                bg=COLORS["bg"],
            )
            no_services.pack(anchor=tk.W)
        else:
            for service in self.services:
                self._create_service_row(services_frame, service)

    def _create_service_row(self, parent: tk.Frame, service: dict) -> None:
        """Create a row for a service."""
        row = tk.Frame(parent, bg=COLORS["card_bg"])
        row.pack(fill=tk.X, pady=2)

        inner = tk.Frame(row, bg=COLORS["card_bg"])
        inner.pack(fill=tk.X, padx=8, pady=6)

        # Service name and status
        left = tk.Frame(inner, bg=COLORS["card_bg"])
        left.pack(side=tk.LEFT, fill=tk.X, expand=True)

        status = service.get("status", "stopped")
        status_colors = {
            "running": COLORS["green"],
            "starting": COLORS["orange"],
            "error": COLORS["red"],
            "stopped": COLORS["text_dim"],
        }
        status_color = status_colors.get(status, COLORS["text_dim"])

        name_label = tk.Label(
            left,
            text=f"● {service.get('name', 'Unknown')}",
            font=("Segoe UI", 10),
            fg=status_color,
            bg=COLORS["card_bg"],
        )
        name_label.pack(side=tk.LEFT)

        # Action button
        service_id = service.get("id", "")
        service_name = service.get("name", service_id)
        is_external = service.get("external", False)

        if not is_external:
            if status == "running":
                btn = tk.Button(
                    inner,
                    text="Stop",
                    font=("Segoe UI", 8),
                    fg=COLORS["text"],
                    bg=COLORS["border"],
                    activebackground=COLORS["red"],
                    relief=tk.FLAT,
                    cursor="hand2",
                    command=lambda sid=service_id, sn=service_name: self.on_stop_service(sid, sn),
                )
                btn.pack(side=tk.RIGHT)
            elif status in ("stopped", "error"):
                btn = tk.Button(
                    inner,
                    text="Start",
                    font=("Segoe UI", 8),
                    fg=COLORS["text"],
                    bg=COLORS["border"],
                    activebackground=COLORS["green"],
                    relief=tk.FLAT,
                    cursor="hand2",
                    command=lambda sid=service_id, sn=service_name: self.on_start_service(sid, sn),
                )
                btn.pack(side=tk.RIGHT)

    def _create_models_section(self) -> None:
        """Create the loaded models section."""
        # Section header
        header = tk.Label(
            self.main_frame,
            text="Loaded Models",
            font=("Segoe UI", 11, "bold"),
            fg=COLORS["text"],
            bg=COLORS["bg"],
        )
        header.pack(anchor=tk.W, pady=(10, 5))

        models_frame = tk.Frame(self.main_frame, bg=COLORS["bg"])
        models_frame.pack(fill=tk.X)

        if not self.loaded_models:
            no_models = tk.Label(
                models_frame,
                text="No models loaded",
                font=("Segoe UI", 10),
                fg=COLORS["text_dim"],
                bg=COLORS["bg"],
            )
            no_models.pack(anchor=tk.W)
        else:
            for model in self.loaded_models:
                self._create_model_row(models_frame, model)

    def _create_model_row(self, parent: tk.Frame, model: dict) -> None:
        """Create a row for a loaded model."""
        row = tk.Frame(parent, bg=COLORS["card_bg"])
        row.pack(fill=tk.X, pady=2)

        inner = tk.Frame(row, bg=COLORS["card_bg"])
        inner.pack(fill=tk.X, padx=8, pady=6)

        # Model name and size
        name = model.get("name", "Unknown")
        size = model.get("size", "")

        name_label = tk.Label(
            inner,
            text=name,
            font=("Segoe UI", 10),
            fg=COLORS["blue"],
            bg=COLORS["card_bg"],
        )
        name_label.pack(side=tk.LEFT)

        if size:
            size_label = tk.Label(
                inner,
                text=f"({size})",
                font=("Segoe UI", 9),
                fg=COLORS["text_dim"],
                bg=COLORS["card_bg"],
            )
            size_label.pack(side=tk.LEFT, padx=(5, 0))

        # Unload button
        btn = tk.Button(
            inner,
            text="Unload",
            font=("Segoe UI", 8),
            fg=COLORS["text"],
            bg=COLORS["border"],
            activebackground=COLORS["orange"],
            relief=tk.FLAT,
            cursor="hand2",
            command=lambda n=name: self.on_unload_model(n),
        )
        btn.pack(side=tk.RIGHT)

    def _create_footer(self) -> None:
        """Create the footer with action buttons."""
        footer = tk.Frame(self.main_frame, bg=COLORS["bg"])
        footer.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))

        # Open Dashboard button
        open_btn = tk.Button(
            footer,
            text="Open Dashboard",
            font=("Segoe UI", 10),
            fg=COLORS["text"],
            bg=COLORS["blue"],
            activebackground=COLORS["border"],
            relief=tk.FLAT,
            cursor="hand2",
            padx=15,
            pady=5,
            command=self.on_open_dashboard,
        )
        open_btn.pack(side=tk.LEFT)

        # Close button
        close_btn = tk.Button(
            footer,
            text="Close",
            font=("Segoe UI", 10),
            fg=COLORS["text"],
            bg=COLORS["border"],
            activebackground=COLORS["text_dim"],
            relief=tk.FLAT,
            cursor="hand2",
            padx=15,
            pady=5,
            command=self.hide,
        )
        close_btn.pack(side=tk.RIGHT)

    def _refresh_display(self) -> None:
        """Refresh the entire display."""
        if not self.window or not self.window.winfo_exists():
            return

        # Clear and rebuild
        for widget in self.main_frame.winfo_children():
            widget.destroy()

        self._create_header()
        self._create_vram_section()
        self._create_services_section()
        self._create_models_section()
        self._create_footer()

    def destroy(self) -> None:
        """Destroy the window."""
        if self.window:
            self.window.destroy()
            self.window = None
