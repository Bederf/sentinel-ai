"""Optimization API endpoints for HVAC load shedding optimization."""

import logging
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


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