"""
Condition Analysis API (Phase 56-01)

REST endpoints for element-level condition trending and degradation analysis.

Endpoints:
- GET  /api/condition/trends/{equipment_id}              - Equipment trend summary
- GET  /api/condition/trends/{equipment_id}/{element_name} - Specific element trend
- GET  /api/condition/degradation-rates/{equipment_id}    - All degradation rates
- POST /api/condition/analyze-changes                     - Full analysis (ROADMAP spec)
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Query

from app.models.condition import (
    EquipmentTrendSummary,
    ElementTrend,
    DegradationRate,
    AnalyzeChangesRequest,
    TrendDirection,
)
from app.services.element_trend_service import get_element_trend_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/condition", tags=["condition"])


@router.get(
    "/trends/{equipment_id}",
    response_model=EquipmentTrendSummary,
    summary="Get equipment trend summary",
    description="Returns trend analysis for all monitored elements of an equipment item."
)
async def get_equipment_trends(
    equipment_id: str,
    days: int = Query(default=90, ge=1, le=365, description="History window in days")
):
    """Get trend analysis for all elements of an equipment."""
    try:
        service = get_element_trend_service()
        summary = await service.get_equipment_trend_summary(equipment_id, days=days)
        return summary
    except Exception as e:
        logger.error(f"Error calculating trends for {equipment_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating trends: {str(e)}"
        )


@router.get(
    "/trends/{equipment_id}/{element_name}",
    response_model=ElementTrend,
    summary="Get element trend detail",
    description="Returns detailed trend for a specific element of an equipment item."
)
async def get_element_trend(
    equipment_id: str,
    element_name: str,
    days: int = Query(default=90, ge=1, le=365, description="History window in days")
):
    """Get detailed trend for a specific element."""
    try:
        service = get_element_trend_service()
        points = await service.get_element_history(equipment_id, element_name, days=days)

        if not points:
            return ElementTrend(
                element_name=element_name,
                equipment_id=equipment_id,
                measurement_type="unknown",
                data_points=[],
                trend_direction=TrendDirection.STABLE,
                days_of_data=0
            )

        # Calculate degradation rate and trend
        rate = service.calculate_degradation_rate(points)
        rate.element_name = element_name
        direction = service.classify_trend(rate)

        days_span = 0
        if len(points) >= 2:
            days_span = int(
                (points[-1].timestamp - points[0].timestamp).total_seconds() / 86400.0
            )

        # Infer measurement type from first point's unit
        measurement_type = _infer_measurement_type(points[0].unit if points else "")

        return ElementTrend(
            element_name=element_name,
            equipment_id=equipment_id,
            measurement_type=measurement_type,
            data_points=points,
            degradation_rate_per_day=rate.rate_per_day,
            trend_direction=direction,
            r_squared=rate.confidence,
            days_of_data=days_span
        )

    except Exception as e:
        logger.error(f"Error calculating trend for {equipment_id}/{element_name}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating element trend: {str(e)}"
        )


@router.get(
    "/degradation-rates/{equipment_id}",
    response_model=List[DegradationRate],
    summary="Get degradation rates",
    description="Returns degradation rates for all monitored elements of an equipment item."
)
async def get_degradation_rates(
    equipment_id: str,
    days: int = Query(default=90, ge=1, le=365, description="History window in days")
):
    """Get degradation rates for all elements."""
    try:
        service = get_element_trend_service()
        summary = await service.get_equipment_trend_summary(equipment_id, days=days)

        rates: List[DegradationRate] = []
        for trend in summary.element_trends:
            if trend.degradation_rate_per_day is not None:
                rate = DegradationRate(
                    element_name=trend.element_name,
                    rate_per_day=trend.degradation_rate_per_day,
                    rate_per_month=trend.degradation_rate_per_day * 30.0,
                    unit=trend.data_points[0].unit if trend.data_points else "",
                    confidence=trend.r_squared or 0.0
                )
                rates.append(rate)

        return rates

    except Exception as e:
        logger.error(f"Error calculating degradation rates for {equipment_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating degradation rates: {str(e)}"
        )


@router.post(
    "/analyze-changes",
    response_model=EquipmentTrendSummary,
    summary="Analyze equipment changes",
    description="Runs full trend analysis and returns results. Matches ROADMAP spec endpoint."
)
async def analyze_changes(request: AnalyzeChangesRequest):
    """Run full analysis and return results."""
    try:
        service = get_element_trend_service()

        if request.element_name:
            # Analyze single element, return as summary with one trend
            points = await service.get_element_history(
                request.equipment_id, request.element_name, days=90
            )

            if not points:
                return EquipmentTrendSummary(
                    equipment_id=request.equipment_id,
                    element_trends=[],
                    overall_trend_direction=TrendDirection.STABLE,
                    condition_score=100.0,
                    message=f"No data found for element {request.element_name}"
                )

            rate = service.calculate_degradation_rate(points)
            rate.element_name = request.element_name
            direction = service.classify_trend(rate)

            days_span = 0
            if len(points) >= 2:
                days_span = int(
                    (points[-1].timestamp - points[0].timestamp).total_seconds() / 86400.0
                )

            measurement_type = _infer_measurement_type(points[0].unit if points else "")

            trend = ElementTrend(
                element_name=request.element_name,
                equipment_id=request.equipment_id,
                measurement_type=measurement_type,
                data_points=points,
                degradation_rate_per_day=rate.rate_per_day,
                trend_direction=direction,
                r_squared=rate.confidence,
                days_of_data=days_span
            )

            score = 100.0
            if direction == TrendDirection.DEGRADING:
                score = 60.0
            elif direction == TrendDirection.RAPID_DEGRADING:
                score = 30.0

            return EquipmentTrendSummary(
                equipment_id=request.equipment_id,
                element_trends=[trend],
                worst_element=request.element_name if direction in (
                    TrendDirection.DEGRADING, TrendDirection.RAPID_DEGRADING
                ) else None,
                overall_trend_direction=direction,
                condition_score=score,
                message=f"Analysis complete for {request.element_name}: {direction.value}"
            )

        else:
            # Full equipment analysis
            summary = await service.get_equipment_trend_summary(request.equipment_id)
            return summary

    except Exception as e:
        logger.error(f"Error analyzing changes for {request.equipment_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error analyzing changes: {str(e)}"
        )


def _infer_measurement_type(unit: str) -> str:
    """Infer measurement type from unit string."""
    unit_lower = unit.lower().strip()
    if unit_lower in ("mm/s", "m/s2", "m/s²", "g"):
        return "vibration"
    elif unit_lower in ("c", "°c", "f", "°f"):
        return "temperature"
    elif unit_lower in ("bar", "kpa", "psi", "pa"):
        return "pressure"
    elif unit_lower in ("a", "v", "kw", "w"):
        return "electrical"
    elif unit_lower in ("dba", "db"):
        return "sound"
    elif unit_lower in ("l/s", "m3/h"):
        return "flow"
    else:
        return "general"
