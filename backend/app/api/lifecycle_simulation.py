"""
24-Hour Building Lifecycle Simulation API

Endpoints to control the building lifecycle simulation that demonstrates
the full AI optimization → fault → alert → repair → feedback cycle.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.lifecycle_orchestrator import (
    get_lifecycle_orchestrator,
    SCENARIOS,
    EventType,
)
from app.services.simulation_logger import SimulationLogger
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
    Start a 24-hour building lifecycle simulation.

    The simulation compresses 24 hours into the specified duration,
    running through building wake, occupancy cycles, peak load,
    potential faults, repairs, and AI optimizations.

    **Scenarios:**
    - `normal_day`: Typical operations, 10% fault chance
    - `fault_day`: Guaranteed fault at 11am with auto-repair
    - `chiller_failure`: Chiller fault scenario
    - `multi_fault`: Multiple equipment issues
    - `maintenance_day`: Scheduled maintenance, no faults

    **Time Compression:**
    - `duration_minutes=24`: 1 real minute = 1 simulated hour
    - `duration_minutes=12`: 30 real seconds = 1 simulated hour
    - `duration_minutes=2.4`: 6 real seconds = 1 simulated hour (fast demo)
    """
    if request.scenario not in SCENARIOS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scenario: {request.scenario}. Available: {list(SCENARIOS.keys())}"
        )

    orchestrator = get_lifecycle_orchestrator()
    
    # Set up event logging
    run_id = f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
    logger_service = SimulationLogger()
    logger_service.start_run(
        run_id=run_id,
        scenario=request.scenario,
        building_code="site-002",
        config={
            "duration_minutes": request.duration_minutes,
            "scenario": request.scenario,
            "start_hour": request.start_hour,
        },
    )
    orchestrator.add_event_callback(logger_service.on_event)
    
    result = await orchestrator.start(
        scenario=request.scenario,
        duration_minutes=request.duration_minutes,
        start_hour=request.start_hour
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    # Add run_id to response
    result["run_id"] = run_id
    
    # Schedule finalization after simulation completes
    async def finalize_log():
        import asyncio
        # Wait for simulation to complete (estimated based on duration_minutes)
        await asyncio.sleep((request.duration_minutes * 60) + 5)
        logger_service.end_run()
    
    # Start finalization task in background
    import asyncio
    asyncio.create_task(finalize_log())

    return result


@router.post("/stop")
async def stop_simulation():
    """Stop the running simulation."""
    orchestrator = get_lifecycle_orchestrator()
    result = await orchestrator.stop()

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/pause")
async def pause_simulation():
    """Pause the simulation (can be resumed)."""
    orchestrator = get_lifecycle_orchestrator()

    if not orchestrator.running:
        raise HTTPException(status_code=400, detail="Simulation not running")

    orchestrator.pause()
    return {"success": True, "status": "paused"}


@router.post("/resume")
async def resume_simulation():
    """Resume a paused simulation."""
    orchestrator = get_lifecycle_orchestrator()

    if not orchestrator.running:
        raise HTTPException(status_code=400, detail="Simulation not running")

    orchestrator.resume()
    return {"success": True, "status": "running"}


@router.get("/status", response_model=SimulationStatusResponse)
async def get_simulation_status():
    """
    Get the current status of the lifecycle simulation.

    Returns simulated time, events count, active faults, and recent events.
    """
    orchestrator = get_lifecycle_orchestrator()
    status = orchestrator.get_status()
    return SimulationStatusResponse(**status)


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
    orchestrator = get_lifecycle_orchestrator()

    events = orchestrator.events

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


@router.get("/events/timeline")
async def get_event_timeline():
    """
    Get events organized by simulated hour.

    Useful for visualizing the day's activity.
    """
    orchestrator = get_lifecycle_orchestrator()

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
    orchestrator = get_lifecycle_orchestrator()

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
    orchestrator = get_lifecycle_orchestrator()

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
    orchestrator = get_lifecycle_orchestrator()

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
    orchestrator = get_lifecycle_orchestrator()

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
