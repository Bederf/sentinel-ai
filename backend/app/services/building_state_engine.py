"""Compose deterministic building-state services into a cockpit payload."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

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

# Site capacity (kW) — used for load_high gate
_CAPACITY_KW: float = 300.0
_LOAD_HIGH_THRESHOLD: float = 0.85


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


def _zone_temps_from_equipment(equip_rows: list[dict], target_zones: list[str]) -> list[float]:
    """Extract zone temperatures from equipment by matching on location name.

    Zones table: zone_id='Zone-001', floor='L0'
    Equipment table: location='Level 0 Zone A', operating_data has temperature_c

    Zone-001 → floor L0 → location 'Level 0 Zone A'
    Zone-101 → floor L1 → location 'Level 1 Zone A'
    Zone-201 → floor L2 → location 'Level 2 Zone A'
    """
    zone_letter_map = {1: "A", 2: "B", 3: "C", 4: "D", 5: "E"}
    zone_to_location: dict[str, str] = {}

    for zone in target_zones:
        # Parse zone_id: 'Zone-NNN' where NNN = floor*100 + zone position
        try:
            num = int(zone.replace("Zone-", ""))
        except ValueError:
            continue
        floor_num = num // 100  # 1→L0, 2→L1, 3→L2, 0→Basement
        zone_pos = num % 100  # 1-5 → A-E

        if floor_num == 0:
            loc = "Basement 1"
        elif floor_num == 1:
            loc = f"Level 0 Zone {zone_letter_map.get(zone_pos, '')}"
        elif floor_num == 2:
            loc = f"Level 1 Zone {zone_letter_map.get(zone_pos, '')}"
        elif floor_num == 3:
            loc = f"Level 2 Zone {zone_letter_map.get(zone_pos, '')}"
        else:
            continue

        if loc:
            zone_to_location[zone] = loc

    # Build equipment.location → [temperatures] map
    loc_to_temps: dict[str, list[float]] = {}
    for row in equip_rows:
        loc = row.get("location") or ""
        od = row.get("operating_data") or {}
        t = od.get("temperature_c") or od.get("temperature") or od.get("temp_c")
        if isinstance(t, (int, float)) and loc:
            loc_to_temps.setdefault(loc, []).append(float(t))

    temps: list[float] = []
    for zone, loc in zone_to_location.items():
        if loc in loc_to_temps:
            temps.extend(loc_to_temps[loc])

    return temps


def _fetch_fallback_telemetry(site_id: str) -> dict[str, Any]:
    """Fetch telemetry for fallback narrative gating.

    Sources:
      - Zone temps: equipment table (temperature_c) per zone
      - Chiller cycling: equipment_sensor_readings (staging_state changes)
      - Load trending: equipment_sensor_readings (total_kw from site_aggregate)

    Returns:
        dict with basement_temp_c, l0_avg_temp_c, sustained_polls,
        staging_state, chiller_cycle_rate, total_kw, load_trending_up, load_high
    """
    from app.database.supabase_client import get_supabase_client

    result: dict[str, Any] = {}

    try:
        sb = get_supabase_client()

        # Get site UUID
        site_row = sb.table("sites").select("id").eq("code", site_id).execute()
        if not site_row.data:
            return result
        site_uuid = site_row.data[0]["id"]

        # ── Zone temperatures ────────────────────────────────────────────────
        try:
            rows = sb.table("zones").select("zone_id, floor").eq("site_id", site_uuid).execute()
            if rows.data:
                basement_zones = [r["zone_id"] for r in rows.data if r.get("floor") == "B1"]
                l0_zones = [r["zone_id"] for r in rows.data if r.get("floor") == "L0"]

                basement_temps: list[float] = []
                l0_temps: list[float] = []

                # equipment table has no zone_id — use equipment.location as zone_id proxy
                if basement_zones:
                    equip_rows = (
                        sb.table("equipment")
                        .select("id, code, location, operating_data")
                        .eq("site_id", site_uuid)
                        .execute()
                    ).data
                    basement_temps = _zone_temps_from_equipment(equip_rows, basement_zones)

                if l0_zones:
                    equip_rows = (
                        sb.table("equipment")
                        .select("id, code, location, operating_data")
                        .eq("site_id", site_uuid)
                        .execute()
                    ).data
                    l0_temps = _zone_temps_from_equipment(equip_rows, l0_zones)

                basement_temp = basement_temps[0] if basement_temps else None
                l0_avg = sum(l0_temps) / len(l0_temps) if l0_temps else None

                global _fallback_poll_count, _cooling_drift_last_met
                _fallback_poll_count += 1

                cooling_drift_now = basement_temp is not None and l0_avg is not None and basement_temp > l0_avg + 1.0
                sustained = _fallback_poll_count if (cooling_drift_now and _cooling_drift_last_met) else 0
                if cooling_drift_now:
                    _cooling_drift_last_met = True
                else:
                    _cooling_drift_last_met = False
                    _fallback_poll_count = 0

                result["basement_temp_c"] = basement_temp
                result["l0_avg_temp_c"] = l0_avg
                result["sustained_polls"] = sustained
        except Exception as exc:
            logger.debug("Zone temperature block failed for %s: %s", site_id, exc)

        # ── Chiller cycling — count staging_state changes in last 30 min ───────
        thirty_min_ago = (datetime.now(tz=UTC) - timedelta(minutes=30)).isoformat()
        chiller_rows = sb.table("equipment").select("id").eq("site_id", site_uuid).eq("type", "chiller").execute().data
        if chiller_rows:
            chiller_ids = [r["id"] for r in chiller_rows]

            staging_rows = (
                sb.table("equipment_sensor_readings")
                .select("sensor_type, value, recorded_at")
                .in_("equipment_id", chiller_ids)
                .eq("sensor_type", "staging_state")
                .gte("recorded_at", thirty_min_ago)
                .order("recorded_at", desc=True)
                .execute()
            ).data

            if staging_rows:
                # Count staging state changes (value transitions)
                values = [float(r["value"]) for r in staging_rows if r.get("value") is not None]
                result["staging_state"] = values[0] if values else None
                # Count direction changes: how many times did staging state toggle?
                changes = sum(1 for i in range(1, len(values)) if values[i] != values[i - 1])
                result["chiller_cycle_rate"] = changes
            else:
                # No recent staging readings — check current operating_data for latest value
                chiller_data = (
                    sb.table("equipment")
                    .select("operating_data")
                    .eq("site_id", site_uuid)
                    .eq("type", "chiller")
                    .limit(1)
                    .execute()
                ).data
                if chiller_data:
                    od = chiller_data[0].get("operating_data", {})
                    staging_od = od.get("staging_state", {})
                    if isinstance(staging_od, dict):
                        result["staging_state"] = staging_od.get("value")
                    elif isinstance(staging_od, (int, float)):
                        result["staging_state"] = float(staging_od)

        # ── Load trending — total_kw from site_aggregate sensor readings ─────
        thirty_min_ago = (datetime.now(tz=UTC) - timedelta(minutes=30)).isoformat()
        site_agg_row = (
            sb.table("equipment").select("id").eq("site_id", site_uuid).ilike("code", "%SITE-AGG%").limit(1).execute()
        ).data

        total_kw: float | None = None
        if site_agg_row:
            site_agg_id = site_agg_row[0]["id"]
            kw_rows = (
                sb.table("equipment_sensor_readings")
                .select("sensor_type, value, recorded_at")
                .eq("equipment_id", site_agg_id)
                .eq("sensor_type", "total_kw")
                .gte("recorded_at", thirty_min_ago)
                .order("recorded_at", desc=True)
                .execute()
            ).data

            if kw_rows:
                # Get latest total_kw
                latest = kw_rows[0].get("value")
                if latest is not None:
                    total_kw = float(latest)
                    result["total_kw"] = total_kw

                # Compute trending: 3+ readings, all deltas positive
                if len(kw_rows) >= 3:
                    vals = [float(r["value"]) for r in kw_rows if r.get("value") is not None]
                    if len(vals) >= 3:
                        deltas = [vals[i] - vals[i + 1] for i in range(len(vals) - 1)]
                        result["load_trending_up"] = all(d > 0 for d in deltas)
                    else:
                        result["load_trending_up"] = False
                else:
                    result["load_trending_up"] = False

                # High load: above 85% of 300kW capacity
                if total_kw is not None:
                    result["load_high"] = total_kw > (_CAPACITY_KW * _LOAD_HIGH_THRESHOLD)

    except Exception as exc:
        logger.debug("Could not fetch fallback telemetry for %s: %s", site_id, exc)

    return result


def build_building_state_payload(
    site_id: str,
    issue_service: CockpitIssueFusionService | None = None,
    operating_mode: SentinelOperatingMode | None = None,
) -> BuildingStatePayload:
    resolved_mode = operating_mode or resolve_site_operating_mode(site_id)
    telemetry = _fetch_fallback_telemetry(site_id)
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
