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

# Module-level poll counter for sustained-polls tracking
_fallback_poll_count: int = 0
_cooling_drift_last_met: bool = False


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


def _fetch_zone_temperatures(site_id: str) -> dict[str, float | int]:
    """Fetch basement and L0 zone temperatures for fallback telemetry gating.

    Returns:
        dict with basement_temp_c, l0_avg_temp_c, sustained_polls
    """
    try:
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()

        # Get site UUID for zone query
        site_row = sb.table("sites").select("id").eq("code", site_id).execute()
        if not site_row.data:
            return {}
        site_uuid = site_row.data[0]["id"]

        # Fetch all zones for this site — includes floor and zone_id
        rows = sb.table("zones").select("zone_id, floor").eq("site_id", site_uuid).execute()
        if not rows.data:
            return {}

        # Separate basement (B1) and L0 zones
        basement_zones: list[str] = []
        l0_zones: list[str] = []
        for row in rows.data:
            floor = row.get("floor", "")
            zone_id = row.get("zone_id", "")
            if floor == "B1":
                basement_zones.append(zone_id)
            elif floor == "L0":
                l0_zones.append(zone_id)

        # Fetch temperature from equipment table — zone-level FCU/VAV units
        # Equipment naming: S002-FCU-{zone_num} → zone_id is Zone-{num}
        basement_temps: list[float] = []
        l0_temps: list[float] = []

        if basement_zones:
            # Map zone_id (Zone-XXX) → zone_num for equipment lookup
            basement_nums = []
            for zid in basement_zones:
                parts = zid.split("-")
                if len(parts) == 2:
                    basement_nums.append(parts[1])

            equip_rows = (
                sb.table("equipment")
                .select("equipment_id, zone_id, temperature_c")
                .eq("site_id", site_uuid)
                .in_("zone_id", basement_zones)
                .execute()
            ).data
            for row in equip_rows:
                temp = row.get("temperature_c")
                if isinstance(temp, (int, float)):
                    basement_temps.append(float(temp))

        if l0_zones:
            l0_nums = []
            for zid in l0_zones:
                parts = zid.split("-")
                if len(parts) == 2:
                    l0_nums.append(parts[1])

            equip_rows = (
                sb.table("equipment")
                .select("equipment_id, zone_id, temperature_c")
                .eq("site_id", site_uuid)
                .in_("zone_id", l0_zones)
                .execute()
            ).data
            for row in equip_rows:
                temp = row.get("temperature_c")
                if isinstance(temp, (int, float)):
                    l0_temps.append(float(temp))

        basement_temp = basement_temps[0] if basement_temps else None
        l0_avg = sum(l0_temps) / len(l0_temps) if l0_temps else None

        # Update sustained-polls counter
        global _fallback_poll_count, _cooling_drift_last_met
        _fallback_poll_count += 1

        cooling_drift_now = basement_temp is not None and l0_avg is not None and basement_temp > l0_avg + 1.0
        sustained = _fallback_poll_count if (cooling_drift_now and _cooling_drift_last_met) else 0
        if cooling_drift_now:
            _cooling_drift_last_met = True
        else:
            _cooling_drift_last_met = False
            _fallback_poll_count = 0

        result: dict[str, float | int] = {
            "basement_temp_c": basement_temp,
            "l0_avg_temp_c": l0_avg,
            "sustained_polls": sustained,
        }
        return {k: v for k, v in result.items() if v is not None}

    except Exception as exc:
        logger.debug("Could not fetch zone temperatures for %s: %s", site_id, exc)
        return {}


def build_building_state_payload(
    site_id: str,
    issue_service: CockpitIssueFusionService | None = None,
    operating_mode: SentinelOperatingMode | None = None,
) -> BuildingStatePayload:
    resolved_mode = operating_mode or resolve_site_operating_mode(site_id)
    telemetry = _fetch_zone_temperatures(site_id)
    candidates = generate_narrative_candidates(
        site_id, issue_service=issue_service, operating_mode=resolved_mode, telemetry=telemetry
    )
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
