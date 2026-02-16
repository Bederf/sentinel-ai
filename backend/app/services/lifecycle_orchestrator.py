"""
24-Hour Building Lifecycle Orchestrator

Simulates a complete building day with:
- AI optimization adjustments
- Equipment degradation and faults
- Alert generation and Clawd notifications
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
import json

from app.database.supabase_client import get_supabase_client
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
    clawd_notifications: bool = True
    operation_mode: Optional[OperationMode] = None
    demo_mode: bool = False  # Enable continuous AI recommendations (lower thresholds, BESS arbitrage)  # Building operation mode for demos


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
        description="Full-year simulation with South African seasonal variations - temperature cycles, rainfall patterns, occupancy variations, and seasonal fault probabilities",
        operation_mode=OperationMode.HVAC_DALI_SENTINEL,
        fault_probability=0.05,
        auto_repair=True,
        repair_delay_hours=4,
        optimization_enabled=True,
        demo_mode=True,  # Enable continuous AI recommendations for demo (lower thresholds, BESS arbitrage)
    ),
    "grant_solar_bess_ai_annual": ScenarioConfig(
        name="Grant Demo: Solar + BESS + Sentinel AI (365 days)",
        description="Full-year simulation with 3.9 MWp solar + 5 MWh BESS, City Power TOU arbitrage, demand management, and South African seasonal variations",
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

    Integrates:
    - Equipment health and readings
    - AI optimization
    - Fault injection and alerts
    - Work order creation
    - Technician simulation
    - Service feedback
    """

    def __init__(self, task_id: Optional[str] = None):
        self.task_id = task_id  # For database task tracking
        self.running = False
        self.paused = False
        self.current_scenario: Optional[ScenarioConfig] = None
        self.simulated_time: datetime = datetime.now().replace(hour=0, minute=0, second=0)
        self.real_start_time: Optional[datetime] = None
        self.time_multiplier: float = 60.0  # 1 real minute = 1 simulated hour
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
        
        # Seeded random for reproducible but realistic variation
        # Same scenario always produces same results, but with day-to-day variation
        self._scenario_rng = random.Random()
        self._occupancy_seed: Optional[int] = None
        
        # Seasonal modeler for annual simulations
        self.seasonal_modeler: Optional[SeasonalModeler] = None
        self.days_simulated: int = 0  # Track days for annual simulations

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
        self.events = []
        self.active_faults = {}
        self.pending_repairs = {}
        self._task = None
        self._scenario_rng = random.Random()
        self._occupancy_seed = None
        self.seasonal_modeler = None
        self.days_simulated = 0
        logger.info("Orchestrator reset: Ready for fresh demo")

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
        scenario: str = "fault_day",
        duration_minutes: float = 24.0,
        start_hour: int = 0,
        task_id: str = None,  # For checkpoint recovery
    ) -> Dict[str, Any]:
        """
        Start the 24-hour simulation.

        Args:
            scenario: Scenario name from SCENARIOS
            duration_minutes: Real-time duration (24 = 1 min per hour)
            start_hour: Simulated hour to start (0-23)
            task_id: Optional task_id for checkpoint recovery

        Returns:
            Status dict with session info
        """
        # FIRST: Check for existing checkpoint to recover from
        checkpoint = None
        if task_id and scenario == "grant_hvac_dali_ai_annual":
            try:
                from app.database.supabase_client import get_supabase_client
                supabase = get_supabase_client()
                response = supabase.table("lifecycle_simulation_tasks").select("state_snapshot").eq("task_id", task_id).execute()
                if response.data and response.data[0].get("state_snapshot"):
                    checkpoint = response.data[0]["state_snapshot"]
                    logger.info(f"✅ Found checkpoint for task {task_id}, recovering from day {checkpoint.get('days_simulated', 0)}/365")
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

        # Check if this is an annual scenario
        is_annual = scenario == "grant_hvac_dali_ai_annual"

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
                logger.info(f"✅ Restored checkpoint: day {self.days_simulated}/365, time={self.simulated_time.strftime('%Y-%m-%d %H:%M')}")

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
                "started_at": self.real_start_time.isoformat()
            }

        # FRESH START PATH: Initialize fresh (no checkpoint)
        if is_annual:
            # Annual simulation: 365 days × 24 hours = 8760 hours total
            self.seasonal_modeler = SeasonalModeler(seed=self._occupancy_seed)
            self.days_simulated = 0
            # Calculate time multiplier for 365-day simulation
            # Default: 240 minutes = 4 hours real time for full year (1 day per ~20 real seconds)
            total_hours_annual = 365 * 24
            self.time_multiplier = (duration_minutes / total_hours_annual) * 60.0  # seconds per simulated hour
            # Start on January 1st, 6am (year is arbitrary - Python will handle date math)
            self.simulated_time = datetime(2024, 1, 1, start_hour, 0, 0)
            logger.info(f"Annual simulation initialized: {duration_minutes} min for full year (365 days)")
        else:
            # Daily simulation: just 24 hours
            self.seasonal_modeler = None
            # Calculate time multiplier for 24-hour simulation
            # duration_minutes for full 24 hours
            # So 1 simulated hour = duration_minutes / 24 real minutes
            self.time_multiplier = (duration_minutes / 24.0) * 60.0  # seconds per simulated hour
            self.simulated_time = datetime.now().replace(
                hour=start_hour, minute=0, second=0, microsecond=0
            )

        self.real_start_time = datetime.now()
        self.events = []
        self.active_faults = {}
        self.pending_repairs = {}
        self.running = True
        self.paused = False

        logger.info(
            f"Starting lifecycle simulation: {self.current_scenario.name}, "
            f"duration={duration_minutes}min, start_hour={start_hour}, "
            f"time_multiplier={self.time_multiplier}s/hour"
        )

        # Start background task
        self._task = asyncio.create_task(self._run_simulation())

        return {
            "success": True,
            "scenario": self.current_scenario.name,
            "duration_minutes": duration_minutes,
            "time_multiplier_seconds_per_hour": self.time_multiplier,
            "start_hour": start_hour,
            "started_at": self.real_start_time.isoformat()
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

        return {
            "success": True,
            "events_generated": len(self.events),
            "stopped_at": datetime.now().isoformat()
        }

    def pause(self):
        """Pause the simulation."""
        self.paused = True

    def resume(self):
        """Resume the simulation."""
        self.paused = False

    def get_status(self) -> Dict[str, Any]:
        """Get current simulation status."""
        elapsed_real = (datetime.now() - self.real_start_time).total_seconds() if self.real_start_time else 0

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
            "recent_events": [
                {
                    "hour": e.simulated_hour,
                    "type": e.event_type.value,
                    "description": e.description,
                    "equipment": e.equipment_name
                }
                for e in self.events[-10:]
            ]
        }

    async def _run_simulation(self):
        """Main simulation loop."""
        try:
            last_hour = -1
            last_checkpoint_hour = -1
            is_annual = self.seasonal_modeler is not None

            while self.running:
                if self.paused:
                    await asyncio.sleep(0.5)
                    continue

                current_hour = self.simulated_time.hour

                # Process hour change
                if current_hour != last_hour:
                    await self._process_hour(current_hour)
                    last_hour = current_hour
                    
                    # Save checkpoint every 6 simulated hours for crash recovery
                    if is_annual and (current_hour % 6 == 0):
                        if current_hour != last_checkpoint_hour:
                            await self.save_checkpoint()
                            last_checkpoint_hour = current_hour

                # Advance time
                await asyncio.sleep(self.time_multiplier / 60)  # Sleep for 1 simulated minute
                self.simulated_time += timedelta(minutes=1)

                # Check for day rollover
                if self.simulated_time.hour == 0 and last_hour == 23:
                    self.days_simulated += 1
                    season = self.seasonal_modeler.get_season_name(self.simulated_time.date()) if is_annual else None
                    logger.info(f"Day {self.days_simulated}/365 complete{f' ({season})' if is_annual else ''}...")
                    
                    # Save checkpoint on day boundary
                    if is_annual:
                        await self.save_checkpoint()
                    
                    # For annual simulation, stop after 365 days
                    if is_annual and self.days_simulated >= 365:
                        logger.info("Annual simulation complete (365 days)")
                        self.running = False

        except asyncio.CancelledError:
            logger.info("Simulation cancelled")
        except Exception as e:
            logger.error(f"Simulation error: {e}")
            self.running = False

    async def _process_hour(self, hour: int):
        """Process events for the given simulated hour."""
        logger.info(f"Processing simulated hour: {hour:02d}:00 (Day {self.days_simulated + 1}/365)" if self.seasonal_modeler else f"Processing simulated hour: {hour:02d}:00")

        # Midnight: daily summary for annual simulations
        if hour == 0 and self.seasonal_modeler:
            season = self.seasonal_modeler.get_season_name(self.simulated_time.date())
            self._emit_event(LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=0,
                event_type=EventType.BUILDING_WAKE,
                description=f"Day {self.days_simulated + 1}: {season.capitalize()} - Building daily cycle begins",
                details={
                    "day_of_year": self.days_simulated + 1,
                    "season": season,
                    "month": self.simulated_time.strftime("%B")
                }
            ))

        # Morning startup
        if hour == 6:
            await self._building_wake()

        # Occupancy increase
        elif hour == 8:
            await self._occupancy_increase()

        # Mid-morning optimization
        elif hour == 10:
            await self._ai_optimization("mid_morning")

        # Peak load - potential fault time
        elif hour == 11:
            await self._peak_load()
            if self.current_scenario and self.current_scenario.fault_hour == 11:
                await self._inject_fault()

        # Afternoon
        elif hour == 14:
            await self._ai_optimization("afternoon")
            # Check for scheduled repairs
            await self._check_pending_repairs()

        # Late afternoon
        elif hour == 16:
            await self._check_pending_repairs()

        # Evening wind-down
        elif hour == 18:
            await self._occupancy_decrease()

        # Night mode
        elif hour == 22:
            await self._night_mode()

        # Check for random faults based on probability (with seasonal adjustment)
        if self.current_scenario:
            base_probability = self.current_scenario.fault_probability / 24
            seasonal_probability = self._get_seasonal_fault_probability(base_probability)
            if random.random() < seasonal_probability:
                if not self.current_scenario.fault_hour:  # Only if not scheduled
                    await self._inject_fault()

        # Check pending repairs every hour
        await self._check_pending_repairs()

    async def _building_wake(self):
        """Simulate building morning startup."""
        self._emit_event(LifecycleEvent(
            timestamp=datetime.now(),
            simulated_hour=6,
            event_type=EventType.BUILDING_WAKE,
            description="Building systems starting up for the day",
            details={"hvac_mode": "pre_cooling", "lighting": "minimal"}
        ))

        # AI pre-cooling optimization
        await self._ai_optimization("pre_cooling")

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
        
        self._emit_event(LifecycleEvent(
            timestamp=datetime.now(),
            simulated_hour=8,
            event_type=EventType.OCCUPANCY_INCREASE,
            description=f"Occupancy increasing - staff arriving (~{occupancy_percent}%)",
            details={"occupancy_percent": occupancy_percent, "zones_active": zones_active}
        ))

        # Adjust setpoints for occupancy
        await self._setpoint_change("cooling_setpoint", 22.0, "Occupied mode")
        await self._setpoint_change("lighting_level", int(80 * day_factor), "Occupied mode")

    async def _peak_load(self):
        """Simulate peak load period."""
        self._emit_event(LifecycleEvent(
            timestamp=datetime.now(),
            simulated_hour=11,
            event_type=EventType.PEAK_LOAD,
            description="Peak cooling load - maximum demand",
            details={"load_percent": 95, "ambient_temp": 32}
        ))

    async def _occupancy_decrease(self):
        """Simulate evening occupancy decrease with realistic variation."""
        # Day-of-week variation (some people leave early Friday, more people Friday night)
        day_of_week = self.simulated_time.weekday()
        day_factor = [0.9, 0.85, 0.85, 0.88, 1.2, 0.1, 0.05][day_of_week]  # Mon-Sun
        
        # Seeded random variation (±15% reproducible)
        occupancy_variance = self._scenario_rng.uniform(0.85, 1.15)
        occupancy_percent = max(5, int(20 * day_factor * occupancy_variance))
        zones_active = max(1, int(occupancy_percent / 5))
        
        self._emit_event(LifecycleEvent(
            timestamp=datetime.now(),
            simulated_hour=18,
            event_type=EventType.OCCUPANCY_DECREASE,
            description=f"Occupancy decreasing - staff leaving (~{occupancy_percent}%)",
            details={"occupancy_percent": occupancy_percent, "zones_active": zones_active}
        ))

        # Adjust setpoints for reduced occupancy
        await self._setpoint_change("cooling_setpoint", 25.0, "Unoccupied mode")
        await self._setpoint_change("lighting_level", int(30 * day_factor), "Unoccupied mode")

    async def _night_mode(self):
        """Simulate night mode."""
        self._emit_event(LifecycleEvent(
            timestamp=datetime.now(),
            simulated_hour=22,
            event_type=EventType.NIGHT_MODE,
            description="Building entering night mode",
            details={"hvac_mode": "setback", "lighting": "security_only"}
        ))

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
            
            logger.info(f"AI Optimization ({context}): hour={current_hour}, occupancy={occupancy_percent}%, daylight={daylight_factor}%, zones={zones_active}")
            
            equipment_list = self.equipment_repo.get_all()
            if not equipment_list:
                return
            
            # Filter to site-002 if available
            site_002_equipment = [eq for eq in equipment_list if eq.get("code", "").startswith("S002-")]
            if not site_002_equipment:
                site_002_equipment = equipment_list[:5]
            else:
                site_002_equipment = site_002_equipment[:5]
            
            recommendations_created = []
            hvac_recs = []
            dali_recs = []

            for eq in site_002_equipment:
                eq_code = eq.get("code", eq.get("id"))
                eq_type = eq.get("type", "unknown").upper()
                
                # Skip if not controllable
                if not self.device_control_service.is_controllable(eq_code):
                    continue
                
                # ========== HVAC OPTIMIZATION ==========
                if eq_type in ["FCU", "VAV", "AHU", "CHILLER"]:
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
                if eq_type in ["DALI", "LUM"]:
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
                        "savings": 15
                    }
                    recommendations_created.append(bess_rec)
                elif current_hour in [0, 1, 2, 3, 4, 5]:  # Off-peak (R 1.05/kWh)
                    bess_rec = {
                        "equipment": "S002-BESS-001",
                        "control_point": "charge_power",
                        "target_value": 300,  # kW
                        "reason": "Off-peak charging - cheap grid power",
                        "description": "Charge 300kW during off-peak hours",
                        "savings": 12
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
                        "savings": 8
                    }
                    recommendations_created.append(gen_rec)

            # Emit comprehensive optimization event
            self._emit_event(LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=current_hour,
                event_type=EventType.AI_OPTIMIZATION,
                description=f"AI optimization ({context}) - Occupancy {occupancy_percent}%, Daylight {daylight_factor}%, {len(recommendations_created)} recommendations pending",
                details={
                    "context": context,
                    "occupancy_percent": occupancy_percent,
                    "daylight_factor": daylight_factor,
                    "zones_active": zones_active,
                    "hvac_recommendations": len(hvac_recs),
                    "dali_recommendations": len(dali_recs),
                    "total_recommendations": len(recommendations_created),
                    "recommendations": recommendations_created
                }
            ))
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
        seasonal_factor = self.seasonal_modeler.get_occupancy_factor(
            self.simulated_time.date(), hour, rain_today
        )
        return seasonal_factor
    
    def _get_seasonal_fault_probability(self, base_probability: float) -> float:
        """Get fault probability adjusted for seasonal stress."""
        if not self.seasonal_modeler:
            # No seasonal modeler: use base probability
            return base_probability
        
        # Get seasonal multiplier from modeler
        rain_today = self.seasonal_modeler.should_rain_today(self.simulated_time.date())
        multiplier = self.seasonal_modeler.get_fault_probability_multiplier(
            self.simulated_time.date(), rain_today
        )
        # Apply multiplier to base probability (capped at 1.0 for daily chance)
        return min(1.0, base_probability * multiplier)
    
    def _generate_hvac_recommendation(self, eq_code: str, eq_type: str, context: str, 
                                      occupancy_percent: int, hour: int) -> Optional[Dict[str, Any]]:
        """Generate occupancy-aware HVAC recommendation."""
        # Demo mode: lower thresholds for continuous recommendations (2x more sensitive)
        is_demo = self.current_scenario and self.current_scenario.demo_mode
        low_occupancy_threshold = 30 if is_demo else 20
        high_occupancy_threshold = 70 if is_demo else 80
        
        if occupancy_percent < low_occupancy_threshold:
            # Low occupancy: reduce cooling, increase setpoint
            return {
                "equipment": eq_code,
                "control_point": "cooling_setpoint",
                "target_value": 24.0,  # Relax setpoint when unoccupied
                "reason": f"Low occupancy ({occupancy_percent}%) - reduce active cooling",
                "description": "Increase setpoint to 24°C for energy efficiency",
                "savings": 8
            }
        elif occupancy_percent >= high_occupancy_threshold and hour >= 10 and hour <= 12:
            # Peak occupancy during peak solar hours: pre-cool
            return {
                "equipment": eq_code,
                "control_point": "cooling_setpoint",
                "target_value": 20.5,  # Pre-cool during peak demand
                "reason": f"High occupancy ({occupancy_percent}%) + peak demand - anticipatory pre-cooling",
                "description": "Reduce setpoint to 20.5°C for peak demand management",
                "savings": 5
            }
        elif context == "afternoon":
            # Afternoon: moderate adjustment
            return {
                "equipment": eq_code,
                "control_point": "cooling_setpoint",
                "target_value": 21.5,
                "reason": f"Afternoon optimization at {occupancy_percent}% occupancy",
                "description": "Adjust setpoint to 21.5°C for afternoon efficiency",
                "savings": 3
            }
        
        return None
    
    def _generate_dali_recommendation(self, eq_code: str, eq_type: str, context: str,
                                     occupancy_percent: int, daylight_factor: int, 
                                     zones_active: int, hour: int) -> Optional[Dict[str, Any]]:
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
            "description": f"Set Tridonic brightness to {brightness}% (daylight {daylight_factor}%, occupancy {occupancy_percent}%)",
            "savings": max(2, int(100 - brightness) / 10)  # Energy savings from dimming
        }

    async def _setpoint_change(self, point: str, value: float, reason: str):
        """Simulate a setpoint change."""
        self._emit_event(LifecycleEvent(
            timestamp=datetime.now(),
            simulated_hour=self.simulated_time.hour,
            event_type=EventType.SETPOINT_CHANGE,
            description=f"Setpoint change: {point} → {value}",
            details={"point": point, "value": value, "reason": reason}
        ))

    async def _inject_fault(self):
        """Inject a fault into equipment."""
        try:
            # Get equipment to fault (site-002 only)
            equipment_list = self.equipment_repo.get_all(building_id="site-002")
            if not equipment_list:
                logger.warning("No equipment available to fault")
                return

            # Filter by type if specified
            if self.current_scenario and self.current_scenario.fault_equipment_type:
                target_type = self.current_scenario.fault_equipment_type.lower()
                filtered = [
                    eq for eq in equipment_list
                    if target_type in (eq.get("equipment_type", "") or "").lower()
                    or target_type in (eq.get("code", "") or "").lower()
                ]
                if filtered:
                    equipment_list = filtered

            # Pick random equipment
            equipment = random.choice(equipment_list)
            eq_id = equipment.get("id")
            eq_code = equipment.get("code", eq_id)
            eq_name = equipment.get("name", eq_code)

            # Generate fault details
            fault_types = [
                ("High vibration detected", "vibration", 85),
                ("Temperature deviation", "temperature", 75),
                ("Pressure anomaly", "pressure", 70),
                ("Current draw elevated", "electrical", 80),
                ("Filter differential high", "filter", 65),
            ]
            fault_type, fault_category, severity = random.choice(fault_types)

            # Record fault
            fault_info = {
                "equipment_id": eq_id,
                "equipment_code": eq_code,
                "equipment_name": eq_name,
                "fault_type": fault_type,
                "fault_category": fault_category,
                "severity": severity,
                "fault_hour": self.simulated_time.hour,
                "detected_at": datetime.now().isoformat()
            }
            self.active_faults[eq_code] = fault_info

            # Emit fault event
            self._emit_event(LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=self.simulated_time.hour,
                event_type=EventType.EQUIPMENT_FAULT,
                equipment_id=eq_code,
                equipment_name=eq_name,
                description=f"{fault_type} on {eq_name}",
                details=fault_info
            ))

            # Degrade equipment health
            current_health = equipment.get("health_score", 80)
            new_health = max(30, current_health - random.randint(15, 30))

            self.equipment_repo.update(eq_code, {
                "health_score": new_health,
                "status": "warning" if new_health >= 50 else "critical"
            })

            # Create prediction in database
            await self._create_prediction(equipment, fault_info)

            # Generate alert
            await self._generate_alert(equipment, fault_info)

            # Schedule repair if auto_repair enabled
            if self.current_scenario and self.current_scenario.auto_repair:
                repair_hour = self.simulated_time.hour + self.current_scenario.repair_delay_hours
                if repair_hour >= 24:
                    repair_hour -= 24

                self.pending_repairs[eq_code] = {
                    **fault_info,
                    "scheduled_repair_hour": repair_hour,
                    "work_order_id": None
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
                "model_version": "lifecycle_sim_v1"
            }

            self.prediction_repo.create(prediction_data)

            self._emit_event(LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=self.simulated_time.hour,
                event_type=EventType.ALERT_GENERATED,
                equipment_id=fault_info["equipment_code"],
                equipment_name=fault_info["equipment_name"],
                description=f"ML prediction created: {fault_info['severity']}% failure probability",
                details={"prediction": prediction_data}
            ))

        except Exception as e:
            logger.error(f"Prediction creation error: {e}")

    async def _generate_alert(self, equipment: Dict, fault_info: Dict):
        """Generate alert and optionally notify Clawd."""
        try:
            # Create work order
            work_order = await self.work_order_repo.create_work_order({
                "equipment_id": equipment.get("id"),
                "title": f"Repair: {fault_info['fault_type']}",
                "description": f"Automated work order for {fault_info['equipment_name']}: {fault_info['fault_type']}",
                "priority": "high" if fault_info["severity"] >= 75 else "medium",
                "status": "scheduled",
                "created_by": "LIFECYCLE_SIM"
            })

            wo_code = work_order.get("code", "WO-SIM") if work_order else "WO-SIM"

            self._emit_event(LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=self.simulated_time.hour,
                event_type=EventType.WORK_ORDER_CREATED,
                equipment_id=fault_info["equipment_code"],
                equipment_name=fault_info["equipment_name"],
                description=f"Work order {wo_code} created",
                details={"work_order_code": wo_code, "priority": "high"}
            ))

            # Update pending repair with work order ID
            if fault_info["equipment_code"] in self.pending_repairs:
                self.pending_repairs[fault_info["equipment_code"]]["work_order_id"] = wo_code

            # Notify Clawd if enabled
            if self.current_scenario and self.current_scenario.clawd_notifications:
                await self._notify_clawd(equipment, fault_info, wo_code)

        except Exception as e:
            logger.error(f"Alert generation error: {e}")

    async def _notify_clawd(self, equipment: Dict, fault_info: Dict, work_order_code: str):
        """Send notification to Clawd bot."""
        try:
            from app.services.clawd_integration.work_order_notifier import notify_technician_of_work_order

            # This would send actual Telegram message
            # For simulation, we just log it
            logger.info(f"[CLAWD] Notification sent for {work_order_code}: {fault_info['fault_type']}")

            self._emit_event(LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=self.simulated_time.hour,
                event_type=EventType.TECHNICIAN_DISPATCHED,
                equipment_id=fault_info["equipment_code"],
                equipment_name=fault_info["equipment_name"],
                description=f"Technician notified via Clawd for {work_order_code}",
                details={"notification_method": "telegram", "work_order": work_order_code}
            ))

        except Exception as e:
            logger.warning(f"Clawd notification skipped: {e}")

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
        """Simulate technician completing repair."""
        try:
            # Emit repair started
            self._emit_event(LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=self.simulated_time.hour,
                event_type=EventType.REPAIR_COMPLETED,
                equipment_id=eq_code,
                equipment_name=repair_info.get("equipment_name"),
                description=f"Technician completed repair on {repair_info.get('equipment_name')}",
                details={"fault_type": repair_info.get("fault_type")}
            ))

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
                work_order_id=work_order_id,
                equipment_id=equipment_id,
                equipment_code=eq_code,
                service_type="breakdown"
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
                    notes="Post-repair vibration within normal range"
                )
            elif fault_category == "temperature":
                await self.feedback_service.submit_feedback_item(
                    session.session_id,
                    "temperature",
                    22.5,
                    FeedbackItemType.READING,
                    unit="°C",
                    notes="Temperature stable after repair"
                )

            # Submit observation
            await self.feedback_service.submit_feedback_item(
                session.session_id,
                "observation",
                f"Repaired {repair_info.get('fault_type')}. Equipment operating normally.",
                FeedbackItemType.OBSERVATION,
                notes="Repair successful"
            )

            # Complete session (force=True to skip missing items)
            result = await self.feedback_service.complete_feedback_session(
                session.session_id,
                force=True
            )

            self._emit_event(LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=self.simulated_time.hour,
                event_type=EventType.FEEDBACK_SUBMITTED,
                equipment_id=eq_code,
                equipment_name=repair_info.get("equipment_name"),
                description=f"Service feedback submitted: health +{result.get('health_score_change', 0)}",
                details={
                    "session_id": session.session_id,
                    "health_change": result.get("health_score_change", 0),
                    "items_collected": result.get("items_collected", 0)
                }
            ))

            # Emit health restored event
            self._emit_event(LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=self.simulated_time.hour,
                event_type=EventType.HEALTH_RESTORED,
                equipment_id=eq_code,
                equipment_name=repair_info.get("equipment_name"),
                description=f"Equipment health restored for {repair_info.get('equipment_name')}",
                details={"new_status": "normal"}
            ))

            # Resolve predictions
            equipment = self.equipment_repo.get_by_id(eq_code)
            if equipment:
                self.prediction_repo.resolve_by_equipment(equipment.get("id"))

            self._emit_event(LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=self.simulated_time.hour,
                event_type=EventType.ALERT_RESOLVED,
                equipment_id=eq_code,
                equipment_name=repair_info.get("equipment_name"),
                description=f"Alert resolved for {repair_info.get('equipment_name')}",
                details={}
            ))

        except Exception as e:
            logger.error(f"Service feedback submission error: {e}")

    def serialize_state(self) -> Dict[str, Any]:
        """
        Serialize orchestrator state to JSON-serializable dict for database storage.
        Enables crash recovery by preserving simulation state.
        
        Returns:
            Dict with: simulated_time, days_simulated, active_faults, pending_repairs, recent_events, time_multiplier, occupancy_seed
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
            return False  # No task_id means not a queued task
            
        try:
            from app.database.supabase_client import Supabase
            
            state_snapshot = self.serialize_state()
            
            # Update task in database with checkpoint
            result = await Supabase.instance().client.table("lifecycle_simulation_tasks") \
                .update({
                    "state_snapshot": state_snapshot,
                    "progress_pct": int((self.days_simulated / 365) * 100) if self.seasonal_modeler else 0,
                    "days_completed": self.days_simulated,
                }) \
                .eq("task_id", str(self.task_id)) \
                .execute()
            
            logger.info(f"Checkpoint saved for task {self.task_id}: day {self.days_simulated}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            return False


def create_lifecycle_orchestrator(task_id: Optional[str] = None) -> LifecycleOrchestrator:
    """
    Create a new lifecycle orchestrator instance.

    Args:
        task_id: Optional task ID for database-backed task tracking

    Returns:
        New LifecycleOrchestrator instance
    """
    return LifecycleOrchestrator(task_id=task_id)


# Global singleton instance
_orchestrator_instance: Optional[LifecycleOrchestrator] = None


def get_lifecycle_orchestrator() -> LifecycleOrchestrator:
    """
    Get or create the global lifecycle orchestrator singleton.

    Returns:
        Singleton LifecycleOrchestrator instance
    """
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = LifecycleOrchestrator()
        logger.info("Created lifecycle orchestrator singleton")
    return _orchestrator_instance
