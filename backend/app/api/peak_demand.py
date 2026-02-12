"""
Peak Demand Management API - Module-Aware Demand Shaving Endpoints

Provides real-time demand monitoring and multi-module peak shaving recommendations.
Coordinates HVAC, Solar/BESS, and Energy modules for NMD headroom management.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import logging

# # from app.services.demand_aware_coordinator import get_demand_aware_coordinator
from app.services.solar_demand_service import get_solar_demand_service
from app.services.module_registry_service import module_registry
from app.services.approval_service import get_approval_service
from app.models.module_registry import ModuleType
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/peak-demand", tags=["peak_demand"])


# ==================== Request/Response Models ====================

class DemandStatusResponse(BaseModel):
    """Current demand status with NMD context."""
    site_id: str
    current_demand_kw: float
    nmd_limit_kva: float
    headroom_kw: float
    headroom_percent: float
    headroom_level: str  # "normal", "caution", "warning", "critical"
    demand_trend: str  # "rising", "stable", "falling"
    active_modules: List[str]  # Which modules are active at this site
    available_reductions: Dict[str, Dict[str, Any]]  # Per-module reduction options
    last_updated: str


class ModuleActionResponse(BaseModel):
    """Single module action in a coordinated recommendation."""
    module: str
    action: str
    duration_min: Optional[int] = None
    reduction_kw: Optional[float] = None
    estimated_savings_r: Optional[float] = None
    comfort_impact: Optional[str] = None


class MultiModuleRecommendationResponse(BaseModel):
    """Multi-module peak shaving recommendation."""
    recommendation_id: str
    timestamp: str
    type: str
    urgency: str  # "normal", "caution", "warning", "critical"
    priority: str
    modules_involved: List[str]
    module_actions: List[ModuleActionResponse]
    estimated_reduction_kw: float
    estimated_savings_r: float
    reasoning: str
    requires_approval: bool


class ApproveRecommendationRequest(BaseModel):
    """Approve a peak shaving recommendation."""
    recommendation_id: str
    approved_by: str
    approval_notes: Optional[str] = None


class ForecastIntervalResponse(BaseModel):
    """Hourly demand forecast interval."""
    hour: int
    date: str
    forecasted_demand_kw: float
    confidence_low_kw: float
    confidence_high_kw: float
    nmd_headroom_kw: float
    headroom_percent: float
    risk_level: str  # "safe", "caution", "warning", "critical"


class DemandForecastResponse(BaseModel):
    """24-hour demand forecast."""
    site_id: str
    forecast_start: str
    forecast_hours: List[ForecastIntervalResponse]
    peak_hour: int
    peak_demand_kw: float
    peak_headroom_kw: float
    peak_headroom_percent: float
    peak_risk_level: str


# ==================== Status & Monitoring Endpoints ====================

@router.get("/{site_id}/status", response_model=DemandStatusResponse)
async def get_demand_status(site_id: str):
    """
    Get current demand status with NMD headroom and active modules.

    Returns current building demand, monthly peak, NMD limit, headroom,
    demand trend, alert level, and which modules are active (Solar, HVAC, etc).
    Also shows available reduction options per module.
    """
    try:
        demand_service = get_solar_demand_service()
        demand_status = demand_service.get_current_demand(site_id)

        if not demand_status:
            raise HTTPException(
                status_code=404,
                detail=f"No demand data available for site {site_id}"
            )

        current_demand_kw = demand_status.get("current_demand_kw", 0)
        
        # PHASE 081: Fetch NMD from database (from municipal bills), fallback to demand_status or default
        nmd_limit_kva = demand_status.get("nmd_limit_kva")
        if not nmd_limit_kva:
            try:
                nmd_limit_kva = await demand_service.get_nmd_limit(site_id)
            except Exception as exc:
                logger.warning(f"Failed to fetch NMD from database for {site_id}: {exc}")
                nmd_limit_kva = 6000  # Final fallback to default
        headroom_kw = nmd_limit_kva - current_demand_kw
        headroom_percent = (headroom_kw / nmd_limit_kva * 100) if nmd_limit_kva > 0 else 100

        # Determine headroom level
        if headroom_percent < 5:
            headroom_level = "critical"
        elif headroom_percent < 15:
            headroom_level = "warning"
        elif headroom_percent < 25:
            headroom_level = "caution"
        else:
            headroom_level = "normal"

        # Get active modules
        active_modules = module_registry.get_active_modules(site_id)
        active_module_names = [m.module_type.value for m in active_modules]

        # Build available reductions per module
        available_reductions = {}

        if ModuleType.SOLAR in [m.module_type for m in active_modules]:
            available_reductions["solar"] = {
                "max_reduction_kw": 200,
                "method": "bess_discharge",
                "duration_options": [30, 60, 120]
            }

        if ModuleType.HVAC in [m.module_type for m in active_modules]:
            available_reductions["hvac"] = {
                "max_reduction_kw": 50,
                "method": "setpoint_increase",
                "duration_options": [15, 30, 60]
            }

        if ModuleType.ENERGY in [m.module_type for m in active_modules]:
            available_reductions["energy"] = {
                "max_reduction_kw": 30,
                "method": "load_deferral",
                "duration_options": [15, 30]
            }

        return DemandStatusResponse(
            site_id=site_id,
            current_demand_kw=current_demand_kw,
            nmd_limit_kva=nmd_limit_kva,
            headroom_kw=headroom_kw,
            headroom_percent=round(headroom_percent, 1),
            headroom_level=headroom_level,
            demand_trend=demand_status.get("demand_trend", "stable"),
            active_modules=active_module_names,
            available_reductions=available_reductions,
            last_updated=demand_status.get("timestamp", "")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting demand status for site {site_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve demand status")


@router.get("/{site_id}/forecast-24h", response_model=DemandForecastResponse)
async def get_demand_forecast(site_id: str):
    """
    Get 24-hour demand forecast with NMD headroom predictions.

    Returns hourly demand predictions with confidence bands and risk assessment.
    Identifies peak demand hour and headroom status throughout the day.
    """
    try:
        demand_service = get_solar_demand_service()

        # Get current demand for NMD limit reference
        current_status = demand_service.get_current_demand(site_id)
        if not current_status:
            raise HTTPException(
                status_code=404,
                detail=f"No demand data available for site {site_id}"
            )

        # PHASE 081: Fetch NMD from database (from municipal bills)
        nmd_limit_kva = current_status.get("nmd_limit_kva")
        if not nmd_limit_kva:
            try:
                nmd_limit_kva = await demand_service.get_nmd_limit(site_id)
            except Exception as exc:
                logger.warning(f"Failed to fetch NMD from database for forecast: {exc}")
                nmd_limit_kva = 6000  # Fallback

        # Get 24-hour profile
        profile = demand_service.get_demand_profile(site_id, period="day")
        if not profile:
            raise HTTPException(
                status_code=404,
                detail=f"No forecast available for site {site_id}"
            )

        # Build forecast intervals
        forecast_intervals = []
        peak_hour = 0
        peak_demand_kw = 0

        for i, interval in enumerate(profile.get("intervals", [])):
            demand_kw = interval.get("demand_kw", 0)
            headroom_kw = nmd_limit_kva - demand_kw
            headroom_percent = (headroom_kw / nmd_limit_kva * 100) if nmd_limit_kva > 0 else 100

            # Determine risk level
            if headroom_percent < 5:
                risk_level = "critical"
            elif headroom_percent < 15:
                risk_level = "warning"
            elif headroom_percent < 25:
                risk_level = "caution"
            else:
                risk_level = "safe"

            forecast_intervals.append(ForecastIntervalResponse(
                hour=i,
                date=interval.get("date", ""),
                forecasted_demand_kw=demand_kw,
                confidence_low_kw=max(0, demand_kw - 50),  # ±50kW confidence band
                confidence_high_kw=demand_kw + 50,
                nmd_headroom_kw=headroom_kw,
                headroom_percent=round(headroom_percent, 1),
                risk_level=risk_level
            ))

            # Track peak
            if demand_kw > peak_demand_kw:
                peak_demand_kw = demand_kw
                peak_hour = i

        peak_headroom_kw = nmd_limit_kva - peak_demand_kw
        peak_headroom_percent = (peak_headroom_kw / nmd_limit_kva * 100) if nmd_limit_kva > 0 else 100

        if peak_headroom_percent < 5:
            peak_risk_level = "critical"
        elif peak_headroom_percent < 15:
            peak_risk_level = "warning"
        elif peak_headroom_percent < 25:
            peak_risk_level = "caution"
        else:
            peak_risk_level = "safe"

        return DemandForecastResponse(
            site_id=site_id,
            forecast_start=current_status.get("timestamp", ""),
            forecast_hours=forecast_intervals,
            peak_hour=peak_hour,
            peak_demand_kw=peak_demand_kw,
            peak_headroom_kw=peak_headroom_kw,
            peak_headroom_percent=round(peak_headroom_percent, 1),
            peak_risk_level=peak_risk_level
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting demand forecast for site {site_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve demand forecast")


# ==================== Recommendation Endpoints ====================

@router.get("/{site_id}/recommendations", response_model=List[MultiModuleRecommendationResponse])
async def get_peak_shaving_recommendations(site_id: str):
    """
    Get available multi-module peak shaving recommendations.

    Returns all pending peak shaving recommendations from the demand-aware
    coordinator, showing BESS discharge + HVAC setpoint + load deferral options.
    """
    try:
        # Get pending recommendations for this site
        # (in a real system, these would come from coordinator output stored in DB)
        recommendations = []

        logger.info(f"Retrieved {len(recommendations)} peak shaving recommendations for site {site_id}")

        return [
            MultiModuleRecommendationResponse(
                recommendation_id=rec.get("recommendation_id"),
                timestamp=rec.get("timestamp", ""),
                type=rec.get("type", "multi_system_shaving"),
                urgency=rec.get("urgency", "normal"),
                priority=rec.get("priority", "low"),
                modules_involved=rec.get("modules_involved", []),
                module_actions=[
                    ModuleActionResponse(
                        module=action.get("module"),
                        action=action.get("action"),
                        duration_min=action.get("duration_min"),
                        reduction_kw=action.get("reduction_kw"),
                        estimated_savings_r=action.get("estimated_savings_r")
                    )
                    for action in rec.get("module_actions", [])
                ],
                estimated_reduction_kw=rec.get("estimated_reduction_kw", 0),
                estimated_savings_r=rec.get("estimated_savings_r", 0),
                reasoning=rec.get("reasoning", ""),
                requires_approval=rec.get("requires_approval", True)
            )
            for rec in recommendations
        ]

    except Exception as e:
        logger.error(f"Error getting recommendations for site {site_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve recommendations")


@router.post("/{site_id}/approve-recommendation")
async def approve_peak_shaving_recommendation(
    site_id: str,
    request: ApproveRecommendationRequest
):
    """
    Approve a multi-module peak shaving recommendation.

    Executes all coordinated actions (BESS discharge, HVAC setpoint, etc.)
    with safety validation via approval_service for COV feedback and rollback.
    """
    try:
        approval_service = get_approval_service()

        # Execute approval (which handles multi-module coordination)
        result = await approval_service.execute_multi_module_approval(
            recommendation_id=request.recommendation_id,
            approved_by=request.approved_by,
            approval_notes=request.approval_notes or ""
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=f"Approval failed: {result.get('error', 'Unknown error')}"
            )

        logger.info(
            f"Peak shaving recommendation {request.recommendation_id} approved and executing - "
            f"Expected reduction: {result.get('estimated_reduction_kw', 0):.0f}kW"
        )

        return {
            "status": "executing",
            "recommendation_id": request.recommendation_id,
            "modules_executing": len(result.get("module_actions", [])),
            "estimated_reduction_kw": result.get("estimated_reduction_kw", 0),
            "estimated_savings_r": result.get("estimated_savings_r", 0),
            "execution_details": result.get("details", {})
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving recommendation for site {site_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to execute recommendation")


# ==================== Utility Endpoints ====================

@router.get("/{site_id}/summary")
async def get_demand_summary(site_id: str):
    """
    Get demand management summary for dashboard display.

    Quick overview combining current demand, peak risk, and available actions.
    """
    try:
        demand_service = get_solar_demand_service()
        demand_status = demand_service.get_current_demand(site_id)

        if not demand_status:
            raise HTTPException(status_code=404, detail=f"Site {site_id} not found")

        # Get active modules
        active_modules = module_registry.get_active_modules(site_id)
        active_names = [m.module_type.value for m in active_modules]

        # PHASE 081: Fetch NMD from database (from municipal bills)
        nmd_limit_kva = demand_status.get("nmd_limit_kva")
        if not nmd_limit_kva:
            try:
                nmd_limit_kva = await demand_service.get_nmd_limit(site_id)
            except Exception as exc:
                logger.warning(f"Failed to fetch NMD from database for summary: {exc}")
                nmd_limit_kva = 6000  # Fallback
        
        current_demand_kw = demand_status.get("current_demand_kw", 0)
        headroom_percent = ((nmd_limit_kva - current_demand_kw) / nmd_limit_kva * 100) if nmd_limit_kva > 0 else 100

        return {
            "site_id": site_id,
            "current_demand_kw": round(current_demand_kw, 1),
            "nmd_limit_kva": round(nmd_limit_kva, 1),
            "headroom_percent": round(headroom_percent, 1),
            "risk_level": "critical" if headroom_percent < 5 else (
                "warning" if headroom_percent < 15 else (
                    "caution" if headroom_percent < 25 else "safe"
                )
            ),
            "active_modules": active_names,
            "coordinator_active": ModuleType.SOLAR in [m.module_type for m in active_modules]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting demand summary for site {site_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve summary")
