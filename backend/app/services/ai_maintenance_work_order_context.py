"""Helpers for AI-origin maintenance work order context.

Staff-created work orders stay free-form. These helpers are only for work
orders created from AI maintenance recommendations, where the technician needs
the original evidence and targeted closeout prompts.
"""

from __future__ import annotations

from typing import Any


MAINTENANCE_RECOMMENDATION_TYPES = {
    "health_maintenance",
    "maintenance",
    "maintenance_gap",
    "maintenance_schedule",
}


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if value]


def is_ai_maintenance_recommendation(action_type: str | None, action: dict[str, Any] | None) -> bool:
    """Return True when a recommendation should become an AI maintenance WO."""
    normalized_action_type = str(action_type or "").strip().lower()
    action_type_value = str((action or {}).get("type") or "").strip().lower()
    return normalized_action_type in MAINTENANCE_RECOMMENDATION_TYPES or action_type_value == "schedule_maintenance"


def build_ai_maintenance_context(
    *,
    recommendation_id: str,
    site_id: str,
    equipment_code: str,
    action_type: str | None,
    action: dict[str, Any] | None,
    reason: str,
    confidence_score: float | None = None,
) -> dict[str, Any]:
    """Build diagnostic context consumed by the technician closeout flow."""
    action = action or {}
    evidence = _clean_list(action.get("evidence"))
    recommended_actions = _clean_list(action.get("immediate_actions"))
    priority = str(action.get("priority") or "medium")

    fault_description = reason or f"AI maintenance recommendation for {equipment_code}"
    if evidence:
        fault_description = f"{fault_description}\nEvidence: " + "; ".join(evidence)

    return {
        "source": "ai_maintenance_recommendation",
        "recommendation_id": recommendation_id,
        "site_id": site_id,
        "fault_type": str(action.get("type") or action_type or "schedule_maintenance"),
        "fault_description": fault_description[:1200],
        "faulty_equipment": equipment_code,
        "recommended_actions": recommended_actions,
        "evidence": evidence,
        "priority": priority,
        "confidence_score": confidence_score,
        "inspection_checklist": recommended_actions,
    }


def build_ai_maintenance_description(
    *,
    recommendation_id: str,
    equipment_code: str,
    reason: str,
    diagnostic_context: dict[str, Any],
) -> str:
    """Build the WO description shown to dispatchers and technicians."""
    evidence = diagnostic_context.get("evidence") or []
    actions = diagnostic_context.get("recommended_actions") or []

    lines = [
        f"Created from SENTINEL AI maintenance recommendation {recommendation_id}.",
        "",
        f"Equipment: {equipment_code or 'Unknown'}",
        f"Priority: {diagnostic_context.get('priority', 'medium')}",
    ]
    if reason:
        lines.extend(["", "Reason:", reason])
    if evidence:
        lines.extend(["", "Evidence:"])
        lines.extend(f"- {item}" for item in evidence)
    if actions:
        lines.extend(["", "Technician to check:"])
        lines.extend(f"- {item}" for item in actions)
    lines.extend(
        [
            "",
            "Closeout required:",
            "- Confirm whether the AI-indicated condition was present.",
            "- Record root cause, corrective action, readings/photos, and any follow-up work needed.",
        ]
    )
    return "\n".join(lines)
