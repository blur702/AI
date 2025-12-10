from __future__ import annotations

import logging
import queue
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import Tk, ttk

from dashboard_app.assets.styles import apply_style
from dashboard_app.config import AppConfig, get_config_dir, load_config, save_config
from dashboard_app.controllers.ollama_controller import OllamaController
from dashboard_app.controllers.vram_controller import VRAMMonitor
from dashboard_app.utils.threading_utils import start_poller
from dashboard_app.views.dashboard_tab import DashboardTab
from dashboard_app.views.models_tab import ModelsTab
from dashboard_app.views.settings_tab import SettingsTab
from dashboard_app.views.widgets.status_bar import StatusBar


# Ensure project root (parent of dashboard_app) is on sys.path so imports like
# `dashboard.backend.services_config` and `vram_manager` resolve correctly.
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dashboard_app.controllers.service_controller import ServiceController  # noqa: E402


def _configure_logging() -> None:
    """Configure rotating file logging for the desktop app."""
    log_dir = get_config_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "dashboard_app.log"

    handler = RotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s - %(message)s"
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)


class DashboardApp:
    """Tkinter-based desktop dashboard."""

    def __init__(self) -> None:
        self.config_obj: AppConfig = load_config()
        self.root = Tk()
        self.root.title("AI Dashboard")

        # Window sizing
        self.root.geometry(
            f"{self.config_obj.window_width}x{self.config_obj.window_height}"
        )
        if (
            self.config_obj.window_x is not None
            and self.config_obj.window_y is not None
        ):
            self.root.geometry(
                f"+{self.config_obj.window_x}+{self.config_obj.window_y}"
            )

        apply_style(self.root, theme=self.config_obj.theme)

        # Controllers
        self.vram_monitor = VRAMMonitor(
            poll_interval=self.config_obj.poll_vram_interval
        )
        self.vram_monitor.start()
        self.service_controller = ServiceController(
            self.config_obj, vram_monitor=self.vram_monitor
        )
        self.ollama_controller = OllamaController()
        if self.config_obj.autostop_enabled:
            self.service_controller.enable_auto_stop(True)

        # Layout
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        self.dashboard_tab = DashboardTab(
            self.notebook,
            service_controller=self.service_controller,
            vram_monitor=self.vram_monitor,
            ollama_controller=self.ollama_controller,
            app_config=self.config_obj,
        )
        self.models_tab = ModelsTab(
            self.notebook,
            controller=self.ollama_controller,
            vram_monitor=self.vram_monitor,
        )
        self.settings_tab = SettingsTab(self.notebook)

        self.notebook.add(self.dashboard_tab, text="Dashboard")
        self.notebook.add(self.models_tab, text="Models")
        self.notebook.add(self.settings_tab, text="Settings")

        # Restore last selected tab.
        tab_map = {"dashboard": 0, "models": 1, "settings": 2}
        initial_index = tab_map.get(self.config_obj.last_tab, 0)
        try:
            self.notebook.select(initial_index)
        except Exception:
            self.notebook.select(0)

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.status_bar = StatusBar(self.root)
        self.status_bar.pack(fill="x")
        self.status_bar.set_status("Ready")

        # Background pollers
        self._queue: queue.Queue = queue.Queue()
        self._service_poller = start_poller(
            "service-poller",
            self.config_obj.poll_services_interval,
            self._poll_services,
            self._queue,
        )
        self._vram_poller = start_poller(
            "vram-poller",
            self.config_obj.poll_vram_interval,
            self._poll_vram,
            self._queue,
        )

        self.root.after(100, self._process_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _poll_services(self):
        self.service_controller.refresh_statuses()
        return ("services", None)

    def _poll_vram(self):
        return ("vram", None)

    def _process_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "services":
                    self.dashboard_tab.refresh_services()
                elif kind == "vram":
                    self.dashboard_tab.refresh_resources()
        except queue.Empty:
            pass
        self.root.after(100, self._process_queue)

    def _on_tab_changed(self, event) -> None:
        try:
            tab_id = event.widget.select()
            index = event.widget.index(tab_id)
        except Exception:
            index = 0
        index_map = {0: "dashboard", 1: "models", 2: "settings"}
        self.config_obj.last_tab = index_map.get(index, "dashboard")

    def on_close(self) -> None:
        # Persist window geometry
        try:
            geo = self.root.winfo_geometry()
            size, _, pos = geo.partition("+")
            width, _, height = size.partition("x")
            x_str, _, y_str = pos.partition("+")
            self.config_obj.window_width = int(width)
            self.config_obj.window_height = int(height)
            if x_str and y_str:
                self.config_obj.window_x = int(x_str)
                self.config_obj.window_y = int(y_str)
        except Exception:
            pass

        save_config(self.config_obj)

        # Stop pollers
        self._service_poller.stop()
        self._vram_poller.stop()

        # Cleanup managed services
        try:
            self.service_controller.cleanup()
        except Exception:
            pass

        # Stop VRAM monitor
        try:
            self.vram_monitor.stop()
        except Exception:
            pass

        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    _configure_logging()
    app = DashboardApp()
    app.run()


if __name__ == "__main__":
    main()
