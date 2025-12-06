"""
Service Manager Module

Handles starting, stopping, and monitoring AI services.
Provides process management and health checking capabilities.
"""

import logging
import platform
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional

import requests

from services_config import DEFAULT_HOST, SERVICES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class ServiceState:
    status: ServiceStatus = ServiceStatus.STOPPED
    process: Optional[subprocess.Popen] = None
    error_message: Optional[str] = None
    start_time: Optional[float] = None
    pid: Optional[int] = None


class ServiceManager:
    """Manages AI service lifecycle (start, stop, status)."""

    def __init__(self, status_callback: Optional[Callable] = None):
        """
        Initialize the service manager.

        Args:
            status_callback: Optional callback function(service_id, status, message)
                             called when service status changes
        """
        self._services: Dict[str, ServiceState] = {}
        self._lock = threading.Lock()
        self._status_callback = status_callback

        # Initialize state for all services
        for service_id in SERVICES:
            self._services[service_id] = ServiceState()

    def _emit_status(self, service_id: str, status: ServiceStatus, message: str = ""):
        """Emit status update via callback if configured."""
        if self._status_callback:
            try:
                self._status_callback(service_id, status.value, message)
            except Exception as e:
                logger.error(f"Error in status callback: {e}")

    def _check_port_in_use(self, port: int) -> bool:
        """Check if a port is in use (service might be running externally)."""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) == 0

    def _kill_process_on_port(self, port: int) -> bool:
        """Attempt to terminate a process listening on the given port.

        This is primarily intended to handle services that were started
        outside of the dashboard but are using the configured port.
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
                for line in result.stdout.splitlines():
                    # Typical line: TCP    0.0.0.0:7851         0.0.0.0:0              LISTENING       1234
                    if f":{port} " in line or f":{port}\n" in line or f":{port}\r" in line:
                        parts = line.split()
                        if len(parts) >= 5 and parts[-1].isdigit():
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

        except Exception as exc:  # noqa: BLE001
            logger.error("Error killing process on port %s: %s", port, exc)
            return False

    def _health_check(self, service_id: str, timeout: float = 2.0) -> bool:
        """
        Check if a service is responding to health checks.

        Args:
            service_id: The service identifier
            timeout: Request timeout in seconds (default 2.0 for fast checks)

        Returns:
            True if service is healthy, False otherwise
        """
        config = SERVICES.get(service_id)
        if not config:
            return False

        port = config["port"]
        endpoint = config.get("health_endpoint", "/")

        try:
            url = f"http://{DEFAULT_HOST}:{port}{endpoint}"
            response = requests.get(url, timeout=timeout)
            return response.status_code < 500
        except requests.exceptions.RequestException:
            return False

    def get_status(self, service_id: str) -> dict:
        """
        Get the current status of a service.

        Args:
            service_id: The service identifier

        Returns:
            Dictionary with status information
        """
        config = SERVICES.get(service_id)
        if not config:
            return {"error": f"Unknown service: {service_id}"}

        with self._lock:
            state = self._services.get(service_id, ServiceState())

            # Check if service is running (either managed or external)
            is_healthy = self._health_check(service_id)
            port_in_use = self._check_port_in_use(config["port"])

            # Update status based on actual state
            if state.status == ServiceStatus.STARTING:
                if is_healthy:
                    state.status = ServiceStatus.RUNNING
                    self._emit_status(service_id, ServiceStatus.RUNNING, "Service is ready")
            elif state.status == ServiceStatus.RUNNING:
                if not is_healthy and not port_in_use:
                    state.status = ServiceStatus.STOPPED
                    state.process = None
                    self._emit_status(service_id, ServiceStatus.STOPPED, "Service stopped")
            elif state.status == ServiceStatus.STOPPED:
                if is_healthy:
                    # Service running externally
                    state.status = ServiceStatus.RUNNING

            return {
                "service_id": service_id,
                "name": config["name"],
                "status": state.status.value,
                "port": config["port"],
                "icon": config["icon"],
                "description": config["description"],
                "healthy": is_healthy,
                "pid": state.pid,
                "error": state.error_message,
                "external": config.get("external", False),
                "manageable": config.get("command") is not None and not config.get("external", False),
            }

    def get_all_status(self) -> Dict[str, dict]:
        """Get status of all services using concurrent health and port checks."""
        # Run health checks and port checks concurrently
        health_results = {}
        port_results = {}

        def check_service(service_id):
            config = SERVICES[service_id]
            is_healthy = self._health_check(service_id)
            port_in_use = self._check_port_in_use(config["port"])
            return service_id, is_healthy, port_in_use

        try:
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(check_service, sid) for sid in SERVICES]
                for future in as_completed(futures, timeout=10):
                    try:
                        service_id, is_healthy, port_in_use = future.result()
                        health_results[service_id] = is_healthy
                        port_results[service_id] = port_in_use
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Error in concurrent service checks: {e}")
            # Fallback: mark all as unknown
            for service_id in SERVICES:
                if service_id not in health_results:
                    health_results[service_id] = False
                    port_results[service_id] = False

        # Build status dict using cached results
        result = {}
        with self._lock:
            for service_id in SERVICES:
                config = SERVICES[service_id]
                state = self._services.get(service_id, ServiceState())
                is_healthy = health_results.get(service_id, False)
                port_in_use = port_results.get(service_id, False)

                # Update status based on actual state
                if state.status == ServiceStatus.STARTING:
                    if is_healthy:
                        state.status = ServiceStatus.RUNNING
                        self._emit_status(service_id, ServiceStatus.RUNNING, "Service is ready")
                elif state.status == ServiceStatus.RUNNING:
                    if not is_healthy and not port_in_use:
                        state.status = ServiceStatus.STOPPED
                        state.process = None
                        self._emit_status(service_id, ServiceStatus.STOPPED, "Service stopped")
                elif state.status == ServiceStatus.STOPPED:
                    if is_healthy:
                        state.status = ServiceStatus.RUNNING

                result[service_id] = {
                    "service_id": service_id,
                    "name": config["name"],
                    "status": state.status.value,
                    "port": config["port"],
                    "icon": config["icon"],
                    "description": config["description"],
                    "healthy": is_healthy,
                    "pid": state.pid,
                    "error": state.error_message,
                    "external": config.get("external", False),
                    "manageable": config.get("command") is not None and not config.get("external", False),
                }

        return result

    def start_service(self, service_id: str) -> dict:
        """
        Start a service.

        Args:
            service_id: The service identifier

        Returns:
            Dictionary with result information
        """
        config = SERVICES.get(service_id)
        if not config:
            return {"success": False, "error": f"Unknown service: {service_id}"}

        if config.get("external", False) or config.get("command") is None:
            return {"success": False, "error": f"Service {service_id} is not managed by this system"}

        with self._lock:
            state = self._services[service_id]

            # Check if already running
            if state.status in (ServiceStatus.RUNNING, ServiceStatus.STARTING):
                if self._health_check(service_id):
                    return {"success": True, "message": "Service already running"}

            # Check if port is in use
            if self._check_port_in_use(config["port"]):
                state.status = ServiceStatus.RUNNING
                return {"success": True, "message": "Service already running (external)"}

            # Start the service
            state.status = ServiceStatus.STARTING
            state.error_message = None
            self._emit_status(service_id, ServiceStatus.STARTING, "Starting service...")

        # Start in background thread
        thread = threading.Thread(
            target=self._start_service_thread,
            args=(service_id,),
            daemon=True
        )
        thread.start()

        return {"success": True, "message": "Service starting..."}

    def _start_service_thread(self, service_id: str):
        """Background thread to start a service and monitor startup."""
        config = SERVICES[service_id]

        try:
            # Start the process
            process = subprocess.Popen(
                config["command"],
                cwd=config["working_dir"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                shell=False
            )

            with self._lock:
                state = self._services[service_id]
                state.process = process
                state.pid = process.pid
                state.start_time = time.time()

            logger.info(f"Started {service_id} with PID {process.pid}")

            # Wait for service to become healthy
            timeout = config.get("startup_timeout", 120)
            start_time = time.time()

            while time.time() - start_time < timeout:
                # Check if process died
                if process.poll() is not None:
                    # Process exited
                    stdout, _ = process.communicate()
                    error_msg = stdout.decode('utf-8', errors='replace')[-1000:] if stdout else "Process exited"
                    with self._lock:
                        state = self._services[service_id]
                        state.status = ServiceStatus.ERROR
                        state.error_message = error_msg
                        state.process = None
                    self._emit_status(service_id, ServiceStatus.ERROR, f"Service failed to start: {error_msg[:100]}")
                    return

                # Check if healthy
                if self._health_check(service_id):
                    with self._lock:
                        state = self._services[service_id]
                        state.status = ServiceStatus.RUNNING
                    self._emit_status(service_id, ServiceStatus.RUNNING, "Service is ready")
                    logger.info(f"Service {service_id} is now healthy")
                    return

                time.sleep(2)

            # Timeout reached
            with self._lock:
                state = self._services[service_id]
                if state.status == ServiceStatus.STARTING:
                    state.status = ServiceStatus.ERROR
                    state.error_message = "Startup timeout"
            self._emit_status(service_id, ServiceStatus.ERROR, "Startup timeout - service may still be loading")

        except Exception as e:
            logger.error(f"Error starting {service_id}: {e}")
            with self._lock:
                state = self._services[service_id]
                state.status = ServiceStatus.ERROR
                state.error_message = str(e)
            self._emit_status(service_id, ServiceStatus.ERROR, f"Failed to start: {e}")

    def stop_service(self, service_id: str) -> dict:
        """
        Stop a service.

        Args:
            service_id: The service identifier

        Returns:
            Dictionary with result information
        """
        config = SERVICES.get(service_id)
        if not config:
            return {"success": False, "error": f"Unknown service: {service_id}"}

        with self._lock:
            state = self._services[service_id]
            port = config["port"]

            if state.process is None:
                # Service was not started by the dashboard; attempt to stop an
                # external process using the configured port, if any.
                if self._check_port_in_use(port):
                    logger.info(
                        "Service %s appears to be running externally on port %s; "
                        "attempting to terminate external process.",
                        service_id,
                        port,
                    )
                    killed = self._kill_process_on_port(port)
                    if killed:
                        state.status = ServiceStatus.STOPPED
                        state.pid = None
                        state.process = None
                        state.error_message = None
                        self._emit_status(service_id, ServiceStatus.STOPPED, "Service stopped")
                        return {"success": True, "message": "Service stopped"}

                    return {
                        "success": False,
                        "error": "Service running externally - unable to stop process",
                    }

                # No managed process and no listener on the port: treat as already stopped.
                state.status = ServiceStatus.STOPPED
                state.process = None
                state.pid = None
                state.error_message = None
                return {"success": True, "message": "Service already stopped"}

            state.status = ServiceStatus.STOPPING
            self._emit_status(service_id, ServiceStatus.STOPPING, "Stopping service...")

        try:
            # Try graceful termination first
            state.process.terminate()

            # Wait for process to exit
            try:
                state.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # Force kill
                state.process.kill()
                state.process.wait(timeout=5)

            with self._lock:
                state.status = ServiceStatus.STOPPED
                state.process = None
                state.pid = None
                state.error_message = None
            self._emit_status(service_id, ServiceStatus.STOPPED, "Service stopped")

            return {"success": True, "message": "Service stopped"}

        except Exception as e:  # noqa: BLE001
            with self._lock:
                state.status = ServiceStatus.ERROR
                state.error_message = str(e)
            self._emit_status(service_id, ServiceStatus.ERROR, f"Failed to stop: {e}")
            return {"success": False, "error": str(e)}

    def restart_service(self, service_id: str) -> dict:
        """
        Restart a service.

        Args:
            service_id: The service identifier

        Returns:
            Dictionary with result information
        """
        stop_result = self.stop_service(service_id)
        if not stop_result.get("success", False) and "already stopped" not in stop_result.get("message", ""):
            return stop_result

        time.sleep(2)  # Brief pause between stop and start
        return self.start_service(service_id)


# Singleton instance
_manager: Optional[ServiceManager] = None


def get_service_manager(status_callback: Optional[Callable] = None) -> ServiceManager:
    """Get or create the singleton ServiceManager instance."""
    global _manager
    if _manager is None:
        _manager = ServiceManager(status_callback)
    elif status_callback and _manager._status_callback is None:
        _manager._status_callback = status_callback
    return _manager
