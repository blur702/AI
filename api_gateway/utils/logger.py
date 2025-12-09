"""
Logging configuration for API Gateway.

Provides a centralized logging factory that creates loggers with consistent
formatting, file rotation, and console output. Uses log level from settings.

Features:
    - Rotating file handler (5MB max, 3 backups)
    - Console output with timestamp formatting
    - Configurable log level via LOG_LEVEL setting

Usage:
    from api_gateway.utils.logger import get_logger
    logger = get_logger("api_gateway.mymodule")
    logger.info("Message")
"""
import logging
from logging.handlers import RotatingFileHandler

from ..config import settings


def get_logger(name: str) -> logging.Logger:
    """
    Get or create a logger with standard configuration.

    Creates a logger with rotating file handler and console handler if not
    already configured. Uses LOG_LEVEL from settings.

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

    file_handler = RotatingFileHandler(
        "api_gateway.log", maxBytes=5 * 1024 * 1024, backupCount=3
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.propagate = False
    return logger


logger = get_logger("api_gateway")

