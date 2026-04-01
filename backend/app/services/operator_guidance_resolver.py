"""Resolve operator guidance from building posture."""

from __future__ import annotations

from app.services.building_state_models import BuildingPosture, GuidanceMode, OperatorGuidance


def resolve_operator_guidance(posture: BuildingPosture) -> OperatorGuidance:
    if posture == "critical":
        return OperatorGuidance(headline="Immediate operator attention required.", mode="act_now")
    if posture == "strained":
        return OperatorGuidance(headline="Intervene soon.", mode="intervene_soon")
    if posture == "compensating":
        return OperatorGuidance(headline="Prepare for intervention.", mode="prepare")
    if posture == "drifting":
        return OperatorGuidance(headline="Watch the building drift.", mode="watch")
    return OperatorGuidance(headline="No action needed.", mode="none")
