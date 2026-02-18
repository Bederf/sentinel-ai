"""
Condition Analysis API (Phase 56-01, 56-02, 56-03)

REST endpoints for element-level condition trending, degradation analysis,
remaining useful life (RUL) predictions, and service optimization.

Endpoints:
- GET  /api/condition/trends/{equipment_id}                - Equipment trend summary
- GET  /api/condition/trends/{equipment_id}/{element_name} - Specific element trend
- GET  /api/condition/degradation-rates/{equipment_id}     - All degradation rates
- POST /api/condition/analyze-changes                      - Full analysis (ROADMAP spec)
- GET  /api/condition/rul/{equipment_id}                   - RUL prediction
- GET  /api/condition/recommendations/{equipment_id}       - Service recommendations
- GET  /api/condition/fleet-risk                           - Fleet-wide risk overview
- POST /api/condition/optimize-service-schedule             - Fleet schedule optimization (ROADMAP spec)
- GET  /api/condition/utilization/{equipment_id}            - Asset utilization tracking
- GET  /api/condition/cost-comparison/{equipment_id}        - Fixed vs conditional cost comparison
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.condition import (
    EquipmentTrendSummary,
    ElementTrend,
    DegradationRate,
    AnalyzeChangesRequest,
    TrendDirection,
    EquipmentRUL,
    ServiceRecommendation,
    AssetUtilization,
    MaintenanceCostComparison,
    OptimizedSchedule,
    OptimizeScheduleRequest,
)
from app.services.element_trend_service import get_element_trend_service
from app.services.rul_calculator import get_rul_calculator
from app.services.service_optimizer import get_service_optimizer

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


# ============================================================================
# RUL Prediction Endpoints (Phase 56-02)
# ============================================================================

@router.get(
    "/rul/{equipment_id}",
    response_model=EquipmentRUL,
    summary="Get equipment RUL prediction",
    description="Returns Remaining Useful Life prediction for all elements of an equipment item."
)
async def get_equipment_rul(
    equipment_id: str,
    days: int = Query(default=90, ge=1, le=365, description="History window in days for trend calculation")
):
    """Get RUL prediction for equipment."""
    try:
        calculator = get_rul_calculator()
        rul = await calculator.calculate_equipment_rul(equipment_id, days=days)
        return rul
    except Exception as e:
        logger.error(f"Error calculating RUL for {equipment_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating RUL: {str(e)}"
        )


@router.get(
    "/recommendations/{equipment_id}",
    response_model=List[ServiceRecommendation],
    summary="Get service recommendations",
    description="Returns prioritized service recommendations for degrading elements."
)
async def get_recommendations(
    equipment_id: str,
    days: int = Query(default=90, ge=1, le=365, description="History window in days")
):
    """Get service recommendations for equipment."""
    try:
        calculator = get_rul_calculator()
        recommendations = await calculator.get_service_recommendations(equipment_id, days=days)
        return recommendations
    except Exception as e:
        logger.error(f"Error generating recommendations for {equipment_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating recommendations: {str(e)}"
        )


@router.get(
    "/fleet-risk",
    response_model=List[EquipmentRUL],
    summary="Get fleet-wide risk overview",
    description="Returns RUL for all equipment, sorted by days until first threshold ascending."
)
async def get_fleet_risk(
    risk_level: Optional[str] = Query(
        default=None,
        description="Filter by minimum risk level (low, medium, high, critical)"
    ),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results to return")
):
    """Get fleet-wide RUL risk overview."""
    try:
        # Load equipment list from equipment.json
        equipment_path = Path(__file__).parent.parent / "data" / "equipment.json"
        equipment_list = []

        if equipment_path.exists():
            with open(equipment_path, "r") as f:
                equipment_list = json.load(f)
        else:
            logger.warning(f"Equipment data not found at {equipment_path}")
            return []

        calculator = get_rul_calculator()

        # Calculate RUL for each equipment
        all_ruls: List[EquipmentRUL] = []
        for eq in equipment_list:
            eq_id = eq.get("id", "")
            if not eq_id:
                continue

            try:
                rul = await calculator.calculate_equipment_rul(eq_id)
                # Populate equipment_type from the data if not set
                if not rul.equipment_type:
                    rul.equipment_type = eq.get("type")
                all_ruls.append(rul)
            except Exception as e:
                logger.debug(f"Skipping {eq_id} in fleet risk: {e}")
                continue

        # Filter by minimum risk level if specified
        if risk_level:
            risk_order = {
                "low": 0, "medium": 1, "high": 2, "critical": 3
            }
            min_level = risk_order.get(risk_level.lower(), 0)
            all_ruls = [
                r for r in all_ruls
                if risk_order.get(r.overall_risk_level.value, 0) >= min_level
            ]

        # Sort by days_until_first_threshold ascending (None = infinity at end)
        all_ruls.sort(
            key=lambda r: (
                r.days_until_first_threshold if r.days_until_first_threshold is not None else float("inf")
            )
        )

        # Apply limit
        return all_ruls[:limit]

    except Exception as e:
        logger.error(f"Error calculating fleet risk: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating fleet risk: {str(e)}"
        )


# ============================================================================
# Service Optimization Endpoints (Phase 56-03)
# ============================================================================

@router.post(
    "/optimize-service-schedule",
    response_model=OptimizedSchedule,
    summary="Optimize fleet service schedule",
    description=(
        "Returns optimized maintenance schedule for specified equipment or full fleet. "
        "Compares condition-based timing against fixed-schedule approach. "
        "Matches ROADMAP spec endpoint."
    )
)
async def optimize_service_schedule(request: OptimizeScheduleRequest):
    """Optimize service schedule for fleet or specific equipment."""
    try:
        optimizer = get_service_optimizer()
        schedule = await optimizer.optimize_fleet_schedule(
            equipment_ids=request.equipment_ids,
            fixed_interval_days=request.fixed_interval_days,
        )
        return schedule
    except Exception as e:
        logger.error(f"Error optimizing service schedule: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error optimizing service schedule: {str(e)}"
        )


@router.get(
    "/utilization/{equipment_id}",
    response_model=List[AssetUtilization],
    summary="Get asset utilization",
    description=(
        "Returns utilization percentages for all monitored elements of an equipment item. "
        "Shows how much of each component's usable life has been consumed."
    )
)
async def get_utilization(equipment_id: str):
    """Get asset utilization for all elements of equipment."""
    try:
        optimizer = get_service_optimizer()
        utilizations = await optimizer.calculate_utilization(equipment_id)

        if not utilizations:
            # Return empty list with informative log
            logger.info(
                f"No utilization data for {equipment_id} - "
                f"no inspection data or thresholds available"
            )

        return utilizations
    except Exception as e:
        logger.error(f"Error calculating utilization for {equipment_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating utilization: {str(e)}"
        )


@router.get(
    "/cost-comparison/{equipment_id}",
    response_model=MaintenanceCostComparison,
    summary="Get maintenance cost comparison",
    description=(
        "Compares fixed-schedule vs condition-based maintenance costs for equipment. "
        "Shows potential savings from adopting condition-based approach."
    )
)
async def get_cost_comparison(
    equipment_id: str,
    fixed_interval_days: int = Query(
        default=90,
        ge=7,
        le=365,
        description="Fixed-schedule interval in days for comparison (default 90 = quarterly)"
    )
):
    """Compare fixed vs condition-based maintenance costs."""
    try:
        optimizer = get_service_optimizer()
        comparison = await optimizer.compare_maintenance_costs(
            equipment_id=equipment_id,
            fixed_interval_days=fixed_interval_days,
        )
        return comparison
    except Exception as e:
        logger.error(f"Error comparing costs for {equipment_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error comparing maintenance costs: {str(e)}"
        )


# ============================================================================
# Helper Functions
# ============================================================================

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
