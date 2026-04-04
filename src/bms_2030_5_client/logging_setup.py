"""
Unified logging setup for BMS IEEE 2030.5 Client.

Configures:
- structlog for structured JSON logging (production) or colored console (debug)
- RotatingFileHandler for persistent log files
- stdlib logging bridge so all libraries route through structlog
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog


def setup_logging(
    *,
    level: str = "INFO",
    log_file: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    debug: bool = False,
) -> None:
    """
    Configure logging for the entire application.

    Args:
        level: Root log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Path to log file. None disables file logging.
        max_bytes: Maximum size per log file before rotation.
        backup_count: Number of rotated log files to keep.
        debug: If True, use colored console output instead of JSON.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # ── stdlib handlers ──────────────────────────────────────────────
    handlers: list[logging.Handler] = []

    # 1. Console (stdout)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(log_level)
    handlers.append(console)

    # 2. Rotating file handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        handlers.append(file_handler)

    # ── Reset root logger ────────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(log_level)
    # Remove existing handlers to prevent duplicates on reload
    for h in root.handlers[:]:
        root.removeHandler(h)
    for h in handlers:
        root.addHandler(h)

    # ── structlog configuration ──────────────────────────────────────
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.stdlib.ExtraAdder(),
    ]

    if debug:
        # Colored, human-readable console output for development
        renderer = structlog.dev.ConsoleRenderer()
    else:
        # Machine-parseable JSON for production / log aggregation
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Use structlog formatter on all stdlib handlers so both
    # structlog loggers and plain `logging.getLogger()` produce
    # the same structured output.
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    for h in handlers:
        h.setFormatter(formatter)
