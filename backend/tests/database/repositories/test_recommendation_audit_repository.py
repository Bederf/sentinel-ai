"""Recommendation audit event repository tests."""

import pytest

from app.database.repositories.recommendation_audit_repository import (
    infer_lifecycle_event_type,
    recommendation_state,
    RecommendationAuditRepository,
)


def test_recommendation_state_keeps_audit_relevant_fields_only():
    row = {
        "id": "rec-1",
        "status": "pending",
        "risk_level": "high",
        "approval_status": None,
        "approved_by": None,
        "target_equipment": "S002-CHILLER-B01",
        "action_type": "ai_optimization",
        "reason": "Long narrative not needed in state diff",
    }

    state = recommendation_state(row)

    assert state["status"] == "pending"
    assert state["risk_level"] == "high"
    assert state["target_equipment"] == "S002-CHILLER-B01"
    assert state["action_type"] == "ai_optimization"
    assert "reason" not in state


@pytest.mark.parametrize(
    ("new_status", "event_type"),
    [
        ("approved", "approved"),
        ("rejected", "rejected"),
        ("expired", "expired"),
        ("failed", "failed"),
        ("executed", "executed"),
        ("auto_executed", "resolved"),
    ],
)
def test_infer_lifecycle_event_type_from_status_transition(new_status, event_type):
    assert infer_lifecycle_event_type({"status": "pending"}, {"status": new_status}) == event_type


def test_infer_lifecycle_event_type_returns_updated_without_status_change():
    assert infer_lifecycle_event_type({"status": "pending"}, {"status": "pending"}) == "updated"


@pytest.mark.asyncio
async def test_quality_exception_requires_detected_by():
    repo = RecommendationAuditRepository()

    with pytest.raises(ValueError, match="detected_by"):
        await repo.record_event(
            recommendation_id="11111111-1111-1111-1111-111111111111",
            linked_recommendation_id="11111111-1111-1111-1111-111111111111",
            site_id="site-002",
            event_type="system_quality_exception",
            quality_exception_type="severity_reclassified",
            previous_state={"risk_level": "low"},
            new_state={"risk_level": "high"},
        )


@pytest.mark.asyncio
async def test_quality_exception_requires_linked_recommendation_id():
    repo = RecommendationAuditRepository()

    with pytest.raises(ValueError, match="linked_recommendation_id"):
        await repo.record_event(
            recommendation_id=None,
            site_id="site-002",
            event_type="system_quality_exception",
            quality_exception_type="severity_reclassified",
            detected_by="human_review:Shad",
            previous_state={"risk_level": "low"},
            new_state={"risk_level": "high"},
        )
