"""Building State API for the SENTINEL cockpit."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app.services.building_state_engine import build_building_state_payload
from app.services.building_state_models import BuildingStatePayload

router = APIRouter(prefix="/api/building-state", tags=["building-state"])


@router.get("/{site_id}")
async def get_building_state(site_id: str) -> dict[str, str | BuildingStatePayload]:
    payload = build_building_state_payload(site_id)
    return {
        "payload": payload,
        "site_id": site_id,
        "fetched_at": datetime.now(UTC).isoformat(),
    }
