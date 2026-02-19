"""Tests for structured decision event logger.

Verifies that emit_decision_event() produces correct JSON-structured
log lines compatible with Promtail/Loki ingestion.
"""

import json
import logging

import pytest

from app.services.decision_event_logger import emit_decision_event


class TestEmitDecisionEvent:
    """emit_decision_event produces structured JSON log lines."""

    def test_emits_json_with_all_fields(self, caplog):
        with caplog.at_level(logging.INFO, logger="sentinel.decisions"):
            emit_decision_event(
                "tier_routing.decided",
                correlation_id="corr-123",
                decision_id="dec-456",
                recommendation_id="rec-789",
                equipment_code="S002-CHILLER-B1-001",
                site_id="S002",
                tier="tier3",
                status="auto_execute",
                details={"confidence_score": 0.92},
            )

        assert len(caplog.records) == 1
        event = json.loads(caplog.records[0].message)
        assert event["stage"] == "tier_routing.decided"
        assert event["correlation_id"] == "corr-123"
        assert event["decision_id"] == "dec-456"
        assert event["recommendation_id"] == "rec-789"
        assert event["equipment_code"] == "S002-CHILLER-B1-001"
        assert event["site_id"] == "S002"
        assert event["tier"] == "tier3"
        assert event["status"] == "auto_execute"
        assert event["details"]["confidence_score"] == 0.92
        assert event["component"] == "sentinel-parasite"
        assert "timestamp" in event

    def test_failed_status_uses_warning_level(self, caplog):
        with caplog.at_level(logging.WARNING, logger="sentinel.decisions"):
            emit_decision_event(
                "safety.validated",
                status="failed",
                details={"reason": "Temperature out of range"},
            )

        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.WARNING

    def test_success_status_uses_info_level(self, caplog):
        with caplog.at_level(logging.INFO, logger="sentinel.decisions"):
            emit_decision_event(
                "device.write",
                status="success",
            )

        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.INFO

    def test_defaults_empty_strings(self, caplog):
        with caplog.at_level(logging.INFO, logger="sentinel.decisions"):
            emit_decision_event("cov.verified", status="verified")

        event = json.loads(caplog.records[0].message)
        assert event["correlation_id"] == ""
        assert event["decision_id"] == ""
        assert event["recommendation_id"] == ""
        assert event["equipment_code"] == ""
        assert event["details"] == {}

    def test_handles_exception_gracefully(self, caplog):
        """If JSON serialization fails, should not raise."""
        with caplog.at_level(logging.ERROR):
            # Pass a non-serializable object
            emit_decision_event(
                "test.stage",
                details={"bad": object()},
            )
        # Should not raise, and should log error via fallback logger


class TestLifecycleEventStages:
    """All pipeline stages emit events with correct stage names."""

    EXPECTED_STAGES = [
        "tier_routing.decided",
        "safety.validated",
        "device.write",
        "cov.verified",
        "rollback.executed",
        "pipeline.complete",
        "approval.decided",
        "outcome.scheduled",
        "outcome.measured",
        "feedback.recorded",
    ]

    @pytest.mark.parametrize("stage", EXPECTED_STAGES)
    def test_stage_emits_valid_json(self, stage, caplog):
        with caplog.at_level(logging.INFO, logger="sentinel.decisions"):
            emit_decision_event(stage, status="test")

        event = json.loads(caplog.records[0].message)
        assert event["stage"] == stage
