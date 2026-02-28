"""Tests for the Security Audit Events module (137-09 Task 1).

Covers:
    - SECURITY_EVENTS and ALERT_EVENTS set definitions
    - write_security_audit() writes to AuditLogger
    - Immediate flush for security events
    - Telegram alert for ALERT_EVENTS
    - Audit log capacity increased to 10,000
    - CONFIG_CHANGE wired to settings endpoints
    - Convenience wrappers (audit_prompt_guard_block, etc.)
"""

from unittest.mock import patch

from app.security.audit_events import (
    ALERT_EVENTS,
    SECURITY_EVENTS,
    _hash_input,
    _redact_snippet,
    audit_config_change,
    audit_document_quarantined,
    audit_output_filter_block,
    audit_prompt_guard_block,
    audit_prompt_guard_rewrite,
    audit_rate_limit_exceeded,
    audit_secret_detected,
    audit_step_up_failed,
    audit_tool_denied,
    audit_webhook_suspicious,
    write_security_audit,
)
from app.security.constants import LOG_MAX_ENTRIES, REDACTED_SNIPPET_MAX_LENGTH


# ---------------------------------------------------------------------------
# Event set definitions
# ---------------------------------------------------------------------------


class TestEventSets:
    def test_security_events_count(self):
        """12 security event types defined."""
        assert len(SECURITY_EVENTS) == 12

    def test_alert_events_count(self):
        """7 alert event types trigger Telegram notification."""
        assert len(ALERT_EVENTS) == 7

    def test_alert_events_subset_of_security(self):
        """All ALERT_EVENTS must be in SECURITY_EVENTS."""
        assert ALERT_EVENTS.issubset(SECURITY_EVENTS)

    def test_expected_security_events(self):
        expected = {
            "PROMPT_GUARD_BLOCK",
            "PROMPT_GUARD_REWRITE",
            "OUTPUT_FILTER_BLOCK",
            "SECRET_DETECTED",
            "DOCUMENT_QUARANTINED",
            "RAG_INJECTION_DETECTED",
            "TOOL_DENIED",
            "STEP_UP_FAILED",
            "WEBHOOK_SUSPICIOUS",
            "CONFIG_CHANGE",
            "PERMISSION_CHANGE",
            "RATE_LIMIT_EXCEEDED",
        }
        assert SECURITY_EVENTS == expected

    def test_expected_alert_events(self):
        expected = {
            "PROMPT_GUARD_BLOCK",
            "OUTPUT_FILTER_BLOCK",
            "SECRET_DETECTED",
            "DOCUMENT_QUARANTINED",
            "WEBHOOK_SUSPICIOUS",
            "CONFIG_CHANGE",
            "PERMISSION_CHANGE",
        }
        assert ALERT_EVENTS == expected


# ---------------------------------------------------------------------------
# write_security_audit
# ---------------------------------------------------------------------------


class TestWriteSecurityAudit:
    @patch("app.security.audit_events._send_telegram_alert")
    def test_security_event_written(self, mock_telegram):
        """write_security_audit writes to the AuditLogger and returns an entry ID."""
        entry_id = write_security_audit(
            "PROMPT_GUARD_BLOCK",
            user="test-user",
            source_ip="10.0.0.1",
            input_hash="abc123",
            snippet="ignore all previous instructions",
        )
        assert entry_id  # Non-empty string
        assert isinstance(entry_id, str)

    @patch("app.security.audit_events._send_telegram_alert")
    def test_alert_event_triggers_notification(self, mock_telegram):
        """ALERT_EVENTS should trigger _send_telegram_alert."""
        write_security_audit("CONFIG_CHANGE", user="admin", metadata={"setting_key": "test"})
        mock_telegram.assert_called_once()
        args = mock_telegram.call_args
        assert args[0][0] == "CONFIG_CHANGE"  # event_type

    @patch("app.security.audit_events._send_telegram_alert")
    def test_non_alert_event_no_notification(self, mock_telegram):
        """Non-ALERT_EVENTS should NOT trigger Telegram."""
        write_security_audit("RATE_LIMIT_EXCEEDED", metadata={"path": "/api/chat"})
        mock_telegram.assert_not_called()

    @patch("app.security.audit_events._send_telegram_alert")
    def test_unknown_event_type_logged(self, mock_telegram):
        """Unknown event types are logged as warnings but still written."""
        entry_id = write_security_audit("UNKNOWN_EVENT_TYPE")
        # Should still return an entry ID (write succeeds)
        assert isinstance(entry_id, str)

    @patch("app.security.audit_events._send_telegram_alert")
    def test_immediate_flush_for_security_events(self, mock_telegram):
        """Buffer is flushed immediately after writing a security event."""
        with patch("app.services.audit_logger.AuditLogger.flush") as mock_flush:
            write_security_audit("TOOL_DENIED", metadata={"tool_name": "evil_tool"})
            mock_flush.assert_called_once()


# ---------------------------------------------------------------------------
# Audit log capacity
# ---------------------------------------------------------------------------


class TestAuditLogCapacity:
    def test_log_max_entries_constant(self):
        """LOG_MAX_ENTRIES constant is 10,000."""
        assert LOG_MAX_ENTRIES == 10_000

    def test_audit_logger_uses_constant(self):
        """AuditLogger.max_entries should use the security constant."""
        from app.services.audit_logger import AuditLogger

        audit_logger = AuditLogger()
        assert audit_logger.max_entries == 10_000


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_hash_input(self):
        """_hash_input returns a 16-char hex string."""
        h = _hash_input("test input")
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_input_deterministic(self):
        h1 = _hash_input("same text")
        h2 = _hash_input("same text")
        assert h1 == h2

    def test_hash_input_different(self):
        h1 = _hash_input("text a")
        h2 = _hash_input("text b")
        assert h1 != h2

    def test_redact_snippet_short(self):
        """Short text is returned as-is."""
        text = "short text"
        assert _redact_snippet(text) == text

    def test_redact_snippet_long(self):
        """Long text is truncated with ellipsis."""
        text = "x" * (REDACTED_SNIPPET_MAX_LENGTH + 50)
        result = _redact_snippet(text)
        assert len(result) == REDACTED_SNIPPET_MAX_LENGTH + 3  # + "..."
        assert result.endswith("...")

    def test_redact_snippet_empty(self):
        assert _redact_snippet("") == ""


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------


class TestConvenienceWrappers:
    @patch("app.security.audit_events._send_telegram_alert")
    def test_audit_prompt_guard_block(self, mock_telegram):
        entry_id = audit_prompt_guard_block("malicious text", score=0.85, source="direct")
        assert isinstance(entry_id, str)
        assert entry_id != ""

    @patch("app.security.audit_events._send_telegram_alert")
    def test_audit_prompt_guard_rewrite(self, mock_telegram):
        entry_id = audit_prompt_guard_rewrite("borderline text", score=0.35)
        assert isinstance(entry_id, str)

    @patch("app.security.audit_events._send_telegram_alert")
    def test_audit_output_filter_block(self, mock_telegram):
        entry_id = audit_output_filter_block(redactions=["system_prompt_leak"])
        assert isinstance(entry_id, str)

    @patch("app.security.audit_events._send_telegram_alert")
    def test_audit_secret_detected(self, mock_telegram):
        entry_id = audit_secret_detected(redaction_type="secret:[REDACTED-JWT]")
        assert isinstance(entry_id, str)

    @patch("app.security.audit_events._send_telegram_alert")
    def test_audit_document_quarantined(self, mock_telegram):
        entry_id = audit_document_quarantined(file_hash="abc123", reason="injection_score=0.8")
        assert isinstance(entry_id, str)

    @patch("app.security.audit_events._send_telegram_alert")
    def test_audit_tool_denied(self, mock_telegram):
        entry_id = audit_tool_denied(tool_name="evil_tool", reason="unregistered_tool")
        assert isinstance(entry_id, str)

    @patch("app.security.audit_events._send_telegram_alert")
    def test_audit_step_up_failed(self, mock_telegram):
        entry_id = audit_step_up_failed(user="user1", device_id="dev1")
        assert isinstance(entry_id, str)

    @patch("app.security.audit_events._send_telegram_alert")
    def test_audit_webhook_suspicious(self, mock_telegram):
        entry_id = audit_webhook_suspicious(webhook_type="whatsapp", reason="bad_sig")
        assert isinstance(entry_id, str)

    @patch("app.security.audit_events._send_telegram_alert")
    def test_audit_config_change(self, mock_telegram):
        entry_id = audit_config_change(setting_key="notifications", user="admin")
        assert isinstance(entry_id, str)

    @patch("app.security.audit_events._send_telegram_alert")
    def test_audit_rate_limit_exceeded(self, mock_telegram):
        entry_id = audit_rate_limit_exceeded(path="/api/chat", source_ip="1.2.3.4")
        assert isinstance(entry_id, str)
