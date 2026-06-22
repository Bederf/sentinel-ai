import os

os.environ.setdefault("SITE_ID", "site-002")
os.environ.setdefault("PLANT_SITE_ID", "site-002")
os.environ.setdefault("BUILDING_NAME", "Sandton City")
os.environ.setdefault("CONSENT_HASH_SALT", "test-only-consent-salt")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars")

import pytest
from fastapi import HTTPException

from app.api.optimization import (
    _coordinated_draft_decision_update,
    _coordinated_draft_retire_update,
    _coordinated_execution_blocked_result,
    _coordinated_execution_blockers,
    _format_coordinated_draft_telegram_message,
    _is_active_coordinated_bundle_record,
    _transition_bundle_to_supervised_draft,
    _validate_coordinated_draft_record,
    _validate_coordinated_execution_record,
    _validate_coordinated_packaging_allowed,
    _validate_coordinated_retire_record,
)
from app.services.coordinated_optimization_planner import (
    LEGACY_JACE_BACNET_BLOCKER,
    READ_ONLY_BLOCKER,
    SIMBIOT_WRITE_MAPPING_BLOCKER,
    PlannerContext,
    build_coordinated_bundles,
)


def _bundle_payload(bundle):
    return bundle["metadata"]["coordination_bundle"]


def test_transition_to_supervised_draft_uses_existing_recommendation_lifecycle():
    bundles = build_coordinated_bundles(
        context=PlannerContext(
            site_id="site-002",
            site_phase="supervised",
            simbiot_write_mapping_verified=True,
            insurance_confirmed=True,
        ),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
        ],
    )

    draft = _transition_bundle_to_supervised_draft(bundles[0], requested_by="operator-1")
    payload = _bundle_payload(draft)

    assert draft["action_type"] == "coordinated_optimization"
    assert draft["status"] == "pending"
    assert draft["approval_status"] == "pending"
    assert draft["requires_approval"] is True
    assert draft["action"]["execution_blocked"] is True
    assert draft["metadata"]["lifecycle"] == "draft_pending_approval"
    assert draft["metadata"]["packaging_transition"] == "read_only_bundle_to_supervised_draft"
    assert READ_ONLY_BLOCKER not in payload["blocked_reasons"]
    assert payload["execution_eligibility"] == "pending_approval"


def test_transition_preserves_real_blockers_when_read_only_blocker_is_removed():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
        ],
    )

    draft = _transition_bundle_to_supervised_draft(bundles[0], requested_by="operator-1")
    blockers = _bundle_payload(draft)["blocked_reasons"]

    assert READ_ONLY_BLOCKER not in blockers
    assert SIMBIOT_WRITE_MAPPING_BLOCKER in blockers
    assert "insurance_not_confirmed" in blockers


def test_packaged_draft_payload_uses_pending_recommendation_columns():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
        ],
    )
    draft = _transition_bundle_to_supervised_draft(bundles[0], requested_by="operator-1")

    assert draft["action_type"] == "coordinated_optimization"
    assert draft["status"] == "pending"
    assert draft["approval_status"] == "pending"
    assert draft["requires_approval"] is True
    assert draft["action"]["execution_blocked"] is True
    assert draft["metadata"]["lifecycle"] == "draft_pending_approval"


def test_packaging_rejects_advisory_phase():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
        ],
    )

    with pytest.raises(HTTPException) as exc:
        _validate_coordinated_packaging_allowed(bundles[0], "advisory")

    assert exc.value.status_code == 409
    assert "cannot package" in exc.value.detail


def test_packaging_rejects_active_work_order_conflict():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
        ],
        work_orders=[{"code": "WO-1", "equipment_code": "S002-AHU-B01", "status": "scheduled"}],
    )

    with pytest.raises(HTTPException) as exc:
        _validate_coordinated_packaging_allowed(bundles[0], "supervised")

    assert exc.value.status_code == 409
    assert "active or pending work orders" in exc.value.detail


def test_operator_review_actions_can_package_with_missing_simbiot_mapping_preserved():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
        ],
    )

    _validate_coordinated_packaging_allowed(bundles[0], "supervised")
    draft = _transition_bundle_to_supervised_draft(bundles[0], requested_by="operator-1")
    payload = _bundle_payload(draft)

    assert payload["recommended_actions"][0]["action_type"] == "operator_review"
    assert SIMBIOT_WRITE_MAPPING_BLOCKER in payload["recommended_actions"][0]["blocked_reasons"]


def test_controllable_actions_reject_missing_simbiot_mapping():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
        ],
    )
    payload = _bundle_payload(bundles[0])
    payload["recommended_actions"] = [
        {
            "action_id": "child-1",
            "equipment_code": "S002-AHU-B01",
            "action_type": "setpoint_change",
            "point": "cooling_setpoint",
            "recommended_value": 22,
            "blocked_reasons": [READ_ONLY_BLOCKER, SIMBIOT_WRITE_MAPPING_BLOCKER],
        }
    ]

    with pytest.raises(HTTPException) as exc:
        _validate_coordinated_packaging_allowed(bundles[0], "supervised")

    assert exc.value.status_code == 409
    assert "SIMBIOT/BMS write mapping" in exc.value.detail


def test_coordinated_draft_approval_marks_parent_approved_without_execution():
    bundles = build_coordinated_bundles(
        context=PlannerContext(
            site_id="site-002",
            site_phase="supervised",
            simbiot_write_mapping_verified=True,
            insurance_confirmed=True,
        ),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
        ],
    )
    record = _transition_bundle_to_supervised_draft(bundles[0], requested_by="operator-1")

    _validate_coordinated_draft_record(record, "site-002")
    updates = _coordinated_draft_decision_update(
        record,
        decision="approved",
        user_id="operator-2",
        reason="Proceed with supervised review",
    )

    assert updates["status"] == "approved"
    assert updates["approval_status"] == "approved"
    assert updates["action"]["execution_blocked"] is True
    assert updates["action"]["blocker"] == "coordinated_execution_not_implemented"
    assert updates["execution_result"]["executed"] is False
    assert updates["execution_result"]["device_writes"] == 0
    assert updates["metadata"]["lifecycle"] == "approved_pending_execution"
    assert updates["metadata"]["coordination_bundle"]["approval_status"] == "approved"
    assert updates["metadata"]["approval_audit"][0]["decision"] == "approved"


def test_approved_coordinated_bundle_still_blocks_repackaging():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
        ],
    )
    record = _transition_bundle_to_supervised_draft(bundles[0], requested_by="operator-1")
    updates = _coordinated_draft_decision_update(
        record,
        decision="approved",
        user_id="operator-2",
        reason="Proceed with supervised review",
    )
    approved_record = {**record, **updates}
    bundle_id = _bundle_payload(record)["bundle_id"]

    assert _is_active_coordinated_bundle_record(approved_record, bundle_id) is True

    rejected_record = {
        **approved_record,
        "status": "rejected",
        "metadata": {**approved_record["metadata"], "lifecycle": "rejected"},
    }
    assert _is_active_coordinated_bundle_record(rejected_record, bundle_id) is False

    expired_stale_lifecycle_record = {
        **record,
        "status": "expired",
        "approval_status": "pending",
    }
    assert _is_active_coordinated_bundle_record(expired_stale_lifecycle_record, bundle_id) is False


def test_retired_coordinated_bundle_no_longer_blocks_repackaging():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
        ],
    )
    record = _transition_bundle_to_supervised_draft(bundles[0], requested_by="operator-1")
    approved_updates = _coordinated_draft_decision_update(
        record,
        decision="approved",
        user_id="operator-2",
        reason="Proceed with supervised review",
    )
    approved_record = {**record, **approved_updates}
    blocked_update = _coordinated_execution_blocked_result(
        record=approved_record,
        blockers=["missing_verified_simbiot_write_mapping"],
        user_id="operator-2",
        reason="Preflight blocked",
    )
    blocked_record = {**approved_record, **blocked_update}
    retire_updates = _coordinated_draft_retire_update(
        blocked_record,
        user_id="operator-3",
        reason="Supersede before clean Telegram callback proof",
    )
    retired_record = {**blocked_record, **retire_updates}
    bundle_id = _bundle_payload(record)["bundle_id"]

    assert retire_updates["status"] == "expired"
    assert retire_updates["approval_status"] == "superseded"
    assert retire_updates["execution_result"]["device_writes"] == 0
    assert retire_updates["metadata"]["lifecycle"] == "superseded"
    assert retire_updates["metadata"]["coordination_bundle"]["approval_status"] == "superseded"
    assert retire_updates["metadata"]["approval_audit"][-1]["decision"] == "superseded"
    assert _is_active_coordinated_bundle_record(retired_record, bundle_id) is False


def test_coordinated_execution_requires_approved_parent_lifecycle():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
        ],
    )
    record = _transition_bundle_to_supervised_draft(bundles[0], requested_by="operator-1")

    with pytest.raises(HTTPException) as exc:
        _validate_coordinated_execution_record(record, "site-002")

    assert exc.value.status_code == 400
    assert "not approved" in exc.value.detail

    updates = _coordinated_draft_decision_update(record, decision="approved", user_id="operator-2", reason=None)
    approved_record = {**record, **updates}
    _validate_coordinated_execution_record(approved_record, "site-002")


def test_coordinated_retire_requires_approved_preflight_blocked_row():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
        ],
    )
    record = _transition_bundle_to_supervised_draft(bundles[0], requested_by="operator-1")
    updates = _coordinated_draft_decision_update(record, decision="approved", user_id="operator-2", reason=None)
    approved_record = {**record, **updates}

    with pytest.raises(HTTPException) as exc:
        _validate_coordinated_retire_record(approved_record, "site-002")

    assert exc.value.status_code == 409
    assert "blocked before device writes" in exc.value.detail

    blocked_update = _coordinated_execution_blocked_result(
        record=approved_record,
        blockers=["missing_verified_simbiot_write_mapping"],
        user_id="operator-2",
        reason="Preflight blocked",
    )
    blocked_record = {**approved_record, **blocked_update}
    _validate_coordinated_retire_record(blocked_record, "site-002")


def test_coordinated_execution_preflight_blocks_stale_prerequisites_without_device_writes():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
        ],
    )
    record = _transition_bundle_to_supervised_draft(bundles[0], requested_by="operator-1")
    updates = _coordinated_draft_decision_update(record, decision="approved", user_id="operator-2", reason=None)
    approved_record = {**record, **updates}

    blockers = _coordinated_execution_blockers(
        record=approved_record,
        live_bundle=bundles[0],
        site_phase="supervised",
    )
    blocked_update = _coordinated_execution_blocked_result(
        record=approved_record,
        blockers=blockers,
        user_id="operator-2",
        reason="Verify blocked execution",
    )

    assert SIMBIOT_WRITE_MAPPING_BLOCKER in blockers
    assert "insurance_not_confirmed" in blockers
    assert "no_controllable_child_actions" in blockers
    assert blocked_update["execution_result"]["executed"] is False
    assert blocked_update["execution_result"]["device_writes"] == 0
    assert blocked_update["execution_result"]["status"] == "blocked_preflight"


def test_coordinated_draft_rejection_marks_parent_rejected_without_execution():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
        ],
    )
    record = _transition_bundle_to_supervised_draft(bundles[0], requested_by="operator-1")

    updates = _coordinated_draft_decision_update(
        record,
        decision="rejected",
        user_id="operator-2",
        reason="Needs more evidence",
    )

    assert updates["status"] == "rejected"
    assert updates["approval_status"] == "rejected"
    assert updates["action"]["execution_blocked"] is True
    assert updates["execution_result"]["executed"] is False
    assert updates["execution_result"]["device_writes"] == 0
    assert updates["metadata"]["lifecycle"] == "rejected"
    assert updates["metadata"]["coordination_bundle"]["approval_status"] == "rejected"
    assert updates["metadata"]["approval_audit"][0]["decision"] == "rejected"


def test_coordinated_draft_telegram_message_states_no_setpoint_write():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
        ],
    )
    record = _transition_bundle_to_supervised_draft(bundles[0], requested_by="operator-1")
    record["metadata"]["site_name"] = "Sandton City Office Tower Updated"

    message = _format_coordinated_draft_telegram_message(record)

    assert "SENTINEL AI Recommendation" in message
    assert "Coordinated Optimization Draft" not in message
    assert "Sandton City" in message
    assert "Office Tower Updated" not in message
    assert "site-002" not in message
    assert "S002-AHU-B01" in message
    assert "Recommended action" in message
    assert "Expected benefit" in message
    assert "{'reliability'" not in message
    assert SIMBIOT_WRITE_MAPPING_BLOCKER in message
    assert "Approve will apply the change only if SIMBIOT mapping" in message


def test_coordinated_draft_telegram_message_normalizes_legacy_jace_blocker():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised", insurance_confirmed=True),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
        ],
    )
    record = _transition_bundle_to_supervised_draft(bundles[0], requested_by="operator-1")
    record["metadata"]["coordination_bundle"]["blocked_reasons"] = [LEGACY_JACE_BACNET_BLOCKER]

    message = _format_coordinated_draft_telegram_message(record)

    assert SIMBIOT_WRITE_MAPPING_BLOCKER in message
    assert LEGACY_JACE_BACNET_BLOCKER not in message
