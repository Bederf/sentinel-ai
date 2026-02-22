"""Autonomous Decision Engine for bounded autonomy system.

This service implements the core decision engine that evaluates and executes
approved rules automatically within strict safety boundaries.
"""

import logging
import uuid
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable

from app.models.autonomous_decision import (
    AutonomousDecision,
    DecisionStatus,
    EscalationLevel,
    BoundaryStatus,
    AutonomousSystemStatus,
)
from app.models.audit_log import AuditResultType
from app.services.safety_interlocks import safety_engine
from app.services.device_abstraction import device_manager

logger = logging.getLogger(__name__)

# Data directory
DATA_DIR = Path(__file__).parent.parent / "data"
DECISION_HISTORY_FILE = DATA_DIR / "autonomous_decisions.json"


class AutonomousDecisionEngine:
    """Engine for evaluating and executing autonomous decisions within safety boundaries."""

    def __init__(self):
        """Initialize the autonomous decision engine."""
        self.enabled = False
        self.decision_history: List[AutonomousDecision] = []
        self.active_decisions: Dict[str, AutonomousDecision] = {}
        self.boundary_status_cache: Dict[str, BoundaryStatus] = {}
        self._initialized = False
        self._decision_callbacks: List[Callable] = []

    async def initialize(self, load_demo_data: bool = True) -> None:
        """Initialize the autonomous decision engine."""
        if self._initialized:
            return

        logger.info("Initializing AutonomousDecisionEngine")

        # Initialize safety engine if not already done
        if not safety_engine._initialized:
            await safety_engine.initialize()

        # Load decision history
        if load_demo_data:
            await self._load_decision_history()

        self._initialized = True
        logger.info("AutonomousDecisionEngine initialized")

    async def _load_decision_history(self) -> None:
        """Load decision history from JSON file."""
        try:
            if not DECISION_HISTORY_FILE.exists():
                logger.info("No decision history file found, creating demo data")
                await self._create_demo_decisions()
                return

            with open(DECISION_HISTORY_FILE) as f:
                history_data = json.load(f)

            self.decision_history = [AutonomousDecision.from_dict(decision_data) for decision_data in history_data]

            logger.info(f"Loaded {len(self.decision_history)} decisions from history")
        except Exception as e:
            logger.error(f"Failed to load decision history: {e}")
            await self._create_demo_decisions()

    async def _create_demo_decisions(self) -> None:
        """Create demo autonomous decisions for demonstration."""
        from datetime import timedelta

        decisions = [
            {
                "id": "auto_001",
                "timestamp": datetime.now() - timedelta(hours=2),
                "device_id": "hvac_001",
                "device_name": "Zone Controller 1",
                "point_name": "cooling_setpoint",
                "current_value": 22.0,
                "target_value": 23.5,
                "decision_rationale": "Outdoor temperature rising to 29°C, increasing setpoint 1.5°C for energy savings while maintaining comfort",
                "rule_triggered": "temp_optimization_rule",
                "safety_validation": {
                    "allowed": True,
                    "reasons": [],
                    "warnings": [],
                    "rule_results": [
                        {
                            "rule_id": "temp_hvac_safe_range",
                            "allowed": True,
                            "message": "Temperature within safe range (16-28°C)",
                        }
                    ],
                },
                "status": DecisionStatus.SUCCESS,
                "result": AuditResultType.SUCCESS,
                "execution_time_ms": 250.5,
                "escalation_level": EscalationLevel.NONE,
                "metadata": {
                    "energy_savings_kwh": 8.5,
                    "cost_savings_zar": 21.25,
                    "outdoor_temp": 29.0,
                },
            },
            {
                "id": "auto_002",
                "timestamp": datetime.now() - timedelta(hours=1, minutes=30),
                "device_id": "lighting_001",
                "device_name": "Office Lighting Zone 1",
                "point_name": "brightness",
                "current_value": 85.0,
                "target_value": 75.0,
                "decision_rationale": "Occupancy sensors indicate low activity, reducing brightness 10% for energy conservation",
                "rule_triggered": "occupancy_based_optimization",
                "safety_validation": {
                    "allowed": True,
                    "warnings": ["Brightness reduction near safety limit (90%)"],
                    "rule_results": [
                        {
                            "rule_id": "lighting_brightness_max",
                            "allowed": True,
                            "warning": True,
                            "message": "Brightness at 83% of maximum allowed (90%)",
                        }
                    ],
                },
                "status": DecisionStatus.SUCCESS,
                "result": AuditResultType.SUCCESS,
                "execution_time_ms": 180.0,
                "escalation_level": EscalationLevel.WARNING,
                "metadata": {
                    "energy_savings_kwh": 2.1,
                    "cost_savings_zar": 5.25,
                    "occupancy_level": "low",
                },
            },
            {
                "id": "auto_003",
                "timestamp": datetime.now() - timedelta(minutes=45),
                "device_id": "hvac_002",
                "device_name": "Chiller System 1",
                "point_name": "supply_temp_setpoint",
                "current_value": 7.0,
                "target_value": 8.5,
                "decision_rationale": "Increasing CHW temperature for chiller efficiency optimization based on load conditions",
                "rule_triggered": "chiller_efficiency_rule",
                "safety_validation": {
                    "allowed": True,
                    "reasons": [],
                    "warnings": [],
                    "rule_results": [
                        {
                            "rule_id": "temp_chiller_min",
                            "allowed": True,
                            "message": "Chiller supply temp above minimum 5°C",
                        }
                    ],
                },
                "status": DecisionStatus.SUCCESS,
                "result": AuditResultType.SUCCESS,
                "execution_time_ms": 320.0,
                "escalation_level": EscalationLevel.NONE,
                "metadata": {
                    "energy_savings_kwh": 15.2,
                    "cost_savings_zar": 38.0,
                    "chiller_load": 65,
                },
            },
            {
                "id": "auto_004",
                "timestamp": datetime.now() - timedelta(minutes=30),
                "device_id": "hvac_003",
                "device_name": "Zone Controller 2",
                "point_name": "cooling_setpoint",
                "current_value": 22.0,
                "target_value": 25.0,
                "decision_rationale": "Peak demand period detected, implementing load shedding by increasing setpoint 3°C",
                "rule_triggered": "peak_demand_shedding",
                "safety_validation": {
                    "allowed": False,
                    "reasons": ["Target temperature 25°C exceeds safe maximum 24°C by 1°C"],
                    "warnings": ["High outdoor temperature may affect comfort"],
                    "rule_results": [
                        {
                            "rule_id": "temp_hvac_safe_range",
                            "allowed": False,
                            "message": "Temperature 25°C exceeds maximum allowed 24°C",
                        }
                    ],
                },
                "status": DecisionStatus.BLOCKED,
                "result": AuditResultType.BLOCKED,
                "execution_time_ms": 95.0,
                "escalation_level": EscalationLevel.ALERT,
                "metadata": {
                    "blocked_reason": "Safety limit exceeded",
                    "operator_notified": True,
                },
            },
            {
                "id": "auto_005",
                "timestamp": datetime.now() - timedelta(minutes=20),
                "device_id": "hvac_004",
                "device_name": "Chiller System 2",
                "point_name": "supply_temp_setpoint",
                "current_value": 7.0,
                "target_value": 9.5,
                "decision_rationale": "Testing upper boundary of chiller supply temperature for maximum efficiency",
                "rule_triggered": "boundary_test_rule",
                "safety_validation": {
                    "allowed": False,
                    "reasons": ["Target 9.5°C is too close to freeze limit. Minimum 5°C"],
                    "warnings": [
                        "Attempting to operate outside recommended range",
                        "Risk of equipment damage",
                    ],
                    "rule_results": [
                        {
                            "rule_id": "temp_chiller_min",
                            "allowed": False,
                            "message": "Chiller supply temp 9.5°C is too close to boundary 5°C",
                        }
                    ],
                },
                "status": DecisionStatus.BLOCKED,
                "result": AuditResultType.BLOCKED,
                "execution_time_ms": 110.0,
                "escalation_level": EscalationLevel.CRITICAL,
                "metadata": {
                    "blocked_reason": "Equipment safety limit",
                    "emergency_review_required": True,
                },
            },
            {
                "id": "auto_006",
                "timestamp": datetime.now() - timedelta(minutes=10),
                "device_id": "lighting_002",
                "device_name": "Office Lighting Zone 2",
                "point_name": "brightness",
                "current_value": 70.0,
                "target_value": 68.0,
                "decision_rationale": "Minor brightness adjustment based on natural light availability",
                "rule_triggered": "daylight_harvesting",
                "safety_validation": {
                    "allowed": True,
                    "reasons": [],
                    "warnings": [],
                    "rule_results": [
                        {
                            "rule_id": "lighting_brightness_max",
                            "allowed": True,
                            "message": "Brightness 75% well within safe limit 90%",
                        }
                    ],
                },
                "status": DecisionStatus.SUCCESS,
                "result": AuditResultType.SUCCESS,
                "execution_time_ms": 155.0,
                "escalation_level": EscalationLevel.NONE,
                "metadata": {
                    "energy_savings_kwh": 0.8,
                    "cost_savings_zar": 2.0,
                    "natural_light_lux": 450,
                },
            },
            {
                "id": "auto_007",
                "timestamp": datetime.now() - timedelta(minutes=5),
                "device_id": "hvac_005",
                "device_name": "Chiller System 3",
                "point_name": "runtime",
                "current_value": 0,
                "target_value": 1,  # Start chiller
                "decision_rationale": "Rising building load requires additional chiller capacity",
                "rule_triggered": "load_based_staging",
                "safety_validation": {
                    "allowed": False,
                    "reasons": ["Chiller must run minimum 5 minutes before restart"],
                    "warnings": [],
                    "rule_results": [
                        {
                            "rule_id": "chiller_runtime_limit",
                            "allowed": False,
                            "message": "Chiller stopped 2 minutes ago, minimum 5 min required",
                        }
                    ],
                },
                "status": DecisionStatus.BLOCKED,
                "result": AuditResultType.BLOCKED,
                "execution_time_ms": 65.0,
                "escalation_level": EscalationLevel.WARNING,
                "metadata": {
                    "blocked_reason": "Runtime protection active",
                    "time_remaining_minutes": 3,
                },
            },
        ]

        # Convert datetime objects to ISO strings and enums to their values for from_dict
        for d in decisions:
            if isinstance(d.get("timestamp"), datetime):
                d["timestamp"] = d["timestamp"].isoformat()
            if hasattr(d.get("status"), "value"):
                d["status"] = d["status"].value
            if hasattr(d.get("result"), "value"):
                d["result"] = d["result"].value
            if hasattr(d.get("escalation_level"), "value"):
                d["escalation_level"] = d["escalation_level"].value

        self.decision_history = [AutonomousDecision.from_dict(decision) for decision in decisions]

        # Save to file
        await self._save_decision_history()

    async def _save_decision_history(self) -> None:
        """Save decision history to JSON file."""
        try:
            history_data = [decision.to_dict() for decision in self.decision_history]

            with open(DECISION_HISTORY_FILE, "w") as f:
                json.dump(history_data, f, indent=2)

            logger.info(f"Saved {len(history_data)} decisions to {DECISION_HISTORY_FILE}")
        except Exception as e:
            logger.error(f"Failed to save decision history: {e}")

    async def evaluate_and_execute(
        self, rule_id: str, device_id: str, point_name: str, target_value: float, decision_rationale: str
    ) -> AutonomousDecision:
        """Evaluate a rule and execute the decision if safe."""
        start_time = datetime.now()

        # Get device information
        devices = await device_manager.list_devices()
        device = next((d for d in devices if d.id == device_id), None)

        if not device:
            raise ValueError(f"Device {device_id} not found")

        # Get current value
        current_point = device.points.get(point_name)
        if not current_point:
            raise ValueError(f"Point {point_name} not found on device {device_id}")

        current_value = current_point.value or current_point.default_value or 0

        # Create decision record
        decision = AutonomousDecision(
            id=f"auto_{uuid.uuid4().hex[:8]}",
            timestamp=start_time,
            device_id=device_id,
            device_name=device.name,
            point_name=point_name,
            current_value=current_value,
            target_value=target_value,
            decision_rationale=decision_rationale,
            rule_triggered=rule_id,
            safety_validation={},
            status=DecisionStatus.PENDING,
            result=None,
            execution_time_ms=None,
            escalation_level=EscalationLevel.NONE,
        )

        # Perform safety validation
        safety_result = await safety_engine.validate_control(device, point_name, target_value)
        decision.safety_validation = safety_result

        # Determine escalation level based on boundary approach
        if safety_result.get("allowed", False) and safety_result.get("warnings"):
            decision.escalation_level = EscalationLevel.WARNING

        if not safety_result.get("allowed", False):
            # Safety validation failed
            decision.status = DecisionStatus.BLOCKED
            decision.result = AuditResultType.BLOCKED
            decision.execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            decision.metadata["blocked_reason"] = "Safety validation failed"

            self.decision_history.append(decision)
            await self._save_decision_history()

            logger.warning(
                f"Decision {decision.id} BLOCKED - Safety validation failed: {safety_result.get('reasons', [])}"
            )

            # Notify callbacks
            await self._notify_decision_callbacks(decision)
            return decision

        # Safety validation passed - execute the decision
        decision.status = DecisionStatus.EXECUTING
        self.active_decisions[decision.id] = decision

        try:
            # Execute the control action
            result = await device_manager.write_device_value(device_id, point_name, target_value)

            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            decision.execution_time_ms = execution_time

            if result.get("success", False):
                decision.status = DecisionStatus.SUCCESS
                decision.result = AuditResultType.SUCCESS
                decision.metadata.update(result.get("metadata", {}))

                logger.info(
                    f"Decision {decision.id} SUCCESS - "
                    f"{device.name} {point_name}: {current_value} -> {target_value} "
                    f"(execution: {execution_time:.1f}ms)"
                )
            else:
                decision.status = DecisionStatus.FAILED
                decision.result = AuditResultType.FAILED
                decision.metadata["error"] = result.get("error", "Unknown error")

                logger.error(
                    f"Decision {decision.id} FAILED - "
                    f"{device.name} {point_name}: {result.get('error', 'Unknown error')}"
                )

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            decision.execution_time_ms = execution_time
            decision.status = DecisionStatus.FAILED
            decision.result = AuditResultType.FAILED
            decision.metadata["error"] = str(e)

            logger.error(f"Decision {decision.id} EXCEPTION - {str(e)}")

        finally:
            # Remove from active decisions
            if decision.id in self.active_decisions:
                del self.active_decisions[decision.id]

            # Add to history
            self.decision_history.append(decision)
            if len(self.decision_history) > 1000:  # Keep last 1000 decisions
                self.decision_history = self.decision_history[-1000:]

            await self._save_decision_history()

        # Notify callbacks
        await self._notify_decision_callbacks(decision)

        return decision

    async def add_decision_callback(self, callback: Callable[[AutonomousDecision], None]) -> None:
        """Add a callback to be notified when decisions are made."""
        self._decision_callbacks.append(callback)

    async def _notify_decision_callbacks(self, decision: AutonomousDecision) -> None:
        """Notify all registered callbacks about a new decision."""
        for callback in self._decision_callbacks:
            try:
                await callback(decision)
            except Exception as e:
                logger.error(f"Error in decision callback: {e}")

    def get_decision_history(
        self,
        limit: int = 100,
        offset: int = 0,
        device_id: Optional[str] = None,
        status: Optional[DecisionStatus] = None,
    ) -> List[AutonomousDecision]:
        """Get decision history with optional filtering."""
        filtered_decisions = self.decision_history

        if device_id:
            filtered_decisions = [d for d in filtered_decisions if d.device_id == device_id]

        if status:
            filtered_decisions = [d for d in filtered_decisions if d.status == status]

        return filtered_decisions[-(offset + limit) : -offset] if offset > 0 else filtered_decisions[-limit:]

    async def get_system_status(self) -> AutonomousSystemStatus:
        """Get current status of the autonomous system."""
        # Calculate success rate from recent history
        recent_decisions = self.get_decision_history(limit=50)
        successful = len([d for d in recent_decisions if d.status == DecisionStatus.SUCCESS])
        success_rate = (successful / len(recent_decisions) * 100) if recent_decisions else 0.0

        # Determine current escalation level (highest from active decisions)
        current_escalation = EscalationLevel.NONE
        for decision in self.active_decisions.values():
            if decision.escalation_level.value > current_escalation.value:
                current_escalation = decision.escalation_level

        # Calculate safety score (based on recent blocked/failed decisions)
        blocked_failed = len(
            [d for d in recent_decisions if d.status in (DecisionStatus.BLOCKED, DecisionStatus.FAILED)]
        )
        safety_score = max(0.0, 100.0 - (blocked_failed * 10.0))

        last_decision_time = None
        if self.decision_history:
            last_decision_time = self.decision_history[-1].timestamp

        return AutonomousSystemStatus(
            enabled=self.enabled,
            active_decisions=len(self.active_decisions),
            total_decisions_today=len([d for d in recent_decisions if d.timestamp.date() == datetime.now().date()]),
            success_rate=success_rate,
            current_escalation_level=current_escalation,
            last_decision_time=last_decision_time,
            safety_score=safety_score,
        )

    def enable_autonomous_mode(self) -> Dict[str, Any]:
        """Enable autonomous mode."""
        if self.enabled:
            return {"success": False, "message": "Autonomous mode already enabled"}

        self.enabled = True
        logger.info("Autonomous mode ENABLED")

        return {"success": True, "message": "Autonomous mode enabled successfully"}

    def disable_autonomous_mode(self) -> Dict[str, Any]:
        """Disable autonomous mode and cancel active decisions."""
        if not self.enabled:
            return {"success": False, "message": "Autonomous mode already disabled"}

        self.enabled = False

        # Cancel any active decisions
        cancelled_count = 0
        for decision in list(self.active_decisions.values()):
            decision.status = DecisionStatus.CANCELLED
            decision.result = AuditResultType.CANCELLED
            cancelled_count += 1

        self.active_decisions.clear()

        logger.info(f"Autonomous mode DISABLED - Cancelled {cancelled_count} active decisions")

        return {
            "success": True,
            "message": f"Autonomous mode disabled - Cancelled {cancelled_count} active decisions",
            "cancelled_decisions": cancelled_count,
        }


# Global instance
autonomous_decision_engine = AutonomousDecisionEngine()
