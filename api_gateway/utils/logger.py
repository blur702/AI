import logging
from logging.handlers import RotatingFileHandler

from ..config import settings


def get_logger(name: str) -> logging.Logger:
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

