"""Energy consumption API endpoints."""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import random

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from app.database.repositories.energy_consumption_repository import get_energy_consumption_repository
from app.services.building_loader import BuildingDataLoader

router = APIRouter()
logger = logging.getLogger(__name__)

# Load data files
DATA_DIR = Path(__file__).parent.parent / "data"

# Initialize building loader
_building_loader = None


def get_building_loader():
    """Get or initialize building loader."""
    global _building_loader
    if _building_loader is None:
        _building_loader = BuildingDataLoader()
    return _building_loader


def load_equipment() -> list[dict]:
    """Load equipment from Supabase."""
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()

    # Get all equipment from Supabase with building info (paginated to handle >1000 records)
    all_equipment = []
    offset = 0
    batch_size = 1000

    while True:
        result = (
            client.table('equipment')
            .select('*, buildings(code, name)')
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        if not result.data:
            break

        all_equipment.extend(result.data)
        offset += batch_size

        if len(result.data) < batch_size:
            break

    # Map to the format expected by generate_energy_data
    equipment = []
    for eq in all_equipment:
        building = eq.get('buildings')
        if building:
            equipment.append({
                'id': eq.get('id'),
                'site_id': building.get('code'),  # Use building code instead of UUID
                'type': eq.get('type'),
                'name': eq.get('name'),
                'manufacturer': eq.get('manufacturer'),
                'model': eq.get('model'),
                'capacity': eq.get('capacity') or eq.get('rated_capacity') or '10kW',
            })

    return equipment


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


def get_energy_from_supabase(
    building_id: Optional[str],
    days: int,
) -> tuple[list[EnergyDataPoint], bool]:
    """Get energy consumption data from Supabase.

    Args:
        building_id: Optional building code to filter by
        days: Number of days of data

    Returns:
        Tuple of (data points, success flag)
    """
    from app.database.supabase_client import get_supabase_client

    try:
        repo = get_energy_consumption_repository()
        client = get_supabase_client()

        # Get consumption records
        if building_id:
            records = repo.get_by_building(building_id, days)
        else:
            records = repo.get_all_buildings(days)

        if not records:
            return [], False

        # Get building info from Supabase for names
        result = client.table('buildings').select('code, name').execute()
        building_names = {}
        for b in result.data or []:
            building_names[b.get("code")] = b.get("name") or b.get("code")

        # Convert to EnergyDataPoint format
        data = []
        for record in records:
            bid = record["building_id"]
            site_name = building_names.get(bid, bid)

            data.append(
                EnergyDataPoint(
                    date=record["date"],
                    site_id=bid,
                    site_name=site_name,
                    hvac_kwh=float(record["hvac_kwh"] or 0),
                    lighting_kwh=float(record["lighting_kwh"] or 0),
                    other_kwh=float(record["other_kwh"] or 0),
                    total_kwh=float(record["total_kwh"] or 0),
                )
            )

        return data, True

    except Exception as e:
        logger.warning(f"Failed to get energy data from Supabase: {e}")
        return [], False


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

    Note:
        Tries to load from Supabase first. Falls back to mock data if unavailable.
    """
    # Try Supabase first
    supabase_data, success = get_energy_from_supabase(site_id, days)
    if success and supabase_data:
        logger.info(f"Using Supabase energy data ({len(supabase_data)} records)")
        return EnergyResponse(
            days=days,
            site_id=site_id,
            data=supabase_data,
        )

    # Fall back to mock data generation using Supabase buildings
    logger.info("Supabase energy data empty, using mock generation")

    from app.database.supabase_client import get_supabase_client

    try:
        client = get_supabase_client()
        result = client.table('buildings').select('code, name, sqm').execute()
        sites = []
        for b in result.data or []:
            sites.append({
                "id": b.get("code"),
                "name": b.get("name"),
                "sqm": b.get("sqm") or 1000,
            })
    except Exception as e:
        logger.warning(f"Failed to load buildings from Supabase: {e}")
        sites = []

    # If still no sites, use building_loader
    if not sites:
        building_loader = get_building_loader()
        buildings = building_loader.get_all_buildings()

        for b in buildings:
            if hasattr(b, 'to_dict'):
                b_dict = b.to_dict()
            elif isinstance(b, dict):
                b_dict = b
            else:
                b_dict = {"id": getattr(b, "id", "unknown"), "name": getattr(b, "name", "Unknown")}

            metadata = b_dict.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}

            sites.append({
                "id": b_dict.get("id"),
                "name": b_dict.get("display_name") or b_dict.get("name") or b_dict.get("id"),
                "sqm": metadata.get("sqm", 1000),
            })

    equipment = load_equipment()

    data = generate_energy_data(sites, equipment, days=days, site_id=site_id)

    return EnergyResponse(
        days=days,
        site_id=site_id,
        data=data,
    )


@router.post("/energy/seed")
async def seed_energy_data(
    building_id: Optional[str] = Query(None, description="Building code to seed (default: all)"),
    days: int = Query(90, ge=1, le=365, description="Number of days to seed"),
) -> dict:
    """
    Seed energy consumption data for demo purposes.

    Uses the mock data generator and stores results in Supabase.

    Args:
        building_id: Optional building code (default: all buildings)
        days: Number of days to seed (default 90)

    Returns:
        Dictionary with seeding results
    """
    from app.database.supabase_client import get_supabase_client

    try:
        repo = get_energy_consumption_repository()
        client = get_supabase_client()

        # Get buildings from Supabase (has all 10 sites)
        if building_id:
            result = client.table('buildings').select('id, code, name, sqm').eq('code', building_id).execute()
        else:
            result = client.table('buildings').select('id, code, name, sqm').execute()

        if not result.data:
            raise HTTPException(status_code=404, detail=f"Building {building_id} not found")

        buildings = result.data

        # Load equipment from Supabase with building codes
        equipment = load_equipment()

        # Generate data for each building
        records_created = 0
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days - 1)
        building_codes = []

        for building in buildings:
            building_code = building.get("code", building.get("id"))
            building_codes.append(building_code)

            # Prepare site data for energy generator
            sites = [{
                "id": building_code,  # Use building code as site_id
                "name": building.get("name", building_code),
                "sqm": building.get("sqm") or 1000,
            }]

            # Generate mock data for this building
            mock_data = generate_energy_data(sites, equipment, days=days, site_id=building_code)

            # Batch upsert for efficiency
            batch_records = []
            for point in mock_data:
                batch_records.append({
                    "building_id": point.site_id,
                    "date": point.date,
                    "hvac_kwh": point.hvac_kwh,
                    "lighting_kwh": point.lighting_kwh,
                    "other_kwh": point.other_kwh,
                })

            if batch_records:
                repo.batch_upsert(batch_records)
                records_created += len(batch_records)

        return {
            "success": True,
            "message": f"Seeded {records_created} energy consumption records",
            "buildings": building_codes,
            "days": days,
            "date_range": f"{start_date} to {end_date}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to seed energy data: {e}")
        raise HTTPException(status_code=500, detail=str(e))
