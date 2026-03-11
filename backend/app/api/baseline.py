"""
Baseline Assessment API - REST endpoints for equipment baseline management

Phase 44: Asset Baseline Assessment

Provides endpoints for:
- Capturing equipment baselines
- Comparing current readings to baselines
- Element-level baseline tracking
- Baseline history and reporting
"""

from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query, status

from app.middleware.auth_middleware import require_equipment_access
from app.models.auth import AuthContext

from app.models.baseline import (
    EquipmentBaseline,
    ElementBaseline,
    BaselineComparison,
    EquipmentElement,
    ManualBaselineCaptureRequest,
    ElementBaselineCaptureRequest,
    BaselineCaptureResponse,
    BaselineComparisonResponse,
    BaselineReportResponse,
    DeviationStatus,
)
from app.services.baseline_service import get_baseline_service
from app.services.baseline_report_service import get_baseline_report_service
from app.services.auth_service import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/equipment", tags=["baseline"])


# ============================================================================
# Equipment Baseline Endpoints
# ============================================================================


@router.post(
    "/{equipment_id}/baseline",
    response_model=BaselineCaptureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Capture new equipment baseline",
    description="Capture baseline readings for equipment. Can be manual entry or automated from BMS sensors.",
)
async def capture_equipment_baseline(
    equipment_id: str,
    request: ManualBaselineCaptureRequest,
    current_user: User = Depends(get_current_user),
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
):
    """Capture a new baseline for equipment."""
    service = get_baseline_service()

    try:
        baseline = await service.capture_equipment_baseline(
            equipment_id=equipment_id,
            captured_by=request.captured_by or current_user.username,
            baseline_type=request.baseline_type,
            notes=request.notes,
            baseline_values=request.baseline_values,
            measurement_conditions=request.measurement_conditions,
            source_type="manual",
            attachment_urls=request.attachment_urls,
        )

        return BaselineCaptureResponse(
            success=True,
            message="Baseline captured successfully",
            baseline_id=baseline.id,
            equipment_id=equipment_id,
            metrics_captured=len(baseline.baseline_values),
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to capture baseline: {str(e)}"
        )


@router.post(
    "/{equipment_id}/baseline/automated",
    response_model=BaselineCaptureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Capture automated baseline from BMS",
    description="Automatically capture baseline by averaging BMS sensor readings over 24 hours",
)
async def capture_automated_baseline(
    equipment_id: str,
    baseline_type: str = "periodic",
    captured_by: str = "automated",
    current_user: User = Depends(get_current_user),
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
):
    """Capture automated baseline from BMS sensor averages."""
    service = get_baseline_service()

    try:
        baseline = await service.capture_equipment_baseline(
            equipment_id=equipment_id, captured_by=captured_by, baseline_type=baseline_type, source_type="bms_average"
        )

        return BaselineCaptureResponse(
            success=True,
            message="Automated baseline captured successfully",
            baseline_id=baseline.id,
            equipment_id=equipment_id,
            metrics_captured=len(baseline.baseline_values),
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to capture automated baseline: {str(e)}"
        )


@router.get(
    "/{equipment_id}/baseline",
    response_model=Optional[EquipmentBaseline],
    summary="Get current active baseline",
    description="Retrieve the most recent active baseline for equipment",
)
async def get_active_baseline(
    equipment_id: str,
    current_user: User = Depends(get_current_user),
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
):
    """Get current active baseline for equipment."""
    service = get_baseline_service()

    baseline = await service.repository.get_active_equipment_baseline(equipment_id)
    if not baseline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No active baseline found for equipment {equipment_id}"
        )

    return baseline


@router.get(
    "/{equipment_id}/baseline/history",
    response_model=List[EquipmentBaseline],
    summary="Get baseline history",
    description="List all historical baselines for equipment",
)
async def get_baseline_history(
    equipment_id: str,
    limit: int = Query(10, ge=1, le=100, description="Maximum number of baselines to return"),
    current_user: User = Depends(get_current_user),
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
):
    """Get baseline history for equipment."""
    service = get_baseline_service()

    baselines = await service.get_baseline_history(equipment_id, limit)
    return baselines


@router.delete(
    "/{equipment_id}/baseline/{baseline_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive a baseline",
    description="Archive a baseline record (set status to archived)",
)
async def archive_baseline(
    equipment_id: str,
    baseline_id: str,
    current_user: User = Depends(get_current_user),
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
):
    """Archive a baseline record."""
    service = get_baseline_service()

    baseline = await service.repository.get_equipment_baseline(baseline_id)
    if not baseline or baseline.equipment_id != equipment_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Baseline not found")

    await service.repository.archive_equipment_baseline(baseline_id)
    return {"message": "Baseline archived successfully"}


# ============================================================================
# Baseline Comparison Endpoints
# ============================================================================


@router.post(
    "/{equipment_id}/baseline/compare",
    response_model=BaselineComparisonResponse,
    summary="Compare current readings to baseline",
    description="Compare current sensor readings to stored baseline and calculate deviations",
)
async def compare_to_baseline(
    equipment_id: str,
    current_values: Optional[Dict[str, Any]] = None,
    data_source: str = "bms_sensor",
    current_user: User = Depends(get_current_user),
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
):
    """Compare current readings to equipment baseline."""
    service = get_baseline_service()

    try:
        comparison = await service.compare_to_baseline(
            equipment_id=equipment_id, current_values=current_values, data_source=data_source
        )

        # Count statuses
        critical_count = sum(1 for r in comparison.comparison_results.values() if r.status == DeviationStatus.CRITICAL)
        warning_count = sum(1 for r in comparison.comparison_results.values() if r.status == DeviationStatus.WARNING)
        normal_count = sum(1 for r in comparison.comparison_results.values() if r.status == DeviationStatus.NORMAL)

        return BaselineComparisonResponse(
            success=True,
            comparison_id=comparison.id,
            overall_status=comparison.overall_status,
            max_deviation_percent=comparison.max_deviation_percent,
            critical_count=critical_count,
            warning_count=warning_count,
            normal_count=normal_count,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Comparison failed: {str(e)}")


@router.get(
    "/{equipment_id}/baseline/comparisons",
    response_model=List[BaselineComparison],
    summary="Get comparison history",
    description="List recent baseline comparison results",
)
async def get_comparison_history(
    equipment_id: str,
    limit: int = Query(10, ge=1, le=50, description="Maximum comparisons to return"),
    current_user: User = Depends(get_current_user),
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
):
    """Get recent baseline comparisons for equipment."""
    service = get_baseline_service()

    comparisons = await service.repository.get_recent_comparisons(equipment_id, limit)
    return comparisons


@router.get(
    "/{equipment_id}/baseline/deviations/critical",
    response_model=List[BaselineComparison],
    summary="Get critical deviations",
    description="List baseline comparisons with critical deviations in last 30 days",
)
async def get_critical_deviations(
    equipment_id: str,
    days: int = Query(30, ge=1, le=365, description="Lookback period in days"),
    current_user: User = Depends(get_current_user),
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
):
    """Get critical baseline deviations for equipment."""
    service = get_baseline_service()

    deviations = await service.repository.get_critical_deviations(equipment_id, days)
    return deviations


# ============================================================================
# Element Baseline Endpoints
# ============================================================================


@router.post(
    "/{equipment_id}/elements/{element_id}/baseline",
    response_model=BaselineCaptureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Capture element baseline",
    description="Capture baseline for a specific equipment element (bearing, filter, etc.)",
)
async def capture_element_baseline(
    equipment_id: str,
    element_id: str,
    request: ElementBaselineCaptureRequest,
    current_user: User = Depends(get_current_user),
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
):
    """Capture baseline for equipment element."""
    service = get_baseline_service()

    try:
        baseline = await service.capture_element_baseline(
            equipment_id=equipment_id,
            element_id=element_id,
            captured_by=request.captured_by or current_user.username,
            measurement_type=request.measurement_type,
            baseline_type=request.baseline_type,
            baseline_values=request.baseline_values,
            measurement_conditions=request.measurement_conditions,
            notes=request.notes,
            attachment_urls=request.attachment_urls,
        )

        return BaselineCaptureResponse(
            success=True,
            message="Element baseline captured successfully",
            baseline_id=baseline.id,
            equipment_id=equipment_id,
            metrics_captured=len(baseline.baseline_values),
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to capture element baseline: {str(e)}"
        )


@router.get(
    "/{equipment_id}/elements",
    response_model=List[EquipmentElement],
    summary="List equipment elements",
    description="Get all elements defined for equipment",
)
async def list_equipment_elements(
    equipment_id: str,
    current_user: User = Depends(get_current_user),
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
):
    """List all elements for equipment."""
    service = get_baseline_service()

    elements = await service.repository.get_equipment_elements(equipment_id)
    return elements


@router.get(
    "/{equipment_id}/elements/{element_id}/baseline",
    response_model=Optional[ElementBaseline],
    summary="Get active element baseline",
    description="Get the most recent active baseline for an element",
)
async def get_active_element_baseline(
    equipment_id: str,
    element_id: str,
    current_user: User = Depends(get_current_user),
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
):
    """Get active baseline for equipment element."""
    service = get_baseline_service()

    # Get element first
    element = await service.repository.get_element(equipment_id, element_id)
    if not element:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Element {element_id} not found for equipment {equipment_id}"
        )

    # Get active baseline
    baseline = await service.repository.get_active_element_baseline(element.id)
    if not baseline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No active baseline found for element {element_id}"
        )

    return baseline


# ============================================================================
# Reporting Endpoints
# ============================================================================


@router.get(
    "/{equipment_id}/baseline/report",
    response_model=BaselineReportResponse,
    summary="Generate baseline report",
    description="Generate comprehensive baseline assessment report for equipment",
)
async def get_baseline_report(
    equipment_id: str,
    current_user: User = Depends(get_current_user),
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
):
    """Generate comprehensive baseline report for equipment."""
    service = get_baseline_service()

    try:
        report = await service.get_baseline_report(equipment_id)
        return report

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to generate report: {str(e)}"
        )


@router.get(
    "/{equipment_id}/baseline/summary",
    summary="Get baseline summary",
    description="Get summary statistics about baseline status for equipment",
)
async def get_baseline_summary(
    equipment_id: str,
    current_user: User = Depends(get_current_user),
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
):
    """Get baseline summary for equipment."""
    service = get_baseline_service()

    summary = await service.repository.get_baseline_summary(equipment_id)
    return summary


@router.get(
    "/{equipment_id}/baseline/report/json",
    summary="Generate JSON baseline report",
    description="Generate comprehensive baseline assessment report in JSON format",
)
async def generate_json_report(
    equipment_id: str,
    include_elements: bool = Query(True, description="Include element-level baselines"),
    include_history: bool = Query(True, description="Include comparison history"),
    current_user: User = Depends(get_current_user),
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
):
    """Generate JSON baseline report."""
    report_service = get_baseline_report_service()

    try:
        report = await report_service.generate_json_report(
            equipment_id, include_element_baselines=include_elements, include_comparison_history=include_history
        )
        return report
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/{equipment_id}/baseline/report/html",
    summary="Generate HTML baseline report",
    description="Generate comprehensive baseline assessment report in HTML format",
)
async def generate_html_report(
    equipment_id: str,
    current_user: User = Depends(get_current_user),
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
):
    """Generate HTML baseline report."""
    report_service = get_baseline_report_service()

    try:
        html_content = await report_service.generate_html_report(equipment_id)
        return {"html": html_content}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/{equipment_id}/baseline/report/pdf",
    summary="Generate PDF baseline report",
    description="Generate comprehensive baseline assessment report in PDF format",
)
async def generate_pdf_report(
    equipment_id: str,
    current_user: User = Depends(get_current_user),
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
):
    """Generate PDF baseline report."""
    report_service = get_baseline_report_service()

    try:
        pdf_content = await report_service.generate_pdf_report(equipment_id)
        return {"pdf_content": pdf_content}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ============================================================================
# Bulk Operations
# ============================================================================


@router.post(
    "/baseline/capture-bulk",
    summary="Capture baselines for multiple equipment",
    description="Initiate automated baseline capture for list of equipment IDs",
)
async def capture_baselines_bulk(
    equipment_ids: List[str], baseline_type: str = "periodic", current_user: User = Depends(get_current_user)
):
    """Capture automated baselines for multiple equipment."""
    service = get_baseline_service()

    results = []
    for equipment_id in equipment_ids:
        try:
            baseline = await service.capture_equipment_baseline(
                equipment_id=equipment_id,
                captured_by=f"bulk_automated_by_{current_user.username}",
                baseline_type=baseline_type,
                source_type="bms_average",
            )
            results.append({"equipment_id": equipment_id, "success": True, "baseline_id": baseline.id})
        except Exception as e:
            results.append({"equipment_id": equipment_id, "success": False, "error": str(e)})

    return {
        "success": True,
        "results": results,
        "total": len(equipment_ids),
        "success_count": sum(1 for r in results if r["success"]),
    }
