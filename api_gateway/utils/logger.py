"""
Logging configuration for API Gateway.

Provides a centralized logging factory that creates loggers with consistent
formatting, file rotation, and console output. Uses log level from settings.

Features:
    - Rotating file handler (5MB max, 3 backups)
    - Console output with timestamp formatting
    - Configurable log level via LOG_LEVEL setting
    - Safe rotation handling for multi-process environments (Windows)

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
    """

    def doRollover(self) -> None:
        """Perform rollover, handling Windows file locking errors."""
        try:
            super().doRollover()
        except PermissionError:
            # Another process has the file locked - skip rotation
            # The file will be rotated on the next attempt when unlocked
            pass
        except OSError as e:
            # Handle other OS errors (disk full, etc.) gracefully
            if e.errno == 32:  # Windows: file in use by another process
                pass
            else:
                raise


def _is_subprocess_with_redirected_output() -> bool:
    """
    Check if we're running in a subprocess with stdout redirected to a file.

    Workers spawned by the congressional supervisor have their stdout
    redirected to per-worker log files. In this case, we skip the shared
    file handler to avoid rotation conflicts.
    """
    try:
        # Check if stdout is redirected to a file (not a TTY or console)
        if not sys.stdout.isatty():
            # Check for common worker environment indicators
            if os.environ.get("WORKER_ID") or "--worker-id" in sys.argv:
                return True
    except (AttributeError, ValueError):
        pass
    return False


def get_logger(name: str) -> logging.Logger:
    """
    Get or create a logger with standard configuration.

    Creates a logger with rotating file handler and console handler if not
    already configured. Uses LOG_LEVEL from settings.

    For subprocess workers with redirected stdout (like congressional scrapers),
    skips the shared file handler to avoid rotation conflicts.

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

    # File handler - skip for workers with redirected stdout
    # (they log to per-worker files via stdout redirection)
    if not _is_subprocess_with_redirected_output():
        log_path = Path("D:/AI/api_gateway.log")
        file_handler = SafeRotatingFileHandler(
            str(log_path), maxBytes=5 * 1024 * 1024, backupCount=3
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


logger = get_logger("api_gateway")

