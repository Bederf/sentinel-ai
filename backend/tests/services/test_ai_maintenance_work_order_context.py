from app.services.ai_maintenance_work_order_context import (
    build_ai_maintenance_context,
    build_ai_maintenance_description,
    is_ai_maintenance_recommendation,
)


def test_identifies_ai_maintenance_recommendations():
    assert is_ai_maintenance_recommendation("maintenance", {}) is True
    assert is_ai_maintenance_recommendation("optimization", {"type": "schedule_maintenance"}) is True
    assert is_ai_maintenance_recommendation("ai_optimization", {"point": "setpoint", "value": 22}) is False


def test_builds_context_for_closeout_prompts():
    action = {
        "type": "schedule_maintenance",
        "priority": "high",
        "evidence": ["Health at 60%", "2 alerts in 30 days", None],
        "immediate_actions": ["Check condenser approach temps", "Review recent alarms"],
    }

    context = build_ai_maintenance_context(
        recommendation_id="rec-123",
        site_id="site-002",
        equipment_code="S002-CHILLER-B01",
        action_type="maintenance",
        action=action,
        reason="Maintenance Required: chiller health degradation",
        confidence_score=0.75,
    )

    assert context["source"] == "ai_maintenance_recommendation"
    assert context["fault_type"] == "schedule_maintenance"
    assert context["faulty_equipment"] == "S002-CHILLER-B01"
    assert context["recommended_actions"] == ["Check condenser approach temps", "Review recent alarms"]
    assert "Health at 60%" in context["fault_description"]


def test_builds_technician_description_with_evidence_and_checks():
    context = {
        "priority": "high",
        "evidence": ["Health at 60%"],
        "recommended_actions": ["Check condenser approach temps"],
    }

    description = build_ai_maintenance_description(
        recommendation_id="rec-123",
        equipment_code="S002-CHILLER-B01",
        reason="Maintenance Required",
        diagnostic_context=context,
    )

    assert "Created from SENTINEL AI maintenance recommendation rec-123" in description
    assert "Health at 60%" in description
    assert "Check condenser approach temps" in description
    assert "Closeout required" in description
