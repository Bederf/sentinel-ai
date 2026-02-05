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
from app.services.feedback_collection_service import (
    get_feedback_collection_service,
    FeedbackItemType,
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

    def __init__(self):
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
        self._task: Optional[asyncio.Task] = None
        self._callbacks: List[Callable[[LifecycleEvent], None]] = []

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
        start_hour: int = 0
    ) -> Dict[str, Any]:
        """
        Start the 24-hour simulation.

        Args:
            scenario: Scenario name from SCENARIOS
            duration_minutes: Real-time duration (24 = 1 min per hour)
            start_hour: Simulated hour to start (0-23)

        Returns:
            Status dict with session info
        """
        if self.running:
            return {"success": False, "error": "Simulation already running"}

        # Get scenario config
        self.current_scenario = SCENARIOS.get(scenario, SCENARIOS["fault_day"])

        # Calculate time multiplier
        # duration_minutes for full 24 hours
        # So 1 simulated hour = duration_minutes / 24 real minutes
        self.time_multiplier = (duration_minutes / 24.0) * 60.0  # seconds per simulated hour

        # Initialize time
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

            while self.running:
                if self.paused:
                    await asyncio.sleep(0.5)
                    continue

                current_hour = self.simulated_time.hour

                # Process hour change
                if current_hour != last_hour:
                    await self._process_hour(current_hour)
                    last_hour = current_hour

                # Advance time
                await asyncio.sleep(self.time_multiplier / 60)  # Sleep for 1 simulated minute
                self.simulated_time += timedelta(minutes=1)

                # Check for day rollover
                if self.simulated_time.hour == 0 and last_hour == 23:
                    logger.info("24-hour cycle complete, continuing...")
                    # Could stop here or continue cycling

        except asyncio.CancelledError:
            logger.info("Simulation cancelled")
        except Exception as e:
            logger.error(f"Simulation error: {e}")
            self.running = False

    async def _process_hour(self, hour: int):
        """Process events for the given simulated hour."""
        logger.info(f"Processing simulated hour: {hour:02d}:00")

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

        # Check for random faults based on probability
        if self.current_scenario and random.random() < (self.current_scenario.fault_probability / 24):
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
        """Simulate morning occupancy increase."""
        self._emit_event(LifecycleEvent(
            timestamp=datetime.now(),
            simulated_hour=8,
            event_type=EventType.OCCUPANCY_INCREASE,
            description="Occupancy increasing - staff arriving",
            details={"occupancy_percent": 60, "zones_active": 12}
        ))

        # Adjust setpoints for occupancy
        await self._setpoint_change("cooling_setpoint", 22.0, "Occupied mode")
        await self._setpoint_change("lighting_level", 80, "Occupied mode")

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
        """Simulate evening occupancy decrease."""
        self._emit_event(LifecycleEvent(
            timestamp=datetime.now(),
            simulated_hour=18,
            event_type=EventType.OCCUPANCY_DECREASE,
            description="Occupancy decreasing - staff leaving",
            details={"occupancy_percent": 20, "zones_active": 4}
        ))

        # Adjust setpoints for reduced occupancy
        await self._setpoint_change("cooling_setpoint", 25.0, "Unoccupied mode")
        await self._setpoint_change("lighting_level", 30, "Unoccupied mode")

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
        """Simulate AI optimization cycle."""
        # Get a sample of equipment to "optimize"
        try:
            equipment_list = self.equipment_repo.get_all()[:5]
            optimized = []

            for eq in equipment_list:
                if random.random() < 0.3:  # 30% chance to optimize each
                    optimized.append({
                        "equipment": eq.get("code", eq.get("id")),
                        "adjustment": random.choice([
                            "Reduced fan speed 10%",
                            "Adjusted setpoint +0.5°C",
                            "Optimized staging",
                            "Enabled economizer"
                        ])
                    })

            self._emit_event(LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=self.simulated_time.hour,
                event_type=EventType.AI_OPTIMIZATION,
                description=f"AI optimization cycle ({context})",
                details={
                    "context": context,
                    "equipment_analyzed": len(equipment_list),
                    "optimizations_applied": len(optimized),
                    "changes": optimized
                }
            ))
        except Exception as e:
            logger.warning(f"AI optimization error: {e}")

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
            # Get equipment to fault
            equipment_list = self.equipment_repo.get_all()
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


# Singleton instance
_orchestrator: Optional[LifecycleOrchestrator] = None


def get_lifecycle_orchestrator() -> LifecycleOrchestrator:
    """Get singleton lifecycle orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = LifecycleOrchestrator()
    return _orchestrator
