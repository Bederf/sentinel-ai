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
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.settings import load_settings

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


class CockpitHealthResolution(BaseModel):
    """Backend-resolved health semantics for cockpit rendering."""

    score: float
    """0-1 health score."""

    state: Literal["stable", "watch", "degraded"]
    """Simple health state for the current contract slice."""

    trend: Literal["improving", "flat", "declining"]
    """Simple health trend for the current contract slice."""


class CockpitDecisionPayload(BaseModel):
    """
    Complete payload shape for cockpit decision surface rendering.

    All fields support null (for calm buildings, missing context, etc).
    Frontend mapCockpitState will use these nulls to trigger fallback states.

    This shape does NOT change between v1 (stub) and v2 (real intelligence).
    """

    building_id: str
    """Site ID (e.g., S002)."""

    alert_text: Optional[str] = None
    """Plain-language alert summary (null = no active alert)."""

    reasoning_summary: Optional[str] = None
    """Why SENTINEL made this decision (diagnostic context for operator)."""

    active_posture: Optional[str] = None
    """Deployment posture: 'advisory', 'supervised', 'autonomous', 'ghost'."""

    time_to_discomfort: Optional[int] = None
    """Minutes until comfort threshold breached (null = not computed)."""

    time_confidence: Optional[str | int] = None
    """Confidence label: 'stable', 'declining', 'critical' or score 0-1."""

    estimated_impact: Optional[Any] = None
    """Projected impact of inaction (cost, energy, comfort, compliance)."""

    recommended_action: Optional[str] = None
    """Operator-facing action prompt (null = monitor only)."""

    urgency_score: Optional[float] = None
    """0-1 urgency score interpreted by frontend threshold policy."""

    urgency_components: Optional[dict[str, float]] = None
    """Decomposed urgency: {'comfort': 0.1, 'asset_risk': 0.2, 'cost': 0.3}, etc."""

    affected_zone_ids: Optional[list[str]] = None
    """Zone IDs with active conditions (null = site-wide, [] = no zones)."""

    primary_asset_id: Optional[str] = None
    """Equipment ID if decision is equipment-centric (null = site-level)."""

    building_metadata: Optional[dict[str, Any]] = None
    """Site config: {'deployment_mode': 'advisory', ...}."""

    risk: Optional[CockpitRiskResolution] = None
    """Backend-resolved cockpit risk interpretation."""

    health: Optional[CockpitHealthResolution] = None
    """Backend-resolved cockpit health summary."""


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _resolve_threshold_policy_source() -> tuple[dict[str, int], dict[str, int], str]:
    """Load threshold settings for cockpit interpretation."""

    defaults = (
        {"healthy": 80, "warning": 60, "critical": 0},
        {"medium": 31, "high": 61, "critical": 81},
        "global.default",
    )

    try:
        settings = load_settings()
        return (
            settings.get("healthThresholds", defaults[0]),
            settings.get("riskThresholds", defaults[1]),
            "global.settings",
        )
    except Exception:
        logger.exception("Failed to load cockpit threshold policy; using defaults")
        return defaults


def _risk_band_from_score(score: float, thresholds: dict[str, int]) -> Literal["low", "medium", "high", "critical"]:
    score_percent = round(_clamp01(score) * 100)
    if score_percent >= thresholds["critical"]:
        return "critical"
    if score_percent >= thresholds["high"]:
        return "high"
    if score_percent >= thresholds["medium"]:
        return "medium"
    return "low"


def _build_risk_reason(
    payload: CockpitDecisionPayload,
    score: float,
    band: Literal["low", "medium", "high", "critical"],
    thresholds: dict[str, int],
) -> str:
    score_percent = round(_clamp01(score) * 100)
    if payload.reasoning_summary:
        return payload.reasoning_summary
    if band == "critical":
        return f"Resolved risk {score_percent} is above the critical threshold of {thresholds['critical']}."
    if band == "high":
        return f"Resolved risk {score_percent} is above the high threshold of {thresholds['high']}."
    if band == "medium":
        return f"Resolved risk {score_percent} is above the medium threshold of {thresholds['medium']}."
    return f"Resolved risk {score_percent} remains below the medium threshold of {thresholds['medium']}."


def _resolve_health_state(score: float, thresholds: dict[str, int]) -> Literal["stable", "watch", "degraded"]:
    score_percent = round(_clamp01(score) * 100)
    if score_percent >= thresholds["healthy"]:
        return "stable"
    if score_percent >= thresholds["warning"]:
        return "watch"
    return "degraded"


def _resolve_health_trend(urgency_score: float) -> Literal["improving", "flat", "declining"]:
    if urgency_score >= 0.55:
        return "declining"
    if urgency_score <= 0.2:
        return "improving"
    return "flat"


def _attach_resolved_contract(payload: CockpitDecisionPayload) -> CockpitDecisionPayload:
    """
    Attach backend-resolved risk and health semantics to the cockpit payload.

    This is the first narrow contract step. It still uses current stub sourcing and
    urgency-derived values, but moves interpretation ownership into the backend.
    """

    health_thresholds, risk_thresholds, policy_source = _resolve_threshold_policy_source()
    urgency_score = _clamp01(payload.urgency_score or 0.0)
    health_score = _clamp01(1.0 - (urgency_score * 0.2))
    risk_band = _risk_band_from_score(urgency_score, risk_thresholds)

    payload.risk = CockpitRiskResolution(
        score=urgency_score,
        band=risk_band,
        reason=_build_risk_reason(payload, urgency_score, risk_band, risk_thresholds),
        policy_source=policy_source,
    )
    payload.health = CockpitHealthResolution(
        score=health_score,
        state=_resolve_health_state(health_score, health_thresholds),
        trend=_resolve_health_trend(urgency_score),
    )
    return payload


# ---------------------------------------------------------------------------
# Site fixture logic (v1: deterministic stub)
# ---------------------------------------------------------------------------


def _build_stub_payload_for_site(site_id: str) -> Optional[CockpitDecisionPayload]:
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
                alert_text="Zone B1-001 is drifting toward discomfort.",
                reasoning_summary=(
                    "Pressure drop is 18% above baseline while flow stays flat. "
                    "Check the valve before comfort starts slipping."
                ),
                active_posture="advisory",
                time_to_discomfort=240,  # 4 hours
                time_confidence="declining",
                estimated_impact="Comfort margin is tightening and energy waste is rising.",
                recommended_action=(
                    "Inspect and clean the Zone B1-001 valve now. If fouling remains, schedule water treatment."
                ),
                urgency_score=0.62,
                urgency_components={
                    "comfort": 0.25,
                    "asset_risk": 0.20,
                    "cost": 0.17,
                },
                affected_zone_ids=["Zone-B1-001"],
                primary_asset_id="S002-VAV-101",
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
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
