"""Optimization API endpoints for HVAC load shedding and AI optimization."""

import json
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException, Body, Request
from pydantic import BaseModel

from app.services.ai_optimizer import ai_optimizer_service
from app.services.device_abstraction import device_manager
from app.services.audit_logger import AuditLogger
from app.models.audit_log import AuditResultType
from app.models.optimization import (
    OptimizationRecommendation,
    OptimizationSettings,
    SiteOptimizationStatus,
    OptimizationStatus,
    OptimizationHistoryEntry,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Data directory
DATA_DIR = Path(__file__).parent.parent / "data"


# Pydantic models for request/response validation


# Pydantic models for request/response validation
class LoadSheddingStage(BaseModel):
    """Model for load shedding stage information."""
    stage: int
    start_time: str
    end_time: str


class EskomStatusResponse(BaseModel):
    """Response model for Eskom status endpoint."""
    current_stage: int
    updated_at: str
    next_stages: List[LoadSheddingStage]
    area_schedules: Dict[str, List[LoadSheddingStage]]


class SiteScheduleResponse(BaseModel):
    """Response model for site-specific schedule endpoint."""
    site_id: str
    site_name: str
    current_stage: int
    schedules: List[LoadSheddingStage]
    next_outage: Optional[LoadSheddingStage]


# Mock data generation functions
def generate_random_stage() -> int:
    """Generate random load shedding stage (0-4)."""
    return random.randint(0, 4)


def generate_outage_times() -> tuple:
    """Generate realistic outage times for South African patterns."""
    # Typical load shedding times in South Africa
    time_blocks = [
        ("06:00", "08:00"),
        ("08:00", "10:00"),
        ("14:00", "16:00"),
        ("16:00", "18:00"),
        ("18:00", "20:00"),
        ("20:00", "22:00"),
    ]
    return random.choice(time_blocks)


def generate_site_schedules(site_id: str) -> List[LoadSheddingStage]:
    """Generate load shedding schedules for a specific site."""
    schedules = []

    # Generate 2-4 outages for the day
    num_outages = random.randint(2, 4)

    for i in range(num_outages):
        start_time, end_time = generate_outage_times()
        stage = generate_random_stage()

        # Ensure Gateway Theatre has Stage 4 from 16:00-18:30 for demo consistency
        if site_id == "site-001" and i == 0:
            stage = 4
            start_time = "16:00"
            end_time = "18:30"

        schedules.append(
            LoadSheddingStage(
                stage=stage,
                start_time=start_time,
                end_time=end_time
            )
        )

    # Sort by start time
    schedules.sort(key=lambda x: x.start_time)
    return schedules


def get_site_name(site_id: str) -> str:
    """Get site name from site ID."""
    site_names = {
        "site-001": "Gateway Theatre",
        "site-002": "Sandton City",
        "site-003": "Centurion Mall",
        "site-004": "Tygervalley",
        "site-005": "Canal Walk",
        "site-006": "East Rand Mall",
        "site-007": "Pavilion",
        "site-008": "N1 City",
        "site-009": "Blue Route",
        "site-010": "Cresta"
    }
    return site_names.get(site_id, f"Site {site_id}")


@router.get("/optimization/eskom-status", response_model=EskomStatusResponse)
async def get_eskom_status():
    """
    Get current Eskom load shedding status and schedules.

    Returns simulated load shedding data for demo purposes.
    """
    current_stage = generate_random_stage()

    # Generate next stages (forecast for next few hours)
    next_stages = []
    for i in range(3):
        start_time = (datetime.now() + timedelta(hours=i)).strftime("%H:%M")
        end_time = (datetime.now() + timedelta(hours=i+2)).strftime("%H:%M")
        next_stages.append(
            LoadSheddingStage(
                stage=max(0, current_stage + random.randint(-1, 1)),
                start_time=start_time,
                end_time=end_time
            )
        )

    # Generate schedules for all sites
    area_schedules = {}
    for site_id in [f"site-{i:03d}" for i in range(1, 11)]:
        schedules = generate_site_schedules(site_id)
        area_schedules[site_id] = schedules

    return EskomStatusResponse(
        current_stage=current_stage,
        updated_at=datetime.now().isoformat(),
        next_stages=next_stages,
        area_schedules=area_schedules
    )


@router.get("/optimization/eskom-status/{site_id}", response_model=SiteScheduleResponse)
async def get_site_eskom_status(site_id: str):
    """
    Get load shedding schedule for a specific site.

    Args:
        site_id: The site ID to get schedule for

    Returns:
        Site-specific load shedding schedule
    """
    # Validate site ID format
    if not site_id.startswith("site-"):
        raise HTTPException(
            status_code=400,
            detail="Invalid site ID format. Expected format: site-001"
        )

    # Generate schedules for this site
    schedules = generate_site_schedules(site_id)

    # Find next outage (if any)
    current_time = datetime.now().strftime("%H:%M")
    next_outage = None

    for schedule in schedules:
        if schedule.start_time > current_time:
            next_outage = schedule
            break

    return SiteScheduleResponse(
        site_id=site_id,
        site_name=get_site_name(site_id),
        current_stage=generate_random_stage(),
        schedules=schedules,
        next_outage=next_outage
    )


@router.get("/optimization/thermal-runway")
async def calculate_thermal_runway(
    site_id: str,
    current_temp: float = 22.4,
    comfort_limit: float = 26.0
):
    """
    Calculate thermal runway for a building during load shedding.

    Args:
        site_id: The site ID
        current_temp: Current inside temperature in °C
        comfort_limit: Comfort temperature limit in °C

    Returns:
        Thermal runway calculation results
    """
    # Import thermal model service
    try:
        from app.services.thermal_model import calculate_thermal_runway as calc_runway
    except ImportError:
        # Fallback calculation if thermal model not available
        logger.warning("Thermal model service not available, using fallback calculation")

        # Simple fallback calculation
        outside_temp = 32.0  # Assume hot day
        temp_difference = outside_temp - current_temp
        heat_transfer_rate = 0.05  # Simplified coefficient

        # Calculate minutes until comfort breach
        runway_minutes = int((comfort_limit - current_temp) / (temp_difference * heat_transfer_rate) * 60)
        runway_minutes = max(10, min(180, runway_minutes))  # Clamp between 10-180 minutes

        return {
            "site_id": site_id,
            "site_name": get_site_name(site_id),
            "current_temperature": current_temp,
            "comfort_limit": comfort_limit,
            "thermal_runway_minutes": runway_minutes,
            "comfort_breach_time": None,
            "calculation_method": "fallback",
            "building_params": {
                "thermal_mass": 0.8,
                "insulation_factor": 0.6,
                "internal_heat_gain": 0.5
            }
        }

    # Use thermal model service
    building_params = {
        "thermal_mass": 0.8,
        "insulation_factor": 0.6,
        "internal_heat_gain": 0.5
    }

    weather_forecast = {
        "outside_temp": 32.0,
        "solar_load": 0.7,
        "humidity": 65
    }

    runway_minutes = calc_runway(current_temp, comfort_limit, building_params, weather_forecast)

    # Calculate comfort breach time
    current_time = datetime.now()
    breach_time = current_time + timedelta(minutes=runway_minutes)

    return {
        "site_id": site_id,
        "site_name": get_site_name(site_id),
        "current_temperature": current_temp,
        "comfort_limit": comfort_limit,
        "thermal_runway_minutes": runway_minutes,
        "comfort_breach_time": breach_time.isoformat(),
        "calculation_method": "thermal_model",
        "building_params": building_params,
        "weather_forecast": weather_forecast
    }


# ============================================================================
# AI Optimization Endpoints (Phase 8)
# ============================================================================

class AnalyzeRequest(BaseModel):
    """Request model for analyze endpoint."""
    site_id: str
    current_conditions: Optional[Dict[str, Any]] = None
    weather_forecast: Optional[Dict[str, Any]] = None
    energy_prices: Optional[Dict[str, Any]] = None


class LoadSheddingAnalyzeRequest(BaseModel):
    """Request model for load shedding analysis endpoint."""
    site_id: str
    load_shedding_stage: int  # 1-4, higher = more severe
    current_conditions: Optional[Dict[str, Any]] = None


class ApproveRequest(BaseModel):
    """Request model for approve endpoint."""
    recommendation_id: str
    site_id: str
    setpoints_to_apply: List[Dict[str, Any]]


class ToggleRequest(BaseModel):
    """Request model for toggle endpoint."""
    enabled: bool


def load_sites():
    """Load sites from JSON file."""
    filepath = DATA_DIR / "sites.json"
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return []


def save_sites(sites: List[Dict[str, Any]]):
    """Save sites to JSON file."""
    filepath = DATA_DIR / "sites.json"
    with open(filepath, 'w') as f:
        json.dump(sites, f, indent=2)


@router.post("/optimization/analyze")
async def analyze_optimization(request: AnalyzeRequest) -> Dict[str, Any]:
    """
    Analyze building conditions and generate optimization recommendations.

    Uses AI to analyze current building telemetry, weather forecast, and
    energy pricing to recommend optimal HVAC setpoints.

    Args:
        request: Analysis request with site_id and optional conditions

    Returns:
        OptimizationRecommendation with setpoint changes and projected savings
    """
    try:
        logger.info(f"Analyzing optimization for site {request.site_id}")

        # Call AI optimizer service
        recommendation = await ai_optimizer_service.analyze_building(
            site_id=request.site_id,
            current_conditions=request.current_conditions,
            weather_forecast=request.weather_forecast,
            energy_prices=request.energy_prices,
        )

        # Validate recommendation against safety rules
        validation = await ai_optimizer_service.validate_recommendation(
            request.site_id, recommendation
        )

        # Update site status
        sites = load_sites()
        site = next((s for s in sites if s["id"] == request.site_id), None)
        if site:
            if validation["allowed"]:
                site["optimization_status"] = OptimizationStatus.RECOMMENDATION_PENDING.value
                site["last_recommendation"] = recommendation.to_dict()
            else:
                site["optimization_status"] = OptimizationStatus.WARNING.value
                site["last_recommendation"] = recommendation.to_dict()
                site["error_message"] = "Recommendation failed safety validation"

            # Add to history
            if "optimization_history" not in site:
                site["optimization_history"] = []

            history_entry = OptimizationHistoryEntry(
                timestamp=datetime.now().isoformat(),
                action="analyzed",
                result="success" if validation["allowed"] else "warning",
                user="system",
                details={
                    "confidence": recommendation.confidence,
                    "validation_passed": validation["allowed"],
                }
            )
            site["optimization_history"].append(history_entry.to_dict())

            # Keep only last 50 history entries
            if len(site["optimization_history"]) > 50:
                site["optimization_history"] = site["optimization_history"][-50:]

            save_sites(sites)

        return {
            "success": True,
            "recommendation": recommendation.to_dict(),
            "validation": validation,
        }

    except ValueError as e:
        logger.error(f"Site not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error analyzing optimization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimization/analyze-load-shedding")
async def analyze_load_shedding(request: LoadSheddingAnalyzeRequest) -> Dict[str, Any]:
    """
    Analyze building optimization with load shedding stage awareness.

    During load shedding, the optimizer prioritizes critical zones (P1-P2)
    while allowing more aggressive optimization in lower-priority zones.

    Zone Priority Behavior by Stage:
    - Stage 1: Maintain P1-P4 normally, aggressive optimization on P5
    - Stage 2: Maintain P1-P3 normally, aggressive optimization on P4-P5
    - Stage 3: Maintain P1-P2 normally, aggressive optimization on P3-P5
    - Stage 4: Maintain P1 only (executive, server rooms), aggressive on all else

    Args:
        request: Analysis request with site_id, load_shedding_stage (1-4), and optional conditions

    Returns:
        OptimizationRecommendation with zone-priority-aware recommendations
    """
    try:
        # Validate stage
        if request.load_shedding_stage < 1 or request.load_shedding_stage > 4:
            raise HTTPException(
                status_code=400,
                detail="load_shedding_stage must be between 1 and 4"
            )

        logger.info(f"Analyzing load shedding optimization for site {request.site_id}, stage {request.load_shedding_stage}")

        # Call AI optimizer service with load shedding awareness
        recommendation = await ai_optimizer_service.analyze_building_load_shedding(
            site_id=request.site_id,
            load_shedding_stage=request.load_shedding_stage,
            current_conditions=request.current_conditions,
        )

        # Validate recommendation against safety rules
        validation = await ai_optimizer_service.validate_recommendation(
            request.site_id, recommendation
        )

        return {
            "success": True,
            "load_shedding_stage": request.load_shedding_stage,
            "recommendation": recommendation.to_dict(),
            "validation": validation,
            "zone_priority_info": {
                1: "Stage 1: Maintain P1-P4, shed P5 (parking, plant rooms)",
                2: "Stage 2: Maintain P1-P3, shed P4-P5 (+ lobby)",
                3: "Stage 3: Maintain P1-P2, shed P3-P5 (executive/server/meeting only)",
                4: "Stage 4: Maintain P1 only (executive/server rooms only)",
            }.get(request.load_shedding_stage, ""),
        }

    except ValueError as e:
        logger.error(f"Site not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing load shedding optimization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimization/approve")
async def approve_optimization(
    request: Request,
    body: ApproveRequest = Body(...)
) -> Dict[str, Any]:
    """
    Apply approved optimization recommendations to building systems.

    Validates setpoints against safety rules, applies changes via device
    control API, and logs to audit trail.

    Args:
        body: Approval request with recommendation_id, site_id, and setpoints

    Returns:
        Success/failure result with details
    """
    try:
        logger.info(f"Approving optimization for site {body.site_id}, recommendation {body.recommendation_id}, setpoints: {len(body.setpoints_to_apply)}")
        
        # Validate setpoints array is not empty
        if not body.setpoints_to_apply:
            raise HTTPException(
                status_code=422,
                detail="setpoints_to_apply cannot be empty"
            )

        # Extract user from headers
        user = request.headers.get("X-User-Id", "operator")

        audit_logger = AuditLogger()
        results = []
        all_success = True

        for setpoint in body.setpoints_to_apply:
            device_id = setpoint.get("device_id")
            point_name = setpoint.get("point_name")
            value = setpoint.get("value")

            if not all([device_id, point_name, value is not None]):
                results.append({
                    "device_id": device_id,
                    "success": False,
                    "error": "Missing required fields: device_id, point_name, value"
                })
                all_success = False
                continue

            try:
                # Write to device via device manager
                success = await device_manager.write_device_value(
                    device_id=device_id,
                    point_name=point_name,
                    value=value,
                    user=user,
                )

                if success:
                    results.append({
                        "device_id": device_id,
                        "point_name": point_name,
                        "success": True,
                        "value": value,
                    })

                    # Log to audit trail
                    audit_logger.log_control_action(
                        device_id=device_id,
                        point_name=point_name,
                        user=user,
                        old_value=None,  # Could fetch current value if needed
                        new_value=value,
                        result=AuditResultType.SUCCESS,
                        metadata={
                            "source": "ai_optimization",
                            "recommendation_id": body.recommendation_id,
                        }
                    )
                else:
                    results.append({
                        "device_id": device_id,
                        "success": False,
                        "error": f"Failed to write {value} to {point_name}"
                    })
                    all_success = False

            except Exception as e:
                logger.error(f"Error applying setpoint to {device_id}: {e}")
                results.append({
                    "device_id": device_id,
                    "success": False,
                    "error": str(e)
                })
                all_success = False

        # Flush audit log
        audit_logger.flush()

        # Update site status
        sites = load_sites()
        site = next((s for s in sites if s["id"] == body.site_id), None)
        if site:
            if all_success:
                site["optimization_status"] = OptimizationStatus.OPTIMIZED.value
                site["last_optimization"] = datetime.now().isoformat()
                # Clear the recommendation after successful approval
                site["last_recommendation"] = None

                # Add to history
                if "optimization_history" not in site:
                    site["optimization_history"] = []

                history_entry = OptimizationHistoryEntry(
                    timestamp=datetime.now().isoformat(),
                    action="approved",
                    result="success",
                    user=user,
                    details={
                        "recommendation_id": body.recommendation_id,
                        "setpoints_applied": len(body.setpoints_to_apply),
                    }
                )
                site["optimization_history"].append(history_entry.to_dict())

                # Keep only last 50 history entries
                if len(site["optimization_history"]) > 50:
                    site["optimization_history"] = site["optimization_history"][-50:]

            else:
                site["optimization_status"] = OptimizationStatus.ERROR.value

                # Add to history
                if "optimization_history" not in site:
                    site["optimization_history"] = []

                history_entry = OptimizationHistoryEntry(
                    timestamp=datetime.now().isoformat(),
                    action="approved",
                    result="error",
                    user=user,
                    details={
                        "recommendation_id": body.recommendation_id,
                        "error": "Some setpoints failed to apply",
                    }
                )
                site["optimization_history"].append(history_entry.to_dict())

            save_sites(sites)

        return {
            "success": all_success,
            "results": results,
            "message": f"Applied {len([r for r in results if r['success']])} of {len(results)} setpoints"
        }

    except Exception as e:
        logger.error(f"Error approving optimization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/optimization/status/{site_id}")
async def get_optimization_status(site_id: str) -> Dict[str, Any]:
    """
    Get optimization status for a specific site.

    Returns current optimization status, last recommendation, and
    optimization history.

    Args:
        site_id: Site ID to get status for

    Returns:
        Site optimization status with history
    """
    try:
        sites = load_sites()
        site = next((s for s in sites if s["id"] == site_id), None)

        if not site:
            raise HTTPException(status_code=404, detail=f"Site {site_id} not found")

        # Build status response
        status = {
            "site_id": site.get("id"),
            "site_name": site.get("name"),
            "optimization_enabled": site.get("optimization_enabled", False),
            "optimization_status": site.get("optimization_status", OptimizationStatus.UNKNOWN.value),
            "optimization_settings": site.get("optimization_settings", {
                "mode": "supervised",
                "last_analysis": None,
                "analysis_interval_minutes": 15,
            }),
            "last_recommendation": site.get("last_recommendation"),
            "last_optimization": site.get("last_optimization"),
            "optimization_history": site.get("optimization_history", []),
            "error_message": site.get("error_message"),
        }

        return status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting optimization status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimization/toggle/{site_id}")
async def toggle_optimization(site_id: str, request: ToggleRequest) -> Dict[str, Any]:
    """
    Enable or disable optimization for a specific site.

    Updates site optimization settings.

    Args:
        site_id: Site ID to toggle optimization for
        request: Toggle request with enabled boolean

    Returns:
        Updated optimization settings
    """
    try:
        sites = load_sites()
        site = next((s for s in sites if s["id"] == site_id), None)

        if not site:
            raise HTTPException(status_code=404, detail=f"Site {site_id} not found")

        # Update optimization enabled flag
        site["optimization_enabled"] = request.enabled

        # Initialize optimization settings if not present
        if "optimization_settings" not in site:
            site["optimization_settings"] = {
                "mode": "supervised",
                "last_analysis": None,
                "analysis_interval_minutes": 15,
            }

        # Update status
        if request.enabled:
            site["optimization_status"] = OptimizationStatus.UNKNOWN.value
        else:
            site["optimization_status"] = OptimizationStatus.UNKNOWN.value
            site["last_recommendation"] = None

        # Save to file
        save_sites(sites)

        logger.info(f"Optimization {'enabled' if request.enabled else 'disabled'} for site {site_id}")

        return {
            "success": True,
            "site_id": site_id,
            "optimization_enabled": request.enabled,
            "optimization_settings": site["optimization_settings"],
            "message": f"Optimization {'enabled' if request.enabled else 'disabled'} for {site.get('name', site_id)}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling optimization: {e}")
        raise HTTPException(status_code=500, detail=str(e))