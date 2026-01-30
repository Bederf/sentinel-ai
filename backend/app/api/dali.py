"""
DALI Lighting API
=================
REST endpoints for Tridonic Scenecom DALI-2 lighting system.
"""

import logging
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from app.services.dali_service import get_dali_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dali", tags=["DALI Lighting"])


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
    """List sensors with optional filters."""
    service = get_dali_service()
    sensors = service.get_sensors(zone_id=zone_id, controller_id=controller_id)
    return [s.to_dict() for s in sensors[:limit]]


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
    """Get DALI system statistics."""
    service = get_dali_service()
    controllers = service.get_controllers()
    sensors = service.get_sensors()
    luminaires = service.get_luminaires()

    occupied = sum(1 for s in sensors if s.occupancy)
    faulty_lum = sum(1 for l in luminaires if l.fault_status)
    total_power = sum(l.power_consumption for l in luminaires)

    return {
        "controllers": {
            "total": len(controllers),
            "online": sum(1 for c in controllers if c.status == "online"),
            "offline": sum(1 for c in controllers if c.status == "offline")
        },
        "sensors": {
            "total": len(sensors),
            "occupied": occupied,
            "occupancy_percent": round(occupied / len(sensors) * 100, 1) if sensors else 0
        },
        "luminaires": {
            "total": len(luminaires),
            "active": sum(1 for l in luminaires if l.current_level > 0),
            "faulty": faulty_lum,
            "total_power_kw": round(total_power / 1000, 2)
        }
    }
