"""Compose deterministic building-state services into a cockpit payload."""

from __future__ import annotations

from app.services.cockpit_issue_fusion import CockpitIssueFusionService
from app.services.building_posture_resolver import resolve_building_posture
from app.services.building_state_models import (
    BuildingStatePayload,
    PrimaryNarrative,
    SecondaryTension,
)
from app.services.dominant_narrative_selector import select_dominant_narrative
from app.services.narrative_candidate_generator import generate_narrative_candidates
from app.services.operator_guidance_resolver import resolve_operator_guidance
from app.services.site_operating_mode_service import SentinelOperatingMode, resolve_site_operating_mode


def build_building_state_payload(
    site_id: str,
    issue_service: CockpitIssueFusionService | None = None,
    operating_mode: SentinelOperatingMode | None = None,
) -> BuildingStatePayload:
    resolved_mode = operating_mode or resolve_site_operating_mode(site_id)
    candidates = generate_narrative_candidates(site_id, issue_service=issue_service, operating_mode=resolved_mode)
    posture = resolve_building_posture(candidates)
    primary_candidate, secondary_candidates = select_dominant_narrative(posture, candidates)
    guidance = resolve_operator_guidance(posture)

    return BuildingStatePayload(
        site_id=site_id,
        building_posture=posture,
        primary_narrative=(
            PrimaryNarrative(
                voice=primary_candidate.voice,
                message=primary_candidate.message,
                location=primary_candidate.location,
                time_to_breach_min=primary_candidate.time_to_constraint_breach_min,
                urgency=guidance.mode,
                action=primary_candidate.action,
            )
            if primary_candidate
            else None
        ),
        secondary_tensions=[
            SecondaryTension(voice=candidate.voice, message=candidate.message)
            for candidate in secondary_candidates
        ][:2],
        operator_guidance=guidance,
    )
