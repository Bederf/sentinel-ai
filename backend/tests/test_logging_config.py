"""Tests for structured logging configuration."""

import logging
from pathlib import Path
from unittest.mock import patch

from app.logging_config import _get_writable_log_dir, setup_logging


class TestGetWritableLogDir:
    """_get_writable_log_dir finds a writable directory."""

    def test_returns_path_when_writable(self, tmp_path):
        with patch("app.logging_config.LOG_DIR", tmp_path / "sentinel"):
            result = _get_writable_log_dir()
            assert result is not None
            assert result.exists()

    def test_falls_back_when_primary_not_writable(self, tmp_path):
        with (
            patch("app.logging_config.LOG_DIR", Path("/nonexistent/path")),
            patch("app.logging_config.FALLBACK_LOG_DIR", tmp_path / "fallback"),
        ):
            result = _get_writable_log_dir()
            assert result is not None
            assert "fallback" in str(result)


class TestSetupLogging:
    """setup_logging configures file handlers for structured loggers."""

    def test_creates_file_handlers(self, tmp_path):
        with (
            patch("app.logging_config.LOG_DIR", tmp_path / "sentinel"),
            patch("app.logging_config.FALLBACK_LOG_DIR", tmp_path / "fallback"),
        ):
            setup_logging()

            audit_logger = logging.getLogger("sentinel.audit")
            decisions_logger = logging.getLogger("sentinel.decisions")

            # Should have at least one file handler each
            file_handlers = [h for h in audit_logger.handlers if hasattr(h, "baseFilename")]
            assert len(file_handlers) >= 1

            file_handlers = [h for h in decisions_logger.handlers if hasattr(h, "baseFilename")]
            assert len(file_handlers) >= 1

        # Cleanup: remove handlers to avoid test pollution
        for logger_name in ["sentinel.audit", "sentinel.decisions"]:
            logger = logging.getLogger(logger_name)
            for handler in logger.handlers[:]:
                handler.close()
                logger.removeHandler(handler)

    def test_graceful_when_no_writable_dir(self):
        with (
            patch("app.logging_config.LOG_DIR", Path("/nonexistent/1")),
            patch("app.logging_config.FALLBACK_LOG_DIR", Path("/nonexistent/2")),
        ):
            # Should not raise
            setup_logging()
