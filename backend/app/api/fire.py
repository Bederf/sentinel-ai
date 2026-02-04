"""Fire & Life Safety API endpoints.

Provides read-only monitoring of fire alarm panels, smoke dampers,
stairwell pressurization, and cause-effect matrix. Plus demo simulation.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import logging

from app.services.fire_system_service import get_fire_system_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fire", tags=["fire"])


@router.get("/status")
async def get_fire_status():
    """Get overall fire system status.

    Returns panel status, active alarm count, zone count,
    damper health, pressurization status, and battery voltage.
    """
    svc = get_fire_system_service()
    status = svc.get_system_status()
    return {
        "panel_status": status.panel_status.value,
        "active_alarm_count": len(status.active_alarms),
        "active_alarms": [a.model_dump(mode="json") for a in status.active_alarms],
        "zone_count": status.zone_count,
        "damper_count": status.damper_count,
        "all_dampers_healthy": status.all_dampers_healthy,
        "pressurization_ok": status.pressurization_ok,
        "battery_voltage": status.battery_voltage,
        "last_test_date": status.last_test_date,
    }


@router.get("/alarms")
async def get_fire_alarms(zone_id: Optional[str] = Query(None, description="Filter by zone ID")):
    """Get active fire alarms with optional zone filter."""
    svc = get_fire_system_service()
    alarms = svc.get_active_alarms()
    if zone_id:
        alarms = [a for a in alarms if a.zone_id == zone_id]
    return {
        "alarms": [a.model_dump(mode="json") for a in alarms],
        "count": len(alarms),
    }


@router.get("/zones")
async def get_fire_zones():
    """Get all fire zones with detector counts and status."""
    svc = get_fire_system_service()
    zones = svc.get_zones()
    active_alarms = svc.get_active_alarms()

    # Annotate zones with alarm status
    alarm_zones = {a.zone_id for a in active_alarms}
    zone_list = []
    for z in zones:
        zone_dict = z.model_dump()
        zone_dict["zone_type"] = z.zone_type.value
        zone_dict["has_active_alarm"] = z.zone_id in alarm_zones
        zone_dict["total_detectors"] = (
            z.smoke_detectors + z.heat_detectors + z.beam_detectors + z.manual_call_points
        )
        zone_list.append(zone_dict)

    return {
        "zones": zone_list,
        "count": len(zone_list),
    }


@router.get("/zones/{zone_id}")
async def get_fire_zone_detail(zone_id: str):
    """Get single zone detail with active alarms."""
    svc = get_fire_system_service()
    result = svc.get_zone_status(zone_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")
    return result


@router.get("/dampers")
async def get_damper_status():
    """Get all smoke damper positions and health."""
    svc = get_fire_system_service()
    dampers = svc.get_damper_status()
    return {
        "dampers": [d.model_dump(mode="json") for d in dampers],
        "count": len(dampers),
        "faults": sum(1 for d in dampers if d.status.value == "fault"),
    }


@router.get("/pressurization")
async def get_pressurization_status():
    """Get stairwell pressurization status."""
    svc = get_fire_system_service()
    press = svc.get_pressurization_status()
    return {
        "stairwells": [p.model_dump(mode="json") for p in press],
        "count": len(press),
        "all_ok": all(p.fan_status.value != "fault" for p in press),
    }


@router.get("/cause-effect")
async def get_cause_effect_matrix():
    """Get cause & effect matrix for fire coordination."""
    svc = get_fire_system_service()
    matrix = svc.get_cause_effect_matrix()
    return {
        "entries": [
            {
                "trigger_zone": e.trigger_zone,
                "trigger_type": e.trigger_type,
                "effects": [
                    {
                        "target_type": eff.target_type.value,
                        "target_id": eff.target_id,
                        "action": eff.action,
                        "delay_seconds": eff.delay_seconds,
                        "priority": eff.priority,
                    }
                    for eff in e.effects
                ],
            }
            for e in matrix
        ],
        "count": len(matrix),
    }


@router.get("/health")
async def get_fire_health():
    """Get fire system health (battery, comms, faults)."""
    svc = get_fire_system_service()
    health = svc.get_system_health()
    return {
        "panel_comms": health.panel_comms,
        "battery_status": health.battery_status,
        "detector_faults": health.detector_faults,
        "damper_faults": health.damper_faults,
        "overall_health": health.overall_health.value,
    }


@router.post("/simulate-alarm")
async def simulate_alarm(
    zone_id: str = Query(..., description="Zone ID to simulate alarm in"),
    alarm_type: str = Query("smoke", description="Alarm type: smoke, heat, manual, flow, fault"),
):
    """Simulate a fire alarm event for demo purposes.

    Creates a simulated alarm and returns the cause-effect
    actions that would be triggered.
    """
    if alarm_type not in ("smoke", "heat", "manual", "flow", "fault"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid alarm type: {alarm_type}. Must be smoke, heat, manual, flow, or fault",
        )

    svc = get_fire_system_service()
    result = svc.simulate_alarm(zone_id, alarm_type)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
