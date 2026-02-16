"""
24-Hour Building Lifecycle Simulation API

Endpoints to control the building lifecycle simulation that demonstrates
the full AI optimization → fault → alert → repair → feedback cycle.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.lifecycle_orchestrator import SCENARIOS, EventType
from app.services.simulation_orchestrator import (
    get_simulation_by_task_id,
)
from app.services.simulation_logger import SimulationLogger
from app.database.supabase_client import Supabase
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lifecycle", tags=["lifecycle-simulation"])


# ============================================================================
# Request/Response Models
# ============================================================================

class StartSimulationRequest(BaseModel):
    """Request to start lifecycle simulation."""
    scenario: str = Field(
        default="fault_day",
        description="Scenario name: normal_day, fault_day, chiller_failure, multi_fault, maintenance_day"
    )
    duration_minutes: float = Field(
        default=24.0,
        ge=1.0,
        le=1440.0,
        description="Real-time duration for 24-hour simulation (24 = 1 min/hour)"
    )
    start_hour: int = Field(
        default=6,
        ge=0,
        le=23,
        description="Simulated hour to start (0-23)"
    )


class SimulationStatusResponse(BaseModel):
    """Response for simulation status."""
    running: bool
    paused: bool
    scenario: Optional[str]
    simulated_time: Optional[str]
    simulated_hour: Optional[int]
    real_elapsed_seconds: float
    events_count: int
    active_faults: int
    pending_repairs: int
    recent_events: List[dict]


class ScenarioInfo(BaseModel):
    """Information about a scenario."""
    name: str
    description: str
    fault_probability: float
    fault_hour: Optional[int]
    fault_equipment_type: Optional[str]
    auto_repair: bool
    repair_delay_hours: int


class EventResponse(BaseModel):
    """A lifecycle event."""
    hour: int
    event_type: str
    description: str
    equipment_id: Optional[str]
    equipment_name: Optional[str]
    details: dict
    success: bool
    timestamp: str


# ============================================================================
# Simulation Control Endpoints
# ============================================================================

@router.post("/start")
async def start_simulation(request: StartSimulationRequest):
    """
    Start a 24-hour building lifecycle simulation (task-queued).

    Creates a task in the database and returns immediately.
    Background processor picks up queued tasks and runs simulations sequentially.
    
    This enables:
    - Multiple users to start simulations without conflicts
    - Crash recovery (simulation resumes from checkpoint)
    - Progress tracking via polling /status/{task_id}

    **Scenarios:**
    - `normal_day`: Typical operations, 10% fault chance
    - `fault_day`: Guaranteed fault at 11am with auto-repair
    - `chiller_failure`: Chiller fault scenario
    - `multi_fault`: Multiple equipment issues
    - `maintenance_day`: Scheduled maintenance, no faults
    - `grant_hvac_dali_ai_annual`: 365-day annual simulation (demo mode with continuous AI)

    **Time Compression:**
    - `duration_minutes=24`: 1 real minute = 1 simulated hour
    - `duration_minutes=12`: 30 real seconds = 1 simulated hour
    - `duration_minutes=2.4`: 6 real seconds = 1 simulated hour (fast demo)
    - `duration_minutes=240`: 4 hours real time for 365-day simulation (default)
    """
    if request.scenario not in SCENARIOS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scenario: {request.scenario}. Available: {list(SCENARIOS.keys())}"
        )

    try:
        client = Supabase.instance()
        task_id = str(uuid.uuid4())
        
        # Create task in database (status='queued')
        response = client.table("solar_annual_tasks").insert({
            "task_id": task_id,
            "site_id": "site-002",  # Default to site-002 (can be parameterized later)
            "scenario": request.scenario,
            "simulation_type": "lifecycle",
            "status": "queued",
            "progress_pct": 0,
            "days_completed": 0,
            "duration_minutes": request.duration_minutes,
        }).execute()
        
        logger.info(f"Created lifecycle simulation task {task_id}: {request.scenario}")
        
        return {
            "success": True,
            "task_id": task_id,
            "status": "queued",
            "scenario": request.scenario,
            "duration_minutes": request.duration_minutes,
            "message": "Simulation queued. Poll /status/{task_id} to track progress."
        }
        
    except Exception as e:
        logger.error(f"Failed to create simulation task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create task: {str(e)}")


@router.post("/cancel/{task_id}")
async def stop_simulation(task_id: str):
    """
    Cancel a queued or running simulation task.
    
    Args:
        task_id: Task identifier from /start endpoint
        
    Returns:
        Success response confirming cancellation
    """
    try:
        orchestrator = get_simulation_by_task_id(task_id)
        
        if orchestrator:
            # Simulation is running - stop it
            result = await orchestrator.stop()
            return {
                "success": True,
                "status": "cancelled",
                "message": "Simulation stopped successfully"
            }
        else:
            # Simulation not running - try to update database status to cancelled
            client = Supabase.instance()
            client.table("solar_annual_tasks") \
                .update({"status": "failed", "error_message": "Cancelled by user"}) \
                .eq("task_id", task_id) \
                .execute()
            
            return {
                "success": True,
                "status": "cancelled",
                "message": "Task cancelled"
            }
    except Exception as e:
        logger.error(f"Failed to cancel simulation {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel: {str(e)}")


@router.post("/pause/{task_id}")
async def pause_simulation(task_id: str):
    """
    Pause a running simulation (can be resumed).
    
    Args:
        task_id: Task identifier from /start endpoint
        
    Returns:
        Success response confirming pause
    """
    try:
        orchestrator = get_simulation_by_task_id(task_id)
        
        if not orchestrator or not orchestrator.running:
            raise HTTPException(status_code=400, detail="Simulation not running")
        
        orchestrator.pause()
        return {"success": True, "status": "paused", "message": "Simulation paused"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to pause simulation {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to pause: {str(e)}")


@router.post("/resume/{task_id}")
async def resume_simulation(task_id: str):
    """
    Resume a paused simulation.
    
    Args:
        task_id: Task identifier from /start endpoint
        
    Returns:
        Success response confirming resume
    """
    try:
        orchestrator = get_simulation_by_task_id(task_id)
        
        if not orchestrator or not orchestrator.running:
            raise HTTPException(status_code=400, detail="Simulation not running")
        
        orchestrator.resume()
        return {"success": True, "status": "running", "message": "Simulation resumed"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume simulation {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to resume: {str(e)}")


@router.get("/status/{task_id}", response_model=SimulationStatusResponse)
async def get_simulation_status(task_id: str):
    """
    Get the current status of a lifecycle simulation task.

    Queries database for task status and state snapshot.
    Returns simulated time, progress, events count, active faults, and recent events.

    Args:
        task_id: Task identifier from /start endpoint or site_id (e.g., site-002)

    Returns:
        SimulationStatusResponse with status, progress, and recent events
    """
    # If this looks like a site_id (e.g., "site-002"), return empty status
    if task_id.startswith("site-"):
        return SimulationStatusResponse(
            running=False,
            paused=False,
            scenario=None,
            simulated_time=None,
            simulated_hour=None,
            real_elapsed_seconds=0,
            events_count=0,
            active_faults=0,
            pending_repairs=0,
            recent_events=[]
        )

    try:
        client = Supabase.instance()

        # Query task from database
        response = client.table("solar_annual_tasks") \
            .select("*") \
            .eq("task_id", task_id) \
            .execute()

        if not response or not response.data or len(response.data) == 0:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        task = response.data[0]
        if not task or not isinstance(task, dict):
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        # Check if running orchestrator (for real-time event updates)
        orchestrator = get_simulation_by_task_id(task_id)
        
        if orchestrator and orchestrator.running:
            # Simulation is running - get live status from orchestrator
            status = orchestrator.get_status()
            return SimulationStatusResponse(
                running=True,
                paused=orchestrator.paused,
                scenario=orchestrator.current_scenario.name if orchestrator.current_scenario else None,
                simulated_time=orchestrator.simulated_time.isoformat(),
                simulated_hour=orchestrator.simulated_time.hour,
                real_elapsed_seconds=(datetime.now() - orchestrator.real_start_time).total_seconds() if orchestrator.real_start_time else 0,
                events_count=len(orchestrator.events),
                active_faults=len(orchestrator.active_faults),
                pending_repairs=len(orchestrator.pending_repairs),
                recent_events=[
                    {
                        "timestamp": e.timestamp.isoformat(),
                        "event_type": e.event_type.value,
                        "equipment_id": e.equipment_id,
                        "message": e.message,
                    }
                    for e in orchestrator.events[-10:]
                ]
            )
        else:
            # Simulation not running - get status from database
            if not isinstance(task, dict):
                task = {}
            state_snapshot = task.get("state_snapshot", {}) if task else {}
            if state_snapshot is None or not isinstance(state_snapshot, dict):
                state_snapshot = {}
            recent_events = state_snapshot.get("recent_events", [])[-10:] if isinstance(state_snapshot, dict) else []
            
            # Extract simulated_hour from ISO format datetime string (YYYY-MM-DDTHH:MM:SS)
            simulated_hour = None
            simulated_time_str = state_snapshot.get("simulated_time") if isinstance(state_snapshot, dict) else None
            if simulated_time_str:
                try:
                    dt = datetime.fromisoformat(simulated_time_str.replace('Z', '+00:00'))
                    simulated_hour = dt.hour
                except:
                    simulated_hour = None
            
            return SimulationStatusResponse(
                running=task.get("status") == "running" if task else False,
                paused=False,
                scenario=task.get("scenario") if task else None,
                simulated_time=simulated_time_str,
                simulated_hour=simulated_hour,
                real_elapsed_seconds=0,
                events_count=len(state_snapshot.get("recent_events", [])) if isinstance(state_snapshot, dict) else 0,
                active_faults=len(state_snapshot.get("active_faults", {})) if isinstance(state_snapshot, dict) else 0,
                pending_repairs=len(state_snapshot.get("pending_repairs", {})) if isinstance(state_snapshot, dict) else 0,
                recent_events=recent_events
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get simulation status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@router.get("/status")
async def get_default_simulation_status():
    """
    Get status of the default simulation (for backwards compatibility).
    
    Returns the status of any currently running simulation or a default empty response.
    Used by frontend health check to determine if a simulation is running.
    """
    try:
        # Try to get the default site's running simulation
        orchestrator = get_simulation_by_task_id("default")
        
        if orchestrator and orchestrator.running:
            return {
                "running": True,
                "paused": orchestrator.paused,
                "scenario": orchestrator.current_scenario.name if orchestrator.current_scenario else None,
                "simulated_time": orchestrator.simulated_time.isoformat(),
                "simulated_hour": orchestrator.simulated_time.hour,
            }
        else:
            # No simulation running
            return {
                "running": False,
                "paused": False,
                "scenario": None,
                "simulated_time": None,
                "simulated_hour": None,
            }
    except Exception as e:
        logger.debug(f"Could not get default simulation status: {e}")
        # Return empty response instead of failing
        return {
            "running": False,
            "paused": False,
            "scenario": None,
            "simulated_time": None,
            "simulated_hour": None,
        }


@router.get("/status/{site_id}")
async def get_site_simulation_status(site_id: str):
    """
    Get status of a simulation for a specific site.
    
    Args:
        site_id: Site identifier (e.g., 'site-002')
        
    Returns:
        Simulation status or empty response if none running
    """
    # Return default empty status (no simulation running)
    # This endpoint exists for frontend compatibility
    return {
        "running": False,
        "paused": False,
        "scenario": None,
        "simulated_time": None,
        "simulated_hour": None,
        "site_id": site_id,
    }


# ============================================================================
# Event Retrieval Endpoints
# ============================================================================

@router.get("/events")
async def get_simulation_events(
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    equipment_id: Optional[str] = Query(None, description="Filter by equipment"),
    limit: int = Query(50, ge=1, le=500, description="Maximum events to return")
):
    """
    Get events from the current simulation.

    Events include building wake, occupancy changes, faults, repairs, etc.
    """
    try:
        orchestrator = get_simulation_by_task_id("default")
        if not orchestrator:
            return {"count": 0, "events": []}

        events = orchestrator.events if orchestrator.events else []

        # Filter by type
        if event_type:
            events = [e for e in events if e.event_type.value == event_type]

        # Filter by equipment
        if equipment_id:
            events = [e for e in events if e.equipment_id == equipment_id]

        # Limit and format
        events = events[-limit:]

        return {
            "count": len(events),
            "events": [
                {
                    "hour": e.simulated_hour,
                    "event_type": e.event_type.value,
                    "description": e.description,
                    "equipment_id": e.equipment_id,
                    "equipment_name": e.equipment_name,
                    "details": e.details,
                    "success": e.success,
                    "timestamp": e.timestamp.isoformat()
                }
                for e in events
            ]
        }
    except Exception as err:
        import logging
        logging.error(f"Error in get_simulation_events: {err}", exc_info=True)
        return {"count": 0, "events": [], "error": str(err)}


@router.get("/events/timeline")
async def get_event_timeline():
    """
    Get events organized by simulated hour.

    Useful for visualizing the day's activity.
    """
    orchestrator = get_simulation_by_task_id("default")

    timeline = {}
    for event in orchestrator.events:
        hour = event.simulated_hour
        if hour not in timeline:
            timeline[hour] = []
        timeline[hour].append({
            "type": event.event_type.value,
            "description": event.description,
            "equipment": event.equipment_name,
            "timestamp": event.timestamp.isoformat()
        })

    return {
        "hours": sorted(timeline.keys()),
        "timeline": timeline
    }


# ============================================================================
# Scenario Information
# ============================================================================

@router.get("/scenarios")
async def list_scenarios():
    """
    List all available simulation scenarios.

    Each scenario defines fault probability, timing, and repair behavior.
    """
    return {
        "scenarios": [
            {
                "id": key,
                "name": config.name,
                "description": config.description,
                "fault_probability": config.fault_probability,
                "fault_hour": config.fault_hour,
                "fault_equipment_type": config.fault_equipment_type,
                "auto_repair": config.auto_repair,
                "repair_delay_hours": config.repair_delay_hours,
                "optimization_enabled": config.optimization_enabled,
                "clawd_notifications": config.clawd_notifications
            }
            for key, config in SCENARIOS.items()
        ]
    }


@router.get("/scenarios/{scenario_id}", response_model=ScenarioInfo)
async def get_scenario(scenario_id: str):
    """Get details of a specific scenario."""
    if scenario_id not in SCENARIOS:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_id}")

    config = SCENARIOS[scenario_id]
    return ScenarioInfo(
        name=config.name,
        description=config.description,
        fault_probability=config.fault_probability,
        fault_hour=config.fault_hour,
        fault_equipment_type=config.fault_equipment_type,
        auto_repair=config.auto_repair,
        repair_delay_hours=config.repair_delay_hours
    )


# ============================================================================
# Manual Intervention Endpoints
# ============================================================================

@router.post("/inject-fault")
async def inject_fault_manually(
    equipment_code: Optional[str] = Query(None, description="Equipment to fault (random if not specified)"),
    fault_type: str = Query("vibration", description="Fault type: vibration, temperature, pressure, electrical")
):
    """
    Manually inject a fault during simulation.

    Useful for demonstrating the fault → alert → repair cycle on demand.
    """
    orchestrator = get_simulation_by_task_id("default")

    if not orchestrator.running:
        raise HTTPException(status_code=400, detail="Simulation not running")

    # Trigger fault injection
    await orchestrator._inject_fault()

    return {
        "success": True,
        "message": "Fault injected",
        "active_faults": len(orchestrator.active_faults)
    }


@router.post("/trigger-repair/{equipment_code}")
async def trigger_repair_manually(equipment_code: str):
    """
    Manually trigger repair completion for equipment.

    Simulates technician completing repair immediately.
    """
    orchestrator = get_simulation_by_task_id("default")

    if equipment_code not in orchestrator.pending_repairs:
        raise HTTPException(
            status_code=404,
            detail=f"No pending repair for {equipment_code}"
        )

    repair_info = orchestrator.pending_repairs[equipment_code]
    await orchestrator._complete_repair(equipment_code, repair_info)

    return {
        "success": True,
        "message": f"Repair completed for {equipment_code}",
        "remaining_faults": len(orchestrator.active_faults)
    }


# ============================================================================
# Quick Demo Endpoints
# ============================================================================

@router.post("/demo/quick-cycle")
async def run_quick_demo_cycle():
    """
    Run a quick 5-minute demo cycle showing the full lifecycle.

    This compresses 24 hours into 5 minutes with a guaranteed fault
    at simulated 11am and repair at 2pm.
    """
    orchestrator = get_simulation_by_task_id("default")

    # Stop any running simulation
    if orchestrator.running:
        await orchestrator.stop()

    # Start fast demo
    result = await orchestrator.start(
        scenario="fault_day",
        duration_minutes=5.0,  # 5 minutes for full day
        start_hour=6
    )

    return {
        **result,
        "demo_info": {
            "total_duration": "5 minutes",
            "time_per_hour": "12.5 seconds",
            "fault_expected_at": "~1 minute (simulated 11am)",
            "repair_expected_at": "~3 minutes (simulated 2pm)",
            "watch_events_at": "/api/lifecycle/events"
        }
    }


@router.post("/demo/ultra-fast")
async def run_ultra_fast_demo():
    """
    Run an ultra-fast 2-minute demo.

    24 hours in 2 minutes = 5 seconds per simulated hour.
    """
    orchestrator = get_simulation_by_task_id("default")

    if orchestrator.running:
        await orchestrator.stop()

    result = await orchestrator.start(
        scenario="fault_day",
        duration_minutes=2.0,
        start_hour=6
    )

    return {
        **result,
        "demo_info": {
            "total_duration": "2 minutes",
            "time_per_hour": "5 seconds",
            "watch_events_at": "/api/lifecycle/events"
        }
    }
