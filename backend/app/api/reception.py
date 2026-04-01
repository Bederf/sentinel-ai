"""Reception API — visitor management endpoints.

Provides:
    POST /api/reception/scan      — QR or PIN scan at reception
    POST /api/reception/register   — Capture visitor details
    POST /api/reception/issue-card — Issue access card

Prefix: /api/reception
Tags: reception
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.api.visit_service import VisitService
from app.models.visit import VisitStatus
from app.services.visit_notification_service import get_notification_service
from app.services.visit_policy_engine import VisitPolicyEngine
from app.schemas.visit import (
    IssueCardRequest,
    IssueCardResponse,
    RegisterRequest,
    RegisterResponse,
    ScanRequest,
    ScanResponse,
    VisitResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reception", tags=["reception"])

# Module dependency — reception is part of the security module
# NOTE: Module gating will be added in a later phase. For now, all
# endpoints are open. When the security module is enabled, uncomment:
# from app.api.dependencies.module_access import require_active_module
# from app.models.module_registry import ModuleType
# router = APIRouter(..., dependencies=[Depends(require_active_module(ModuleType.SECURITY))])


def _visit_to_response(visit) -> VisitResponse:
    """Convert a Visit model to a VisitResponse schema."""
    return VisitResponse(
        id=visit.id,
        token=visit.token,
        pin=visit.pin,
        visitor_email=visit.visitor_email,
        visitor_name=visit.visitor_name,
        host_email=visit.host_email,
        host_name=visit.host_name,
        host_mobile=visit.host_mobile,
        building_id=visit.building_id,
        meeting_start=visit.meeting_start,
        meeting_end=visit.meeting_end,
        status=visit.status,
        visitor_photo=visit.visitor_photo,
        visitor_vehicle=visit.visitor_vehicle,
        visitor_id_number=visit.visitor_id_number,
        access_card_id=visit.access_card_id,
        qr_code=visit.qr_code,
        created_at=visit.created_at,
        updated_at=visit.updated_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/scan", response_model=ScanResponse)
def scan_visit(request: ScanRequest) -> ScanResponse:
    """Scan a visitor's QR code or enter their PIN at reception.

    Accepts EITHER a token UUID OR a 6-digit PIN.
    Validates via policy engine (time window, expiry, status) before transition.
    """
    if request.token is None and request.pin is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'token' or 'pin' must be provided",
        )
    if request.token is not None and request.pin is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide only 'token' OR 'pin', not both",
        )

    # Enforce policy BEFORE any state transition
    policy = VisitPolicyEngine()
    result = policy.check_scan_policy(token=request.token, pin=request.pin)

    if not result.allowed:
        raise HTTPException(
            status_code=result.status_code,
            detail=result.reason,
        )

    visit = result.visit
    time_window_valid = visit.status != VisitStatus.EXPIRED

    # Transition CREATED -> ARRIVED on first scan
    service_layer = VisitService()
    updated_visit = service_layer.arrive_visit(visit)
    building_name = service_layer.get_building_name(updated_visit.building_id)

    return ScanResponse(
        visit=_visit_to_response(updated_visit),
        building_name=building_name,
        time_window_valid=time_window_valid,
    )


@router.post("/register", response_model=RegisterResponse)
def register_visit(request: RegisterRequest) -> RegisterResponse:
    """Capture visitor details at reception.

    Updates an EXISTING visit only — never creates a new visit.
    Requires the visit to have been scanned (ARRIVED status).
    """
    service = VisitService()

    visit = service.scan_visit(token=request.token)
    if visit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Visit not found",
        )

    # Can only register visits that are ARRIVED (scanned)
    if visit.status != VisitStatus.ARRIVED:
        if visit.status == VisitStatus.REGISTERED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Visitor already registered",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Visit must be scanned (ARRIVED) before registration, current status: {visit.status}",
        )

    updated = service.register_visit(
        token=request.token,
        visitor_name=request.visitor_name,
        photo=request.photo,
        vehicle=request.vehicle,
        id_number=request.id_number,
    )

    # Notify host once visitor has completed reception registration.
    try:
        notification_service = get_notification_service()
        notification_service.notify_host_arrival(updated)
    except Exception as exc:
        logger.warning("Host notification failed for visit %s: %s", updated.id, exc)

    return RegisterResponse(
        visit=_visit_to_response(updated),
        message="Visitor registered successfully",
    )


@router.post("/issue-card", response_model=IssueCardResponse)
def issue_card(request: IssueCardRequest) -> IssueCardResponse:
    """Issue an access card to a registered visitor.

    Visit must be in REGISTERED status. In Plan 4, this will
    delegate to the C-CURE adapter for actual card provisioning.
    """
    service = VisitService()

    # First check if visit exists
    visit = service.scan_visit(token=request.token)
    if visit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Visit not found",
        )

    if visit.status == VisitStatus.DENIED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Host denied access",
        )

    if visit.status != VisitStatus.REGISTERED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Visit must be in REGISTERED status to issue card, got {visit.status}",
        )

    updated = service.issue_card(token=request.token, access_card_id=request.access_card_id)

    return IssueCardResponse(
        visit_id=updated.id,
        status=updated.status,
        access_card_id=updated.access_card_id,
    )
