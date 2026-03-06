"""Control Policy API — exposes control mode, policies, and command envelopes.

Phase 145: Control Policy Engine.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/control", tags=["Control Policy"])


@router.get("/mode")
async def get_control_mode():
    """Get current control mode and available tools."""
    from app.services.control_policy_engine import get_control_policy_engine

    engine = get_control_policy_engine()
    mode = engine.get_control_mode()
    return {
        "control_mode": mode.value,
        "write_allowed": engine.is_write_allowed(),
        "available_tools": engine.get_available_tools(),
    }


@router.get("/policies")
async def list_policies():
    """List all asset control policies."""
    from app.services.control_policy_engine import get_control_policy_engine

    engine = get_control_policy_engine()
    return {"policies": [p.to_dict() for p in engine.list_policies()]}


@router.get("/policies/{equipment_type}")
async def get_policy(equipment_type: str):
    """Get control policy for an equipment type."""
    from app.services.control_policy_engine import get_control_policy_engine

    engine = get_control_policy_engine()
    policy = engine.get_policy(equipment_type)
    if not policy:
        raise HTTPException(status_code=404, detail=f"No policy for {equipment_type}")
    return policy.to_dict()


@router.get("/envelopes/active")
async def get_active_envelopes(site_id: Optional[str] = Query(None)):
    """Get active (executed, not rolled back) command envelopes."""
    from app.services.control_policy_engine import get_control_policy_engine

    engine = get_control_policy_engine()
    envelopes = engine.get_active_envelopes(site_id)
    return {"envelopes": [e.to_dict() for e in envelopes]}


@router.get("/envelopes/{envelope_id}")
async def get_envelope(envelope_id: str):
    """Get a specific command envelope."""
    from app.services.control_policy_engine import get_control_policy_engine

    engine = get_control_policy_engine()
    envelope = engine._active_envelopes.get(envelope_id)
    if not envelope:
        raise HTTPException(status_code=404, detail=f"Envelope {envelope_id} not found")
    return envelope.to_dict()


@router.post("/envelopes/{envelope_id}/rollback")
async def rollback_envelope(envelope_id: str, reason: str = Query("operator_requested")):
    """Roll back a previously executed command."""
    from app.services.control_policy_engine import get_control_policy_engine

    engine = get_control_policy_engine()
    try:
        envelope = await engine.rollback_envelope(envelope_id, reason)
        return envelope.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
