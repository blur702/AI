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
from typing import Callable, Dict, Optional, Set

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
    last_activity: Optional[float] = None  # Last time service was accessed/used


class ServiceManager:
    """Manages AI service lifecycle (start, stop, status)."""

    # Default idle timeout in seconds (30 minutes)
    DEFAULT_IDLE_TIMEOUT = 30 * 60

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
        self._idle_timeout = self.DEFAULT_IDLE_TIMEOUT
        self._auto_stop_enabled = False
        self._idle_check_thread: Optional[threading.Thread] = None
        self._idle_check_stop = False
        self._test_error_services: Set[str] = set()
        # Track which services have had their auto_start_with dependencies triggered
        self._auto_start_triggered: Set[str] = set()

        # Initialize state for all services
        for service_id in SERVICES:
            self._services[service_id] = ServiceState()

    def set_test_error_mode(self, service_id: str, enabled: bool = True):
        """
        Enable or disable test-only error mode for a service.

        When enabled, start requests will simulate a startup failure and
        transition the service into ERROR without launching a real process.
        """
        with self._lock:
            if enabled:
                self._test_error_services.add(service_id)
            else:
                self._test_error_services.discard(service_id)

    def _emit_status(self, service_id: str, status: ServiceStatus, message: str = ""):
        """Emit status update via callback if configured."""
        if self._status_callback:
            try:
                self._status_callback(service_id, status.value, message)
            except Exception as e:
                logger.error(f"Error in status callback: {e}")

    def _check_auto_start_dependencies(self, service_id: str):
        """
        Check if a service that just came online has auto_start_with dependencies.
        If so, start those dependent services.
        """
        config = SERVICES.get(service_id)
        if not config:
            return

        auto_start_services = config.get("auto_start_with", [])
        if not auto_start_services:
            return

        # Only trigger once per session (reset when service goes offline)
        with self._lock:
            if service_id in self._auto_start_triggered:
                return
            self._auto_start_triggered.add(service_id)
        logger.info(f"Service {service_id} is online, auto-starting: {auto_start_services}")

        # Start dependent services in background threads
        for dep_service_id in auto_start_services:
            if dep_service_id not in SERVICES:
                logger.warning(f"Unknown auto_start_with service: {dep_service_id}")
                continue

            # Check if already running - copy status while holding lock
            should_start = False
            with self._lock:
                dep_state = self._services.get(dep_service_id)
                if not dep_state or dep_state.status != ServiceStatus.RUNNING:
                    should_start = True
                else:
                    logger.info(f"Dependent service {dep_service_id} already running")

            # Start the dependent service outside the lock
            if should_start:
                logger.info(f"Auto-starting dependent service: {dep_service_id}")
                threading.Thread(
                    target=self._auto_start_dependent_service,
                    args=(dep_service_id, service_id),
                    daemon=True
                ).start()

    def _is_docker_available(self) -> bool:
        """Check if Docker is running and available."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _auto_start_dependent_service(self, service_id: str, triggered_by: str):
        """Background thread to auto-start a dependent service."""
        try:
            # Special handling for Weaviate - requires Docker
            if service_id == "weaviate":
                if not self._is_docker_available():
                    logger.warning(
                        f"Cannot auto-start {service_id}: Docker is not running"
                    )
                    return

            result = self.start_service(service_id)
            if result.get("success"):
                logger.info(f"Auto-started {service_id} (triggered by {triggered_by})")
                
                # Only emit STARTING if the service hasn't already transitioned to RUNNING
                with self._lock:
                    state = self._services.get(service_id)
                    if state and state.status == ServiceStatus.STARTING:
                        self._emit_status(
                            service_id,
                            ServiceStatus.STARTING,
                            f"Auto-started with {SERVICES[triggered_by]['name']}"
                        )
            else:
                logger.warning(
                    f"Failed to auto-start {service_id}: {result.get('error', 'unknown')}"
                )
        except Exception as e:
            logger.error(f"Error auto-starting {service_id}: {e}")

    def _clear_auto_start_trigger(self, service_id: str):
        """Clear the auto-start trigger when a service goes offline."""
        self._auto_start_triggered.discard(service_id)

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
                target_port = str(port)
                for line in result.stdout.splitlines():
                    # Typical line: TCP    0.0.0.0:7851         0.0.0.0:0              LISTENING       1234
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

        # Capture current state while holding lock
        with self._lock:
            state = self._services.get(service_id, ServiceState())
            current_status = state.status

        # Perform blocking I/O operations outside the lock
        is_healthy = self._health_check(service_id)
        port_in_use = self._check_port_in_use(config["port"])

        # Track if we need to check auto-start after releasing lock
        should_check_auto_start = False

        # Re-acquire lock to update state
        with self._lock:
            state = self._services.get(service_id, ServiceState())
            
            # Only update if state hasn't changed significantly
            if state.status == current_status:
                # Update status based on actual state
                if state.status == ServiceStatus.STARTING:
                    if is_healthy:
                        state.status = ServiceStatus.RUNNING
                        self._emit_status(service_id, ServiceStatus.RUNNING, "Service is ready")
                elif state.status == ServiceStatus.RUNNING:
                    if not is_healthy and not port_in_use:
                        state.status = ServiceStatus.STOPPED
                        state.process = None
                        state.pid = None
                        self._clear_auto_start_trigger(service_id)
                        self._emit_status(service_id, ServiceStatus.STOPPED, "Service stopped")
                elif state.status == ServiceStatus.STOPPED:
                    if is_healthy:
                        # Service running externally - notify subscribers and mark for auto-start check
                        state.status = ServiceStatus.RUNNING
                        self._emit_status(service_id, ServiceStatus.RUNNING, "Service detected running externally")
                        should_check_auto_start = True

            result = {
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

        # Check auto-start dependencies outside the lock
        if should_check_auto_start:
            self._check_auto_start_dependencies(service_id)

        return result

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
        # Track services that need auto-start check (processed outside lock)
        services_to_auto_start = []

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
                        state.pid = None
                        self._clear_auto_start_trigger(service_id)
                        self._emit_status(service_id, ServiceStatus.STOPPED, "Service stopped")
                elif state.status == ServiceStatus.STOPPED:
                    if is_healthy:
                        state.status = ServiceStatus.RUNNING
                        # Mark for auto-start check after lock is released
                        services_to_auto_start.append(service_id)

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

        # Check auto-start dependencies for services that just came online
        for service_id in services_to_auto_start:
            self._check_auto_start_dependencies(service_id)

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
            return {
                "success": False,
                "error": f"Service {service_id} is not managed by this system",
            }

        # Test-only error mode: simulate a startup failure without launching a process
        if service_id in self._test_error_services:
            with self._lock:
                state = self._services[service_id]
                state.status = ServiceStatus.STARTING
                state.error_message = None
                self._emit_status(
                    service_id,
                    ServiceStatus.STARTING,
                    "Starting service (test error mode)...",
                )

            def _fail_start():
                time.sleep(0.5)
                with self._lock:
                    state = self._services[service_id]
                    # Only transition to error if still starting
                    if state.status == ServiceStatus.STARTING:
                        state.status = ServiceStatus.ERROR
                        state.error_message = "Test-forced startup error"
                self._emit_status(
                    service_id,
                    ServiceStatus.ERROR,
                    "Test-forced startup error",
                )

            threading.Thread(target=_fail_start, daemon=True).start()

            return {
                "success": True,
                "message": "Service starting (test error mode)",
            }

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
            target=self._start_service_thread, args=(service_id,), daemon=True
        )
        thread.start()

        return {"success": True, "message": "Service starting..."}

    def _start_service_thread(self, service_id: str):
        """Background thread to start a service and monitor startup."""
        config = SERVICES[service_id]

        try:
            # Prepare creationflags for cross-platform compatibility
            # CREATE_NEW_PROCESS_GROUP is Windows-only
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            
            # Start the process
            popen_kwargs = {
                "cwd": config["working_dir"],
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "shell": False,
            }
            if creationflags:
                popen_kwargs["creationflags"] = creationflags
            
            process = subprocess.Popen(config["command"], **popen_kwargs)

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
            # Capture process reference while holding lock
            process = state.process
            self._emit_status(service_id, ServiceStatus.STOPPING, "Stopping service...")

        try:
            # Try graceful termination first
            process.terminate()

            # Wait for process to exit
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # Force kill
                process.kill()
                process.wait(timeout=5)

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
        # Check both "message" and "error" keys for "already stopped"
        stop_message = stop_result.get("message", stop_result.get("error", ""))
        if not stop_result.get("success", False) and "already stopped" not in stop_message:
            return stop_result

        time.sleep(2)  # Brief pause between stop and start
        return self.start_service(service_id)

    def touch_activity(self, service_id: str):
        """
        Update the last activity timestamp for a service.

        Args:
            service_id: The identifier of the service whose activity timestamp should be updated.

        Behavior:
            Updates the last_activity timestamp to the current time. Does nothing if service_id
            is not found in the service registry.
        """
        with self._lock:
            if service_id in self._services:
                self._services[service_id].last_activity = time.time()

    def get_idle_time(self, service_id: str) -> Optional[float]:
        """Get idle time in seconds for a service, or None if not running."""
        with self._lock:
            state = self._services.get(service_id)
            if not state or state.status != ServiceStatus.RUNNING:
                return None
            last = state.last_activity or state.start_time
            if not last:
                return None
        
        return time.time() - last

    def _get_idle_time_unlocked(self, service_id: str) -> Optional[float]:
        """Get idle time without acquiring lock (caller must hold lock)."""
        state = self._services.get(service_id)
        if not state or state.status != ServiceStatus.RUNNING:
            return None
        last = state.last_activity or state.start_time
        if not last:
            return None
        return time.time() - last

    def set_idle_timeout(self, timeout_seconds: int):
        """Set the idle timeout in seconds."""
        self._idle_timeout = timeout_seconds

    def get_idle_timeout(self) -> int:
        """Get the current idle timeout in seconds."""
        return self._idle_timeout

    def enable_auto_stop(self, enabled: bool = True):
        """Enable or disable auto-stop for idle services."""
        self._auto_stop_enabled = enabled
        if enabled:
            self._start_idle_check_thread()
        else:
            self._stop_idle_check_thread()

    def is_auto_stop_enabled(self) -> bool:
        """Check if auto-stop is enabled."""
        return self._auto_stop_enabled

    def _start_idle_check_thread(self):
        """Start the background thread that checks for idle services."""
        if self._idle_check_thread and self._idle_check_thread.is_alive():
            return  # Already running

        self._idle_check_stop = False
        self._idle_check_thread = threading.Thread(
            target=self._idle_check_loop,
            daemon=True
        )
        self._idle_check_thread.start()
        logger.info("Idle check thread started")

    def _stop_idle_check_thread(self):
        """Stop the idle check background thread."""
        self._idle_check_stop = True
        if self._idle_check_thread:
            self._idle_check_thread.join(timeout=5)
        logger.info("Idle check thread stopped")

    def _idle_check_loop(self):
        """Background loop that stops idle services."""
        from services_config import GPU_INTENSIVE_SERVICES

        while not self._idle_check_stop:
            time.sleep(60)  # Check every minute

            if not self._auto_stop_enabled:
                continue

            services_to_stop = []

            with self._lock:
                for service_id, state in self._services.items():
                    if state.status != ServiceStatus.RUNNING:
                        continue

                    # Only auto-stop GPU-intensive services
                    if service_id not in GPU_INTENSIVE_SERVICES:
                        continue

                    idle_time = self._get_idle_time_unlocked(service_id)
                    if idle_time and idle_time > self._idle_timeout:
                        services_to_stop.append((service_id, idle_time))

            # Stop services outside the lock
            for service_id, idle_time in services_to_stop:
                logger.info(
                    f"Auto-stopping {service_id} after {idle_time:.0f}s idle"
                )
                self.stop_service(service_id)
                self._emit_status(
                    service_id,
                    ServiceStatus.STOPPED,
                    f"Auto-stopped after {idle_time // 60:.0f} min idle"
                )

    def get_resource_summary(self) -> dict:
        """Get a summary of resource usage across all services."""
        from services_config import GPU_INTENSIVE_SERVICES

        running_services = []
        idle_services = []
        total_running = 0
        gpu_intensive_running = 0

        with self._lock:
            for service_id, state in self._services.items():
                if state.status == ServiceStatus.RUNNING:
                    total_running += 1
                    idle_time = self._get_idle_time_unlocked(service_id)
                    service_info = {
                        "id": service_id,
                        "name": SERVICES[service_id]["name"],
                        "idle_seconds": idle_time,
                        "gpu_intensive": service_id in GPU_INTENSIVE_SERVICES,
                        "start_time": state.start_time,
                    }
                    running_services.append(service_info)

                    if service_id in GPU_INTENSIVE_SERVICES:
                        gpu_intensive_running += 1

                    if idle_time and idle_time > 300:  # 5 min idle threshold
                        idle_services.append(service_info)

        return {
            "total_running": total_running,
            "gpu_intensive_running": gpu_intensive_running,
            "running_services": running_services,
            "idle_services": idle_services,
            "auto_stop_enabled": self._auto_stop_enabled,
            "idle_timeout_seconds": self._idle_timeout,
        }


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
