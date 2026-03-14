"""
Tests for contradiction detection (Phase 156-02).

Pure logic tests -- no DB required.
"""

from __future__ import annotations

import pytest

from app.services.correlation.contradiction_detector import (
    CONTRADICTION_PENALTY,
    ContradictionResult,
    apply_contradiction_penalty,
    detect_contradiction,
)

# ============================================================================
# 1. Signal type pair contradictions
# ============================================================================


class TestSignalTypeContradictions:
    def test_resolution_vs_complaint(self):
        result = detect_contradiction("resolution_email", "complaint_email")
        assert result.is_contradiction is True
        assert result.rule == "resolution_contradicts_complaint"
        assert result.penalty == -0.20

    def test_complaint_vs_resolution_bidirectional(self):
        result = detect_contradiction("complaint_email", "resolution_email")
        assert result.is_contradiction is True
        assert result.rule == "resolution_contradicts_complaint"

    def test_occupancy_normal_vs_anomaly(self):
        result = detect_contradiction("occupancy_normal", "occupancy_anomaly")
        assert result.is_contradiction is True
        assert result.rule == "occupancy_normal_contradicts_anomaly"

    def test_booking_released_vs_conflict(self):
        result = detect_contradiction("booking_released", "booking_conflict")
        assert result.is_contradiction is True
        assert result.rule == "booking_released_contradicts_conflict"

    def test_same_type_no_contradiction(self):
        result = detect_contradiction("complaint_email", "complaint_email")
        assert result.is_contradiction is False
        assert result.rule is None
        assert result.penalty == 0.0

    def test_complaint_vs_escalation_no_contradiction(self):
        result = detect_contradiction("complaint_email", "escalation_email")
        assert result.is_contradiction is False

    def test_explanation_present_on_contradiction(self):
        result = detect_contradiction("resolution_email", "complaint_email")
        assert "resolution_email" in result.explanation
        assert "complaint_email" in result.explanation

    def test_explanation_present_on_no_contradiction(self):
        result = detect_contradiction("complaint_email", "complaint_email")
        assert result.explanation == "No contradiction detected"


# ============================================================================
# 2. Resolved cluster contradictions
# ============================================================================


class TestResolvedClusterContradictions:
    def test_resolved_cluster_new_complaint(self):
        result = detect_contradiction("complaint_email", "observation_email", cluster_state="resolved")
        assert result.is_contradiction is True
        assert result.rule == "resolved_contradicts_active"

    def test_resolved_cluster_new_escalation(self):
        result = detect_contradiction("observation_email", "escalation_email", cluster_state="resolved")
        assert result.is_contradiction is True
        assert result.rule == "resolved_contradicts_active"

    def test_resolved_cluster_new_action_request(self):
        result = detect_contradiction("action_request_email", "intake_email", cluster_state="resolved")
        assert result.is_contradiction is True
        assert result.rule == "resolved_contradicts_active"

    def test_resolved_cluster_observation_no_contradiction(self):
        """observation_email is NOT in ACTIVE_SIGNAL_TYPES."""
        result = detect_contradiction("observation_email", "intake_email", cluster_state="resolved")
        assert result.is_contradiction is False

    def test_active_cluster_complaint_no_contradiction(self):
        """Only resolved clusters trigger this rule."""
        result = detect_contradiction("complaint_email", "observation_email", cluster_state="active")
        assert result.is_contradiction is False

    def test_no_cluster_state_no_contradiction(self):
        result = detect_contradiction("complaint_email", "observation_email", cluster_state=None)
        assert result.is_contradiction is False


# ============================================================================
# 3. Penalty application
# ============================================================================


class TestApplyContradictionPenalty:
    def test_penalty_applied(self):
        contradiction = ContradictionResult(
            is_contradiction=True,
            rule="resolution_contradicts_complaint",
            penalty=-0.20,
            explanation="test",
        )
        assert apply_contradiction_penalty(0.80, contradiction) == pytest.approx(0.60)

    def test_penalty_clamped_to_zero(self):
        contradiction = ContradictionResult(
            is_contradiction=True,
            rule="resolution_contradicts_complaint",
            penalty=-0.20,
            explanation="test",
        )
        assert apply_contradiction_penalty(0.15, contradiction) == 0.0

    def test_no_contradiction_score_unchanged(self):
        no_contradiction = ContradictionResult(
            is_contradiction=False,
            rule=None,
            penalty=0.0,
            explanation="No contradiction detected",
        )
        assert apply_contradiction_penalty(0.80, no_contradiction) == 0.80

    def test_penalty_constant(self):
        assert CONTRADICTION_PENALTY == -0.20
