"""Sites API endpoints."""

import json
import logging
from pathlib import Path
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config.settings import settings
from app.database.repositories import BuildingRepository, AlertRepository

router = APIRouter()
logger = logging.getLogger(__name__)

# Load sites data (fallback)
DATA_DIR = Path(__file__).parent.parent / "data"


def load_sites() -> list[dict]:
    """Load sites from JSON file (fallback)."""
    sites_file = DATA_DIR / "sites.json"
    if sites_file.exists():
        with open(sites_file) as f:
            return json.load(f)
    return []


def load_equipment() -> list[dict]:
    """Load equipment from JSON file (fallback)."""
    equipment_file = DATA_DIR / "equipment.json"
    if equipment_file.exists():
        with open(equipment_file) as f:
            return json.load(f)
    return []


def load_alerts() -> list[dict]:
    """Load alerts from JSON file (fallback)."""
    alerts_file = DATA_DIR / "alerts.json"
    if alerts_file.exists():
        with open(alerts_file) as f:
            return json.load(f)
    return []


def get_json_asset_counts(site_id: str) -> dict:
    """Aggregate asset counts from all JSON sources for a site.

    Counts assets from:
    - equipment.json (legacy equipment)
    - buildings/{building_code}/zones.json (HVAC zones)
    - buildings/{building_code}/generators.json (generators, groups, tanks)
    - buildings/{building_code}/energy_centre.json (EC components)
    - dali_mock_data.json (DALI controllers by building)

    Returns:
        Dict with total_assets and breakdown by category
    """
    # Map site_id to building_code (for modular building structure)
    # TODO: Store this mapping in sites.json or buildings registry
    SITE_TO_BUILDING = {
        "site-002": "sandton",  # Sandton City Office Tower -> sandton folder
    }

    building_code = SITE_TO_BUILDING.get(site_id, site_id)

    counts = {
        "equipment": 0,
        "hvac_zones": 0,
        "generators": 0,
        "generator_groups": 0,
        "diesel_tanks": 0,
        "energy_centre": 0,
        "dali_controllers": 0,
    }

    # 1. Legacy equipment from equipment.json
    equipment_file = DATA_DIR / "equipment.json"
    if equipment_file.exists():
        with open(equipment_file) as f:
            equipment = json.load(f)
            counts["equipment"] = len([e for e in equipment if e.get("site_id") == site_id])

    # 2. Building-specific data
    building_path = DATA_DIR / "buildings" / building_code

    # HVAC zones
    zones_file = building_path / "zones.json"
    if zones_file.exists():
        with open(zones_file) as f:
            zones = json.load(f)
            counts["hvac_zones"] = len(zones)

    # Generators (includes generators, groups, tanks)
    generators_file = building_path / "generators.json"
    if generators_file.exists():
        with open(generators_file) as f:
            gen_data = json.load(f)
            counts["generators"] = len(gen_data.get("generators", []))
            counts["generator_groups"] = len(gen_data.get("groups", []))
            counts["diesel_tanks"] = len(gen_data.get("diesel_tanks", []))

    # Energy centre components
    ec_file = building_path / "energy_centre.json"
    if ec_file.exists():
        with open(ec_file) as f:
            ec_data = json.load(f)
            ec_count = 1 if ec_data else 0  # The energy centre itself
            ec_count += len(ec_data.get("mv_incomers", []))
            ec_count += len(ec_data.get("transformers", []))
            ec_count += len(ec_data.get("lv_switchboards", []))
            ec_count += len(ec_data.get("ats_units", []))
            ec_count += len(ec_data.get("power_meters", []))
            ec_count += len(ec_data.get("pfc_banks", []))
            ec_count += len(ec_data.get("ups_systems", []))
            ec_count += len(ec_data.get("feeders", []))
            counts["energy_centre"] = ec_count

    # 3. DALI controllers from dali_mock_data.json
    dali_file = DATA_DIR / "dali_mock_data.json"
    if dali_file.exists():
        with open(dali_file) as f:
            dali_data = json.load(f)
            # Check if site_id matches (flat structure) or building_id matches (nested)
            if dali_data.get("site_id") == site_id:
                counts["dali_controllers"] = len(dali_data.get("controllers", []))
            else:
                # Try nested buildings structure
                for building in dali_data.get("buildings", []):
                    if building.get("building_id", "").lower() == building_code.lower():
                        counts["dali_controllers"] = len(building.get("controllers", []))
                        break

    # Calculate total
    total = sum(counts.values())

    return {
        "total_assets": total,
        "breakdown": counts,
    }


def calculate_site_status(site_alerts: list[dict]) -> Literal["normal", "warning", "critical"]:
    """Calculate site status based on active alerts."""
    if not site_alerts:
        return "normal"

    has_critical = any(
        a.get("severity", "").lower() == "critical"
        for a in site_alerts
    )
    if has_critical:
        return "critical"

    has_warning = any(
        a.get("severity", "").lower() in ["warning", "high"]
        for a in site_alerts
    )
    if has_warning:
        return "warning"

    return "normal"


def db_to_site_dict(
    db_building: dict,
    equipment_count: int = 0,
    alert_count: int = 0,
    asset_summary: Optional[dict] = None
) -> dict:
    """Convert database building record to API-compatible site dict.

    Args:
        db_building: Building record from database
        equipment_count: Legacy equipment count (fallback)
        alert_count: Active alert count
        asset_summary: Asset summary from v_building_asset_summary view (if available)
    """
    operating_hours = db_building.get("operating_hours") or {}
    if isinstance(operating_hours, str):
        operating_hours = json.loads(operating_hours)

    # Use total_assets from summary if available, otherwise fall back to equipment_count
    if asset_summary:
        total_assets = asset_summary.get("total_assets", 0)
    else:
        total_assets = equipment_count or db_building.get("equipment_count", 0)

    result = {
        "id": db_building.get("code"),
        "name": db_building.get("name"),
        "address": db_building.get("address", ""),
        "region": db_building.get("region", ""),
        "type": db_building.get("type", "branch"),
        "sqm": db_building.get("sqm", 0),
        "floors": db_building.get("floors", 1),
        "year_built": db_building.get("year_built", 2020),
        "operating_hours": operating_hours if operating_hours else {"start": "08:00", "end": "18:00"},
        "timezone": db_building.get("timezone", "Africa/Johannesburg"),
        "occupancy_pattern": db_building.get("occupancy_pattern", "office"),
        "latitude": float(db_building.get("latitude", 0)) if db_building.get("latitude") else 0.0,
        "longitude": float(db_building.get("longitude", 0)) if db_building.get("longitude") else 0.0,
        "contact_email": db_building.get("contact_email", ""),
        "contact_phone": db_building.get("contact_phone", ""),
        "optimization_enabled": db_building.get("optimization_enabled", False),
        "optimization_status": db_building.get("optimization_status") or "unknown",
        "control_enabled": db_building.get("control_enabled", False),
        "control_note": db_building.get("control_note"),
        "equipment_count": total_assets,  # Total assets (renamed from equipment_count for API compat)
        "alert_count": alert_count,
        "active_alerts": alert_count,
    }

    # Include asset breakdown if available
    if asset_summary:
        result["asset_breakdown"] = {
            "equipment": asset_summary.get("equipment_count", 0),
            "hvac_zones": asset_summary.get("hvac_zone_count", 0),
            "generators": asset_summary.get("generator_count", 0),
            "generator_groups": asset_summary.get("generator_group_count", 0),
            "diesel_tanks": asset_summary.get("diesel_tank_count", 0),
            "energy_centre": (
                asset_summary.get("energy_centre_count", 0) +
                asset_summary.get("mv_incomer_count", 0) +
                asset_summary.get("transformer_count", 0) +
                asset_summary.get("lv_switchboard_count", 0) +
                asset_summary.get("ats_count", 0) +
                asset_summary.get("power_meter_count", 0) +
                asset_summary.get("pfc_bank_count", 0) +
                asset_summary.get("ups_count", 0) +
                asset_summary.get("feeder_count", 0)
            ),
            "dali_controllers": asset_summary.get("dali_controller_count", 0),
        }

    return result


class OperatingHours(BaseModel):
    """Operating hours model."""
    start: str
    end: str


class SiteBase(BaseModel):
    """Base site model."""
    id: str
    name: str
    address: str
    region: str
    type: str
    sqm: int
    floors: int
    year_built: int
    operating_hours: OperatingHours
    timezone: str = "Africa/Johannesburg"  # IANA timezone
    occupancy_pattern: str
    latitude: float
    longitude: float
    contact_email: str
    contact_phone: str


class SiteResponse(SiteBase):
    """Site response with computed fields."""
    equipment_count: int = 0
    active_alerts: int = 0
    alert_count: int = 0
    location: str = ""
    status: Literal["normal", "warning", "critical"] = "normal"
    optimization_enabled: bool = False
    optimization_status: str = "unknown"
    control_enabled: bool = False
    control_note: Optional[str] = None


class SiteListResponse(BaseModel):
    """Response for site list."""
    total: int
    sites: list[SiteResponse]


def get_sites_from_supabase(
    region: Optional[str] = None,
    site_type: Optional[str] = None
) -> tuple[list[dict], bool]:
    """Try to get sites from Supabase. Returns (sites, success)."""
    if settings.use_json_storage:
        return [], False

    try:
        repo = BuildingRepository()
        buildings = repo.get_all(region=region, site_type=site_type)

        if not buildings:
            return [], False

        sites = []
        for b in buildings:
            # Get equipment and alert counts
            building_uuid = b.get("id")
            building_code = b.get("code")

            # Try to get asset summary from view
            asset_summary = None
            if building_code:
                asset_summary = repo.get_asset_summary_by_code(building_code)

            # Fallback to legacy equipment count
            eq_count = repo.get_equipment_count(building_uuid) if building_uuid else 0
            alert_count = repo.get_alert_count(building_uuid) if building_uuid else 0

            sites.append(db_to_site_dict(b, eq_count, alert_count, asset_summary))

        return sites, True
    except Exception as e:
        logger.warning(f"Supabase query failed, falling back to JSON: {e}")
        return [], False


def get_site_from_supabase(site_id: str) -> tuple[Optional[dict], bool]:
    """Try to get a single site from Supabase. Returns (site, success)."""
    if settings.use_json_storage:
        return None, False

    try:
        repo = BuildingRepository()
        building = repo.get_by_id(site_id)

        if not building:
            return None, True  # Success but not found

        building_uuid = building.get("id")

        # Try to get asset summary from view
        asset_summary = repo.get_asset_summary_by_code(site_id)

        # Fallback to legacy equipment count
        eq_count = repo.get_equipment_count(building_uuid) if building_uuid else 0
        alert_count = repo.get_alert_count(building_uuid) if building_uuid else 0

        return db_to_site_dict(building, eq_count, alert_count, asset_summary), True
    except Exception as e:
        logger.warning(f"Supabase query failed, falling back to JSON: {e}")
        return None, False


@router.get("/sites", response_model=SiteListResponse)
async def list_sites(
    region: Optional[str] = Query(None, description="Filter by region"),
    site_type: Optional[str] = Query(None, alias="type", description="Filter by type"),
) -> SiteListResponse:
    """List all sites with optional filtering."""

    # Try Supabase first
    sites, success = get_sites_from_supabase(region, site_type)

    if success and sites:
        result = []
        for site in sites:
            status = "normal"  # Default status, alerts already counted
            if site.get("alert_count", 0) > 0:
                status = "warning"
            result.append(
                SiteResponse(
                    **site,
                    location=site.get("address", ""),
                    status=status,
                )
            )
        return SiteListResponse(total=len(result), sites=result)

    # Fallback to JSON
    sites = load_sites()
    alerts = load_alerts()

    if region:
        sites = [s for s in sites if s["region"].lower() == region.lower()]
    if site_type:
        sites = [s for s in sites if s["type"].lower() == site_type.lower()]

    result = []
    for site in sites:
        site_id = site["id"]

        # Get aggregated asset counts from all JSON sources
        asset_counts = get_json_asset_counts(site_id)

        site_alerts = [
            a for a in alerts if a.get("site_id") == site_id and a.get("status") == "active"
        ]
        status = calculate_site_status(site_alerts)
        alert_count = len(site_alerts)

        site_response = SiteResponse(
            **site,
            equipment_count=asset_counts["total_assets"],
            active_alerts=alert_count,
            alert_count=alert_count,
            status=status,
        )

        # Add asset breakdown to the response dict (for SiteCard tooltip)
        site_dict = site_response.model_dump()
        site_dict["asset_breakdown"] = asset_counts["breakdown"]
        result.append(site_dict)

    # Convert back to SiteResponse objects (with extra fields preserved)
    return SiteListResponse(total=len(result), sites=[SiteResponse(**s) for s in result])


@router.get("/sites/{site_id}", response_model=SiteResponse)
async def get_site(site_id: str) -> SiteResponse:
    """Get a single site by ID."""

    # Try Supabase first
    site, success = get_site_from_supabase(site_id)

    if success:
        if site:
            status = "normal"
            if site.get("alert_count", 0) > 0:
                status = "warning"
            return SiteResponse(
                **site,
                location=site.get("address", ""),
                status=status,
            )
        else:
            raise HTTPException(status_code=404, detail=f"Site {site_id} not found")

    # Fallback to JSON
    sites = load_sites()
    alerts = load_alerts()

    site = next((s for s in sites if s["id"] == site_id), None)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site {site_id} not found")

    # Get aggregated asset counts from all JSON sources
    asset_counts = get_json_asset_counts(site_id)

    site_alerts = [
        a for a in alerts if a.get("site_id") == site_id and a.get("status") == "active"
    ]
    alert_count = len(site_alerts)
    status = calculate_site_status(site_alerts)

    return SiteResponse(
        **site,
        equipment_count=asset_counts["total_assets"],
        active_alerts=alert_count,
        alert_count=alert_count,
        location=site.get("address", ""),
        status=status,
    )
