"""
24-Hour Building Lifecycle Simulation API

Endpoints to control the building lifecycle simulation that demonstrates
the full AI optimization → fault → alert → repair → feedback cycle.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.lifecycle_orchestrator import ALL_SCENARIOS, SCENARIOS
from app.services.simulation_orchestrator import (
    get_simulation_by_task_id,
)
from app.database.supabase_client import Supabase
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lifecycle", tags=["lifecycle-simulation"])


def _numeric_or_default(value, default=0):
    """Return numeric value or default for mocks/invalid types."""
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ============================================================================
# Request/Response Models
# ============================================================================


class StartSimulationRequest(BaseModel):
    """Request to start lifecycle simulation."""

    scenario: str = Field(
        default="sentinel_annual",
        description=(
            "Scenario name: sentinel_annual (365-day unified), normal_day, fault_day, "
            "chiller_failure, multi_fault, maintenance_day"
        ),
    )
    duration_minutes: float = Field(
        default=3650.0,
        ge=1.0,
        le=11000.0,
        description="Total real-time minutes for 365 days (3650 = 10 min/day, 25s/hour)",
    )
    start_hour: int = Field(default=6, ge=0, le=23, description="Simulated hour to start (0-23)")
    speed_multiplier: float = Field(
        default=10.0,
        ge=0.1,
        le=10000.0,
        description="Speed factor: 1x=real-time, 10x=10x faster, 100x=100x faster",
    )
    site_id: str = Field(
        default="site-002",
        description="Target site identifier (e.g. 'site-002', 'site-005')",
    )
    start_date: Optional[str] = Field(
        default=None,
        description="ISO date string for simulation start date (e.g. '2025-06-15')",
    )


class SpeedChangeRequest(BaseModel):
    """Request to change simulation speed while running."""

    speed_multiplier: float = Field(
        ge=0.1,
        le=10000.0,
        description="New speed multiplier (0.1 to 10000)",
    )


class SimulationStatusResponse(BaseModel):
    """Response for simulation status."""

    running: bool
    paused: bool
    scenario: Optional[str] = None
    simulated_time: Optional[str] = None
    simulated_hour: Optional[int] = None
    real_elapsed_seconds: float = 0
    events_count: int = 0
    active_faults: int = 0
    pending_repairs: int = 0
    recent_events: List[dict] = []
    progress_pct: int = 0  # Progress percentage (0-100)
    days_simulated: int = 0
    # Speed control fields
    speed_multiplier: Optional[float] = None
    seconds_per_hour: Optional[float] = None
    # Schedule state fields
    schedule_state: Optional[str] = None
    hvac_mode: Optional[str] = None
    chiller_staging: Optional[str] = None
    target_occupancy: Optional[float] = None
    lighting_mode: Optional[str] = None
    # Weather and environment fields
    ambient_temp: Optional[float] = None
    is_raining: Optional[bool] = None
    cloud_cover: Optional[float] = None
    solar_efficiency: Optional[float] = None
    current_season: Optional[str] = None
    occupancy_percent: Optional[float] = None
    # Energy consumption fields
    total_energy_kwh: Optional[float] = None  # Cumulative kWh consumed
    current_hour_power_kw: Optional[float] = None  # Current hour's power in kW
    # SENTINEL response loop status (106-02)
    sentinel_status: Optional[dict] = None


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
    Start a building lifecycle simulation (task-queued).

    Creates a task in the database and returns immediately.
    Background processor picks up queued tasks and runs simulations sequentially.

    This enables:
    - Multiple users to start simulations without conflicts
    - Crash recovery (simulation resumes from checkpoint)
    - Progress tracking via polling /status/{task_id}

    **Scenarios:**
    - `normal_day`: Typical operations, 10% fault chance (default)
    - `fault_day`: Guaranteed fault at 11am with auto-repair
    - `chiller_failure`: Chiller fault scenario
    - `multi_fault`: Multiple equipment issues
    - `maintenance_day`: Scheduled maintenance, no faults
    - `sentinel_annual`: 365-day unified annual simulation (HVAC + DALI + Solar + BESS)

    **Speed Control:**
    - `speed_multiplier=1`: Real-time (1 hour = 60 seconds)
    - `speed_multiplier=10`: 10x speed (1 hour = 6 seconds) [default]
    - `speed_multiplier=100`: 100x speed (1 hour = 0.6 seconds)
    - `speed_multiplier=1000`: 1000x speed (1 hour = 0.06 seconds)
    """
    if request.scenario not in ALL_SCENARIOS:
        raise HTTPException(
            status_code=400, detail=f"Unknown scenario: {request.scenario}. Available: {list(SCENARIOS.keys())}"
        )

    try:
        client = Supabase.instance()
        task_id = str(uuid.uuid4())

        # Create task in database (status='queued')
        (
            client.table("lifecycle_simulation_tasks")
            .insert(
                {
                    "task_id": task_id,
                    "site_id": request.site_id,
                    "scenario": request.scenario,
                    "simulation_type": "lifecycle",
                    "status": "queued",
                    "progress_pct": 0,
                    "days_completed": 0,
                    "duration_minutes": request.duration_minutes,
                }
            )
            .execute()
        )

        logger.info(
            f"Created lifecycle simulation task {task_id}: {request.scenario} at {request.speed_multiplier}x speed"
        )

        return {
            "success": True,
            "task_id": task_id,
            "status": "queued",
            "scenario": request.scenario,
            "speed_multiplier": request.speed_multiplier,
            "duration_minutes": request.duration_minutes,
            "start_date": request.start_date,
            "message": "Simulation queued. Poll /status/{task_id} to track progress.",
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
            await orchestrator.stop()
            return {"success": True, "status": "cancelled", "message": "Simulation stopped successfully"}
        else:
            # Simulation not running - try to update database status to cancelled
            client = Supabase.instance()
            client.table("lifecycle_simulation_tasks").update(
                {"status": "failed", "error_message": "Cancelled by user"}
            ).eq("task_id", task_id).execute()

            return {"success": True, "status": "cancelled", "message": "Task cancelled"}
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


@router.post("/speed/{task_id}")
async def change_simulation_speed(task_id: str, request: SpeedChangeRequest):
    """
    Change the speed of a running simulation.

    Args:
        task_id: Task identifier from /start endpoint
        request: SpeedChangeRequest with new speed_multiplier

    Returns:
        New speed settings
    """
    try:
        orchestrator = get_simulation_by_task_id(task_id)

        if not orchestrator or not orchestrator.running:
            raise HTTPException(status_code=400, detail="No simulation running")

        result = orchestrator.set_speed(request.speed_multiplier)
        return {
            "success": True,
            **result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to change speed for {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to change speed: {str(e)}")


@router.post("/speed")
async def change_default_speed(request: SpeedChangeRequest):
    """
    Change the speed of the currently running simulation.

    Finds any active simulation from the task queue and changes its speed.

    Args:
        request: SpeedChangeRequest with new speed_multiplier

    Returns:
        New speed settings
    """
    try:
        from app.services.simulation_orchestrator import get_all_active_simulations

        # Find any running simulation from the task-based queue
        active = get_all_active_simulations()
        orchestrator = None
        for _tid, orch in active.items():
            if orch.running:
                orchestrator = orch
                break

        # Fallback to singleton
        if not orchestrator:
            from app.services.lifecycle_orchestrator import get_lifecycle_orchestrator

            orchestrator = get_lifecycle_orchestrator()

        if not orchestrator or not orchestrator.running:
            raise HTTPException(status_code=400, detail="No simulation running")

        result = orchestrator.set_speed(request.speed_multiplier)
        return {
            "success": True,
            **result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to change speed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to change speed: {str(e)}")


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
    # If this looks like a site_id (e.g., "site-002"), find the most recent running/queued task
    if task_id.startswith("site-"):
        try:
            client = Supabase.instance()
            # Look for the most recent running or queued task for this site
            site_task = (
                client.table("lifecycle_simulation_tasks")
                .select("task_id")
                .eq("site_id", task_id)
                .in_("status", ["running", "queued"])
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if site_task.data and site_task.data[0].get("task_id"):
                # Redirect to the actual task status
                task_id = site_task.data[0]["task_id"]
                logger.info(f"Resolved site {task_id} to running task: {task_id}")
            else:
                # No running simulation for this site
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
                    recent_events=[],
                )
        except Exception as e:
            logger.warning(f"Could not look up site simulation: {e}")
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
                recent_events=[],
            )

    try:
        client = Supabase.instance()

        # Query task from database
        response = client.table("lifecycle_simulation_tasks").select("*").eq("task_id", task_id).execute()

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
            days = _numeric_or_default(getattr(orchestrator, "days_simulated", None), -1)
            if days < 0:
                days = _numeric_or_default(task.get("days_completed", 0) if task else 0, 0)

            progress_pct = int((days / 365) * 100) if days > 0 else 0
            if progress_pct <= 0:
                progress_pct = int(
                    _numeric_or_default(
                        status.get("progress_percent"),
                        _numeric_or_default(
                            status.get("progress_pct"),
                            _numeric_or_default(task.get("progress_pct", 0) if task else 0, 0),
                        ),
                    )
                )
            progress_pct = max(0, min(100, progress_pct))

            # Get schedule state for enriched status
            schedule_state_str = None
            hvac_mode_str = None
            chiller_staging_str = None
            target_occupancy_val = None
            lighting_mode_str = None
            try:
                sched = orchestrator.building_schedule.get_state(
                    orchestrator.simulated_time.hour,
                    orchestrator.simulated_time.weekday(),
                )
                schedule_state_str = sched.state.value
                hvac_mode_str = sched.hvac_mode.value
                chiller_staging_str = sched.chiller_staging.value
                target_occupancy_val = sched.target_occupancy_pct
                lighting_mode_str = sched.lighting_mode.value
            except Exception:
                pass

            return SimulationStatusResponse(
                running=True,
                paused=orchestrator.paused,
                scenario=orchestrator.current_scenario.name if orchestrator.current_scenario else None,
                simulated_time=orchestrator.simulated_time.isoformat(),
                simulated_hour=orchestrator.simulated_time.hour,
                real_elapsed_seconds=(datetime.now() - orchestrator.real_start_time).total_seconds()
                if orchestrator.real_start_time
                else 0,
                events_count=len(orchestrator.events),
                active_faults=len(orchestrator.active_faults),
                pending_repairs=len(orchestrator.pending_repairs),
                recent_events=[
                    {
                        "timestamp": e.timestamp.isoformat(),
                        "event_type": e.event_type.value,
                        "equipment_id": e.equipment_id,
                        "description": getattr(e, "description", ""),
                        "simulated_hour": getattr(e, "simulated_hour", 0),
                        "details": getattr(e, "details", {}),
                    }
                    for e in orchestrator.events[-10:]
                ],
                progress_pct=progress_pct,
                days_simulated=days,
                # Speed control
                speed_multiplier=orchestrator.speed_multiplier,
                seconds_per_hour=orchestrator.seconds_per_simulated_hour,
                # Schedule state
                schedule_state=schedule_state_str,
                hvac_mode=hvac_mode_str,
                chiller_staging=chiller_staging_str,
                target_occupancy=target_occupancy_val,
                lighting_mode=lighting_mode_str,
                # Weather data from orchestrator's get_status()
                ambient_temp=status.get("ambient_temp"),
                is_raining=status.get("is_raining"),
                cloud_cover=status.get("cloud_cover"),
                solar_efficiency=status.get("solar_efficiency"),
                current_season=status.get("current_season"),
                occupancy_percent=status.get("occupancy_percent"),
                # Energy consumption data
                total_energy_kwh=status.get("total_energy_kwh"),
                current_hour_power_kw=status.get("current_hour_power_kw"),
                # SENTINEL response loop status (106-02)
                sentinel_status=orchestrator._get_sentinel_status()
                if hasattr(orchestrator, "_get_sentinel_status")
                else None,
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
                    dt = datetime.fromisoformat(simulated_time_str.replace("Z", "+00:00"))
                    simulated_hour = dt.hour
                except (ValueError, TypeError):
                    simulated_hour = None

            # For completed simulations, also use progress_pct from database
            # If task is completed and progress > 0, update simulated_time from completion timestamp
            task_status = task.get("status") if task else "unknown"
            progress_pct = _numeric_or_default(task.get("progress_pct", 0) if task else 0, 0)

            # If simulation is completed but has progress, derive simulated_time from completion date
            if task_status == "completed" and progress_pct > 0 and not simulated_time_str:
                completed_at = task.get("completed_at") if task else None
                if completed_at:
                    try:
                        dt = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
                        simulated_time_str = dt.isoformat()
                        simulated_hour = dt.hour
                    except (ValueError, TypeError):
                        pass

            # Get days from database or derive from state snapshot
            days_completed = _numeric_or_default(task.get("days_completed", 0) if task else 0, 0)
            if not days_completed and isinstance(state_snapshot, dict):
                days_completed = _numeric_or_default(state_snapshot.get("days_simulated", 0), 0)

            # Compute weather data from simulated_time using SeasonalModeler
            ambient_temp = None
            is_raining = None
            cloud_cover = None
            solar_efficiency = None
            current_season = None
            if simulated_time_str:
                try:
                    from app.services.seasonal_modeler import SeasonalModeler

                    sim_dt = datetime.fromisoformat(simulated_time_str.replace("Z", "+00:00"))
                    sim_hour = sim_dt.hour
                    modeler = SeasonalModeler()
                    current_season = modeler.get_season_name(sim_dt.date())
                    is_raining = modeler.should_rain_today(sim_dt.date())
                    cloud_cover = modeler.get_cloud_cover_percent(sim_dt.date())
                    ambient_temp = modeler.get_ambient_temperature(sim_dt.date(), sim_hour, is_raining)
                    if 6 <= sim_hour < 18:
                        base_eff = 100 - (cloud_cover * 0.8)
                        if is_raining:
                            base_eff *= 0.3
                        solar_efficiency = max(10, base_eff)
                    else:
                        solar_efficiency = 0
                except Exception:
                    pass

            return SimulationStatusResponse(
                running=task_status == "running",
                paused=False,
                scenario=task.get("scenario") if task else None,
                simulated_time=simulated_time_str,
                simulated_hour=simulated_hour,
                real_elapsed_seconds=0,
                events_count=len(state_snapshot.get("recent_events", [])) if isinstance(state_snapshot, dict) else 0,
                active_faults=len(state_snapshot.get("active_faults", {})) if isinstance(state_snapshot, dict) else 0,
                pending_repairs=len(state_snapshot.get("pending_repairs", {}))
                if isinstance(state_snapshot, dict)
                else 0,
                recent_events=recent_events,
                progress_pct=progress_pct if task else 0,
                days_simulated=days_completed,
                ambient_temp=ambient_temp,
                is_raining=is_raining,
                cloud_cover=cloud_cover,
                solar_efficiency=solar_efficiency,
                current_season=current_season,
                total_energy_kwh=state_snapshot.get("total_energy_kwh") if isinstance(state_snapshot, dict) else None,
                current_hour_power_kw=state_snapshot.get("current_hour_power_kw")
                if isinstance(state_snapshot, dict)
                else None,
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


async def get_site_simulation_status(site_id: str):
    """
    Get status of a simulation for a specific site.

    Args:
        site_id: Site identifier (e.g., 'site-002')

    Returns:
        Simulation status or empty response if none running
    """
    try:
        from app.services.simulation_orchestrator import _active_simulations

        # Look for any running simulation (simulations run site-wide)
        for task_id, orchestrator in _active_simulations.items():
            if orchestrator.running:
                # Get full status from orchestrator
                status = orchestrator.get_status()

                return SimulationStatusResponse(
                    running=True,
                    paused=orchestrator.paused,
                    scenario=orchestrator.current_scenario.name if orchestrator.current_scenario else None,
                    simulated_time=orchestrator.simulated_time.isoformat() if orchestrator.simulated_time else None,
                    simulated_hour=orchestrator.simulated_time.hour if orchestrator.simulated_time else None,
                    real_elapsed_seconds=status.get("real_elapsed_seconds", 0),
                    events_count=status.get("events_count", 0),
                    active_faults=status.get("active_faults", 0),
                    pending_repairs=status.get("pending_repairs", 0),
                    recent_events=status.get("recent_events", []),
                    progress_pct=status.get("progress_percent", 0),
                    days_simulated=orchestrator.days_simulated,
                    # Weather fields
                    ambient_temp=status.get("ambient_temp"),
                    is_raining=status.get("is_raining"),
                    cloud_cover=status.get("cloud_cover"),
                    solar_efficiency=status.get("solar_efficiency"),
                    current_season=status.get("current_season"),
                    occupancy_percent=status.get("occupancy_percent"),
                    # Energy consumption fields
                    total_energy_kwh=status.get("total_energy_kwh"),
                    current_hour_power_kw=status.get("current_hour_power_kw"),
                )
    except Exception as e:
        logger.debug(f"Error getting simulation status: {e}")

    # Return default empty status if no simulation running
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
        recent_events=[],
        progress_pct=0,
        days_simulated=0,
    )


# ============================================================================
# Event Retrieval Endpoints
# ============================================================================


@router.get("/events")
async def get_simulation_events(
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    equipment_id: Optional[str] = Query(None, description="Filter by equipment"),
    limit: int = Query(50, ge=1, le=500, description="Maximum events to return"),
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
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in events
            ],
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
        timeline[hour].append(
            {
                "type": event.event_type.value,
                "description": event.description,
                "equipment": event.equipment_name,
                "timestamp": event.timestamp.isoformat(),
            }
        )

    return {"hours": sorted(timeline.keys()), "timeline": timeline}


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
                "sentry_notifications": config.sentry_notifications,
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
        repair_delay_hours=config.repair_delay_hours,
    )


# ============================================================================
# Manual Intervention Endpoints
# ============================================================================


@router.post("/inject-fault")
async def inject_fault_manually(
    equipment_code: Optional[str] = Query(None, description="Equipment to fault (random if not specified)"),
    fault_type: str = Query("vibration", description="Fault type: vibration, temperature, pressure, electrical"),
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

    return {"success": True, "message": "Fault injected", "active_faults": len(orchestrator.active_faults)}


@router.post("/trigger-repair/{equipment_code}")
async def trigger_repair_manually(equipment_code: str):
    """
    Manually trigger repair completion for equipment.

    Simulates technician completing repair immediately.
    """
    orchestrator = get_simulation_by_task_id("default")

    if equipment_code not in orchestrator.pending_repairs:
        raise HTTPException(status_code=404, detail=f"No pending repair for {equipment_code}")

    repair_info = orchestrator.pending_repairs[equipment_code]
    await orchestrator._complete_repair(equipment_code, repair_info)

    return {
        "success": True,
        "message": f"Repair completed for {equipment_code}",
        "remaining_faults": len(orchestrator.active_faults),
    }


# ============================================================================
# Quick Demo Endpoints
# ============================================================================


@router.post("/demo/quick-cycle")
async def run_quick_demo_cycle():
    """
    Run a quick demo cycle at 100x speed showing the full lifecycle.

    At 100x speed: 24 hours in ~14.4 seconds with a guaranteed fault
    at simulated 11am and repair at 1pm.
    """
    orchestrator = get_simulation_by_task_id("default")

    # Stop any running simulation
    if orchestrator.running:
        await orchestrator.stop()

    # Start fast demo at 100x speed
    result = await orchestrator.start(
        scenario="fault_day",
        speed_multiplier=100.0,
        start_hour=6,
    )

    return {
        **result,
        "demo_info": {
            "speed": "100x",
            "time_per_hour": "0.6 seconds",
            "total_duration": "~14 seconds",
            "fault_expected_at": "simulated 11am",
            "repair_expected_at": "simulated 1pm",
            "watch_events_at": "/api/lifecycle/events",
        },
    }


@router.post("/demo/ultra-fast")
async def run_ultra_fast_demo():
    """
    Run an ultra-fast demo at 1000x speed.

    24 hours in ~1.4 seconds.
    """
    orchestrator = get_simulation_by_task_id("default")

    if orchestrator.running:
        await orchestrator.stop()

    result = await orchestrator.start(
        scenario="fault_day",
        speed_multiplier=1000.0,
        start_hour=6,
    )

    return {
        **result,
        "demo_info": {
            "speed": "1000x",
            "time_per_hour": "0.06 seconds",
            "total_duration": "~1.4 seconds",
            "watch_events_at": "/api/lifecycle/events",
        },
    }
