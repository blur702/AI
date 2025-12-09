"""
AI Services System Tray Application

A Windows system tray utility for managing AI services and VRAM.
"""

import logging
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from functools import partial

from PIL import Image, ImageDraw, ImageFont
import pystray
from pystray import MenuItem as Item, Menu

from api_client import DashboardAPI


# Configuration
DASHBOARD_PORT = 80
DASHBOARD_URL = f"http://localhost:{DASHBOARD_PORT}"
POLL_INTERVAL = 10  # seconds
ICON_SIZE = 64

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class AITrayApp:
    """System tray application for managing AI services."""

    def __init__(self):
        self.api = DashboardAPI(DASHBOARD_URL)
        self.icon = None
        self.running = True
        self._lock = threading.Lock()
        self.services = []
        self.gpu_info = None
        self.loaded_models = []
        self.api_available = False

        # Dashboard auto-restart state
        self.dashboard_auto_restart = True
        self.consecutive_failures = 0
        self.dashboard_process = None

        # Create the initial icon
        self.normal_icon = self._create_icon("AI", (76, 175, 80))  # Green
        self.busy_icon = self._create_icon("AI", (255, 152, 0))    # Orange
        self.error_icon = self._create_icon("AI", (244, 67, 54))   # Red

    def _create_icon(self, text: str, color: tuple) -> Image.Image:
        """Create a simple icon with text."""
        img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Draw a rounded rectangle background
        padding = 4
        draw.rounded_rectangle(
            [padding, padding, ICON_SIZE - padding, ICON_SIZE - padding],
            radius=8,
            fill=color
        )

        # Draw text
        try:
            font = ImageFont.truetype("arial.ttf", 24)
        except (OSError, IOError):
            font = ImageFont.load_default()

        # Center the text
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (ICON_SIZE - text_width) // 2
        y = (ICON_SIZE - text_height) // 2 - 2

        draw.text((x, y), text, fill="white", font=font)

        return img

    def _format_bytes(self, mb: int) -> str:
        """Format megabytes to human readable string."""
        if mb >= 1024:
            return f"{mb / 1024:.1f} GB"
        return f"{mb} MB"

    def _get_vram_text(self) -> str:
        """Get VRAM status text for menu."""
        if not self.gpu_info:
            return "VRAM: N/A"
        used = self.gpu_info.get("used_mb", 0)
        total = self.gpu_info.get("total_mb", 1)
        percent = int((used / total) * 100) if total > 0 else 0
        return f"VRAM: {self._format_bytes(used)} / {self._format_bytes(total)} ({percent}%)"

    def _get_tooltip(self) -> str:
        """Generate tooltip text."""
        if not self.api_available:
            return "AI Services - Dashboard Offline"

        running_count = sum(1 for s in self.services if s.get("status") == "running")

        if self.gpu_info:
            used = self.gpu_info.get("used_mb", 0)
            total = self.gpu_info.get("total_mb", 1)
            return f"AI Services: {running_count} running | VRAM: {self._format_bytes(used)}/{self._format_bytes(total)}"

        return f"AI Services: {running_count} running"

    def _open_dashboard(self):
        """Open the dashboard in the default browser."""
        webbrowser.open(DASHBOARD_URL)

    def _open_service(self, service_id: str, port: int):
        """Open a service in the browser."""
        webbrowser.open(f"http://localhost:{port}")

    def _show_error(self, message: str):
        """Show error notification to user."""
        if self.icon:
            self.icon.notify(f"Error: {message}", "AI Tray")

    def _start_service(self, service_id: str):
        """Start a service."""
        try:
            self.api.start_service(service_id)
            self._refresh_data()
        except Exception as e:
            logger.error(f"Failed to start service '{service_id}': {e}")
            self._show_error(f"Failed to start service: {service_id}")

    def _stop_service(self, service_id: str):
        """Stop a service."""
        try:
            self.api.stop_service(service_id)
            self._refresh_data()
        except Exception as e:
            logger.error(f"Failed to stop service '{service_id}': {e}")
            self._show_error(f"Failed to stop service: {service_id}")

    def _unload_model(self, model_name: str):
        """Unload an Ollama model."""
        try:
            self.api.unload_model(model_name)
            self._refresh_data()
        except Exception as e:
            logger.error(f"Failed to unload model '{model_name}': {e}")
            self._show_error(f"Failed to unload model: {model_name}")

    def _unload_all_models(self):
        """Unload all Ollama models."""
        try:
            count = self.api.unload_all_models()
            self._refresh_data()
            if self.icon:
                self.icon.notify(f"Unloaded {count} model(s)", "AI Tray")
        except Exception as e:
            logger.error(f"Failed to unload all models: {e}")
            self._show_error("Failed to unload models")

    def _kill_process_on_port(self, port: int) -> bool:
        """Attempt to terminate a process listening on the given port.

        Returns:
            True if successful, False otherwise.
        """
        try:
            system = platform.system()

            if system == "Windows":
                # Use netstat to find PID listening on the port
                result = subprocess.run(
                    ["netstat", "-ano"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    logger.error("netstat failed while looking up port %s", port)
                    return False

                pid = None
                target_port = str(port)
                for line in result.stdout.splitlines():
                    # Typical line: TCP    0.0.0.0:80         0.0.0.0:0              LISTENING       1234
                    parts = line.split()
                    if len(parts) < 5:
                        continue

                    # Local address is typically the 2nd column (index 1)
                    local_address = parts[1]

                    # Extract port by splitting on the last ':' (handles IPv6)
                    if ':' not in local_address:
                        continue

                    addr_port = local_address.rsplit(':', 1)[-1]

                    # Check for exact port match
                    if addr_port == target_port:
                        # Verify PID is in the last column and is numeric
                        if parts[-1].isdigit():
                            pid = parts[-1]
                            break

                if not pid:
                    return False

                logger.info("Attempting to kill PID %s for port %s", pid, port)
                kill_result = subprocess.run(
                    ["taskkill", "/PID", pid, "/F"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if kill_result.returncode != 0:
                    logger.error(
                        "taskkill failed for PID %s (port %s): %s",
                        pid,
                        port,
                        kill_result.stderr.strip(),
                    )
                    return False

                return True

            # Basic UNIX-like implementation using lsof/kill if available
            # Check if lsof is available on this system
            if shutil.which("lsof") is None:
                logger.warning(
                    "Port-based process kill is not supported on this platform: "
                    "lsof command not found"
                )
                return False

            result = subprocess.run(
                ["lsof", "-i", f":{port}", "-t"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return False

            pids = [p.strip() for p in result.stdout.splitlines() if p.strip().isdigit()]
            if not pids:
                return False

            for pid in pids:
                logger.info("Attempting to kill PID %s for port %s", pid, port)
                subprocess.run(
                    ["kill", "-9", pid],
                    capture_output=True,
                    text=True,
                    check=False,
                )

            return True

        except Exception as exc:
            logger.error("Error killing process on port %s: %s", port, exc)
            return False

    def _restart_dashboard(self):
        """Restart the dashboard backend."""
        logger.warning("Dashboard unresponsive, attempting restart...")

        # Kill existing dashboard process on configured port
        self._kill_process_on_port(DASHBOARD_PORT)

        # Wait for port to be released
        time.sleep(2)

        # Determine dashboard backend path
        tray_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.join(tray_dir, '..', 'dashboard', 'backend')
        dashboard_path = os.path.join(backend_dir, 'app.py')

        try:
            # Start new dashboard process
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == 'Windows' else 0
            process = subprocess.Popen(
                ['python', dashboard_path],
                cwd=backend_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            self.dashboard_process = process
            self.consecutive_failures = 0

            if self.icon:
                self.icon.notify("Dashboard restarted", "AI Tray")
            logger.info(f"Dashboard restarted with PID {process.pid}")
        except Exception as e:
            logger.error(f"Failed to restart dashboard: {e}")
            if self.icon:
                self.icon.notify("Failed to restart dashboard", "AI Tray")

    def _toggle_auto_restart(self):
        """Toggle the dashboard auto-restart feature."""
        self.dashboard_auto_restart = not self.dashboard_auto_restart
        status = "enabled" if self.dashboard_auto_restart else "disabled"
        logger.info(f"Dashboard auto-restart {status}")
        if self.icon:
            self.icon.notify(f"Auto-restart {status}", "AI Tray")

    def _refresh_data(self):
        """Refresh data from the API."""
        api_available = self.api.is_available()

        services = []
        gpu_info = None
        loaded_models = []

        if api_available:
            services = self.api.get_services()
            gpu_info = self.api.get_vram_status()
            loaded_models = self.api.get_loaded_models()

        with self._lock:
            self.api_available = api_available
            self.services = services
            self.gpu_info = gpu_info
            self.loaded_models = loaded_models

            # Update icon and tooltip
            if self.icon:
                self.icon.icon = self.normal_icon if self.api_available else self.error_icon
                self.icon.title = self._get_tooltip()

    def _build_service_submenu(self, service: dict) -> Menu:
        """Build submenu for a service."""
        service_id = service.get("id", "")
        status = service.get("status", "stopped")
        port = service.get("port", 0)
        is_external = service.get("external", False)

        items = []

        if status == "running":
            if not is_external:
                items.append(Item("Stop", partial(self._stop_service, service_id)))
            if port:
                items.append(Item("Open in Browser", partial(self._open_service, service_id, port)))
        elif status == "stopped":
            if not is_external:
                items.append(Item("Start", partial(self._start_service, service_id)))
        elif status == "starting":
            items.append(Item("Starting...", None, enabled=False))
        elif status == "error":
            if not is_external:
                items.append(Item("Restart", partial(self._start_service, service_id)))

        return Menu(*items) if items else None

    def _build_model_submenu(self) -> list:
        """Build submenu items for loaded models."""
        if not self.loaded_models:
            return [Item("No models loaded", None, enabled=False)]

        items = []
        for model in self.loaded_models:
            name = model.get("name", "Unknown")
            size = model.get("size", "")
            label = f"{name} ({size})" if size else name
            items.append(Item(label, Menu(
                Item("Unload", partial(self._unload_model, name))
            )))

        return items

    def _build_menu(self) -> Menu:
        """Build the complete tray menu."""
        with self._lock:
            # Services submenu
            service_items = []
            for service in self.services:
                name = service.get("name", "Unknown")
                status = service.get("status", "stopped")
                is_external = service.get("external", False)

                # Status indicator
                if status == "running":
                    status_icon = "[Running]"
                elif status == "starting":
                    status_icon = "[Starting]"
                elif status == "error":
                    status_icon = "[Error]"
                else:
                    status_icon = "[Stopped]"

                label = f"{name} {status_icon}"
                submenu = self._build_service_submenu(service)

                if submenu:
                    service_items.append(Item(label, submenu))
                else:
                    service_items.append(Item(label, None, enabled=False))

            # Build main menu
            menu_items = [
                Item("Services", Menu(*service_items) if service_items else Menu(
                    Item("No services found", None, enabled=False)
                )),
                Menu.SEPARATOR,
                Item(self._get_vram_text(), None, enabled=False),
                Item("Loaded Models", Menu(*self._build_model_submenu())),
                Item(
                    "Unload All Models",
                    self._unload_all_models,
                    enabled=len(self.loaded_models) > 0
                ),
                Menu.SEPARATOR,
                Item(
                    "Auto-restart Dashboard",
                    self._toggle_auto_restart,
                    checked=lambda item: self.dashboard_auto_restart
                ),
                Menu.SEPARATOR,
                Item("Open Dashboard", self._open_dashboard),
                Item("Refresh", lambda: self._refresh_data()),
                Menu.SEPARATOR,
                Item("Exit", self._quit),
            ]

        return Menu(*menu_items)

    def _poll_loop(self):
        """Background thread to poll the API periodically."""
        while self.running:
            try:
                self._refresh_data()

                # Track consecutive failures for auto-restart
                if not self.api_available:
                    self.consecutive_failures += 1
                    logger.debug(f"Dashboard check failed ({self.consecutive_failures}/3)")
                    if self.consecutive_failures >= 3 and self.dashboard_auto_restart:
                        self._restart_dashboard()
                else:
                    self.consecutive_failures = 0

                # Update menu dynamically
                if self.icon:
                    self.icon.menu = self._build_menu()
            except Exception as e:
                logger.error(f"Poll error: {e}")

            # Sleep in small intervals to allow quick exit
            for _ in range(POLL_INTERVAL * 10):
                if not self.running:
                    break
                time.sleep(0.1)

    def _quit(self):
        """Quit the application."""
        self.running = False

        # Terminate dashboard process if we started it
        if self.dashboard_process:
            try:
                if self.dashboard_process.poll() is None:
                    logger.info("Terminating dashboard process on exit")
                    self.dashboard_process.terminate()
                    try:
                        self.dashboard_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.dashboard_process.kill()
                        logger.warning("Dashboard process killed after timeout")
            except Exception as e:
                logger.error(f"Error terminating dashboard process: {e}")

        if self.icon:
            self.icon.stop()

    def _on_left_click(self, icon, item):
        """Handle left click on tray icon."""
        self._open_dashboard()

    def run(self):
        """Run the tray application."""
        # Initial data fetch
        self._refresh_data()

        # Create the icon
        self.icon = pystray.Icon(
            "AI Services",
            self.normal_icon if self.api_available else self.error_icon,
            self._get_tooltip(),
            menu=self._build_menu()
        )

        # Set up left click handler
        self.icon.default_action = self._on_left_click

        # Start the polling thread
        poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        poll_thread.start()

        # Run the icon (blocks until quit)
        self.icon.run()


def main():
    """Main entry point."""
    # Change to the script directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    app = AITrayApp()
    app.run()


if __name__ == "__main__":
    main()
