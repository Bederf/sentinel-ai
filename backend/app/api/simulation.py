"""
Simulation API endpoints for BMS Intelligence

Unified simulation engine — powered by LifecycleOrchestrator.
BMSimulationService is deprecated; all endpoints now route through the orchestrator.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime
import logging
import random
import uuid

from app.services.lifecycle_orchestrator import get_lifecycle_orchestrator
from app.services.health_threshold_service import get_health_status
from app.services.simulation_store import get_simulation_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulation", tags=["simulation"])


def _get_orchestrator():
    """Get the singleton lifecycle orchestrator."""
    return get_lifecycle_orchestrator()


@router.on_event("startup")
async def startup_event():
    """Simulation ready — starts manually via POST /api/simulation/start."""
    logger.info("Unified Simulation ready (not auto-started). Use POST /api/simulation/start to begin.")


@router.on_event("shutdown")
async def shutdown_event():
    """Save checkpoint on shutdown — leave task status as 'running' for auto-resume."""
    try:
        orchestrator = _get_orchestrator()
        if orchestrator.running:
            # Save final checkpoint so we can resume on next startup
            await orchestrator.save_checkpoint()
            orchestrator.running = False
            if orchestrator._task and not orchestrator._task.done():
                orchestrator._task.cancel()
            logger.info(
                f"Simulation checkpoint saved on shutdown (day {orchestrator.days_simulated}). "
                "Will auto-resume on next startup."
            )
    except Exception as e:
        logger.error(f"Error saving simulation checkpoint on shutdown: {e}")


@router.get("/status")
async def get_simulation_status():
    """Get current simulation status."""
    orchestrator = _get_orchestrator()
    return {
        "is_running": orchestrator.running,
        "simulation_speed": orchestrator.speed_multiplier,
        "total_equipment": len(orchestrator._simulation_equipment),
        "days_simulated": orchestrator.days_simulated,
        "last_update": datetime.now().isoformat(),
    }


@router.get("/equipment")
async def get_equipment(
    equipment_type: Optional[str] = Query(None, description="Filter by equipment type"),
    health_threshold: Optional[float] = Query(None, description="Filter by health score threshold"),
    limit: int = Query(100, description="Maximum number of results"),
):
    """Get simulated equipment data from the unified engine."""
    try:
        orchestrator = _get_orchestrator()
        states = orchestrator._simulation_equipment

        equipment_list = []
        for code, state in states.items():
            entry = {
                "id": code,
                "code": code,
                "type": state.get("type", "unknown"),
                "health_score": round(state.get("health_score", 0), 1),
                "status": state.get("status", "unknown"),
                "is_running": state.get("is_running", False),
                "runtime_hours": state.get("runtime_hours", 0),
                "sensor_readings": state.get("sensor_readings", {}),
                "fault_codes": list(orchestrator.active_faults.get(code, {}).keys())
                if code in orchestrator.active_faults
                else [],
            }
            equipment_list.append(entry)

        # Apply filters
        if equipment_type:
            equipment_list = [eq for eq in equipment_list if eq["type"] == equipment_type]

        if health_threshold is not None:
            equipment_list = [eq for eq in equipment_list if eq["health_score"] >= health_threshold]

        equipment_list = equipment_list[:limit]

        return {
            "total": len(states),
            "returned": len(equipment_list),
            "equipment": equipment_list,
        }
    except Exception as e:
        logger.error(f"Error getting equipment data: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting equipment data: {e}")


@router.get("/equipment/{equipment_id}")
async def get_equipment_by_id(equipment_id: str):
    """Get specific equipment by code."""
    orchestrator = _get_orchestrator()
    state = orchestrator._simulation_equipment.get(equipment_id)

    if not state:
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

    return {
        "id": equipment_id,
        "code": equipment_id,
        "type": state.get("type", "unknown"),
        "health_score": round(state.get("health_score", 0), 1),
        "status": state.get("status", "unknown"),
        "health_status": get_health_status(state.get("health_score", 0)),
        "is_running": state.get("is_running", False),
        "runtime_hours": state.get("runtime_hours", 0),
        "sensor_readings": state.get("sensor_readings", {}),
        "has_fault": equipment_id in orchestrator.active_faults,
    }


@router.post("/fault/inject")
async def inject_fault(equipment_id: str, fault_code: str, description: Optional[str] = None):
    """Manually inject a fault for testing."""
    try:
        orchestrator = _get_orchestrator()
        result = orchestrator.inject_fault(equipment_id, fault_code)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "Unknown error"))
        result["description"] = description
        result["timestamp"] = datetime.now().isoformat()
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error injecting fault: {e}")
        raise HTTPException(status_code=500, detail=f"Error injecting fault: {e}")


@router.delete("/fault/clear/{equipment_id}")
async def clear_faults(equipment_id: str):
    """Clear all faults from equipment."""
    try:
        orchestrator = _get_orchestrator()
        orchestrator.clear_faults(equipment_id)
        return {
            "success": True,
            "message": f"Faults cleared from {equipment_id}",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error clearing faults: {e}")
        raise HTTPException(status_code=500, detail=f"Error clearing faults: {e}")


@router.post("/control/speed")
async def set_simulation_speed(speed: float = Query(..., description="Simulation speed multiplier", ge=0.1, le=10.0)):
    """Set simulation speed multiplier."""
    try:
        orchestrator = _get_orchestrator()
        orchestrator.speed_multiplier = speed
        return {
            "success": True,
            "message": f"Simulation speed set to {speed}x",
            "current_speed": speed,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error setting simulation speed: {e}")
        raise HTTPException(status_code=500, detail=f"Error setting simulation speed: {e}")


@router.post("/stop")
async def stop_simulation():
    """Stop the unified simulation."""
    try:
        orchestrator = _get_orchestrator()
        result = await orchestrator.stop()
        return {
            "success": True,
            "message": "Simulation stopped",
            "is_running": orchestrator.running,
            "summary": result,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error stopping simulation: {e}")
        raise HTTPException(status_code=500, detail=f"Error stopping simulation: {e}")


@router.post("/start")
async def start_simulation():
    """Start the unified simulation engine (LifecycleOrchestrator).

    Registers the task in the simulation store so checkpoints are saved
    and the simulation can auto-resume after server restart.
    """
    try:
        orchestrator = _get_orchestrator()

        # Register in simulation store for checkpoint persistence
        task_id = str(uuid.uuid4())
        store = get_simulation_store(orchestrator.building_id)
        store.update_task_progress(
            task_id,
            {
                "task_id": task_id,
                "site_id": orchestrator.building_id,
                "scenario": "sentinel_annual",
                "simulation_type": "lifecycle",
                "status": "running",
                "progress_pct": 0,
                "days_completed": 0,
                "duration_minutes": 3650.0,
                "created_at": datetime.now().isoformat(),
            },
        )
        orchestrator.task_id = task_id

        result = await orchestrator.start(scenario="sentinel_annual")
        return {
            "success": True,
            "message": "Unified simulation started",
            "is_running": orchestrator.running,
            "result": result,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error starting simulation: {e}")
        raise HTTPException(status_code=500, detail=f"Error starting simulation: {e}")


@router.get("/stats")
async def get_simulation_stats():
    """Get simulation statistics from the unified engine."""
    try:
        orchestrator = _get_orchestrator()
        return orchestrator.get_equipment_summary()
    except Exception as e:
        logger.error(f"Error getting simulation stats: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting simulation stats: {e}")


@router.post("/scenario/{scenario_name}")
async def run_scenario(
    scenario_name: str, duration_minutes: int = Query(60, description="Duration in minutes", ge=1, le=1440)
):
    """Run a predefined simulation scenario via the unified engine."""
    scenarios = {
        "summer_peak": "High ambient temperature, maximum cooling load",
        "winter_night": "Low ambient temperature, minimal occupancy",
        "fault_cascade": "Multiple equipment failures in sequence",
        "maintenance_mode": "Equipment offline for maintenance",
        "energy_saving": "Optimized for minimum energy consumption",
    }

    if scenario_name not in scenarios:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {scenario_name}")

    try:
        orchestrator = _get_orchestrator()
        result = await orchestrator.start(
            scenario=scenario_name,
            duration_minutes=float(duration_minutes),
        )
        return {
            "success": True,
            "scenario": scenario_name,
            "description": scenarios[scenario_name],
            "duration_minutes": duration_minutes,
            "result": result,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error running scenario {scenario_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Error running scenario: {e}")


@router.get("/health")
async def get_system_health():
    """Get overall system health summary from unified engine."""
    try:
        orchestrator = _get_orchestrator()
        summary = orchestrator.get_equipment_summary()

        total = summary.get("total", 0)
        faults = summary.get("faults", 0)
        avg_health = summary.get("health_stats", {}).get("avg", 0)

        health_status = "healthy"
        if avg_health < 70:
            health_status = "degraded"
        elif total > 0 and faults > total * 0.1:
            health_status = "warning"

        return {
            "status": health_status,
            "summary": summary,
            "recommendations": [
                f"Average equipment health: {avg_health:.1f}%",
                f"{faults} equipment items have faults",
                f"{total - faults} equipment items operating normally",
            ],
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting system health: {e}")


@router.get("/alerts")
async def get_simulation_alerts():
    """Get active alerts from unified simulation."""
    try:
        orchestrator = _get_orchestrator()
        active_alerts = orchestrator.get_active_alerts()
        alert_history = orchestrator.get_alert_history()

        return {
            "active_count": len(active_alerts),
            "total_history": len(alert_history),
            "active_alerts": active_alerts,
            "recent_history": alert_history[-20:] if alert_history else [],
            "by_severity": {
                "critical": len([a for a in active_alerts if a.get("severity") == "critical"]),
                "warning": len([a for a in active_alerts if a.get("severity") == "warning"]),
                "info": len([a for a in active_alerts if a.get("severity") == "info"]),
            },
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting simulation alerts: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting simulation alerts: {e}")


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_simulation_alert(
    alert_id: str, acknowledged_by: str = Query("Facilities Manager", description="Name of person acknowledging")
):
    """Acknowledge a simulation alert."""
    try:
        orchestrator = _get_orchestrator()
        success = orchestrator.acknowledge_alert(alert_id)
        if success:
            return {
                "success": True,
                "message": f"Alert {alert_id} acknowledged by {acknowledged_by}",
                "timestamp": datetime.now().isoformat(),
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
    """Clear/resolve a simulation alert."""
    try:
        orchestrator = _get_orchestrator()
        success = orchestrator.clear_alert(alert_id)
        if success:
            return {"success": True, "message": f"Alert {alert_id} cleared", "timestamp": datetime.now().isoformat()}
        else:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing alert: {e}")
        raise HTTPException(status_code=500, detail=f"Error clearing alert: {e}")


@router.post("/maintenance/{equipment_id}")
async def perform_maintenance(equipment_id: str):
    """Perform maintenance on equipment — restores health and clears faults."""
    try:
        orchestrator = _get_orchestrator()
        result = orchestrator.perform_maintenance(equipment_id)
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=404, detail=result.get("error", "Not found"))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error performing maintenance: {e}")
        raise HTTPException(status_code=500, detail=f"Error performing maintenance: {e}")


@router.get("/equipment/{equipment_id}/status")
async def get_equipment_status(equipment_id: str):
    """Get detailed status of specific equipment."""
    orchestrator = _get_orchestrator()
    state = orchestrator._simulation_equipment.get(equipment_id)

    if not state:
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

    eq_alerts = [a for a in orchestrator.get_active_alerts() if a.get("equipment_code") == equipment_id]

    return {
        "id": equipment_id,
        "code": equipment_id,
        "type": state.get("type", "unknown"),
        "status": state.get("status", "unknown"),
        "health_score": round(state.get("health_score", 0), 1),
        "health_status": get_health_status(state.get("health_score", 0)),
        "is_running": state.get("is_running", False),
        "runtime_hours": state.get("runtime_hours", 0),
        "sensor_readings": state.get("sensor_readings", {}),
        "active_alerts": eq_alerts,
        "has_fault": equipment_id in orchestrator.active_faults,
    }


@router.post("/scenario/degrade/{equipment_id}")
async def force_equipment_degradation(
    equipment_id: str, amount: float = Query(10.0, description="Amount to degrade health (0-50)", ge=0, le=50)
):
    """Force equipment health to degrade (for demo purposes)."""
    orchestrator = _get_orchestrator()
    if equipment_id not in orchestrator._equipment_health:
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

    old_health = orchestrator._equipment_health[equipment_id]
    new_health = max(0, old_health - amount)
    orchestrator._equipment_health[equipment_id] = new_health

    # Update snapshot
    if equipment_id in orchestrator._simulation_equipment:
        orchestrator._simulation_equipment[equipment_id]["health_score"] = new_health
        orchestrator._simulation_equipment[equipment_id]["status"] = (
            "online" if new_health >= 70 else ("degraded" if new_health >= 40 else "offline")
        )

    return {
        "success": True,
        "equipment_id": equipment_id,
        "old_health": round(old_health, 1),
        "new_health": round(new_health, 1),
        "status": "online" if new_health >= 70 else ("degraded" if new_health >= 40 else "offline"),
        "message": f"Degraded {equipment_id} health by {amount}%",
    }


# =============================================================================
# Health Simulation (Supabase) Endpoints
# These endpoints control the health simulation that writes to Supabase
# and triggers Sentry health alerts
# =============================================================================

from app.services.health_simulation_service import health_simulation_service  # noqa: E402


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


# =============================================================================
# Demo Flow Endpoints
# Trigger warnings and reset to healthy for demo presentations
# =============================================================================

from app.services.equipment_alert_service import get_equipment_alert_service  # noqa: E402
from app.services.prediction_generator import get_prediction_generator  # noqa: E402
from app.database.repositories.prediction_repository import PredictionRepository  # noqa: E402
from app.services.maintenance_recommender import get_maintenance_recommender  # noqa: E402
from app.services.module_registry_service import ModuleRegistryService  # noqa: E402
from app.models.module_registry import AIRecommendation, ModuleType, RecommendationType, RecommendationPriority  # noqa: E402


@router.post("/demo/trigger-warnings")
async def trigger_demo_warnings(
    site_code: str = Query(..., description="Site code to trigger warnings for"),
    count: int = Query(3, description="Number of equipment to set to warning state", ge=1, le=10),
):
    """
    Demo endpoint: Trigger warning states on random equipment.

    1. Selects N random equipment from the building
    2. Updates health_score to 65 and status to 'warning'
    3. Creates alerts in Supabase for each
    4. Sends Telegram notifications via Sentry
    5. Generates predictions for at-risk equipment
    6. Creates AI maintenance recommendations with suggested actions

    Args:
        site_code: Building code (default: site-002 for Sandton)
        count: Number of equipment to affect (1-10)

    Returns:
        Summary of triggered warnings including AI recommendations
    """
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()
    alert_service = get_equipment_alert_service()
    prediction_generator = get_prediction_generator()

    # Get building UUID from code
    building_resp = client.table("buildings").select("id, name, code").eq("code", site_code).execute()
    if not building_resp.data:
        raise HTTPException(status_code=404, detail=f"Building {site_code} not found")

    building = building_resp.data[0]
    building_id = building["id"]
    building_name = building["name"]

    logger.info(f"Demo: Triggering {count} warnings for {building_name} ({site_code})")

    # Get healthy equipment from building (health >= 70)
    equipment_resp = (
        client.table("equipment")
        .select("id, code, name, type, health_score")
        .eq("building_id", building_id)
        .gte("health_score", 70)
        .execute()
    )

    if not equipment_resp.data:
        raise HTTPException(
            status_code=400, detail=f"No healthy equipment found in {building_name} to trigger warnings"
        )

    # Select random subset
    available = equipment_resp.data
    selected_count = min(count, len(available))
    selected_equipment = random.sample(available, selected_count)

    results = {
        "building": building_name,
        "site_code": site_code,
        "equipment_affected": [],
        "alerts_created": 0,
        "telegram_notifications": 0,
        "predictions_generated": 0,
        "recommendations_generated": 0,
        "errors": [],
    }

    # Initialize AI recommendation services
    module_registry = ModuleRegistryService()
    recommender = get_maintenance_recommender(client)

    # Process each selected equipment
    for eq in selected_equipment:
        try:
            old_health = eq.get("health_score", 92)
            # Vary health scores for realistic demo (55-75% range)
            new_health = random.randint(55, 75)

            # Update health to warning state and status to 'warning'
            client.table("equipment").update(
                {
                    "health_score": new_health,
                    "status": "warning",
                    "updated_at": datetime.now().isoformat(),
                }
            ).eq("id", eq["id"]).execute()

            # Create alert
            alert_result = alert_service.create_alert_for_equipment(
                equipment_id=eq["id"],
                building_id=building_id,
                severity="warning",
                message=f"Health score dropped from {old_health}% to {new_health}%. Maintenance recommended.",
                alert_type="health_degradation",
                notify_telegram=True,
            )

            results["equipment_affected"].append(
                {
                    "name": eq["name"],
                    "code": eq.get("code", ""),
                    "type": eq.get("type", ""),
                    "old_health": old_health,
                    "new_health": new_health,
                }
            )

            if alert_result.get("alert"):
                results["alerts_created"] += 1
            if alert_result.get("telegram_sent"):
                results["telegram_notifications"] += 1

        except Exception as e:
            error_msg = f"Error processing {eq.get('name', eq['id'])}: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)

    # Generate predictions for at-risk equipment
    try:
        pred_result = await prediction_generator.generate_predictions_for_all_sites()
        results["predictions_generated"] = pred_result.get("generated", 0)
    except Exception as e:
        logger.error(f"Prediction generation failed: {e}")
        results["errors"].append(f"Prediction generation failed: {str(e)}")

    # Generate AI recommendations for affected equipment
    for eq_info in results["equipment_affected"]:
        try:
            # Find the equipment in our selected list
            eq = next((e for e in selected_equipment if e["name"] == eq_info["name"]), None)
            if not eq:
                continue

            # Generate maintenance recommendation using fallback (fast, no LLM)
            recommendation = recommender._generate_fallback_recommendation(
                equipment_id=eq.get("code", eq["id"]),
                equipment_type=eq.get("type", "unknown"),
                risk_level="high",  # Warning state = high risk
                predicted_failure="health_degradation",
            )

            # Create AIRecommendation for module registry
            ai_rec = AIRecommendation(
                recommendation_id=str(uuid.uuid4()),
                timestamp=datetime.now().isoformat(),
                source_module=ModuleType.HVAC,  # Default to HVAC module
                recommendation_type=RecommendationType.MAINTENANCE,
                priority=RecommendationPriority.HIGH,
                title=f"Maintenance Required: {eq['name']}",
                description=(
                    f"Health score dropped to {eq_info['new_health']}%. "
                    f"{'; '.join(recommendation.immediate_actions[:2])}"
                ),
                confidence=0.85,
                related_modules=[ModuleType.ENERGY] if "chiller" in eq.get("type", "").lower() else [],
                telemetry_context={
                    "equipment_id": eq.get("code", eq["id"]),
                    "equipment_type": eq.get("type", "unknown"),
                    "health_score": eq_info["new_health"],
                    "building_id": site_code,
                },
                suggested_action={
                    "type": "schedule_maintenance",
                    "priority": recommendation.priority,
                    "immediate_actions": recommendation.immediate_actions,
                    "scheduled_maintenance": recommendation.scheduled_maintenance,
                    "spare_parts": recommendation.spare_parts,
                    "estimated_downtime": recommendation.estimated_downtime,
                },
                auto_actionable=False,
                acknowledged=False,
                resolved=False,
            )

            # Add to module registry
            module_registry.add_recommendation(site_code, ai_rec)
            results["recommendations_generated"] += 1

        except Exception as e:
            logger.warning(f"Failed to generate recommendation for {eq_info['name']}: {e}")

    logger.info(
        f"Demo complete: {results['alerts_created']} alerts, "
        f"{results['telegram_notifications']} Telegram notifications, "
        f"{results['predictions_generated']} predictions, "
        f"{results['recommendations_generated']} AI recommendations"
    )

    return {
        "success": True,
        "message": f"Triggered {len(results['equipment_affected'])} warning states for {building_name}",
        "results": results,
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/demo/reset-to-healthy")
async def reset_demo_to_healthy(
    site_code: str = Query(..., description="Site code to reset to healthy state"),
):
    """
    Demo endpoint: Reset all equipment to healthy state.

    1. Updates all equipment health_score to 92 and status to 'normal'
    2. Resolves all active alerts for the building
    3. Resolves all active predictions for the building

    Args:
        site_code: Building code (default: site-002 for Sandton)

    Returns:
        Summary of reset operations
    """
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()
    alert_service = get_equipment_alert_service()
    prediction_repo = PredictionRepository()

    # Get building UUID from code
    building_resp = client.table("buildings").select("id, name, code").eq("code", site_code).execute()
    if not building_resp.data:
        raise HTTPException(status_code=404, detail=f"Building {site_code} not found")

    building = building_resp.data[0]
    building_id = building["id"]
    building_name = building["name"]

    logger.info(f"Demo: Resetting {building_name} ({site_code}) to healthy state")

    results = {
        "building": building_name,
        "site_code": site_code,
        "equipment_reset": 0,
        "alerts_resolved": 0,
        "predictions_resolved": 0,
        "recommendations_resolved": 0,
        "errors": [],
    }

    # Initialize module registry for recommendations
    module_registry = ModuleRegistryService()

    # Reset all equipment health to 92 and status to 'normal'
    try:
        equipment_resp = client.table("equipment").select("id").eq("building_id", building_id).execute()

        if equipment_resp.data:
            for eq in equipment_resp.data:
                client.table("equipment").update(
                    {
                        "health_score": 92,
                        "status": "normal",
                        "updated_at": datetime.now().isoformat(),
                    }
                ).eq("id", eq["id"]).execute()
                results["equipment_reset"] += 1

    except Exception as e:
        error_msg = f"Failed to reset equipment: {str(e)}"
        logger.error(error_msg)
        results["errors"].append(error_msg)

    # Resolve all active alerts for building
    try:
        resolved_alerts = alert_service.resolve_alerts_for_building(building_id)
        results["alerts_resolved"] = resolved_alerts
    except Exception as e:
        error_msg = f"Failed to resolve alerts: {str(e)}"
        logger.error(error_msg)
        results["errors"].append(error_msg)

    # Resolve all active predictions for building
    try:
        active_predictions = prediction_repo.get_active_by_building(building_id)
        for pred in active_predictions:
            prediction_repo.resolve(pred.get("code", pred.get("id")))
            results["predictions_resolved"] += 1
    except Exception as e:
        error_msg = f"Failed to resolve predictions: {str(e)}"
        logger.error(error_msg)
        results["errors"].append(error_msg)

    # Resolve all AI recommendations for site
    try:
        active_recs = module_registry.get_recommendations(site_id=site_code, include_resolved=False, limit=100)
        for rec in active_recs:
            module_registry.resolve_recommendation(site_code, rec.recommendation_id)
            results["recommendations_resolved"] += 1
    except Exception as e:
        error_msg = f"Failed to resolve recommendations: {str(e)}"
        logger.error(error_msg)
        results["errors"].append(error_msg)

    logger.info(
        f"Demo reset complete: {results['equipment_reset']} equipment, "
        f"{results['alerts_resolved']} alerts, "
        f"{results['predictions_resolved']} predictions, "
        f"{results['recommendations_resolved']} AI recommendations"
    )

    return {
        "success": True,
        "message": f"Reset {building_name} to healthy state",
        "results": results,
        "timestamp": datetime.now().isoformat(),
    }


# =============================================================================
# Background Scheduler Control
# Pause/resume prediction generation and other background jobs
# =============================================================================

from app.services.background_scheduler import scheduler_service  # noqa: E402


@router.get("/scheduler/status")
async def get_scheduler_status():
    """Get status of all background scheduler jobs."""
    jobs = []
    for job in scheduler_service.scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "paused": job.next_run_time is None,
            }
        )

    return {
        "running": scheduler_service.scheduler.running,
        "jobs": jobs,
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/scheduler/pause/{job_id}")
async def pause_scheduler_job(job_id: str):
    """Pause a specific scheduler job."""
    job = scheduler_service.scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    scheduler_service.scheduler.pause_job(job_id)
    return {
        "success": True,
        "message": f"Paused job: {job.name}",
        "job_id": job_id,
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/scheduler/resume/{job_id}")
async def resume_scheduler_job(job_id: str):
    """Resume a paused scheduler job."""
    job = scheduler_service.scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    scheduler_service.scheduler.resume_job(job_id)
    return {
        "success": True,
        "message": f"Resumed job: {job.name}",
        "job_id": job_id,
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/scheduler/pause-all")
async def pause_all_scheduler_jobs():
    """Pause all background scheduler jobs."""
    paused = []
    for job in scheduler_service.scheduler.get_jobs():
        scheduler_service.scheduler.pause_job(job.id)
        paused.append(job.id)

    return {
        "success": True,
        "message": f"Paused {len(paused)} jobs",
        "jobs_paused": paused,
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/scheduler/resume-all")
async def resume_all_scheduler_jobs():
    """Resume all background scheduler jobs."""
    resumed = []
    for job in scheduler_service.scheduler.get_jobs():
        scheduler_service.scheduler.resume_job(job.id)
        resumed.append(job.id)

    return {
        "success": True,
        "message": f"Resumed {len(resumed)} jobs",
        "jobs_resumed": resumed,
        "timestamp": datetime.now().isoformat(),
    }


# Export the router
__all__ = ["router", "health_simulation_service"]
