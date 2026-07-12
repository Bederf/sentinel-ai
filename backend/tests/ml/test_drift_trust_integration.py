"""Unit tests for drift→trust integration (Phase 240 M2.3).

Tests mapping drift verdicts to trust penalties, computing trust confidence,
and creating operator-visible findings.
"""

from app.ml.models.drift_trust_integration import (
    compute_drift_penalty_for_site,
    compute_trust_confidence,
    create_findings_from_drift,
    drift_verdict_to_penalty,
)


class TestDriftVerdictToPenalty:
    """Test drift verdict → penalty mapping."""

    def test_unevaluable_penalty(self):
        """UNEVALUABLE → -0.5 penalty (fail-closed)."""
        assert drift_verdict_to_penalty("UNEVALUABLE") == -0.5

    def test_feature_mismatch_penalty(self):
        """FEATURE_MISMATCH → -0.3 penalty (schema mismatch)."""
        assert drift_verdict_to_penalty("FEATURE_MISMATCH") == -0.3

    def test_drift_detected_penalty(self):
        """DRIFT_DETECTED → -0.2 penalty (model degrading)."""
        assert drift_verdict_to_penalty("DRIFT_DETECTED") == -0.2

    def test_no_drift_detected_boost(self):
        """NO_DRIFT_DETECTED → +0.05 confidence boost."""
        assert drift_verdict_to_penalty("NO_DRIFT_DETECTED") == 0.05

    def test_insufficient_data_penalty(self):
        """INSUFFICIENT_DATA → -0.5 penalty (fail-closed)."""
        assert drift_verdict_to_penalty("INSUFFICIENT_DATA") == -0.5

    def test_unknown_verdict_default(self):
        """Unknown verdict → -0.5 default (fail-closed)."""
        assert drift_verdict_to_penalty("UNKNOWN_VERDICT") == -0.5

    def test_case_insensitive(self):
        """Verdicts are case-insensitive."""
        assert drift_verdict_to_penalty("drift_detected") == -0.2
        assert drift_verdict_to_penalty("Drift_Detected") == -0.2
        assert drift_verdict_to_penalty("no_drift_detected") == 0.05


class TestComputeDriftPenaltyForSite:
    """Test max penalty computation across equipment."""

    def test_empty_verdicts(self):
        """No equipment verdicts → 0.0 penalty."""
        assert compute_drift_penalty_for_site("site-002", {}) == 0.0

    def test_single_equipment_no_drift(self):
        """Single equipment, no drift → +0.05 penalty."""
        verdicts = {"chiller": "NO_DRIFT_DETECTED"}
        assert compute_drift_penalty_for_site("site-002", verdicts) == 0.05

    def test_single_equipment_drift_detected(self):
        """Single equipment, drift detected → -0.2 penalty."""
        verdicts = {"chiller": "DRIFT_DETECTED"}
        assert compute_drift_penalty_for_site("site-002", verdicts) == -0.2

    def test_multiple_equipment_max_penalty(self):
        """Multiple equipment: return worst (most negative) penalty."""
        verdicts = {
            "chiller": "NO_DRIFT_DETECTED",  # +0.05
            "ahu": "DRIFT_DETECTED",  # -0.2
            "fcu": "UNEVALUABLE",  # -0.5
        }
        # Max of [0.05, -0.2, -0.5] = 0.05 (worst is most negative)
        assert compute_drift_penalty_for_site("site-002", verdicts) == 0.05

    def test_all_equipment_drift_worst_penalty(self):
        """All equipment have worst penalty."""
        verdicts = {
            "chiller": "UNEVALUABLE",
            "ahu": "UNEVALUABLE",
            "fcu": "UNEVALUABLE",
        }
        assert compute_drift_penalty_for_site("site-002", verdicts) == -0.5


class TestComputeTrustConfidence:
    """Test trust confidence formula."""

    def test_full_trust_no_drift(self):
        """base_trust=1.0, drift_penalty=0.0 → confidence=1.0."""
        confidence = compute_trust_confidence(1.0, 0.0)
        assert confidence == 1.0

    def test_full_gates_drift_detected(self):
        """base_trust=1.0 (all gates pass), drift_detected (-0.2) → 0.8."""
        # 1.0 * (1.0 - (-0.2)) = 1.0 * 1.2 = 1.2 → clamped to 1.0
        confidence = compute_trust_confidence(1.0, -0.2)
        assert confidence == 1.0

    def test_three_quarters_trust_no_drift(self):
        """base_trust=0.75, drift_penalty=0.0 → confidence=0.75."""
        confidence = compute_trust_confidence(0.75, 0.0)
        assert confidence == 0.75

    def test_three_quarters_trust_drift_detected(self):
        """base_trust=0.75, drift_penalty=-0.2 → 0.75 * 1.2 = 0.9."""
        confidence = compute_trust_confidence(0.75, -0.2)
        assert round(confidence, 2) == 0.9

    def test_half_trust_feature_mismatch(self):
        """base_trust=0.5, drift_penalty=-0.3 → 0.5 * 1.3 = 0.65."""
        confidence = compute_trust_confidence(0.5, -0.3)
        assert round(confidence, 2) == 0.65

    def test_low_trust_unevaluable(self):
        """base_trust=0.4, drift_penalty=-0.5 → 0.4 * 1.5 = 0.6."""
        confidence = compute_trust_confidence(0.4, -0.5)
        assert round(confidence, 1) == 0.6

    def test_zero_base_trust(self):
        """base_trust=0.0 → confidence=0.0 (gates failed)."""
        confidence = compute_trust_confidence(0.0, -0.2)
        assert confidence == 0.0

    def test_clamped_to_one(self):
        """Result > 1.0 is clamped to 1.0."""
        # 0.9 * (1.0 - (-0.3)) = 0.9 * 1.3 = 1.17 → clamped to 1.0
        confidence = compute_trust_confidence(0.9, -0.3)
        assert confidence == 1.0


class TestCreateFindingsFromDrift:
    """Test findings creation for operator visibility."""

    def test_no_findings_all_no_drift(self):
        """All equipment no drift → no findings."""
        verdicts = {
            "chiller": ("NO_DRIFT_DETECTED", "S002-CHILLER-B1-001"),
            "ahu": ("NO_DRIFT_DETECTED", "S002-AHU-001"),
        }
        findings = create_findings_from_drift("site-002", verdicts)
        assert len(findings) == 0

    def test_unevaluable_finding(self):
        """UNEVALUABLE → data_quality_uncertain finding."""
        verdicts = {
            "chiller": ("UNEVALUABLE", None),
        }
        findings = create_findings_from_drift("site-002", verdicts)
        assert len(findings) == 1
        assert findings[0]["finding_type"] == "data_quality_uncertain"
        assert findings[0]["equipment_type"] == "chiller"
        assert findings[0]["severity"] == "medium"
        assert findings[0]["operator_review_required"] is True

    def test_feature_mismatch_finding(self):
        """FEATURE_MISMATCH → baseline_schema_mismatch finding."""
        verdicts = {
            "ahu": ("FEATURE_MISMATCH", "S002-AHU-001"),
        }
        findings = create_findings_from_drift("site-002", verdicts)
        assert len(findings) == 1
        assert findings[0]["finding_type"] == "baseline_schema_mismatch"
        assert findings[0]["equipment_type"] == "ahu"
        assert findings[0]["equipment_id"] == "S002-AHU-001"
        assert findings[0]["severity"] == "medium"

    def test_drift_detected_finding(self):
        """DRIFT_DETECTED → model_degradation finding."""
        verdicts = {
            "chiller": ("DRIFT_DETECTED", "S002-CHILLER-B1-001"),
        }
        findings = create_findings_from_drift("site-002", verdicts)
        assert len(findings) == 1
        assert findings[0]["finding_type"] == "model_degradation"
        assert findings[0]["equipment_type"] == "chiller"
        assert findings[0]["severity"] == "high"
        assert findings[0]["operator_review_required"] is True

    def test_multiple_findings(self):
        """Multiple equipment with issues → multiple findings."""
        verdicts = {
            "chiller": ("DRIFT_DETECTED", "S002-CHILLER-B1-001"),
            "ahu": ("UNEVALUABLE", None),
            "fcu": ("FEATURE_MISMATCH", "S002-FCU-001"),
        }
        findings = create_findings_from_drift("site-002", verdicts)
        assert len(findings) == 3

        # Check findings are created for each issue
        finding_types = {f["finding_type"] for f in findings}
        assert finding_types == {"model_degradation", "data_quality_uncertain", "baseline_schema_mismatch"}

    def test_unknown_equipment_id_fallback(self):
        """Missing equipment_id → fallback to equipment_type."""
        verdicts = {
            "vav": ("UNEVALUABLE", None),
        }
        findings = create_findings_from_drift("site-002", verdicts)
        assert findings[0]["equipment_id"] == "unknown_vav"
