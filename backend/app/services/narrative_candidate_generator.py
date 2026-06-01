"""Deterministic candidate generation for cockpit building narratives."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from app.schemas.cockpit import CockpitIssue, CockpitSourceStatus
from app.services.building_state_models import NarrativeCandidate, NarrativeLocation, PropagationDirection, Voice
from app.services.cockpit_issue_fusion import CockpitIssueFusionService
from app.services.site_operating_mode_service import SentinelOperatingMode


def normalize_site_id(site_id: str) -> str:
    normalized = site_id.strip().lower().replace("_", "-")
    if normalized == "s002":
        return "site-002"
    return normalized


def _extract_asset_type(issue: CockpitIssue) -> str | None:
    asset_id = issue.location.asset_ids[0] if issue.location.asset_ids else None
    if not asset_id:
        return None
    parts = asset_id.split("-")
    if len(parts) < 2:
        return None
    return parts[1].upper()


def _mode_adjusted_hvac_voice(issue: CockpitIssue, operating_mode: SentinelOperatingMode) -> Voice:
    if issue.issue_category == "thermal":
        return "comfort_stress"
    if issue.issue_category == "energy":
        return "energy_pressure"
    if issue.issue_category == "stability":
        return "operational_stability"
    if issue.issue_category == "occupant":
        return "occupant_friction"

    if operating_mode == "asset_preservation":
        return "asset_stress"
    if operating_mode == "cost_saving":
        return "energy_pressure"
    return "comfort_stress"


def _voice_from_issue(issue: CockpitIssue, operating_mode: SentinelOperatingMode) -> Voice:
    asset_type = _extract_asset_type(issue)
    is_hvac_asset = asset_type in {"CHILLER", "AHU", "FCU", "VAV", "PUMP", "CT"}
    should_apply_mode_bias = issue.issue_category not in {"thermal", "energy", "stability", "occupant"} and (
        issue.subsystem == "hvac" or is_hvac_asset
    )
    if should_apply_mode_bias:
        return _mode_adjusted_hvac_voice(issue, operating_mode)

    if issue.constraint_type == "comfort":
        return "comfort_stress"
    if issue.constraint_type == "asset":
        return "asset_stress"
    if issue.constraint_type == "energy":
        return "energy_pressure"
    if issue.constraint_type == "occupant":
        return "occupant_friction"
    if issue.constraint_type == "stability":
        return "operational_stability"

    if issue.issue_category == "thermal":
        return "comfort_stress"
    if issue.issue_category == "fault":
        return "asset_stress"
    if issue.issue_category == "energy":
        return "energy_pressure"
    if issue.issue_category == "occupant":
        return "occupant_friction"
    if issue.issue_category == "stability":
        return "operational_stability"

    if issue.subsystem == "hvac":
        return _mode_adjusted_hvac_voice(issue, operating_mode)
    if issue.subsystem == "power":
        return "energy_pressure"
    if issue.subsystem == "occupancy":
        return "occupant_friction"

    zone_count = len(issue.location.zone_ids)

    if issue.source == "tech" and zone_count > 0 and not issue.location.asset_ids:
        return "occupant_friction"
    if asset_type in {"CHILLER", "AHU", "FCU", "VAV", "PUMP", "CT"}:
        return _mode_adjusted_hvac_voice(issue, operating_mode)
    if asset_type in {"GEN", "UPS"}:
        return "asset_stress"
    if zone_count >= 2 and not issue.location.asset_ids:
        return "comfort_stress"

    text = " ".join(
        [
            issue.title or "",
            issue.summary or "",
            issue.impact_summary or "",
            issue.cause_hypothesis or "",
        ]
    ).lower()

    if any(token in text for token in ("comfort", "thermal", "cool", "heating", "temperature", "drift")):
        return "comfort_stress"
    if any(token in text for token in ("unstable", "stability", "cycling", "oscillation", "volatile")):
        return "operational_stability"
    if any(token in text for token in ("asset", "compressor", "chiller", "ahu", "equipment", "failure", "fault")):
        return "asset_stress"
    if any(token in text for token in ("occupant", "meeting", "complaint", "friction")):
        return "occupant_friction"
    return "energy_pressure"


def _propagation_from_issue(issue: CockpitIssue) -> PropagationDirection:
    if len(issue.location.zone_ids) >= 3:
        return "building_wide"

    text = " ".join([issue.summary or "", issue.impact_summary or "", issue.cause_hypothesis or ""]).lower()
    if "upward" in text or "rising" in text or "spread" in text:
        return "upward"
    if "downward" in text:
        return "downward"
    if "building wide" in text or "building-wide" in text or "campus" in text:
        return "building_wide"
    if len(issue.location.zone_ids) > 1:
        return "lateral"
    return "contained"


def _time_to_breach_from_issue(issue: CockpitIssue) -> int | None:
    if issue.sla_due_at is not None:
        due_at = issue.sla_due_at
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=UTC)
        minutes = max(1, int((due_at - datetime.now(UTC)).total_seconds() // 60))
        return minutes

    if issue.severity == "critical":
        return 12
    if issue.severity == "high":
        return 18
    if issue.severity == "medium":
        return 30
    return 45


def _criticality_from_issue(issue: CockpitIssue) -> float:
    asset_type = _extract_asset_type(issue)
    if asset_type in {"CHILLER", "GEN", "UPS"}:
        return 0.95 if issue.severity in {"critical", "high"} else 0.78
    if asset_type in {"AHU", "FCU", "VAV", "PUMP", "CT"}:
        return 0.82 if issue.severity in {"critical", "high"} else 0.62
    if issue.severity == "critical":
        return 0.95
    if issue.severity == "high":
        return 0.8
    if issue.severity == "medium":
        return 0.6
    return 0.35


def _propagation_risk_from_issue(issue: CockpitIssue) -> float:
    zone_count = len(issue.location.zone_ids)
    if issue.location.floor_id and zone_count >= 2:
        return 0.72
    if zone_count >= 3:
        return 0.8
    if zone_count == 2:
        return 0.6
    if zone_count == 1:
        return 0.35
    return 0.2


def _candidate_from_issue(issue: CockpitIssue, operating_mode: SentinelOperatingMode) -> NarrativeCandidate:
    affected_zones = [zone_id for zone_id in issue.location.zone_ids if zone_id]
    epicenter = (
        issue.location.floor_id
        or (affected_zones[0] if affected_zones else None)
        or (issue.location.asset_ids[0] if issue.location.asset_ids else None)
        or "building"
    )

    message = issue.impact_summary or issue.summary or issue.title
    action = issue.recommended_action or "Investigate the dominant building tension."

    return NarrativeCandidate(
        candidate_id=issue.id,
        voice=_voice_from_issue(issue, operating_mode),
        message=message,
        location=NarrativeLocation(
            epicenter=epicenter,
            affected=affected_zones[1:] if epicenter in affected_zones else affected_zones,
            propagation=_propagation_from_issue(issue),
        ),
        action=action,
        time_to_constraint_breach_min=_time_to_breach_from_issue(issue),
        affected_occupants_est=len(affected_zones) * 12
        if affected_zones
        else (8 if issue.source == "tech" and affected_zones else None),
        system_criticality=_criticality_from_issue(issue),
        propagation_risk=_propagation_risk_from_issue(issue),
        resolved=issue.status == "resolved",
        spatially_grounded=bool(issue.location.floor_id or issue.location.zone_ids or issue.location.asset_ids),
        eroding_margin=issue.severity in {"critical", "high"},
    )


def _fallback_candidates_for_site(
    site_id: str,
    telemetry: dict[str, Any] | None = None,
) -> list[NarrativeCandidate]:
    """Return fallback candidates only when real telemetry confirms conditions.

    Gating logic:
      - cooling_drift: fires only when basement zone temp > L0 avg + 1.0°C
        AND this condition has been observed in 2+ consecutive polls (sustained).
      - chiller_cycling / load_compensation: always available as fallback.
    """
    canonical_site_id = normalize_site_id(site_id)

    if canonical_site_id != "site-002":
        return []

    t = telemetry or {}

    # ── cooling drift gate ────────────────────────────────────────────────────
    basement_temp = t.get("basement_temp_c")
    l0_avg_temp = t.get("l0_avg_temp_c")
    sustained_polls = t.get("sustained_polls", 0)

    cooling_drift_candidate: NarrativeCandidate | None = None
    if basement_temp is not None and l0_avg_temp is not None:
        if basement_temp > l0_avg_temp + 1.0 and sustained_polls >= 2:
            cooling_drift_candidate = NarrativeCandidate(
                candidate_id="comfort-s002-b1-upward-drift",
                voice="comfort_stress",
                message="Cooling drift is spreading upward from the basement plant.",
                location=NarrativeLocation(
                    epicenter="B1",
                    affected=["L0", "L1"],
                    propagation="upward",
                ),
                action="Prepare standby cooling.",
                time_to_constraint_breach_min=18,
                affected_occupants_est=42,
                system_criticality=0.88,
                propagation_risk=0.74,
                eroding_margin=True,
            )

    # ── chiller cycling gate ─────────────────────────────────────────────────
    # Fires when staging_state transitions > 2 in last 30 min (chiller starts/stops).
    # Also fires when elevated staging (no quiet baseline).
    chiller_cycle_rate = t.get("chiller_cycle_rate", 0)
    staging_state = t.get("staging_state")
    chiller_cycling_candidate: NarrativeCandidate | None = None
    if chiller_cycle_rate > 2 or (staging_state is not None and staging_state > 0):
        chiller_cycling_candidate = NarrativeCandidate(
            candidate_id="stability-s002-chiller-cycling",
            voice="operational_stability",
            message="Chiller cycling margin is tightening around the plant transition.",
            location=NarrativeLocation(
                epicenter="B1",
                affected=["B1", "L0"],
                propagation="contained",
            ),
            action="Stabilize plant staging before the next load step.",
            time_to_constraint_breach_min=24,
            affected_occupants_est=18,
            system_criticality=0.91,
            propagation_risk=0.52,
            eroding_margin=True,
        )

    # ── load compensation gate ──────────────────────────────────────────────
    # Fires when load is trending upward (3+ consecutive positive deltas)
    # OR when current load > 85% of site capacity.
    load_trending_up = t.get("load_trending_up", False)
    load_high = t.get("load_high", False)
    load_compensation_candidate: NarrativeCandidate | None = None
    if load_trending_up or load_high:
        load_compensation_candidate = NarrativeCandidate(
            candidate_id="energy-s002-compensation-load",
            voice="energy_pressure",
            message="Load is rising as the building compensates.",
            location=NarrativeLocation(
                epicenter="B1",
                affected=["L0", "L1"],
                propagation="upward",
            ),
            action="Watch plant efficiency while compensation remains active.",
            time_to_constraint_breach_min=28,
            affected_occupants_est=24,
            system_criticality=0.45,
            propagation_risk=0.38,
            eroding_margin=False,
        )

    candidates = [
        cooling_drift_candidate,
        chiller_cycling_candidate,
        load_compensation_candidate,
    ]
    return [c for c in candidates if c is not None]


def _build_calm_state_candidate(site_id: str) -> NarrativeCandidate:
    """Return a calm-state candidate when no issues and no fallback conditions are met."""
    return NarrativeCandidate(
        candidate_id=f"calm-{normalize_site_id(site_id).lower()}",
        voice="operational_stability",
        message="All building systems are operating within normal parameters.",
        location=NarrativeLocation(
            epicenter="building",
            affected=[],
            propagation="building_wide",
        ),
        action="Continue monitoring. No action required.",
        time_to_constraint_breach_min=60,
        affected_occupants_est=None,
        system_criticality=0.1,
        propagation_risk=0.05,
        eroding_margin=False,
    )


def _candidate_from_source_health(statuses: Iterable[CockpitSourceStatus]) -> NarrativeCandidate | None:
    degraded = [status for status in statuses if status.state in {"degraded", "stale", "unavailable"}]
    if not degraded:
        return None

    highest = sorted(
        degraded,
        key=lambda status: (
            2 if status.state == "unavailable" else 1 if status.state == "stale" else 0,
            status.freshness_seconds or 0,
        ),
        reverse=True,
    )[0]

    if highest.state == "unavailable":
        message = "Building observability is unavailable. Verify live sources before trusting a calm state."
        breach = 18
        propagation = "building_wide"
        criticality = 0.82
    elif highest.state == "stale":
        message = "Building observability is stale. Validate live sources before trusting the current posture."
        breach = 30
        propagation = "building_wide"
        criticality = 0.68
    else:
        message = "Building observability is degrading. Watch source freshness before acting on a calm reading."
        breach = 45
        propagation = "building_wide"
        criticality = 0.5

    return NarrativeCandidate(
        candidate_id=f"source-health-{highest.source}",
        voice="operational_stability",
        message=message,
        location=NarrativeLocation(
            epicenter="building",
            affected=[],
            propagation=propagation,
        ),
        action="Verify source health and refresh live inputs.",
        time_to_constraint_breach_min=breach,
        affected_occupants_est=None,
        system_criticality=criticality,
        propagation_risk=0.72,
        resolved=False,
        spatially_grounded=True,
        eroding_margin=False,
    )


def generate_narrative_candidates_from_issues(
    issues: Iterable[CockpitIssue],
    operating_mode: SentinelOperatingMode = "comfort",
) -> list[NarrativeCandidate]:
    candidates = [_candidate_from_issue(issue, operating_mode) for issue in issues]
    return [candidate for candidate in candidates if candidate.spatially_grounded]


def generate_narrative_candidates(
    site_id: str,
    issue_service: CockpitIssueFusionService | None = None,
    operating_mode: SentinelOperatingMode = "comfort",
    telemetry: dict[str, Any] | None = None,
) -> list[NarrativeCandidate]:
    service = issue_service or CockpitIssueFusionService()

    try:
        issues, _statuses, _, _ = service.aggregate(site_id)
    except Exception:
        issues = []

    candidates = generate_narrative_candidates_from_issues(issues, operating_mode=operating_mode)
    if candidates:
        return candidates

    fallback_candidates = _fallback_candidates_for_site(site_id, telemetry=telemetry)
    if fallback_candidates:
        return fallback_candidates

    # No issues AND no fallback conditions met → calm state
    return [_build_calm_state_candidate(site_id)]
