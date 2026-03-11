"""
Equipment Baseline API Endpoints

REST API for equipment baseline capture and retrieval.
Provides CRUD operations for equipment-level baseline data.

Phase 54-01: Equipment Baseline Assessment - Wave 1
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.middleware.auth_middleware import require_equipment_access
from app.models.auth import AuthContext
from pydantic import BaseModel, Field

from app.models.baseline import (
    EquipmentBaseline,
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
    request: BaselineCaptureRequest,
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
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
            raise HTTPException(status_code=400, detail="At least one baseline value required")

        # Create baseline
        baseline = await repo.create_equipment_baseline(
            equipment_id=equipment_id,
            captured_by=request.captured_by,
            baseline_type=request.baseline_type.value,
            baseline_values=request.baseline_values,
            measurement_conditions=request.measurement_conditions,
            source_type=request.source_type.value,
            notes=request.notes,
            attachment_urls=request.attachment_urls,
        )

        logger.info(f"Captured baseline {baseline.id} for equipment {equipment_id}")
        return baseline

    except Exception as e:
        logger.error(f"Error capturing baseline for {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{equipment_id}", response_model=EquipmentBaseline)
async def get_latest_baseline(
    equipment_id: str, auth: AuthContext = Depends(require_equipment_access("equipment_id"))
) -> EquipmentBaseline:
    """
    Get latest active baseline for equipment.

    Returns the most recent baseline with status='active'.
    Raises 404 if no baseline found.
    """
    try:
        repo = get_baseline_repository()
        baseline = await repo.get_active_equipment_baseline(equipment_id)

        if not baseline:
            raise HTTPException(status_code=404, detail=f"No active baseline found for equipment {equipment_id}")

        return baseline

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting baseline for {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{equipment_id}/history", response_model=List[EquipmentBaseline])
async def get_baseline_history(
    equipment_id: str,
    limit: int = Query(10, ge=1, le=100, description="Number of records to return"),
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
) -> List[EquipmentBaseline]:
    """
    Get baseline history for equipment.

    Returns historical baselines ordered by date (newest first).
    Useful for tracking equipment condition over time.
    """
    try:
        repo = get_baseline_repository()
        baselines = await repo.get_equipment_baseline_history(equipment_id=equipment_id, limit=limit)

        logger.info(f"Retrieved {len(baselines)} baselines for {equipment_id}")
        return baselines

    except Exception as e:
        logger.error(f"Error getting baseline history for {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{equipment_id}/compare", response_model=ComparisonResponse)
async def compare_to_baseline(
    equipment_id: str,
    request: CurrentDataRequest,
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
) -> ComparisonResponse:
    """
    Compare current readings to baseline.

    Calculates deviations for each metric and determines overall status.
    Deviations beyond tolerance trigger warning/critical alerts.

    Uses BaselineComparisonService for deviation detection.

    Integration with workflow triggers:
    - Deviations > 20% trigger baseline deviation alert
    - Critical deviations create inspection tasks
    """
    try:
        from app.services.baseline_comparison_service import get_baseline_comparison_service
        from app.services.workflow_triggers import get_trigger_engine, BaselineComparison as WorkflowBaselineComparison

        # Get comparison service
        comparison_service = get_baseline_comparison_service()

        # Perform comparison
        comparison = await comparison_service.compare_to_baseline(
            equipment_id=equipment_id, current_data=request.current_values
        )

        # Build deviations dict for response
        deviations_dict = {}
        for dev in comparison.deviations:
            deviations_dict[dev.element_name] = ComparisonResult(
                baseline=dev.baseline_value,
                current=dev.current_value,
                deviation_percent=dev.deviation_percent,
                status=DeviationStatus(dev.severity),
            )

        # Build response
        response = ComparisonResponse(
            equipment_id=equipment_id,
            baseline_id=comparison.baseline_id,
            baseline_date=comparison.baseline_date,
            comparison_date=comparison.comparison_date,
            overall_status=comparison.overall_status,
            max_deviation_percent=comparison.max_deviation_percent,
            deviations=deviations_dict,
            comparison_notes=comparison.summary,
        )

        logger.info(
            f"Comparison for {equipment_id}: {comparison.overall_status.value}, "
            f"max deviation: {comparison.max_deviation_percent:.2f}%"
        )

        # Trigger workflow alert if significant deviation
        if comparison.max_deviation_percent > 20.0:
            try:
                trigger_engine = get_trigger_engine()
                workflow_comparison = WorkflowBaselineComparison(
                    equipment_id=equipment_id,
                    baseline_id=comparison.baseline_id,
                    comparison_date=comparison.comparison_date,
                    max_deviation_percent=comparison.max_deviation_percent,
                    deviating_metrics={d.element_name: d.deviation_percent for d in comparison.deviations},
                    within_threshold=False,
                )

                trigger_result = await trigger_engine.on_baseline_deviation(
                    equipment_id=equipment_id, comparison=workflow_comparison
                )

                logger.info(f"Workflow trigger result: {trigger_result.action_taken}")

            except Exception as trigger_error:
                logger.error(f"Failed to trigger workflow alert: {trigger_error}")
                # Don't fail the request if workflow trigger fails

        return response

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing baseline for {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{equipment_id}/summary")
async def get_baseline_summary(
    equipment_id: str, auth: AuthContext = Depends(require_equipment_access("equipment_id"))
) -> Dict[str, Any]:
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


@router.get("/{equipment_id}/report")
async def get_baseline_report(
    equipment_id: str,
    baseline_id: Optional[str] = Query(None, description="Specific baseline ID (uses latest if None)"),
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
):
    """
    Generate PDF baseline report.

    Returns PDF file with:
    - Equipment details and baseline date
    - Baseline values table
    - Current comparison (if available)
    - Color-coded deviations (red=critical, yellow=warning)
    - Technician notes section
    """
    try:
        from fastapi.responses import Response
        from app.services.baseline_comparison_service import get_baseline_comparison_service
        from datetime import datetime

        comparison_service = get_baseline_comparison_service()
        repo = get_baseline_repository()

        # Get baseline
        if baseline_id:
            baseline = await repo.get_baseline_by_id(baseline_id)
        else:
            baseline = await repo.get_active_equipment_baseline(equipment_id)

        if not baseline:
            raise HTTPException(status_code=404, detail=f"No baseline found for equipment {equipment_id}")

        # Generate PDF report
        pdf_bytes = await comparison_service.generate_baseline_report(
            equipment_id=equipment_id,
            baseline=baseline,
            comparison=None,  # Could optionally include latest comparison
        )

        # Return PDF file
        filename = f"baseline_{equipment_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating report for {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Health Check
# ============================================================================


@router.get("/health", tags=["baselines"])
async def health_check() -> Dict[str, str]:
    """Baseline API health check."""
    return {"service": "equipment-baseline-api", "status": "healthy", "version": "1.0.0"}
