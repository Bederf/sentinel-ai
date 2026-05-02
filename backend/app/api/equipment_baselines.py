"""
Equipment Baselines Seed API (Phase 206-01)

REST API for seeding baselines during asset onboarding.
Provides /api/equipment/baselines/seed endpoint for CLI/batch seeding.

Phase: 206-asset-onboarding
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from app.database.repositories.baseline_repository import BaselineRepository
from app.models.baseline import BaselineSource, EquipmentBaseline
from app.services.baseline_seed_service import BaselineSeedService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/equipment/baselines", tags=["equipment-baselines"])


@router.post("/seed", response_model=dict[str, Any], status_code=201)
async def seed_equipment_baseline(
    equipment_id: str,
    site_id: str,
    source: BaselineSource = BaselineSource.BMS_AVERAGE,
    captured_by: str = "automated",
) -> dict[str, Any]:
    """
    Seed a baseline for equipment.

    Args:
        equipment_id: Equipment identifier
        site_id: Site identifier
        source: Baseline source (BMS_AVERAGE, MANUAL, etc.)
        captured_by: Who/what captured the baseline

    Returns:
        Result dict with status, baseline_id, equipment_id

    Raises:
        404: Equipment not found
        500: Baseline capture failed
    """
    service = BaselineSeedService()

    try:
        baseline, status = await service.seed_for_equipment_with_fallback(
            equipment_id=equipment_id,
            site_id=site_id,
            captured_by=captured_by,
        )
        # source parameter is used when we enhance the service
        _ = source  # noqa: ARG001

        if baseline is None:
            raise HTTPException(
                status_code=500,
                detail=f"Baseline capture failed for {equipment_id}"
            )

        return {
            "status": status,
            "baseline_id": baseline.id,
            "equipment_id": equipment_id,
            "baseline": {
                "id": baseline.id,
                "equipment_id": baseline.equipment_id,
                "baseline_date": baseline.baseline_date.isoformat() if hasattr(baseline, 'baseline_date') else None,
                "captured_by": baseline.captured_by,
                "baseline_type": baseline.baseline_type.value if hasattr(baseline, 'baseline_type') else None,
                "status": baseline.status.value if hasattr(baseline, 'status') else None,
            },
        }

    except Exception as e:
        logger.error(f"Error seeding baseline for {equipment_id}: {e}")
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e)) from e
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/seed-batch", response_model=dict[str, Any], status_code=201)
async def seed_equipment_baselines_batch(
    equipment_ids: list[str],
    site_id: str,
    captured_by: str = "automated",
) -> dict[str, Any]:
    """
    Seed baselines for multiple equipment items.

    Args:
        equipment_ids: List of equipment identifiers
        site_id: Site identifier
        captured_by: Who/what captured the baselines

    Returns:
        Batch result with counts and per-equipment results
    """
    service = BaselineSeedService()

    try:
        results = await service.seed_batch(
            equipment_ids=equipment_ids,
            site_id=site_id,
            captured_by=captured_by,
        )

        seeded_count = sum(1 for r in results if r["status"] in ("seeded", "seeded_fallback"))
        skipped_count = 0
        error_count = sum(1 for r in results if r["status"] == "error")

        return {
            "site_id": site_id,
            "total_requested": len(equipment_ids),
            "seeded_count": seeded_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Error seeding baselines batch for site {site_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{equipment_id}", response_model=EquipmentBaseline)
async def get_equipment_baseline(
    equipment_id: str,
) -> EquipmentBaseline:
    """
    Get active baseline for equipment.

    Returns the most recent active baseline.
    """
    repo = BaselineRepository()
    baseline = await repo.get_active_equipment_baseline(equipment_id)

    if not baseline:
        raise HTTPException(
            status_code=404,
            detail=f"No active baseline found for equipment {equipment_id}"
        )

    return baseline