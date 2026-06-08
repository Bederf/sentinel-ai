"""
Cockpit Decision API — Issue-based contract (Phase 209 V2).

GET  /api/cockpit/decision/{site_id}
     Sources live issues via CockpitIssueFusionService; returns CockpitDecisionPayload.
     Merges any in-session status mutations from _ISSUE_STORE before responding.

POST /api/cockpit/decision/approve/{site_id}
     Supervised-mode approval (Phase 207 path, unchanged).

POST /api/cockpit/issues/{site_id}/{issue_id}/action
     Issue lifecycle mutations: acknowledge, assign, create_work_order, escalate.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.schemas.cockpit import (
    AuditOutcome,
    CockpitActionAudit,
    CockpitActionType,
    CockpitIssue,
    CockpitIssueEvidenceRef,
    CockpitIssueLocation,
    CockpitSourceStatus,
    IssueStatus,
)
from app.models.module_registry import ModuleType
from app.services.cockpit_issue_fusion import CockpitIssueFusionService
from app.services.module_registry_service import module_registry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cockpit", tags=["cockpit"])

# Subsystem → module gate: issues whose subsystem maps here are only shown
# when the corresponding module is active for the site.
# Subsystems not listed (general, occupancy) are always shown.
_SUBSYSTEM_MODULE_GATE: dict[str, ModuleType] = {
    "hvac": ModuleType.HVAC,
    "power": ModuleType.ENERGY,
    "lighting": ModuleType.LIGHTING,
    "security": ModuleType.SECURITY,
    "water": ModuleType.WATER,
    "digital_twin": ModuleType.DIGITAL_TWIN,
}

# ---------------------------------------------------------------------------
# Module-level stores (in-memory, cleared between test runs via fixture)
# ---------------------------------------------------------------------------

_ISSUE_STORE: dict[str, list[CockpitIssue]] = {}
_AUDIT_LOG_STORE: dict[str, list[CockpitActionAudit]] = {}
_ISSUE_SITE_LOOKUP: dict[str, str] = {}  # issue_id → site_id

# Module-level service instance (monkeypatched in tests)
cockpit_issue_service = CockpitIssueFusionService()

# ---------------------------------------------------------------------------
# Re-export schema types used in tests (imported from app.api.cockpit)
# ---------------------------------------------------------------------------

__all__ = [
    "_AUDIT_LOG_STORE",
    "_ISSUE_SITE_LOOKUP",
    "_ISSUE_STORE",
    "CockpitActionRequest",
    "CockpitDecisionPayload",
    "CockpitIssue",
    "CockpitIssueEvidenceRef",
    "CockpitIssueLocation",
    "CockpitSourceStatus",
    "_apply_action",
    "_available_actions",
    "_build_cockpit_payload",
    "_cache_site_issues",
    "_fetch_control_enabled",
    "_fetch_site_phase",
    "_record_audit",
    "cockpit_issue_service",
]


# ---------------------------------------------------------------------------
# Request / payload models
# ---------------------------------------------------------------------------


class CockpitActionRequest(BaseModel):
    action: CockpitActionType
    actor_id: str
    actor_label: str
    assign_to: str | None = None
    assign_team: str | None = None
    work_order_title: str | None = None
    notes: str | None = None
    evidence_refs: list[str] = []


class CockpitRiskResolution(BaseModel):
    """Backend-resolved risk semantics for cockpit rendering."""

    score: float
    band: Literal["low", "medium", "high", "critical"]
    reason: str
    policy_source: str
    policy_level: Literal["site_asset_criticality", "site_asset", "site", "posture", "system"]
    constraint_type: Literal["comfort", "asset", "cost", "compliance"]
    time_to_constraint_breach_min: int | None = None
    affected_scope: dict[str, Any]


class CockpitHealthResolution(BaseModel):
    """Backend-resolved health semantics for cockpit rendering."""

    score: float
    state: Literal["healthy", "stable", "watch", "degraded", "critical"]
    trend: Literal["improving", "flat", "declining", "volatile"]
    reason: str
    asset_class: str
    criticality: Literal["low", "medium", "high", "mission_critical"]


class CockpitDecisionPayload(BaseModel):
    """
    Complete payload shape for cockpit decision surface rendering.

    All fields support null (for calm buildings, missing context, etc).
    Frontend mapCockpitState will use these nulls to trigger fallback states.
    """

    building_id: str
    issues: list[CockpitIssue] = []
    selected_issue_id: str | None = None
    source_health: list[CockpitSourceStatus] = []

    alert_text: str | None = None
    reasoning_summary: str | None = None
    active_posture: str | None = None
    time_to_discomfort: int | None = None
    time_confidence: str | int | None = None
    estimated_impact: Any | None = None
    recommended_action: str | None = None
    urgency_score: float | None = None
    urgency_components: dict[str, float] | None = None
    affected_zone_ids: list[str] | None = None
    primary_asset_id: str | None = None
    building_metadata: dict[str, Any] | None = None
    risk: CockpitRiskResolution | None = None
    health: CockpitHealthResolution | None = None
    overflow_issues: list[CockpitIssue] = []
    overflow_count: int = 0


# ---------------------------------------------------------------------------
# In-memory helpers
# ---------------------------------------------------------------------------


def _cache_site_issues(site_id: str, issues: list[CockpitIssue]) -> None:
    """Cache a list of issues for a site and populate the reverse lookup."""
    _ISSUE_STORE[site_id] = issues
    for issue in issues:
        _ISSUE_SITE_LOOKUP[issue.id] = site_id


# ---------------------------------------------------------------------------
# Action helpers
# ---------------------------------------------------------------------------


def _available_actions(status: IssueStatus, posture: str = "supervised") -> list[CockpitActionType]:
    """Return valid next actions for an issue in the given status and posture."""
    if posture == "advisory":
        # Read-only: only acknowledge allowed for new issues
        return ["acknowledge"] if status == "new" else []
    if status == "new":
        return ["acknowledge", "assign"]
    if status == "triaged":
        return ["assign", "create_work_order", "escalate"]
    if status == "in_progress":
        return ["create_work_order", "escalate"]
    return []


def _apply_action(
    issue: CockpitIssue,
    request: CockpitActionRequest,
) -> tuple[Literal["accepted", "rejected"], IssueStatus, str]:
    """Apply an action to an issue in-place. Returns (result, status_after, message)."""
    action = request.action

    if action == "acknowledge":
        if issue.status != "new":
            return "rejected", issue.status, "acknowledge requires new status"
        issue.status = "triaged"
        return "accepted", issue.status, "Issue acknowledged"

    if action == "assign":
        if not request.assign_to and not request.assign_team:
            return "rejected", issue.status, "assign_to or assign_team required"
        if issue.status not in ("new", "triaged"):
            return "rejected", issue.status, "assign requires new or triaged status"
        issue.owner = request.assign_to
        issue.owner_team = request.assign_team
        if issue.status == "new":
            issue.status = "triaged"
        return "accepted", issue.status, "Issue assigned"

    if action == "create_work_order":
        if issue.status not in ("triaged", "in_progress"):
            return "rejected", issue.status, "create_work_order requires triaged or in_progress status"
        issue.status = "in_progress"
        return "accepted", issue.status, "Work order created"

    if action == "escalate":
        return "accepted", issue.status, "Issue escalated"

    return "rejected", issue.status, f"Unknown action: {action}"


def _record_audit(
    issue: CockpitIssue,
    request: CockpitActionRequest,
    result: str,
    status_before: IssueStatus,
    status_after: IssueStatus,
    message: str | None = None,
    *,
    site_id: str | None = None,
) -> CockpitActionAudit:
    """Record an action audit entry and persist to _AUDIT_LOG_STORE."""
    outcome_map: dict[str, AuditOutcome] = {
        "accepted": "success",
        "rejected": "rejected",
        "failed": "failed",
    }
    outcome: AuditOutcome = outcome_map.get(result, "failed")  # type: ignore[assignment]

    audit = CockpitActionAudit(
        id=str(uuid.uuid4()),
        issue_id=issue.id,
        action=request.action,
        actor_type="user",
        actor_id=request.actor_id,
        actor_label=request.actor_label,
        occurred_at=datetime.now(UTC),
        outcome=outcome,
        status_before=status_before,
        status_after=status_after,
        notes=message or request.notes,
        evidence_refs=request.evidence_refs,
    )

    resolved_site = site_id or _ISSUE_SITE_LOOKUP.get(issue.id, "unknown")
    _AUDIT_LOG_STORE.setdefault(resolved_site, []).append(audit)
    return audit


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------


def _filter_by_active_modules(issues: list[CockpitIssue], site_id: str) -> list[CockpitIssue]:
    """Drop issues whose subsystem maps to a module that is not active for the site."""
    result = []
    for issue in issues:
        module_type = _SUBSYSTEM_MODULE_GATE.get(issue.subsystem or "")
        if module_type is None or module_registry.is_module_active(site_id, module_type):
            result.append(issue)
    return result


async def _build_cockpit_payload(site_id: str) -> CockpitDecisionPayload | None:
    """Build a CockpitDecisionPayload for a site, merging cached issue state."""
    phase = await _fetch_site_phase(site_id)

    # Commissioning / shadow_live: no cockpit payload
    if phase in ("commissioning", "shadow_live"):
        return None

    issues, overflow_issues, source_statuses, _tensions, selected_id = cockpit_issue_service.aggregate(site_id)

    # Drop issues from inactive/unlicensed modules
    issues = _filter_by_active_modules(issues, site_id)
    overflow_issues = _filter_by_active_modules(overflow_issues, site_id)
    if not issues:
        return None

    # Merge in-session status mutations from _ISSUE_STORE (e.g., after actions)
    cached = {i.id: i for i in _ISSUE_STORE.get(site_id, [])}
    merged = [cached.get(issue.id, issue) for issue in issues]
    overflow_merged = [cached.get(issue.id, issue) for issue in overflow_issues]

    # Derive posture from phase
    posture_map = {"advisory": "advisory", "supervised": "supervised", "automatic": "autonomous"}
    posture = posture_map.get(phase, "advisory")

    # Cache issues for the action endpoint — without this, POST .../action returns 404
    _cache_site_issues(site_id, merged)

    return CockpitDecisionPayload(
        building_id=site_id,
        active_posture=posture,
        issues=merged,
        overflow_issues=overflow_merged,
        overflow_count=len(overflow_merged),
        selected_issue_id=selected_id,
        source_health=source_statuses,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/decision/{site_id}")
async def get_cockpit_decision(site_id: str) -> dict[str, Any]:
    """
    Get cockpit decision payload for a site (V2 issue-based).

    Returns null payload when no active issues exist or phase is pre-advisory.
    """
    payload = await _build_cockpit_payload(site_id)
    return {
        "payload": payload,
        "site_id": site_id,
        "fetched_at": datetime.now(UTC).isoformat(),
    }


@router.post("/issues/{site_id}/{issue_id}/action")
async def cockpit_issue_action(
    site_id: str,
    issue_id: str,
    request: CockpitActionRequest,
) -> dict[str, Any]:
    """
    Apply a lifecycle action to a cockpit issue.

    Actions: acknowledge, assign, create_work_order, escalate.
    Issue must be present in the in-session _ISSUE_STORE for the site.
    """
    phase = await _fetch_site_phase(site_id)
    posture_map = {"advisory": "advisory", "supervised": "supervised", "automatic": "autonomous"}
    posture = posture_map.get(phase, "advisory")

    issues = _ISSUE_STORE.get(site_id, [])
    issue = next((i for i in issues if i.id == issue_id), None)
    if not issue:
        raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")

    # Advisory gate: only acknowledge allowed
    if posture == "advisory" and request.action not in ("acknowledge",):
        raise HTTPException(
            status_code=403,
            detail=f"Action '{request.action}' not available in advisory posture",
        )

    # Control-enabled gate: create_work_order and escalate require control_enabled
    control_enabled = await _fetch_control_enabled(site_id)
    if not control_enabled and request.action in ("create_work_order", "escalate"):
        raise HTTPException(
            status_code=403,
            detail=f"Control not enabled for site {site_id}. Enable via site settings.",
        )

    status_before = issue.status
    result, status_after, message = _apply_action(issue, request)
    audit = _record_audit(issue, request, result, status_before, status_after, message, site_id=site_id)

    return {
        "result": result,
        "status_before": status_before,
        "status_after": status_after,
        "message": message,
        "audit_id": audit.id,
        "available_actions": _available_actions(status_after, posture),
    }


@router.post("/decision/approve/{site_id}", status_code=202)
async def approve_cockpit_decision(site_id: str) -> dict[str, Any]:
    """
    Operator approval for supervised-mode cockpit action (Phase 207 path, unchanged).

    Validates phase ≥ supervised, fetches active recommendation, routes
    through ApprovalService, persists parasite_decision, returns execution_id.

    Returns 202 Accepted — action is queued, not yet verified.
    """
    accepted_at = datetime.now(UTC).isoformat()

    phase = await _fetch_site_phase(site_id)
    if phase not in ("supervised", "automatic"):
        logger.warning("Cockpit approve rejected: phase %s < supervised for %s", phase, site_id)
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve: site is in '{phase}' phase. Supervised or automatic required.",
        )

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


# ---------------------------------------------------------------------------
# Data fetch helpers (used by approve endpoint)
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


async def _fetch_control_enabled(site_id: str) -> bool:
    """Fetch control_enabled flag from Supabase for the given site."""
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        row = client.table("sites").select("control_enabled").eq("code", site_id).limit(1).execute()
        if row.data:
            return bool(row.data[0].get("control_enabled", False))
    except Exception as exc:
        logger.debug("Could not fetch control_enabled for %s: %s", site_id, exc)
    return False


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
