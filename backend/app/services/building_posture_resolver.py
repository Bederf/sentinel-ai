"""Deterministic building posture resolution for the cockpit."""

from __future__ import annotations

from app.services.building_state_models import BuildingPosture, NarrativeCandidate


def resolve_building_posture(candidates: list[NarrativeCandidate]) -> BuildingPosture:
    eligible = [candidate for candidate in candidates if not candidate.resolved and candidate.spatially_grounded]
    if not eligible:
        return "calm"

    soonest_breach = min(
        (
            candidate.time_to_constraint_breach_min
            for candidate in eligible
            if candidate.time_to_constraint_breach_min is not None
        ),
        default=None,
    )
    high_criticality = max((candidate.system_criticality for candidate in eligible), default=0.0)
    widespread = max((candidate.propagation_risk for candidate in eligible), default=0.0)
    margin_erosion = any(candidate.eroding_margin for candidate in eligible)

    if soonest_breach is not None and soonest_breach <= 10:
        return "critical"
    if soonest_breach is not None and soonest_breach <= 15:
        return "strained"
    if margin_erosion:
        return "compensating"
    if high_criticality >= 0.9 and widespread >= 0.6:
        return "strained"
    return "drifting"
