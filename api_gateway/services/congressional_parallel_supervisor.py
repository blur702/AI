"""
Congressional scraper parallel supervisor.

Manages 20 worker processes scraping House member websites in parallel.
Monitors health via heartbeat files and auto-restarts failed workers.

Usage:
    python -m api_gateway.services.congressional_parallel_supervisor start
    python -m api_gateway.services.congressional_parallel_supervisor check
    python -m api_gateway.services.congressional_parallel_supervisor status
    python -m api_gateway.services.congressional_parallel_supervisor stop
    python -m api_gateway.services.congressional_parallel_supervisor rebalance
    python -m api_gateway.services.congressional_parallel_supervisor install-task
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..utils.logger import get_logger
from .congressional_scraper import CongressionalDocScraper, MemberInfo, ScrapeConfig

logger = get_logger("api_gateway.congressional_parallel_supervisor")

DEFAULT_CONFIG_PATH = Path("D:/AI/data/scraper/congressional/congressional_parallel_config.json")


@dataclass
class SupervisorConfig:
    """Configuration for the supervisor."""

    worker_count: int = 20
    heartbeat_timeout_seconds: int = 300
    health_check_interval_seconds: int = 30
    max_restarts_per_worker: int = 3
    restart_cooldown_seconds: int = 60
    stale_heartbeat_kill_timeout_seconds: int = 600


@dataclass
class WorkerPaths:
    """Paths for worker files."""

    data_dir: Path
    heartbeat_dir: Path
    checkpoint_dir: Path
    log_dir: Path
    pid_file: Path


@dataclass
class WorkerState:
    """State of a single worker."""

    worker_id: int
    pid: int | None = None
    process: subprocess.Popen | None = None
    status: str = "pending"  # pending, running, crashed, completed, killed
    start_index: int = 0
    end_index: int = 0
    last_heartbeat: datetime | None = None
    restart_count: int = 0
    last_restart: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "pid": self.pid,
            "status": self.status,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "restart_count": self.restart_count,
            "last_restart": self.last_restart.isoformat() if self.last_restart else None,
        }


@dataclass
class WorkAssignment:
    """Work assignment for all workers."""

    created_at: str
    total_members: int
    worker_count: int
    assignments: list[dict[str, Any]] = field(default_factory=list)


class ParallelSupervisor:
    """Supervisor that manages parallel worker processes."""

    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self.config = self._load_config()
        self.paths = self._load_paths()
        self.workers: dict[int, WorkerState] = {}
        self._ensure_directories()

    def _load_config(self) -> SupervisorConfig:
        """Load configuration from file."""
        if self.config_path.exists():
            data = json.loads(self.config_path.read_text())
            supervisor_data = data.get("supervisor", {})
            return SupervisorConfig(
                worker_count=supervisor_data.get("worker_count", 20),
                heartbeat_timeout_seconds=supervisor_data.get("heartbeat_timeout_seconds", 300),
                health_check_interval_seconds=supervisor_data.get(
                    "health_check_interval_seconds", 30
                ),
                max_restarts_per_worker=supervisor_data.get("max_restarts_per_worker", 3),
                restart_cooldown_seconds=supervisor_data.get("restart_cooldown_seconds", 60),
                stale_heartbeat_kill_timeout_seconds=supervisor_data.get(
                    "stale_heartbeat_kill_timeout_seconds", 600
                ),
            )
        return SupervisorConfig()

    def _load_paths(self) -> WorkerPaths:
        """Load paths from config file."""
        if self.config_path.exists():
            data = json.loads(self.config_path.read_text())
            paths_data = data.get("paths", {})
            return WorkerPaths(
                data_dir=Path(paths_data.get("data_dir", "D:/AI/data/scraper/congressional")),
                heartbeat_dir=Path(
                    paths_data.get("heartbeat_dir", "D:/AI/data/scraper/congressional/heartbeats")
                ),
                checkpoint_dir=Path(
                    paths_data.get("checkpoint_dir", "D:/AI/data/scraper/congressional/checkpoints")
                ),
                log_dir=Path(paths_data.get("log_dir", "D:/AI/logs/congressional_scraper")),
                pid_file=Path(
                    paths_data.get("pid_file", "D:/AI/data/scraper/congressional/supervisor.pid")
                ),
            )
        return WorkerPaths(
            data_dir=Path("D:/AI/data/scraper/congressional"),
            heartbeat_dir=Path("D:/AI/data/scraper/congressional/heartbeats"),
            checkpoint_dir=Path("D:/AI/data/scraper/congressional/checkpoints"),
            log_dir=Path("D:/AI/logs/congressional_scraper"),
            pid_file=Path("D:/AI/data/scraper/congressional/supervisor.pid"),
        )

    def _ensure_directories(self) -> None:
        """Create required directories."""
        self.paths.heartbeat_dir.mkdir(parents=True, exist_ok=True)
        self.paths.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.paths.log_dir.mkdir(parents=True, exist_ok=True)

    def _fetch_members(self) -> list[MemberInfo]:
        """Fetch member list from House feed."""
        logger.info("Fetching member list for work assignment...")
        scrape_config = ScrapeConfig(request_delay=1.0)
        with CongressionalDocScraper(scrape_config) as scraper:
            members = scraper.fetch_member_feed()
        members.sort(key=lambda m: m.name)
        logger.info("Fetched %d members", len(members))
        return members

    def _create_work_assignments(self, members: list[MemberInfo]) -> WorkAssignment:
        """Divide members among workers."""
        total = len(members)
        worker_count = self.config.worker_count
        chunk_size = (total + worker_count - 1) // worker_count  # Ceiling division

        assignments = []
        for i in range(worker_count):
            start = i * chunk_size
            end = min(start + chunk_size, total)
            if start >= total:
                break
            assignments.append(
                {
                    "worker_id": i,
                    "start_index": start,
                    "end_index": end,
                    "member_count": end - start,
                }
            )

        return WorkAssignment(
            created_at=datetime.now(UTC).isoformat(),
            total_members=total,
            worker_count=len(assignments),
            assignments=assignments,
        )

    def _save_work_assignments(self, assignment: WorkAssignment) -> None:
        """Save work assignments to file."""
        path = self.paths.data_dir / "work_assignments.json"
        path.write_text(json.dumps(asdict(assignment), indent=2))
        logger.info("Saved work assignments to %s", path)

    def _load_work_assignments(self) -> WorkAssignment | None:
        """Load work assignments from file."""
        path = self.paths.data_dir / "work_assignments.json"
        if path.exists():
            data = json.loads(path.read_text())
            return WorkAssignment(**data)
        return None

    def _write_pid_file(self) -> None:
        """Write supervisor PID file."""
        self.paths.pid_file.write_text(str(os.getpid()))

    def _read_pid_file(self) -> int | None:
        """Read supervisor PID from file."""
        if self.paths.pid_file.exists():
            try:
                return int(self.paths.pid_file.read_text().strip())
            except ValueError:
                return None
        return None

    def _delete_pid_file(self) -> None:
        """Delete supervisor PID file."""
        if self.paths.pid_file.exists():
            self.paths.pid_file.unlink()

    def _start_worker(
        self,
        worker_id: int,
        start_index: int,
        end_index: int,
        remaining: bool = False,
    ) -> subprocess.Popen:
        """Start a single worker process.

        Args:
            worker_id: The worker's ID number
            start_index: Start index in member list
            end_index: End index in member list
            remaining: If True, use remaining_members.json instead of House feed
        """
        cmd = [
            sys.executable,
            "-m",
            "api_gateway.services.congressional_worker",
            "--worker-id",
            str(worker_id),
            "--start-index",
            str(start_index),
            "--end-index",
            str(end_index),
            "--config",
            str(self.config_path),
        ]

        if remaining:
            cmd.append("--remaining")

        log_file = self.paths.log_dir / f"worker_{worker_id}.log"
        mode_str = "REBALANCED " if remaining else ""
        logger.info(
            "Starting %sworker %d (members %d-%d), log: %s",
            mode_str,
            worker_id,
            start_index,
            end_index,
            log_file,
        )

        with open(log_file, "a") as log:
            log.write(f"\n{'='*60}\n")
            log.write(f"Worker {worker_id} {mode_str}start at {datetime.now(UTC).isoformat()}\n")
            log.write(f"{'='*60}\n\n")

            # Windows: CREATE_NO_WINDOW to hide console
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NO_WINDOW

            process = subprocess.Popen(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=Path("D:/AI"),
                creationflags=creationflags,
            )

        return process

    def _kill_worker(self, worker_id: int) -> bool:
        """Kill a worker process."""
        worker = self.workers.get(worker_id)
        if not worker or not worker.pid:
            return False

        logger.warning("Killing worker %d (PID %d)", worker_id, worker.pid)

        try:
            if sys.platform == "win32":
                # Try graceful termination first
                result = subprocess.run(
                    ["taskkill", "/PID", str(worker.pid)],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode != 0:
                    # Force kill
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(worker.pid)],
                        capture_output=True,
                    )
            else:
                os.kill(worker.pid, 9)

            worker.status = "killed"
            return True
        except Exception as e:
            logger.error("Failed to kill worker %d: %s", worker_id, e)
            return False

    def _read_heartbeat(self, worker_id: int) -> dict[str, Any] | None:
        """Read heartbeat file for a worker."""
        path = self.paths.heartbeat_dir / f"worker_{worker_id}.json"
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                pass
        return None

    def _check_worker_health(self, worker_id: int) -> str:
        """
        Check health of a worker.

        Returns: "healthy", "crashed", "stale", "completed", "unknown"
        """
        worker = self.workers.get(worker_id)
        if not worker:
            return "unknown"

        # Check process status
        if worker.process:
            poll_result = worker.process.poll()
            if poll_result is not None:
                # Process exited
                if poll_result == 0:
                    return "completed"
                else:
                    logger.warning("Worker %d exited with code %d", worker_id, poll_result)
                    return "crashed"

        # Check heartbeat
        heartbeat = self._read_heartbeat(worker_id)
        if not heartbeat:
            return "unknown"

        # Check heartbeat status
        if heartbeat.get("status") == "completed":
            return "completed"
        if heartbeat.get("status") == "failed":
            return "crashed"

        # Check heartbeat freshness
        last_beat_str = heartbeat.get("last_heartbeat")
        if last_beat_str:
            last_beat = datetime.fromisoformat(last_beat_str.replace("Z", "+00:00"))
            age = (datetime.now(UTC) - last_beat).total_seconds()

            if age > self.config.stale_heartbeat_kill_timeout_seconds:
                logger.warning("Worker %d heartbeat very stale (%.0fs), needs kill", worker_id, age)
                return "stale"
            elif age > self.config.heartbeat_timeout_seconds:
                logger.warning("Worker %d heartbeat stale (%.0fs)", worker_id, age)
                return "stale"

        return "healthy"

    def _can_restart_worker(self, worker_id: int) -> bool:
        """Check if worker can be restarted (within limits)."""
        worker = self.workers.get(worker_id)
        if not worker:
            return True

        # Check restart count
        if worker.restart_count >= self.config.max_restarts_per_worker:
            logger.error(
                "Worker %d exceeded max restarts (%d)",
                worker_id,
                self.config.max_restarts_per_worker,
            )
            return False

        # Check cooldown
        if worker.last_restart:
            elapsed = (datetime.now(UTC) - worker.last_restart).total_seconds()
            if elapsed < self.config.restart_cooldown_seconds:
                logger.info(
                    "Worker %d in restart cooldown (%.0fs remaining)",
                    worker_id,
                    self.config.restart_cooldown_seconds - elapsed,
                )
                return False

        return True

    def start_all_workers(self) -> None:
        """Start all worker processes."""
        logger.info("Starting parallel supervisor with %d workers", self.config.worker_count)

        # Write PID file
        self._write_pid_file()

        # Fetch members and create assignments
        members = self._fetch_members()
        assignment = self._create_work_assignments(members)
        self._save_work_assignments(assignment)

        # Start workers
        for a in assignment.assignments:
            worker_id = a["worker_id"]
            start_index = a["start_index"]
            end_index = a["end_index"]

            process = self._start_worker(worker_id, start_index, end_index)

            self.workers[worker_id] = WorkerState(
                worker_id=worker_id,
                pid=process.pid,
                process=process,
                status="running",
                start_index=start_index,
                end_index=end_index,
            )

        logger.info("Started %d workers", len(self.workers))

    def run_health_check(self) -> dict[str, Any]:
        """Run a single health check on all workers."""
        # Load existing work assignments
        assignment = self._load_work_assignments()
        if not assignment:
            logger.warning("No work assignments found")
            return {"error": "No work assignments found"}

        # Initialize worker states from assignments if not already done
        if not self.workers:
            for a in assignment.assignments:
                self.workers[a["worker_id"]] = WorkerState(
                    worker_id=a["worker_id"],
                    start_index=a["start_index"],
                    end_index=a["end_index"],
                )

        results = {
            "timestamp": datetime.now(UTC).isoformat(),
            "workers": {},
            "actions": [],
        }

        for worker_id, worker in self.workers.items():
            health = self._check_worker_health(worker_id)
            heartbeat = self._read_heartbeat(worker_id)

            results["workers"][worker_id] = {
                "health": health,
                "heartbeat": heartbeat,
                "restart_count": worker.restart_count,
            }

            # Take action based on health
            if health == "completed":
                worker.status = "completed"
                results["actions"].append(f"Worker {worker_id} completed")

            elif health in ("crashed", "stale"):
                # Try to restart
                if self._can_restart_worker(worker_id):
                    if health == "stale":
                        self._kill_worker(worker_id)

                    process = self._start_worker(worker_id, worker.start_index, worker.end_index)
                    worker.pid = process.pid
                    worker.process = process
                    worker.status = "running"
                    worker.restart_count += 1
                    worker.last_restart = datetime.now(UTC)
                    results["actions"].append(f"Restarted worker {worker_id}")
                else:
                    results["actions"].append(f"Worker {worker_id} failed, max restarts exceeded")

        return results

    def get_status(self) -> dict[str, Any]:
        """Get status of all workers."""
        assignment = self._load_work_assignments()

        status = {
            "supervisor_pid": self._read_pid_file(),
            "config": asdict(self.config),
            "assignment": asdict(assignment) if assignment else None,
            "workers": {},
        }

        if assignment:
            for a in assignment.assignments:
                worker_id = a["worker_id"]
                heartbeat = self._read_heartbeat(worker_id)
                status["workers"][worker_id] = {
                    "assignment": a,
                    "heartbeat": heartbeat,
                }

        return status

    def stop_all_workers(self) -> None:
        """Stop all worker processes."""
        logger.info("Stopping all workers...")

        assignment = self._load_work_assignments()
        if not assignment:
            return

        for a in assignment.assignments:
            worker_id = a["worker_id"]
            heartbeat = self._read_heartbeat(worker_id)
            if heartbeat and heartbeat.get("pid"):
                pid = heartbeat["pid"]
                logger.info("Killing worker %d (PID %d)", worker_id, pid)
                try:
                    if sys.platform == "win32":
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                    else:
                        os.kill(pid, 9)
                except Exception as e:
                    logger.warning("Failed to kill worker %d: %s", worker_id, e)

        # Delete PID file
        self._delete_pid_file()
        logger.info("All workers stopped")

    def install_task(self, interval_minutes: int = 5) -> bool:
        """Install Windows scheduled task for health checks."""
        if sys.platform != "win32":
            logger.error("Task installation only supported on Windows")
            return False

        task_name = "CongressionalScraperSupervisor"
        python_exe = sys.executable
        working_dir = Path("D:/AI")

        cmd = f'cd /d "{working_dir}" && "{python_exe}" -m api_gateway.services.congressional_parallel_supervisor check'

        logger.info(
            "Installing scheduled task '%s' (every %d minutes)", task_name, interval_minutes
        )

        try:
            result = subprocess.run(
                [
                    "schtasks",
                    "/create",
                    "/tn",
                    task_name,
                    "/tr",
                    f'cmd /c "{cmd}"',
                    "/sc",
                    "MINUTE",
                    "/mo",
                    str(interval_minutes),
                    "/ru",
                    "SYSTEM",
                    "/rl",
                    "HIGHEST",
                    "/f",
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                logger.info("Task installed successfully")
                return True
            else:
                logger.error("Failed to install task: %s", result.stderr)
                return False
        except Exception as e:
            logger.error("Failed to install task: %s", e)
            return False

    def uninstall_task(self) -> bool:
        """Uninstall Windows scheduled task."""
        if sys.platform != "win32":
            logger.error("Task uninstallation only supported on Windows")
            return False

        task_name = "CongressionalScraperSupervisor"

        try:
            result = subprocess.run(
                [
                    "schtasks",
                    "/delete",
                    "/tn",
                    task_name,
                    "/f",
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                logger.info("Task uninstalled successfully")
                return True
            else:
                logger.error("Failed to uninstall task: %s", result.stderr)
                return False
        except Exception as e:
            logger.error("Failed to uninstall task: %s", e)
            return False

    def _collect_completed_members(self) -> set[str]:
        """Collect all completed member names from checkpoint files."""
        completed: set[str] = set()

        for checkpoint_file in self.paths.checkpoint_dir.glob("worker_*_checkpoint.json"):
            try:
                data = json.loads(checkpoint_file.read_text())
                members_completed = data.get("members_completed", [])
                completed.update(members_completed)
                logger.info(
                    "Loaded %d completed members from %s",
                    len(members_completed),
                    checkpoint_file.name,
                )
            except Exception as e:
                logger.warning("Failed to read checkpoint %s: %s", checkpoint_file, e)

        logger.info("Total completed members from checkpoints: %d", len(completed))
        return completed

    def _clear_checkpoints_and_heartbeats(self) -> None:
        """Clear all checkpoint and heartbeat files."""
        # Clear checkpoints
        for f in self.paths.checkpoint_dir.glob("worker_*_checkpoint.json"):
            try:
                f.unlink()
                logger.info("Deleted checkpoint: %s", f.name)
            except FileNotFoundError:
                # File already deleted (possibly by concurrent operation)
                pass
            except OSError as e:
                logger.warning("Failed to delete checkpoint %s: %s", f.name, e)

        # Clear heartbeats
        for f in self.paths.heartbeat_dir.glob("worker_*.json"):
            try:
                f.unlink()
                logger.info("Deleted heartbeat: %s", f.name)
            except FileNotFoundError:
                # File already deleted (possibly by concurrent operation)
                pass
            except OSError as e:
                logger.warning("Failed to delete heartbeat %s: %s", f.name, e)

    def _create_rebalanced_assignments(self, remaining_members: list[MemberInfo]) -> WorkAssignment:
        """Create work assignments for remaining members only."""
        total = len(remaining_members)
        worker_count = min(
            self.config.worker_count, total
        )  # Don't create more workers than members

        if worker_count == 0:
            return WorkAssignment(
                created_at=datetime.now(UTC).isoformat(),
                total_members=0,
                worker_count=0,
                assignments=[],
            )

        chunk_size = (total + worker_count - 1) // worker_count  # Ceiling division

        assignments = []
        for i in range(worker_count):
            start = i * chunk_size
            end = min(start + chunk_size, total)
            if start >= total:
                break
            assignments.append(
                {
                    "worker_id": i,
                    "start_index": start,
                    "end_index": end,
                    "member_count": end - start,
                }
            )

        return WorkAssignment(
            created_at=datetime.now(UTC).isoformat(),
            total_members=total,
            worker_count=len(assignments),
            assignments=assignments,
        )

    def _wait_for_workers_to_stop(self, timeout: float = 10.0) -> None:
        """Wait for all tracked worker processes to terminate.

        Uses deterministic process waiting instead of fixed sleep.
        Attempts graceful termination first, then forceful kill if needed.

        Args:
            timeout: Maximum seconds to wait for each process
        """
        # Collect processes from heartbeat PIDs
        assignment = self._load_work_assignments()
        if not assignment:
            return

        processes_to_wait: list[tuple] = []  # (worker_id, pid)

        for a in assignment.assignments:
            worker_id = a["worker_id"]
            heartbeat = self._read_heartbeat(worker_id)
            if heartbeat and heartbeat.get("pid"):
                processes_to_wait.append((worker_id, heartbeat["pid"]))

        for worker_id, pid in processes_to_wait:
            logger.info("Waiting for worker %d (PID %d) to terminate...", worker_id, pid)
            try:
                if sys.platform == "win32":
                    # On Windows, use taskkill and then check if process exists
                    result = subprocess.run(
                        ["taskkill", "/PID", str(pid)],
                        capture_output=True,
                        timeout=timeout,
                    )
                    if result.returncode != 0:
                        # Process may not exist or needs force kill
                        logger.info(
                            "Worker %d graceful termination failed, trying force kill", worker_id
                        )
                        subprocess.run(
                            ["taskkill", "/F", "/PID", str(pid)],
                            capture_output=True,
                            timeout=timeout,
                        )
                    # Wait a moment for the process to fully exit
                    time.sleep(0.5)
                    logger.info("Worker %d (PID %d) terminated", worker_id, pid)
                else:
                    # On Unix, we can use os.waitpid or just send signals
                    try:
                        os.kill(pid, 15)  # SIGTERM
                        time.sleep(1)
                        os.kill(pid, 9)  # SIGKILL if still alive
                    except ProcessLookupError:
                        pass  # Process already dead
                    logger.info("Worker %d (PID %d) terminated", worker_id, pid)

            except subprocess.TimeoutExpired:
                logger.warning(
                    "Timeout waiting for worker %d (PID %d), force killing", worker_id, pid
                )
                try:
                    if sys.platform == "win32":
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                    else:
                        os.kill(pid, 9)
                except Exception as e:
                    logger.error("Failed to force kill worker %d: %s", worker_id, e)

            except Exception as e:
                logger.warning("Error waiting for worker %d (PID %d): %s", worker_id, pid, e)

    def _atomic_write_json(self, path: Path, data: Any) -> None:
        """Write JSON data to a file atomically.

        Creates a temporary file, writes data, then atomically renames.

        Args:
            path: Target file path
            data: Data to serialize as JSON
        """
        # Create temp file in same directory for atomic rename
        temp_suffix = f".tmp.{uuid.uuid4().hex[:8]}"
        temp_path = path.with_suffix(path.suffix + temp_suffix)

        try:
            # Write to temp file
            content = json.dumps(data, indent=2)
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())

            # Atomic rename (overwrites target on both Windows and Unix)
            os.replace(temp_path, path)
            logger.debug("Atomically wrote %s", path)

        except Exception as e:
            # Clean up temp file on error
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
            raise e

    def rebalance(self) -> dict[str, Any]:
        """
        Rebalance work by redistributing remaining members across all workers.

        This method:
        1. Stops all running workers (with deterministic waiting)
        2. Collects completed members from checkpoints
        3. Fetches fresh member list
        4. Creates new assignments for remaining members
        5. Clears old state files
        6. Starts fresh workers
        """
        logger.info("Starting rebalance operation...")

        # Step 1: Stop all workers with deterministic waiting
        logger.info("Stopping all workers...")
        self.stop_all_workers()
        self._wait_for_workers_to_stop(timeout=10.0)

        # Step 2: Collect completed members
        completed_members = self._collect_completed_members()

        # Step 3: Fetch fresh member list
        logger.info("Fetching current member list...")
        all_members = self._fetch_members()
        all_member_names = {m.name for m in all_members}

        # Step 4: Calculate remaining members
        remaining_member_names = all_member_names - completed_members
        remaining_members = [m for m in all_members if m.name in remaining_member_names]
        remaining_members.sort(key=lambda m: m.name)

        logger.info(
            "Rebalance: %d total, %d completed, %d remaining",
            len(all_members),
            len(completed_members),
            len(remaining_members),
        )

        if not remaining_members:
            logger.info("All members already scraped!")
            return {
                "status": "complete",
                "total_members": len(all_members),
                "completed": len(completed_members),
                "remaining": 0,
                "workers_started": 0,
            }

        # Step 5: Clear old state
        logger.info("Clearing old checkpoints and heartbeats...")
        self._clear_checkpoints_and_heartbeats()

        # Step 6: Create new assignments
        assignment = self._create_rebalanced_assignments(remaining_members)

        # Save remaining members list for workers to use (atomic write)
        remaining_members_path = self.paths.data_dir / "remaining_members.json"
        remaining_members_data = [
            {
                "name": m.name,
                "url": m.website_url,
                "state": m.state,
                "district": m.district,
                "party": m.party,
            }
            for m in remaining_members
        ]
        self._atomic_write_json(remaining_members_path, remaining_members_data)
        logger.info(
            "Saved %d remaining members to %s", len(remaining_members), remaining_members_path
        )

        # Save work assignments
        self._save_work_assignments(assignment)

        # Step 7: Write PID and start workers
        self._write_pid_file()

        for a in assignment.assignments:
            worker_id = a["worker_id"]
            start_index = a["start_index"]
            end_index = a["end_index"]

            # Start worker with remaining=True to use remaining_members.json
            process = self._start_worker(worker_id, start_index, end_index, remaining=True)

            self.workers[worker_id] = WorkerState(
                worker_id=worker_id,
                pid=process.pid,
                process=process,
                status="running",
                start_index=start_index,
                end_index=end_index,
            )

        logger.info(
            "Rebalance complete: started %d workers for %d remaining members",
            len(self.workers),
            len(remaining_members),
        )

        return {
            "status": "rebalanced",
            "total_members": len(all_members),
            "completed": len(completed_members),
            "remaining": len(remaining_members),
            "workers_started": len(self.workers),
            "members_per_worker": (
                len(remaining_members) // len(self.workers) if self.workers else 0
            ),
        }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Congressional scraper parallel supervisor")
    parser.add_argument(
        "command",
        choices=["start", "check", "status", "stop", "rebalance", "install-task", "uninstall-task"],
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Config file path")
    parser.add_argument(
        "--interval", type=int, default=5, help="Task scheduler interval in minutes"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    supervisor = ParallelSupervisor(args.config)

    if args.command == "start":
        supervisor.start_all_workers()

        # Keep running and monitor
        print("Supervisor started. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(supervisor.config.health_check_interval_seconds)
                results = supervisor.run_health_check()
                if args.json:
                    print(json.dumps(results, indent=2))
                else:
                    healthy = sum(
                        1 for w in results["workers"].values() if w["health"] == "healthy"
                    )
                    completed = sum(
                        1 for w in results["workers"].values() if w["health"] == "completed"
                    )
                    print(
                        f"[{results['timestamp']}] Healthy: {healthy}, Completed: {completed}, Actions: {len(results['actions'])}"
                    )

                # Check if all completed
                all_completed = all(w["health"] == "completed" for w in results["workers"].values())
                if all_completed:
                    print("All workers completed!")
                    break

        except KeyboardInterrupt:
            print("\nStopping...")
            supervisor.stop_all_workers()

    elif args.command == "check":
        results = supervisor.run_health_check()
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"Health check at {results['timestamp']}")
            for worker_id, info in results["workers"].items():
                print(f"  Worker {worker_id}: {info['health']}")
            for action in results["actions"]:
                print(f"  Action: {action}")

    elif args.command == "status":
        status = supervisor.get_status()
        if args.json:
            print(json.dumps(status, indent=2))
        else:
            print(f"Supervisor PID: {status['supervisor_pid']}")
            print(f"Worker count: {status['config']['worker_count']}")
            if status["assignment"]:
                print(f"Total members: {status['assignment']['total_members']}")
            print("\nWorkers:")
            for worker_id, info in status["workers"].items():
                hb = info.get("heartbeat", {})
                status_str = hb.get("status", "unknown") if hb else "no heartbeat"
                members = (
                    f"{hb.get('members_processed', 0)}/{hb.get('members_total', 0)}" if hb else "?"
                )
                print(f"  Worker {worker_id}: {status_str} ({members} members)")

    elif args.command == "stop":
        supervisor.stop_all_workers()
        print("All workers stopped")

    elif args.command == "rebalance":
        result = supervisor.rebalance()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("Rebalance complete!")
            print(f"  Total members: {result['total_members']}")
            print(f"  Already completed: {result['completed']}")
            print(f"  Remaining: {result['remaining']}")
            print(f"  Workers started: {result['workers_started']}")
            if result["workers_started"] > 0:
                print(f"  Members per worker: ~{result['members_per_worker']}")
                print(
                    "\nMonitoring workers. Press Ctrl+C to detach (workers continue in background)."
                )
                try:
                    while True:
                        time.sleep(supervisor.config.health_check_interval_seconds)
                        results = supervisor.run_health_check()
                        healthy = sum(
                            1 for w in results["workers"].values() if w["health"] == "healthy"
                        )
                        completed = sum(
                            1 for w in results["workers"].values() if w["health"] == "completed"
                        )
                        print(
                            f"[{results['timestamp']}] Healthy: {healthy}, Completed: {completed}"
                        )

                        all_completed = all(
                            w["health"] == "completed" for w in results["workers"].values()
                        )
                        if all_completed:
                            print("All workers completed!")
                            break
                except KeyboardInterrupt:
                    print("\nDetaching (workers continue in background)...")

    elif args.command == "install-task":
        if supervisor.install_task(args.interval):
            print(f"Task installed (interval: {args.interval} minutes)")
        else:
            print("Failed to install task")
            sys.exit(1)

    elif args.command == "uninstall-task":
        if supervisor.uninstall_task():
            print("Task uninstalled")
        else:
            print("Failed to uninstall task")
            sys.exit(1)


if __name__ == "__main__":
    main()
