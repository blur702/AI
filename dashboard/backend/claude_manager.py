"""
Claude Code execution manager for the dashboard.

Manages Claude CLI process execution with WebSocket streaming, session tracking,
and cancellation support.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

EmitCallback = Callable[[str, Dict[str, Any]], None]

# Working directory for Claude CLI execution (hardcoded for security)
CLAUDE_WORKING_DIR = os.path.abspath("d:\\AI")

# Configuration
DEFAULT_TIMEOUT_SECONDS = 300  # 5 minutes
MAX_CONCURRENT_SESSIONS = 5
SESSION_CLEANUP_INTERVAL = 600  # 10 minutes
SESSION_MAX_AGE = 3600  # 1 hour


@dataclass
class ClaudeSession:
    """Represents a Claude CLI execution session."""

    session_id: str
    prompt: str
    mode: str  # "normal" or "yolo"
    status: str = "starting"  # starting, running, completed, cancelled, error, timeout
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    output_lines: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    process: Optional[subprocess.Popen] = None
    cancel_requested: bool = False

    def to_dict(self, include_output: bool = False) -> Dict[str, Any]:
        """Convert session to dictionary for API responses."""
        result = {
            "session_id": self.session_id,
            "prompt": self.prompt,
            "mode": self.mode,
            "status": self.status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "output_line_count": len(self.output_lines),
            "error_message": self.error_message,
        }
        if include_output:
            result["output_lines"] = self.output_lines
        return result


class ClaudeManager:
    """
    Manages Claude CLI execution with session tracking and WebSocket streaming.

    Provides:
    - Session-based execution tracking
    - Real-time output streaming via WebSocket
    - Cancellation support
    - Concurrent session limiting
    - Automatic session cleanup
    """

    def __init__(self, emit_callback: EmitCallback, socketio_start_task: Callable):
        """
        Initialize the Claude manager.

        Args:
            emit_callback: Function to emit WebSocket events.
                          Signature: emit_callback(event_name, data_dict)
            socketio_start_task: Function to start background tasks (socketio.start_background_task)
        """
        self.emit = emit_callback
        self.start_background_task = socketio_start_task
        self._sessions: Dict[str, ClaudeSession] = {}
        self._lock = threading.Lock()
        self._timeout_seconds = DEFAULT_TIMEOUT_SECONDS
        self._cleanup_thread: Optional[threading.Thread] = None
        self._cleanup_stop = False

        # Start cleanup thread
        self._start_cleanup_thread()

    def _start_cleanup_thread(self) -> None:
        """Start the background cleanup thread."""
        self._cleanup_stop = False
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="claude-session-cleanup"
        )
        self._cleanup_thread.start()
        logger.info("Claude session cleanup thread started")

    def _cleanup_loop(self) -> None:
        """Background loop that cleans up old sessions."""
        while not self._cleanup_stop:
            time.sleep(SESSION_CLEANUP_INTERVAL)
            if self._cleanup_stop:
                break
            self._cleanup_old_sessions()

    def _cleanup_old_sessions(self) -> None:
        """Remove completed sessions older than SESSION_MAX_AGE."""
        now = time.time()
        terminal_statuses = {"completed", "cancelled", "error", "timeout"}
        removed_count = 0

        with self._lock:
            sessions_to_remove = []
            for session_id, session in self._sessions.items():
                if session.status in terminal_statuses and session.end_time:
                    if now - session.end_time > SESSION_MAX_AGE:
                        sessions_to_remove.append(session_id)

            for session_id in sessions_to_remove:
                del self._sessions[session_id]
                removed_count += 1

        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} old Claude sessions")

    def set_timeout(self, seconds: int) -> None:
        """Set the execution timeout in seconds."""
        self._timeout_seconds = max(30, min(seconds, 3600))  # 30s to 1 hour

    def execute_claude(self, prompt: str, mode: str) -> Dict[str, Any]:
        """
        Start a Claude CLI execution.

        Args:
            prompt: The prompt to send to Claude
            mode: "normal" or "yolo" (YOLO skips permission prompts)

        Returns:
            Dictionary with success status and session_id or error message.
        """
        # Validate prompt
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            return {
                "success": False,
                "error": "Prompt is required and must be a non-empty string",
            }

        # Validate mode
        if mode not in ("normal", "yolo"):
            return {
                "success": False,
                "error": f"Invalid mode '{mode}'. Must be 'normal' or 'yolo'",
            }

        # Check API key
        if not os.environ.get("ANTHROPIC_API_KEY"):
            logger.warning("Claude execution attempted without API key")
            return {
                "success": False,
                "error": "ANTHROPIC_API_KEY not configured",
            }

        # Check concurrent session limit
        with self._lock:
            active_count = sum(
                1 for s in self._sessions.values()
                if s.status in ("starting", "running")
            )
            if active_count >= MAX_CONCURRENT_SESSIONS:
                return {
                    "success": False,
                    "error": f"Maximum concurrent sessions ({MAX_CONCURRENT_SESSIONS}) reached",
                }

        # Generate session ID
        session_id = str(uuid.uuid4())

        # Create session
        session = ClaudeSession(
            session_id=session_id,
            prompt=prompt.strip(),
            mode=mode,
        )

        with self._lock:
            self._sessions[session_id] = session

        # Emit updated session list (after releasing lock)
        self._emit_session_list()

        logger.info(
            f"Claude execution started: session={session_id}, mode={mode}, "
            f"prompt_length={len(prompt)} chars"
        )

        # Start background execution
        self.start_background_task(self._execute_thread, session_id)

        return {
            "success": True,
            "session_id": session_id,
            "message": "Execution started",
        }

    def _execute_thread(self, session_id: str) -> None:
        """
        Execute Claude CLI in background thread.

        Args:
            session_id: The session ID to execute
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                logger.error(f"Session {session_id} not found in execute thread")
                return
            prompt = session.prompt
            mode = session.mode

        # Build command
        cmd = ["claude", "-p", prompt]
        if mode == "yolo":
            cmd.append("--dangerously-skip-permissions")

        start_time = time.time()
        process = None

        try:
            # Emit starting status
            self.emit("claude_status", {
                "session_id": session_id,
                "status": "running",
                "message": "Starting Claude CLI",
                "timestamp": time.time(),
            })

            # Start process
            process = subprocess.Popen(
                cmd,
                cwd=CLAUDE_WORKING_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                shell=False,
                bufsize=1,  # Line buffered
            )

            with self._lock:
                session = self._sessions.get(session_id)
                if session:
                    session.status = "running"
                    session.process = process

            # Stream output
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break

                line = line.rstrip('\n\r')

                with self._lock:
                    session = self._sessions.get(session_id)
                    if session:
                        session.output_lines.append(line)
                        cancel_requested = session.cancel_requested
                    else:
                        cancel_requested = True

                # Emit output line
                self.emit("claude_output", {
                    "session_id": session_id,
                    "line": line,
                    "timestamp": time.time(),
                })

                # Check cancellation
                if cancel_requested:
                    logger.info(f"Cancellation requested for session {session_id}")
                    self._terminate_process(process)
                    self._finalize_session(session_id, "cancelled", "Execution cancelled by user")
                    return

                # Check timeout
                elapsed = time.time() - start_time
                if elapsed > self._timeout_seconds:
                    logger.warning(f"Session {session_id} timed out after {elapsed:.1f}s")
                    self._terminate_process(process)
                    self._finalize_session(session_id, "timeout", f"Execution timed out after {self._timeout_seconds}s")
                    return

            # Wait for process to complete
            return_code = process.wait()

            if return_code == 0:
                self._finalize_session(session_id, "completed", "Execution completed successfully")
            else:
                self._finalize_session(session_id, "error", f"Process exited with code {return_code}")

        except FileNotFoundError:
            error_msg = "Claude CLI not found - ensure @anthropic-ai/claude-code is installed"
            logger.error(f"Session {session_id}: {error_msg}")
            self._finalize_session(session_id, "error", error_msg)

        except PermissionError as e:
            error_msg = f"Permission denied - check working directory access: {e}"
            logger.error(f"Session {session_id}: {error_msg}")
            self._finalize_session(session_id, "error", error_msg)

        except Exception as e:
            error_msg = f"Execution error: {str(e)}"
            logger.error(f"Session {session_id}: {error_msg}", exc_info=True)
            self._finalize_session(session_id, "error", error_msg)

        finally:
            # Ensure process is cleaned up
            if process:
                try:
                    if process.stdout:
                        process.stdout.close()
                    if process.poll() is None:
                        self._terminate_process(process)
                except Exception:
                    pass

    def _terminate_process(self, process: subprocess.Popen) -> None:
        """Terminate a process gracefully, then forcefully if needed."""
        try:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Process did not terminate, killing")
                process.kill()
                process.wait(timeout=5)
        except Exception as e:
            logger.error(f"Error terminating process: {e}")

    def _finalize_session(self, session_id: str, status: str, message: str) -> None:
        """Finalize a session with the given status."""
        end_time = time.time()
        duration = 0.0

        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.status = status
                session.end_time = end_time
                session.process = None
                if status in ("error", "timeout"):
                    session.error_message = message
                duration = end_time - session.start_time

        if session:
            logger.info(f"Claude execution completed: session={session_id}, status={status}, duration={duration:.1f}s")
        else:
            logger.warning(f"Claude session not found during finalization: session={session_id}, status={status}")

        # Emit final status
        self.emit("claude_status", {
            "session_id": session_id,
            "status": status,
            "message": message,
            "timestamp": end_time,
        })

        # Emit updated session list
        self._emit_session_list()

    def _emit_session_list(self) -> None:
        """Emit the current session list via WebSocket."""
        sessions = self.get_sessions()
        self.emit("claude_session_list", {"sessions": sessions})

    def get_sessions(self) -> List[Dict[str, Any]]:
        """Get list of all sessions."""
        with self._lock:
            return [
                session.to_dict()
                for session in sorted(
                    self._sessions.values(),
                    key=lambda s: s.start_time,
                    reverse=True
                )
            ]

    def get_session(self, session_id: str, include_output: bool = False) -> Dict[str, Any]:
        """
        Get details for a specific session.

        Args:
            session_id: The session ID to retrieve
            include_output: Whether to include output lines

        Returns:
            Session dictionary or error dict if not found.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return {"error": "Session not found"}
            return session.to_dict(include_output=include_output)

    def cancel_session(self, session_id: str) -> Dict[str, Any]:
        """
        Request cancellation of a running session.

        Args:
            session_id: The session ID to cancel

        Returns:
            Dictionary with success status.
        """
        with self._lock:
            session = self._sessions.get(session_id)

            if not session:
                return {
                    "success": False,
                    "error": "Session not found",
                }

            if session.status not in ("starting", "running"):
                return {
                    "success": False,
                    "error": f"Session is not running (status: {session.status})",
                }

            session.cancel_requested = True
            logger.info(f"Cancellation requested for session {session_id}")

        return {
            "success": True,
            "message": "Cancellation requested",
            "session_id": session_id,
        }


# Singleton instance
_manager: Optional[ClaudeManager] = None


def get_claude_manager(
    emit_callback: Optional[EmitCallback] = None,
    socketio_start_task: Optional[Callable] = None
) -> ClaudeManager:
    """
    Get or create the singleton ClaudeManager instance.

    Args:
        emit_callback: Required on first call to initialize the manager.
        socketio_start_task: Required on first call to start background tasks.

    Returns:
        The ClaudeManager singleton.
    """
    global _manager
    if _manager is None:
        if emit_callback is None or socketio_start_task is None:
            raise RuntimeError("emit_callback and socketio_start_task required for first initialization")
        _manager = ClaudeManager(emit_callback, socketio_start_task)
    return _manager
