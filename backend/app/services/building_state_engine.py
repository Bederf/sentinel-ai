"""Compose deterministic building-state services into a cockpit payload."""

from __future__ import annotations

import logging

from app.services.building_posture_resolver import resolve_building_posture
from app.services.building_state_models import (
    BuildingStatePayload,
    EmailClusterPayload,
    PrimaryNarrative,
    SecondaryTension,
)
from app.services.cockpit_issue_fusion import CockpitIssueFusionService
from app.services.dominant_narrative_selector import select_dominant_narrative
from app.services.email_cluster_service import get_email_cluster_service
from app.services.narrative_candidate_generator import generate_narrative_candidates
from app.services.operator_guidance_resolver import resolve_operator_guidance
from app.services.site_operating_mode_service import SentinelOperatingMode, resolve_site_operating_mode

logger = logging.getLogger(__name__)


async def _get_site_onboarding_phase(site_id: str) -> str:
    """Fetch onboarding phase for a site. Returns 'shadow' as safe default on error."""
    try:
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        result = sb.table("sites").select("onboarding_phase").eq("code", site_id).execute()
        if result.data:
            return result.data[0].get("onboarding_phase") or "shadow"
    except Exception as exc:
        logger.debug("Could not fetch onboarding_phase for %s: %s", site_id, exc)
    return "shadow"


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

    # Email cluster heatmap data
    cluster_service = get_email_cluster_service()
    open_clusters = cluster_service.get_open_clusters(site_id)
    email_clusters = [
        EmailClusterPayload(
            cluster_id=c["id"],
            zone_id=c["zone_id"],
            zone_name=c.get("zone_name", c["zone_id"]),
            floor=c.get("floor", ""),
            email_count=c["email_count"],
            complaint_type=c["complaint_type"],
            severity=c["severity"],
            summary=c.get("summary", ""),
        )
        for c in open_clusters
        if c.get("email_count", 0) >= 3  # Only clusters that have hit the heatmap threshold
    ]

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
            SecondaryTension(voice=candidate.voice, message=candidate.message) for candidate in secondary_candidates
        ][:2],
        operator_guidance=guidance,
        email_clusters=email_clusters,
    )
