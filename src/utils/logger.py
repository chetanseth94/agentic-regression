"""Logging configuration and utilities."""

import logging
import sys
from typing import Optional

from ..config import get_settings


def setup_logger(name: str = "triage", level: Optional[str] = None) -> logging.Logger:
    """
    Set up and configure logger.

    Args:
        name: Logger name
        level: Log level (defaults to settings.LOG_LEVEL)

    Returns:
        Configured logger instance
    """
    settings = get_settings()
    log_level = level or settings.log_level

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    # We install handlers only on the base logger. Child loggers should propagate to it.
    logger.propagate = False if name == "triage" else True

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    return logger


def get_logger(name: str = "triage") -> logging.Logger:
    """Get or create a logger instance."""
    base = setup_logger("triage")
    logger = logging.getLogger(name)
    logger.setLevel(base.level)
    if name != "triage":
        # Ensure child loggers propagate to the base handler and don't attach their own.
        logger.propagate = True
    return logger
