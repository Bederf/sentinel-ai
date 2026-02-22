"""Generator API endpoints.

SCADA-style monitoring for generator sets with DeepSea DSE controllers.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from app.services.generator_service import get_generator_service

router = APIRouter(prefix="/generators", tags=["generators"])


@router.get("")
async def list_generators(
    site_id: Optional[str] = Query(None, description="Filter by site"),
    group_id: Optional[str] = Query(None, description="Filter by generator group"),
):
    """List all generators with optional filters."""
    service = get_generator_service()
    generators = service.get_generators(site_id=site_id, group_id=group_id)
    return {
        "generators": [g.to_dict() for g in generators],
        "total": len(generators),
    }


@router.get("/{generator_id}")
async def get_generator(generator_id: str):
    """Get single generator by ID."""
    service = get_generator_service()
    generator = service.get_generator(generator_id)
    if not generator:
        raise HTTPException(status_code=404, detail=f"Generator {generator_id} not found")
    return generator.to_dict()


@router.get("/{generator_id}/telemetry")
async def get_generator_telemetry(generator_id: str):
    """Get current telemetry for a generator (Modbus poll data)."""
    service = get_generator_service()
    telemetry = service.get_generator_telemetry(generator_id)
    if not telemetry:
        raise HTTPException(status_code=404, detail=f"Generator {generator_id} not found")
    return telemetry


@router.get("/{generator_id}/health")
async def get_generator_health(generator_id: str):
    """Get health assessment with predictive indicators."""
    service = get_generator_service()
    health = service.get_generator_health(generator_id)
    if not health:
        raise HTTPException(status_code=404, detail=f"Generator {generator_id} not found")
    return health.to_dict()


# === Generator Groups ===


@router.get("/groups/list")
async def list_groups(
    site_id: Optional[str] = Query(None, description="Filter by site"),
):
    """List all generator groups."""
    service = get_generator_service()
    groups = service.get_groups(site_id=site_id)
    return {
        "groups": [g.to_dict() for g in groups],
        "total": len(groups),
    }


@router.get("/groups/{group_id}")
async def get_group(group_id: str):
    """Get single generator group by ID."""
    service = get_generator_service()
    group = service.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail=f"Group {group_id} not found")
    return group.to_dict()


@router.get("/groups/{group_id}/status")
async def get_group_status(group_id: str):
    """Get comprehensive status for a generator group."""
    service = get_generator_service()
    status = service.get_group_status(group_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Group {group_id} not found")
    return status


@router.get("/groups/{group_id}/fuel")
async def get_group_fuel_status(group_id: str):
    """Get fuel status for a generator group."""
    service = get_generator_service()
    fuel_status = service.get_fuel_status(group_id)
    if not fuel_status:
        raise HTTPException(status_code=404, detail=f"Group {group_id} not found or no fuel tank")
    return fuel_status


# === Diesel Tanks ===


@router.get("/tanks/list")
async def list_tanks():
    """List all diesel tanks."""
    service = get_generator_service()
    tanks = service.get_tanks()
    return {
        "tanks": [t.to_dict() for t in tanks],
        "total": len(tanks),
    }


@router.get("/tanks/{tank_id}")
async def get_tank(tank_id: str):
    """Get single diesel tank by ID."""
    service = get_generator_service()
    tank = service.get_tank(tank_id)
    if not tank:
        raise HTTPException(status_code=404, detail=f"Tank {tank_id} not found")
    return tank.to_dict()


# === SCADA Overview ===


@router.get("/scada/{site_id}")
async def get_scada_overview(site_id: str):
    """Get SCADA-style overview for control room display."""
    service = get_generator_service()
    overview = service.get_scada_overview(site_id)
    return overview


@router.get("/health/{site_id}")
async def get_site_health_summary(site_id: str):
    """Get health summary for all generators at a site."""
    service = get_generator_service()
    summary = service.get_site_health_summary(site_id)
    return summary


# === Simulation (Demo) ===


@router.post("/simulate/{event}")
async def simulate_event(event: str):
    """Simulate state changes for demo purposes.

    Events:
    - load_shedding: Simulate Eskom outage, generators start
    - mains_restored: Simulate mains return, generators stop
    - normal: Normal standby variations
    """
    if event not in ("load_shedding", "mains_restored", "normal"):
        raise HTTPException(
            status_code=400, detail=f"Invalid event: {event}. Use: load_shedding, mains_restored, normal"
        )

    service = get_generator_service()
    service.simulate_state_change(event)
    return {"status": "ok", "event": event}
