"""
Cockpit Decision API (Phase 172-05).

GET /api/cockpit/decision/{site_id}
  Returns site-aware CockpitDecisionPayload for decision surface rendering.

  v1: Deterministic stub logic (site-aware fixtures, no real intelligence sourcing)
  v2: Real intelligence integration (recommendations, urgency, posture, asset context)

  Response shape is locked and final. Internal sourcing will change v1→v2, not shape.
  Supports deployment modes: ghost, advisory, supervised, autonomous.
  Supports calm buildings (no active decision).

  Target: < 200ms latency, all nullable fields present.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.cockpit_policy_resolution import resolve_cockpit_contract

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cockpit", tags=["cockpit"])


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
# Site fixture logic (v1: deterministic stub)
# ---------------------------------------------------------------------------


def _build_stub_payload_for_site(site_id: str) -> CockpitDecisionPayload | None:
    """
    v1 site-aware stub logic.

    Returns deterministic payload based on site_id.
    No database queries, no ML, no real intelligence—just fixtures.

    This is the contract verification layer.
    When v2 replaces this with real data, the shape stays identical.
    """

    if site_id == "S002":
        # Fairlands: active advisory decision (one stub recommendation)
        return _attach_resolved_contract(
            CockpitDecisionPayload(
                building_id="S002",
                alert_text="Executive boardroom cooling resilience is slipping.",
                reasoning_summary=(
                    "Compressor load is rising while boardroom thermal drift accelerates. "
                    "Start standby cooling before the next occupied meeting window."
                ),
                active_posture="comfort_priority",
                time_to_discomfort=12,
                time_confidence="declining",
                estimated_impact=(
                    "Boardroom comfort will breach during the next occupied window and plant stress is rising."
                ),
                recommended_action="Start standby chiller and inspect the lead compressor train.",
                urgency_score=0.78,
                urgency_components={
                    "comfort": 0.42,
                    "asset_risk": 0.24,
                    "cost": 0.12,
                },
                affected_zone_ids=["Zone-L4-Boardroom-A", "Zone-L4-Boardroom-B"],
                primary_asset_id="S002-CHILLER-B1-001",
                building_metadata={
                    "deployment_mode": "advisory",
                },
            )
        )

    # All other sites: calm building (no active decision, null payload)
    # This is the fallback state frontend expects.
    return None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/decision/{site_id}")
async def get_cockpit_decision(site_id: str) -> dict[str, Any]:
    """
    Get cockpit decision payload for a site.

    Path Parameters:
        site_id: Building identifier (e.g., S002)

    Returns:
        Cockpit decision payload (shape: CockpitDecisionPayload).
        If no active decision, returns null payload (null fields in response).

    Response shape:
        {
            "payload": CockpitDecisionPayload | None,
            "site_id": string,
            "fetched_at": ISO8601 datetime,
        }

    v1 behavior:
        - S002: Active advisory decision with HVAC stub alert
        - Other sites: Null payload (calm building, no decision)
        - Missing site: null payload (treats as calm)

    v2 will replace internal logic with:
        - Query active recommendations for site
        - Compute urgency from equipment health + telemetry
        - Resolve deployment posture from site config
        - Map affected zones/assets from equipment registry
        Same response shape, real intelligence inside.
    """

    # Site existence not validated in v1 (no database query).
    # v2 will validate against buildings table.
    payload = _build_stub_payload_for_site(site_id)

    return {
        "payload": payload,
        "site_id": site_id,
        "fetched_at": datetime.now(UTC).isoformat(),
    }
