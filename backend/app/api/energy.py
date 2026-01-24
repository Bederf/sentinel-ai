"""Energy consumption API endpoints."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import random

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()

# Load data files
DATA_DIR = Path(__file__).parent.parent / "data"


def load_sites() -> list[dict]:
    """Load sites from JSON file."""
    sites_file = DATA_DIR / "sites.json"
    if sites_file.exists():
        with open(sites_file) as f:
            return json.load(f)
    return []


def load_equipment() -> list[dict]:
    """Load equipment from JSON file."""
    equipment_file = DATA_DIR / "equipment.json"
    if equipment_file.exists():
        with open(equipment_file) as f:
            return json.load(f)
    return []


# Equipment types for energy categorization
HVAC_TYPES = {"ahu", "chiller", "cooling_tower", "crac", "split_unit", "fcu", "vrf"}
LIGHTING_TYPES = {"lighting", "emergency_lighting"}
# Everything else is "other"


class EnergyDataPoint(BaseModel):
    """Daily energy consumption data point."""

    date: str
    site_id: str
    site_name: str
    hvac_kwh: float
    lighting_kwh: float
    other_kwh: float
    total_kwh: float


class EnergyResponse(BaseModel):
    """Energy consumption response."""

    days: int
    site_id: Optional[str]
    data: list[EnergyDataPoint]


def generate_energy_data(
    sites: list[dict],
    equipment: list[dict],
    days: int = 30,
    site_id: Optional[str] = None,
) -> list[EnergyDataPoint]:
    """
    Generate synthetic energy consumption data based on equipment.

    Uses equipment capacity to estimate realistic energy usage patterns.
    """
    # Set random seed for reproducibility per request
    random.seed(42)

    # Filter sites if site_id specified
    if site_id:
        sites = [s for s in sites if s["id"] == site_id]

    # Build site lookup
    site_lookup = {s["id"]: s for s in sites}

    # Build equipment by site
    equipment_by_site = {}
    for eq in equipment:
        sid = eq.get("site_id")
        if sid not in equipment_by_site:
            equipment_by_site[sid] = []
        equipment_by_site[sid].append(eq)

    # Generate data for each day
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days - 1)

    result = []
    current_date = start_date

    while current_date <= end_date:
        for site in sites:
            sid = site["id"]
            site_name = site["name"]
            site_equipment = equipment_by_site.get(sid, [])

            # Calculate base energy by equipment type
            hvac_base = 0.0
            other_base = 0.0

            for eq in site_equipment:
                eq_type = eq.get("type", "").lower()
                # Extract capacity number (e.g., "60kW" -> 60)
                capacity_str = eq.get("capacity", "10kW")
                try:
                    capacity = float("".join(c for c in capacity_str if c.isdigit() or c == ".") or "10")
                except ValueError:
                    capacity = 10.0

                if eq_type in HVAC_TYPES:
                    # HVAC runs ~8-12 hours per day at 60-80% load
                    hvac_base += capacity * 10 * 0.7  # kWh/day estimate
                elif eq_type in LIGHTING_TYPES:
                    # Lighting accounted separately
                    pass
                else:
                    # Other equipment (UPS, generators, etc.) - standby + occasional use
                    other_base += capacity * 2 * 0.3  # Lower utilization

            # Lighting estimate based on site sqm (~10W/sqm * 10 hours)
            sqm = site.get("sqm", 1000)
            lighting_base = sqm * 0.01 * 10  # kWh/day

            # Add daily variation (weekday vs weekend, seasonal)
            day_of_week = current_date.weekday()
            is_weekend = day_of_week >= 5

            # Reduce consumption on weekends
            weekend_factor = 0.4 if is_weekend else 1.0

            # Add random variation (+/- 15%)
            hvac_var = random.uniform(0.85, 1.15)
            lighting_var = random.uniform(0.90, 1.10)
            other_var = random.uniform(0.95, 1.05)

            hvac_kwh = round(hvac_base * weekend_factor * hvac_var, 1)
            lighting_kwh = round(lighting_base * weekend_factor * lighting_var, 1)
            other_kwh = round(other_base * other_var, 1)  # Other less affected by weekend
            total_kwh = round(hvac_kwh + lighting_kwh + other_kwh, 1)

            result.append(
                EnergyDataPoint(
                    date=current_date.isoformat(),
                    site_id=sid,
                    site_name=site_name,
                    hvac_kwh=hvac_kwh,
                    lighting_kwh=lighting_kwh,
                    other_kwh=other_kwh,
                    total_kwh=total_kwh,
                )
            )

        current_date += timedelta(days=1)

    # Sort by date, then site
    result.sort(key=lambda x: (x.date, x.site_id))
    return result


@router.get("/energy", response_model=EnergyResponse)
async def get_energy(
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
    days: int = Query(30, ge=1, le=365, description="Number of days of data"),
) -> EnergyResponse:
    """
    Get daily energy consumption data.

    Args:
        site_id: Optional site ID to filter by (e.g., "site-001")
        days: Number of days of data to return (default 30, max 365)

    Returns:
        EnergyResponse with aggregated daily energy by category:
        - hvac_kwh: HVAC systems (AHU, chillers, etc.)
        - lighting_kwh: Lighting systems
        - other_kwh: Other equipment (UPS, generators, etc.)
        - total_kwh: Sum of all categories
    """
    sites = load_sites()
    equipment = load_equipment()

    data = generate_energy_data(sites, equipment, days=days, site_id=site_id)

    return EnergyResponse(
        days=days,
        site_id=site_id,
        data=data,
    )
