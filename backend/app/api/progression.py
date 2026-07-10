"""Progression Engine API — trust level visibility and operator controls.

Phase D of the SENTINEL Autonomous Building Operator progression engine.

Endpoints:
  GET    /api/progression/trust/{site_id}   — Site trust summary + all classes + gates
  GET    /api/progression/classes/{site_id}  — Per-class readiness detail
  POST   /api/progression/override/{site_id} — Operator overrides (hold, force promote)
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel
from app.services.progression_engine_service import get_progression_engine_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/progression", tags=["progression"])


# ── Gate thresholds for each trust level ──────────────────────────────
# Thresholds: evidence_count, accuracy_pct_30d, distinct_classes
_GATES_BY_CURRENT_LEVEL: dict[int, dict[str, Any]] = {
    1: {  # Advisory → Supervised
        "required_evidence": 200,
        "required_accuracy": 85.0,
        "required_distinct_classes": 5,
    },
    2: {  # Supervised → Autonomous
        "required_evidence": 500,
        "required_accuracy": 90.0,
        "required_distinct_classes": 8,
    },
}


@router.get("/trust/{site_id}")
async def get_site_trust(
    site_id: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> dict[str, Any]:
    """Return site trust summary: current level, readiness gates, and all classes.

    This is the primary dashboard endpoint for operators to understand
    the site's trust-ladder status at a glance.
    """
    prog = get_progression_engine_service()
    return await prog.get_site_trust_summary(site_id)


@router.get("/classes/{site_id}")
async def get_class_readiness_detail(
    site_id: str,
    class_name: str | None = Query(None, description="Filter by class name"),
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> dict[str, Any]:
    """Return per-class readiness detail.

    If class_name is specified, returns detail for that class only.
    Otherwise returns all classes at the site.
    """
    prog = get_progression_engine_service()

    if class_name:
        readiness = await prog.get_class_readiness(site_id, class_name)
        return {"site_id": site_id, "classes": [readiness]}

    summary = await prog.get_site_trust_summary(site_id)
    return {"site_id": site_id, "classes": summary.get("classes", [])}


class OverrideRequest:
    """Parsed operator override request."""

    def __init__(self, body: dict[str, Any]):
        self.override_type: str = body.get("override_type", "hold_site")
        self.class_name: str | None = body.get("class_name")
        self.hold_until: str | None = body.get("hold_until")
        self.override_level: int | None = body.get("override_level")
        self.reason: str | None = body.get("reason")


@router.post("/override/{site_id}")
async def apply_operator_override(
    site_id: str,
    request: Request,
    auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR)),
) -> dict[str, Any]:
    """Apply an operator override for trust progression.

    Supported override types:
      hold_site             — Prevent site from progressing until a date
      override_class_level  — Force a class to a specific trust level

    Body:
    ```json
    {
        "override_type": "hold_site",
        "hold_until": "2026-08-09",
        "reason": "Investigating comfort complaints"
    }
    ```
    or
    ```json
    {
        "override_type": "override_class_level",
        "class_name": "zone_shutdown",
        "override_level": 3,
        "reason": "Proven safe — accelerated to autonomous"
    }
    ```
    """
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    op = OverrideRequest(body)
    operator_id = getattr(auth, "user_id", None) or request.headers.get("X-User-Id", "unknown")

    # Validate
    valid_types = {"hold_site", "override_class_level"}
    if op.override_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid override_type '{op.override_type}'. Must be one of {valid_types}",
        )

    if op.override_type == "override_class_level":
        if not op.class_name:
            raise HTTPException(status_code=400, detail="class_name required for override_class_level")
        if op.override_level is not None and (op.override_level < 0 or op.override_level > 3):
            raise HTTPException(status_code=400, detail="override_level must be 0-3")

    prog = get_progression_engine_service()

    if op.override_type == "hold_site":
        overrides = {}
        if op.hold_until:
            overrides["hold_until"] = op.hold_until
        result = await prog.apply_overrides(site_id, overrides)
    elif op.override_type == "override_class_level":
        class_overrides = {op.class_name: op.override_level} if op.class_name and op.override_level is not None else {}
        result = await prog.apply_overrides(site_id, {"class_overrides": class_overrides})

    # Audit log
    logger.info(
        "Operator override: site=%s type=%s class=%s level=%s hold=%s reason=%s operator=%s",
        site_id,
        op.override_type,
        op.class_name,
        op.override_level,
        op.hold_until,
        op.reason,
        operator_id,
    )

    return {
        "success": True,
        "site_id": site_id,
        "override_type": op.override_type,
        "class_name": op.class_name,
        "override_level": op.override_level,
        "hold_until": op.hold_until,
        "details": result,
    }
