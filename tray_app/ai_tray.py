"""
AI Services System Tray Application

A Windows system tray utility for managing AI services and VRAM.

Features:
    - Dynamic tray icon with status indicators
    - Service management (start/stop)
    - VRAM monitoring
    - Ollama model management
    - Dashboard auto-restart with exponential backoff
    - Enhanced notifications for all operations
    - Graphical dashboard popup on icon click
"""

import logging
import os
import platform
import shutil
import subprocess
import threading
import time
import webbrowser
from functools import partial
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
import pystray
from pystray import MenuItem as Item, Menu

from api_client import DashboardAPI
from dashboard_window import DashboardWindow


# Configuration
DASHBOARD_PORT = 80
DASHBOARD_URL = f"http://localhost:{DASHBOARD_PORT}"
ICON_SIZE = 64

# Polling configuration with adaptive intervals
POLL_INTERVAL_NORMAL = 10  # seconds when connected
POLL_INTERVAL_FAST = 5     # seconds during active operations
POLL_INTERVAL_SLOW = 30    # seconds when dashboard is down (save resources)
POLL_INTERVAL_MAX = 60     # maximum poll interval with backoff

# Logging configuration
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tray_app.log")

# Setup logging with file rotation
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


class AITrayApp:
    """System tray application for managing AI services.

    Provides system tray interface for:
        - Viewing and controlling AI services
        - Monitoring GPU VRAM usage
        - Managing loaded Ollama models
        - Auto-restarting the dashboard on failures
    """

    def __init__(self) -> None:
        self.api = DashboardAPI(DASHBOARD_URL)
        self.icon: Optional[pystray.Icon] = None
        self.running = True
        self._lock = threading.Lock()
        self.services: list = []
        self.gpu_info: Optional[dict] = None
        self.loaded_models: list = []
        self.api_available = False

        # Dashboard auto-restart state
        self.dashboard_auto_restart = True
        self.consecutive_failures = 0
        self.dashboard_process: Optional[subprocess.Popen] = None

        # Adaptive polling state
        self._poll_interval = POLL_INTERVAL_NORMAL
        self._backoff_multiplier = 1.0
        self._last_successful_poll: Optional[float] = None
        self._pending_operation = False

        # Create the initial icons
        self.normal_icon = self._create_icon("AI", (76, 175, 80))   # Green
        self.busy_icon = self._create_icon("AI", (255, 152, 0))     # Orange
        self.error_icon = self._create_icon("AI", (244, 67, 54))    # Red

        # Create the graphical dashboard window
        self.dashboard_window = DashboardWindow(
            on_start_service=self._start_service_with_notify,
            on_stop_service=self._stop_service_with_notify,
            on_unload_model=self._unload_model_with_notify,
            on_unload_all_models=self._unload_all_models_with_notify,
            on_open_dashboard=self._open_dashboard,
        )

        logger.info("AI Tray App initialized")

    def _create_icon(self, text: str, color: tuple) -> Image.Image:
        """Create a simple icon with text.

        Args:
            text: Text to display on the icon.
            color: RGB tuple for background color.

        Returns:
            PIL Image object for the icon.
        """
        img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Draw a rounded rectangle background
        padding = 4
        draw.rounded_rectangle(
            [padding, padding, ICON_SIZE - padding, ICON_SIZE - padding],
            radius=8,
            fill=color,
        )

        # Draw text
        try:
            font = ImageFont.truetype("arial.ttf", 24)
        except OSError:
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
        """Format megabytes to human readable string.

        Args:
            mb: Size in megabytes.

        Returns:
            Human-readable string (e.g., "2.5 GB" or "512 MB").
        """
        if mb >= 1024:
            return f"{mb / 1024:.1f} GB"
        return f"{mb} MB"

    def _get_vram_text(self) -> str:
        """Get VRAM status text for menu.

        Returns:
            Formatted VRAM status string.
        """
        if not self.gpu_info:
            return "VRAM: N/A"
        used = self.gpu_info.get("used_mb", 0)
        total = self.gpu_info.get("total_mb", 1)
        percent = int((used / total) * 100) if total > 0 else 0
        return f"VRAM: {self._format_bytes(used)} / {self._format_bytes(total)} ({percent}%)"

    def _get_tooltip(self) -> str:
        """Generate tooltip text.

        Returns:
            Tooltip string showing service count and VRAM usage.
        """
        if not self.api_available:
            return "AI Services - Dashboard Offline"

        running_count = sum(1 for s in self.services if s.get("status") == "running")

        if self.gpu_info:
            used = self.gpu_info.get("used_mb", 0)
            total = self.gpu_info.get("total_mb", 1)
            return (
                f"AI Services: {running_count} running | "
                f"VRAM: {self._format_bytes(used)}/{self._format_bytes(total)}"
            )

        return f"AI Services: {running_count} running"

    def _notify(self, message: str, title: str = "AI Tray") -> None:
        """Show a notification to the user.

        Args:
            message: Notification message.
            title: Notification title.
        """
        if self.icon:
            try:
                self.icon.notify(message, title)
            except Exception as e:
                logger.warning("Failed to show notification: %s", e)

    def _notify_success(self, message: str) -> None:
        """Show a success notification.

        Args:
            message: Success message.
        """
        self._notify(f"✓ {message}", "AI Tray")

    def _notify_error(self, message: str) -> None:
        """Show an error notification.

        Args:
            message: Error message.
        """
        self._notify(f"✗ {message}", "AI Tray - Error")

    def _notify_info(self, message: str) -> None:
        """Show an info notification.

        Args:
            message: Info message.
        """
        self._notify(message, "AI Tray")

    def _open_dashboard(self) -> None:
        """Open the dashboard in the default browser."""
        webbrowser.open(DASHBOARD_URL)
        logger.info("Opened dashboard in browser")

    def _show_dashboard_popup(self) -> None:
        """Show the graphical dashboard popup window."""
        logger.info("Showing dashboard popup")
        self.dashboard_window.show()

    def _open_service(self, service_id: str, port: int) -> None:
        """Open a service in the browser.

        Args:
            service_id: Service identifier (for logging).
            port: Service port number.
        """
        url = f"http://localhost:{port}"
        webbrowser.open(url)
        logger.info("Opened service %s at %s", service_id, url)

    def _start_service(self, service_id: str, service_name: str) -> None:
        """Start a service.

        Args:
            service_id: Service identifier.
            service_name: Human-readable service name for notifications.
        """
        self._pending_operation = True
        try:
            logger.info("User requested start: %s", service_id)
            if self.api.start_service(service_id):
                self._notify_success(f"Started {service_name}")
            else:
                self._notify_error(f"Failed to start {service_name}")
            self._refresh_data()
        except Exception as e:
            logger.exception("Failed to start service '%s': %s", service_id, e)
            self._notify_error(f"Failed to start {service_name}: {e}")
        finally:
            self._pending_operation = False

    def _stop_service(self, service_id: str, service_name: str) -> None:
        """Stop a service.

        Args:
            service_id: Service identifier.
            service_name: Human-readable service name for notifications.
        """
        self._pending_operation = True
        try:
            logger.info("User requested stop: %s", service_id)
            if self.api.stop_service(service_id):
                self._notify_success(f"Stopped {service_name}")
            else:
                self._notify_error(f"Failed to stop {service_name}")
            self._refresh_data()
        except Exception as e:
            logger.exception("Failed to stop service '%s': %s", service_id, e)
            self._notify_error(f"Failed to stop {service_name}: {e}")
        finally:
            self._pending_operation = False

    def _unload_model(self, model_name: str) -> None:
        """Unload an Ollama model.

        Args:
            model_name: Name of the model to unload.
        """
        self._pending_operation = True
        try:
            logger.info("User requested unload: %s", model_name)
            if self.api.unload_model(model_name):
                self._notify_success(f"Unloaded {model_name}")
            else:
                self._notify_error(f"Failed to unload {model_name}")
            self._refresh_data()
        except Exception as e:
            logger.exception("Failed to unload model '%s': %s", model_name, e)
            self._notify_error(f"Failed to unload {model_name}: {e}")
        finally:
            self._pending_operation = False

    def _unload_all_models(self) -> None:
        """Unload all Ollama models."""
        self._pending_operation = True
        try:
            logger.info("User requested unload all models")
            count = self.api.unload_all_models()
            self._refresh_data()
            if count > 0:
                self._notify_success(f"Unloaded {count} model(s)")
            else:
                self._notify_info("No models to unload")
        except Exception as e:
            logger.exception("Failed to unload all models: %s", e)
            self._notify_error("Failed to unload models")
        finally:
            self._pending_operation = False

    # =========================================================================
    # Dashboard Window Callbacks (with in-window notifications)
    # =========================================================================

    def _start_service_with_notify(self, service_id: str, service_name: str) -> None:
        """Start a service and notify the dashboard window."""
        self._pending_operation = True
        try:
            logger.info("User requested start: %s", service_id)
            if self.api.start_service(service_id):
                self.dashboard_window.show_status(f"✓ Started {service_name}", is_error=False)
                self._notify_success(f"Started {service_name}")
            else:
                self.dashboard_window.show_status(f"✗ Failed to start {service_name}", is_error=True)
                self._notify_error(f"Failed to start {service_name}")
            self._refresh_data()
        except Exception as e:
            logger.exception("Failed to start service '%s': %s", service_id, e)
            self.dashboard_window.show_status(f"✗ Error: {e}", is_error=True)
            self._notify_error(f"Failed to start {service_name}: {e}")
        finally:
            self._pending_operation = False

    def _stop_service_with_notify(self, service_id: str, service_name: str) -> None:
        """Stop a service and notify the dashboard window."""
        self._pending_operation = True
        try:
            logger.info("User requested stop: %s", service_id)
            if self.api.stop_service(service_id):
                self.dashboard_window.show_status(f"✓ Stopped {service_name}", is_error=False)
                self._notify_success(f"Stopped {service_name}")
            else:
                self.dashboard_window.show_status(f"✗ Failed to stop {service_name}", is_error=True)
                self._notify_error(f"Failed to stop {service_name}")
            self._refresh_data()
        except Exception as e:
            logger.exception("Failed to stop service '%s': %s", service_id, e)
            self.dashboard_window.show_status(f"✗ Error: {e}", is_error=True)
            self._notify_error(f"Failed to stop {service_name}: {e}")
        finally:
            self._pending_operation = False

    def _unload_model_with_notify(self, model_name: str) -> None:
        """Unload an Ollama model and notify the dashboard window."""
        self._pending_operation = True
        try:
            logger.info("User requested unload: %s", model_name)
            if self.api.unload_model(model_name):
                self.dashboard_window.show_status(f"✓ Unloaded {model_name}", is_error=False)
                self._notify_success(f"Unloaded {model_name}")
            else:
                self.dashboard_window.show_status(f"✗ Failed to unload {model_name}", is_error=True)
                self._notify_error(f"Failed to unload {model_name}")
            self._refresh_data()
        except Exception as e:
            logger.exception("Failed to unload model '%s': %s", model_name, e)
            self.dashboard_window.show_status(f"✗ Error: {e}", is_error=True)
            self._notify_error(f"Failed to unload {model_name}: {e}")
        finally:
            self._pending_operation = False

    def _unload_all_models_with_notify(self) -> None:
        """Unload all Ollama models and notify the dashboard window."""
        self._pending_operation = True
        try:
            logger.info("User requested unload all models")
            count = self.api.unload_all_models()
            self._refresh_data()
            if count > 0:
                self.dashboard_window.show_status(f"✓ Unloaded {count} model(s)", is_error=False)
                self._notify_success(f"Unloaded {count} model(s)")
            else:
                self.dashboard_window.show_status("No models to unload", is_error=False)
                self._notify_info("No models to unload")
        except Exception as e:
            logger.exception("Failed to unload all models: %s", e)
            self.dashboard_window.show_status(f"✗ Error: {e}", is_error=True)
            self._notify_error("Failed to unload models")
        finally:
            self._pending_operation = False

    def _kill_process_on_port(self, port: int) -> bool:
        """Attempt to terminate a process listening on the given port.

        Args:
            port: Port number to check.

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
                    parts = line.split()
                    if len(parts) < 5:
                        continue

                    local_address = parts[1]
                    if ":" not in local_address:
                        continue

                    addr_port = local_address.rsplit(":", 1)[-1]
                    if addr_port == target_port and parts[-1].isdigit():
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

            # Unix-like systems using lsof
            if shutil.which("lsof") is None:
                logger.warning("lsof command not found")
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

    def _restart_dashboard(self) -> None:
        """Restart the dashboard backend."""
        logger.warning("Dashboard unresponsive, attempting restart...")

        # Kill existing dashboard process on configured port
        self._kill_process_on_port(DASHBOARD_PORT)

        # Wait for port to be released
        time.sleep(2)

        # Determine dashboard backend path
        tray_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.join(tray_dir, "..", "dashboard", "backend")
        dashboard_path = os.path.join(backend_dir, "app.py")

        try:
            # Start new dashboard process
            creationflags = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                if platform.system() == "Windows"
                else 0
            )
            process = subprocess.Popen(
                ["python", dashboard_path],
                cwd=backend_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            self.dashboard_process = process
            self.consecutive_failures = 0
            self._backoff_multiplier = 1.0

            self._notify_info("Dashboard restarted")
            logger.info("Dashboard restarted with PID %s", process.pid)
        except Exception as e:
            logger.exception("Failed to restart dashboard: %s", e)
            self._notify_error("Failed to restart dashboard")

    def _toggle_auto_restart(self) -> None:
        """Toggle the dashboard auto-restart feature."""
        self.dashboard_auto_restart = not self.dashboard_auto_restart
        status = "enabled" if self.dashboard_auto_restart else "disabled"
        logger.info("Dashboard auto-restart %s", status)
        self._notify_info(f"Auto-restart {status}")

    def _calculate_poll_interval(self) -> float:
        """Calculate the adaptive poll interval based on current state.

        Returns:
            Poll interval in seconds.
        """
        if self._pending_operation:
            return POLL_INTERVAL_FAST

        if not self.api_available:
            # Exponential backoff when dashboard is down
            interval = POLL_INTERVAL_SLOW * self._backoff_multiplier
            return min(interval, POLL_INTERVAL_MAX)

        return POLL_INTERVAL_NORMAL

    def _refresh_data(self) -> None:
        """Refresh data from the API."""
        api_available = self.api.is_available()

        services: list = []
        gpu_info: Optional[dict] = None
        loaded_models: list = []

        if api_available:
            services = self.api.get_services()
            gpu_info = self.api.get_vram_status()
            loaded_models = self.api.get_loaded_models()
            self._last_successful_poll = time.time()
            self._backoff_multiplier = 1.0  # Reset backoff on success

        with self._lock:
            self.api_available = api_available
            self.services = services
            self.gpu_info = gpu_info
            self.loaded_models = loaded_models

            # Update icon and tooltip
            if self.icon:
                if not api_available:
                    self.icon.icon = self.error_icon
                elif self._pending_operation:
                    self.icon.icon = self.busy_icon
                else:
                    self.icon.icon = self.normal_icon
                self.icon.title = self._get_tooltip()

            # Update the dashboard window if it exists
            self.dashboard_window.update_data(
                services=services,
                gpu_info=gpu_info,
                loaded_models=loaded_models,
                api_available=api_available,
            )

    def _build_service_submenu(self, service: dict) -> Optional[Menu]:
        """Build submenu for a service.

        Args:
            service: Service dictionary.

        Returns:
            Menu object or None if no actions available.
        """
        service_id = service.get("id", "")
        service_name = service.get("name", service_id)
        status = service.get("status", "stopped")
        port = service.get("port", 0)
        is_external = service.get("external", False)

        items = []

        if status == "running":
            if not is_external:
                items.append(
                    Item("Stop", partial(self._stop_service, service_id, service_name))
                )
            if port:
                items.append(
                    Item(
                        "Open in Browser",
                        partial(self._open_service, service_id, port),
                    )
                )
        elif status == "stopped":
            if not is_external:
                items.append(
                    Item("Start", partial(self._start_service, service_id, service_name))
                )
        elif status == "starting":
            items.append(Item("Starting...", None, enabled=False))
        elif status == "error":
            if not is_external:
                items.append(
                    Item(
                        "Restart",
                        partial(self._start_service, service_id, service_name),
                    )
                )

        return Menu(*items) if items else None

    def _build_model_submenu(self) -> list:
        """Build submenu items for loaded models.

        Returns:
            List of MenuItem objects.
        """
        if not self.loaded_models:
            return [Item("No models loaded", None, enabled=False)]

        items = []
        for model in self.loaded_models:
            name = model.get("name", "Unknown")
            size = model.get("size", "")
            label = f"{name} ({size})" if size else name
            items.append(
                Item(label, Menu(Item("Unload", partial(self._unload_model, name))))
            )

        return items

    def _build_menu(self) -> Menu:
        """Build the complete tray menu.

        Returns:
            Menu object for the tray icon.
        """
        with self._lock:
            # Services submenu
            service_items = []
            for service in self.services:
                name = service.get("name", "Unknown")
                status = service.get("status", "stopped")

                # Status indicator
                status_icons = {
                    "running": "[Running]",
                    "starting": "[Starting]",
                    "error": "[Error]",
                }
                status_icon = status_icons.get(status, "[Stopped]")

                label = f"{name} {status_icon}"
                submenu = self._build_service_submenu(service)

                if submenu:
                    service_items.append(Item(label, submenu))
                else:
                    service_items.append(Item(label, None, enabled=False))

            # Build main menu
            menu_items = [
                Item(
                    "Services",
                    Menu(*service_items)
                    if service_items
                    else Menu(Item("No services found", None, enabled=False)),
                ),
                Menu.SEPARATOR,
                Item(self._get_vram_text(), None, enabled=False),
                Item("Loaded Models", Menu(*self._build_model_submenu())),
                Item(
                    "Unload All Models",
                    self._unload_all_models,
                    enabled=len(self.loaded_models) > 0,
                ),
                Menu.SEPARATOR,
                Item(
                    "Auto-restart Dashboard",
                    self._toggle_auto_restart,
                    checked=lambda item: self.dashboard_auto_restart,
                ),
                Menu.SEPARATOR,
                Item("Show Dashboard", self._show_dashboard_popup),
                Item("Open in Browser", self._open_dashboard),
                Item("Refresh", lambda: self._refresh_data()),
                Menu.SEPARATOR,
                Item("Exit", self._quit),
            ]

        return Menu(*menu_items)

    def _poll_loop(self) -> None:
        """Background thread to poll the API periodically with adaptive intervals."""
        while self.running:
            try:
                self._refresh_data()

                # Track consecutive failures for auto-restart
                if not self.api_available:
                    self.consecutive_failures += 1
                    self._backoff_multiplier = min(
                        self._backoff_multiplier * 1.5, 4.0
                    )  # Max 4x backoff
                    logger.debug(
                        "Dashboard check failed (%d/3), backoff=%.1fx",
                        self.consecutive_failures,
                        self._backoff_multiplier,
                    )
                    if self.consecutive_failures >= 3 and self.dashboard_auto_restart:
                        self._restart_dashboard()
                else:
                    if self.consecutive_failures > 0:
                        logger.info("Dashboard connection restored")
                    self.consecutive_failures = 0

                # Update menu dynamically
                if self.icon:
                    self.icon.menu = self._build_menu()

            except Exception as e:
                logger.exception("Poll error: %s", e)

            # Adaptive sleep based on state
            poll_interval = self._calculate_poll_interval()

            # Sleep in small intervals to allow quick exit
            for _ in range(int(poll_interval * 10)):
                if not self.running:
                    break
                time.sleep(0.1)

    def _quit(self) -> None:
        """Quit the application."""
        logger.info("Shutting down AI Tray App")
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
                logger.exception("Error terminating dashboard process: %s", e)

        # Close API session
        self.api.close()

        # Destroy dashboard window
        self.dashboard_window.destroy()

        if self.icon:
            self.icon.stop()

    def _on_left_click(self, icon: pystray.Icon, item: Optional[Item]) -> None:
        """Handle left click on tray icon.

        Args:
            icon: The tray icon object.
            item: Menu item (unused).
        """
        self._show_dashboard_popup()

    def run(self) -> None:
        """Run the tray application."""
        logger.info("Starting AI Tray App")

        # Initial data fetch
        self._refresh_data()

        # Create the icon
        self.icon = pystray.Icon(
            "AI Services",
            self.normal_icon if self.api_available else self.error_icon,
            self._get_tooltip(),
            menu=self._build_menu(),
        )

        # Set up left click handler
        self.icon.default_action = self._on_left_click

        # Start the polling thread
        poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        poll_thread.start()

        # Run the icon (blocks until quit)
        self.icon.run()


def main() -> None:
    """Main entry point."""
    # Change to the script directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    app = AITrayApp()
    app.run()


if __name__ == "__main__":
    main()
