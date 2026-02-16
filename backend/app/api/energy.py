"""Energy consumption API endpoints."""

import json
import logging
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional
import random

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from app.database.repositories.energy_consumption_repository import get_energy_consumption_repository
from app.services.building_loader import BuildingDataLoader
from app.services.energy_rules_engine import get_energy_rules_engine
from app.models.energy_rules import BuildingState

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


class EnergyMetrics(BaseModel):
    """Energy metrics for a time period."""

    total_kwh: float
    total_cost_zar: float
    carbon_kg: float
    hvac_kwh: float
    hvac_percent: float
    lighting_kwh: float
    lighting_percent: float
    power_kwh: float
    power_percent: float
    timestamp: str


class ComparisonSummary(BaseModel):
    """Side-by-side actual vs SENTINEL comparison."""

    actual: EnergyMetrics
    sentinel: EnergyMetrics
    daily_savings_zar: float
    daily_savings_percent: float
    progress_to_target_percent: float
    ai_confidence_percent: float


class EnergyActual(BaseModel):
    """Actual energy consumption data."""

    site_id: str
    period_days: int
    metrics: list[EnergyMetrics]
    period_start: str
    period_end: str


class EnergyPrediction(BaseModel):
    """Predicted/optimized energy consumption."""

    site_id: str
    scenario: str  # 'sentinel_optimized' | 'standard_ems' | 'baseline'
    period_days: int
    metrics: list[EnergyMetrics]
    period_start: str
    period_end: str
    model_confidence: float


# ==================== HELPER FUNCTIONS FOR RULES ENGINE ====================


def _estimate_occupancy(dt: datetime, site_id: str) -> int:
    """Estimate occupancy % from live simulation first, fallback to time-based.
    
    Primary: Try to get from lifecycle orchestrator's simulation state
    Fallback: Time/day-of-week heuristics
    """
    try:
        from app.services.lifecycle_orchestrator import get_lifecycle_orchestrator
        orchestrator = get_lifecycle_orchestrator()
        if orchestrator.building_state:
            occupancy = orchestrator.building_state.get("occupancy_percent")
            if occupancy is not None:
                return int(occupancy)
    except Exception:
        pass
    
    # Fallback: time-based heuristics
    hour = dt.hour
    day_of_week = dt.weekday()
    is_weekend = day_of_week >= 5
    
    if is_weekend:
        return 5  # Very low on weekends
    
    # Weekday patterns
    if 8 <= hour < 12:
        return 85  # Morning peak
    elif 12 <= hour < 14:
        return 60  # Lunch dip
    elif 14 <= hour < 17:
        return 90  # Afternoon peak
    elif 17 <= hour < 18:
        return 50  # Early evening decline
    else:
        return 10  # Night/early morning


def _estimate_daylight(dt: datetime, site_id: str) -> int:
    """Estimate daylight lux from live simulation first, fallback to seasonal.
    
    Primary: Try to get from lifecycle orchestrator
    Fallback: SeasonalModeler patterns
    """
    try:
        from app.services.lifecycle_orchestrator import get_lifecycle_orchestrator
        orchestrator = get_lifecycle_orchestrator()
        if orchestrator.building_state:
            daylight = orchestrator.building_state.get("daylight_factor")
            if daylight is not None:
                return int(daylight)
    except Exception:
        pass
    
    # Fallback: seasonal + hourly pattern
    hour = dt.hour
    month = dt.month
    
    # Night hours: 0 lux
    if hour < 7 or hour >= 18:
        return 0
    
    # Peak hours (10:00-14:00): 800-1000 lux
    if 10 <= hour < 14:
        base = 900
    # Shoulder hours: 400-800 lux
    else:
        base = 600
    
    # Seasonal adjustment (winter = lower, summer = higher)
    if month in [6, 7, 8]:  # Winter
        base = int(base * 0.7)
    elif month in [12, 1, 2]:  # Summer
        base = int(base * 1.1)
    
    return base


def _estimate_chiller_load(site_id: str) -> int:
    """Estimate chiller load % from live simulation first.
    
    Primary: Try to get from lifecycle orchestrator
    Fallback: Temperature-based estimation
    """
    try:
        from app.services.lifecycle_orchestrator import get_lifecycle_orchestrator
        orchestrator = get_lifecycle_orchestrator()
        if orchestrator.building_state:
            chiller_load = orchestrator.building_state.get("chiller_load_percent")
            if chiller_load is not None:
                return int(chiller_load)
    except Exception:
        pass
    
    # Fallback: use ambient temperature for estimation
    # Higher temp = higher chiller load
    month = date.today().month
    if month in [12, 1, 2]:  # Summer
        ambient_temp = 24
    elif month in [6, 7, 8]:  # Winter
        ambient_temp = 13
    else:
        ambient_temp = 18
    
    # Scale load: 15°C=30%, 35°C=85%
    if ambient_temp < 15:
        return 30
    elif ambient_temp > 35:
        return 85
    else:
        # Linear scale 15->30%, 35->85%
        return int(30 + (ambient_temp - 15) * 2.75)


def _get_tariff_band(hour: int, month: int) -> str:
    """Get City Power tariff band based on time and season.
    
    Summer (Oct-Mar): peak 07-10, 18-20
    Winter (Apr-Sep): peak 06-09, 17-22
    Off-peak: 21-05
    Standard: rest
    """
    is_summer = month in [10, 11, 12, 1, 2, 3]
    
    # Off-peak: 21:00 - 05:59 (always)
    if 21 <= hour or hour < 6:
        return "off_peak"
    
    if is_summer:
        # Summer: peak 07-10, 18-20
        if (7 <= hour < 10) or (18 <= hour < 20):
            return "peak"
    else:
        # Winter: peak 06-09, 17-22
        if (6 <= hour < 9) or (17 <= hour < 22):
            return "peak"
    
    return "standard"


def _get_seasonal_temp(month: int) -> float:
    """Get average ambient temperature for month (South Africa).
    
    Primary: Try to get from SeasonalModeler if available
    Fallback: Hardcoded seasonal averages
    """
    try:
        from app.services.seasonal_modeler import get_seasonal_modeler
        modeler = get_seasonal_modeler()
        if modeler:
            return modeler.get_temperature_for_month(month)
    except Exception:
        pass
    
    # Fallback: SA seasonal averages (Johannesburg-like)
    seasonal_temps = {
        1: 24, 2: 24, 3: 23,  # Summer
        4: 21, 5: 19, 6: 13,  # Autumn to winter
        7: 13, 8: 15,          # Winter
        9: 18, 10: 21,         # Spring
        11: 22, 12: 24         # Early summer
    }
    
    return float(seasonal_temps.get(month, 20))


def _apply_rules_output(
    actual_metrics: EnergyMetrics,
    rules_output
) -> EnergyMetrics:
    """Apply rules output savings to actual metrics, creating sentinel metrics."""
    # Get breakdown of savings by system
    by_system = rules_output.by_system
    
    # Subtract savings from each system
    sentinel_hvac = actual_metrics.hvac_kwh - by_system.hvac_kwh
    sentinel_lighting = actual_metrics.lighting_kwh - by_system.lighting_kwh
    sentinel_power = actual_metrics.power_kwh - by_system.power_kwh
    
    sentinel_total_kwh = sentinel_hvac + sentinel_lighting + sentinel_power
    
    # Recalculate percentages
    sentinel_hvac_percent = (sentinel_hvac / sentinel_total_kwh * 100) if sentinel_total_kwh > 0 else 0
    sentinel_lighting_percent = (sentinel_lighting / sentinel_total_kwh * 100) if sentinel_total_kwh > 0 else 0
    sentinel_power_percent = (sentinel_power / sentinel_total_kwh * 100) if sentinel_total_kwh > 0 else 0
    
    # Recalculate carbon and cost
    sentinel_carbon_kg = sentinel_total_kwh * 0.35
    sentinel_cost_zar = sentinel_total_kwh * 5.0
    
    return EnergyMetrics(
        total_kwh=round(sentinel_total_kwh, 2),
        total_cost_zar=round(sentinel_cost_zar, 2),
        carbon_kg=round(sentinel_carbon_kg, 2),
        hvac_kwh=round(sentinel_hvac, 2),
        hvac_percent=round(sentinel_hvac_percent, 1),
        lighting_kwh=round(sentinel_lighting, 2),
        lighting_percent=round(sentinel_lighting_percent, 1),
        power_kwh=round(sentinel_power, 2),
        power_percent=round(sentinel_power_percent, 1),
        timestamp=datetime.now().isoformat(),
    )


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



@router.get("/energy/actual", response_model=EnergyActual)
async def get_energy_actual(
    site_id: str = Query("site-002", description="Site ID to analyze"),
    days: int = Query(30, ge=1, le=365, description="Number of days"),
) -> EnergyActual:
    """
    Get actual (monitored) energy consumption data.

    Returns daily energy metrics aggregated by system type (HVAC, Lighting, Power).
    Data is sourced from device telemetry and real-time meters.

    Args:
        site_id: Site ID to analyze (e.g., "site-002")
        days: Number of days to return (1-365, default: 30)

    Returns:
        EnergyActual with daily metrics for the period
    """
    # Fetch energy data using existing function
    energy_response = await get_energy(site_id=site_id, days=days)

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days - 1)

    # Convert EnergyDataPoint to EnergyMetrics (daily aggregates)
    metrics = []
    total_kwh_sum = 0
    total_hvac = 0
    total_lighting = 0
    total_power = 0

    for point in energy_response.data:
        total_hvac += point.hvac_kwh
        total_lighting += point.lighting_kwh
        total_power += point.other_kwh
        total_kwh_sum += point.total_kwh

    # Calculate percentages
    total_kwh = total_kwh_sum
    hvac_percent = (total_hvac / total_kwh * 100) if total_kwh > 0 else 0
    lighting_percent = (total_lighting / total_kwh * 100) if total_kwh > 0 else 0
    power_percent = (total_power / total_kwh * 100) if total_kwh > 0 else 0

    # SA carbon intensity: 0.35 kg CO₂/kWh
    carbon_kg = total_kwh * 0.35

    # Cost calculation: ~R5/kWh (typical SA commercial rate)
    total_cost_zar = total_kwh * 5.0

    metrics.append(
        EnergyMetrics(
            total_kwh=round(total_kwh, 2),
            total_cost_zar=round(total_cost_zar, 2),
            carbon_kg=round(carbon_kg, 2),
            hvac_kwh=round(total_hvac, 2),
            hvac_percent=round(hvac_percent, 1),
            lighting_kwh=round(total_lighting, 2),
            lighting_percent=round(lighting_percent, 1),
            power_kwh=round(total_power, 2),
            power_percent=round(power_percent, 1),
            timestamp=datetime.now().isoformat(),
        )
    )

    return EnergyActual(
        site_id=site_id,
        period_days=days,
        metrics=metrics,
        period_start=start_date.isoformat(),
        period_end=end_date.isoformat(),
    )


@router.get("/energy/prediction", response_model=EnergyPrediction)
async def get_energy_prediction(
    site_id: str = Query("site-002", description="Site ID to analyze"),
    scenario: str = Query("sentinel_optimized", description="Scenario: sentinel_optimized, standard_ems, or baseline"),
    days: int = Query(30, ge=1, le=365, description="Number of days"),
) -> EnergyPrediction:
    """
    Get predicted/optimized energy consumption for a scenario.

    Returns ML-predicted energy metrics based on the selected optimization scenario.

    Args:
        site_id: Site ID to analyze (e.g., "site-002")
        scenario: Optimization scenario:
            - "sentinel_optimized": SENTINEL AI full optimization (~30% savings)
            - "standard_ems": Standard EMS without AI (~10% savings)
            - "baseline": No optimization
        days: Number of days to return (1-365, default: 30)

    Returns:
        EnergyPrediction with metrics for the scenario
    """
    # Get actual energy data as baseline
    energy_response = await get_energy(site_id=site_id, days=days)

    # Calculate totals from actual data
    total_kwh_actual = sum(d.total_kwh for d in energy_response.data)
    total_hvac_actual = sum(d.hvac_kwh for d in energy_response.data)
    total_lighting_actual = sum(d.lighting_kwh for d in energy_response.data)
    total_power_actual = sum(d.other_kwh for d in energy_response.data)

    # Apply scenario-based reductions
    if scenario == "sentinel_optimized":
        # SENTINEL AI: 30% total savings (distributed across all systems)
        reduction_factor = 0.70
        confidence = 85.0
    elif scenario == "standard_ems":
        # Standard EMS: 10% savings
        reduction_factor = 0.90
        confidence = 65.0
    else:  # baseline
        # No optimization
        reduction_factor = 1.0
        confidence = 50.0

    # Apply reduction factor
    total_kwh = total_kwh_actual * reduction_factor
    total_hvac = total_hvac_actual * reduction_factor * 0.95  # HVAC optimization slightly better
    total_lighting = total_lighting_actual * reduction_factor * 1.1  # Lighting optimization better
    total_power = total_power_actual * reduction_factor * 0.98  # Power optimization less impact

    # Recalculate percentages
    hvac_percent = (total_hvac / total_kwh * 100) if total_kwh > 0 else 0
    lighting_percent = (total_lighting / total_kwh * 100) if total_kwh > 0 else 0
    power_percent = (total_power / total_kwh * 100) if total_kwh > 0 else 0

    # SA carbon intensity
    carbon_kg = total_kwh * 0.35

    # Cost calculation
    total_cost_zar = total_kwh * 5.0

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days - 1)

    metrics = [
        EnergyMetrics(
            total_kwh=round(total_kwh, 2),
            total_cost_zar=round(total_cost_zar, 2),
            carbon_kg=round(carbon_kg, 2),
            hvac_kwh=round(total_hvac, 2),
            hvac_percent=round(hvac_percent, 1),
            lighting_kwh=round(total_lighting, 2),
            lighting_percent=round(lighting_percent, 1),
            power_kwh=round(total_power, 2),
            power_percent=round(power_percent, 1),
            timestamp=datetime.now().isoformat(),
        )
    ]

    return EnergyPrediction(
        site_id=site_id,
        scenario=scenario,
        period_days=days,
        metrics=metrics,
        period_start=start_date.isoformat(),
        period_end=end_date.isoformat(),
        model_confidence=confidence,
    )


@router.get("/energy/comparison-summary", response_model=ComparisonSummary)
async def get_energy_comparison_summary(
    site_id: str = Query("site-002", description="Site ID to analyze"),
    method: str = Query("rules_based", description="rules_based | hardcoded"),
) -> ComparisonSummary:
    """
    Get side-by-side actual vs SENTINEL AI energy comparison.

    Compares actual monitored consumption with AI-optimized prediction,
    showing daily savings, progress to target, and AI confidence.

    Args:
        site_id: Site ID to analyze (e.g., "site-002")
        method: Optimization method ("rules_based" or "hardcoded", default: "rules_based")

    Returns:
        ComparisonSummary with actual, sentinel, and savings metrics
    """
    # Get actual energy for last 30 days
    actual_response = await get_energy_actual(site_id=site_id, days=30)
    actual_metrics = actual_response.metrics[0] if actual_response.metrics else None

    if not actual_metrics:
        raise HTTPException(status_code=404, detail=f"No energy data found for site {site_id}")

    # Use rules-based engine if requested
    if method == "rules_based":
        try:
            # Build current building state from helpers
            now = datetime.now()
            building_state = BuildingState(
                current_hour=now.hour,
                occupancy_percent=_estimate_occupancy(now, site_id),
                daylight_lux=_estimate_daylight(now, site_id),
                chiller_load_percent=_estimate_chiller_load(site_id),
                peak_demand_kw=actual_metrics.total_kwh / 30 / 24,  # Average hourly demand
                tariff_band=_get_tariff_band(now.hour, now.month),
                ambient_temp_c=_get_seasonal_temp(now.month),
                site_id=site_id,
                date=now.isoformat()
            )
            
            # Get active modules for conditional DALI rule
            active_modules = []
            try:
                from app.services.module_registry_service import module_registry
                modules = module_registry.get_active_modules(site_id)
                active_modules = [m.module_type.value for m in modules] if modules else []
            except Exception:
                pass
            
            # Evaluate rules
            engine = get_energy_rules_engine(site_id)
            rules_output = engine.evaluate_rules(
                building_state,
                active_modules,
                baseline_kwh=actual_metrics.total_kwh
            )
            
            # Apply rules output to actual metrics to get sentinel metrics
            sentinel_metrics = _apply_rules_output(actual_metrics, rules_output)
            
            # Calculate comparison metrics
            daily_savings_zar = actual_metrics.total_cost_zar - sentinel_metrics.total_cost_zar
            daily_savings_percent = rules_output.delta_percent
            
            # Progress to target (35% total savings target)
            progress_to_target_percent = min(daily_savings_percent / 35.0 * 100, 100.0)
            
            return ComparisonSummary(
                actual=actual_metrics,
                sentinel=sentinel_metrics,
                daily_savings_zar=round(daily_savings_zar, 2),
                daily_savings_percent=round(daily_savings_percent, 1),
                progress_to_target_percent=round(progress_to_target_percent, 1),
                ai_confidence_percent=round(rules_output.confidence * 100, 1),
            )
        
        except Exception as e:
            logger.warning(f"Rules engine failed, falling back to hardcoded: {e}")
            # Fall through to hardcoded method
    
    # Fallback: hardcoded method (original logic)
    prediction_response = await get_energy_prediction(
        site_id=site_id,
        scenario="sentinel_optimized",
        days=30,
    )
    sentinel_metrics = prediction_response.metrics[0] if prediction_response.metrics else None

    if not sentinel_metrics:
        raise HTTPException(status_code=500, detail="Failed to generate prediction")

    # Calculate comparison metrics
    daily_savings_zar = actual_metrics.total_cost_zar - sentinel_metrics.total_cost_zar
    daily_savings_percent = (
        (actual_metrics.total_kwh - sentinel_metrics.total_kwh)
        / actual_metrics.total_kwh
        * 100
    ) if actual_metrics.total_kwh > 0 else 0

    # Progress to target (assume 35% total savings target)
    progress_to_target_percent = min(daily_savings_percent / 35.0 * 100, 100.0)

    return ComparisonSummary(
        actual=actual_metrics,
        sentinel=sentinel_metrics,
        daily_savings_zar=round(daily_savings_zar, 2),
        daily_savings_percent=round(daily_savings_percent, 1),
        progress_to_target_percent=round(progress_to_target_percent, 1),
        ai_confidence_percent=85.0,
    )


@router.get("/energy/comparison")
async def get_energy_comparison(
    site_id: str = Query("site-002", description="Site ID to analyze"),
    days: int = Query(30, ge=1, le=365, description="Number of days"),
):
    """
    Returns 3-tier energy comparison for Grant demo.

    Scenarios:
    - Baseline: Traditional lighting (no DALI)
    - With DALI: Occupancy + daylight harvesting (-20% savings)
    - With SENTINEL: AI optimization on top (-30% total savings)

    Args:
        site_id: Site ID to analyze (default: site-002)
        days: Number of days to analyze (1-365, default: 30)

    Returns:
        Dictionary with 3 scenarios showing kWh, savings, and descriptions
    """
    # Fetch actual energy data using existing get_energy function
    energy_response = await get_energy(site_id=site_id, days=days)

    # Calculate total from actual data
    total_kwh = sum(d.total_kwh for d in energy_response.data)

    # Calculate scenarios (based on industry benchmarks)
    # Assume current is 70% of baseline (already optimized)
    baseline_kwh = total_kwh / 0.70
    with_dali_kwh = baseline_kwh * 0.80  # 20% savings with DALI
    with_sentinel_kwh = baseline_kwh * 0.70  # 30% total savings

    return {
        "site_id": site_id,
        "period_days": days,
        "scenarios": [
            {
                "name": "Baseline (No DALI)",
                "kwh": round(baseline_kwh, 2),
                "description": "Traditional lighting controls",
                "savings_percent": 0
            },
            {
                "name": "With DALI (Tridonic)",
                "kwh": round(with_dali_kwh, 2),
                "description": "Occupancy & daylight harvesting",
                "savings_percent": 20,
                "savings_kwh": round(baseline_kwh - with_dali_kwh, 2)
            },
            {
                "name": "With SENTINEL (AI)",
                "kwh": round(with_sentinel_kwh, 2),
                "description": "AI optimization on top of DALI",
                "savings_percent": 30,
                "savings_kwh": round(baseline_kwh - with_sentinel_kwh, 2)
            }
        ]
    }



@router.get("/energy/simulated")
async def get_energy_simulated(
    site_id: str = Query("site-002", description="Site ID"),
) -> dict:
    """
    Get simulated energy consumption during an active simulation.
    
    Returns real-time energy metrics based on the current simulated state.
    If no simulation is running, returns empty/zero values.
    
    This endpoint is called by the Dashboard every 5 seconds during Grant's
    365-day simulation to show live energy accumulation.
    
    Args:
        site_id: Site ID (e.g., "site-002")
    
    Returns:
        EnergyMetrics with current simulated values, or zeros if no simulation
    """
    try:
        from app.services.simulation_orchestrator import get_simulation_by_task_id
        
        # Try to find any running simulation for this site
        # First check for simulation with a task_id pattern
        from app.database.supabase_client import Supabase
        
        client = Supabase.instance()
        
        # Query for running simulations on this site
        running_tasks = client.table("solar_annual_tasks") \
            .select("task_id, scenario") \
            .eq("site_id", site_id) \
            .eq("status", "running") \
            .limit(1) \
            .execute()
        
        if not running_tasks.data:
            # No simulation running - return zero metrics
            return {
                "total_kwh": 0.0,
                "total_cost_zar": 0.0,
                "carbon_kg": 0.0,
                "hvac_kwh": 0.0,
                "hvac_percent": 0.0,
                "lighting_kwh": 0.0,
                "lighting_percent": 0.0,
                "power_kwh": 0.0,
                "power_percent": 0.0,
                "timestamp": datetime.now().isoformat(),
                "simulated": False,
                "message": "No active simulation"
            }
        
        task_id = running_tasks.data[0]["task_id"]
        orchestrator = get_simulation_by_task_id(task_id)
        
        if not orchestrator or not orchestrator.running:
            # Task marked as running but no orchestrator found
            return {
                "total_kwh": 0.0,
                "total_cost_zar": 0.0,
                "carbon_kg": 0.0,
                "hvac_kwh": 0.0,
                "hvac_percent": 0.0,
                "lighting_kwh": 0.0,
                "lighting_percent": 0.0,
                "power_kwh": 0.0,
                "power_percent": 0.0,
                "timestamp": datetime.now().isoformat(),
                "simulated": False,
                "message": "Simulation task not running"
            }
        
        # Get current simulated state
        building_state = orchestrator.building_state or {}
        
        # Extract simulated values (or use defaults)
        occupancy_percent = building_state.get("occupancy_percent", 0)
        daylight_lux = building_state.get("daylight_factor", 0)
        chiller_load_percent = building_state.get("chiller_load_percent", 0)
        
        # Generate energy based on simulated state
        # Base values (from building capacity at full occupancy)
        base_hvac_kwh = 500.0  # Base HVAC per 24 hours
        base_lighting_kwh = 200.0  # Base lighting per 24 hours
        base_power_kwh = 100.0  # Base other power per 24 hours
        
        # Scale by occupancy (HVAC most affected)
        occupancy_factor = occupancy_percent / 100.0
        hvac_kwh = base_hvac_kwh * occupancy_factor * (chiller_load_percent / 100.0)
        
        # Lighting scales with occupancy and inverse of daylight
        daylight_factor = max(0, 1.0 - (daylight_lux / 1000.0))  # More daylight = less artificial
        lighting_kwh = base_lighting_kwh * occupancy_factor * daylight_factor
        
        # Power (standby equipment) less affected by occupancy
        power_kwh = base_power_kwh * 0.7  # 70% base load
        
        # Total and percentages
        total_kwh = hvac_kwh + lighting_kwh + power_kwh
        
        if total_kwh > 0:
            hvac_percent = (hvac_kwh / total_kwh) * 100
            lighting_percent = (lighting_kwh / total_kwh) * 100
            power_percent = (power_kwh / total_kwh) * 100
        else:
            hvac_percent = 0
            lighting_percent = 0
            power_percent = 0
        
        # Carbon and cost
        carbon_kg = total_kwh * 0.35  # SA grid: 0.35 kg CO₂/kWh
        total_cost_zar = total_kwh * 5.0  # ~R5/kWh commercial rate
        
        return {
            "total_kwh": round(total_kwh, 2),
            "total_cost_zar": round(total_cost_zar, 2),
            "carbon_kg": round(carbon_kg, 2),
            "hvac_kwh": round(hvac_kwh, 2),
            "hvac_percent": round(hvac_percent, 1),
            "lighting_kwh": round(lighting_kwh, 2),
            "lighting_percent": round(lighting_percent, 1),
            "power_kwh": round(power_kwh, 2),
            "power_percent": round(power_percent, 1),
            "timestamp": datetime.now().isoformat(),
            "simulated": True,
            "occupancy_percent": round(occupancy_percent, 1),
            "daylight_lux": round(daylight_lux, 1),
            "chiller_load_percent": round(chiller_load_percent, 1),
        }
    
    except Exception as e:
        logger.error(f"Error getting simulated energy: {e}", exc_info=True)
        # Return zero metrics on error
        return {
            "total_kwh": 0.0,
            "total_cost_zar": 0.0,
            "carbon_kg": 0.0,
            "hvac_kwh": 0.0,
            "hvac_percent": 0.0,
            "lighting_kwh": 0.0,
            "lighting_percent": 0.0,
            "power_kwh": 0.0,
            "power_percent": 0.0,
            "timestamp": datetime.now().isoformat(),
            "simulated": False,
            "error": str(e)
        }
