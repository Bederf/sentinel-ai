"""Logging configuration for SENTINEL backend.

Configures structured JSON file handlers for Promtail/Loki ingestion:
- sentinel.audit    → /var/log/sentinel/security.log (security events)
- sentinel.decisions → /var/log/sentinel/decisions.log (pipeline events)

Falls back gracefully if /var/log/sentinel/ is not writable (e.g., local dev).
"""

import logging
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
        max_bytes=5 * 1024 * 1024,  # 5 MB  ← dev-appropriate cap
        backup_count=3,  # 3 backups = 15 MB total per logger
    )

    # sentinel.decisions → decisions.log
    _setup_file_handler(
        logger_name="sentinel.decisions",
        filename=log_dir / "decisions.log",
        max_bytes=5 * 1024 * 1024,  # 5 MB  ← dev-appropriate cap
        backup_count=3,  # 3 backups = 15 MB total per logger
    )


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
