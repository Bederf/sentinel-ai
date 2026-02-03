"""
Equipment Baseline API Endpoints

REST API for equipment baseline capture and retrieval.
Provides CRUD operations for equipment-level baseline data.

Phase 54-01: Equipment Baseline Assessment - Wave 1
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from app.models.baseline import (
    EquipmentBaselineCreate,
    EquipmentBaseline,
    BaselineComparison,
    ComparisonResult,
    DeviationStatus,
    BaselineType,
    BaselineSource,
)
from app.database.repositories.baseline_repository import BaselineRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/equipment/baseline", tags=["baselines"])

# Global repository instance
_baseline_repo: Optional[BaselineRepository] = None


def get_baseline_repository() -> BaselineRepository:
    """Get or create baseline repository instance."""
    global _baseline_repo
    if _baseline_repo is None:
        _baseline_repo = BaselineRepository()
    return _baseline_repo


# ============================================================================
# Request/Response Models
# ============================================================================

class BaselineCaptureRequest(BaseModel):
    """Request to capture equipment baseline."""
    captured_by: str = Field(..., description="Technician name or system identifier")
    baseline_type: BaselineType = Field(default=BaselineType.INITIAL, description="Type of baseline")
    baseline_values: Dict[str, Any] = Field(..., description="Baseline measurement values", min_length=1)
    measurement_conditions: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Measurement context")
    source_type: BaselineSource = Field(default=BaselineSource.MANUAL, description="Data source")
    notes: Optional[str] = Field(None, description="Capture notes")
    attachment_urls: Optional[List[str]] = Field(default_factory=list, description="Documentation URLs")


class CurrentDataRequest(BaseModel):
    """Request containing current readings for comparison."""
    current_values: Dict[str, float] = Field(..., description="Current equipment readings")
    data_source: str = Field(default="bms_sensor", description="Source of current data")


class ComparisonResponse(BaseModel):
    """Response from baseline comparison."""
    equipment_id: str
    baseline_id: str
    baseline_date: datetime
    comparison_date: datetime
    overall_status: DeviationStatus
    max_deviation_percent: float
    deviations: Dict[str, ComparisonResult]
    comparison_notes: Optional[str] = None


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/{equipment_id}", response_model=EquipmentBaseline, status_code=201)
async def capture_equipment_baseline(
    equipment_id: str,
    request: BaselineCaptureRequest
) -> EquipmentBaseline:
    """
    Capture baseline for equipment.

    Creates a new baseline record with element-level readings.
    Each element in baseline_values should have value, unit, and tolerance.

    Example baseline_values:
    {
        "filter_dp": {"value": 250, "unit": "Pa", "tolerance": 50},
        "vibration": {"value": 1.2, "unit": "mm/s", "tolerance": 0.5},
        "discharge_temp": {"value": 72, "unit": "°C", "tolerance": 5},
        "oil_pressure": {"value": 45, "unit": "PSI", "tolerance": 10}
    }
    """
    try:
        repo = get_baseline_repository()

        # Validate at least one element
        if not request.baseline_values:
            raise HTTPException(
                status_code=400,
                detail="At least one baseline value required"
            )

        # Create baseline
        baseline = await repo.create_equipment_baseline(
            equipment_id=equipment_id,
            captured_by=request.captured_by,
            baseline_type=request.baseline_type.value,
            baseline_values=request.baseline_values,
            measurement_conditions=request.measurement_conditions,
            source_type=request.source_type.value,
            notes=request.notes,
            attachment_urls=request.attachment_urls
        )

        logger.info(f"Captured baseline {baseline.id} for equipment {equipment_id}")
        return baseline

    except Exception as e:
        logger.error(f"Error capturing baseline for {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{equipment_id}", response_model=EquipmentBaseline)
async def get_latest_baseline(equipment_id: str) -> EquipmentBaseline:
    """
    Get latest active baseline for equipment.

    Returns the most recent baseline with status='active'.
    Raises 404 if no baseline found.
    """
    try:
        repo = get_baseline_repository()
        baseline = await repo.get_active_equipment_baseline(equipment_id)

        if not baseline:
            raise HTTPException(
                status_code=404,
                detail=f"No active baseline found for equipment {equipment_id}"
            )

        return baseline

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting baseline for {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{equipment_id}/history", response_model=List[EquipmentBaseline])
async def get_baseline_history(
    equipment_id: str,
    limit: int = Query(10, ge=1, le=100, description="Number of records to return")
) -> List[EquipmentBaseline]:
    """
    Get baseline history for equipment.

    Returns historical baselines ordered by date (newest first).
    Useful for tracking equipment condition over time.
    """
    try:
        repo = get_baseline_repository()
        baselines = await repo.get_equipment_baseline_history(
            equipment_id=equipment_id,
            limit=limit
        )

        logger.info(f"Retrieved {len(baselines)} baselines for {equipment_id}")
        return baselines

    except Exception as e:
        logger.error(f"Error getting baseline history for {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{equipment_id}/compare", response_model=ComparisonResponse)
async def compare_to_baseline(
    equipment_id: str,
    request: CurrentDataRequest
) -> ComparisonResponse:
    """
    Compare current readings to baseline.

    Calculates deviations for each metric and determines overall status.
    Deviations beyond tolerance trigger warning/critical alerts.

    Comparison logic:
    - deviation_percent = |current - baseline| / baseline * 100
    - status = normal if deviation <= tolerance
    - status = warning if deviation > tolerance but < 2*tolerance
    - status = critical if deviation >= 2*tolerance

    This is a placeholder implementation. Full comparison service
    will be implemented in Phase 54-02.
    """
    try:
        repo = get_baseline_repository()

        # Get active baseline
        baseline = await repo.get_active_equipment_baseline(equipment_id)
        if not baseline:
            raise HTTPException(
                status_code=404,
                detail=f"No active baseline found for equipment {equipment_id}"
            )

        # Perform comparison (simplified for now)
        deviations = {}
        max_deviation = 0.0
        critical_count = 0
        warning_count = 0

        for metric_name, current_value in request.current_values.items():
            # Extract baseline data
            baseline_data = baseline.baseline_values.get(metric_name)

            if not baseline_data:
                logger.warning(f"Metric {metric_name} not found in baseline")
                continue

            # Handle both simple values and complex structures
            if isinstance(baseline_data, dict):
                baseline_value = baseline_data.get("value")
                tolerance = baseline_data.get("tolerance", 10)  # Default 10%
            else:
                baseline_value = baseline_data
                tolerance = 10  # Default 10% tolerance

            # Calculate deviation
            if baseline_value != 0:
                deviation_percent = abs(current_value - baseline_value) / baseline_value * 100
            else:
                deviation_percent = 0.0

            # Determine status
            if deviation_percent >= tolerance * 2:
                status = DeviationStatus.CRITICAL
                critical_count += 1
            elif deviation_percent > tolerance:
                status = DeviationStatus.WARNING
                warning_count += 1
            else:
                status = DeviationStatus.NORMAL

            # Track max deviation
            if deviation_percent > max_deviation:
                max_deviation = deviation_percent

            # Create comparison result
            deviations[metric_name] = ComparisonResult(
                baseline=float(baseline_value),
                current=float(current_value),
                deviation_percent=round(deviation_percent, 2),
                status=status
            )

        # Determine overall status
        if critical_count > 0:
            overall_status = DeviationStatus.CRITICAL
        elif warning_count > 0:
            overall_status = DeviationStatus.WARNING
        else:
            overall_status = DeviationStatus.NORMAL

        # Build response
        response = ComparisonResponse(
            equipment_id=equipment_id,
            baseline_id=baseline.id,
            baseline_date=baseline.baseline_date,
            comparison_date=datetime.now(),
            overall_status=overall_status,
            max_deviation_percent=round(max_deviation, 2),
            deviations=deviations,
            comparison_notes=f"Compared {len(deviations)} metrics: {critical_count} critical, {warning_count} warning"
        )

        logger.info(
            f"Comparison for {equipment_id}: {overall_status.value}, "
            f"max deviation: {max_deviation:.2f}%"
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing baseline for {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{equipment_id}/summary")
async def get_baseline_summary(equipment_id: str) -> Dict[str, Any]:
    """
    Get baseline summary statistics for equipment.

    Returns:
    - has_active_baseline: Boolean
    - total_baselines: Count
    - last_baseline_date: Most recent baseline
    - total_elements: Element count
    - elements_with_baselines: Elements that have baselines
    """
    try:
        repo = get_baseline_repository()
        summary = await repo.get_baseline_summary(equipment_id)

        return summary

    except Exception as e:
        logger.error(f"Error getting baseline summary for {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Health Check
# ============================================================================

@router.get("/health", tags=["baselines"])
async def health_check() -> Dict[str, str]:
    """Baseline API health check."""
    return {
        "service": "equipment-baseline-api",
        "status": "healthy",
        "version": "1.0.0"
    }
