"""POPIA privacy request and retention endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel
from app.services.popia_retention_service import get_popia_retention_service
from app.services.privacy_request_service import (
    RequestStatus,
    get_privacy_request_service,
)
from app.services.supabase_retention_service import get_supabase_retention_service

router = APIRouter(prefix="/api/privacy", tags=["privacy"])


class CreatePrivacyRequestBody(BaseModel):
    """Request body for creating POPIA data-subject workflow entries."""

    request_type: str = Field(..., description="access|correction|deletion|objection|portability|withdraw_consent")
    channel: str = Field(default="api", description="Channel that received request")
    details: str = Field(default="", description="Request description")
    data_subject_id: str | None = Field(
        default=None,
        description="Explicit data subject identifier. Defaults to current user.",
    )
    metadata: dict = Field(default_factory=dict)


class UpdatePrivacyRequestBody(BaseModel):
    """Request body for updates and closure of privacy requests."""

    status: str = Field(..., description="pending|in_progress|fulfilled|rejected|cancelled|expired")
    assigned_to: str | None = None
    outcome_summary: str | None = None
    evidence_refs: list[str] | None = None
    metadata: dict = Field(default_factory=dict)


class RetentionEnforcementBody(BaseModel):
    """Retention enforcement request body."""

    dry_run: bool = True


@router.post("/requests", response_model=dict)
async def create_privacy_request(
    body: CreatePrivacyRequestBody,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Create POPIA data subject request entry with SLA timestamp."""
    subject_id = body.data_subject_id or auth.email or auth.user_id
    if not subject_id:
        raise HTTPException(status_code=400, detail="Unable to determine data subject identifier")

    service = get_privacy_request_service()
    item = service.submit_request(
        data_subject_id=subject_id,
        request_type=body.request_type,
        channel=body.channel,
        details=body.details,
        requested_by=auth.email or auth.user_id,
        metadata=body.metadata,
    )
    return item.model_dump()


@router.get("/requests", response_model=dict)
async def list_privacy_requests(
    status: str | None = Query(default=None),
    include_closed: bool = Query(default=True),
    overdue_only: bool = Query(default=False),
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """List privacy requests and current SLA metrics."""
    service = get_privacy_request_service()
    items = service.list_requests(status=status, include_closed=include_closed, overdue_only=overdue_only)
    metrics = service.get_metrics()

    if auth.role.value != "admin":
        owned = [item for item in items if item.requested_by in {auth.user_id, auth.email}]
        return {"items": [item.model_dump() for item in owned], "count": len(owned), "metrics": metrics}

    return {"items": [item.model_dump() for item in items], "count": len(items), "metrics": metrics}


@router.get("/requests/{request_id}", response_model=dict)
async def get_privacy_request(
    request_id: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Get one privacy request entry."""
    service = get_privacy_request_service()
    item = service.get_request(request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Privacy request not found")

    if auth.role.value != "admin" and item.requested_by not in {auth.user_id, auth.email}:
        raise HTTPException(status_code=403, detail="Access denied")

    return item.model_dump()


@router.post("/requests/{request_id}/status", response_model=dict)
async def update_privacy_request(
    request_id: str,
    body: UpdatePrivacyRequestBody,
    _auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR)),
):
    """Update privacy request status, assignment, and evidence links."""
    valid_statuses = {
        RequestStatus.PENDING,
        RequestStatus.IN_PROGRESS,
        RequestStatus.FULFILLED,
        RequestStatus.REJECTED,
        RequestStatus.CANCELLED,
        RequestStatus.EXPIRED,
    }
    if body.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status '{body.status}'")

    service = get_privacy_request_service()
    updated = service.update_request(
        request_id,
        status=body.status,
        assigned_to=body.assigned_to,
        outcome_summary=body.outcome_summary,
        evidence_refs=body.evidence_refs,
        metadata=body.metadata,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Privacy request not found")
    return updated.model_dump()


@router.get("/requests-metrics", response_model=dict)
async def get_privacy_request_metrics(
    _auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR)),
):
    """Return SLA and status metrics for privacy requests."""
    return get_privacy_request_service().get_metrics()


@router.get("/retention/status", response_model=dict)
async def get_retention_status(
    _auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR)),
):
    """Get retention overdue snapshot."""
    return get_popia_retention_service().get_retention_status()


@router.post("/retention/enforce", response_model=dict)
async def enforce_retention(
    body: RetentionEnforcementBody,
    _auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Execute or preview retention cleanup."""
    return get_popia_retention_service().enforce_policies(dry_run=body.dry_run)


# =============================================================================
# Supabase SQL Table Retention (POPIA Section 14 — S14(1) / S14(2))
# =============================================================================


@router.get("/retention/sql-status", response_model=dict)
async def get_sql_retention_status(
    _auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR)),
):
    """Get Supabase SQL table retention overdue counts per tier.

    Returns current overdue row counts for ML training (7d), operational
    snapshots (30d), and audit trail (5y) without deleting anything.
    """
    service = get_supabase_retention_service()
    return service.get_retention_status()


@router.post("/retention/sql-enforce", response_model=dict)
async def enforce_sql_retention(
    _auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Execute Supabase SQL table retention enforcement.

    Runs deletion for all three tiers (ML training, operational, audit trail)
    and logs results to retention_execution_log table.
    """
    service = get_supabase_retention_service()

    ml = service.run_ml_training_deletion(dry_run=False)
    snap = service.run_snapshot_deletion(dry_run=False)
    audit = service.run_audit_trail_deletion(dry_run=False)

    total_deleted = ml.total_deleted + snap.total_deleted + audit.total_deleted
    total_reviewed = ml.total_reviewed + snap.total_reviewed + audit.total_reviewed
    errors = len(ml.errors) + len(snap.errors) + len(audit.errors)

    # Log to retention_execution_log
    try:
        from app.config.database import supabase_client

        for result, tier_label in [
            (ml, "ml_training"),
            (snap, "operational"),
            (audit, "audit_trail"),
        ]:
            for r in result.results:
                supabase_client.table("retention_execution_log").insert(
                    {
                        "tier": tier_label,
                        "execution_time": result.executed_at,
                        "rows_reviewed": r.reviewed,
                        "rows_deleted": r.deleted,
                        "status": "success" if r.error is None else "error",
                        "details": {"table": r.table_name, "error": r.error},
                    }
                ).execute()
    except Exception as e:
        import logging

        logging.warning(f"Failed to log retention execution: {e}")

    return {
        "ml_training": {"reviewed": ml.total_reviewed, "deleted": ml.total_deleted, "errors": ml.errors},
        "operational": {"reviewed": snap.total_reviewed, "deleted": snap.total_deleted, "errors": snap.errors},
        "audit_trail": {"reviewed": audit.total_reviewed, "deleted": audit.total_deleted, "errors": audit.errors},
        "total_reviewed": total_reviewed,
        "total_deleted": total_deleted,
        "total_errors": errors,
    }


@router.get("/retention/sql-history", response_model=dict)
async def get_sql_retention_history(
    limit: int = Query(default=10, ge=1, le=100),
    _auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR)),
):
    """Get last N retention execution log entries."""
    try:
        from app.config.database import supabase_client

        result = (
            supabase_client.table("retention_execution_log")
            .select("*")
            .order("execution_time", desc=True)
            .limit(limit)
            .execute()
        )
        return {"items": result.data, "count": len(result.data)}
    except Exception as e:
        return {"items": [], "count": 0, "error": str(e)}
