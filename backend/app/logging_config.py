"""Logging configuration for SENTINEL backend.

Configures structured JSON file handlers for Promtail/Loki ingestion:
- sentinel.audit    → /var/log/sentinel/security.log (security events)
- sentinel.decisions → /var/log/sentinel/decisions.log (pipeline events)
- Root logger → StreamHandler at configurable LOG_LEVEL (default: INFO)

Falls back gracefully if /var/log/sentinel/ is not writable (e.g., local dev).
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path("/var/log/sentinel")
FALLBACK_LOG_DIR = Path(__file__).parent / "data" / "logs"


def setup_logging() -> None:
    """Configure structured logging for SENTINEL.

    Sets up file handlers for Promtail ingestion. If the production
    log directory (/var/log/sentinel/) isn't writable, falls back to
    backend/app/data/logs/ for local development.
    """
    log_dir = _get_writable_log_dir()
    if not log_dir:
        logging.getLogger(__name__).warning("No writable log directory found, structured loggers will use stderr only")
        return

    # sentinel.audit → security.log
    _setup_file_handler(
        logger_name="sentinel.audit",
        filename=log_dir / "security.log",
        max_bytes=5 * 1024 * 1024,
        backup_count=3,
    )

    # sentinel.decisions → decisions.log
    _setup_file_handler(
        logger_name="sentinel.decisions",
        filename=log_dir / "decisions.log",
        max_bytes=5 * 1024 * 1024,
        backup_count=3,
    )

    # Root logger — configurable level, streams to stdout
    root_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    _handler = logging.StreamHandler()
    _handler.setLevel(getattr(logging, root_log_level, logging.INFO))
    _handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    root_logger = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        root_logger.addHandler(_handler)
    root_logger.setLevel(getattr(logging, root_log_level, logging.INFO))
    logging.getLogger(__name__).info("Root logger configured at %s via StreamHandler", root_log_level)


def _get_writable_log_dir() -> Path | None:
    """Find a writable log directory, preferring production path."""
    for candidate in [LOG_DIR, FALLBACK_LOG_DIR]:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            # Test write access
            test_file = candidate / ".write_test"
            test_file.touch()
            test_file.unlink()
            return candidate
        except (OSError, PermissionError):
            continue
    return None


def _setup_file_handler(
    logger_name: str,
    filename: Path,
    max_bytes: int,
    backup_count: int,
) -> None:
    """Add a rotating file handler to a named logger."""
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)

    handler = RotatingFileHandler(
        filename=str(filename),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)

    # JSON lines format — no extra formatting, the message IS the JSON
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    logging.getLogger(__name__).info(f"Configured {logger_name} → {filename}")
