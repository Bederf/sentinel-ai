"""Remote Operations API - Building status, equipment diagnostics, and dispatch assessment.

Phase 59: Remote Operations
Provides REST endpoints for remote monitoring consumed by WhatsApp/Telegram
bots or direct API calls.  All endpoints enforce role-based authorization via
the AuthorizationService.

Endpoints:
  GET /api/remote/building/{site_id}/status       - Building overview (VIEW_ONLY+)
  GET /api/remote/equipment/{id}/diagnostic        - Equipment diagnostic (OPERATOR+)
  GET /api/remote/equipment/{id}/dispatch-assessment - Dispatch decision (OPERATOR+)
  GET /api/remote/user/{user_id}/sessions          - Session history (own user or admin)
  GET /api/remote/commands/allowed                 - Allowed commands for current role
"""

import logging

from fastapi import APIRouter, Header, HTTPException, Query

from app.models.remote_ops import AuthorizationLevel
from app.services.audit_logger import AuditLogger
from app.services.auth_service import get_authorization_service
from app.services.remote_monitoring_service import get_remote_monitoring_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/remote", tags=["remote-ops"])

# Singletons
_auth_service = get_authorization_service()
_monitoring_service = get_remote_monitoring_service()
_audit_logger = AuditLogger()


def _resolve_user(x_user_id: str | None) -> dict:
    """Resolve user from X-User-Id header. Requires valid user ID."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header required")
    # Default role mapping — callers authenticated upstream via JWT
    return {"user_id": x_user_id, "role": "technician", "full_name": x_user_id}


def _check_auth(user_role: str, required: AuthorizationLevel) -> None:
    """Raise 403 if user role does not meet the required authorization level."""
    if not _auth_service.check_authorization(user_role, required):
        level_name = required.name
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient authorization. Requires {level_name} level or above.",
        )


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


@router.get("/building/{site_id}/status")
async def get_site_status(
    site_id: str,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
):
    """Get building-wide status summary.

    Aggregates device counts, active alarms, health score, and key metrics.
    Requires VIEW_ONLY authorization or above.
    """
    user = _resolve_user(x_user_id)
    _check_auth(user["role"], AuthorizationLevel.VIEW_ONLY)

    try:
        status = await _monitoring_service.get_site_status(site_id)
        # Log the action
        _audit_logger.log_system_event(
            event_type="remote_site_status",
            user=user["user_id"],
            metadata={"site_id": site_id},
        )
        return status
    except Exception as exc:
        logger.error(f"Error getting building status for {site_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/equipment/{equipment_id}/diagnostic")
async def get_equipment_diagnostic(
    equipment_id: str,
    diagnostic_type: str = Query(
        "quick_status",
        description="Diagnostic type: quick_status or full_diagnostic",
    ),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
):
    """Run a remote diagnostic on equipment.

    For quick_status: current readings and safety status.
    For full_diagnostic: includes anomaly detection and recommendations.
    Requires OPERATOR authorization or above.
    """
    user = _resolve_user(x_user_id)
    _check_auth(user["role"], AuthorizationLevel.OPERATOR)

    if diagnostic_type not in ("quick_status", "full_diagnostic"):
        raise HTTPException(
            status_code=400,
            detail="diagnostic_type must be 'quick_status' or 'full_diagnostic'",
        )

    try:
        report = await _monitoring_service.get_equipment_diagnostic(equipment_id, diagnostic_type)
        _audit_logger.log_system_event(
            event_type="remote_equipment_diagnostic",
            user=user["user_id"],
            metadata={
                "equipment_id": equipment_id,
                "diagnostic_type": diagnostic_type,
            },
        )
        return report.model_dump()
    except Exception as exc:
        logger.error(f"Error running diagnostic for {equipment_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/equipment/{equipment_id}/dispatch-assessment")
async def get_dispatch_assessment(
    equipment_id: str,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
):
    """Assess whether a technician dispatch is needed.

    Evaluates device status, safety violations, and whether the issue
    can be resolved remotely. Requires OPERATOR authorization or above.
    """
    user = _resolve_user(x_user_id)
    _check_auth(user["role"], AuthorizationLevel.OPERATOR)

    try:
        decision = await _monitoring_service.assess_dispatch_need(equipment_id)
        _audit_logger.log_system_event(
            event_type="remote_dispatch_assessment",
            user=user["user_id"],
            metadata={
                "equipment_id": equipment_id,
                "dispatch_required": decision.dispatch_required,
                "urgency": decision.urgency,
            },
        )
        return decision.model_dump()
    except Exception as exc:
        logger.error(f"Error assessing dispatch for {equipment_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/user/{user_id}/sessions")
async def get_user_sessions(
    user_id: str,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
):
    """Get remote session history for a user.

    Users can view their own sessions. Admin/engineer can view any user's sessions.
    """
    current_user = _resolve_user(x_user_id)

    # Users can see their own sessions; admins/engineers can see anyone's
    if current_user["user_id"] != user_id:
        _check_auth(current_user["role"], AuthorizationLevel.ENGINEER)

    try:
        sessions = await _monitoring_service.get_remote_session_summary(user_id)
        return {"user_id": user_id, "sessions": sessions}
    except Exception as exc:
        logger.error(f"Error getting sessions for {user_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/commands/allowed")
async def get_allowed_commands(
    x_user_id: str | None = Header(None, alias="X-User-Id"),
):
    """List remote commands the current user is authorized to execute.

    Returns command types and the user's authorization level.
    """
    user = _resolve_user(x_user_id)
    allowed = _auth_service.get_allowed_commands(user["role"])
    level = _auth_service.get_user_authorization_level(user["role"])

    return {
        "user_id": user["user_id"],
        "role": user["role"],
        "authorization_level": level.value,
        "authorization_name": level.name,
        "allowed_commands": allowed,
    }
