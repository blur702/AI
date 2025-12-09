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
    "purple": "#cba6f7",       # Model color
    "border": "#45475a",       # Border color
}


class DashboardWindow:
    """Popup dashboard window showing service status and VRAM info."""

    def __init__(
        self,
        on_start_service: Callable[[str, str], None],
        on_stop_service: Callable[[str, str], None],
        on_unload_model: Callable[[str], None],
        on_unload_all_models: Callable[[], None],
        on_open_dashboard: Callable[[], None],
    ) -> None:
        """Initialize the dashboard window.

        Args:
            on_start_service: Callback for starting a service (id, name).
            on_stop_service: Callback for stopping a service (id, name).
            on_unload_model: Callback for unloading a model (name).
            on_unload_all_models: Callback for unloading all models.
            on_open_dashboard: Callback for opening the web dashboard.
        """
        self.on_start_service = on_start_service
        self.on_stop_service = on_stop_service
        self.on_unload_model = on_unload_model
        self.on_unload_all_models = on_unload_all_models
        self.on_open_dashboard = on_open_dashboard

        self.window: Optional[tk.Tk] = None
        self.main_frame: Optional[tk.Frame] = None
        self.services: list = []
        self.gpu_info: Optional[dict] = None
        self.loaded_models: list = []
        self.api_available = False

        # Status message for notifications
        self._status_label: Optional[tk.Label] = None
        self._status_message: str = ""
        self._status_color: str = COLORS["text_dim"]

    def show_status(self, message: str, is_error: bool = False) -> None:
        """Show a status message in the window.

        Args:
            message: The message to display.
            is_error: If True, show as error (red), otherwise success (green).
        """
        self._status_message = message
        self._status_color = COLORS["red"] if is_error else COLORS["green"]

        if self._status_label and self.window and self.window.winfo_exists():
            self._status_label.config(text=message, fg=self._status_color)
            # Clear message after 3 seconds
            self.window.after(3000, self._clear_status)

    def _clear_status(self) -> None:
        """Clear the status message."""
        self._status_message = ""
        if self._status_label and self.window and self.window.winfo_exists():
            self._status_label.config(text="")

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
            self.window.destroy()
            self.window = None

    def _create_window(self) -> None:
        """Create the dashboard window."""
        self.window = tk.Tk()
        self.window.title("AI Services Dashboard")
        self.window.configure(bg=COLORS["bg"])
        self.window.overrideredirect(True)  # Remove window decorations

        # Set window size and position (near system tray)
        width = 420
        height = 520
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        x = screen_width - width - 20
        y = screen_height - height - 60  # Above taskbar
        self.window.geometry(f"{width}x{height}+{x}+{y}")

        # Make window stay on top
        self.window.attributes("-topmost", True)

        # Add border effect
        self.window.configure(highlightbackground=COLORS["border"], highlightthickness=2)

        # Close on Escape
        self.window.bind("<Escape>", lambda e: self.hide())

        # Create main frame with scrollbar support
        self.main_frame = tk.Frame(self.window, bg=COLORS["bg"])
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        self._build_ui()
        self.window.focus_force()

    def _build_ui(self) -> None:
        """Build the complete UI."""
        self._create_header()
        self._create_vram_section()
        self._create_models_section()
        self._create_services_section()
        self._create_status_bar()
        self._create_footer()

    def _create_header(self) -> None:
        """Create the header section."""
        header = tk.Frame(self.main_frame, bg=COLORS["bg"])
        header.pack(fill=tk.X, pady=(0, 10))

        # Title
        title = tk.Label(
            header,
            text="AI Services Dashboard",
            font=("Segoe UI", 14, "bold"),
            fg=COLORS["text"],
            bg=COLORS["bg"],
        )
        title.pack(side=tk.LEFT)

        # Status indicator
        status_color = COLORS["green"] if self.api_available else COLORS["red"]
        status_text = "● Online" if self.api_available else "● Offline"
        status = tk.Label(
            header,
            text=status_text,
            font=("Segoe UI", 10),
            fg=status_color,
            bg=COLORS["bg"],
        )
        status.pack(side=tk.RIGHT)

    def _create_vram_section(self) -> None:
        """Create the VRAM usage section with prominent percentage."""
        vram_frame = tk.Frame(self.main_frame, bg=COLORS["card_bg"])
        vram_frame.pack(fill=tk.X, pady=(0, 10))

        inner = tk.Frame(vram_frame, bg=COLORS["card_bg"])
        inner.pack(fill=tk.X, padx=12, pady=10)

        if self.gpu_info:
            used_mb = self.gpu_info.get("used_mb", 0)
            total_mb = self.gpu_info.get("total_mb", 1)
            percent = int((used_mb / total_mb) * 100) if total_mb > 0 else 0
            used_gb = used_mb / 1024
            total_gb = total_mb / 1024

            # Top row: Label and percentage
            top_row = tk.Frame(inner, bg=COLORS["card_bg"])
            top_row.pack(fill=tk.X)

            vram_label = tk.Label(
                top_row,
                text="GPU VRAM",
                font=("Segoe UI", 10),
                fg=COLORS["text_dim"],
                bg=COLORS["card_bg"],
            )
            vram_label.pack(side=tk.LEFT)

            # Large percentage display
            percent_color = COLORS["green"]
            if percent > 80:
                percent_color = COLORS["red"]
            elif percent > 60:
                percent_color = COLORS["orange"]

            percent_label = tk.Label(
                top_row,
                text=f"{percent}%",
                font=("Segoe UI", 18, "bold"),
                fg=percent_color,
                bg=COLORS["card_bg"],
            )
            percent_label.pack(side=tk.RIGHT)

            # Progress bar
            bar_frame = tk.Frame(inner, bg=COLORS["card_bg"])
            bar_frame.pack(fill=tk.X, pady=(8, 5))

            bar_width = 376
            bar_height = 12
            canvas = tk.Canvas(
                bar_frame,
                width=bar_width,
                height=bar_height,
                bg=COLORS["border"],
                highlightthickness=0,
            )
            canvas.pack()

            fill_width = int(bar_width * (percent / 100))
            canvas.create_rectangle(0, 0, fill_width, bar_height, fill=percent_color, outline="")

            # Usage text
            usage_text = tk.Label(
                inner,
                text=f"{used_gb:.1f} GB used of {total_gb:.1f} GB",
                font=("Segoe UI", 10),
                fg=COLORS["text"],
                bg=COLORS["card_bg"],
            )
            usage_text.pack(anchor=tk.W)
        else:
            no_vram = tk.Label(
                inner,
                text="VRAM info unavailable",
                font=("Segoe UI", 10),
                fg=COLORS["text_dim"],
                bg=COLORS["card_bg"],
            )
            no_vram.pack(anchor=tk.W)

    def _create_models_section(self) -> None:
        """Create the loaded models section."""
        # Section header with count and unload all button
        header_frame = tk.Frame(self.main_frame, bg=COLORS["bg"])
        header_frame.pack(fill=tk.X, pady=(5, 5))

        model_count = len(self.loaded_models)
        header = tk.Label(
            header_frame,
            text=f"Loaded Models ({model_count})",
            font=("Segoe UI", 11, "bold"),
            fg=COLORS["text"],
            bg=COLORS["bg"],
        )
        header.pack(side=tk.LEFT)

        if model_count > 0:
            unload_all_btn = tk.Button(
                header_frame,
                text="Unload All",
                font=("Segoe UI", 8),
                fg=COLORS["text"],
                bg=COLORS["red"],
                activebackground=COLORS["orange"],
                relief=tk.FLAT,
                cursor="hand2",
                padx=8,
                command=self.on_unload_all_models,
            )
            unload_all_btn.pack(side=tk.RIGHT)

        # Models container
        models_frame = tk.Frame(self.main_frame, bg=COLORS["bg"])
        models_frame.pack(fill=tk.X)

        if not self.loaded_models:
            no_models = tk.Label(
                models_frame,
                text="No models loaded in VRAM",
                font=("Segoe UI", 10),
                fg=COLORS["text_dim"],
                bg=COLORS["bg"],
            )
            no_models.pack(anchor=tk.W, pady=5)
        else:
            for model in self.loaded_models:
                self._create_model_row(models_frame, model)

    def _create_model_row(self, parent: tk.Frame, model: dict) -> None:
        """Create a row for a loaded model with VRAM usage."""
        row = tk.Frame(parent, bg=COLORS["card_bg"])
        row.pack(fill=tk.X, pady=2)

        inner = tk.Frame(row, bg=COLORS["card_bg"])
        inner.pack(fill=tk.X, padx=10, pady=8)

        # Left side: model info
        left = tk.Frame(inner, bg=COLORS["card_bg"])
        left.pack(side=tk.LEFT, fill=tk.X, expand=True)

        name = model.get("name", "Unknown")
        size = model.get("size", "")
        vram_gb = model.get("vram_gb", 0)

        # Model name with icon
        name_label = tk.Label(
            left,
            text=f"🤖 {name}",
            font=("Segoe UI", 10, "bold"),
            fg=COLORS["purple"],
            bg=COLORS["card_bg"],
        )
        name_label.pack(anchor=tk.W)

        # Size info
        size_text = size if size else f"{vram_gb:.1f} GB" if vram_gb else "Unknown size"
        size_label = tk.Label(
            left,
            text=f"VRAM: {size_text}",
            font=("Segoe UI", 9),
            fg=COLORS["text_dim"],
            bg=COLORS["card_bg"],
        )
        size_label.pack(anchor=tk.W)

        # Unload button
        btn = tk.Button(
            inner,
            text="Unload",
            font=("Segoe UI", 9),
            fg=COLORS["text"],
            bg=COLORS["orange"],
            activebackground=COLORS["red"],
            relief=tk.FLAT,
            cursor="hand2",
            padx=10,
            command=lambda n=name: self._handle_unload_model(n),
        )
        btn.pack(side=tk.RIGHT, padx=(10, 0))

    def _handle_unload_model(self, model_name: str) -> None:
        """Handle model unload with status feedback."""
        self.show_status(f"Unloading {model_name}...")
        self.on_unload_model(model_name)

    def _create_services_section(self) -> None:
        """Create the services section."""
        # Count running services
        running_count = sum(1 for s in self.services if s.get("status") == "running")
        total_count = len(self.services)

        # Section header
        header = tk.Label(
            self.main_frame,
            text=f"Services ({running_count}/{total_count} running)",
            font=("Segoe UI", 11, "bold"),
            fg=COLORS["text"],
            bg=COLORS["bg"],
        )
        header.pack(anchor=tk.W, pady=(10, 5))

        # Scrollable frame for services
        services_frame = tk.Frame(self.main_frame, bg=COLORS["bg"])
        services_frame.pack(fill=tk.X)

        if not self.services:
            no_services = tk.Label(
                services_frame,
                text="No services available",
                font=("Segoe UI", 10),
                fg=COLORS["text_dim"],
                bg=COLORS["bg"],
            )
            no_services.pack(anchor=tk.W, pady=5)
        else:
            # Only show GPU-intensive services or running ones for VRAM relevance
            for service in self.services:
                if service.get("gpu_intensive", False) or service.get("status") == "running":
                    self._create_service_row(services_frame, service)

    def _create_service_row(self, parent: tk.Frame, service: dict) -> None:
        """Create a row for a service."""
        row = tk.Frame(parent, bg=COLORS["card_bg"])
        row.pack(fill=tk.X, pady=2)

        inner = tk.Frame(row, bg=COLORS["card_bg"])
        inner.pack(fill=tk.X, padx=10, pady=6)

        # Service name and status
        status = service.get("status", "stopped")
        status_colors = {
            "running": COLORS["green"],
            "starting": COLORS["orange"],
            "error": COLORS["red"],
            "stopped": COLORS["text_dim"],
            "paused": COLORS["blue"],
        }
        status_color = status_colors.get(status, COLORS["text_dim"])

        # Status icon
        status_icons = {
            "running": "●",
            "starting": "◐",
            "error": "✗",
            "stopped": "○",
            "paused": "◑",
        }
        status_icon = status_icons.get(status, "○")

        name_label = tk.Label(
            inner,
            text=f"{status_icon} {service.get('name', 'Unknown')}",
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
                    bg=COLORS["red"],
                    activebackground=COLORS["orange"],
                    relief=tk.FLAT,
                    cursor="hand2",
                    padx=8,
                    command=lambda sid=service_id, sn=service_name: self.on_stop_service(sid, sn),
                )
                btn.pack(side=tk.RIGHT)
            elif status in ("stopped", "error"):
                btn = tk.Button(
                    inner,
                    text="Start",
                    font=("Segoe UI", 8),
                    fg=COLORS["text"],
                    bg=COLORS["green"],
                    activebackground=COLORS["orange"],
                    relief=tk.FLAT,
                    cursor="hand2",
                    padx=8,
                    command=lambda sid=service_id, sn=service_name: self.on_start_service(sid, sn),
                )
                btn.pack(side=tk.RIGHT)

    def _create_status_bar(self) -> None:
        """Create a status bar for notifications."""
        status_frame = tk.Frame(self.main_frame, bg=COLORS["bg"])
        status_frame.pack(fill=tk.X, pady=(10, 0))

        self._status_label = tk.Label(
            status_frame,
            text=self._status_message,
            font=("Segoe UI", 9),
            fg=self._status_color,
            bg=COLORS["bg"],
        )
        self._status_label.pack(anchor=tk.W)

    def _create_footer(self) -> None:
        """Create the footer with action buttons."""
        footer = tk.Frame(self.main_frame, bg=COLORS["bg"])
        footer.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))

        # Open Dashboard button
        open_btn = tk.Button(
            footer,
            text="Open Web Dashboard",
            font=("Segoe UI", 10),
            fg=COLORS["bg"],
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
        if not self.main_frame:
            return

        # Save current status message
        saved_message = self._status_message
        saved_color = self._status_color

        # Clear and rebuild
        for widget in self.main_frame.winfo_children():
            widget.destroy()

        self._build_ui()

        # Restore status message
        if saved_message:
            self._status_message = saved_message
            self._status_color = saved_color
            if self._status_label:
                self._status_label.config(text=saved_message, fg=saved_color)

    def destroy(self) -> None:
        """Destroy the window."""
        if self.window:
            self.window.destroy()
            self.window = None
            self.main_frame = None
            self._status_label = None
