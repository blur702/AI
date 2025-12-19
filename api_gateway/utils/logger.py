"""
Logging configuration for API Gateway.

Provides a centralized logging factory that creates loggers with consistent
formatting, file rotation, and console output. Uses log level from settings.

Features:
    - Rotating file handler (5MB max, 3 backups)
    - Console output with timestamp formatting
    - Configurable log level via LOG_LEVEL setting
    - Safe rotation handling for multi-process environments (Windows)
    - Configurable log file path via LOG_FILE setting or environment variable

Environment Variables:
    LOG_SKIP_FILE_HANDLER: Set to "1", "true", or "yes" to skip file logging
    LOG_FILE: Override the log file path

Usage:
    from api_gateway.utils.logger import get_logger
    logger = get_logger("api_gateway.mymodule")
    logger.info("Message")
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ..config import settings


class SafeRotatingFileHandler(RotatingFileHandler):
    """
    A RotatingFileHandler that handles file locking errors gracefully.

    On Windows with multiple processes writing to the same log file,
    rotation can fail with PermissionError when another process has
    the file open. This handler catches such errors and continues
    logging to the current file without rotating.

    After catching rotation errors, ensures the stream is reopened so
    logging can continue.
    """

    def doRollover(self) -> None:
        """Perform rollover, handling Windows file locking errors."""
        try:
            super().doRollover()
        except PermissionError:
            # Another process has the file locked - skip rotation
            # Ensure we still have a usable stream to continue logging
            self._reopen_stream_if_needed()
        except OSError as e:
            # Handle Windows ERROR_SHARING_VIOLATION (errno 32)
            if e.errno == 32:
                self._reopen_stream_if_needed()
            else:
                raise

    def _reopen_stream_if_needed(self) -> None:
        """Reopen the stream if it was closed during a failed rotation."""
        try:
            if self.stream is None or self.stream.closed:
                self.stream = self._open()
        except Exception:
            # If reopening fails, let it propagate so failure is visible
            raise


def _should_skip_file_handler() -> bool:
    """
    Determine if file handler should be skipped.

    Checks for explicit opt-out via environment variable first, then
    falls back to heuristic detection of worker subprocesses.

    Environment Variables:
        LOG_SKIP_FILE_HANDLER: Set to "1", "true", or "yes" to skip file logging

    Returns:
        True if file handler should be skipped, False otherwise.
    """
    # Check for explicit opt-out via environment variable
    skip_env = os.environ.get("LOG_SKIP_FILE_HANDLER", "").lower()
    if skip_env in ("1", "true", "yes"):
        return True

    # Heuristic: detect worker subprocesses with redirected stdout
    # Workers spawned by supervisors have stdout redirected to per-worker logs
    try:
        if not sys.stdout.isatty():
            # Check for worker environment indicators
            if os.environ.get("WORKER_ID") or "--worker-id" in sys.argv:
                return True
    except (AttributeError, ValueError):
        pass

    return False


def _get_log_file_path() -> Path:
    """
    Get the log file path from configuration or environment.

    Priority:
        1. LOG_FILE environment variable
        2. settings.LOG_FILE if defined
        3. Default: api_gateway.log in project root

    Returns:
        Path to the log file.
    """
    # Check environment variable first
    log_file_env = os.environ.get("LOG_FILE")
    if log_file_env:
        return Path(log_file_env).expanduser()

    # Check settings
    log_file_setting = getattr(settings, "LOG_FILE", None)
    if log_file_setting:
        return Path(log_file_setting).expanduser()

    # Default: project root (where this module is typically run from)
    # Use absolute path for clarity
    return Path(__file__).parent.parent.parent / "api_gateway.log"


def get_logger(name: str) -> logging.Logger:
    """
    Get or create a logger with standard configuration.

    Creates a logger with rotating file handler and console handler if not
    already configured. Uses LOG_LEVEL from settings.

    File handler is skipped if:
        - LOG_SKIP_FILE_HANDLER env var is set to "1", "true", or "yes"
        - Running as a worker subprocess with redirected stdout

    Args:
        name: Logger name (typically module path like "api_gateway.services.foo")

    Returns:
        Configured Logger instance
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # Console handler - always added
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler - skip if explicitly disabled or running as worker
    if not _should_skip_file_handler():
        log_path = _get_log_file_path()
        # Ensure parent directory exists
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = SafeRotatingFileHandler(
            str(log_path), maxBytes=5 * 1024 * 1024, backupCount=3
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


logger = get_logger("api_gateway")

