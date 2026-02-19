"""Measurement & Verification (M&V) Service for AI Recommendations.

Verifies that applied optimization recommendations produce the expected
energy savings by comparing predicted vs actual consumption after execution.

Workflow:
1. When a recommendation is auto-applied or approved, record a verification
   task with the predicted impact and a measurement window.
2. After the measurement window elapses, query actual energy readings.
3. Compare predicted vs actual, compute accuracy score.
4. Store Outcome for feedback loop to recommendation scorer.
5. If variance exceeds rollback threshold, flag for rollback.

M&V windows vary by action type:
- Lighting dimming: 30 min (immediate effect)
- HVAC setpoint change: 2 hours (thermal response)
- Chiller CHW temp: 3 hours (thermal inertia)
- BESS dispatch: 15 min (immediate power effect)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models.outcome import Outcome
from app.models.audit_log import AuditResultType

logger = logging.getLogger(__name__)

# Storage for pending verifications (JSON file in demo mode)
DATA_DIR = Path(__file__).parent.parent / "data"
MV_FILE = DATA_DIR / "mv_verifications.json"

# Measurement windows by recommendation system type (hours)
MEASUREMENT_WINDOWS = {
    "lighting": 0.5,
    "hvac": 2.0,
    "chiller": 3.0,
    "bess": 0.25,
    "power": 1.0,
    "solar": 1.0,
    "default": 2.0,
}

# Variance thresholds
ENERGY_VARIANCE_WARNING_PCT = 10.0  # >10% = warning
ENERGY_VARIANCE_ROLLBACK_PCT = 25.0  # >25% = recommend rollback
COMFORT_VIOLATION_THRESHOLD_C = 1.5  # >1.5C deviation from setpoint = comfort issue


@dataclass
class VerificationTask:
    """A pending M&V verification for a recommendation that was applied."""

    id: str
    site_id: str
    recommendation_id: str
    applied_at: str  # ISO timestamp
    measurement_window_hours: float
    verify_after: str  # ISO timestamp (applied_at + window)
    status: str = "pending"  # pending, verified, failed, rolled_back
    predicted_savings_kwh: float = 0.0
    predicted_savings_zar: float = 0.0
    baseline_power_kw: Optional[float] = None
    recommendation_systems: List[str] = field(default_factory=list)
    setpoints_applied: List[Dict[str, Any]] = field(default_factory=list)
    # Filled after verification
    actual_power_kw: Optional[float] = None
    actual_savings_kwh: Optional[float] = None
    actual_savings_zar: Optional[float] = None
    accuracy: Optional[float] = None
    variance_pct: Optional[float] = None
    comfort_violations: List[Dict[str, Any]] = field(default_factory=list)
    verified_at: Optional[str] = None
    rollback_recommended: bool = False
    notes: str = ""
    # Routing metadata (Phase 82-03): populated when routing is active
    routing_tier: Optional[str] = None
    control_tier: Optional[str] = None
    effective_confidence: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "site_id": self.site_id,
            "recommendation_id": self.recommendation_id,
            "applied_at": self.applied_at,
            "measurement_window_hours": self.measurement_window_hours,
            "verify_after": self.verify_after,
            "status": self.status,
            "predicted_savings_kwh": self.predicted_savings_kwh,
            "predicted_savings_zar": self.predicted_savings_zar,
            "baseline_power_kw": self.baseline_power_kw,
            "recommendation_systems": self.recommendation_systems,
            "setpoints_applied": self.setpoints_applied,
            "actual_power_kw": self.actual_power_kw,
            "actual_savings_kwh": self.actual_savings_kwh,
            "actual_savings_zar": self.actual_savings_zar,
            "accuracy": self.accuracy,
            "variance_pct": self.variance_pct,
            "comfort_violations": self.comfort_violations,
            "verified_at": self.verified_at,
            "rollback_recommended": self.rollback_recommended,
            "notes": self.notes,
            "routing_tier": self.routing_tier,
            "control_tier": self.control_tier,
            "effective_confidence": self.effective_confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VerificationTask":
        return cls(
            id=data.get("id", ""),
            site_id=data.get("site_id", ""),
            recommendation_id=data.get("recommendation_id", ""),
            applied_at=data.get("applied_at", ""),
            measurement_window_hours=data.get("measurement_window_hours", 2.0),
            verify_after=data.get("verify_after", ""),
            status=data.get("status", "pending"),
            predicted_savings_kwh=data.get("predicted_savings_kwh", 0.0),
            predicted_savings_zar=data.get("predicted_savings_zar", 0.0),
            baseline_power_kw=data.get("baseline_power_kw"),
            recommendation_systems=data.get("recommendation_systems", []),
            setpoints_applied=data.get("setpoints_applied", []),
            actual_power_kw=data.get("actual_power_kw"),
            actual_savings_kwh=data.get("actual_savings_kwh"),
            actual_savings_zar=data.get("actual_savings_zar"),
            accuracy=data.get("accuracy"),
            variance_pct=data.get("variance_pct"),
            comfort_violations=data.get("comfort_violations", []),
            verified_at=data.get("verified_at"),
            rollback_recommended=data.get("rollback_recommended", False),
            notes=data.get("notes", ""),
            routing_tier=data.get("routing_tier"),
            control_tier=data.get("control_tier"),
            effective_confidence=data.get("effective_confidence"),
        )


class MVVerificationService:
    """Service for tracking and verifying optimization recommendation outcomes."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._tasks: List[VerificationTask] = []
        self._outcomes: List[Outcome] = []
        self._load()
        self._initialized = True

    def _load(self):
        """Load pending verifications from JSON file."""
        if MV_FILE.exists():
            try:
                with open(MV_FILE) as f:
                    data = json.load(f)
                self._tasks = [VerificationTask.from_dict(t) for t in data.get("tasks", [])]
                self._outcomes = [Outcome.from_dict(o) for o in data.get("outcomes", [])]
            except Exception as e:
                logger.warning(f"Failed to load M&V data: {e}")
                self._tasks = []
                self._outcomes = []

    def _save(self):
        """Persist verifications and outcomes to JSON file."""
        try:
            data = {
                "tasks": [t.to_dict() for t in self._tasks[-200:]],
                "outcomes": [o.to_dict() for o in self._outcomes[-200:]],
                "last_updated": datetime.now().isoformat(),
            }
            with open(MV_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save M&V data: {e}")

    def record_applied_recommendation(
        self,
        site_id: str,
        recommendation_id: str,
        projected_savings: Dict[str, Any],
        setpoints_applied: List[Dict[str, Any]],
        recommendation_systems: Optional[List[str]] = None,
        routing_metadata: Optional[Dict[str, Any]] = None,
    ) -> VerificationTask:
        """Record a verification task when a recommendation is applied.

        Args:
            site_id: Site where recommendation was applied
            recommendation_id: Unique recommendation identifier
            projected_savings: Dict with energy_kwh, cost_zar_per_hour, etc.
            setpoints_applied: List of {device_id, point_name, old_value, new_value}
            recommendation_systems: List of system types (hvac, lighting, bess, etc.)
            routing_metadata: Optional dict with routing_tier, control_tier,
                effective_confidence from the tier router

        Returns:
            Created VerificationTask
        """
        # Determine measurement window from the longest-acting system
        systems = recommendation_systems or ["default"]
        window = max(MEASUREMENT_WINDOWS.get(s, 2.0) for s in systems)

        now = datetime.now()
        task_id = f"mv-{site_id}-{now.strftime('%Y%m%d%H%M%S')}"
        baseline_power_kw = None

        # Capture baseline site power at the moment the recommendation is applied.
        # This allows savings variance to compare savings-to-savings (not savings vs consumption).
        try:
            from app.services.energy_centre_service import get_energy_centre_service

            energy_svc = get_energy_centre_service()
            summary = energy_svc.get_power_summary(site_id)
            if summary:
                baseline = summary.get("total_power_kw")
                if isinstance(baseline, (int, float)):
                    baseline_power_kw = float(baseline)
        except Exception as e:
            logger.warning(f"M&V: Could not capture baseline power for {site_id}: {e}")

        # Extract routing metadata fields if provided
        routing_tier = None
        control_tier_val = None
        effective_confidence = None
        if routing_metadata:
            routing_tier = routing_metadata.get("routing_tier")
            control_tier_val = routing_metadata.get("control_tier")
            effective_confidence = routing_metadata.get("effective_confidence")

        task = VerificationTask(
            id=task_id,
            site_id=site_id,
            recommendation_id=recommendation_id,
            applied_at=now.isoformat(),
            measurement_window_hours=window,
            verify_after=(now + timedelta(hours=window)).isoformat(),
            predicted_savings_kwh=projected_savings.get("energy_kwh", 0) or projected_savings.get("total_kwh", 0),
            predicted_savings_zar=projected_savings.get("cost_zar_per_hour", 0),
            baseline_power_kw=baseline_power_kw,
            recommendation_systems=systems,
            setpoints_applied=setpoints_applied,
            routing_tier=routing_tier,
            control_tier=control_tier_val,
            effective_confidence=effective_confidence,
        )

        self._tasks.append(task)
        self._save()

        logger.info(
            f"M&V task {task_id} created for site {site_id}: "
            f"verify after {window}h, predicted {task.predicted_savings_kwh:.1f} kWh, "
            f"baseline {baseline_power_kw if baseline_power_kw is not None else 'n/a'} kW"
        )
        return task

    async def run_pending_verifications(self) -> List[VerificationTask]:
        """Check and verify any tasks whose measurement window has elapsed.

        This should be called periodically (e.g., every 15 minutes) by a
        background job or scheduler.

        Returns:
            List of newly verified tasks
        """
        now = datetime.now()
        verified = []

        for task in self._tasks:
            if task.status != "pending":
                continue

            try:
                verify_after = datetime.fromisoformat(task.verify_after)
            except (ValueError, TypeError):
                continue

            if now < verify_after:
                continue  # Not yet time

            # Time to verify
            try:
                await self._verify_task(task)
                verified.append(task)
            except Exception as e:
                logger.error(f"M&V verification failed for {task.id}: {e}")
                task.status = "failed"
                task.notes = f"Verification error: {e}"

        if verified:
            self._save()
            logger.info(f"M&V: verified {len(verified)} tasks")

        return verified

    async def _verify_task(self, task: VerificationTask):
        """Verify a single task by comparing predicted vs actual energy.

        Reads actual energy data from energy centre meters and compares
        to the predicted savings from the recommendation.
        """
        from app.services.energy_centre_service import get_energy_centre_service
        from app.services.device_abstraction import device_manager
        from app.services.audit_logger import AuditLogger

        now = datetime.now()
        task.verified_at = now.isoformat()

        # 1. Read current device values to check setpoints held
        comfort_violations = []
        for sp in task.setpoints_applied:
            device_id = sp.get("device_id")
            point_name = sp.get("point_name")
            expected_value = sp.get("new_value") or sp.get("value")

            if not device_id or not point_name:
                continue

            try:
                reading = await device_manager.read_device_value(device_id, point_name)
                current = reading.value if reading else None

                if current is not None and expected_value is not None:
                    # Check if setpoint drifted (for numeric values)
                    if isinstance(current, (int, float)) and isinstance(expected_value, (int, float)):
                        drift = abs(float(current) - float(expected_value))
                        if drift > COMFORT_VIOLATION_THRESHOLD_C:
                            comfort_violations.append(
                                {
                                    "device_id": device_id,
                                    "point_name": point_name,
                                    "expected": expected_value,
                                    "actual": current,
                                    "drift": round(drift, 2),
                                }
                            )
            except Exception as e:
                logger.warning(f"M&V: Could not read {device_id}/{point_name}: {e}")

        task.comfort_violations = comfort_violations

        # 2. Read actual site power from meters (best-effort)
        actual_power_kw = None
        try:
            energy_svc = get_energy_centre_service()
            summary = energy_svc.get_power_summary(task.site_id)
            if summary:
                power_reading = summary.get("total_power_kw")
                if isinstance(power_reading, (int, float)):
                    actual_power_kw = float(power_reading)
        except Exception as e:
            logger.warning(f"M&V: Could not read energy meters for {task.site_id}: {e}")
        task.actual_power_kw = actual_power_kw

        # 3. Calculate variance and accuracy
        predicted = task.predicted_savings_kwh
        if predicted > 0 and actual_power_kw is not None and task.baseline_power_kw is not None:
            # Compare savings-to-savings:
            # actual_savings = (baseline power at apply time - measured power now) * window
            actual_savings = max(0.0, (task.baseline_power_kw - actual_power_kw) * task.measurement_window_hours)
            task.actual_savings_kwh = round(actual_savings, 2)

            variance = abs(predicted - actual_savings) / predicted * 100 if predicted else 0
            task.variance_pct = round(variance, 1)
            task.accuracy = round(max(0.0, 1.0 - (variance / 100)), 3)
        else:
            # Can't compute savings variance without both baseline and actual power.
            task.actual_savings_kwh = None
            task.accuracy = None
            task.variance_pct = None
            if actual_power_kw is None:
                task.notes += " No actual meter data available for comparison."
            elif task.baseline_power_kw is None:
                task.notes += " Baseline power unavailable; savings variance not computed."

        # 4. Determine if rollback is recommended
        rollback = False
        rollback_reasons = []

        if task.variance_pct is not None and task.variance_pct > ENERGY_VARIANCE_ROLLBACK_PCT:
            rollback = True
            rollback_reasons.append(
                f"Energy variance {task.variance_pct:.1f}% exceeds {ENERGY_VARIANCE_ROLLBACK_PCT}% threshold"
            )

        if len(comfort_violations) > 0:
            rollback = True
            rollback_reasons.append(
                f"{len(comfort_violations)} comfort violations detected "
                f"(setpoint drift > {COMFORT_VIOLATION_THRESHOLD_C}C)"
            )

        task.rollback_recommended = rollback
        if rollback_reasons:
            task.notes = "; ".join(rollback_reasons)
            task.status = "failed"
            logger.warning(f"M&V {task.id}: ROLLBACK recommended — {task.notes}")
        else:
            task.status = "verified"
            if task.variance_pct is not None and task.variance_pct > ENERGY_VARIANCE_WARNING_PCT:
                task.notes = f"Warning: variance {task.variance_pct:.1f}% above {ENERGY_VARIANCE_WARNING_PCT}%"

        # 5. Create Outcome record for feedback loop
        outcome = Outcome(
            recommendation_id=task.recommendation_id,
            predicted={
                "energy_kwh": task.predicted_savings_kwh,
                "cost_zar_per_hour": task.predicted_savings_zar,
            },
            actual={
                "energy_kwh": task.actual_savings_kwh,
                "comfort_violations": len(comfort_violations),
            },
            accuracy=task.accuracy or 0.0,
            verified_at=now,
            notes=task.notes,
        )
        self._outcomes.append(outcome)

        # 6. Feed verified outcomes into shared ML feedback loop per module.
        try:
            from app.services.ml_feedback_service import get_ml_feedback_service

            ml_feedback = get_ml_feedback_service()
            module_names = [s.lower() for s in (task.recommendation_systems or ["hvac"])]
            primary_equipment = None
            if task.setpoints_applied:
                primary_equipment = task.setpoints_applied[0].get("device_id")

            for module_name in module_names:
                ml_feedback.record_module_outcome(
                    site_id=task.site_id,
                    module_type=module_name,
                    recommendation_id=task.recommendation_id,
                    action_type="optimization_mv_verification",
                    successful=task.status == "verified" and not task.rollback_recommended,
                    outcome_status=task.status,
                    predicted_impact={
                        "energy_kwh": task.predicted_savings_kwh,
                        "cost_zar_per_hour": task.predicted_savings_zar,
                    },
                    actual_impact={
                        "energy_kwh": task.actual_savings_kwh,
                        "variance_pct": task.variance_pct,
                        "comfort_violations": len(comfort_violations),
                    },
                    confidence_score=task.effective_confidence,
                    equipment_id=primary_equipment,
                    metadata={
                        "source": "mv_verification",
                        "rollback_recommended": task.rollback_recommended,
                        "routing_tier": task.routing_tier,
                        "control_tier": task.control_tier,
                    },
                )
        except Exception as e:
            logger.warning(f"M&V: Failed to record ML module feedback for {task.id}: {e}")

        # 7. Log to audit trail
        try:
            audit = AuditLogger()
            audit.log_system_event(
                event_type="mv_verification",
                metadata={
                    "task_id": task.id,
                    "recommendation_id": task.recommendation_id,
                    "site_id": task.site_id,
                    "predicted_kwh": task.predicted_savings_kwh,
                    "actual_kwh": task.actual_savings_kwh,
                    "baseline_power_kw": task.baseline_power_kw,
                    "actual_power_kw": task.actual_power_kw,
                    "variance_pct": task.variance_pct,
                    "accuracy": task.accuracy,
                    "rollback_recommended": rollback,
                    "comfort_violations": len(comfort_violations),
                },
                result=AuditResultType.WARNING if rollback else AuditResultType.SUCCESS,
            )
            audit.flush()
        except Exception as e:
            logger.warning(f"M&V: Failed to write audit log: {e}")

    def get_verification_summary(self, site_id: str) -> Dict[str, Any]:
        """Get M&V summary for a site.

        Returns:
            Dict with verification stats, recent outcomes, and accuracy trends
        """
        site_tasks = [t for t in self._tasks if t.site_id == site_id]
        site_outcomes = [
            o
            for o in self._outcomes
            if any(t.recommendation_id == o.recommendation_id and t.site_id == site_id for t in self._tasks)
        ]

        verified = [t for t in site_tasks if t.status == "verified"]
        failed = [t for t in site_tasks if t.status == "failed"]
        pending = [t for t in site_tasks if t.status == "pending"]

        # Average accuracy of verified tasks
        accuracies = [t.accuracy for t in verified if t.accuracy is not None]
        avg_accuracy = sum(accuracies) / len(accuracies) if accuracies else None

        # Recent outcomes (last 10)
        recent = sorted(site_outcomes, key=lambda o: o.verified_at, reverse=True)[:10]

        return {
            "site_id": site_id,
            "total_verifications": len(site_tasks),
            "verified": len(verified),
            "failed": len(failed),
            "pending": len(pending),
            "rollbacks_recommended": sum(1 for t in site_tasks if t.rollback_recommended),
            "average_accuracy": round(avg_accuracy, 3) if avg_accuracy else None,
            "recent_outcomes": [o.to_dict() for o in recent],
        }

    def get_pending_count(self) -> int:
        """Get count of pending verifications across all sites."""
        return sum(1 for t in self._tasks if t.status == "pending")


# Singleton accessor
_mv_service: Optional[MVVerificationService] = None


def get_mv_verification_service() -> MVVerificationService:
    """Get the singleton MVVerificationService instance."""
    global _mv_service
    if _mv_service is None:
        _mv_service = MVVerificationService()
    return _mv_service
