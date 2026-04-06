"""
Cockpit Decision API (Phase 172-05).

GET /api/cockpit/decision/{site_id}
  Returns site-aware CockpitDecisionPayload for decision surface rendering.

POST /api/cockpit/decision/approve/{site_id}
  Records operator approval of a cockpit-guided action (Tier 2 supervised mode).

  v1: Stub — logs approval attempt, returns 202.
  v2: Routes through ApprovalService with BOLA gate and full audit trail.

Response shapes are locked and final.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from app.middleware.auth_middleware import AuthContext, require_site_access
from app.schemas.cockpit import (
    CockpitActionAudit,
    CockpitIssue,
    CockpitSourceStatus,
    CockpitActionType,
)
from app.services.approval_service import get_approval_service
from app.services.cockpit_policy_resolution import resolve_cockpit_contract
from app.services.cockpit_issue_fusion import CockpitIssueFusionService
from app.services.recommendation_service import get_recommendation_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cockpit", tags=["cockpit"])
cockpit_issue_service = CockpitIssueFusionService()
_ISSUE_STORE: dict[str, list[CockpitIssue]] = defaultdict(list)
_AUDIT_LOG_STORE: dict[str, list[CockpitActionAudit]] = defaultdict(list)
_ISSUE_SITE_LOOKUP: dict[str, str] = {}


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

    issues: list[CockpitIssue] = Field(default_factory=list)
    selected_issue_id: str | None = None
    source_health: list[CockpitSourceStatus] = Field(default_factory=list)


class CockpitActionRequest(BaseModel):
    """Compatibility action request model for cockpit issue actions."""

    action: CockpitActionType
    actor_id: str
    actor_label: str
    actor_type: Literal["user", "system"] = "user"
    assign_to: str | None = None
    assign_team: str | None = None
    work_order_title: str | None = None
    notes: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class CockpitApprovalResponse(BaseModel):
    """Response contract for POST /api/cockpit/decision/approve/{site_id}."""

    accepted: bool = True
    site_id: str
    accepted_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    recommendation_id: str | None = None
    execution_id: str | None = None
    status: str


def _cache_site_issues(site_id: str, issues: list[CockpitIssue]) -> None:
    _ISSUE_STORE[site_id] = list(issues)
    for issue in issues:
        _ISSUE_SITE_LOOKUP[issue.id] = site_id


def _available_actions(status: str) -> list[str]:
    if status == "new":
        return ["acknowledge", "assign"]
    if status in {"triaged", "in_progress"}:
        return ["assign", "create_work_order", "escalate"]
    return []


def _apply_action(issue: CockpitIssue, request: CockpitActionRequest) -> tuple[str, str, str]:
    status_before = issue.status
    if request.action == "acknowledge":
        issue.status = "triaged"
        issue.updated_at = datetime.now(UTC)
        return "accepted", issue.status, "Issue acknowledged"
    if request.action == "assign":
        if not request.assign_to and not request.assign_team:
            return "rejected", status_before, "assign_to or assign_team required"
        issue.owner = request.assign_to
        if request.assign_team:
            issue.owner_team = request.assign_team
        issue.status = "triaged"
        issue.updated_at = datetime.now(UTC)
        return "accepted", issue.status, "Issue assigned"
    if request.action == "create_work_order":
        if issue.status not in {"triaged", "in_progress"}:
            return "rejected", status_before, "Issue must be triaged or in_progress before work order creation"
        issue.status = "in_progress"
        issue.updated_at = datetime.now(UTC)
        return "accepted", issue.status, "Work order created"
    if request.action == "escalate":
        issue.status = "in_progress"
        issue.updated_at = datetime.now(UTC)
        return "accepted", issue.status, "Issue escalated"
    return "rejected", status_before, "Unsupported action"


def _record_audit(
    issue: CockpitIssue,
    request: CockpitActionRequest,
    result: str,
    status_before: str,
    status_after: str,
    message: str,
) -> CockpitActionAudit:
    audit = CockpitActionAudit(
        id=str(uuid4()),
        issue_id=issue.id,
        action=request.action,
        actor_type=request.actor_type,
        actor_id=request.actor_id,
        actor_label=request.actor_label,
        occurred_at=datetime.now(UTC),
        outcome="success" if result == "accepted" else "rejected",
        status_before=status_before,
        status_after=status_after,
        notes=message,
        evidence_refs=request.evidence_refs,
        work_order_id=str(uuid4()) if request.action == "create_work_order" and result == "accepted" else None,
    )
    site_id = _ISSUE_SITE_LOOKUP.get(issue.id)
    if site_id:
        _AUDIT_LOG_STORE[site_id].append(audit)
    return audit


def _build_cockpit_payload(site_id: str) -> CockpitDecisionPayload | None:
    issues, statuses, _audit, selected_issue_id = cockpit_issue_service.aggregate(site_id, local_audit_entries=[])
    if not issues:
        return None
    cached_issues = {issue.id: issue for issue in _ISSUE_STORE.get(site_id, [])}
    merged_issues = [cached_issues.get(issue.id, issue) for issue in issues]
    _cache_site_issues(site_id, merged_issues)
    selected_issue = next((issue for issue in merged_issues if issue.id == selected_issue_id), merged_issues[0])
    return CockpitDecisionPayload(
        building_id=site_id,
        alert_text=selected_issue.title,
        reasoning_summary=selected_issue.cause_hypothesis or selected_issue.summary,
        active_posture="advisory",
        recommended_action=selected_issue.recommended_action,
        primary_asset_id=(selected_issue.location.asset_ids or [None])[0],
        affected_zone_ids=selected_issue.location.zone_ids or None,
        issues=merged_issues,
        selected_issue_id=selected_issue.id,
        source_health=statuses,
    )


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
                alert_text="Chiller plant load is rising. Upward pressure detected through L0 and L1.",
                reasoning_summary=(
                    "Chiller cycling margin is tightening around the plant transition. "
                    "Load propagation is moving upward through the mechanical riser into Level 1. "
                    "Start standby chiller before the next occupied peak window."
                ),
                active_posture="adaptive_intelligence",
                time_to_discomfort=12,
                time_confidence="declining",
                estimated_impact=(
                    "Comfort will degrade in L0 and L1 occupied zones if chiller cycling continues unchecked."
                ),
                recommended_action="Start standby chiller and inspect the lead compressor train.",
                urgency_score=0.78,
                urgency_components={
                    "comfort": 0.42,
                    "asset_risk": 0.24,
                    "cost": 0.12,
                },
                affected_zone_ids=[
                    "Zone-B1-ChillerPlant",
                    "Zone-L0-MechanicalRiser",
                    "Zone-L1-CeilingVoid",
                ],
                primary_asset_id="S002-CHILLER-B1-001",
                building_metadata={
                    "deployment_mode": "shadow",
                    "floor_stack_order": ["B1", "L0", "L1", "L2", "L3", "L4", "L5", "R"],
                    "floor_labels": {
                        "B1": "Basement",
                        "L0": "Ground",
                        "L1": "Level 1",
                        "L2": "Level 2",
                        "L3": "Level 3",
                        "L4": "Level 4",
                        "L5": "Level 5",
                        "R":  "Roof",
                    },
                },
            )
        )

    # All other sites: calm building (no active decision, null payload)
    # This is the fallback state frontend expects.
    return None


# ---------------------------------------------------------------------------
# Endpoints
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
    payload = _build_cockpit_payload(site_id)

    return {
        "payload": payload,
        "site_id": site_id,
        "fetched_at": datetime.now(UTC).isoformat(),
    }


@router.post("/decision/approve/{site_id}", status_code=status.HTTP_202_ACCEPTED)
async def approve_cockpit_decision(
    request: Request,
    site_id: str,
    auth: AuthContext = Depends(require_site_access("site_id")),
) -> CockpitApprovalResponse:
    """
    Acknowledge and record operator approval of a cockpit-guided action.

    BOLA gate: require_site_access validates the operator has access to site_id
    before any read or write occurs.

    v2 flow:
        1. BOLA gate (require_site_access)
        2. Fetch the most recent PENDING recommendation for site_id
        3. Route through ApprovalService.approve_recommendation()
           with routing_source="cockpit_approval"
        4. Return 202 with execution_id for frontend polling

    Error handling: catches all exceptions, logs at ERROR, returns 202 with
    status="approval_failed". Never propagates a 500 to the cockpit UI.
    """
    accepted_at = datetime.now(UTC).isoformat()
    user_id = getattr(auth, "user_id", None) or "unknown"

    # Step 1: BOLA gate is fulfilled by require_site_access dependency above

    # Step 2: Fetch the most recent PENDING recommendation for this site
    recommendation_service = get_recommendation_service()
    pending_recs = await recommendation_service.get_pending_recommendations(site_id, limit=1)
    recommendation_id: str | None = None
    execution_id: str | None = None
    approval_status = "no_active_recommendation"

    if pending_recs:
        recommendation = pending_recs[0]
        recommendation_id = recommendation.id

        # Step 3: Route through ApprovalService
        try:
            approval_service = get_approval_service()
            result = await approval_service.approve_recommendation(
                rec_id=recommendation_id,
                user_id=user_id,
                reason="Operator approved via cockpit supervised confirm bar",
            )
            # Extract execution_id from execution_result if present
            if result.execution_result:
                execution_id = result.execution_result.get("correlation_id") or result.execution_result.get(
                    "decision_id"
                )
            approval_status = result.status

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Cockpit approval failed",
                extra={
                    "site_id": site_id,
                    "recommendation_id": recommendation_id,
                    "routing_source": "cockpit_approval",
                    "status": "approval_failed",
                    "accepted_at": accepted_at,
                    "error": str(exc),
                },
            )
            approval_status = "approval_failed"

    # Step 4: INFO-level audit log for every call
    logger.info(
        "Cockpit approval processed",
        extra={
            "site_id": site_id,
            "recommendation_id": recommendation_id,
            "routing_source": "cockpit_approval",
            "status": approval_status,
            "accepted_at": accepted_at,
        },
    )

    return CockpitApprovalResponse(
        accepted=True,
        site_id=site_id,
        accepted_at=accepted_at,
        recommendation_id=recommendation_id,
        execution_id=execution_id,
        status=approval_status,
    )
