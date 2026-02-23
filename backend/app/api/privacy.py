"""POPIA privacy request and retention endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel
from app.services.privacy_request_service import (
    RequestStatus,
    get_privacy_request_service,
)
from app.services.popia_retention_service import get_popia_retention_service

router = APIRouter(prefix="/api/privacy", tags=["privacy"])


class CreatePrivacyRequestBody(BaseModel):
    """Request body for creating POPIA data-subject workflow entries."""

    request_type: str = Field(..., description="access|correction|deletion|objection|portability|withdraw_consent")
    channel: str = Field(default="api", description="Channel that received request")
    details: str = Field(default="", description="Request description")
    data_subject_id: Optional[str] = Field(
        default=None,
        description="Explicit data subject identifier. Defaults to current user.",
    )
    metadata: dict = Field(default_factory=dict)


class UpdatePrivacyRequestBody(BaseModel):
    """Request body for updates and closure of privacy requests."""

    status: str = Field(..., description="pending|in_progress|fulfilled|rejected|cancelled|expired")
    assigned_to: Optional[str] = None
    outcome_summary: Optional[str] = None
    evidence_refs: Optional[list[str]] = None
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
    status: Optional[str] = Query(default=None),
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
