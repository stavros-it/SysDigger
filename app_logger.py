"""Centralized application logging.

Provides a configured logger that writes to ``app.log`` next to the script
directory. All modules import ``get_logger`` to obtain a named child
logger that inherits the file handler and formatting.

Usage:
    from app_logger import get_logger
    logger = get_logger(__name__)
    logger.info("message")
    logger.error("something failed", exc_info=True)

Log levels:
    DEBUG   - detailed diagnostic info (default in development)
    INFO    - normal operation milestones
    WARNING - unexpected but recoverable situations
    ERROR   - failures that degrade a feature
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

from paths import data_dir

_LOG_DIR = data_dir()
_LOG_PATH = os.path.join(_LOG_DIR, "app.log")
_MAX_LOG_SIZE = 2 * 1024 * 1024  # 2 MB
_MAX_LOG_BACKUPS = 3

_configured = False


def _configure() -> None:
    """Set up the root logger with a rotating file handler."""
    global _configured
    if _configured:
        return
    _configured = True

    from logging.handlers import RotatingFileHandler

    try:
        handler = RotatingFileHandler(
            _LOG_PATH,
            maxBytes=_MAX_LOG_SIZE,
            backupCount=_MAX_LOG_BACKUPS,
            encoding="utf-8",
        )
    except OSError:
        handler = logging.StreamHandler(sys.stderr)

    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a named child logger configured to write to app.log."""
    _configure()
    return logging.getLogger(name)


def log_startup() -> None:
    """Log a startup banner with Python version and platform info."""
    logger = get_logger("app")
    logger.info("=" * 60)
    logger.info("SysDigger starting")
    logger.info("Python %s", sys.version.replace("\n", " "))
    logger.info("Log file: %s", _LOG_PATH)
    logger.info("=" * 60)


def log_exception(logger: logging.Logger, context: str,
                  exc: Exception | None = None) -> None:
    """Log an exception with context.

    Args:
        logger: the logger to use
        context: description of what was being done
        exc: the exception (if None, uses sys.exc_info())
    """
    if exc is not None:
        logger.error("%s: %s: %s", context, type(exc).__name__, exc,
                     exc_info=True)
    else:
        logger.error("%s", context, exc_info=True)
