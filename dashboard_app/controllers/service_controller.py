from __future__ import annotations

import logging
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import requests

from dashboard_app.config import AppConfig
from dashboard_app.controllers.vram_controller import VRAMMonitor

logger = logging.getLogger(__name__)


try:
    # Trust the existing services_config module layout as described in the plan.
    from dashboard.backend import services_config as svc_cfg  # type: ignore
except ImportError:  # pragma: no cover - defensive import
    svc_cfg = None  # type: ignore[assignment]

try:
    from dashboard.backend.services_config import GPU_INTENSIVE_SERVICES  # type: ignore
except ImportError:  # pragma: no cover - defensive import
    GPU_INTENSIVE_SERVICES = []  # type: ignore[assignment]


class ServiceStatus(Enum):
    """Service lifecycle states, aligned with the backend service manager."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"
    PAUSED = "paused"


@dataclass
class ServiceState:
    """In-memory runtime state for a single service."""

    service_id: str
    name: str
    section: str
    port: int
    icon: str | None
    description: str | None
    status: ServiceStatus = ServiceStatus.STOPPED
    process: subprocess.Popen | None = None
    pid: int | None = None
    start_time: float | None = None
    last_activity: float = field(default_factory=lambda: time.time())
    idle_seconds: float = 0.0
    error_message: str | None = None
    external: bool = False
    manageable: bool = True
    health_endpoint: str = "/health"
    startup_timeout: int = 60
    auto_start_with: list[str] = field(default_factory=list)
    gradio: bool = False
    is_healthy: bool = False


class ServiceController:
    """Manage lifecycle and status of dashboard services for the desktop app."""

    def __init__(self, config: AppConfig, vram_monitor: VRAMMonitor | None = None) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._states: dict[str, ServiceState] = {}
        self._configs: dict[str, dict[str, Any]] = {}
        self._auto_start_triggered: set[str] = set()
        self._auto_stop_enabled: bool = config.autostop_enabled
        self._idle_timeout: int = config.autostop_timeout_minutes * 60
        self._idle_check_thread: threading.Thread | None = None
        self._idle_check_stop: bool = False
        self._vram_monitor: VRAMMonitor | None = vram_monitor
        self._load_services_from_config()

    # ------------------------------------------------------------------ #
    # Config loading
    # ------------------------------------------------------------------ #

    def _load_services_from_config(self) -> None:
        """Initialize service configuration and initial states."""
        if svc_cfg is None:
            logger.warning("services_config could not be imported; no services loaded")
            return

        services = getattr(svc_cfg, "SERVICES", {})

        with self._lock:
            for service_id, meta in services.items():
                name = meta.get("name", service_id)
                section = meta.get("section", "Main")
                port = int(meta.get("port", 0))
                icon = meta.get("icon")
                description = meta.get("description")

                working_dir = meta.get("working_dir") or meta.get("cwd")
                command = meta.get("command") or meta.get("cmd")
                health_endpoint = meta.get("health_endpoint", "/health")
                startup_timeout = int(meta.get("startup_timeout", 60))
                external = bool(meta.get("external", False))
                auto_start_with = list(meta.get("auto_start_with", []))
                gradio = bool(meta.get("gradio", False))

                self._configs[service_id] = {
                    "service_id": service_id,
                    "name": name,
                    "section": section,
                    "port": port,
                    "icon": icon,
                    "description": description,
                    "working_dir": working_dir,
                    "command": command,
                    "health_endpoint": health_endpoint,
                    "startup_timeout": startup_timeout,
                    "external": external,
                    "auto_start_with": auto_start_with,
                    "gradio": gradio,
                }

                if service_id not in self._states:
                    self._states[service_id] = ServiceState(
                        service_id=service_id,
                        name=name,
                        section=section,
                        port=port,
                        icon=icon,
                        description=description,
                        external=external,
                        manageable=bool(command) and not external,
                        health_endpoint=health_endpoint,
                        startup_timeout=startup_timeout,
                        auto_start_with=auto_start_with,
                        gradio=gradio,
                    )

    # ------------------------------------------------------------------ #
    # Utility helpers
    # ------------------------------------------------------------------ #

    def _touch_activity(self, state: ServiceState) -> None:
        state.last_activity = time.time()

    def _update_idle_times(self) -> None:
        now = time.time()
        for state in self._states.values():
            state.idle_seconds = max(0.0, now - (state.last_activity or now))

    def _is_docker_available(self) -> bool:
        """Check if Docker daemon is reachable."""
        try:
            proc = subprocess.run(
                ["docker", "info"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            return proc.returncode == 0
        except Exception:
            return False

    def _check_port_in_use(self, port: int) -> bool:
        if port <= 0:
            return False
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        try:
            result = sock.connect_ex(("127.0.0.1", port))
            return result == 0
        except OSError:
            return False
        finally:
            sock.close()

    def _kill_process_on_port(self, port: int) -> None:
        """Attempt to kill any process listening on the given port."""
        if port <= 0:
            return

        try:
            if subprocess.os.name == "nt":  # Windows
                subprocess.run(
                    [
                        "powershell",
                        "-Command",
                        (
                            "netstat -ano | Select-String ':{0} ' | "
                            "ForEach-Object { ($_ -split '\\s+')[-1] } | "
                            "Select-Object -First 1 | "
                            "ForEach-Object { if ($_ -match '^[0-9]+$') "
                            "{ taskkill /PID $_ /F } }"
                        ).format(port),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:  # Unix-like
                subprocess.run(
                    [
                        "bash",
                        "-lc",
                        f"lsof -ti tcp:{port} | xargs -r kill -9",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
        except Exception as exc:
            logger.warning("Failed to kill process on port %s: %s", port, exc)

    def _health_check(self, service_id: str) -> bool:
        """Return True if the service's health endpoint responds with 200."""
        with self._lock:
            state = self._states.get(service_id)
            cfg = self._configs.get(service_id)
        if not state or not cfg or not state.port:
            return False

        url = f"http://127.0.0.1:{state.port}{cfg['health_endpoint']}"
        try:
            resp = requests.get(url, timeout=2.0)
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Auto-start dependencies
    # ------------------------------------------------------------------ #

    def _check_auto_start_dependencies(self, service_id: str) -> None:
        cfg = self._configs.get(service_id)
        if not cfg:
            return
        for dep_id in cfg.get("auto_start_with", []):
            if dep_id in self._auto_start_triggered:
                continue
            self._auto_start_triggered.add(dep_id)
            threading.Thread(
                target=self._auto_start_dependent_service,
                args=(dep_id, service_id),
                daemon=True,
            ).start()

    def _auto_start_dependent_service(self, service_id: str, triggered_by: str) -> None:
        cfg = self._configs.get(service_id)
        if not cfg:
            return

        if service_id == "weaviate" and not self._is_docker_available():
            logger.info("Skipping auto-start of %s (Docker not available)", service_id)
            return

        logger.info("Auto-starting %s (triggered by %s)", service_id, triggered_by)
        self.start_service(service_id)

    def _clear_auto_start_trigger(self, service_id: str) -> None:
        self._auto_start_triggered.discard(service_id)

    # ------------------------------------------------------------------ #
    # Auto-stop for idle GPU services
    # ------------------------------------------------------------------ #

    def enable_auto_stop(self, enabled: bool) -> None:
        """Enable or disable auto-stop for idle GPU-intensive services."""
        self._auto_stop_enabled = bool(enabled)
        if enabled:
            self._start_idle_check_thread()
        else:
            self._stop_idle_check_thread()

    def set_idle_timeout(self, minutes: int) -> None:
        """Set idle timeout in minutes."""
        self._idle_timeout = max(1, int(minutes)) * 60

    def _start_idle_check_thread(self) -> None:
        if self._idle_check_thread and self._idle_check_thread.is_alive():
            return
        self._idle_check_stop = False
        self._idle_check_thread = threading.Thread(
            target=self._idle_check_loop, name="idle-check", daemon=True
        )
        self._idle_check_thread.start()

    def _stop_idle_check_thread(self) -> None:
        self._idle_check_stop = True
        if self._idle_check_thread and self._idle_check_thread.is_alive():
            self._idle_check_thread.join(timeout=2.0)

    def _idle_check_loop(self) -> None:
        """Background loop that stops idle GPU-intensive services."""
        while not self._idle_check_stop:
            time.sleep(60)
            if not self._auto_stop_enabled or self._idle_timeout <= 0:
                continue

            now = time.time()
            to_stop: list[str] = []

            # Optional VRAM pressure check (falls back to idle-only when unavailable).
            usage_high = False
            if self._vram_monitor is not None:
                try:
                    stats = self._vram_monitor.get_gpu_stats()
                    total = stats.get("total_mb") or stats.get("total_vram")
                    used = stats.get("used_mb") or stats.get("used_vram")
                    if total and used is not None:
                        pct = (used * 100.0) / float(total)
                        usage_high = pct >= 90.0
                except Exception:
                    usage_high = False

            with self._lock:
                self._update_idle_times()
                for sid in GPU_INTENSIVE_SERVICES:
                    state = self._states.get(sid)
                    if not state:
                        continue
                    if state.status is not ServiceStatus.RUNNING:
                        continue
                    idle = now - (state.last_activity or now)
                    # Stop when fully idle beyond timeout, or when VRAM is under pressure
                    # and the service has been idle for at least half the timeout.
                    if idle >= self._idle_timeout or (
                        usage_high and idle >= self._idle_timeout / 2
                    ):
                        to_stop.append(sid)

            for sid in to_stop:
                logger.info("Auto-stopping idle GPU service %s", sid)
                try:
                    self.stop_service(sid)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("Error auto-stopping %s: %s", sid, exc)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get_all_statuses(self) -> list[dict]:
        """Return a snapshot of all known service statuses as dicts."""
        with self._lock:
            self._update_idle_times()
            result: list[dict] = []
            for service_id, state in self._states.items():
                cfg = self._configs.get(service_id, {})
                result.append(
                    {
                        "service_id": service_id,
                        "name": state.name,
                        "status": state.status.value,
                        "port": state.port,
                        "icon": state.icon,
                        "description": state.description,
                        "healthy": bool(state.is_healthy),
                        "pid": state.pid,
                        "error": state.error_message,
                        "external": state.external,
                        "manageable": state.manageable,
                        "section": state.section,
                        "idle_seconds": state.idle_seconds,
                    }
                )
            return result

    def start_service(self, service_id: str) -> None:
        """Start a service using subprocess, based on services_config."""
        cfg = self._configs.get(service_id)
        if not cfg:
            logger.warning("start_service: unknown service_id %s", service_id)
            return

        with self._lock:
            state = self._states.get(service_id)
            if state is None:
                return

            if not state.manageable:
                logger.info("Service %s is not manageable; skipping start", service_id)
                return

            if state.status in {ServiceStatus.RUNNING, ServiceStatus.STARTING}:
                return

            port = state.port

        if port and self._check_port_in_use(port):
            # Something is already listening; treat as running service.
            with self._lock:
                state = self._states.get(service_id)
                if state is None:
                    return
                state.status = ServiceStatus.RUNNING
                state.error_message = None
                state.process = None
                state.pid = None
                state.start_time = None
                self._touch_activity(state)
            logger.info("Service %s port %s already in use; marking as RUNNING", service_id, port)
            self._check_auto_start_dependencies(service_id)
            return

        command = cfg.get("command")
        if not command:
            logger.info("Service %s has no command configured; cannot start", service_id)
            return

        with self._lock:
            state = self._states.get(service_id)
            if state is None:
                return
            state.status = ServiceStatus.STARTING
            state.error_message = None
            state.start_time = time.time()
            state.is_healthy = False

        logger.info("Starting service %s", service_id)
        thread = threading.Thread(
            target=self._start_service_thread, args=(service_id,), daemon=True
        )
        thread.start()

    def _start_service_thread(self, service_id: str) -> None:
        cfg = self._configs.get(service_id)
        if not cfg:
            return

        working_dir = cfg.get("working_dir") or None
        command = cfg.get("command")
        if not command:
            return

        try:
            proc = subprocess.Popen(
                command,
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            logger.error("Failed to start service %s: %s", service_id, exc)
            with self._lock:
                state = self._states.get(service_id)
                if state:
                    state.status = ServiceStatus.ERROR
                    state.error_message = str(exc)
                    state.process = None
                    state.pid = None
                    state.start_time = None
            return

        with self._lock:
            state = self._states.get(service_id)
            if not state:
                proc.terminate()
                return
            state.process = proc
            state.pid = proc.pid
            state.start_time = time.time()
            state.is_healthy = False
            self._touch_activity(state)

        timeout = cfg.get("startup_timeout", 60)
        deadline = time.time() + timeout

        while time.time() < deadline:
            # Process died during startup.
            if proc.poll() is not None:
                logger.error("Service %s exited during startup", service_id)
                with self._lock:
                    state = self._states.get(service_id)
                    if state:
                        state.status = ServiceStatus.ERROR
                        state.error_message = "Process exited during startup"
                        state.process = None
                        state.pid = None
                        state.start_time = None
                return

            if self._health_check(service_id):
                logger.info("Service %s is RUNNING", service_id)
                with self._lock:
                    state = self._states.get(service_id)
                    if state:
                        state.status = ServiceStatus.RUNNING
                        state.error_message = None
                        self._touch_activity(state)
                self._check_auto_start_dependencies(service_id)
                return

            time.sleep(2)

        # Timeout
        logger.error("Service %s startup timed out after %s seconds", service_id, timeout)
        with self._lock:
            state = self._states.get(service_id)
            if state:
                state.status = ServiceStatus.ERROR
                state.error_message = f"Startup timed out after {timeout} seconds"
                state.process = None
                state.pid = None
                state.start_time = None
                state.is_healthy = False

    def stop_service(self, service_id: str) -> None:
        """Gracefully stop a service."""
        cfg = self._configs.get(service_id)
        if not cfg:
            return

        with self._lock:
            state = self._states.get(service_id)
            if state is None:
                return

            if state.external or not state.manageable:
                logger.info(
                    "Service %s is external or not manageable; skipping stop",
                    service_id,
                )
                return

            if state.status in {ServiceStatus.STOPPED, ServiceStatus.ERROR}:
                return

            state.status = ServiceStatus.STOPPING
            state.error_message = None
            state.is_healthy = False
            proc = state.process
            port = state.port

        if proc is not None:
            logger.info("Stopping service %s (PID %s)", service_id, proc.pid)
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning("Service %s did not exit after terminate(); killing", service_id)
                    proc.kill()
            except Exception as exc:
                logger.warning("Error stopping service %s: %s", service_id, exc)

        elif port:
            logger.info("Stopping service %s by killing port %s", service_id, port)
            self._kill_process_on_port(port)

        with self._lock:
            state = self._states.get(service_id)
            if state:
                state.status = ServiceStatus.STOPPED
                state.process = None
                state.pid = None
                state.start_time = None
                state.is_healthy = False
        self._clear_auto_start_trigger(service_id)

    def refresh_statuses(self) -> None:
        """Poll all services concurrently and update their status."""
        with self._lock:
            service_ids = list(self._states.keys())
            ports = {sid: self._states[sid].port for sid in service_ids}

        health_results: dict[str, bool] = {}
        port_results: dict[str, bool] = {}

        with ThreadPoolExecutor(max_workers=10) as executor:
            health_futures = {executor.submit(self._health_check, sid): sid for sid in service_ids}
            port_futures = {
                executor.submit(self._check_port_in_use, port): sid
                for sid, port in ports.items()
                if port
            }

            for future in as_completed(health_futures, timeout=10):
                sid = health_futures[future]
                try:
                    health_results[sid] = bool(future.result())
                except Exception:
                    health_results[sid] = False

            for future in as_completed(port_futures, timeout=10):
                sid = port_futures[future]
                try:
                    port_results[sid] = bool(future.result())
                except Exception:
                    port_results[sid] = False

        now = time.time()
        with self._lock:
            for sid, state in self._states.items():
                healthy = health_results.get(sid, False)
                port_in_use = port_results.get(sid, False)
                state.is_healthy = healthy

                # Detect startup timeout while still in STARTING.
                if state.status is ServiceStatus.STARTING and state.start_time is not None:
                    if now - state.start_time > float(state.startup_timeout or 60) and not healthy:
                        state.status = ServiceStatus.ERROR
                        state.error_message = (
                            f"Startup timed out after {state.startup_timeout} seconds"
                        )

                if state.status is ServiceStatus.STARTING and healthy:
                    state.status = ServiceStatus.RUNNING
                    state.error_message = None
                    self._touch_activity(state)
                    logger.info("Service %s is RUNNING (via health check)", sid)
                    self._check_auto_start_dependencies(sid)

                elif state.status is ServiceStatus.RUNNING:
                    if not healthy and not port_in_use:
                        state.status = ServiceStatus.STOPPED
                        state.process = None
                        state.pid = None
                        state.start_time = None
                        logger.info("Service %s appears stopped (health/port down)", sid)
                        self._clear_auto_start_trigger(sid)

                elif state.status in {ServiceStatus.STOPPED, ServiceStatus.ERROR}:
                    if healthy or port_in_use:
                        state.status = ServiceStatus.RUNNING
                        state.error_message = None
                        logger.info("Service %s detected as RUNNING (external)", sid)
                        self._check_auto_start_dependencies(sid)

            self._update_idle_times()

    def cleanup(self) -> None:
        """Terminate any tracked processes on shutdown."""
        with self._lock:
            states = list(self._states.values())

        for state in states:
            proc = state.process
            if proc is None:
                continue
            logger.info("Cleaning up service %s (PID %s)", state.service_id, proc.pid)
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception as exc:
                logger.warning("Error cleaning up service %s: %s", state.service_id, exc)
