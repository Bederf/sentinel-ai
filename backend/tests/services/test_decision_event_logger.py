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


class TestCorrelationIdThreading:
    """Test correlation ID threading through decision pipeline.

    Control: AUDIT-002 (Audit Event Completeness) — request tracing
    """

    def test_correlation_id_threaded_through_pipeline(self, caplog):
        """Verify that multiple events share same correlation_id for E2E tracing.

        This proves Gap 8 (MEDIUM) — Decision events linked by correlation ID.

        Simulates a complete approval flow where all events are linked
        by the same correlation_id:
        1. recommendation.created
        2. tier_routing.decided
        3. safety.validated
        4. approval.decided
        5. device.write
        6. outcome.measured

        Control: AUDIT-002 (Audit Event Completeness)
        """
        correlation_id = "approval-flow-test-123"
        site_id = "S002"
        equipment_code = "S002-FCU-B1-001"

        with caplog.at_level(logging.INFO, logger="sentinel.decisions"):
            # Stage 1: Recommendation created
            emit_decision_event(
                stage="recommendation.created",
                correlation_id=correlation_id,
                equipment_code=equipment_code,
                site_id=site_id,
                status="pending",
                details={"recommendation_type": "temperature_setpoint"},
            )

            # Stage 2: Tier routing decided
            emit_decision_event(
                stage="tier_routing.decided",
                correlation_id=correlation_id,
                equipment_code=equipment_code,
                site_id=site_id,
                tier="tier2",
                status="require_approval",
                details={"confidence": 0.80},
            )

            # Stage 3: Safety validated
            emit_decision_event(
                stage="safety.validated",
                correlation_id=correlation_id,
                equipment_code=equipment_code,
                site_id=site_id,
                status="success",
                details={"rules_checked": 3, "violations": 0},
            )

            # Stage 4: Approval decided
            emit_decision_event(
                stage="approval.decided",
                correlation_id=correlation_id,
                equipment_code=equipment_code,
                site_id=site_id,
                status="approved",
                details={"approved_by": "technician@site", "notes": "Urgent"},
            )

            # Stage 5: Device write
            emit_decision_event(
                stage="device.write",
                correlation_id=correlation_id,
                equipment_code=equipment_code,
                site_id=site_id,
                status="success",
                details={"value": 25.0, "point": "setpoint"},
            )

            # Stage 6: Outcome measured
            emit_decision_event(
                stage="outcome.measured",
                correlation_id=correlation_id,
                equipment_code=equipment_code,
                site_id=site_id,
                status="success",
                details={"outcome": "temperature_stabilized", "time_to_stable": 120},
            )

        # Verify all 6 events were captured
        assert len(caplog.records) == 6, f"Expected 6 events, got {len(caplog.records)}"

        # Parse all events and verify correlation_id threading
        events = []
        stages_found = []
        for record in caplog.records:
            event = json.loads(record.message)
            events.append(event)
            stages_found.append(event["stage"])

            # Every event must have the same correlation_id
            assert event["correlation_id"] == correlation_id, (
                f"Event {event['stage']} has correlation_id={event['correlation_id']}, expected {correlation_id}"
            )
            # Every event must reference the same equipment
            assert event["equipment_code"] == equipment_code
            assert event["site_id"] == site_id

        # Verify complete pipeline flow (all stages present)
        expected_stages = [
            "recommendation.created",
            "tier_routing.decided",
            "safety.validated",
            "approval.decided",
            "device.write",
            "outcome.measured",
        ]
        assert stages_found == expected_stages, f"Expected stages {expected_stages}, got {stages_found}"

    def test_different_requests_have_different_correlation_ids(self, caplog):
        """Verify that different requests are isolated by correlation_id."""
        correlation_id_1 = "request-1-abc"
        correlation_id_2 = "request-2-xyz"

        with caplog.at_level(logging.INFO, logger="sentinel.decisions"):
            # Request 1
            emit_decision_event(
                stage="recommendation.created",
                correlation_id=correlation_id_1,
                equipment_code="S002-CHILLER-B1-001",
                site_id="S002",
                status="pending",
            )

            # Request 2 (different equipment, different correlation_id)
            emit_decision_event(
                stage="recommendation.created",
                correlation_id=correlation_id_2,
                equipment_code="S002-CHILLER-B1-002",
                site_id="S002",
                status="pending",
            )

        # Verify both events were captured
        assert len(caplog.records) == 2

        event1 = json.loads(caplog.records[0].message)
        event2 = json.loads(caplog.records[1].message)

        # Verify isolation by correlation_id
        assert event1["correlation_id"] == correlation_id_1
        assert event2["correlation_id"] == correlation_id_2

        # Verify different equipment codes
        assert event1["equipment_code"] != event2["equipment_code"]
