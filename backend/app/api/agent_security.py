"""Agent Security API — Phase 120-05.

Provides endpoints for the agent security confirmation flow and
circuit breaker management.

Endpoints:
- POST /api/agent/confirm — Validate confirmation token for dangerous actions
- GET /api/agent/circuit-breaker/{agent_id} — Get breaker state (admin only)
- POST /api/agent/circuit-breaker/{agent_id}/reset — Force reset breaker (admin only)
"""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.middleware.agent_security.circuit_breaker import circuit_breaker
from app.middleware.agent_security.policy_engine import PolicyDecision, policy_engine
from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["Agent Security"])


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class ConfirmActionRequest(BaseModel):
    """Request body for confirmation endpoint."""

    session_id: str
    token: str


class ConfirmActionResponse(BaseModel):
    """Response body for confirmation endpoint."""

    status: str
    detail: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/confirm", response_model=ConfirmActionResponse)
async def confirm_action(body: ConfirmActionRequest):
    """Validate a confirmation token for a dangerous agent action.

    Called after a 202 REQUIRE_CONFIRMATION response from the middleware.
    The client submits the session_id and the token received in the 202 body.

    Returns 200 on success, 403 on failure (expired, mismatch, not found).
    """
    result = policy_engine.confirm_action(
        session_id=body.session_id,
        user_token=body.token,
    )

    if result.decision == PolicyDecision.ALLOW:
        logger.info(
            "agent_security.confirm_success session_id=%s",
            body.session_id,
        )
        return JSONResponse(
            status_code=200,
            content={"status": "confirmed", "detail": result.reason},
        )

    logger.warning(
        "agent_security.confirm_denied session_id=%s reason=%s",
        body.session_id,
        result.reason,
    )
    return JSONResponse(
        status_code=403,
        content={"status": "denied", "detail": result.reason},
    )


@router.get("/circuit-breaker/{agent_id}")
async def get_circuit_breaker_status(
    agent_id: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Get the current circuit breaker state for an agent.

    Admin only. Returns the breaker state, recent failure count,
    trip reason, and cooldown configuration.
    """
    status = circuit_breaker.get_status(agent_id)
    return status


@router.post("/circuit-breaker/{agent_id}/reset")
async def reset_circuit_breaker(
    agent_id: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Force-reset a circuit breaker for an agent.

    Admin only. Clears all failure counters and returns the breaker
    to CLOSED state.
    """
    circuit_breaker.force_reset(agent_id)
    logger.info(
        "agent_security.breaker_reset agent_id=%s by=%s",
        agent_id,
        auth.user_id,
    )
    return {
        "status": "reset",
        "agent_id": agent_id,
        "state": "closed",
    }
