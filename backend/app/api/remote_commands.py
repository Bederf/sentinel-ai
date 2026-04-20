"""Remote Command API Endpoints.

REST API for remote command execution, rollback, override management,
and command history.  All endpoints extract the user from verified JWT
auth state (set by the auth middleware) and enforce authorization +
audit logging.

Phase 59-02: Remote Operations
"""

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.services.remote_command_service import get_remote_command_service

logger = logging.getLogger(__name__)
router = APIRouter()


# --------------------------------------------------------------------- #
#  Request / Response models
# --------------------------------------------------------------------- #


class ExecuteCommandRequest(BaseModel):
    """Body for POST /api/remote/commands/execute."""

    device_id: str = Field(..., description="Target device ID")
    command_type: str = Field(
        ...,
        description=(
            "Command type: status_check, setpoint_adjust, schedule_override, "
            "equipment_start_stop, fault_reset, fire_panel_reset, door_unlock"
        ),
    )
    point: str | None = Field(None, description="Device point to write (optional for status_check)")
    value: float | int | bool | str | None = Field(
        None, description="Value to write (optional for status_check)"
    )
    reason: str = Field("", description="Reason for the command (recommended)")


class BatchCommandItem(BaseModel):
    """Single command within a batch request."""

    device_id: str
    command_type: str
    point: str | None = None
    value: float | int | bool | str | None = None


class BatchCommandRequest(BaseModel):
    """Body for POST /api/remote/commands/batch."""

    commands: list[BatchCommandItem] = Field(..., min_length=1, description="Commands to execute atomically")
    reason: str = Field("", description="Reason for the batch")


# --------------------------------------------------------------------- #
#  Helper: extract user from headers
# --------------------------------------------------------------------- #


def _extract_user(request: Request):
    """Extract user_id and user_role from the verified JWT auth state.

    Role is taken exclusively from request.state.auth (populated by the
    auth middleware after JWT verification).  The X-User-Role header is
    intentionally ignored to prevent role escalation attacks.
    Falls back to safe defaults if auth state is not present.
    """
    auth = getattr(request.state, "auth", None)
    if auth is not None:
        user_id = getattr(auth, "user_id", "unknown")
        # auth.role is a SentinelRole enum; .value gives the string name
        role_obj = getattr(auth, "role", None)
        user_role = role_obj.value if role_obj is not None else "viewer"
    else:
        user_id = "unknown"
        user_role = "viewer"
    return user_id, user_role


# --------------------------------------------------------------------- #
#  Endpoints
# --------------------------------------------------------------------- #


@router.post("/commands/execute", response_model=dict)
async def execute_command(body: ExecuteCommandRequest, request: Request):
    """Execute a remote command.

    Validates authorization, checks safety guardrails, executes the
    command through the device abstraction layer, and returns the result
    with rollback information.
    """
    user_id, user_role = _extract_user(request)
    svc = get_remote_command_service()

    try:
        result = await svc.execute_remote_command(
            user_id=user_id,
            user_role=user_role,
            device_id=body.device_id,
            command_type=body.command_type,
            point=body.point,
            value=body.value,
            reason=body.reason,
        )
        return result
    except Exception as e:
        logger.error(f"Command execution error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/commands/{command_id}/rollback", response_model=dict)
async def rollback_command(command_id: str, request: Request):
    """Rollback a previously executed command.

    Reverts the device point to its pre-command value.
    Only the command owner or an ENGINEER can rollback.
    """
    user_id, user_role = _extract_user(request)
    svc = get_remote_command_service()

    try:
        result = await svc.rollback_command(
            command_id=command_id,
            user_id=user_id,
            user_role=user_role,
        )
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "Rollback failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rollback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/overrides", response_model=list)
async def list_active_overrides(
    site_id: str | None = Query(None, description="Filter by site ID"),
):
    """List all active overrides with expiry times.

    Overrides are commands that will auto-revert after their expiry
    (setpoint: 4h, schedule: 8h, door unlock: 5min).
    """
    svc = get_remote_command_service()
    return svc.get_active_overrides(site_id=site_id)


@router.get("/commands/history", response_model=list)
async def get_command_history(
    user_id: str | None = Query(None, description="Filter by user ID"),
    device_id: str | None = Query(None, description="Filter by device ID"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
):
    """Get recent remote command history.

    Returns the most recent commands, newest first.
    """
    svc = get_remote_command_service()
    return svc.get_command_history(user_id=user_id, device_id=device_id, limit=limit)


@router.post("/commands/batch", response_model=dict)
async def execute_batch_commands(body: BatchCommandRequest, request: Request):
    """Execute multiple commands atomically.

    Pre-validates ALL commands before executing any.  If any single
    command fails validation, none are executed (all-or-nothing).
    """
    user_id, user_role = _extract_user(request)
    svc = get_remote_command_service()

    # Phase 1: Pre-validate every command
    validation_errors: list[dict] = []
    for idx, cmd in enumerate(body.commands):
        # Check authorization
        from app.models.remote_ops import COMMAND_AUTHORIZATION, AuthorizationLevel
        from app.services.auth_service import get_authorization_service

        auth_svc = get_authorization_service()
        required_level = COMMAND_AUTHORIZATION.get(cmd.command_type, AuthorizationLevel.ENGINEER)
        if not auth_svc.check_authorization(user_role, required_level):
            validation_errors.append(
                {
                    "index": idx,
                    "device_id": cmd.device_id,
                    "error": f"Insufficient authorization for {cmd.command_type}",
                }
            )
            continue

        # Check rate limit (peek only -- don't record yet)
        rate = svc._check_rate_limit(user_id)
        if rate["blocked"]:
            validation_errors.append(
                {
                    "index": idx,
                    "device_id": cmd.device_id,
                    "error": rate["message"],
                }
            )
            continue

        # Check command-specific guardrails
        validation = await svc._validate_command(cmd.device_id, cmd.command_type, cmd.point, cmd.value, user_role)
        if not validation["allowed"]:
            validation_errors.append(
                {
                    "index": idx,
                    "device_id": cmd.device_id,
                    "error": validation["error"],
                }
            )

    # If any validation failed, reject the whole batch
    if validation_errors:
        return {
            "success": False,
            "error": "Batch validation failed -- no commands executed",
            "validation_errors": validation_errors,
            "results": [],
        }

    # Phase 2: Execute all commands
    results: list[dict] = []
    for cmd in body.commands:
        result = await svc.execute_remote_command(
            user_id=user_id,
            user_role=user_role,
            device_id=cmd.device_id,
            command_type=cmd.command_type,
            point=cmd.point,
            value=cmd.value,
            reason=body.reason,
        )
        results.append(
            {
                "command_id": result.get("command_id"),
                "device_id": cmd.device_id,
                "success": result.get("success", False),
                "error": result.get("error"),
            }
        )

    all_ok = all(r["success"] for r in results)
    return {
        "success": all_ok,
        "results": results,
    }
