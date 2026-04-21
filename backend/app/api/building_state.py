"""Building State API for the SENTINEL cockpit."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter

from app.services.building_state_engine import _get_site_onboarding_phase, build_building_state_payload
from app.services.building_state_models import BuildingStatePayload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/building-state", tags=["building-state"])


def _build_shadow_payload(site_id: str) -> BuildingStatePayload:
    """Return a minimal observational payload for shadow-mode sites."""
    return BuildingStatePayload(
        site_id=site_id,
        building_posture="calm",
        primary_narrative=None,
        secondary_tensions=[],
        operator_guidance={"headline": "Telemetry indicates stable operation", "mode": "watch"},
        email_clusters=[],
    )


@router.get("/{site_id}")
async def get_building_state(site_id: str) -> dict[str, str | BuildingStatePayload]:
    phase = await _get_site_onboarding_phase(site_id)
    if phase == "shadow":
        # Shadow mode: suppress recommendation narratives — site is in ML training observation only
        payload = _build_shadow_payload(site_id)
    else:
        payload = build_building_state_payload(site_id)
    return {
        "payload": payload,
        "site_id": site_id,
        "fetched_at": datetime.now(UTC).isoformat(),
    }
