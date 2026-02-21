"""
Asset Health + Baseline endpoints — Phase 109A

Surfaces baseline and health metadata for the equipment list.
Health status is delegated to HealthThresholdService (single source of truth).
"""

import logging

from fastapi import APIRouter, HTTPException

from app.models.asset_health import AssetHealthBaseline
from app.services.asset_health_service import get_asset_health_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["asset-health"])


@router.get("/sites/{site_id}/assets/health-baseline")
async def get_site_asset_health(site_id: str) -> dict:
    """List baseline + health snapshot for all equipment at a site."""
    svc = get_asset_health_service()
    try:
        assets = await svc.get_site_assets(site_id)
    except Exception as e:
        logger.error("Failed to fetch asset health for site %s: %s", site_id, e)
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "site_id": site_id,
        "total": len(assets),
        "assets": [a.model_dump() for a in assets],
    }


@router.get("/equipment/{equipment_id}/health-baseline", response_model=AssetHealthBaseline)
async def get_equipment_health_baseline(equipment_id: str) -> AssetHealthBaseline:
    """Detailed baseline + health snapshot for a single equipment item."""
    svc = get_asset_health_service()
    try:
        detail = await svc.get_equipment_detail(equipment_id)
    except Exception as e:
        logger.error("Failed to fetch health-baseline for %s: %s", equipment_id, e)
        raise HTTPException(status_code=500, detail=str(e))

    if not detail:
        raise HTTPException(status_code=404, detail=f"Equipment '{equipment_id}' not found")

    return detail
