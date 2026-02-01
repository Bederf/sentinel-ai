"""
Simulation API endpoints for BMS Intelligence
Provides control and access to simulated equipment data
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from app.services.bms_simulation_service import create_simulation_service
from app.models.device import Device, DeviceValue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulation", tags=["simulation"])

# Global simulation service instance
simulation_service = create_simulation_service()

@router.on_event("startup")
async def startup_event():
    """Start the simulation service on API startup"""
    try:
        await simulation_service.start_simulation()
        logger.info("BMS Simulation service started successfully")
    except Exception as e:
        logger.error(f"Failed to start simulation service: {e}")

@router.on_event("shutdown")
async def shutdown_event():
    """Stop the simulation service on API shutdown"""
    try:
        await simulation_service.stop_simulation()
        logger.info("BMS Simulation service stopped")
    except Exception as e:
        logger.error(f"Error stopping simulation service: {e}")

@router.get("/status")
async def get_simulation_status():
    """Get current simulation status"""
    return {
        "is_running": simulation_service.is_running,
        "simulation_speed": simulation_service.simulation_speed,
        "total_equipment": len(simulation_service.equipment),
        "last_update": datetime.now().isoformat()
    }

@router.get("/equipment")
async def get_equipment(
    equipment_type: Optional[str] = Query(None, description="Filter by equipment type"),
    building: Optional[str] = Query(None, description="Filter by building"),
    health_threshold: Optional[float] = Query(None, description="Filter by health score threshold"),
    include_faults: bool = Query(True, description="Include fault codes"),
    limit: int = Query(100, description="Maximum number of results")
):
    """Get simulated equipment data"""
    try:
        equipment_data = simulation_service.get_real_time_data()

        if equipment_type:
            equipment_data["equipment"] = [
                eq for eq in equipment_data["equipment"]
                if eq.get("type") == equipment_type
            ]

        if building:
            equipment_data["equipment"] = [
                eq for eq in equipment_data["equipment"]
                if building.lower() in eq.get("location", "").lower()
            ]

        if health_threshold is not None:
            equipment_data["equipment"] = [
                eq for eq in equipment_data["equipment"]
                if eq.get("health_score", 0) >= health_threshold
            ]

        # Limit results
        equipment_data["equipment"] = equipment_data["equipment"][:limit]

        # Optionally remove faults
        if not include_faults:
            for eq in equipment_data["equipment"]:
                eq["fault_codes"] = []

        return equipment_data
    except Exception as e:
        logger.error(f"Error getting equipment data: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting equipment data: {e}")

@router.get("/equipment/{equipment_id}")
async def get_equipment_by_id(equipment_id: str):
    """Get specific equipment by ID"""
    try:
        equipment_data = simulation_service.get_real_time_data(equipment_id)

        if "error" in equipment_data:
            raise HTTPException(status_code=404, detail=equipment_data["error"])

        return equipment_data
    except Exception as e:
        logger.error(f"Error getting equipment {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting equipment: {e}")

@router.post("/fault/inject")
async def inject_fault(
    equipment_id: str,
    fault_code: str,
    description: Optional[str] = None
):
    """Manually inject a fault for testing"""
    try:
        simulation_service.inject_fault(equipment_id, fault_code)

        return {
            "success": True,
            "message": f"Fault {fault_code} injected into {equipment_id}",
            "description": description,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error injecting fault: {e}")
        raise HTTPException(status_code=500, detail=f"Error injecting fault: {e}")

@router.delete("/fault/clear/{equipment_id}")
async def clear_faults(equipment_id: str):
    """Clear all faults from equipment"""
    try:
        simulation_service.clear_faults(equipment_id)

        return {
            "success": True,
            "message": f"Faults cleared from {equipment_id}",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error clearing faults: {e}")
        raise HTTPException(status_code=500, detail=f"Error clearing faults: {e}")

@router.post("/control/speed")
async def set_simulation_speed(speed: float = Query(..., description="Simulation speed multiplier", ge=0.1, le=10.0)):
    """Set simulation speed (0.1 = 10x slower, 10.0 = 10x faster)"""
    try:
        simulation_service.simulation_speed = speed

        return {
            "success": True,
            "message": f"Simulation speed set to {speed}x",
            "current_speed": speed,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error setting simulation speed: {e}")
        raise HTTPException(status_code=500, detail=f"Error setting simulation speed: {e}")

@router.get("/stats")
async def get_simulation_stats():
    """Get simulation statistics"""
    try:
        stats = simulation_service.get_equipment_summary()
        return stats
    except Exception as e:
        logger.error(f"Error getting simulation stats: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting simulation stats: {e}")

@router.post("/scenario/{scenario_name}")
async def run_scenario(
    scenario_name: str,
    duration_minutes: int = Query(60, description="Duration in minutes", ge=1, le=1440)
):
    """Run a predefined simulation scenario"""
    scenarios = {
        "summer_peak": "High ambient temperature, maximum cooling load",
        "winter_night": "Low ambient temperature, minimal occupancy",
        "fault_cascade": "Multiple equipment failures in sequence",
        "maintenance_mode": "Equipment offline for maintenance",
        "energy_saving": "Optimized for minimum energy consumption"
    }

    if scenario_name not in scenarios:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {scenario_name}")

    try:
        # Implementation would adjust simulation parameters based on scenario
        logger.info(f"Running scenario: {scenario_name} for {duration_minutes} minutes")

        return {
            "success": True,
            "scenario": scenario_name,
            "description": scenarios[scenario_name],
            "duration_minutes": duration_minutes,
            "message": f"Scenario {scenario_name} started",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error running scenario {scenario_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Error running scenario: {e}")

@router.get("/health")
async def get_system_health():
    """Get overall system health summary"""
    try:
        summary = simulation_service.get_equipment_summary()

        # Calculate additional health metrics
        total_equipment = summary["total_equipment"]
        equipment_with_faults = summary["fault_summary"]["equipment_with_faults"]
        avg_health = summary["health_stats"]["avg_health"]

        health_status = "healthy"
        if avg_health < 70:
            health_status = "degraded"
        elif equipment_with_faults > total_equipment * 0.1:  # >10% with faults
            health_status = "warning"

        return {
            "status": health_status,
            "summary": summary,
            "recommendations": [
                f"Average equipment health: {avg_health:.1f}%",
                f"{equipment_with_faults} equipment items have faults",
                f"{total_equipment - equipment_with_faults} equipment items operating normally"
            ],
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting system health: {e}")

@router.get("/alerts")
async def get_simulation_alerts():
    """Get active alerts from simulation"""
    try:
        active_alerts = simulation_service.get_active_alerts()
        alert_history = simulation_service.get_alert_history()

        return {
            "active_count": len(active_alerts),
            "total_history": len(alert_history),
            "active_alerts": active_alerts,
            "recent_history": alert_history[-20:] if alert_history else [],
            "by_severity": {
                "critical": len([a for a in active_alerts if a["severity"] == "critical"]),
                "warning": len([a for a in active_alerts if a["severity"] == "warning"]),
                "info": len([a for a in active_alerts if a["severity"] == "info"])
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting simulation alerts: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting simulation alerts: {e}")


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_simulation_alert(
    alert_id: str,
    acknowledged_by: str = Query("Facilities Manager", description="Name of person acknowledging")
):
    """Acknowledge a simulation alert"""
    try:
        success = simulation_service.acknowledge_alert(alert_id, acknowledged_by)
        if success:
            return {
                "success": True,
                "message": f"Alert {alert_id} acknowledged by {acknowledged_by}",
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error acknowledging alert: {e}")
        raise HTTPException(status_code=500, detail=f"Error acknowledging alert: {e}")


@router.post("/alerts/{alert_id}/clear")
async def clear_simulation_alert(alert_id: str):
    """Clear/resolve a simulation alert"""
    try:
        success = simulation_service.clear_alert(alert_id)
        if success:
            return {
                "success": True,
                "message": f"Alert {alert_id} cleared",
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing alert: {e}")
        raise HTTPException(status_code=500, detail=f"Error clearing alert: {e}")


@router.post("/maintenance/{equipment_id}")
async def perform_maintenance(equipment_id: str):
    """Perform maintenance on equipment - restores health and clears faults"""
    try:
        result = simulation_service.perform_maintenance(equipment_id)
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=404, detail=result["message"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error performing maintenance: {e}")
        raise HTTPException(status_code=500, detail=f"Error performing maintenance: {e}")


@router.get("/equipment/{equipment_id}/status")
async def get_equipment_status(equipment_id: str):
    """Get detailed status of specific equipment"""
    if equipment_id not in simulation_service.equipment:
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

    eq = simulation_service.equipment[equipment_id]

    # Get alerts for this equipment
    eq_alerts = [a for a in simulation_service.get_active_alerts() if a["equipment_id"] == equipment_id]

    return {
        "id": eq.id,
        "name": eq.name,
        "type": eq.type,
        "status": eq.status,
        "health_score": eq.health_score,
        "health_status": "healthy" if eq.health_score >= 70 else "warning" if eq.health_score >= 50 else "critical" if eq.health_score >= 20 else "failed",
        "fault_codes": eq.fault_codes,
        "temperature": eq.temperature,
        "power_consumption": eq.power_consumption,
        "runtime_hours": eq.runtime_hours,
        "last_maintenance": eq.last_maintenance.isoformat(),
        "days_since_maintenance": (datetime.now() - eq.last_maintenance).days,
        "sensor_readings": eq.sensor_readings,
        "active_alerts": eq_alerts,
        "timestamp": eq.timestamp.isoformat()
    }


@router.post("/scenario/degrade/{equipment_id}")
async def force_equipment_degradation(
    equipment_id: str,
    amount: float = Query(10.0, description="Amount to degrade health (0-50)", ge=0, le=50)
):
    """Force equipment health to degrade (for demo purposes)"""
    if equipment_id not in simulation_service.equipment:
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

    eq = simulation_service.equipment[equipment_id]
    old_health = eq.health_score
    eq.health_score = max(0, eq.health_score - amount)

    # Trigger status update
    simulation_service._update_equipment_status(eq, old_health)

    return {
        "success": True,
        "equipment_id": equipment_id,
        "old_health": old_health,
        "new_health": eq.health_score,
        "status": eq.status,
        "message": f"Degraded {eq.name} health by {amount}%"
    }


# =============================================================================
# Health Simulation (Supabase) Endpoints
# These endpoints control the health simulation that writes to Supabase
# and triggers Clawd health alerts
# =============================================================================

from app.services.health_simulation_service import health_simulation_service


@router.get("/health-sim/status")
async def get_health_simulation_status():
    """Get health simulation status (Supabase-based)."""
    return health_simulation_service.get_status()


@router.post("/health-sim/start")
async def start_health_simulation():
    """Start the health simulation that writes to Supabase."""
    await health_simulation_service.start()
    return {
        "success": True,
        "message": "Health simulation started",
        "status": health_simulation_service.get_status(),
    }


@router.post("/health-sim/stop")
async def stop_health_simulation():
    """Stop the health simulation."""
    await health_simulation_service.stop()
    return {
        "success": True,
        "message": "Health simulation stopped",
        "status": health_simulation_service.get_status(),
    }


@router.post("/health-sim/config")
async def configure_health_simulation(
    interval_seconds: Optional[int] = Query(None, description="Interval between cycles (60-3600)"),
    degradation_rate: Optional[float] = Query(None, description="Max health drop per cycle (1-20)"),
    fault_probability: Optional[float] = Query(None, description="Chance of sudden fault (0.01-0.1)"),
    target_equipment_per_cycle: Optional[int] = Query(None, description="Equipment to update per cycle (1-50)"),
):
    """Configure health simulation parameters."""
    config_updates = {}
    if interval_seconds is not None:
        config_updates["interval_seconds"] = max(60, min(3600, interval_seconds))
    if degradation_rate is not None:
        config_updates["degradation_rate"] = max(1, min(20, degradation_rate))
    if fault_probability is not None:
        config_updates["fault_probability"] = max(0.01, min(0.1, fault_probability))
    if target_equipment_per_cycle is not None:
        config_updates["target_equipment_per_cycle"] = max(1, min(50, target_equipment_per_cycle))

    if config_updates:
        health_simulation_service.set_config(**config_updates)

    return {
        "success": True,
        "updated": config_updates,
        "current_config": {
            "interval_seconds": health_simulation_service.config["interval_seconds"],
            "degradation_rate": health_simulation_service.config["degradation_rate"],
            "fault_probability": health_simulation_service.config["fault_probability"],
            "target_equipment_per_cycle": health_simulation_service.config["target_equipment_per_cycle"],
        },
    }


@router.post("/health-sim/fault/{equipment_id}")
async def trigger_equipment_fault(
    equipment_id: str,
    severity: str = Query("moderate", description="Fault severity: minor, moderate, major, critical"),
):
    """Trigger a fault on specific equipment (writes to Supabase)."""
    result = await health_simulation_service.trigger_fault(equipment_id, severity)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/health-sim/maintenance/{equipment_id}")
async def trigger_equipment_maintenance(equipment_id: str):
    """Trigger maintenance on specific equipment (restores health in Supabase)."""
    result = await health_simulation_service.trigger_maintenance(equipment_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# Export the router
__all__ = ['router', 'simulation_service', 'health_simulation_service']