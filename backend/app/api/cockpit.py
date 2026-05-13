"""
Cockpit Decision API (Phase 207 — v2).

GET /api/cockpit/decision/{site_id}
  Real intelligence integration — replaces v1 stubs.
  Sources active recommendations, equipment health, and site profile.
  Phase-gated: calm building, advisory read-only, supervised approve decision.

POST /api/cockpit/decision/approve/{site_id}
  Wired through ApprovalService — real execution, not stub.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.cockpit_policy_resolution import resolve_cockpit_contract
from app.services.site_operating_mode_service import resolve_site_operating_mode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cockpit", tags=["cockpit"])


# ---------------------------------------------------------------------------
# CockpitDecisionPayload — Final contract (locked between v1 and v2)
# ---------------------------------------------------------------------------


class CockpitRiskResolution(BaseModel):
    """Backend-resolved risk semantics for cockpit rendering."""

    score: float
    """0-1 resolved risk score."""

    band: Literal["low", "medium", "high", "critical"]
    """Resolved risk band from threshold policy."""

    reason: str
    """Explainable reason for the current risk interpretation."""

    policy_source: str
    """Threshold policy source used for this interpretation."""

    policy_level: Literal["site_asset_criticality", "site_asset", "site", "posture", "system"]
    """Resolution layer that produced the active policy."""

    constraint_type: Literal["comfort", "asset", "cost", "compliance"]
    """Primary operational constraint driving risk interpretation."""

    time_to_constraint_breach_min: int | None = None
    """Minutes until the active constraint is expected to breach."""

    affected_scope: dict[str, Any]
    """Resolved impact scope for zones, assets, and estimated occupants."""


class CockpitHealthResolution(BaseModel):
    """Backend-resolved health semantics for cockpit rendering."""

    score: float
    """0-1 health score."""

    state: Literal["healthy", "stable", "watch", "degraded", "critical"]
    """Simple health state for the current contract slice."""

    trend: Literal["improving", "flat", "declining", "volatile"]
    """Simple health trend for the current contract slice."""

    reason: str
    """Explainable reason for the current health interpretation."""

    asset_class: str
    """Resolved asset class for the health interpretation."""

    criticality: Literal["low", "medium", "high", "mission_critical"]
    """Resolved asset criticality used for health interpretation."""


class CockpitDecisionPayload(BaseModel):
    """
    Complete payload shape for cockpit decision surface rendering.

    All fields support null (for calm buildings, missing context, etc).
    Frontend mapCockpitState will use these nulls to trigger fallback states.

    This shape does NOT change between v1 (stub) and v2 (real intelligence).
    """

    building_id: str
    """Site ID (e.g., S002)."""

    alert_text: str | None = None
    """Plain-language alert summary (null = no active alert)."""

    reasoning_summary: str | None = None
    """Why SENTINEL made this decision (diagnostic context for operator)."""

    active_posture: str | None = None
    """Deployment posture: 'advisory', 'supervised', 'autonomous', 'ghost'."""

    time_to_discomfort: int | None = None
    """Minutes until comfort threshold breached (null = not computed)."""

    time_confidence: str | int | None = None
    """Confidence label: 'stable', 'declining', 'critical' or score 0-1."""

    estimated_impact: Any | None = None
    """Projected impact of inaction (cost, energy, comfort, compliance)."""

    recommended_action: str | None = None
    """Operator-facing action prompt (null = monitor only)."""

    urgency_score: float | None = None
    """0-1 urgency score interpreted by frontend threshold policy."""

    urgency_components: dict[str, float] | None = None
    """Decomposed urgency: {'comfort': 0.1, 'asset_risk': 0.2, 'cost': 0.3}, etc."""

    affected_zone_ids: list[str] | None = None
    """Zone IDs with active conditions (null = site-wide, [] = no zones)."""

    primary_asset_id: str | None = None
    """Equipment ID if decision is equipment-centric (null = site-level)."""

    building_metadata: dict[str, Any] | None = None
    """Site config: {'deployment_mode': 'advisory', ...}."""

    risk: CockpitRiskResolution | None = None
    """Backend-resolved cockpit risk interpretation."""

    health: CockpitHealthResolution | None = None
    """Backend-resolved cockpit health summary."""


def _attach_resolved_contract(payload: CockpitDecisionPayload) -> CockpitDecisionPayload:
    """
    Attach backend-resolved risk and health semantics to the cockpit payload.

    This keeps stub sourcing in place while moving richer policy and health meaning
    into the backend contract.
    """

    resolved = resolve_cockpit_contract(
        site_id=payload.building_id,
        primary_asset_id=payload.primary_asset_id,
        affected_zone_ids=payload.affected_zone_ids,
        active_posture=payload.active_posture,
        urgency_score=payload.urgency_score or 0.0,
        time_to_constraint_breach_min=payload.time_to_discomfort,
        time_confidence=payload.time_confidence,
        reasoning_summary=payload.reasoning_summary,
        urgency_components=payload.urgency_components,
    )

    payload.risk = CockpitRiskResolution(
        score=resolved.risk.score,
        band=resolved.risk.band,
        reason=resolved.risk.reason,
        policy_source=resolved.risk.policy_source,
        policy_level=resolved.risk.policy_level,
        constraint_type=resolved.risk.constraint_type,
        time_to_constraint_breach_min=resolved.risk.time_to_constraint_breach_min,
        affected_scope={
            "zones": resolved.risk.affected_scope.zones,
            "assets": resolved.risk.affected_scope.assets,
            "occupants_estimate": resolved.risk.affected_scope.occupants_estimate,
        },
    )
    payload.health = CockpitHealthResolution(
        score=resolved.health.score,
        state=resolved.health.state,
        trend=resolved.health.trend,
        reason=resolved.health.reason,
        asset_class=resolved.health.asset_class,
        criticality=resolved.health.criticality,
    )
    return payload


# ---------------------------------------------------------------------------
# v2: Real data sourcing
# ---------------------------------------------------------------------------


async def _fetch_site_phase(site_id: str) -> str:
    """Fetch onboarding phase from Supabase."""
    try:
        from app.database.supabase_client import get_supabase_client
        client = get_supabase_client()
        row = client.table("sites").select("onboarding_phase").eq("code", site_id).limit(1).execute()
        if row.data:
            return row.data[0].get("onboarding_phase") or "commissioning"
    except Exception as exc:
        logger.debug("Could not fetch onboarding_phase for %s: %s", site_id, exc)
    return "commissioning"


async def _fetch_active_recommendation(site_id: str) -> dict | None:
    """Fetch the highest-priority pending recommendation for a site."""
    try:
        from app.database.repositories.recommendation_repository import RecommendationRepository
        repo = RecommendationRepository()
        recs = await repo.get_by_status(site_id, status="pending", limit=1)
        if recs:
            return recs[0].to_dict()
    except Exception as exc:
        logger.debug("Could not fetch recommendations for %s: %s", site_id, exc)
    return None


async def _fetch_recent_health_snapshots(site_id: str, limit: int = 5) -> list[dict]:
    """Fetch recent health snapshots for urgency computation."""
    try:
        from app.database.supabase_client import get_supabase_client
        client = get_supabase_client()
        rows = client.table("asset_health_snapshots").select("*").eq("site_id", site_id).order("created_at", desc=True).limit(limit).execute()
        return rows.data or []
    except Exception as exc:
        logger.debug("Could not fetch health snapshots for %s: %s", site_id, exc)
    return []


def _compute_urgency(recommendation: dict | None, health_snapshots: list[dict], profile: str) -> dict:
    """Compute urgency score from recommendation risk, health data, and profile."""
    urgency_score = 0.0
    components: dict[str, float] = {"comfort": 0.0, "asset_risk": 0.0, "cost": 0.0}

    if not recommendation:
        return {"score": urgency_score, "components": components}

    # Risk level contributes base urgency
    risk_map = {"low": 0.2, "medium": 0.5, "high": 0.75, "critical": 0.95}
    base = risk_map.get(recommendation.get("risk_level", "medium"), 0.5)
    urgency_score = base

    # Profile weights shift urgency components
    if profile == "comfort":
        components["comfort"] = base * 0.5
        components["asset_risk"] = base * 0.25
        components["cost"] = base * 0.25
    elif profile == "cost_saving":
        components["comfort"] = base * 0.15
        components["asset_risk"] = base * 0.25
        components["cost"] = base * 0.6
    elif profile == "asset_preservation":
        components["comfort"] = base * 0.1
        components["asset_risk"] = base * 0.6
        components["cost"] = base * 0.3
    else:  # balanced
        components = {"comfort": base * 0.33, "asset_risk": base * 0.33, "cost": base * 0.34}

    # Health data boosts asset_risk if equipment health is declining
    if health_snapshots:
        low_health_count = sum(1 for h in health_snapshots if (h.get("health_score") or 100) < 60)
        if low_health_count > 0:
            boost = min(low_health_count * 0.05, 0.2)
            components["asset_risk"] = min(components["asset_risk"] + boost, 1.0)
            urgency_score = min(urgency_score + boost * 0.5, 1.0)

    return {"score": round(urgency_score, 2), "components": {k: round(v, 2) for k, v in components.items()}}


async def _build_v2_payload_for_site(site_id: str) -> CockpitDecisionPayload | None:
    """
    v2: Build cockpit payload from real data sources.

    Phase-gating:
      - commissioning/shadow_live → null (calm building)
      - advisory → read-only recommendation
      - supervised → approve-able recommendation
    """
    phase = await _fetch_site_phase(site_id)

    # Phase gate: calm building for early phases
    if phase in ("commissioning", "shadow_live"):
        return None

    # Fetch real recommendation + health context
    recommendation = await _fetch_active_recommendation(site_id)
    health_snapshots = await _fetch_recent_health_snapshots(site_id)
    profile = resolve_site_operating_mode(site_id)

    if not recommendation:
        return None

    # Build urgency from recommendation + health + profile
    urgency = _compute_urgency(recommendation, health_snapshots, profile)

    # Map deployment posture from phase
    posture_map = {
        "advisory": "advisory",
        "supervised": "supervised",
        "automatic": "autonomous",
    }
    deployment_mode = posture_map.get(phase, "advisory")

    # Determine confidence label
    confidence = recommendation.get("confidence", "medium")
    confidence_map = {"high": "stable", "medium": "stable", "low": "declining"}
    time_confidence = confidence_map.get(confidence, "stable")

    # Extract impacted zones + equipment
    target = recommendation.get("target_equipment", "")
    meta = recommendation.get("metadata", {})
    affected_zone_ids = meta.get("affected_zones", []) if isinstance(meta, dict) else []

    payload = CockpitDecisionPayload(
        building_id=site_id,
        alert_text=recommendation.get("reason", ""),
        reasoning_summary=recommendation.get("reason", ""),
        active_posture=deployment_mode,
        time_to_discomfort=None,
        time_confidence=time_confidence,
        estimated_impact=recommendation.get("expected_impact"),
        recommended_action=f"Apply recommendation: {recommendation.get('action_type', '')} on {target}",
        urgency_score=urgency["score"],
        urgency_components=urgency["components"],
        affected_zone_ids=affected_zone_ids or None,
        primary_asset_id=target or None,
        building_metadata={
            "deployment_mode": deployment_mode,
            "profile": profile,
            "recommendation_id": recommendation.get("id", ""),
        },
    )

    return _attach_resolved_contract(payload)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/decision/{site_id}")
async def get_cockpit_decision(site_id: str) -> dict[str, Any]:
    """
    Get cockpit decision payload for a site (v2).

    Sources real recommendations, phase-gates output, and computes
    urgency from health data + profile settings.

    Phase gating:
      - commissioning/shadow_live → null payload (calm building)
      - advisory → decision payload with read-only recommendations
      - supervised → decision payload with approve-able action
      - automatic → decision payload showing auto-applied state
    """
    payload = await _build_v2_payload_for_site(site_id)
    return {
        "payload": payload,
        "site_id": site_id,
        "fetched_at": datetime.now(UTC).isoformat(),
    }


@router.post("/decision/approve/{site_id}", status_code=202)
async def approve_cockpit_decision(site_id: str) -> dict[str, Any]:
    """
    Operator approval for supervised-mode cockpit action (v2).

    Validates phase ≥ supervised, fetches active recommendation, routes
    through ApprovalService, persists parasite_decision, returns execution_id.

    Returns 202 Accepted — action is queued, not yet verified.
    """
    accepted_at = datetime.now(UTC).isoformat()

    # Phase gate: require supervised+
    phase = await _fetch_site_phase(site_id)
    if phase not in ("supervised", "automatic"):
        logger.warning("Cockpit approve rejected: phase %s < supervised for %s", phase, site_id)
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve: site is in '{phase}' phase. Supervised or automatic required.",
        )

    # Fetch active recommendation
    recommendation = await _fetch_active_recommendation(site_id)
    if not recommendation:
        logger.warning("Cockpit approve rejected: no pending recommendation for %s", site_id)
        raise HTTPException(
            status_code=404,
            detail="No pending recommendation found for this site.",
        )

    rec_id = recommendation.get("id", "")
    if not rec_id:
        raise HTTPException(status_code=500, detail="Recommendation has no ID")

    try:
        from app.services.approval_service import ApprovalService

        approval_svc = ApprovalService()
        result = await approval_svc.execute_approval(
            recommendation_id=rec_id,
            approved_by="cockpit_operator",
            approval_notes="Approved via cockpit hold-to-confirm",
        )
    except Exception as exc:
        logger.error("Cockpit approve failed for %s: %s", site_id, exc)
        raise HTTPException(status_code=500, detail=f"Approval execution failed: {exc}") from exc

    return {
        "accepted": True,
        "site_id": site_id,
        "accepted_at": accepted_at,
        "recommendation_id": rec_id,
        "execution_status": result.status if hasattr(result, "status") else "executed",
        "correlation_id": recommendation.get("correlation_id", ""),
    }
