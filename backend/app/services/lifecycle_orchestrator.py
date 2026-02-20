"""
24-Hour Building Lifecycle Orchestrator

Simulates a complete building day with:
- AI optimization adjustments
- Equipment degradation and faults
- Alert generation and Sentry notifications
- Technician dispatch and repair
- Service feedback and health restoration

Time compression: 24 hours → configurable (default 24 minutes)
"""

import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum

from app.database.repositories.equipment_repository import EquipmentRepository
from app.database.repositories.prediction_repository import PredictionRepository
from app.database.repositories.work_order_repository import get_work_order_repository
from app.database.repositories.recommendation_repository import (
    get_recommendation_repository,
)
from app.services.feedback_collection_service import (
    get_feedback_collection_service,
    FeedbackItemType,
)
from app.services.device_control_service import get_device_control_service
from app.services.seasonal_modeler import SeasonalModeler
from app.services.thermal_simulation_engine import update_simulation_temperatures
from app.services.building_schedule import (
    BuildingSchedule,
    BuildingState,
    HVACMode,
    ScheduleState,
)

from app.services.power_meter_validation_engine import get_power_meter_validation_engine
from app.services.cost_validation_engine import get_cost_validation_engine
from app.services.simulation_persistence import get_simulation_persistence
from app.models.recommendation import (
    Recommendation,
    RecommendationStatus,
    ActionRiskLevel,
)

logger = logging.getLogger(__name__)


class SimulatedHour(int, Enum):
    """Hours of the simulated day."""

    MIDNIGHT = 0
    EARLY_MORNING = 6
    MORNING_START = 8
    MID_MORNING = 10
    NOON = 12
    AFTERNOON = 14
    LATE_AFTERNOON = 16
    EVENING = 18
    NIGHT = 22


class EventType(str, Enum):
    """Types of lifecycle events."""

    BUILDING_WAKE = "building_wake"
    OCCUPANCY_INCREASE = "occupancy_increase"
    PEAK_LOAD = "peak_load"
    EQUIPMENT_FAULT = "equipment_fault"
    ALERT_GENERATED = "alert_generated"
    WORK_ORDER_CREATED = "work_order_created"
    TECHNICIAN_DISPATCHED = "technician_dispatched"
    REPAIR_COMPLETED = "repair_completed"
    FEEDBACK_SUBMITTED = "feedback_submitted"
    HEALTH_RESTORED = "health_restored"
    ALERT_RESOLVED = "alert_resolved"
    OCCUPANCY_DECREASE = "occupancy_decrease"
    NIGHT_MODE = "night_mode"
    AI_OPTIMIZATION = "ai_optimization"
    SETPOINT_CHANGE = "setpoint_change"


class OperationMode(str, Enum):
    """Building operation modes for comparison."""

    HVAC_ONLY = "hvac_only"
    HVAC_DALI = "hvac_dali"
    HVAC_DALI_SENTINEL = "hvac_dali_sentinel"
    SOLAR_BESS_BASELINE = "solar_bess_baseline"
    SOLAR_BESS_SENTINEL = "solar_bess_sentinel"


@dataclass
class LifecycleEvent:
    """A single event in the building lifecycle."""

    timestamp: datetime
    simulated_hour: int
    event_type: EventType
    equipment_id: Optional[str] = None
    equipment_name: Optional[str] = None
    description: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    success: bool = True


@dataclass
class ScenarioConfig:
    """Configuration for a simulation scenario."""

    name: str
    description: str
    fault_probability: float = 0.3  # 30% chance of fault during day
    fault_hour: Optional[int] = None  # Specific hour for fault (None = random)
    fault_equipment_type: Optional[str] = None  # Specific type to fault
    auto_repair: bool = True  # Automatically simulate technician repair
    repair_delay_hours: int = 2  # Hours after fault before repair
    optimization_enabled: bool = True
    sentry_notifications: bool = True
    operation_mode: Optional[OperationMode] = None
    # Enable continuous AI recommendations (lower thresholds, BESS arbitrage)
    # and building operation mode for demos
    demo_mode: bool = False


# Predefined scenarios
SCENARIOS = {
    "normal_day": ScenarioConfig(
        name="Normal Day",
        description="Typical building operations with no major issues",
        fault_probability=0.1,
        auto_repair=True,
    ),
    "fault_day": ScenarioConfig(
        name="Fault Day",
        description="A day with equipment fault, alert, repair cycle",
        fault_probability=1.0,
        fault_hour=11,  # Fault at 11am during peak
        auto_repair=True,
        repair_delay_hours=2,
    ),
    "chiller_failure": ScenarioConfig(
        name="Chiller Failure",
        description="Chiller develops fault requiring urgent repair",
        fault_probability=1.0,
        fault_hour=10,
        fault_equipment_type="chiller",
        auto_repair=True,
        repair_delay_hours=3,
    ),
    "multi_fault": ScenarioConfig(
        name="Multiple Faults",
        description="Stressful day with multiple equipment issues",
        fault_probability=1.0,
        fault_hour=9,
        auto_repair=True,
        repair_delay_hours=1,
    ),
    "maintenance_day": ScenarioConfig(
        name="Maintenance Day",
        description="Scheduled maintenance with controlled downtime",
        fault_probability=0.0,
        auto_repair=False,
        optimization_enabled=True,
    ),
    "grant_hvac_only_7day": ScenarioConfig(
        name="Grant Demo: HVAC Only (7 days)",
        description="7-day HVAC baseline for Grant demo - AC runs all day",
        operation_mode=OperationMode.HVAC_ONLY,
        fault_probability=0.0,
        optimization_enabled=False,
    ),
    "grant_hvac_dali_7day": ScenarioConfig(
        name="Grant Demo: HVAC + DALI (7 days)",
        description="7-day reactive occupancy control for Grant demo",
        operation_mode=OperationMode.HVAC_DALI,
        fault_probability=0.0,
        optimization_enabled=False,
    ),
    "grant_hvac_dali_ai_7day": ScenarioConfig(
        name="Grant Demo: HVAC + DALI + Sentinel AI (7 days)",
        description="7-day predictive AI control for Grant demo",
        operation_mode=OperationMode.HVAC_DALI_SENTINEL,
        fault_probability=0.0,
        optimization_enabled=True,
    ),
    "solar_bess_baseline_7day": ScenarioConfig(
        name="Solar + BESS: Baseline (7 days)",
        description="7-day building with 40kWp solar + 50kWh battery, reactive control",
        operation_mode=OperationMode.SOLAR_BESS_BASELINE,
        fault_probability=0.0,
        optimization_enabled=False,
    ),
    "solar_bess_sentinel_7day": ScenarioConfig(
        name="Solar + BESS: Sentinel AI (7 days)",
        description="7-day building with solar + BESS + Sentinel AI optimization",
        operation_mode=OperationMode.SOLAR_BESS_SENTINEL,
        fault_probability=0.0,
        optimization_enabled=True,
    ),
    "grant_hvac_dali_ai_annual": ScenarioConfig(
        name="Grant Demo: HVAC + DALI + Sentinel AI (365 days)",
        description=(
            "Full-year simulation with South African seasonal variations - "
            "temperature cycles, rainfall patterns, occupancy variations, "
            "and seasonal fault probabilities"
        ),
        operation_mode=OperationMode.HVAC_DALI_SENTINEL,
        fault_probability=0.05,
        auto_repair=True,
        repair_delay_hours=4,
        optimization_enabled=True,
        demo_mode=True,  # Enable continuous AI recommendations for demo (lower thresholds, BESS arbitrage)
    ),
    "grant_solar_bess_ai_annual": ScenarioConfig(
        name="Grant Demo: Solar + BESS + Sentinel AI (365 days)",
        description=(
            "Full-year simulation with 3.9 MWp solar + 5 MWh BESS, "
            "City Power TOU arbitrage, demand management, "
            "and South African seasonal variations"
        ),
        operation_mode=OperationMode.SOLAR_BESS_SENTINEL,
        fault_probability=0.03,
        auto_repair=True,
        repair_delay_hours=6,
        optimization_enabled=True,
        demo_mode=True,  # Enable continuous AI recommendations for demo
    ),
}


class LifecycleOrchestrator:
    """
    Orchestrates a 24-hour building simulation.

    Integrates health simulation, work order automation, AI optimization,
    and multi-day seasonal patterns into a unified lifecycle loop.
    """

    def __init__(self, task_id: Optional[str] = None, site_id: str = "site-002"):
        self.task_id = task_id  # For database task tracking
        self.site_id = site_id  # Parameterized site identifier
        self.building_id = site_id  # Used by update_simulation_temperatures
        self.running = False
        self.paused = False
        self.current_scenario: Optional[ScenarioConfig] = None
        self.simulated_time: datetime = datetime.now().replace(hour=0, minute=0, second=0)
        self.real_start_time: Optional[datetime] = None
        self.time_multiplier: float = 60.0  # 1 real minute = 1 simulated hour
        self.speed_multiplier: float = 1.0  # 1x real-time, 10x = 10x faster, etc.
        self.events: List[LifecycleEvent] = []
        self.active_faults: Dict[str, Dict[str, Any]] = {}
        self.pending_repairs: Dict[str, Dict[str, Any]] = {}
        self.equipment_repo = EquipmentRepository()
        self.prediction_repo = PredictionRepository()
        self.work_order_repo = get_work_order_repository()
        self.feedback_service = get_feedback_collection_service()
        self.recommendation_repo = get_recommendation_repository()
        self.device_control_service = get_device_control_service()
        self._task: Optional[asyncio.Task] = None
        self._callbacks: List[Callable[[LifecycleEvent], None]] = []

        # Energy tracking
        self.total_energy_kwh: float = 0.0  # Cumulative energy consumption
        self.current_hour_power_kw: float = 0.0  # Current hour's power in kW
        self.days_simulated: int = 0  # Track days for progresscible but realistic variation
        # Same scenario always produces same results, but with day-to-day variation
        self._scenario_rng = random.Random()
        self._occupancy_seed: Optional[int] = None

        # Seasonal modeler for annual simulations
        self.seasonal_modeler: Optional[SeasonalModeler] = None
        self.days_simulated: int = 0  # Track days for annual simulations

        # Building schedule engine for time-of-day operating states
        self.building_schedule = BuildingSchedule()

        # JHB climate engine for realistic ambient temperature (104-01)
        # Lazy-import ClimatePattern to avoid bms_simulator/__init__.py which
        # triggers pandas import via the full simulator chain
        self.climate_engine = None
        try:
            import importlib.util
            import os

            spec = importlib.util.spec_from_file_location(
                "climate_pattern",
                os.path.join(os.path.dirname(__file__), "bms_simulator", "patterns", "climate.py"),
            )
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                self.climate_engine = mod.ClimatePattern(climate_zone="johannesburg")
        except Exception:
            pass  # Fall back to seasonal modeler

        # Supabase persistence for dashboard visibility (104-02)
        self.persistence = get_simulation_persistence(site_id=site_id)

    def reset(self):
        """Reset orchestrator state for a fresh demo.

        Clears all simulation state so the next start() call begins fresh.
        Called when a user logs in to ensure demo restarts clean each time.
        """
        self.running = False
        self.paused = False
        self.current_scenario = None
        self.simulated_time = datetime.now().replace(hour=0, minute=0, second=0)
        self.real_start_time = None
        self.time_multiplier = 60.0
        self.speed_multiplier = 1.0
        self.events = []
        self.active_faults = {}
        self.pending_repairs = {}
        self._task = None
        self._scenario_rng = random.Random()
        self._occupancy_seed = None
        self.seasonal_modeler = None
        self.days_simulated = 0
        logger.info("Orchestrator reset: Ready for fresh demo")

    @property
    def seconds_per_simulated_hour(self) -> float:
        """Real seconds to wait between each simulated hour.

        At 1x speed: 60 seconds per simulated hour (24h sim takes 24 minutes).
        At 10x speed: 6 seconds per simulated hour (24h sim takes 2.4 minutes).
        At 100x speed: 0.6 seconds per simulated hour (24h sim takes 14.4 seconds).
        At 1000x speed: 0.06 seconds per simulated hour (24h sim takes 1.4 seconds).
        """
        base_seconds = 60.0  # 1 minute per simulated hour at 1x
        return max(0.05, base_seconds / self.speed_multiplier)

    def set_speed(self, speed_multiplier: float) -> Dict[str, Any]:
        """Change simulation speed while running.

        Args:
            speed_multiplier: New speed multiplier (0.1 to 10000).

        Returns:
            Dict with new speed and seconds_per_hour.
        """
        old_speed = self.speed_multiplier
        self.speed_multiplier = max(0.1, min(10000, speed_multiplier))
        logger.info(
            f"Speed changed: {old_speed}x -> {self.speed_multiplier}x "
            f"({self.seconds_per_simulated_hour:.2f}s per simulated hour)"
        )
        return {
            "speed": self.speed_multiplier,
            "seconds_per_hour": self.seconds_per_simulated_hour,
        }

    def add_event_callback(self, callback: Callable[[LifecycleEvent], None]):
        """Add callback to be notified of events."""
        self._callbacks.append(callback)

    def _emit_event(self, event: LifecycleEvent):
        """Emit event to all callbacks."""
        self.events.append(event)
        logger.info(f"[{event.simulated_hour:02d}:00] {event.event_type.value}: {event.description}")
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Event callback error: {e}")

    async def start(
        self,
        scenario: str = "normal_day",
        duration_minutes: float = 24.0,
        start_hour: int = 0,
        task_id: str = None,  # For checkpoint recovery
        speed_multiplier: float = 10.0,
        start_date: Optional[str] = None,  # ISO date string e.g. "2025-06-15"
    ) -> Dict[str, Any]:
        """
        Start the 24-hour simulation.

        Args:
            scenario: Scenario name from SCENARIOS
            duration_minutes: Real-time duration (24 = 1 min per hour)
            start_hour: Simulated hour to start (0-23)
            task_id: Optional task_id for checkpoint recovery
            speed_multiplier: Speed factor (1x=real-time, 10x=10x faster, etc.)
            start_date: Optional ISO date string for simulation start date

        Returns:
            Status dict with session info
        """
        # FIRST: Check for existing checkpoint to recover from
        checkpoint = None
        if task_id and scenario == "grant_hvac_dali_ai_annual":
            try:
                from app.database.supabase_client import get_supabase_client

                supabase = get_supabase_client()
                response = (
                    supabase.table("lifecycle_simulation_tasks")
                    .select("state_snapshot")
                    .eq("task_id", task_id)
                    .execute()
                )
                if response.data and response.data[0].get("state_snapshot"):
                    checkpoint = response.data[0]["state_snapshot"]
                    day = checkpoint.get("days_simulated", 0)
                    logger.info(f"✅ Found checkpoint for task {task_id}, recovering from day {day}/365")
            except Exception as e:
                logger.warning(f"Could not load checkpoint: {e}")

        # If already running, only allow if we have a checkpoint to recover (fresh start, not overlay)
        if self.running and not checkpoint:
            return {"success": False, "error": "Simulation already running"}

        # Get scenario config
        self.current_scenario = SCENARIOS.get(scenario, SCENARIOS["fault_day"])

        # Initialize seeded random for reproducible occupancy variation
        # Hash scenario name to get consistent seed for same demo
        self._occupancy_seed = hash(scenario) % (2**32)
        self._scenario_rng.seed(self._occupancy_seed)
        logger.info(f"Seeded occupancy randomness for scenario '{scenario}' (seed={self._occupancy_seed})")

        # Check if this is an annual scenario (365-day simulations have "annual" in name)
        is_annual = "annual" in scenario.lower()

        # Set speed multiplier for new speed control system
        self.speed_multiplier = max(0.1, min(10000, speed_multiplier))

        # RECOVERY PATH: If we have a checkpoint, restore ALL state BEFORE starting loop
        if checkpoint and is_annual:
            logger.info("🔄 RECOVERY PATH: Restoring checkpoint state...")
            self.simulated_time = datetime.fromisoformat(checkpoint.get("simulated_time", datetime.now().isoformat()))
            self.days_simulated = checkpoint.get("days_simulated", 0)
            self.time_multiplier = checkpoint.get("time_multiplier", 60.0)
            self.active_faults = checkpoint.get("active_faults", {})
            self.pending_repairs = checkpoint.get("pending_repairs", {})
            self.events = checkpoint.get("events", [])

            # Restore seasonal modeler for annual sims
            if self.days_simulated > 0:
                self.seasonal_modeler = SeasonalModeler(seed=self._occupancy_seed)
                time_str = self.simulated_time.strftime("%Y-%m-%d %H:%M")
                logger.info(f"✅ Restored checkpoint: day {self.days_simulated}/365, time={time_str}")

            self.real_start_time = datetime.now()
            self.running = True
            self.paused = False

            # Start loop directly with restored state (NO fresh init)
            self._task = asyncio.create_task(self._run_simulation())
            return {
                "success": True,
                "scenario": self.current_scenario.name,
                "recovered_from_checkpoint": True,
                "days_simulated": self.days_simulated,
                "started_at": self.real_start_time.isoformat(),
            }

        # FRESH START PATH: Initialize fresh (no checkpoint)
        if is_annual:
            # Annual simulation: 365 days × 24 hours = 8760 hours total
            self.seasonal_modeler = SeasonalModeler(seed=self._occupancy_seed)
            self.days_simulated = 0
            # Calculate time multiplier for 365-day simulation
            # duration_minutes = real time in minutes (e.g., 120 min = 2 hours)
            # total_hours = 365 * 24 = 8760 simulated hours
            # Each simulated hour takes: (duration_minutes * 60) / 8760 seconds
            total_hours_annual = 365 * 24
            self.time_multiplier = (duration_minutes * 60.0) / total_hours_annual  # seconds per simulated hour
            # Start date: use provided date or default to January 1st
            if start_date:
                self.simulated_time = datetime.fromisoformat(start_date).replace(hour=start_hour, minute=0, second=0)
            else:
                self.simulated_time = datetime(2024, 1, 1, start_hour, 0, 0)
            time_mult = f"{self.time_multiplier:.3f}"
            speed_str = f"{self.speed_multiplier}x"
            logger.info(
                f"Annual simulation initialized: {speed_str} speed, {duration_minutes} min for full year "
                f"(365 days), {time_mult}s per hour, {self.seconds_per_simulated_hour:.2f}s effective"
            )
        else:
            # Daily simulation: just 24 hours
            self.seasonal_modeler = None
            # Calculate time multiplier for 24-hour simulation
            # duration_minutes for full 24 hours
            # Each simulated hour takes: (duration_minutes * 60) / 24 seconds
            self.time_multiplier = (duration_minutes * 60.0) / 24.0  # seconds per simulated hour
            # Start date: use provided date or default to today
            if start_date:
                self.simulated_time = datetime.fromisoformat(start_date).replace(hour=start_hour, minute=0, second=0)
            else:
                self.simulated_time = datetime.now().replace(hour=start_hour, minute=0, second=0, microsecond=0)

        self.real_start_time = datetime.now()
        self.events = []
        self.active_faults = {}
        self.pending_repairs = {}
        self.running = True
        self.paused = False

        logger.info(
            f"Starting lifecycle simulation: {self.current_scenario.name}, "
            f"speed={self.speed_multiplier}x, start_hour={start_hour}, "
            f"seconds_per_hour={self.seconds_per_simulated_hour:.2f}s"
        )

        # Start background task
        self._task = asyncio.create_task(self._run_simulation())

        return {
            "success": True,
            "scenario": self.current_scenario.name,
            "speed_multiplier": self.speed_multiplier,
            "seconds_per_simulated_hour": self.seconds_per_simulated_hour,
            "duration_minutes": duration_minutes,
            "time_multiplier_seconds_per_hour": self.time_multiplier,
            "start_hour": start_hour,
            "started_at": self.real_start_time.isoformat(),
        }

    async def stop(self) -> Dict[str, Any]:
        """Stop the simulation."""
        if not self.running:
            return {"success": False, "error": "Simulation not running"}

        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        return {"success": True, "events_generated": len(self.events), "stopped_at": datetime.now().isoformat()}

    def pause(self):
        """Pause the simulation."""

    def get_status(self) -> Dict[str, Any]:
        """Get current simulation status including weather and seasonal data."""
        elapsed_real = (datetime.now() - self.real_start_time).total_seconds() if self.real_start_time else 0

        # Calculate progress percentage
        total_iterations = 8760 if self.seasonal_modeler is not None else 24
        progress_percent = int((self.days_simulated * 24 / total_iterations) * 100) if total_iterations > 0 else 0

        # Get seasonal/weather data if available
        current_season = ""
        is_raining = False
        cloud_cover = 0
        ambient_temp = 22.0
        solar_efficiency = 100.0

        # Use JHB climate engine for ambient temp if available
        if self.climate_engine and self.running:
            current_hour = self.simulated_time.hour
            day_of_year = self.simulated_time.timetuple().tm_yday
            ambient_temp = self.climate_engine.get_temperature(day_of_year, current_hour)

        if self.seasonal_modeler:
            current_date = self.simulated_time.date()
            current_season = self.seasonal_modeler.get_season_name(current_date)
            current_hour = self.simulated_time.hour

            # Get weather data using individual SeasonalModeler methods
            is_raining = self.seasonal_modeler.should_rain_today(current_date)
            cloud_cover = self.seasonal_modeler.get_cloud_cover_percent(current_date)
            # Only use seasonal modeler for temp if climate engine not available
            if not self.climate_engine:
                ambient_temp = self.seasonal_modeler.get_ambient_temperature(current_date, current_hour, is_raining)

            # Calculate solar efficiency based on time and weather
            if 6 <= current_hour < 18:  # Daytime
                base_efficiency = 100 - (cloud_cover * 0.8)
                if is_raining:
                    base_efficiency *= 0.3  # Rain reduces efficiency significantly
                solar_efficiency = max(10, base_efficiency)
            else:
                solar_efficiency = 0

        return {
            "running": self.running,
            "paused": self.paused,
            "scenario": self.current_scenario.name if self.current_scenario else None,
            "simulated_time": self.simulated_time.strftime("%H:%M") if self.running else None,
            "simulated_hour": self.simulated_time.hour if self.running else None,
            "real_elapsed_seconds": round(elapsed_real, 1),
            "events_count": len(self.events),
            "active_faults": len(self.active_faults),
            "pending_repairs": len(self.pending_repairs),
            "progress_percent": progress_percent,
            "is_raining": is_raining,
            "cloud_cover": cloud_cover,
            "ambient_temp": ambient_temp,
            "humidity": getattr(self, "current_humidity", 50.0),
            "solar_efficiency": solar_efficiency,
            "current_season": current_season,
            "occupancy_percent": self._calculate_occupancy(self.simulated_time.hour if self.simulated_time else 0),
            "total_energy_kwh": round(self.total_energy_kwh, 1),
            "current_hour_power_kw": round(self.current_hour_power_kw, 2),
            "recent_events": [
                {
                    "hour": e.simulated_hour,
                    "type": e.event_type.value,
                    "description": e.description,
                    "equipment": e.equipment_name,
                }
                for e in self.events[-10:]
            ],
        }

    async def _run_simulation(self):
        """Main simulation loop - Advances hour-by-hour for entire 365-day year."""
        try:
            is_annual = self.seasonal_modeler is not None
            time_mult_str = f"{self.time_multiplier:.3f}"
            logger.warning(
                f"[SIMULATION START] task_id={self.task_id}, is_annual={is_annual}, "
                f"days={self.days_simulated}, time_mult={time_mult_str}s/hour"
            )

            is_annual = self.seasonal_modeler is not None
            total_iterations = (365 * 24) if is_annual else 24  # Hours: 8760 for annual, 24 for daily
            iteration = 0
            last_checkpoint_hour = -1  # Track checkpoint saves

            # Persistent loop: Run 365 days, then restart (loops until manually stopped)
            cycle_num = 1
            while self.running:
                iteration += 1
                current_hour = self.simulated_time.hour

                # Log progress periodically
                if iteration <= 10 or iteration % 100 == 0:
                    day_num = self.days_simulated + 1
                    logger.warning(
                        f"[SIMULATION CYCLE {cycle_num}] Hour {iteration}/{total_iterations} "
                        f"(day={day_num}, hour={current_hour:02d}:00)"
                    )

                try:
                    # Pause support: hold on same hour
                    if self.paused:
                        await asyncio.sleep(0.1)
                        continue

                    # Process events for this hour
                    await self._process_hour(current_hour)

                    # Save checkpoint every 6 simulated hours for crash recovery
                    if is_annual and (current_hour % 6 == 0):
                        if current_hour != last_checkpoint_hour:
                            await self.save_checkpoint()
                            last_checkpoint_hour = current_hour

                    # Advance time by 1 hour
                    self.simulated_time += timedelta(hours=1)

                    # Track day transitions (every 24 hours)
                    if iteration > 0 and (iteration % 24) == 0:  # Every 24 hours = 1 day
                        self.days_simulated += 1
                        if is_annual:
                            progress = int((self.days_simulated / 365) * 100)
                            logger.warning(f"[DAY COMPLETE] Day {self.days_simulated}/365, progress={progress}%")
                            # Update database with progress every day
                            await self._update_progress_to_db(iteration, total_iterations)

                    # Sleep for the calculated time per simulated hour
                    await asyncio.sleep(self.seconds_per_simulated_hour)

                except asyncio.CancelledError:
                    logger.warning(f"[CANCELLED] iteration={iteration}, task was cancelled")
                    raise
                except Exception as e:
                    logger.error(f"[ERROR in iteration {iteration}] {type(e).__name__}: {e}", exc_info=True)
                    raise

                # Check if completed 365 days (one full cycle)
                if iteration >= total_iterations:
                    days = self.days_simulated
                    logger.warning(f"[CYCLE {cycle_num} COMPLETE] Completed {days} days. Resetting for next cycle...")
                    # Reset for next cycle
                    iteration = 0
                    self.days_simulated = 0
                    self.simulated_time = datetime(2024, 1, 1, 0, 0, 0)  # Reset to Jan 1
                    cycle_num += 1
                    last_checkpoint_hour = -1
                    logger.warning(f"[CYCLE {cycle_num} START] Beginning persistent loop cycle {cycle_num}")

            logger.warning(f"[SIMULATION STOPPED] Completed {cycle_num - 1} full cycles, last iteration={iteration}")
            self.running = False

        except asyncio.CancelledError:
            logger.info("Simulation cancelled")
        except Exception as e:
            logger.error(f"Simulation error: {e}", exc_info=True)
            self.running = False

    async def _update_progress_to_db(self, iteration: int, total_iterations: int) -> None:
        """Update database with simulation progress (called every simulated day)."""
        if not self.task_id:
            return  # No task_id means running standalone, not in background scheduler

        try:
            from app.database.supabase_client import get_supabase_client

            supabase = get_supabase_client()
            progress_pct = int((iteration / total_iterations) * 100)

            supabase.table("lifecycle_simulation_tasks").update(
                {
                    "progress_pct": progress_pct,
                    "days_completed": self.days_simulated,
                }
            ).eq("task_id", self.task_id).execute()

            logger.debug(f"Updated task {self.task_id}: {progress_pct}% progress, {self.days_simulated} days")
        except Exception as e:
            logger.warning(f"Failed to update progress for task {self.task_id}: {e}")

            logger.error(f"Simulation error: {e}", exc_info=True)
            self.running = False

    async def _process_hour(self, hour: int):
        """Process a simulated hour using the building schedule engine.

        Equipment behavior (chiller staging, AHU fan speed, VAV damper positions,
        FCU valve positions, DALI lighting levels) is keyed off schedule state +
        occupancy + ambient temperature rather than hardcoded hour checks.
        """
        day_of_week = self.simulated_time.weekday()
        schedule_state = self.building_schedule.get_state(hour, day_of_week)

        logger.info(
            f"[Hour {hour:02d}:00] Day {self.days_simulated + 1} "
            f"| {schedule_state.state.value} | HVAC: {schedule_state.hvac_mode.value} "
            f"| Occupancy: {schedule_state.target_occupancy_pct:.0f}%"
        )

        # Emit schedule transition events
        await self._emit_schedule_event(hour, schedule_state)

        # Midnight: daily summary for annual simulations
        if hour == 0 and self.seasonal_modeler:
            season = self.seasonal_modeler.get_season_name(self.simulated_time.date())
            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=0,
                    event_type=EventType.BUILDING_WAKE,
                    description=f"Day {self.days_simulated + 1}: {season.capitalize()} - Building daily cycle begins",
                    details={
                        "day_of_year": self.days_simulated + 1,
                        "season": season,
                        "month": self.simulated_time.strftime("%B"),
                    },
                )
            )

        # === FAULT INJECTION (scenario-driven) ===
        if self.current_scenario and self.current_scenario.fault_probability > 0:
            if self.current_scenario.fault_hour == hour:
                await self._inject_fault()
            elif self.current_scenario.fault_hour is None:
                # Random fault based on probability (spread across 24 hours)
                if self._scenario_rng.random() < (self.current_scenario.fault_probability / 24):
                    await self._inject_fault()

        # === PENDING REPAIRS CHECK ===
        if self.active_faults:
            await self._check_pending_repairs()

        # === THERMAL UPDATE ===
        ambient_temp = 20.0  # Default, updated below
        occupancy_data = {}
        try:
            occupancy_data = self._generate_occupancy_for_hour(hour)

            # Get ambient temperature from JHB climate engine (preferred)
            # or fall back to seasonal modeler for backward compatibility
            if self.climate_engine:
                day_of_year = self.simulated_time.timetuple().tm_yday
                ambient_temp = self.climate_engine.get_temperature(day_of_year, hour)
                self.current_humidity = self.climate_engine.get_humidity(day_of_year, hour)
            elif self.seasonal_modeler:
                is_raining = self.seasonal_modeler.should_rain_today(self.simulated_time.date())
                ambient_temp = self.seasonal_modeler.get_ambient_temperature(
                    self.simulated_time.date(), self.simulated_time.hour, is_raining
                )
                self.current_humidity = 50.0  # Default when no climate engine
            else:
                ambient_temp = 20.0
                self.current_humidity = 50.0

            # Use schedule state for equipment health consideration
            consider_health = bool(self.active_faults) or (
                self.current_scenario is not None and self.current_scenario.fault_probability >= 0.5
            )

            is_night_mode = schedule_state.hvac_mode in (HVACMode.OFF, HVACMode.NIGHT_SETBACK)

            await update_simulation_temperatures(
                building_id=self.building_id,
                simulated_hour=hour,
                occupancy_data=occupancy_data,
                ambient_temp=ambient_temp,
                is_night_mode=is_night_mode,
                consider_equipment_health=consider_health,
                simulated_date=self.simulated_time,
            )
        except Exception as e:
            logger.warning(f"[THERMAL] Failed to update temperatures at hour {hour}: {e}")
            occupancy_data = {}

        # === ENERGY CONSUMPTION TRACKING (schedule-driven) ===
        # Power consumption based on equipment staging, not flat 20-35kW
        base_power = self._calculate_hourly_power(schedule_state, occupancy_data)
        self.current_hour_power_kw = base_power
        self.total_energy_kwh += base_power

        # === POWER METER VALIDATION (A.3) ===
        try:
            power_engine = get_power_meter_validation_engine("S002")
            result = await power_engine.validate_hourly_power(
                meter_id="S002-MTR-B1-HVAC",
                reading_kwh=base_power,
                simulated_hour=hour,
                simulated_date=self.simulated_time,
            )
            if result.get("anomaly_detected"):
                logger.warning(f"[POWER VALIDATION] Anomaly at {hour}: {result.get('reason')}")
        except Exception as e:
            logger.debug(f"[POWER VALIDATION] Skipped: {e}")

        # === COST VALIDATION (A.4) ===
        if hour == 23:
            try:
                cost_engine = get_cost_validation_engine("S002")
                result = await cost_engine.validate_monthly_cost(
                    invoice_period_start=self.simulated_time.replace(day=1),
                    invoice_period_end=self.simulated_time,
                    real_cost_r=None,
                )
                if result.get("variance_pct", 0) > 5:
                    logger.warning(f"[COST VALIDATION] Variance > 5%: {result.get('variance_pct')}%")
            except Exception as e:
                logger.debug(f"[COST VALIDATION] Skipped: {e}")

        # AI optimization runs when the building is occupied (HVAC active)
        if schedule_state.hvac_mode != HVACMode.OFF:
            await self._ai_optimization(f"hour_{hour}")

        # === PERSIST STATE TO SUPABASE (104-02) ===
        # Write equipment health, sensor readings, and energy to Supabase
        # so existing dashboards show live building operation
        try:
            equipment_states = await self._collect_equipment_states(hour, schedule_state)
            await self.persistence.persist_hourly_state(
                simulated_time=self.simulated_time,
                equipment_states=equipment_states,
                schedule_state=schedule_state,
                energy_kw=self.current_hour_power_kw,
                ambient_temp=ambient_temp,
                humidity=getattr(self, "current_humidity", 50.0),
            )
        except Exception as e:
            logger.warning(f"[PERSISTENCE] Failed to persist hourly state: {e}")

    async def _emit_schedule_event(self, hour: int, schedule_state: ScheduleState):
        """Emit events on meaningful schedule transitions."""
        event_map = {
            BuildingState.PRE_COOL: (
                EventType.BUILDING_WAKE,
                "Pre-cool cycle started -- pulling overnight heat from zones",
            ),
            BuildingState.MORNING_STARTUP: (
                EventType.BUILDING_WAKE,
                "Full plant online -- chillers staged, AHUs at design speed",
            ),
            BuildingState.OCCUPIED_RAMPUP: (
                EventType.OCCUPANCY_INCREASE,
                "Staff arriving -- occupancy ramping, HVAC at full capacity",
            ),
            BuildingState.AFTERNOON_WINDDOWN: (
                EventType.OCCUPANCY_DECREASE,
                "Staff leaving -- HVAC de-staging",
            ),
            BuildingState.HVAC_SHUTDOWN: (
                EventType.NIGHT_MODE,
                "HVAC shutdown -- building coasting on thermal mass",
            ),
            BuildingState.UNOCCUPIED: (
                EventType.NIGHT_MODE,
                "Building empty -- security mode activated",
            ),
        }
        mapping = event_map.get(schedule_state.state)
        if mapping:
            event_type, description = mapping
            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=hour,
                    event_type=event_type,
                    description=description,
                    details={
                        "schedule_state": schedule_state.state.value,
                        "hvac_mode": schedule_state.hvac_mode.value,
                        "chiller": schedule_state.chiller_staging.value,
                        "occupancy_target": schedule_state.target_occupancy_pct,
                    },
                )
            )

    def _calculate_hourly_power(self, schedule_state: ScheduleState, occupancy_data: Dict[str, float]) -> float:
        """Calculate realistic hourly power based on equipment staging.

        Args:
            schedule_state: Current building schedule state
            occupancy_data: Zone occupancy percentages

        Returns:
            Power consumption in kW for this hour
        """
        # Base loads (always-on: UPS, security, lifts, IT)
        base_kw = 8.0

        # HVAC power based on chiller staging
        hvac_kw = {
            "off": 0.0,
            "stage_1": 25.0,  # ~30% chiller + AHU
            "stage_2": 55.0,  # ~60% chiller + AHU + pumps
            "full_load": 85.0,  # Full cooling plant
        }.get(schedule_state.chiller_staging.value, 0.0)

        # AHU fan power (proportional to fan %)
        ahu_kw = (schedule_state.ahu_fan_pct / 100.0) * 15.0  # 15kW at 100%

        # Lighting power based on mode
        lighting_kw = {
            "off": 0.0,
            "security_only": 2.0,
            "dimmed": 5.0,
            "full": 12.0,
            "daylight_harvest": 8.0,
        }.get(schedule_state.lighting_mode.value, 0.0)

        # Occupancy-driven misc loads (computers, appliances)
        if occupancy_data:
            avg_occupancy = sum(occupancy_data.values()) / len(occupancy_data)
        else:
            avg_occupancy = schedule_state.target_occupancy_pct
        misc_kw = (avg_occupancy / 100.0) * 20.0  # 20kW at full occupancy

        total = base_kw + hvac_kw + ahu_kw + lighting_kw + misc_kw
        # Add +/-5% noise for realism
        noise = self._scenario_rng.uniform(0.95, 1.05)
        return round(total * noise, 1)

    def _generate_occupancy_for_hour(self, hour: int) -> Dict[str, float]:
        """
        Generate zone occupancy percentages for all zones based on hour of day.

        Returns:
            Dictionary mapping zone_id -> occupancy_percent (0-100)
        """
        from app.api.dali import calculate_zone_occupancy

        # Get day-of-week info
        day_of_week = self.simulated_time.weekday()  # 0=Monday, 6=Sunday
        is_weekend = day_of_week >= 5

        # Site 002 actual zone IDs and their typical occupancy patterns
        zone_profiles = {
            "Zone-B1-001": "utility",  # Basement plant room
            "Zone-L1-A": "office",  # Level 1 Zone A
            "Zone-L1-B": "office",  # Level 1 Zone B
            "Zone-L2-A": "office",  # Level 2 Zone A
            "Zone-L2-B": "office",  # Level 2 Zone B
        }

        occupancy_data = {}

        for zone_id, zone_type in zone_profiles.items():
            # Calculate occupancy using existing dali logic
            occupancy_pct = calculate_zone_occupancy(
                hour=hour, day_of_week=day_of_week, is_weekend=is_weekend, zone_type=zone_type
            )

            # Apply seasonal variation if in annual simulation
            if self.seasonal_modeler:
                seasonal_factor = self._get_seasonal_occupancy_factor(hour)
                occupancy_pct *= seasonal_factor

            # Add small random variation for realism (±5%)
            variance = self._scenario_rng.uniform(0.95, 1.05)
            occupancy_pct *= variance

            # Clamp to 0-100%
            occupancy_data[zone_id] = max(0.0, min(100.0, occupancy_pct))

        return occupancy_data

    async def _building_wake(self):
        """Simulate building morning startup."""
        self._emit_event(
            LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=6,
                event_type=EventType.BUILDING_WAKE,
                description="Building systems starting up for the day",
                details={"hvac_mode": "pre_cooling", "lighting": "minimal"},
            )
        )

        # AI optimization handled by hourly check in _process_hour

    async def _occupancy_increase(self):
        """Simulate morning occupancy increase with realistic day-to-day variation."""
        # Day-of-week variation (Monday=100%, Friday=80%, realistic WFH/hybrid patterns)
        day_of_week = self.simulated_time.weekday()  # 0=Monday, 6=Sunday
        day_factor = [1.0, 0.95, 0.90, 0.88, 0.80, 0.3, 0.2][day_of_week]  # Mon-Sun

        # Seeded random variation (±10% reproducible)
        occupancy_variance = self._scenario_rng.uniform(0.90, 1.10)
        occupancy_percent = int(60 * day_factor * occupancy_variance)

        # Apply seasonal occupancy factor if in annual simulation
        if self.seasonal_modeler:
            seasonal_factor = self._get_seasonal_occupancy_factor(8)
            occupancy_percent = int(occupancy_percent * seasonal_factor)

        zones_active = max(2, int(12 * day_factor * occupancy_variance / 100) * 100 // 100)

        self._emit_event(
            LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=8,
                event_type=EventType.OCCUPANCY_INCREASE,
                description=f"Occupancy increasing - staff arriving (~{occupancy_percent}%)",
                details={"occupancy_percent": occupancy_percent, "zones_active": zones_active},
            )
        )

        # Adjust setpoints for occupancy
        await self._setpoint_change("cooling_setpoint", 22.0, "Occupied mode")
        await self._setpoint_change("lighting_level", int(80 * day_factor), "Occupied mode")

    async def _peak_load(self):
        """Simulate peak load period."""
        self._emit_event(
            LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=11,
                event_type=EventType.PEAK_LOAD,
                description="Peak cooling load - maximum demand",
                details={"load_percent": 95, "ambient_temp": 32},
            )
        )

    async def _occupancy_decrease(self):
        """Simulate evening occupancy decrease with realistic variation."""
        # Day-of-week variation (some people leave early Friday, more people Friday night)
        day_of_week = self.simulated_time.weekday()
        day_factor = [0.9, 0.85, 0.85, 0.88, 1.2, 0.1, 0.05][day_of_week]  # Mon-Sun

        # Seeded random variation (±15% reproducible)
        occupancy_variance = self._scenario_rng.uniform(0.85, 1.15)
        occupancy_percent = max(5, int(20 * day_factor * occupancy_variance))
        zones_active = max(1, int(occupancy_percent / 5))

        self._emit_event(
            LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=18,
                event_type=EventType.OCCUPANCY_DECREASE,
                description=f"Occupancy decreasing - staff leaving (~{occupancy_percent}%)",
                details={"occupancy_percent": occupancy_percent, "zones_active": zones_active},
            )
        )

        # Adjust setpoints for reduced occupancy
        await self._setpoint_change("cooling_setpoint", 25.0, "Unoccupied mode")
        await self._setpoint_change("lighting_level", int(30 * day_factor), "Unoccupied mode")

    async def _night_mode(self):
        """Simulate night mode."""
        self._emit_event(
            LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=22,
                event_type=EventType.NIGHT_MODE,
                description="Building entering night mode",
                details={"hvac_mode": "setback", "lighting": "security_only"},
            )
        )

    async def _ai_optimization(self, context: str):
        """Simulate AI optimization cycle - generates occupancy-aware + daylight-aware recommendations."""
        try:
            # Get current building state
            current_hour = self.simulated_time.hour

            # Calculate occupancy based on hour
            occupancy_percent = self._calculate_occupancy(current_hour)

            # Calculate daylight factor (0-100%, peaks at noon)
            daylight_factor = self._calculate_daylight(current_hour)

            # Determine zones that should be active
            zones_active = max(1, int(occupancy_percent / 8)) if occupancy_percent > 10 else 0

            logger.info(
                f"AI Optimization ({context}): hour={current_hour}, "
                f"occupancy={occupancy_percent}%, daylight={daylight_factor}%, zones={zones_active}"
            )

            equipment_list = self.equipment_repo.get_all()
            if not equipment_list:
                return

            # Filter to target site if available — process ALL equipment (no cap)
            # Derive equipment code prefix from site_id: "site-002" -> "S002-"
            site_prefix = "S" + self.site_id.replace("site-", "").upper() + "-"
            site_equipment = [eq for eq in equipment_list if eq.get("code", "").startswith(site_prefix)]
            if not site_equipment:
                site_equipment = equipment_list

            recommendations_created = []
            hvac_recs = []
            dali_recs = []

            for eq in site_equipment:
                eq_code = eq.get("code", eq.get("id"))
                eq_type = eq.get("type", "unknown").upper()

                # Skip if not controllable
                if not self.device_control_service.is_controllable(eq_code):
                    continue

                # ========== HVAC OPTIMIZATION (type-specific dispatch) ==========
                hvac_recommendation = None
                if eq_type == "FCU":
                    hvac_recommendation = self._generate_fcu_recommendation(
                        eq_code, context, occupancy_percent, current_hour
                    )
                elif eq_type == "AHU":
                    hvac_recommendation = self._generate_ahu_recommendation(
                        eq_code, context, occupancy_percent, current_hour
                    )
                elif eq_type == "CHILLER":
                    hvac_recommendation = self._generate_chiller_recommendation(
                        eq_code, context, occupancy_percent, current_hour
                    )
                elif eq_type == "VAV":
                    hvac_recommendation = self._generate_vav_recommendation(
                        eq_code, context, occupancy_percent, current_hour
                    )
                elif eq_type == "PUMP":
                    hvac_recommendation = self._generate_pump_recommendation(
                        eq_code, context, occupancy_percent, current_hour
                    )
                elif eq_type in ["CT", "SPLIT", "ZONE", "CONTROLLER"]:
                    # Generic HVAC fallback for cooling towers, splits, zone controllers
                    hvac_recommendation = self._generate_hvac_recommendation(
                        eq_code, eq_type, context, occupancy_percent, current_hour
                    )

                if hvac_recommendation:
                    recommendations_created.append(hvac_recommendation)
                    hvac_recs.append(hvac_recommendation["equipment"])

                    # Create control recommendation
                    try:
                        rec = Recommendation(
                            site_id="S002",
                            timestamp=datetime.utcnow(),
                            action_type="ai_optimization",
                            risk_level=ActionRiskLevel.LOW,
                            target_equipment=eq_code,
                            action={
                                "point": hvac_recommendation["control_point"],
                                "value": hvac_recommendation["target_value"],
                            },
                            reason=hvac_recommendation["reason"],
                            expected_impact={
                                "description": hvac_recommendation["description"],
                                "energy_savings_percent": hvac_recommendation.get("savings", 5),
                            },
                            confidence="high",
                            profile=context,
                            status=RecommendationStatus.PENDING,
                            requires_approval=True,
                        )
                        await self.recommendation_repo.create(rec)
                    except Exception as e:
                        logger.warning(f"Failed to create HVAC recommendation for {eq_code}: {e}")

                # ========== DALI OPTIMIZATION ==========
                if eq_type in ["DALI", "LUM", "DALI_CONTROLLER", "LUMINAIRE", "DALI_LUMINAIRE"]:
                    dali_recommendation = self._generate_dali_recommendation(
                        eq_code, eq_type, context, occupancy_percent, daylight_factor, zones_active, current_hour
                    )
                    if dali_recommendation:
                        recommendations_created.append(dali_recommendation)
                        dali_recs.append(dali_recommendation["equipment"])

                        # Create control recommendation
                        try:
                            rec = Recommendation(
                                site_id="S002",
                                timestamp=datetime.utcnow(),
                                action_type="ai_optimization",
                                risk_level=ActionRiskLevel.LOW,
                                target_equipment=eq_code,
                                action={
                                    "point": dali_recommendation["control_point"],
                                    "value": dali_recommendation["target_value"],
                                },
                                reason=dali_recommendation["reason"],
                                expected_impact={
                                    "description": dali_recommendation["description"],
                                    "energy_savings_percent": dali_recommendation.get("savings", 3),
                                },
                                confidence="high",
                                profile=context,
                                status=RecommendationStatus.PENDING,
                                requires_approval=True,
                            )
                            await self.recommendation_repo.create(rec)
                        except Exception as e:
                            logger.warning(f"Failed to create DALI recommendation for {eq_code}: {e}")

            # ========== DEMO MODE: BESS TOU ARBITRAGE ==========
            if self.current_scenario and self.current_scenario.demo_mode:
                # BESS TOU arbitrage: charge during off-peak, discharge during peak
                if current_hour in [7, 8, 9, 18, 19]:  # Peak hours (R 3.45/kWh)
                    bess_rec = {
                        "equipment": "S002-BESS-001",
                        "control_point": "discharge_power",
                        "target_value": 500,  # kW
                        "reason": "Peak tariff arbitrage - discharge BESS to grid",
                        "description": "Discharge 500kW during peak hours to reduce grid purchase",
                        "savings": 15,
                    }
                    recommendations_created.append(bess_rec)
                elif current_hour in [0, 1, 2, 3, 4, 5]:  # Off-peak (R 1.05/kWh)
                    bess_rec = {
                        "equipment": "S002-BESS-001",
                        "control_point": "charge_power",
                        "target_value": 300,  # kW
                        "reason": "Off-peak charging - cheap grid power",
                        "description": "Charge 300kW during off-peak hours",
                        "savings": 12,
                    }
                    recommendations_created.append(bess_rec)

                # ========== DEMO MODE: GENERATOR LOAD SHEDDING ==========
                # 5% chance per hour to simulate load shedding event
                if random.random() < 0.05:
                    gen_rec = {
                        "equipment": "S002-GEN-B1-001",
                        "control_point": "start",
                        "target_value": 1,
                        "reason": "Simulated load shedding event from grid operator",
                        "description": "Start backup generator due to grid demand response",
                        "savings": 8,
                    }
                    recommendations_created.append(gen_rec)

            # Emit comprehensive optimization event
            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=current_hour,
                    event_type=EventType.AI_OPTIMIZATION,
                    description=(
                        f"AI optimization ({context}) - Occupancy {occupancy_percent}%, "
                        f"Daylight {daylight_factor}%, {len(recommendations_created)} recommendations pending"
                    ),
                    details={
                        "context": context,
                        "occupancy_percent": occupancy_percent,
                        "daylight_factor": daylight_factor,
                        "zones_active": zones_active,
                        "hvac_recommendations": len(hvac_recs),
                        "dali_recommendations": len(dali_recs),
                        "total_recommendations": len(recommendations_created),
                        "recommendations": recommendations_created,
                    },
                )
            )
        except Exception as e:
            logger.warning(f"AI optimization error: {e}")

    def _calculate_occupancy(self, hour: int) -> int:
        """Calculate occupancy percent based on hour of day, with demo mode drift."""
        # Base occupancy from time of day
        if hour < 6 or hour >= 22:
            base = 0  # Night: 0%
        elif hour < 8:
            base = 10  # Early morning: arriving
        elif hour < 11:
            base = 70  # Morning: ramping up
        elif hour < 12:
            base = 90  # Pre-peak: approaching peak
        elif hour < 13:
            base = 95  # Peak: lunch time, still high
        elif hour < 17:
            base = 80  # Afternoon: peak declining
        elif hour < 18:
            base = 60  # Late afternoon: people leaving
        elif hour < 20:
            base = 30  # Evening: mostly gone
        else:
            base = 5  # Late evening: security/cleaning only

        # Demo mode: add occupancy drift (±15%) to keep rules triggering
        if self.current_scenario and self.current_scenario.demo_mode:
            drift = self._scenario_rng.uniform(0.85, 1.15)
            base = int(max(0, min(100, base * drift)))

        return base  # Late evening: security/cleaning only

    def _calculate_daylight(self, hour: int) -> int:
        """Calculate available natural daylight as percentage (0-100%)."""
        if hour < 6 or hour >= 20:
            return 0  # Night: 0% daylight
        elif hour < 8:
            return int((hour - 6) * 25)  # 0-50% (sunrise ramp)
        elif hour < 12:
            return int(50 + (hour - 8) * 10)  # 50-90% (morning increase)
        elif hour < 13:
            return 100  # Peak: full daylight at noon
        elif hour < 16:
            return int(100 - (hour - 13) * 10)  # 100-70% (afternoon decline)
        elif hour < 18:
            return int(70 - (hour - 16) * 20)  # 70-30% (sunset ramp down)
        else:
            return int(max(0, 30 - (hour - 18) * 10))  # 30-0% (sunset finish)

    def _get_seasonal_occupancy_factor(self, hour: int) -> float:
        """Get occupancy factor with seasonal adjustments for annual simulations."""
        if not self.seasonal_modeler:
            # No seasonal modeler: return 1.0 (no adjustment)
            return 1.0

        # Get seasonal occupancy factor from modeler
        rain_today = self.seasonal_modeler.should_rain_today(self.simulated_time.date())
        seasonal_factor = self.seasonal_modeler.get_occupancy_factor(self.simulated_time.date(), hour, rain_today)
        return seasonal_factor

    def _get_seasonal_fault_probability(self, base_probability: float) -> float:
        """Get fault probability adjusted for seasonal stress."""
        if not self.seasonal_modeler:
            # No seasonal modeler: use base probability
            return base_probability

        # Get seasonal multiplier from modeler
        rain_today = self.seasonal_modeler.should_rain_today(self.simulated_time.date())
        multiplier = self.seasonal_modeler.get_fault_probability_multiplier(self.simulated_time.date(), rain_today)
        # Apply multiplier to base probability (capped at 1.0 for daily chance)
        return min(1.0, base_probability * multiplier)

    def _get_demo_thresholds(self) -> tuple:
        """Return (low_occupancy, high_occupancy) thresholds adjusted for demo mode."""
        is_demo = self.current_scenario and self.current_scenario.demo_mode
        return (30 if is_demo else 20, 70 if is_demo else 80)

    def _generate_fcu_recommendation(
        self, eq_code: str, context: str, occupancy_percent: int, hour: int
    ) -> Optional[Dict[str, Any]]:
        """Generate FCU recommendation — cooling_setpoint adjustments."""
        low_thresh, high_thresh = self._get_demo_thresholds()

        if occupancy_percent < low_thresh:
            return {
                "equipment": eq_code,
                "control_point": "cooling_setpoint",
                "target_value": 24.0,
                "reason": f"Low occupancy ({occupancy_percent}%) - reduce active cooling",
                "description": "Increase FCU setpoint to 24°C for energy efficiency",
                "savings": 8,
            }
        elif occupancy_percent >= high_thresh and 10 <= hour <= 12:
            return {
                "equipment": eq_code,
                "control_point": "cooling_setpoint",
                "target_value": 20.5,
                "reason": f"High occupancy ({occupancy_percent}%) + peak demand - anticipatory pre-cooling",
                "description": "Reduce FCU setpoint to 20.5°C for peak demand management",
                "savings": 5,
            }
        elif context == "afternoon":
            return {
                "equipment": eq_code,
                "control_point": "cooling_setpoint",
                "target_value": 21.5,
                "reason": f"Afternoon FCU optimization at {occupancy_percent}% occupancy",
                "description": "Adjust FCU setpoint to 21.5°C for afternoon efficiency",
                "savings": 3,
            }
        return None

    def _generate_ahu_recommendation(
        self, eq_code: str, context: str, occupancy_percent: int, hour: int
    ) -> Optional[Dict[str, Any]]:
        """Generate AHU recommendation — supply_temp_setpoint + economizer control."""
        low_thresh, high_thresh = self._get_demo_thresholds()

        if occupancy_percent < low_thresh:
            # Low occupancy: raise supply air temp to save reheat energy
            return {
                "equipment": eq_code,
                "control_point": "supply_temp_setpoint",
                "target_value": 14.0,
                "reason": f"Low occupancy ({occupancy_percent}%) - raise supply air temp to reduce reheat",
                "description": "Increase AHU supply air to 14°C (from 12°C) during low occupancy",
                "savings": 10,
            }
        elif 9 <= hour <= 16 and occupancy_percent >= high_thresh:
            # Business hours, high occupancy: full cooling capacity
            return {
                "equipment": eq_code,
                "control_point": "supply_temp_setpoint",
                "target_value": 12.0,
                "reason": f"Peak occupancy ({occupancy_percent}%) - maintain full AHU cooling",
                "description": "Set AHU supply air to 12°C for maximum cooling capacity",
                "savings": 2,
            }
        elif 6 <= hour <= 9:
            # Morning mild conditions: enable economizer (free cooling)
            return {
                "equipment": eq_code,
                "control_point": "economizer_mode",
                "target_value": 1,  # 1=enabled
                "reason": "Morning hours - enable AHU economizer for free cooling",
                "description": "Enable economizer mode during mild morning temperatures",
                "savings": 12,
            }
        elif context == "afternoon" and hour >= 14:
            # Hot afternoon: disable economizer, lower supply air
            return {
                "equipment": eq_code,
                "control_point": "supply_temp_setpoint",
                "target_value": 11.5,
                "reason": "Hot afternoon - lower AHU supply air for increased cooling",
                "description": "Reduce AHU supply air to 11.5°C during peak afternoon heat",
                "savings": 3,
            }
        return None

    def _generate_chiller_recommendation(
        self, eq_code: str, context: str, occupancy_percent: int, hour: int
    ) -> Optional[Dict[str, Any]]:
        """Generate chiller recommendation — chw_setpoint + capacity_percent."""
        low_thresh, high_thresh = self._get_demo_thresholds()

        if occupancy_percent < low_thresh:
            # Low load: raise CHW setpoint for compressor efficiency
            return {
                "equipment": eq_code,
                "control_point": "chw_setpoint",
                "target_value": 8.0,
                "reason": f"Low occupancy ({occupancy_percent}%) - raise CHW setpoint for efficiency",
                "description": "Raise chiller CHW setpoint to 8°C (from 6°C) to reduce compressor load",
                "savings": 12,
            }
        elif occupancy_percent >= high_thresh and 10 <= hour <= 15:
            # Peak load: ensure full capacity
            return {
                "equipment": eq_code,
                "control_point": "capacity_percent",
                "target_value": 100,
                "reason": f"Peak occupancy ({occupancy_percent}%) during business hours - full chiller capacity",
                "description": "Set chiller to 100% capacity for peak cooling demand",
                "savings": 0,
            }
        elif context == "afternoon":
            # Afternoon: moderate CHW adjustment
            return {
                "equipment": eq_code,
                "control_point": "chw_setpoint",
                "target_value": 7.0,
                "reason": f"Afternoon optimization - moderate CHW setpoint at {occupancy_percent}% occupancy",
                "description": "Set chiller CHW to 7°C for balance of efficiency and capacity",
                "savings": 6,
            }
        elif hour >= 17:
            # After hours: raise CHW temp aggressively
            return {
                "equipment": eq_code,
                "control_point": "chw_setpoint",
                "target_value": 9.0,
                "reason": "After-hours operation - raise CHW setpoint to minimize energy use",
                "description": "Raise chiller CHW to 9°C during low-demand after-hours period",
                "savings": 15,
            }
        return None

    def _generate_vav_recommendation(
        self, eq_code: str, context: str, occupancy_percent: int, hour: int
    ) -> Optional[Dict[str, Any]]:
        """Generate VAV recommendation — damper_position + airflow_setpoint."""
        low_thresh, high_thresh = self._get_demo_thresholds()

        if occupancy_percent < low_thresh:
            # Low occupancy: close damper toward minimum
            return {
                "equipment": eq_code,
                "control_point": "damper_position",
                "target_value": 30,  # 30% minimum position
                "reason": f"Low occupancy ({occupancy_percent}%) - reduce VAV airflow to minimum",
                "description": "Close VAV damper to 30% minimum position during low occupancy",
                "savings": 10,
            }
        elif occupancy_percent >= high_thresh:
            # High occupancy: open damper fully
            return {
                "equipment": eq_code,
                "control_point": "damper_position",
                "target_value": 90,  # 90% open
                "reason": f"High occupancy ({occupancy_percent}%) - increase VAV airflow for comfort",
                "description": "Open VAV damper to 90% for adequate airflow during high occupancy",
                "savings": 0,
            }
        elif context == "afternoon":
            # Afternoon moderate: adjust airflow setpoint
            return {
                "equipment": eq_code,
                "control_point": "airflow_setpoint",
                "target_value": 60,  # 60% of design airflow
                "reason": f"Afternoon VAV optimization at {occupancy_percent}% occupancy",
                "description": "Set VAV airflow to 60% of design for afternoon efficiency",
                "savings": 5,
            }
        return None

    def _generate_pump_recommendation(
        self, eq_code: str, context: str, occupancy_percent: int, hour: int
    ) -> Optional[Dict[str, Any]]:
        """Generate pump recommendation — speed_percent (affinity laws: 50% speed ≈ 12.5% power)."""
        low_thresh, _ = self._get_demo_thresholds()

        if occupancy_percent < low_thresh:
            # Low load: reduce pump speed aggressively
            return {
                "equipment": eq_code,
                "control_point": "speed_percent",
                "target_value": 40,
                "reason": f"Low occupancy ({occupancy_percent}%) - reduce pump speed (affinity law savings)",
                "description": "Reduce pump to 40% speed — affinity laws yield ~94% power reduction vs full speed",
                "savings": 18,
            }
        elif hour < 7 or hour >= 20:
            # Night/unoccupied: minimum pump speed
            return {
                "equipment": eq_code,
                "control_point": "speed_percent",
                "target_value": 30,
                "reason": "Night/unoccupied hours - pump at minimum circulation speed",
                "description": "Reduce pump to 30% minimum speed during unoccupied hours",
                "savings": 20,
            }
        elif context == "afternoon":
            # Afternoon moderate reduction
            return {
                "equipment": eq_code,
                "control_point": "speed_percent",
                "target_value": 70,
                "reason": f"Afternoon pump optimization at {occupancy_percent}% occupancy",
                "description": "Reduce pump to 70% speed for afternoon efficiency",
                "savings": 8,
            }
        return None

    def _generate_hvac_recommendation(
        self, eq_code: str, eq_type: str, context: str, occupancy_percent: int, hour: int
    ) -> Optional[Dict[str, Any]]:
        """Generate generic HVAC recommendation (fallback for CT, SPLIT, etc.)."""
        low_thresh, high_thresh = self._get_demo_thresholds()

        if occupancy_percent < low_thresh:
            return {
                "equipment": eq_code,
                "control_point": "cooling_setpoint",
                "target_value": 24.0,
                "reason": f"Low occupancy ({occupancy_percent}%) - reduce active cooling",
                "description": f"Increase {eq_type} setpoint to 24°C for energy efficiency",
                "savings": 8,
            }
        elif occupancy_percent >= high_thresh and 10 <= hour <= 12:
            return {
                "equipment": eq_code,
                "control_point": "cooling_setpoint",
                "target_value": 20.5,
                "reason": f"High occupancy ({occupancy_percent}%) + peak demand - anticipatory pre-cooling",
                "description": f"Reduce {eq_type} setpoint to 20.5°C for peak demand management",
                "savings": 5,
            }
        elif context == "afternoon":
            return {
                "equipment": eq_code,
                "control_point": "cooling_setpoint",
                "target_value": 21.5,
                "reason": f"Afternoon optimization at {occupancy_percent}% occupancy",
                "description": f"Adjust {eq_type} setpoint to 21.5°C for afternoon efficiency",
                "savings": 3,
            }
        return None

    def _generate_dali_recommendation(
        self,
        eq_code: str,
        eq_type: str,
        context: str,
        occupancy_percent: int,
        daylight_factor: int,
        zones_active: int,
        hour: int,
    ) -> Optional[Dict[str, Any]]:
        """Generate occupancy-aware + daylight-aware DALI recommendation (Tridonic luminaire control)."""

        if occupancy_percent < 10:
            # Night/security: minimal lighting
            brightness = 20
            reason = "Unoccupied - security lighting only"
        elif daylight_factor > 80:
            # Bright daylight (10am-2pm): minimize artificial lighting
            brightness = max(20, 100 - daylight_factor)  # 20-100% inverse to daylight
            reason = f"High daylight ({daylight_factor}%) - Tridonic harvesting reduces artificial light"
        elif daylight_factor > 50:
            # Good daylight: supplement with some artificial
            brightness = 40 + (occupancy_percent / 100 * 40)  # 40-80% based on occupancy
            reason = f"Moderate daylight ({daylight_factor}%) + occupancy {occupancy_percent}% - supplement lighting"
        elif daylight_factor > 20:
            # Twilight: use more artificial
            brightness = 60 + (occupancy_percent / 100 * 30)  # 60-90%
            reason = f"Low daylight ({daylight_factor}%) - increase artificial lighting"
        else:
            # Night: full artificial
            brightness = 80 + (occupancy_percent / 100 * 20)  # 80-100%
            reason = "Night - full artificial lighting required"

        # Round to nearest 5%
        brightness = int((brightness + 2.5) / 5) * 5

        return {
            "equipment": eq_code,
            "control_point": "brightness_level",
            "target_value": brightness,
            "reason": reason,
            "description": (
                f"Set Tridonic brightness to {brightness}% "
                f"(daylight {daylight_factor}%, occupancy {occupancy_percent}%)"
            ),
            "savings": max(2, int(100 - brightness) / 10),  # Energy savings from dimming
        }

    async def _setpoint_change(self, point: str, value: float, reason: str):
        """Simulate a setpoint change."""
        self._emit_event(
            LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=self.simulated_time.hour,
                event_type=EventType.SETPOINT_CHANGE,
                description=f"Setpoint change: {point} → {value}",
                details={"point": point, "value": value, "reason": reason},
            )
        )

    # === PERSISTENCE METHODS (104-02) ===

    async def _collect_equipment_states(self, hour: int, schedule_state: ScheduleState) -> Dict[str, Dict]:
        """Collect current state of all site equipment for persistence."""
        equipment_states: Dict[str, Dict] = {}

        try:
            equipment_list = self.equipment_repo.get_all(building_id=self.site_id)
            site_prefix = self.site_id.replace("site-", "S").upper()  # site-002 -> S002

            for equip in equipment_list:
                code = equip.get("code", "")
                if not code.startswith(site_prefix):
                    continue

                equip_type = equip.get("type", "unknown").lower()
                health = equip.get("health_score", 75)

                # Apply fault degradation if this equipment has an active fault
                if code in self.active_faults:
                    fault = self.active_faults[code]
                    hours_faulted = fault.get("hours_faulted", 0) + 1
                    fault["hours_faulted"] = hours_faulted
                    health = max(10, health - (hours_faulted * 2))  # 2% per hour while faulted

                # Generate sensor readings based on equipment type and schedule
                sensor_readings = self._generate_sensor_readings(code, equip_type, health, hour, schedule_state)

                equipment_states[code] = {
                    "health_score": health,
                    "status": "online" if health >= 70 else ("degraded" if health >= 40 else "offline"),
                    "sensor_readings": sensor_readings,
                    "type": equip_type,
                }
        except Exception as e:
            logger.warning(f"Failed to collect equipment states: {e}")

        return equipment_states

    def _generate_sensor_readings(
        self,
        code: str,
        equip_type: str,
        health: float,
        hour: int,
        schedule_state: ScheduleState,
    ) -> Dict[str, float]:
        """Generate realistic sensor readings for an equipment item."""
        readings: Dict[str, float] = {}

        if equip_type in ("chiller", "cooling_tower"):
            if schedule_state.chiller_staging.value != "off":
                readings["supply_temp"] = 6.0 + (100 - health) * 0.1  # Degrades with health
                readings["load_pct"] = {"stage_1": 30, "stage_2": 60, "full_load": 90}.get(
                    schedule_state.chiller_staging.value, 0
                )
                readings["compressor_status"] = 1
            else:
                readings["supply_temp"] = 12.0
                readings["load_pct"] = 0
                readings["compressor_status"] = 0

        elif equip_type == "ahu":
            readings["fan_speed_pct"] = schedule_state.ahu_fan_pct
            readings["supply_air_temp"] = 14.0 + (100 - health) * 0.05
            readings["fan_status"] = 1 if schedule_state.ahu_fan_pct > 0 else 0

        elif equip_type == "vav":
            if schedule_state.hvac_mode.value not in ("off", "night_setback"):
                damper = min(100, schedule_state.target_occupancy_pct + 10)
                readings["damper_position"] = damper
                readings["zone_temp"] = 22.0 + self._scenario_rng.uniform(-1, 1)
                readings["airflow_lps"] = damper * 0.8  # Rough L/s from damper %
            else:
                readings["damper_position"] = 0
                readings["zone_temp"] = 22.0 + schedule_state.setpoint_offset
                readings["airflow_lps"] = 0

        elif equip_type == "fcu":
            if schedule_state.hvac_mode.value not in ("off", "night_setback"):
                readings["valve_position"] = min(100, schedule_state.target_occupancy_pct + 15)
                readings["room_temp"] = 22.0 + self._scenario_rng.uniform(-0.5, 0.5)
                readings["fan_speed"] = 2  # medium
            else:
                readings["valve_position"] = 0
                readings["room_temp"] = 22.0 + schedule_state.setpoint_offset
                readings["fan_speed"] = 0

        elif equip_type == "ups":
            readings["battery_level"] = max(50, 100 - (24 - hour) * 0.5)  # Slow drain
            readings["load_pct"] = 30 + self._scenario_rng.uniform(-5, 5)

        elif equip_type == "generator":
            readings["status"] = 0  # Standby unless load shedding
            readings["fuel_level"] = 85 + self._scenario_rng.uniform(-2, 2)

        elif equip_type == "meter":
            readings["power_kw"] = self.current_hour_power_kw
            readings["power_factor"] = 0.92 + self._scenario_rng.uniform(-0.02, 0.02)

        elif equip_type in ("dali_zone", "dali_controller"):
            lighting_pct = {
                "off": 0,
                "security_only": 10,
                "dimmed": 30,
                "full": 100,
                "daylight_harvest": 65,
            }.get(schedule_state.lighting_mode.value, 0)
            readings["brightness_pct"] = float(lighting_pct)
            readings["status"] = 1.0 if lighting_pct > 0 else 0.0

        elif equip_type == "zone_sensor":
            # CO2 and humidity
            occupancy_factor = schedule_state.target_occupancy_pct / 100.0
            readings["co2_ppm"] = 400 + occupancy_factor * 200 + self._scenario_rng.uniform(-20, 20)
            readings["humidity_pct"] = 45 + occupancy_factor * 10 + self._scenario_rng.uniform(-3, 3)

        return readings

    async def _inject_fault(self):
        """Inject a fault into equipment and create real alerts."""
        try:
            # Get equipment to fault (filtered by site_id)
            equipment_list = self.equipment_repo.get_all(building_id=self.site_id)
            if not equipment_list:
                logger.warning("No equipment available to fault")
                return

            # Filter by type if specified
            if self.current_scenario and self.current_scenario.fault_equipment_type:
                target_type = self.current_scenario.fault_equipment_type.lower()
                filtered = [
                    eq
                    for eq in equipment_list
                    if target_type in (eq.get("equipment_type", "") or "").lower()
                    or target_type in (eq.get("code", "") or "").lower()
                ]
                if filtered:
                    equipment_list = filtered
            else:
                # Prefer HVAC equipment for faults (more realistic)
                hvac_types = {"chiller", "ahu", "fcu", "vav", "pump", "cooling_tower", "ct"}
                hvac_candidates = [e for e in equipment_list if (e.get("type", "") or "").lower() in hvac_types]
                if hvac_candidates:
                    equipment_list = hvac_candidates

            # Pick random equipment
            equipment = self._scenario_rng.choice(equipment_list)
            eq_id = equipment.get("id")
            eq_code = equipment.get("code", eq_id)
            eq_name = equipment.get("name", eq_code)
            eq_type = (equipment.get("type", "") or "unknown").lower()

            # Generate fault details
            fault_types = [
                ("High vibration detected", "vibration", 85),
                ("Temperature deviation", "temperature", 75),
                ("Pressure anomaly", "pressure", 70),
                ("Current draw elevated", "electrical", 80),
                ("Filter differential high", "filter", 65),
            ]
            fault_type, fault_category, severity = self._scenario_rng.choice(fault_types)

            # Record fault with hours_faulted tracking for persistence degradation
            fault_info = {
                "equipment_id": eq_id,
                "equipment_code": eq_code,
                "equipment_name": eq_name,
                "fault_type": fault_type,
                "fault_category": fault_category,
                "severity": severity,
                "fault_hour": self.simulated_time.hour,
                "detected_at": datetime.now().isoformat(),
                "hours_faulted": 0,
            }
            self.active_faults[eq_code] = fault_info

            # Emit fault event
            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=self.simulated_time.hour,
                    event_type=EventType.EQUIPMENT_FAULT,
                    equipment_id=eq_code,
                    equipment_name=eq_name,
                    description=f"{fault_type} on {eq_name}",
                    details=fault_info,
                )
            )

            # Degrade equipment health
            current_health = equipment.get("health_score", 80)
            new_health = max(30, current_health - self._scenario_rng.randint(15, 30))

            self.equipment_repo.update(
                eq_code,
                {
                    "health_score": new_health,
                    "status": "warning" if new_health >= 50 else "critical",
                },
            )

            # Create prediction in database
            await self._create_prediction(equipment, fault_info)

            # Generate alert and work order via existing pipeline
            await self._generate_alert(equipment, fault_info)

            # Create real alert in Supabase via EquipmentAlertService (104-02)
            try:
                from app.services.equipment_alert_service import EquipmentAlertService

                alert_svc = EquipmentAlertService()
                alert_severity = "critical" if eq_type in ("chiller", "generator") else "warning"
                alert_svc.create_alert_for_equipment(
                    equipment_id=eq_id,
                    building_id=equipment.get("building_id", self.site_id),
                    severity=alert_severity,
                    message=f"Simulated fault on {eq_code}: {fault_type}",
                    alert_type="equipment_fault",
                    notify_telegram=self.current_scenario.sentry_notifications if self.current_scenario else False,
                )
                logger.info(f"Alert created for {eq_code} via EquipmentAlertService")
            except Exception as e:
                logger.debug(f"Could not create Supabase alert for {eq_code}: {e}")

            # Schedule repair if auto_repair enabled
            if self.current_scenario and self.current_scenario.auto_repair:
                repair_hour = self.simulated_time.hour + self.current_scenario.repair_delay_hours
                if repair_hour >= 24:
                    repair_hour -= 24

                self.pending_repairs[eq_code] = {
                    **fault_info,
                    "scheduled_repair_hour": repair_hour,
                    "work_order_id": None,
                }
                logger.info(f"Repair scheduled for {eq_code} at hour {repair_hour}")

        except Exception as e:
            logger.error(f"Fault injection error: {e}")

    async def _create_prediction(self, equipment: Dict, fault_info: Dict):
        """Create a prediction in the database."""
        try:
            eq_id = equipment.get("id")
            building_id = equipment.get("building_id")

            prediction_data = {
                "equipment_id": eq_id,
                "building_id": building_id,
                "prediction_type": "failure",
                "probability_percent": fault_info["severity"],
                "timeframe": "14 days",
                "severity": "high" if fault_info["severity"] >= 75 else "medium",
                "description": f"ML detected: {fault_info['fault_type']}",
                "status": "active",
                "model_version": "lifecycle_sim_v1",
            }

            self.prediction_repo.create(prediction_data)

            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=self.simulated_time.hour,
                    event_type=EventType.ALERT_GENERATED,
                    equipment_id=fault_info["equipment_code"],
                    equipment_name=fault_info["equipment_name"],
                    description=f"ML prediction created: {fault_info['severity']}% failure probability",
                    details={"prediction": prediction_data},
                )
            )

        except Exception as e:
            logger.error(f"Prediction creation error: {e}")

    async def _generate_alert(self, equipment: Dict, fault_info: Dict):
        """Generate alert and optionally notify Sentry."""
        try:
            # Create work order
            work_order = await self.work_order_repo.create_work_order(
                {
                    "equipment_id": equipment.get("id"),
                    "title": f"Repair: {fault_info['fault_type']}",
                    "description": (
                        f"Automated work order for {fault_info['equipment_name']}: {fault_info['fault_type']}"
                    ),
                    "priority": "high" if fault_info["severity"] >= 75 else "medium",
                    "status": "scheduled",
                    "created_by": "LIFECYCLE_SIM",
                }
            )

            wo_code = work_order.get("code", "WO-SIM") if work_order else "WO-SIM"

            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=self.simulated_time.hour,
                    event_type=EventType.WORK_ORDER_CREATED,
                    equipment_id=fault_info["equipment_code"],
                    equipment_name=fault_info["equipment_name"],
                    description=f"Work order {wo_code} created",
                    details={"work_order_code": wo_code, "priority": "high"},
                )
            )

            # Update pending repair with work order ID
            if fault_info["equipment_code"] in self.pending_repairs:
                self.pending_repairs[fault_info["equipment_code"]]["work_order_id"] = wo_code

            # Notify Sentry if enabled
            if self.current_scenario and self.current_scenario.sentry_notifications:
                await self._notify_sentry(equipment, fault_info, wo_code)

        except Exception as e:
            logger.error(f"Alert generation error: {e}")

    async def _notify_sentry(self, equipment: Dict, fault_info: Dict, work_order_code: str):
        """Send notification to Sentry bot."""
        try:
            # This would send actual Telegram message
            # For simulation, we just log it
            logger.info(f"[SENTRY] Notification sent for {work_order_code}: {fault_info['fault_type']}")

            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=self.simulated_time.hour,
                    event_type=EventType.TECHNICIAN_DISPATCHED,
                    equipment_id=fault_info["equipment_code"],
                    equipment_name=fault_info["equipment_name"],
                    description=f"Technician notified via Sentry for {work_order_code}",
                    details={"notification_method": "telegram", "work_order": work_order_code},
                )
            )

        except Exception as e:
            logger.warning(f"Sentry notification skipped: {e}")

    async def _check_pending_repairs(self):
        """Check if any repairs are due."""
        current_hour = self.simulated_time.hour
        repairs_to_complete = []

        for eq_code, repair_info in self.pending_repairs.items():
            if repair_info.get("scheduled_repair_hour") == current_hour:
                repairs_to_complete.append((eq_code, repair_info))

        for eq_code, repair_info in repairs_to_complete:
            await self._complete_repair(eq_code, repair_info)

    async def _complete_repair(self, eq_code: str, repair_info: Dict):
        """Simulate technician completing repair with health restoration."""
        try:
            # Create completed work order in Supabase (104-02)
            try:
                wo_id = f"WO-SIM-{eq_code}-{self.simulated_time.strftime('%m%d%H')}"
                await self.work_order_repo.create_work_order(
                    {
                        "work_order_id": wo_id,
                        "equipment_id": repair_info.get("equipment_id", eq_code),
                        "title": f"Repair complete: {repair_info.get('fault_type', 'fault')}",
                        "description": (f"Simulated repair for fault on {eq_code}. Health restored to 85%."),
                        "status": "completed",
                        "priority": "high",
                        "created_by": "LIFECYCLE_SIM",
                    }
                )
                logger.info(f"Work order {wo_id} created for repair of {eq_code}")
            except Exception as e:
                logger.debug(f"Work order creation skipped for {eq_code}: {e}")

            # Restore equipment health to 85% via Supabase (104-02)
            try:
                from app.database.supabase_client import get_supabase_client

                supabase = get_supabase_client()
                supabase.table("equipment").update(
                    {
                        "health_score": 85,
                        "status": "online",
                    }
                ).eq("code", eq_code).execute()
                logger.info(f"Health restored to 85% for {eq_code}")
            except Exception:
                # Fallback: update via equipment repo
                try:
                    self.equipment_repo.update(eq_code, {"health_score": 85, "status": "online"})
                except Exception:
                    pass  # JSON fallback handled by persistence service

            # Emit repair completed event
            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=self.simulated_time.hour,
                    event_type=EventType.REPAIR_COMPLETED,
                    equipment_id=eq_code,
                    equipment_name=repair_info.get("equipment_name"),
                    description=(f"Repair complete: {repair_info.get('equipment_name')} health restored to 85%"),
                    details={
                        "fault_type": repair_info.get("fault_type"),
                        "health_restored": 85,
                    },
                )
            )

            # Submit service feedback
            await self._submit_service_feedback(eq_code, repair_info)

            # Remove from active faults and pending repairs
            self.active_faults.pop(eq_code, None)
            self.pending_repairs.pop(eq_code, None)

        except Exception as e:
            logger.error(f"Repair completion error: {e}")

    async def _submit_service_feedback(self, eq_code: str, repair_info: Dict):
        """Simulate technician submitting service feedback."""
        try:
            # Start feedback session
            work_order_id = repair_info.get("work_order_id", "WO-SIM-001")
            equipment_id = repair_info.get("equipment_id", eq_code)

            session = await self.feedback_service.start_feedback_session(
                work_order_id=work_order_id, equipment_id=equipment_id, equipment_code=eq_code, service_type="breakdown"
            )

            # Submit some readings showing improvement
            fault_category = repair_info.get("fault_category", "vibration")

            # Submit a good reading (improved from fault)
            if fault_category == "vibration":
                await self.feedback_service.submit_feedback_item(
                    session.session_id,
                    "vibration",
                    1.2,  # Good value
                    FeedbackItemType.READING,
                    unit="mm/s",
                    notes="Post-repair vibration within normal range",
                )
            elif fault_category == "temperature":
                await self.feedback_service.submit_feedback_item(
                    session.session_id,
                    "temperature",
                    22.5,
                    FeedbackItemType.READING,
                    unit="°C",
                    notes="Temperature stable after repair",
                )

            # Submit observation
            await self.feedback_service.submit_feedback_item(
                session.session_id,
                "observation",
                f"Repaired {repair_info.get('fault_type')}. Equipment operating normally.",
                FeedbackItemType.OBSERVATION,
                notes="Repair successful",
            )

            # Complete session (force=True to skip missing items)
            result = await self.feedback_service.complete_feedback_session(session.session_id, force=True)

            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=self.simulated_time.hour,
                    event_type=EventType.FEEDBACK_SUBMITTED,
                    equipment_id=eq_code,
                    equipment_name=repair_info.get("equipment_name"),
                    description=f"Service feedback submitted: health +{result.get('health_score_change', 0)}",
                    details={
                        "session_id": session.session_id,
                        "health_change": result.get("health_score_change", 0),
                        "items_collected": result.get("items_collected", 0),
                    },
                )
            )

            # Emit health restored event
            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=self.simulated_time.hour,
                    event_type=EventType.HEALTH_RESTORED,
                    equipment_id=eq_code,
                    equipment_name=repair_info.get("equipment_name"),
                    description=f"Equipment health restored for {repair_info.get('equipment_name')}",
                    details={"new_status": "normal"},
                )
            )

            # Resolve predictions
            equipment = self.equipment_repo.get_by_id(eq_code)
            if equipment:
                self.prediction_repo.resolve_by_equipment(equipment.get("id"))

            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=self.simulated_time.hour,
                    event_type=EventType.ALERT_RESOLVED,
                    equipment_id=eq_code,
                    equipment_name=repair_info.get("equipment_name"),
                    description=f"Alert resolved for {repair_info.get('equipment_name')}",
                    details={},
                )
            )

        except Exception as e:
            logger.error(f"Service feedback submission error: {e}")

    def serialize_state(self) -> Dict[str, Any]:
        """
        Serialize orchestrator state to JSON-serializable dict for database storage.
        Enables crash recovery by preserving simulation state.

        Returns:
            Dict with: simulated_time, days_simulated, active_faults, pending_repairs,
            recent_events, time_multiplier, occupancy_seed
        """
        return {
            "simulated_time": self.simulated_time.isoformat(),
            "days_simulated": self.days_simulated,
            "active_faults": self.active_faults,
            "pending_repairs": self.pending_repairs,
            "recent_events": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "event_type": e.event_type.value,
                    "equipment_id": e.equipment_id,
                    "message": e.description,
                }
                for e in self.events[-50:]  # Keep last 50 events for display
            ],
            "time_multiplier": self.time_multiplier,
            "occupancy_seed": self._occupancy_seed,
            "total_energy_kwh": round(self.total_energy_kwh, 1),
            "current_hour_power_kw": round(self.current_hour_power_kw, 2),
        }

    @staticmethod
    def deserialize_state(state_dict: Dict[str, Any]) -> "LifecycleOrchestrator":
        """
        Restore orchestrator from serialized state (crash recovery).
        Creates new instance and restores state from checkpoint.

        Args:
            state_dict: Dict from serialize_state()

        Returns:
            LifecycleOrchestrator instance with restored state
        """
        orchestrator = LifecycleOrchestrator()

        # Restore time and simulation progress
        orchestrator.simulated_time = datetime.fromisoformat(state_dict["simulated_time"])
        orchestrator.days_simulated = state_dict["days_simulated"]
        orchestrator.time_multiplier = state_dict["time_multiplier"]
        orchestrator._occupancy_seed = state_dict["occupancy_seed"]

        # Restore faults and repairs
        orchestrator.active_faults = state_dict.get("active_faults", {})
        orchestrator.pending_repairs = state_dict.get("pending_repairs", {})

        # Restore energy consumption tracking
        orchestrator.total_energy_kwh = state_dict.get("total_energy_kwh", 0.0)
        orchestrator.current_hour_power_kw = state_dict.get("current_hour_power_kw", 0.0)

        # Restore occupancy randomness (deterministic for same seed)
        if orchestrator._occupancy_seed is not None:
            orchestrator._scenario_rng.seed(orchestrator._occupancy_seed)

        logger.info(
            f"Restored orchestrator state: day {orchestrator.days_simulated}, "
            f"{len(orchestrator.active_faults)} active faults, "
            f"{len(orchestrator.pending_repairs)} pending repairs"
        )

        return orchestrator

    async def save_checkpoint(self) -> bool:
        """
        Save current state to database (called every 6 simulated hours).
        Enables resumption from checkpoint if server crashes.

        Returns:
            True if saved successfully, False otherwise
        """
        if not self.task_id:
            logger.warning(f"Cannot save checkpoint: task_id is None or empty. days_simulated={self.days_simulated}")
            return False  # No task_id means not a queued task

        try:
            from app.database.supabase_client import Supabase

            state_snapshot = self.serialize_state()

            # Update task in database with checkpoint
            client = Supabase.instance()
            client.table("lifecycle_simulation_tasks").update(
                {
                    "state_snapshot": state_snapshot,
                    "progress_pct": int((self.days_simulated / 365) * 100) if self.seasonal_modeler else 0,
                    "days_completed": self.days_simulated,
                }
            ).eq("task_id", str(self.task_id)).execute()

            logger.info(f"Checkpoint saved for task {self.task_id}: day {self.days_simulated}")
            return True

        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            return False


def create_lifecycle_orchestrator(task_id: Optional[str] = None, site_id: str = "site-002") -> LifecycleOrchestrator:
    """
    Create a new lifecycle orchestrator instance.

    Args:
        task_id: Optional task ID for database-backed task tracking
        site_id: Target site identifier (default "site-002")

    Returns:
        New LifecycleOrchestrator instance
    """
    return LifecycleOrchestrator(task_id=task_id, site_id=site_id)


# Global singleton instance
_orchestrator_instance: Optional[LifecycleOrchestrator] = None


def get_lifecycle_orchestrator(site_id: str = "site-002") -> LifecycleOrchestrator:
    """
    Get or create the global lifecycle orchestrator singleton.

    Args:
        site_id: Target site identifier (default "site-002")

    Returns:
        Singleton LifecycleOrchestrator instance
    """
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = LifecycleOrchestrator(site_id=site_id)
        logger.info(f"Created lifecycle orchestrator singleton for {site_id}")
    return _orchestrator_instance
