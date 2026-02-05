"""
Building Management API
=======================
REST API for managing buildings (onboarding, configuration, activation).

To add a new building:
1. POST /api/buildings - Create building with metadata
2. POST /api/buildings/{id}/desks - Upload desk data
3. POST /api/buildings/{id}/zones - Upload zone data
4. POST /api/buildings/{id}/activate - Activate building

To remove a building:
1. POST /api/buildings/{id}/deactivate - Deactivate (keeps data)
2. DELETE /api/buildings/{id} - Remove completely
"""

import json
import logging
import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.services.building_loader import get_building_loader, Building
from app.services.device_abstraction import device_manager

logger = logging.getLogger(__name__)


def _normalize_device_id(device_id: str) -> str:
    """Normalize device ID to S### format for matching.

    Converts 'site-002-xxx' to 'S002-xxx' format.
    """
    import re
    # Match 'site-NNN-' prefix and convert to 'SNNN-'
    match = re.match(r'^site-(\d+)-(.+)$', device_id, re.IGNORECASE)
    if match:
        site_num = match.group(1).zfill(3)  # Zero-pad to 3 digits
        rest = match.group(2)
        return f"S{site_num}-{rest}"
    return device_id


def _is_device_controllable(device_id: str, equipment_points: dict) -> bool:
    """Check if device is controllable by checking equipment points or device_manager.

    First checks if the equipment JSON has writable points.
    If not, falls back to checking if the device exists in device_manager with writable points.
    Handles ID format differences (site-002-xxx vs S002-xxx).
    """
    # Check equipment JSON points first
    if any(p.get("writable", False) for p in equipment_points.values()):
        return True

    # Fall back to device_manager (which includes mock_devices.json)
    # Access the internal _devices dict directly since this is a sync function
    try:
        # Try original ID first
        device = device_manager._devices.get(device_id)

        # If not found, try normalized ID (site-002-xxx -> S002-xxx)
        if not device:
            normalized_id = _normalize_device_id(device_id)
            device = device_manager._devices.get(normalized_id)

        if device and device.points:
            return any(p.writable for p in device.points.values())
    except Exception as e:
        logger.debug(f"Could not check device_manager for {device_id}: {e}")

    return False
router = APIRouter(prefix="/api/buildings", tags=["Building Management"])

# Data path
DATA_PATH = Path(__file__).parent.parent / "data" / "buildings"


class BuildingCreate(BaseModel):
    """Request model for creating a building."""
    id: str
    name: str
    display_name: Optional[str] = None
    address: Optional[str] = ""
    timezone: str = "Africa/Johannesburg"
    floors: List[str] = []
    features: dict = {}


class BuildingUpdate(BaseModel):
    """Request model for updating a building."""
    name: Optional[str] = None
    display_name: Optional[str] = None
    address: Optional[str] = None
    timezone: Optional[str] = None
    floors: Optional[List[str]] = None
    features: Optional[dict] = None


@router.get("")
async def list_buildings() -> dict:
    """
    List all buildings (active and inactive).

    Returns:
        - active: List of active buildings
        - inactive: List of inactive buildings (folders exist but not in registry)
        - default_building: The default building ID
    """
    loader = get_building_loader()
    loader.load(force=True)  # Refresh

    registry = loader.get_registry()
    active_ids = set(registry.get("active_buildings", []))

    # Find all building folders
    all_building_folders = []
    if DATA_PATH.exists():
        for folder in DATA_PATH.iterdir():
            if folder.is_dir() and not folder.name.startswith("_"):
                all_building_folders.append(folder.name)

    # Categorize
    active = []
    inactive = []

    for building_id in all_building_folders:
        building = loader.get_building(building_id)
        if building:
            info = building.to_dict()
            info["status"] = "active" if building_id in active_ids else "inactive"
            if building_id in active_ids:
                active.append(info)
            else:
                inactive.append(info)

    return {
        "active": active,
        "inactive": inactive,
        "default_building": registry.get("default_building"),
        "total": len(active) + len(inactive),
    }


@router.get("/{building_id}")
async def get_building(building_id: str) -> dict:
    """
    Get building details.

    Returns building metadata, desk count, zone count.

    Maps friendly building names (e.g., 'sandton') to site codes (e.g., 'site-002')
    """
    # Map building_id to site code for JSON lookup
    BUILDING_TO_SITE = {"sandton": "site-002"}
    site_code = BUILDING_TO_SITE.get(building_id, building_id)

    loader = get_building_loader()
    building = loader.get_building(site_code)

    if not building:
        raise HTTPException(status_code=404, detail=f"Building '{building_id}' (site '{site_code}') not found")

    desks = loader.get_desks(site_code)
    zones = loader.get_zones(site_code)

    result = building.to_dict()
    result["desk_count"] = len(desks)
    result["zone_count"] = len(zones)
    result["is_active"] = site_code in loader.get_active_building_ids()

    return result


@router.post("")
async def create_building(building: BuildingCreate) -> dict:
    """
    Create a new building.

    Creates the building folder structure and config files.
    Building is NOT activated by default - call /activate after setup.
    """
    building_path = DATA_PATH / building.id

    # Check if already exists
    if building_path.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Building '{building.id}' already exists"
        )

    # Create folder structure
    building_path.mkdir(parents=True, exist_ok=True)

    # Create building.json
    building_data = {
        "id": building.id,
        "name": building.name,
        "display_name": building.display_name or building.name,
        "address": building.address,
        "timezone": building.timezone,
        "floors": building.floors,
        "features": building.features or {
            "hvac": True,
            "dali": False,
            "desk_diagnosis": True,
        },
        "metadata": {
            "created_at": "auto",
        }
    }

    with open(building_path / "building.json", "w") as f:
        json.dump(building_data, f, indent=2)

    # Create empty desks.json
    with open(building_path / "desks.json", "w") as f:
        json.dump([], f, indent=2)

    # Create empty zones.json
    with open(building_path / "zones.json", "w") as f:
        json.dump([], f, indent=2)

    logger.info(f"Created building: {building.id}")

    return {
        "id": building.id,
        "name": building.name,
        "status": "created",
        "message": f"Building created. Upload desks/zones, then call /activate.",
        "next_steps": [
            f"POST /api/buildings/{building.id}/desks - Upload desk data",
            f"POST /api/buildings/{building.id}/zones - Upload zone data",
            f"POST /api/buildings/{building.id}/activate - Activate building",
        ]
    }


@router.post("/{building_id}/desks")
async def upload_desks(building_id: str, desks: List[dict]) -> dict:
    """
    Upload/replace desk data for a building.

    Expects array of desk objects. Building field is added automatically.
    Maps 'sandton' to 'site-002' for file operations.
    """
    BUILDING_TO_SITE = {"sandton": "site-002"}
    site_code = BUILDING_TO_SITE.get(building_id, building_id)
    building_path = DATA_PATH / site_code

    if not building_path.exists():
        raise HTTPException(status_code=404, detail=f"Building '{building_id}' (site '{site_code}') not found")

    # Validate and save
    for desk in desks:
        if "desk_id" not in desk:
            raise HTTPException(status_code=400, detail="Each desk must have a desk_id")

    with open(building_path / "desks.json", "w") as f:
        json.dump(desks, f, indent=2)

    # Reload
    loader = get_building_loader()
    loader.load(force=True)

    return {
        "building_id": building_id,
        "desks_uploaded": len(desks),
        "status": "success",
    }


@router.post("/{building_id}/zones")
async def upload_zones(building_id: str, zones: List[dict]) -> dict:
    """
    Upload/replace zone data for a building.

    Expects array of zone objects.
    Maps 'sandton' to 'site-002' for file operations.
    """
    BUILDING_TO_SITE = {"sandton": "site-002"}
    site_code = BUILDING_TO_SITE.get(building_id, building_id)
    building_path = DATA_PATH / site_code

    if not building_path.exists():
        raise HTTPException(status_code=404, detail=f"Building '{building_id}' (site '{site_code}') not found")

    # Validate and save
    for zone in zones:
        if "zone_id" not in zone:
            raise HTTPException(status_code=400, detail="Each zone must have a zone_id")

    with open(building_path / "zones.json", "w") as f:
        json.dump(zones, f, indent=2)

    # Reload
    loader = get_building_loader()
    loader.load(force=True)

    return {
        "building_id": building_id,
        "zones_uploaded": len(zones),
        "status": "success",
    }


@router.post("/{building_id}/activate")
async def activate_building(building_id: str, set_default: bool = False) -> dict:
    """
    Activate a building (add to registry).

    Args:
        set_default: If True, also set as the default building
    Maps 'sandton' to 'site-002' for file operations.
    """
    BUILDING_TO_SITE = {"sandton": "site-002"}
    site_code = BUILDING_TO_SITE.get(building_id, building_id)
    building_path = DATA_PATH / site_code

    if not building_path.exists():
        raise HTTPException(status_code=404, detail=f"Building '{building_id}' (site '{site_code}') not found")

    # Load and update registry
    registry_path = DATA_PATH / "_registry.json"
    if registry_path.exists():
        with open(registry_path) as f:
            registry = json.load(f)
    else:
        registry = {"active_buildings": [], "default_building": None}

    # Add to active if not already (use site_code for registry)
    if site_code not in registry["active_buildings"]:
        registry["active_buildings"].append(site_code)

    # Set as default if requested or if first building (use site_code for registry)
    if set_default or not registry.get("default_building"):
        registry["default_building"] = site_code

    # Save registry
    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2)

    # Reload
    loader = get_building_loader()
    loader.load(force=True)

    logger.info(f"Activated building: {building_id} -> {site_code}")

    return {
        "building_id": building_id,
        "site_code": site_code,
        "status": "active",
        "is_default": registry["default_building"] == site_code,
        "message": f"Building '{building_id}' (site '{site_code}') is now active",
    }


@router.post("/{building_id}/deactivate")
async def deactivate_building(building_id: str) -> dict:
    """
    Deactivate a building (remove from registry but keep data).
    Maps 'sandton' to 'site-002' for registry operations.
    """
    BUILDING_TO_SITE = {"sandton": "site-002"}
    site_code = BUILDING_TO_SITE.get(building_id, building_id)

    registry_path = DATA_PATH / "_registry.json"

    if not registry_path.exists():
        raise HTTPException(status_code=404, detail="No registry found")

    with open(registry_path) as f:
        registry = json.load(f)

    if site_code not in registry.get("active_buildings", []):
        raise HTTPException(status_code=400, detail=f"Building '{building_id}' (site '{site_code}') is not active")

    # Remove from active
    registry["active_buildings"].remove(site_code)

    # Clear default if this was the default
    if registry.get("default_building") == site_code:
        registry["default_building"] = registry["active_buildings"][0] if registry["active_buildings"] else None

    # Save registry
    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2)

    # Reload
    loader = get_building_loader()
    loader.load(force=True)

    logger.info(f"Deactivated building: {building_id}")

    return {
        "building_id": building_id,
        "status": "inactive",
        "message": f"Building '{building_id}' deactivated. Data preserved.",
    }


@router.delete("/{building_id}")
async def delete_building(building_id: str, confirm: bool = False) -> dict:
    """
    Delete a building and all its data.

    Requires confirm=true to actually delete.
    Maps 'sandton' to 'site-002' for file operations.
    """
    BUILDING_TO_SITE = {"sandton": "site-002"}
    site_code = BUILDING_TO_SITE.get(building_id, building_id)

    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Add ?confirm=true to confirm deletion"
        )

    building_path = DATA_PATH / site_code

    if not building_path.exists():
        raise HTTPException(status_code=404, detail=f"Building '{building_id}' (site '{site_code}') not found")

    # First deactivate
    registry_path = DATA_PATH / "_registry.json"
    if registry_path.exists():
        with open(registry_path) as f:
            registry = json.load(f)
        if site_code in registry.get("active_buildings", []):
            registry["active_buildings"].remove(site_code)
        if registry.get("default_building") == site_code:
            registry["default_building"] = registry["active_buildings"][0] if registry["active_buildings"] else None
        with open(registry_path, "w") as f:
            json.dump(registry, f, indent=2)

    # Delete folder
    shutil.rmtree(building_path)

    # Reload
    loader = get_building_loader()
    loader.load(force=True)

    logger.info(f"Deleted building: {building_id} -> {site_code}")

    return {
        "building_id": building_id,
        "site_code": site_code,
        "status": "deleted",
        "message": f"Building '{building_id}' (site '{site_code}') and all data deleted",
    }


@router.get("/{building_id}/desks")
async def get_building_desks(building_id: str) -> List[dict]:
    """Get all desks for a building. Maps 'sandton' to 'site-002'."""
    BUILDING_TO_SITE = {"sandton": "site-002"}
    site_code = BUILDING_TO_SITE.get(building_id, building_id)

    loader = get_building_loader()
    desks = loader.get_desks(site_code)
    if not desks and site_code not in loader.get_active_building_ids():
        raise HTTPException(status_code=404, detail=f"Building '{building_id}' (site '{site_code}') not found")
    return desks


@router.get("/{building_id}/zones")
async def get_building_zones(building_id: str) -> List[dict]:
    """Get all zones for a building. Maps 'sandton' to 'site-002'."""
    BUILDING_TO_SITE = {"sandton": "site-002"}
    site_code = BUILDING_TO_SITE.get(building_id, building_id)

    loader = get_building_loader()
    zones = loader.get_zones(site_code)
    if not zones and site_code not in loader.get_active_building_ids():
        raise HTTPException(status_code=404, detail=f"Building '{building_id}' (site '{site_code}') not found")
    return zones


@router.get("/{building_id}/equipment-summary")
async def get_equipment_summary(building_id: str) -> dict:
    """
    Get equipment count breakdown by category for a building.

    Returns categorized counts:
    - hvac_zones: HVAC thermal zones
    - generators, generator_groups, diesel_tanks: Generator plant
    - energy_centre components (transformers, meters, UPS, etc.)
    - dali_controllers: Lighting controllers
    - legacy_equipment: From equipment.json

    Note: Desks and luminaires are NOT counted as equipment.
    """
    # Try Supabase first
    try:
        from app.database.repositories.building_repository import BuildingRepository
        repo = BuildingRepository()
        summary = repo.get_asset_summary_by_code(building_id)

        if summary:
            return {
                "building_id": building_id,
                "building_name": summary.get("building_name"),
                "total_assets": summary.get("total_assets", 0),
                "categories": {
                    "equipment": summary.get("equipment_count", 0),
                    "hvac_zones": summary.get("hvac_zone_count", 0),
                    "generators": summary.get("generator_count", 0),
                    "generator_groups": summary.get("generator_group_count", 0),
                    "diesel_tanks": summary.get("diesel_tank_count", 0),
                    "energy_centres": summary.get("energy_centre_count", 0),
                    "mv_incomers": summary.get("mv_incomer_count", 0),
                    "transformers": summary.get("transformer_count", 0),
                    "lv_switchboards": summary.get("lv_switchboard_count", 0),
                    "ats_units": summary.get("ats_count", 0),
                    "power_meters": summary.get("power_meter_count", 0),
                    "pfc_banks": summary.get("pfc_bank_count", 0),
                    "ups_systems": summary.get("ups_count", 0),
                    "feeders": summary.get("feeder_count", 0),
                    "dali_controllers": summary.get("dali_controller_count", 0),
                },
                "supplementary": {
                    "desks": summary.get("desk_count", 0),
                    "luminaires": summary.get("luminaire_count", 0),
                    "dali_sensors": summary.get("dali_sensor_count", 0),
                },
                "source": "supabase",
            }
    except Exception as e:
        logger.debug(f"Supabase asset summary failed: {e}")

    # Fall back to JSON file counting
    # Map building_id to site code for JSON lookup
    BUILDING_TO_SITE = {"sandton": "site-002"}
    site_code = BUILDING_TO_SITE.get(building_id, building_id)

    loader = get_building_loader()
    building = loader.get_building(site_code)

    if not building:
        raise HTTPException(status_code=404, detail=f"Building '{building_id}' (site '{site_code}') not found")

    building_path = DATA_PATH / site_code

    # Count from JSON files
    counts = {
        "equipment": 0,
        "hvac_zones": 0,
        "generators": 0,
        "generator_groups": 0,
        "diesel_tanks": 0,
        "energy_centres": 0,
        "mv_incomers": 0,
        "transformers": 0,
        "lv_switchboards": 0,
        "ats_units": 0,
        "power_meters": 0,
        "pfc_banks": 0,
        "ups_systems": 0,
        "feeders": 0,
        "dali_controllers": 0,
    }

    # HVAC zones
    zones_file = building_path / "zones.json"
    if zones_file.exists():
        with open(zones_file) as f:
            zones = json.load(f)
            counts["hvac_zones"] = len(zones)

    # Generators
    gen_file = building_path / "generators.json"
    if gen_file.exists():
        with open(gen_file) as f:
            gen_data = json.load(f)
            counts["generators"] = len(gen_data.get("generators", []))
            counts["generator_groups"] = len(gen_data.get("groups", []))
            counts["diesel_tanks"] = len(gen_data.get("diesel_tanks", []))

    # Energy centre
    ec_file = building_path / "energy_centre.json"
    if ec_file.exists():
        with open(ec_file) as f:
            ec_data = json.load(f)
            counts["energy_centres"] = 1 if ec_data.get("energy_centre") else 0
            counts["mv_incomers"] = len(ec_data.get("mv_incomers", []))
            counts["transformers"] = len(ec_data.get("transformers", []))
            counts["lv_switchboards"] = len(ec_data.get("lv_switchboards", []))
            counts["ats_units"] = len(ec_data.get("ats_units", []))
            counts["power_meters"] = len(ec_data.get("power_meters", []))
            counts["pfc_banks"] = len(ec_data.get("pfc_banks", []))
            counts["ups_systems"] = len(ec_data.get("ups_systems", []))
            counts["feeders"] = len(ec_data.get("feeders", []))

    # DALI controllers (from main data dir)
    dali_file = Path(__file__).parent.parent / "data" / "dali_mock_data.json"
    if dali_file.exists():
        with open(dali_file) as f:
            dali_data = json.load(f)
            # Count controllers for this site
            controllers = dali_data.get("controllers", [])
            counts["dali_controllers"] = len([
                c for c in controllers
                if c.get("site_id") == building_id
            ])

    # Calculate total
    total = sum(counts.values())

    # Supplementary counts (not in total)
    desks_file = building_path / "desks.json"
    desk_count = 0
    if desks_file.exists():
        with open(desks_file) as f:
            desks = json.load(f)
            desk_count = len(desks)

    return {
        "building_id": building_id,
        "building_name": building.name,
        "total_assets": total,
        "categories": counts,
        "supplementary": {
            "desks": desk_count,
            "luminaires": 0,  # Not counted from JSON
            "dali_sensors": 0,  # Not counted from JSON
        },
        "source": "json",
    }


@router.get("/{building_id}/equipment")
async def get_building_equipment(building_id: str) -> dict:
    """
    Get all equipment for a building with status.

    Returns all equipment items from:
    - Supabase equipment table (primary source)
    - JSON fallback: HVAC zones, generators, energy centre, DALI controllers

    Each item includes: id, name, type, category, status, health, details
    """
    # Map building_id to site code for Supabase lookup
    BUILDING_TO_SITE = {"sandton": "site-002"}
    site_code = BUILDING_TO_SITE.get(building_id, building_id)

    # Try Supabase first
    try:
        from app.database.repositories.equipment_repository import EquipmentRepository
        repo = EquipmentRepository()
        equipment_data = repo.get_by_building_code(site_code)

        if equipment_data:
            # Get building info from Supabase (needed in the loop)
            from app.database.supabase_client import get_supabase_client
            client = get_supabase_client()
            building_result = client.table("buildings").select("id, name").eq("code", site_code).execute()
            building_name = building_result.data[0]["name"] if building_result.data else building_id
            building_uuid = building_result.data[0]["id"] if building_result.data else None

            # Cross-reference active alerts to derive equipment risk status
            alert_severity_map: dict[str, str] = {}  # equipment_uuid -> highest severity
            if building_uuid:
                try:
                    from app.database.repositories.alert_repository import AlertRepository
                    alert_repo = AlertRepository()
                    active_alerts = alert_repo.get_active_by_building(building_uuid)
                    for alert in active_alerts:
                        eq_uuid = alert.get("equipment_id")
                        if eq_uuid:
                            severity = alert.get("severity", "warning")
                            existing = alert_severity_map.get(eq_uuid)
                            if existing != "critical":
                                if severity == "critical" or existing is None:
                                    alert_severity_map[eq_uuid] = severity
                except Exception as e:
                    logger.warning(f"Failed to fetch alerts for equipment status: {e}")

            equipment_list = []
            categories = {}

            for eq in equipment_data:
                # Determine category from type
                eq_type = eq.get("type", "unknown").lower()
                type_to_category = {
                    "sensor": "Sensors",
                    "daylight_sensor": "Sensors",
                    "occupancy_sensor": "Sensors",
                    "vav": "HVAC",
                    "ahu": "HVAC",
                    "fcu": "HVAC",
                    "chiller": "HVAC",
                    "split_unit": "HVAC",
                    "cooling_tower": "HVAC",
                    "hvac_zone": "HVAC",
                    "generator": "Generator Plant",
                    "diesel_tank": "Generator Plant",
                    "generator_group": "Generator Plant",
                    "transformer": "Energy Centre",
                    "mv_incomer": "Energy Centre",
                    "lv_switchboard": "Energy Centre",
                    "ats": "Energy Centre",
                    "ups": "Energy Centre",
                    "power_meter": "Energy Centre",
                    "pfc_bank": "Energy Centre",
                    "feeder": "Energy Centre",
                    "dali_controller": "Lighting",
                    "luminaire": "Lighting",
                    "luminaire_group": "Lighting",
                    "bms_controller": "Building Systems",
                    "bms_scada": "Building Systems",
                    "lift-passenger": "Lifts",
                }
                category = type_to_category.get(eq_type, "Other")
                status = eq.get("status", "normal")
                health = eq.get("health_score", 85)

                # Override status if equipment has active alerts
                eq_uuid = eq.get("id")
                if eq_uuid and eq_uuid in alert_severity_map:
                    alert_sev = alert_severity_map[eq_uuid]
                    if alert_sev == "critical" and status != "critical":
                        status = "critical"
                        health = min(health, 30)
                    elif alert_sev == "warning" and status not in ("critical", "warning"):
                        status = "warning"
                        health = min(health, 60)

                equipment_list.append({
                    "id": eq.get("code", eq.get("id")),
                    "name": eq.get("name"),
                    "type": eq_type,
                    "category": category,
                    "status": status,
                    "health": health,
                    "location": eq.get("location", ""),
                    "building_id": site_code,
                    "building_name": building_name,
                    "site_id": building_id,  # API parameter (e.g., "site-002" or "sandton")
                    "details": {
                        "manufacturer": eq.get("manufacturer"),
                        "model": eq.get("model"),
                        "metadata": eq.get("metadata", {}),
                    },
                    "controllable": _is_device_controllable(
                        eq.get("code", eq.get("id", "")),
                        eq.get("points", {})
                    ),
                })

                # Update category stats
                if category not in categories:
                    categories[category] = {"total": 0, "normal": 0, "warning": 0, "critical": 0}
                categories[category]["total"] += 1
                if status == "normal":
                    categories[category]["normal"] += 1
                elif status == "warning":
                    categories[category]["warning"] += 1
                elif status == "critical":
                    categories[category]["critical"] += 1

            # Merge controllable status from building equipment directory (Niagara discovery)
            # The directory files have points with writable=true that Supabase doesn't have
            building_path = DATA_PATH / site_code
            equipment_dir = building_path / "equipment"
            if equipment_dir.exists():
                # Build lookup from directory files for controllable status
                dir_controllable = {}
                for eq_file in equipment_dir.glob("*.json"):
                    try:
                        with open(eq_file) as f:
                            eq = json.load(f)
                        eq_id = eq.get("id", eq.get("code", ""))
                        points = eq.get("points", {})
                        if any(p.get("writable", False) for p in points.values()):
                            dir_controllable[eq_id] = True
                    except Exception as e:
                        logger.warning(f"Failed to load equipment from {eq_file}: {e}")

                # Update controllable status for existing equipment
                for eq_item in equipment_list:
                    if eq_item["id"] in dir_controllable:
                        eq_item["controllable"] = True

            return {
                "building_id": building_id,
                "building_name": building_name,
                "total_equipment": len(equipment_list),
                "categories": categories,
                "equipment": equipment_list,
                "source": "supabase",
            }
    except Exception as e:
        logger.warning(f"Supabase equipment fetch failed for {building_id}: {e}")

    # Fall back to JSON files
    loader = get_building_loader()
    building = loader.get_building(site_code)

    if not building:
        raise HTTPException(status_code=404, detail=f"Building '{building_id}' (site '{site_code}') not found")

    building_path = DATA_PATH / site_code
    equipment_list = []

    def get_status_health(status: str) -> tuple:
        """Convert status to normalized status and health score."""
        status_map = {
            "running": ("normal", 95),
            "online": ("normal", 95),
            "healthy": ("normal", 95),
            "idle": ("normal", 85),
            "standby": ("normal", 80),
            "closed": ("normal", 90),
            "fault": ("critical", 30),
            "alarm": ("critical", 25),
            "offline": ("critical", 20),
            "warning": ("warning", 60),
            "maintenance": ("warning", 50),
        }
        return status_map.get(status.lower() if status else "unknown", ("unknown", 50))

    # 1. HVAC Zones
    zones_file = building_path / "zones.json"
    if zones_file.exists():
        with open(zones_file) as f:
            zones = json.load(f)
            for zone in zones:
                status, health = get_status_health(zone.get("status", "idle"))
                equipment_list.append({
                    "id": zone.get("zone_id"),
                    "name": zone.get("zone_name"),
                    "type": "hvac_zone",
                    "category": "HVAC",
                    "status": status,
                    "health": health,
                    "location": f"Floor {zone.get('floor', 'N/A')}",
                    "building_id": site_code,
                    "building_name": building.name,
                    "site_id": building_id,
                    "details": {
                        "current_temp": zone.get("current_temp"),
                        "setpoint": zone.get("setpoint"),
                        "fcu_id": zone.get("fcu_id"),
                        "ahu_id": zone.get("ahu_id"),
                    },
                    "controllable": True,
                })

    # 2. Generators
    gen_file = building_path / "generators.json"
    if gen_file.exists():
        with open(gen_file) as f:
            gen_data = json.load(f)

            # Diesel tanks
            for tank in gen_data.get("diesel_tanks", []):
                level_pct = tank.get("current_level_pct", 0)
                status = "normal" if level_pct > 25 else ("warning" if level_pct > 10 else "critical")
                health = min(100, level_pct + 20)
                equipment_list.append({
                    "id": tank.get("tank_id"),
                    "name": tank.get("name"),
                    "type": "diesel_tank",
                    "category": "Generator Plant",
                    "status": status,
                    "health": health,
                    "location": tank.get("location", ""),
                    "building_id": site_code,
                    "building_name": building.name,
                    "site_id": building_id,
                    "details": {
                        "capacity_liters": tank.get("capacity_liters"),
                        "current_level_pct": level_pct,
                    },
                    "controllable": False,
                })

            # Generator groups
            for group in gen_data.get("groups", []):
                status, health = get_status_health("online" if group.get("generators_running", 0) > 0 else "standby")
                equipment_list.append({
                    "id": group.get("group_id"),
                    "name": group.get("name"),
                    "type": "generator_group",
                    "category": "Generator Plant",
                    "status": status,
                    "health": health,
                    "location": group.get("location", ""),
                    "building_id": site_code,
                    "building_name": building.name,
                    "site_id": building_id,
                    "details": {
                        "generators_running": group.get("generators_running"),
                        "total_load_kw": group.get("total_load_kw"),
                        "ats_position": group.get("ats_position"),
                    },
                    "controllable": False,
                })

            # Generators
            for gen in gen_data.get("generators", []):
                status, health = get_status_health(gen.get("status", "standby"))
                equipment_list.append({
                    "id": gen.get("generator_id"),
                    "name": gen.get("name"),
                    "type": "generator",
                    "category": "Generator Plant",
                    "status": status,
                    "health": health,
                    "location": gen.get("location", ""),
                    "building_id": site_code,
                    "building_name": building.name,
                    "site_id": building_id,
                    "details": {
                        "rated_power_kw": gen.get("rated_power_kw"),
                        "engine_running": gen.get("engine_running"),
                        "on_load": gen.get("on_load"),
                        "output_power_kw": gen.get("output_power_kw"),
                    },
                    "controllable": True,
                })

    # 3. Energy Centre
    ec_file = building_path / "energy_centre.json"
    if ec_file.exists():
        with open(ec_file) as f:
            ec_data = json.load(f)

            # MV Incomers
            for incomer in ec_data.get("mv_incomers", []):
                status, health = get_status_health("online" if incomer.get("healthy") else "fault")
                equipment_list.append({
                    "id": incomer.get("incomer_id"),
                    "name": incomer.get("name"),
                    "type": "mv_incomer",
                    "category": "Energy Centre",
                    "status": status,
                    "health": health,
                    "location": incomer.get("location", ""),
                    "building_id": site_code,
                    "building_name": building.name,
                    "site_id": building_id,
                    "details": {
                        "voltage_kv": incomer.get("voltage_kv"),
                        "power_kw": incomer.get("power_kw"),
                        "breaker_state": incomer.get("breaker_state"),
                    },
                    "controllable": False,
                })

            # Transformers
            for tx in ec_data.get("transformers", []):
                status, health = get_status_health("online" if tx.get("healthy") else "fault")
                equipment_list.append({
                    "id": tx.get("transformer_id"),
                    "name": tx.get("name"),
                    "type": "transformer",
                    "category": "Energy Centre",
                    "status": status,
                    "health": health,
                    "location": tx.get("location", ""),
                    "building_id": site_code,
                    "building_name": building.name,
                    "site_id": building_id,
                    "details": {
                        "rated_power_kva": tx.get("rated_power_kva"),
                        "load_percent": tx.get("load_percent"),
                        "oil_temp_c": tx.get("oil_temp_c"),
                    },
                    "controllable": False,
                })

            # LV Switchboards
            for sb in ec_data.get("lv_switchboards", []):
                status, health = get_status_health("online" if sb.get("healthy") else "fault")
                equipment_list.append({
                    "id": sb.get("switchboard_id"),
                    "name": sb.get("name"),
                    "type": "lv_switchboard",
                    "category": "Energy Centre",
                    "status": status,
                    "health": health,
                    "location": sb.get("location", ""),
                    "building_id": site_code,
                    "building_name": building.name,
                    "site_id": building_id,
                    "details": {
                        "total_load_kw": sb.get("total_load_kw"),
                        "bus_voltage_v": sb.get("bus_voltage_v"),
                    },
                    "controllable": False,
                })

            # ATS Units
            for ats in ec_data.get("ats_units", []):
                # ATS health: check if both interlocks are OK and at least one power source is available
                is_healthy = (
                    ats.get("mechanical_interlock_ok", False) and
                    ats.get("electrical_interlock_ok", False) and
                    (ats.get("mains_available", False) or ats.get("generator_available", False))
                )
                status, health = get_status_health("online" if is_healthy else "fault")
                equipment_list.append({
                    "id": ats.get("ats_id"),
                    "name": ats.get("name"),
                    "type": "ats",
                    "category": "Energy Centre",
                    "status": status,
                    "health": health,
                    "location": ats.get("location", ""),
                    "building_id": site_code,
                    "building_name": building.name,
                    "site_id": building_id,
                    "details": {
                        "position": ats.get("position"),
                        "mode": ats.get("mode"),
                    },
                    "controllable": True,
                })

            # Power Meters
            for meter in ec_data.get("power_meters", []):
                equipment_list.append({
                    "id": meter.get("meter_id"),
                    "name": meter.get("name"),
                    "type": "power_meter",
                    "category": "Energy Centre",
                    "status": "normal",
                    "health": 95,
                    "location": meter.get("location", ""),
                    "building_id": site_code,
                    "building_name": building.name,
                    "site_id": building_id,
                    "details": {
                        "power_kw": meter.get("power_kw"),
                        "energy_kwh": meter.get("energy_kwh_total"),
                    },
                    "controllable": False,
                })

            # PFC Banks
            for pfc in ec_data.get("pfc_banks", []):
                status, health = get_status_health("online" if pfc.get("healthy") else "fault")
                equipment_list.append({
                    "id": pfc.get("pfc_id"),
                    "name": pfc.get("name"),
                    "type": "pfc_bank",
                    "category": "Energy Centre",
                    "status": status,
                    "health": health,
                    "location": pfc.get("location", ""),
                    "building_id": site_code,
                    "building_name": building.name,
                    "site_id": building_id,
                    "details": {
                        "power_factor": pfc.get("power_factor"),
                        "stages_active": pfc.get("stages_active"),
                    },
                    "controllable": True,
                })

            # UPS Systems
            for ups in ec_data.get("ups_systems", []):
                status, health = get_status_health(ups.get("status", "online"))
                equipment_list.append({
                    "id": ups.get("ups_id"),
                    "name": ups.get("name"),
                    "type": "ups",
                    "category": "Energy Centre",
                    "status": status,
                    "health": health,
                    "location": ups.get("location", ""),
                    "building_id": site_code,
                    "building_name": building.name,
                    "site_id": building_id,
                    "details": {
                        "rated_power_kva": ups.get("rated_power_kva"),
                        "load_percent": ups.get("load_percent"),
                        "battery_pct": ups.get("battery_pct"),
                        "runtime_minutes": ups.get("runtime_minutes"),
                    },
                    "controllable": False,
                })

            # Feeders
            for feeder in ec_data.get("feeders", []):
                status, health = get_status_health("online" if feeder.get("breaker_state") == "closed" else "offline")
                equipment_list.append({
                    "id": feeder.get("feeder_id"),
                    "name": feeder.get("name"),
                    "type": "feeder",
                    "category": "Energy Centre",
                    "status": status,
                    "health": health,
                    "location": feeder.get("location", ""),
                    "building_id": site_code,
                    "building_name": building.name,
                    "site_id": building_id,
                    "details": {
                        "rated_current_a": feeder.get("rated_current_a"),
                        "current_a": feeder.get("current_a"),
                        "destination": feeder.get("destination"),
                    },
                    "controllable": True,
                })

    # 4. DALI Controllers
    # Map building_id to site_id for DALI data
    BUILDING_TO_SITE = {"sandton": "site-002"}
    site_id = BUILDING_TO_SITE.get(building_id, building_id)

    dali_file = Path(__file__).parent.parent / "data" / "dali_mock_data.json"
    if dali_file.exists():
        with open(dali_file) as f:
            dali_data = json.load(f)
            # Check if site matches (using mapped site_id)
            if dali_data.get("site_id") == site_id:
                for controller in dali_data.get("controllers", []):
                    status, health = get_status_health(controller.get("status", "online"))
                    equipment_list.append({
                        "id": controller.get("controller_id"),
                        "name": controller.get("name"),
                        "type": "dali_controller",
                        "category": "Lighting",
                        "status": status,
                        "health": health,
                        "location": controller.get("location", ""),
                        "building_id": site_code,
                        "building_name": building.name,
                        "site_id": building_id,
                        "details": {
                            "ip_address": controller.get("ip_address"),
                            "channels": controller.get("channels"),
                            "firmware": controller.get("firmware_version"),
                        },
                        "controllable": True,
                    })

    # 5. Equipment from building equipment directory (Niagara discovery)
    equipment_dir = building_path / "equipment"
    if equipment_dir.exists():
        existing_ids = {eq["id"] for eq in equipment_list}  # Avoid duplicates
        for eq_file in equipment_dir.glob("*.json"):
            try:
                with open(eq_file) as f:
                    eq = json.load(f)

                eq_id = eq.get("id", eq.get("code", ""))
                if eq_id in existing_ids:
                    continue  # Skip duplicates

                eq_type = eq.get("equipment_type", eq.get("device_type", "unknown"))
                type_to_category = {
                    "ahu": "HVAC", "fcu": "HVAC", "vav": "HVAC", "chiller": "HVAC",
                    "cooling_tower": "HVAC", "pump": "HVAC", "boiler": "HVAC",
                    "hvac": "HVAC", "split_unit": "HVAC",
                    "generator": "Generator Plant",
                    "ups": "Energy Centre", "transformer": "Energy Centre",
                    "ats": "Energy Centre", "power_meter": "Energy Centre", "meter": "Energy Centre",
                    "dali_controller": "Lighting", "dali_zone": "Lighting", "luminaire": "Lighting",
                    "lighting": "Lighting",
                    "sensor": "Sensors", "zone": "Building Systems",
                }
                category = type_to_category.get(eq_type.lower(), "Other")
                status, health = get_status_health(eq.get("status", "normal"))

                equipment_list.append({
                    "id": eq_id,
                    "name": eq.get("name", eq_id),
                    "type": eq_type,
                    "category": category,
                    "status": status,
                    "health": health,
                    "location": eq.get("location", ""),
                    "building_id": site_code,
                    "building_name": building.name,
                    "site_id": building_id,
                    "details": {
                        "manufacturer": eq.get("manufacturer"),
                        "model": eq.get("model"),
                        "metadata": eq.get("metadata", {}),
                    },
                    "controllable": _is_device_controllable(eq_id, eq.get("points", {})),
                })
                existing_ids.add(eq_id)
            except Exception as e:
                logger.warning(f"Failed to load equipment from {eq_file}: {e}")

    # 6. Legacy Equipment from equipment.json
    equipment_file = Path(__file__).parent.parent / "data" / "equipment.json"
    if equipment_file.exists():
        with open(equipment_file) as f:
            legacy_equipment = json.load(f)
            for eq in legacy_equipment:
                # Match by site_id
                if eq.get("site_id") == site_id:
                    eq_type = eq.get("type", "unknown")
                    # Determine category based on type
                    type_to_category = {
                        "sensor": "Sensors",
                        "daylight_sensor": "Sensors",
                        "occupancy_sensor": "Sensors",
                        "ahu": "HVAC",
                        "split_unit": "HVAC",
                        "fcu": "HVAC",
                        "chiller": "HVAC",
                        "cooling_tower": "HVAC",
                        "vav": "HVAC",
                        "hvac_zone": "HVAC",
                        "ups": "Energy Centre",
                        "transformer": "Energy Centre",
                        "mv_incomer": "Energy Centre",
                        "lv_switchboard": "Energy Centre",
                        "ats": "Energy Centre",
                        "power_meter": "Energy Centre",
                        "pfc_bank": "Energy Centre",
                        "feeder": "Energy Centre",
                        "generator": "Generator Plant",
                        "diesel_tank": "Generator Plant",
                        "generator_group": "Generator Plant",
                        "dali_controller": "Lighting",
                        "luminaire": "Lighting",
                        "luminaire_group": "Lighting",
                        "fire_panel": "Fire & Safety",
                        "bms_controller": "Building Systems",
                        "bms_scada": "Building Systems",
                        "water_heater": "Building Systems",
                        "lift-passenger": "Lifts",
                    }
                    category = type_to_category.get(eq_type, "Other")
                    status, health = get_status_health(eq.get("status", "normal"))

                    equipment_list.append({
                        "id": eq.get("id"),
                        "name": eq.get("name"),
                        "type": eq_type,
                        "category": category,
                        "status": status,
                        "health": health,
                        "location": eq.get("location", ""),
                        "building_id": site_code,
                        "building_name": building.name,
                        "site_id": building_id,
                        "details": {
                            "manufacturer": eq.get("manufacturer"),
                            "model": eq.get("model"),
                        },
                        "controllable": _is_device_controllable(
                            eq.get("id", ""),
                            eq.get("points", {})
                        ),
                    })

    # Summary by category
    categories = {}
    for eq in equipment_list:
        cat = eq["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "normal": 0, "warning": 0, "critical": 0}
        categories[cat]["total"] += 1
        if eq["status"] in ["normal"]:
            categories[cat]["normal"] += 1
        elif eq["status"] in ["warning"]:
            categories[cat]["warning"] += 1
        elif eq["status"] in ["critical"]:
            categories[cat]["critical"] += 1

    return {
        "building_id": building_id,
        "building_name": building.name,
        "total_equipment": len(equipment_list),
        "categories": categories,
        "equipment": equipment_list,
        "source": "json",
    }
