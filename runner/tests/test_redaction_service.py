"""Tests for RedactionService — POPIA SA-specific PII redaction."""

from __future__ import annotations

import pytest

from app.services.redaction_service import RedactionService


@pytest.fixture
def svc() -> RedactionService:
    return RedactionService()


# ---------------------------------------------------------------------------
# Individual pattern tests
# ---------------------------------------------------------------------------

def test_sa_id_redacted(svc: RedactionService):
    """SA 13-digit ID number is redacted."""
    # 8501015009088 is a valid SA ID (Luhn-valid: YY=85, MM=01, DD=01, checksum=8)
    text = "Occupant ID 8501015009088 was present"
    result = svc.redact(text)
    assert "8501015009088" not in result
    assert "[REDACTED-ID-001]" in result


def test_sa_phone_redacted(svc: RedactionService):
    """+27 and 0XX formats are both redacted."""
    text = "Call +27 72 123 4567 or 072 123 4567 for support"
    result = svc.redact(text)
    assert "+27 72 123 4567" not in result
    assert "072 123 4567" not in result
    assert "[REDACTED-PHONE-" in result


def test_email_redacted(svc: RedactionService):
    """Email addresses are redacted."""
    text = "Contact john@example.com for details"
    result = svc.redact(text)
    assert "john@example.com" not in result
    assert "[REDACTED-EMAIL-001]" in result


def test_credit_card_redacted(svc: RedactionService):
    """Credit card numbers (Luhn-valid) are redacted."""
    # 4111 1111 1111 1111 is a well-known Luhn-valid test card number
    text = "Payment on card 4111 1111 1111 1111"
    result = svc.redact(text)
    assert "4111 1111 1111 1111" not in result
    assert "[REDACTED-CC-001]" in result


def test_result_deep_redaction(svc: RedactionService):
    """Full ResultSchema dict with PII in summary/findings — verify redacted."""
    result_dict = {
        "status": "complete",
        "summary": "Technician john@example.com reported an issue at +27 72 123 4567",
        "findings": [
            "Found ID 8501015009088 in access log",
            "Electrical fault detected in zone 101",
        ],
        "anomalies": [
            {"description": "Occupant with email john@example.com entered after hours", "severity": "high"},
        ],
        "timeline": [
            {"description": "Called +27 72 123 4567 at 14:00", "time": "14:00"},
        ],
        "recommended_actions": [
            "Contact john@example.com to verify access",
        ],
        "confidence": 0.85,
        "needs_deeper_run": False,
        "trajectory": {"steps": 2, "files_read": 3, "bytes_read": 1024, "elapsed_s": 5.2},
    }

    redacted = svc.redact_result(result_dict)

    # PII-bearing fields should be redacted
    assert "john@example.com" not in redacted["summary"]
    assert "+27 72 123 4567" not in redacted["summary"]
    assert "8501015009088" not in redacted["findings"][0]
    assert "john@example.com" not in redacted["anomalies"][0]["description"]
    assert "+27 72 123 4567" not in redacted["timeline"][0]["description"]
    assert "john@example.com" not in redacted["recommended_actions"][0]

    # Non-PII findings should be untouched
    assert "Electrical fault detected in zone 101" == redacted["findings"][1]


def test_metadata_not_redacted(svc: RedactionService):
    """confidence, trajectory, status, needs_deeper_run are untouched."""
    result_dict = {
        "status": "complete",
        "summary": "No PII here",
        "findings": [],
        "anomalies": [],
        "timeline": [],
        "recommended_actions": [],
        "confidence": 0.92,
        "needs_deeper_run": True,
        "trajectory": {"steps": 3, "files_read": 5, "bytes_read": 2048, "elapsed_s": 12.5},
    }

    redacted = svc.redact_result(result_dict)

    assert redacted["status"] == "complete"
    assert redacted["confidence"] == 0.92
    assert redacted["needs_deeper_run"] is True
    assert redacted["trajectory"]["steps"] == 3
    assert redacted["trajectory"]["elapsed_s"] == 12.5
