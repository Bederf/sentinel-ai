from pathlib import Path

from app.services.phase188_outcome_validation_service import (
    EPOCH_POST_CUTOVER,
    EPOCH_PRE_CUTOVER,
    GATE_BLOCKED_PRE_CUTOVER,
    GATE_NOT_ENOUGH_EVIDENCE,
    GATE_SAFETY_UNRESOLVED,
    Phase188OutcomeValidationService,
    SafetyProfile,
    ThresholdConfig,
    resolve_threshold,
)


def _service() -> Phase188OutcomeValidationService:
    return Phase188OutcomeValidationService()


def _threshold(
    *,
    equipment_type: str = "fcu",
    recommendation_type: str = "optimization",
    safety_class: str = "MEDIUM",
    site_id: str | None = None,
    min_validated: int = 1,
    min_measured: int = 1,
    promotion_mode: str = "advisory_only",
) -> ThresholdConfig:
    return ThresholdConfig(
        site_id=site_id,
        equipment_type=equipment_type,
        recommendation_type=recommendation_type,
        safety_class=safety_class,
        min_validated_recommendations=min_validated,
        min_measured_outcomes=min_measured,
        max_false_positive_rate=1.0,
        max_false_negative_rate=1.0,
        min_positive_outcome_rate=0.0,
        promotion_mode=promotion_mode,
    )


def test_pre_cutover_rows_are_explicitly_excluded_from_promotion_math():
    report = _service().evaluate_rows(
        [
            {
                "site_id": "site-002",
                "target_equipment": "S002-FCU-101",
                "action_type": "optimization",
                "phase188_evidence_epoch": EPOCH_PRE_CUTOVER,
                "outcome_validated": True,
            }
        ],
        safety_profiles=[
            SafetyProfile(equipment_type="fcu", default_safety_class="MEDIUM"),
        ],
        thresholds=[_threshold()],
        site_id="site-002",
    )

    assert report["eligible_rows"] == 0
    assert report["excluded_pre_cutover"] == 1
    assert report["overall_gate_result"] == GATE_BLOCKED_PRE_CUTOVER


def test_missing_epoch_is_not_treated_as_eligible():
    report = _service().evaluate_rows(
        [
            {
                "site_id": "site-002",
                "target_equipment": "S002-FCU-101",
                "action_type": "optimization",
                "outcome_validated": True,
            }
        ],
        safety_profiles=[
            SafetyProfile(equipment_type="fcu", default_safety_class="MEDIUM"),
        ],
        thresholds=[_threshold()],
        site_id="site-002",
    )

    assert report["eligible_rows"] == 0
    assert report["excluded_unknown"] == 1
    assert report["overall_gate_result"] == GATE_NOT_ENOUGH_EVIDENCE


def test_point_safety_resolution_uses_worst_case_class():
    report = _service().evaluate_rows(
        [
            {
                "site_id": "site-002",
                "target_equipment": "S002-CHILLER-B1-001",
                "action_type": "optimization",
                "phase188_evidence_epoch": EPOCH_POST_CUTOVER,
                "action": {
                    "points": [
                        {"point": "chw_setpoint", "safety_class": "LOW"},
                        {"point": "run", "safety_class": "HIGH"},
                    ]
                },
                "outcome_validated": True,
            }
        ],
        safety_profiles=[],
        thresholds=[
            _threshold(equipment_type="chiller", safety_class="HIGH"),
        ],
        site_id="site-002",
    )

    group = report["groups"][0]
    assert group["equipment_type"] == "chiller"
    assert group["safety_class"] == "HIGH"
    assert group["counts"]["validated"] == 1


def test_equipment_type_safety_profile_is_used_when_points_absent():
    report = _service().evaluate_rows(
        [
            {
                "site_id": "site-002",
                "target_equipment": "S002-FCU-101",
                "action_type": "optimization",
                "phase188_evidence_epoch": EPOCH_POST_CUTOVER,
                "outcome_validated": True,
            }
        ],
        safety_profiles=[
            SafetyProfile(equipment_type="fcu", default_safety_class="MEDIUM"),
        ],
        thresholds=[_threshold()],
        site_id="site-002",
    )

    group = report["groups"][0]
    assert group["safety_class"] == "MEDIUM"
    assert group["gate_result"] == "advisory_only"


def test_unresolved_safety_class_fails_closed():
    report = _service().evaluate_rows(
        [
            {
                "site_id": "site-002",
                "target_equipment": "S002-FCU-101",
                "action_type": "optimization",
                "phase188_evidence_epoch": EPOCH_POST_CUTOVER,
                "outcome_validated": True,
            }
        ],
        safety_profiles=[],
        thresholds=[_threshold()],
        site_id="site-002",
    )

    assert report["safety_unresolved"] == 1
    assert report["overall_gate_result"] == GATE_SAFETY_UNRESOLVED
    assert report["groups"][0]["gate_result"] == GATE_SAFETY_UNRESOLVED


def test_threshold_resolution_prefers_site_override():
    global_threshold = _threshold(min_validated=5)
    site_threshold = _threshold(site_id="site-002", min_validated=2)

    resolved = resolve_threshold(
        [global_threshold, site_threshold],
        site_id="site-002",
        equipment_type="fcu",
        recommendation_type="optimization",
        safety_class="MEDIUM",
    )

    assert resolved is site_threshold
    assert resolved.min_validated_recommendations == 2


def test_low_sample_size_blocks_even_when_positive():
    report = _service().evaluate_rows(
        [
            {
                "site_id": "site-002",
                "target_equipment": "S002-FCU-101",
                "action_type": "optimization",
                "phase188_evidence_epoch": EPOCH_POST_CUTOVER,
                "outcome_validated": True,
            }
        ],
        safety_profiles=[
            SafetyProfile(equipment_type="fcu", default_safety_class="MEDIUM"),
        ],
        thresholds=[_threshold(min_validated=2, min_measured=2)],
        site_id="site-002",
    )

    group = report["groups"][0]
    assert group["gate_result"] == GATE_NOT_ENOUGH_EVIDENCE
    assert group["counts"]["validated"] == 1


def test_migration_bulk_tags_existing_history_explicitly():
    migration = Path("supabase/migrations/20260702_001_phase188_outcome_validation.sql").read_text()

    assert "ADD COLUMN phase188_evidence_epoch text NOT NULL DEFAULT 'excluded_unknown'" in migration
    assert "SET phase188_evidence_epoch = 'pre_cutover_legacy'" in migration
    assert "WHERE phase188_evidence_epoch = 'excluded_unknown'" in migration
