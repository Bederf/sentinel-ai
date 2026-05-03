"""
Call-Log ↔ ThesaurusService integration tests.

Covers all five complaint categories (TOO_HOT, TOO_COLD, STUFFY_AIR, LIGHTING,
OTHER) plus the no-match / escalation path.
"""

import os
import sys

# Make call_log_handler importable from the handlers sibling directory
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_SENTRY_ROOT = os.path.join(_TOOLS_DIR, "..")
_HANDLERS_DIR = os.path.join(_SENTRY_ROOT, "handlers")
_THESAURUS_DIR = os.path.join(_SENTRY_ROOT, "thesaurus")

for _p in (_HANDLERS_DIR, _THESAURUS_DIR, _SENTRY_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest
from call_log_handler import classify_issue, is_facilities_complaint


class TestCallLogThesaurusIntegration:
    """End-to-end: classify_issue() → ThesaurusService → structured result."""

    def test_too_hot_complaint(self):
        result = classify_issue("it's very hot in l2")
        assert result["is_facilities_issue"] is True
        assert result["category"] == "TOO_HOT"
        assert result["discipline"] == "HVAC"
        assert result["matched_phrase"] is not None
        assert result["priority"] == "high"

    def test_too_cold_complaint(self):
        result = classify_issue("freezing in the meeting room")
        assert result["is_facilities_issue"] is True
        assert result["category"] == "TOO_COLD"
        assert result["discipline"] == "HVAC"
        assert result["priority"] == "high"

    def test_stuffy_air_complaint(self):
        result = classify_issue("stale air, can't breathe")
        assert result["is_facilities_issue"] is True
        assert result["category"] == "STUFFY_AIR"
        assert result["discipline"] == "HVAC"
        assert result["specialty"] == "hvac"

    def test_lighting_complaint(self):
        result = classify_issue("lights flickering in the boardroom")
        assert result["is_facilities_issue"] is True
        assert result["category"] == "LIGHTING"
        assert result["discipline"] == "Lighting"
        assert result["priority"] == "medium"

    def test_other_complaint(self):
        result = classify_issue("door stuck in the bathroom")
        assert result["is_facilities_issue"] is True
        assert result["category"] == "OTHER"
        assert result["discipline"] == "General"
        assert result["priority"] == "low"

    def test_non_facilities_escalates(self):
        result = classify_issue("tell me a joke")
        assert result["is_facilities_issue"] is False
        assert result.get("escalate") is True
        assert "reason" in result

    def test_user_id_accepted_without_affecting_classification(self):
        """user_id parameter must not change the classification result."""
        without_id = classify_issue("too hot", user_id=None)
        with_id = classify_issue("too hot", user_id=9999888777)
        assert without_id["category"] == with_id["category"]
        assert without_id["discipline"] == with_id["discipline"]

    def test_is_facilities_complaint_bool(self):
        assert is_facilities_complaint("no airflow at my desk") is True
        assert is_facilities_complaint("what time is lunch") is False
