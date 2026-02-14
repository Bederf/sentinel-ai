"""
DALI Lighting API
=================
REST endpoints for Tridonic Scenecom DALI-2 lighting system.
"""

import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional

from app.api.dependencies.module_access import require_active_module
from app.models.module_registry import ModuleType
from app.services.dali_service import get_dali_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/dali",
    tags=["DALI Lighting"],
    dependencies=[
        Depends(
            require_active_module(
                ModuleType.LIGHTING,
                site_keys=("site_id", "site"),
                default_site_id="site-002",
            )
        )
    ],
)


# === Controllers ===

@router.get("/controllers")
async def list_controllers(site_id: Optional[str] = None) -> List[dict]:
    """List all DALI controllers."""
    service = get_dali_service()
    controllers = service.get_controllers(site_id=site_id)
    return [c.to_dict() for c in controllers]


@router.get("/controllers/{controller_id}")
async def get_controller(controller_id: str) -> dict:
    """Get specific controller details."""
    service = get_dali_service()
    controller = service.get_controller(controller_id)
    if not controller:
        raise HTTPException(status_code=404, detail=f"Controller {controller_id} not found")
    return controller.to_dict()


# === Sensors ===

@router.get("/sensors")
async def list_sensors(
    zone_id: Optional[str] = None,
    controller_id: Optional[str] = None,
    limit: int = Query(100, le=1000)
) -> List[dict]:
    """List sensors with optional filters, enriched with zone and desk information."""
    from app.utils.sensor_formatter import format_sensor_with_zone_and_desks
    
    service = get_dali_service()
    sensors = service.get_sensors(zone_id=zone_id, controller_id=controller_id)
    
    # Enrich sensors with zone and desk information from Equipment table
    enriched = []
    for sensor in sensors[:limit]:
        sensor_dict = sensor.to_dict()
        enriched_dict = await format_sensor_with_zone_and_desks(sensor_dict)
        enriched.append(enriched_dict)
    
    return enriched


@router.get("/sensors/{sensor_id}")
async def get_sensor(sensor_id: str) -> dict:
    """Get specific sensor details."""
    service = get_dali_service()
    sensor = service.get_sensor(sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail=f"Sensor {sensor_id} not found")
    return sensor.to_dict()


@router.get("/sensors/by-desk/{desk_id}")
async def get_sensor_by_desk(desk_id: str) -> dict:
    """Get sensor for a specific desk (for complaint handling)."""
    service = get_dali_service()
    sensor = service.get_sensor_by_desk(desk_id)
    if not sensor:
        raise HTTPException(status_code=404, detail=f"No sensor found for desk {desk_id}")
    return sensor.to_dict()


# === Luminaires ===

@router.get("/luminaires")
async def list_luminaires(
    zone_id: Optional[str] = None,
    faulty_only: bool = False,
    limit: int = Query(100, le=1000)
) -> List[dict]:
    """List luminaires with optional filters."""
    service = get_dali_service()
    luminaires = service.get_luminaires(zone_id=zone_id, faulty_only=faulty_only)
    return [l.to_dict() for l in luminaires[:limit]]


@router.get("/luminaires/faulty")
async def list_faulty_luminaires() -> List[dict]:
    """List all faulty luminaires (for maintenance)."""
    service = get_dali_service()
    luminaires = service.get_luminaires(faulty_only=True)
    return [l.to_dict() for l in luminaires]


@router.get("/luminaires/{luminaire_id}")
async def get_luminaire(luminaire_id: str) -> dict:
    """Get specific luminaire details."""
    service = get_dali_service()
    luminaire = service.get_luminaire(luminaire_id)
    if not luminaire:
        raise HTTPException(status_code=404, detail=f"Luminaire {luminaire_id} not found")
    return luminaire.to_dict()


# === Zone Aggregations ===

@router.get("/zones")
async def list_zones() -> List[dict]:
    """List all lighting zones."""
    service = get_dali_service()
    return service.get_all_zones()


@router.get("/zones/{zone_id}/occupancy")
async def get_zone_occupancy(zone_id: str) -> dict:
    """Get occupancy summary for a zone."""
    service = get_dali_service()
    occupancy = service.get_zone_occupancy(zone_id)
    if not occupancy:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")
    return occupancy.to_dict()


@router.get("/zones/{zone_id}/lighting")
async def get_zone_lighting(zone_id: str) -> dict:
    """Get lighting summary for a zone."""
    service = get_dali_service()
    lighting = service.get_zone_lighting(zone_id)
    if not lighting:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")
    return lighting.to_dict()


@router.get("/zones/{zone_id}/summary")
async def get_zone_summary(zone_id: str) -> dict:
    """Get combined occupancy + lighting for a zone."""
    service = get_dali_service()
    summary = service.get_zone_summary(zone_id)
    if not summary["occupancy"] and not summary["lighting"]:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")
    return summary


# === Floor/Building Aggregations ===

@router.get("/floors/{floor}/summary")
async def get_floor_summary(floor: str) -> dict:
    """Get occupancy summary for a floor."""
    service = get_dali_service()
    summary = service.get_floor_summary(floor)
    return summary.to_dict()


@router.get("/building/occupancy")
async def get_building_occupancy() -> dict:
    """Get real-time occupancy overview for entire building."""
    service = get_dali_service()
    return service.get_building_occupancy()


# === Statistics ===

@router.get("/stats")
async def get_dali_stats() -> dict:
    """Get DALI system statistics (flat structure for frontend DALIStats)."""
    service = get_dali_service()
    controllers = service.get_controllers()
    sensors = service.get_sensors()
    luminaires = service.get_luminaires()

    occupied = sum(1 for s in sensors if s.occupancy)
    faulty_lum = sum(1 for l in luminaires if l.fault_status)
    faulty_sensors = sum(1 for s in sensors if s.sensor_type == "switch" or
                         (hasattr(s, 'last_updated') and s.last_updated is None))
    total_power = sum(l.power_consumption for l in luminaires)

    # Count energy waste zones
    energy_waste_count = 0
    for zone in service.get_all_zones():
        zone_id = zone["zone_id"]
        occ = service.get_zone_occupancy(zone_id)
        lighting = service.get_zone_lighting(zone_id)
        if occ and lighting and occ.occupancy_percent < 20 and lighting.active_luminaires > 0:
            energy_waste_count += 1

    # Estimate energy today (power * assumed 8 business hours)
    energy_today_kwh = round(total_power / 1000 * 8, 1)

    return {
        "total_controllers": len(controllers),
        "online_controllers": sum(1 for c in controllers if c.status == "online"),
        "total_sensors": len(sensors),
        "online_sensors": len(sensors) - faulty_sensors,
        "total_luminaires": len(luminaires),
        "faulty_luminaires": faulty_lum,
        "current_occupancy_percent": round(occupied / len(sensors) * 100, 1) if sensors else 0,
        "current_power_watts": round(total_power, 1),
        "energy_today_kwh": energy_today_kwh,
        "energy_waste_alerts": energy_waste_count,
        "last_sync": datetime.now().isoformat(),
    }
