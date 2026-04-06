"""
SENTINEL Workflow Trigger Engine

Automated triggers that connect the workflow systems:
- ML anomalies create inspection tasks
- Baseline deviations generate recommendations
- Critical deficiencies auto-create work orders
- Repair completions trigger post-repair inspections
- Effectiveness validation compares pre/post baselines

Phase 53-02: Automated Triggers & Workflow Automation
"""

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.database.repositories.workflow_event_repository import (
    get_workflow_event_repository,
)
from app.services.feedback_collection_service import (
    get_feedback_collection_service,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================


class TriggerType(str, Enum):
    """Types of workflow triggers"""

    ML_ANOMALY = "ml_anomaly"
    BASELINE_DEVIATION = "baseline_deviation"
    CRITICAL_DEFICIENCY = "critical_deficiency"
    REPAIR_COMPLETED = "repair_completed"
    REPAIR_VALIDATION = "repair_validation"


class TriggerPriority(str, Enum):
    """Trigger priority levels"""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AnomalyAlert(BaseModel):
    """ML anomaly alert model"""

    id: str
    equipment_id: str
    anomaly_type: str
    description: str
    probability: float
    timeframe: str = "24h"
    detected_at: datetime = Field(default_factory=datetime.now)


class BaselineComparison(BaseModel):
    """Baseline comparison result model"""

    equipment_id: str
    baseline_id: str
    comparison_date: datetime = Field(default_factory=datetime.now)
    max_deviation_percent: float
    deviating_metrics: dict[str, float] = {}
    within_threshold: bool = True


class InspectionDeficiency(BaseModel):
    """Inspection deficiency model"""

    id: str
    inspection_id: str
    equipment_id: str
    severity: str  # critical, safety, major, minor
    deficiency_title: str
    deficiency_description: str
    recommended_action: str
    estimated_repair_cost_min: float = 0.0
    estimated_repair_cost_max: float = 0.0
    estimated_repair_hours: float = 0.0


class InspectionTask(BaseModel):
    """Inspection task model"""

    id: str = ""
    equipment_id: str
    task_name: str
    priority: str = "medium"
    scheduled_date: datetime = Field(default_factory=lambda: datetime.now() + timedelta(hours=24))
    reason: str = ""
    anomaly_reference: str | None = None
    work_order_reference: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)

    def __init__(self, **data):
        super().__init__(**data)
        if not self.id:
            self.id = f"insp-{datetime.now().strftime('%Y%m%d%H%M%S')}"


class WorkOrderCreate(BaseModel):
    """Work order creation model"""

    id: str = ""
    equipment_id: str
    title: str
    description: str
    priority: str = "medium"
    estimated_cost_min: float = 0.0
    estimated_cost_max: float = 0.0
    estimated_hours: float = 0.0
    deficiency_reference: str | None = None
    triggered_by: str = "workflow_automation"
    created_at: datetime = Field(default_factory=datetime.now)

    def __init__(self, **data):
        super().__init__(**data)
        if not self.id:
            self.id = f"WO-{datetime.now().strftime('%Y%m%d')}-AUTO"


class BaselineCaptureTask(BaseModel):
    """Baseline capture task model"""

    id: str = ""
    equipment_id: str
    baseline_type: str  # initial, pre_repair, post_repair
    scheduled_date: datetime = Field(default_factory=datetime.now)
    reason: str = ""
    work_order_reference: str | None = None

    def __init__(self, **data):
        super().__init__(**data)
        if not self.id:
            self.id = f"bl-{datetime.now().strftime('%Y%m%d%H%M%S')}"


class EffectivenessResult(BaseModel):
    """Repair effectiveness validation result"""

    work_order_id: str
    equipment_id: str
    effectiveness_score: float
    improvements: dict[str, dict[str, float]] = {}
    repair_successful: bool = False
    back_to_baseline: bool = False
    validation_date: datetime = Field(default_factory=datetime.now)


class TriggerResult(BaseModel):
    """Result from trigger execution"""

    success: bool
    trigger_type: TriggerType
    equipment_id: str
    action_taken: str
    details: dict[str, Any] = {}
    follow_up_scheduled: bool = False
    timestamp: datetime = Field(default_factory=datetime.now)


# ============================================================================
# Workflow Trigger Engine
# ============================================================================


class WorkflowTriggerEngine:
    """
    Central engine for automated workflow triggers.

    Handles:
    1. ML Anomaly → Inspection Task
    2. Baseline Deviation → Maintenance Recommendation
    3. Critical Deficiency → Work Order
    4. Repair Completion → Post-Repair Inspection
    5. Effectiveness Validation → ML Feedback Loop
    """

    def __init__(self):
        """Initialize trigger engine with service connections."""
        # In-memory storage for local/offline scope
        self._inspection_tasks: dict[str, list[InspectionTask]] = {}
        self._work_orders: dict[str, list[WorkOrderCreate]] = {}
        self._baseline_tasks: dict[str, list[BaselineCaptureTask]] = {}
        self._effectiveness_results: dict[str, EffectivenessResult] = {}
        self._trigger_history: list[TriggerResult] = []

        # Trigger deduplication
        self._last_triggered: dict[str, datetime] = {}
        self._recent_trigger_refs: dict[str, datetime] = {}
        self._cooldowns: dict[TriggerType, timedelta] = {
            TriggerType.ML_ANOMALY: timedelta(hours=6),
            TriggerType.BASELINE_DEVIATION: timedelta(hours=6),
            TriggerType.CRITICAL_DEFICIENCY: timedelta(hours=12),
        }

        # Workflow events log
        self._event_repository = get_workflow_event_repository()

        # Configuration
        self.baseline_deviation_threshold = 15.0  # Percentage
        self.critical_deviation_threshold = 20.0  # Percentage
        self.effectiveness_success_threshold = 50.0  # Percentage improvement
        self.baseline_tolerance = 15.0  # Within % of original baseline

        logger.info("WorkflowTriggerEngine initialized")

    # ========================================================================
    # Trigger 1: ML Anomaly → Inspection Task
    # ========================================================================

    async def on_ml_anomaly(self, equipment_id: str, anomaly: AnomalyAlert) -> TriggerResult:
        """
        Handle ML anomaly detection.

        Creates inspection task when ML detects anomaly.
        Prevents duplicate inspections for same equipment.
        """
        logger.info(f"ML anomaly trigger: {equipment_id} - {anomaly.anomaly_type}")

        try:
            # 0. Dedupe guard
            is_duplicate, dedupe_details = self._is_duplicate_trigger(
                trigger_type=TriggerType.ML_ANOMALY, equipment_id=equipment_id, reference_id=anomaly.id
            )
            if is_duplicate:
                result = TriggerResult(
                    success=True,
                    trigger_type=TriggerType.ML_ANOMALY,
                    equipment_id=equipment_id,
                    action_taken="duplicate_suppressed",
                    details={"anomaly_id": anomaly.id, **dedupe_details},
                )
                await self._record_event(
                    trigger_type=TriggerType.ML_ANOMALY,
                    equipment_id=equipment_id,
                    action_taken=result.action_taken,
                    details=result.details,
                    success=True,
                )
                self._trigger_history.append(result)
                return result

            # 1. Check if inspection already exists
            existing = self._find_pending_inspection(equipment_id)
            if existing:
                logger.info(f"Inspection already exists for {equipment_id}")
                result = TriggerResult(
                    success=True,
                    trigger_type=TriggerType.ML_ANOMALY,
                    equipment_id=equipment_id,
                    action_taken="inspection_exists",
                    details={"existing_task_id": existing.id},
                )
                await self._record_event(
                    trigger_type=TriggerType.ML_ANOMALY,
                    equipment_id=equipment_id,
                    action_taken=result.action_taken,
                    details=result.details,
                    success=True,
                )
                self._trigger_history.append(result)
                return result

            # 2. Create inspection task with high priority
            task = InspectionTask(
                equipment_id=equipment_id,
                task_name=f"Anomaly Response Inspection - {equipment_id}",
                priority=self._calculate_priority(anomaly.probability),
                scheduled_date=datetime.now() + timedelta(hours=24),
                reason=f"ML anomaly detected: {anomaly.description}",
                anomaly_reference=anomaly.id,
            )

            # 3. Save inspection task
            if equipment_id not in self._inspection_tasks:
                self._inspection_tasks[equipment_id] = []
            self._inspection_tasks[equipment_id].append(task)

            # 4. Send notification (currently logged locally)
            await self._send_alert(
                f"Anomaly detected for {equipment_id}. Inspection scheduled for {task.scheduled_date}."
            )

            # 5. Audit log
            await self._audit_log(
                trigger_type=TriggerType.ML_ANOMALY,
                equipment_id=equipment_id,
                action="created_inspection_task",
                details={"anomaly_id": anomaly.id, "task_id": task.id, "probability": anomaly.probability},
            )

            result = TriggerResult(
                success=True,
                trigger_type=TriggerType.ML_ANOMALY,
                equipment_id=equipment_id,
                action_taken="created_inspection_task",
                details={
                    "task_id": task.id,
                    "scheduled_date": task.scheduled_date.isoformat(),
                    "priority": task.priority,
                },
                follow_up_scheduled=True,
            )
            self._mark_trigger(trigger_type=TriggerType.ML_ANOMALY, equipment_id=equipment_id, reference_id=anomaly.id)
            await self._record_event(
                trigger_type=TriggerType.ML_ANOMALY,
                equipment_id=equipment_id,
                action_taken=result.action_taken,
                details={
                    "anomaly_id": anomaly.id,
                    **result.details,
                },
                success=True,
            )
            self._trigger_history.append(result)
            return result

        except Exception as e:
            logger.error(f"Error in ML anomaly trigger: {e}")
            await self._record_event(
                trigger_type=TriggerType.ML_ANOMALY,
                equipment_id=equipment_id,
                action_taken="error",
                details={"error": str(e), "anomaly_id": anomaly.id},
                success=False,
            )
            return TriggerResult(
                success=False,
                trigger_type=TriggerType.ML_ANOMALY,
                equipment_id=equipment_id,
                action_taken="error",
                details={"error": str(e)},
            )

    # ========================================================================
    # Trigger 2: Baseline Deviation → Maintenance Recommendation
    # ========================================================================

    async def on_baseline_deviation(self, equipment_id: str, comparison: BaselineComparison) -> TriggerResult:
        """
        Handle baseline deviation detection.

        Generates AI maintenance recommendation when baseline deviation detected.
        Creates inspection task for critical deviations (>20%).
        """
        logger.info(f"Baseline deviation trigger: {equipment_id} - {comparison.max_deviation_percent}%")

        try:
            # 0. Dedupe guard
            is_duplicate, dedupe_details = self._is_duplicate_trigger(
                trigger_type=TriggerType.BASELINE_DEVIATION,
                equipment_id=equipment_id,
                reference_id=comparison.baseline_id,
            )
            if is_duplicate:
                result = TriggerResult(
                    success=True,
                    trigger_type=TriggerType.BASELINE_DEVIATION,
                    equipment_id=equipment_id,
                    action_taken="duplicate_suppressed",
                    details={
                        "baseline_id": comparison.baseline_id,
                        "deviation": comparison.max_deviation_percent,
                        **dedupe_details,
                    },
                )
                await self._record_event(
                    trigger_type=TriggerType.BASELINE_DEVIATION,
                    equipment_id=equipment_id,
                    action_taken=result.action_taken,
                    details=result.details,
                    success=True,
                )
                self._trigger_history.append(result)
                return result

            # 1. Check severity threshold
            if comparison.max_deviation_percent < self.baseline_deviation_threshold:
                result = TriggerResult(
                    success=True,
                    trigger_type=TriggerType.BASELINE_DEVIATION,
                    equipment_id=equipment_id,
                    action_taken="within_threshold",
                    details={"deviation": comparison.max_deviation_percent},
                )
                await self._record_event(
                    trigger_type=TriggerType.BASELINE_DEVIATION,
                    equipment_id=equipment_id,
                    action_taken=result.action_taken,
                    details={"baseline_id": comparison.baseline_id, **result.details},
                    success=True,
                )
                self._trigger_history.append(result)
                return result

            # 2. Generate AI recommendation (locally assembled fallback)
            recommendation = await self._generate_maintenance_recommendation(
                equipment_id=equipment_id, comparison=comparison
            )

            # 3. If critical deviation, also create inspection task
            inspection_created = False
            if comparison.max_deviation_percent > self.critical_deviation_threshold:
                task = InspectionTask(
                    equipment_id=equipment_id,
                    task_name=f"Baseline Deviation Inspection - {equipment_id}",
                    priority="critical",
                    reason=f"Baseline deviation {comparison.max_deviation_percent:.1f}% exceeds threshold",
                )
                if equipment_id not in self._inspection_tasks:
                    self._inspection_tasks[equipment_id] = []
                self._inspection_tasks[equipment_id].append(task)
                inspection_created = True

            # 4. Audit log
            await self._audit_log(
                trigger_type=TriggerType.BASELINE_DEVIATION,
                equipment_id=equipment_id,
                action="generated_recommendation",
                details={
                    "deviation": comparison.max_deviation_percent,
                    "recommendation_id": recommendation.get("id"),
                    "inspection_created": inspection_created,
                },
            )

            result = TriggerResult(
                success=True,
                trigger_type=TriggerType.BASELINE_DEVIATION,
                equipment_id=equipment_id,
                action_taken="generated_recommendation",
                details={
                    "deviation_percent": comparison.max_deviation_percent,
                    "recommendation": recommendation,
                    "inspection_created": inspection_created,
                },
                follow_up_scheduled=inspection_created,
            )
            self._mark_trigger(
                trigger_type=TriggerType.BASELINE_DEVIATION,
                equipment_id=equipment_id,
                reference_id=comparison.baseline_id,
            )
            await self._record_event(
                trigger_type=TriggerType.BASELINE_DEVIATION,
                equipment_id=equipment_id,
                action_taken=result.action_taken,
                details={"baseline_id": comparison.baseline_id, **result.details},
                success=True,
            )
            self._trigger_history.append(result)
            return result

        except Exception as e:
            logger.error(f"Error in baseline deviation trigger: {e}")
            await self._record_event(
                trigger_type=TriggerType.BASELINE_DEVIATION,
                equipment_id=equipment_id,
                action_taken="error",
                details={"error": str(e), "baseline_id": comparison.baseline_id},
                success=False,
            )
            return TriggerResult(
                success=False,
                trigger_type=TriggerType.BASELINE_DEVIATION,
                equipment_id=equipment_id,
                action_taken="error",
                details={"error": str(e)},
            )

    # ========================================================================
    # Trigger 3: Critical Deficiency → Work Order Creation
    # ========================================================================

    async def on_critical_deficiency(self, deficiency: InspectionDeficiency) -> TriggerResult:
        """
        Handle critical deficiency detection.

        Auto-creates work order for critical/safety deficiencies.
        Schedules pre-repair baseline capture.
        """
        equipment_id = deficiency.equipment_id
        logger.info(f"Critical deficiency trigger: {equipment_id} - {deficiency.severity}")

        try:
            # 0. Dedupe guard
            is_duplicate, dedupe_details = self._is_duplicate_trigger(
                trigger_type=TriggerType.CRITICAL_DEFICIENCY, equipment_id=equipment_id, reference_id=deficiency.id
            )
            if is_duplicate:
                result = TriggerResult(
                    success=True,
                    trigger_type=TriggerType.CRITICAL_DEFICIENCY,
                    equipment_id=equipment_id,
                    action_taken="duplicate_suppressed",
                    details={"deficiency_id": deficiency.id, "severity": deficiency.severity, **dedupe_details},
                )
                await self._record_event(
                    trigger_type=TriggerType.CRITICAL_DEFICIENCY,
                    equipment_id=equipment_id,
                    action_taken=result.action_taken,
                    details=result.details,
                    inspection_id=deficiency.inspection_id,
                    success=True,
                )
                self._trigger_history.append(result)
                return result

            # 1. Check severity (only auto-create for critical/safety)
            if deficiency.severity not in ["critical", "safety"]:
                result = TriggerResult(
                    success=True,
                    trigger_type=TriggerType.CRITICAL_DEFICIENCY,
                    equipment_id=equipment_id,
                    action_taken="below_threshold",
                    details={"severity": deficiency.severity},
                )
                await self._record_event(
                    trigger_type=TriggerType.CRITICAL_DEFICIENCY,
                    equipment_id=equipment_id,
                    action_taken=result.action_taken,
                    details={"deficiency_id": deficiency.id, **result.details},
                    inspection_id=deficiency.inspection_id,
                    success=True,
                )
                self._trigger_history.append(result)
                return result

            # 2. Generate work order
            work_order = WorkOrderCreate(
                equipment_id=equipment_id,
                title=f"Critical Repair: {deficiency.deficiency_title}",
                description=(
                    f"Auto-generated from inspection {deficiency.inspection_id}\n\n"
                    f"Issue: {deficiency.deficiency_description}\n"
                    f"Recommended Action: {deficiency.recommended_action}"
                ),
                priority="critical",
                estimated_cost_min=deficiency.estimated_repair_cost_min,
                estimated_cost_max=deficiency.estimated_repair_cost_max,
                estimated_hours=deficiency.estimated_repair_hours,
                deficiency_reference=deficiency.id,
            )

            # 3. Save work order
            if equipment_id not in self._work_orders:
                self._work_orders[equipment_id] = []
            self._work_orders[equipment_id].append(work_order)

            # 4. Schedule pre-repair baseline capture
            baseline_task = BaselineCaptureTask(
                equipment_id=equipment_id,
                baseline_type="pre_repair",
                scheduled_date=datetime.now() + timedelta(hours=2),
                reason=f"Pre-repair baseline for WO {work_order.id}",
                work_order_reference=work_order.id,
            )
            if equipment_id not in self._baseline_tasks:
                self._baseline_tasks[equipment_id] = []
            self._baseline_tasks[equipment_id].append(baseline_task)

            # 5. Send notification
            await self._send_alert(
                f"Critical deficiency detected for {equipment_id}. Work order {work_order.id} created automatically."
            )

            # 6. Audit log
            await self._audit_log(
                trigger_type=TriggerType.CRITICAL_DEFICIENCY,
                equipment_id=equipment_id,
                action="created_work_order",
                details={
                    "deficiency_id": deficiency.id,
                    "work_order_id": work_order.id,
                    "baseline_task_id": baseline_task.id,
                },
            )

            result = TriggerResult(
                success=True,
                trigger_type=TriggerType.CRITICAL_DEFICIENCY,
                equipment_id=equipment_id,
                action_taken="created_work_order",
                details={
                    "work_order_id": work_order.id,
                    "baseline_task_id": baseline_task.id,
                    "severity": deficiency.severity,
                },
                follow_up_scheduled=True,
            )
            self._mark_trigger(
                trigger_type=TriggerType.CRITICAL_DEFICIENCY, equipment_id=equipment_id, reference_id=deficiency.id
            )
            await self._record_event(
                trigger_type=TriggerType.CRITICAL_DEFICIENCY,
                equipment_id=equipment_id,
                action_taken=result.action_taken,
                details={"deficiency_id": deficiency.id, **result.details},
                inspection_id=deficiency.inspection_id,
                work_order_id=work_order.id,
                success=True,
            )
            self._trigger_history.append(result)
            return result

        except Exception as e:
            logger.error(f"Error in critical deficiency trigger: {e}")
            await self._record_event(
                trigger_type=TriggerType.CRITICAL_DEFICIENCY,
                equipment_id=deficiency.equipment_id,
                action_taken="error",
                details={"error": str(e), "deficiency_id": deficiency.id},
                inspection_id=deficiency.inspection_id,
                success=False,
            )
            return TriggerResult(
                success=False,
                trigger_type=TriggerType.CRITICAL_DEFICIENCY,
                equipment_id=deficiency.equipment_id,
                action_taken="error",
                details={"error": str(e)},
            )

    # ========================================================================
    # Trigger 4: Repair Completion → Post-Repair Inspection
    # ========================================================================

    async def on_repair_completed(
        self, work_order_id: str, equipment_id: str, completion_data: dict[str, Any]
    ) -> TriggerResult:
        """
        Handle work order completion.

        Triggers post-repair baseline capture and verification inspection.
        Schedules effectiveness validation.
        """
        logger.info(f"Repair completed trigger: {work_order_id} - {equipment_id}")

        try:
            # 1. Schedule post-repair baseline capture
            baseline_task = BaselineCaptureTask(
                equipment_id=equipment_id,
                baseline_type="post_repair",
                scheduled_date=datetime.now() + timedelta(hours=1),
                reason=f"Post-repair baseline for WO {work_order_id}",
                work_order_reference=work_order_id,
            )
            if equipment_id not in self._baseline_tasks:
                self._baseline_tasks[equipment_id] = []
            self._baseline_tasks[equipment_id].append(baseline_task)

            # 2. Create verification inspection task
            inspection_task = InspectionTask(
                equipment_id=equipment_id,
                task_name=f"Post-Repair Verification - {equipment_id}",
                priority="high",
                scheduled_date=datetime.now() + timedelta(hours=2),
                reason=f"Verify repair completion for WO {work_order_id}",
                work_order_reference=work_order_id,
            )
            if equipment_id not in self._inspection_tasks:
                self._inspection_tasks[equipment_id] = []
            self._inspection_tasks[equipment_id].append(inspection_task)

            # 3. Start guided feedback collection session
            # Technician will be prompted for readings, observations, photos
            feedback_session_id = None
            try:
                feedback_service = get_feedback_collection_service()
                equipment_code = completion_data.get("equipment_code", equipment_id)
                session = await feedback_service.start_feedback_session(
                    work_order_id=work_order_id,
                    equipment_id=equipment_id,
                    equipment_code=equipment_code,
                    service_type="breakdown",
                )
                feedback_session_id = session.session_id
                logger.info(f"Feedback session {feedback_session_id} started for WO {work_order_id}")
            except Exception as e:
                logger.warning(f"Failed to start feedback session (non-critical): {e}")

            # 4. Queue effectiveness validation (will run after post-repair baseline)
            # Store scheduled time in local memory
            validation_scheduled_time = datetime.now() + timedelta(hours=3)

            # 5. Send notification
            await self._send_alert(
                f"Repair completed for WO {work_order_id}. "
                f"Post-repair inspection scheduled for {inspection_task.scheduled_date}."
            )

            # 6. Audit log
            await self._audit_log(
                trigger_type=TriggerType.REPAIR_COMPLETED,
                equipment_id=equipment_id,
                action="initiated_post_repair_workflow",
                details={
                    "work_order_id": work_order_id,
                    "baseline_task_id": baseline_task.id,
                    "inspection_task_id": inspection_task.id,
                    "feedback_session_id": feedback_session_id,
                    "validation_scheduled": validation_scheduled_time.isoformat(),
                },
            )

            result = TriggerResult(
                success=True,
                trigger_type=TriggerType.REPAIR_COMPLETED,
                equipment_id=equipment_id,
                action_taken="initiated_post_repair_workflow",
                details={
                    "work_order_id": work_order_id,
                    "baseline_task_id": baseline_task.id,
                    "inspection_task_id": inspection_task.id,
                    "feedback_session_id": feedback_session_id,
                    "validation_scheduled": validation_scheduled_time.isoformat(),
                },
                follow_up_scheduled=True,
            )
            await self._record_event(
                trigger_type=TriggerType.REPAIR_COMPLETED,
                equipment_id=equipment_id,
                action_taken=result.action_taken,
                details=result.details,
                work_order_id=work_order_id,
                success=True,
            )
            self._trigger_history.append(result)
            return result

        except Exception as e:
            logger.error(f"Error in repair completed trigger: {e}")
            await self._record_event(
                trigger_type=TriggerType.REPAIR_COMPLETED,
                equipment_id=equipment_id,
                action_taken="error",
                details={"error": str(e)},
                work_order_id=work_order_id,
                success=False,
            )
            return TriggerResult(
                success=False,
                trigger_type=TriggerType.REPAIR_COMPLETED,
                equipment_id=equipment_id,
                action_taken="error",
                details={"error": str(e)},
            )

    # ========================================================================
    # Trigger 5: Pre/Post Baseline Comparison → Effectiveness Validation
    # ========================================================================

    async def validate_repair_effectiveness(
        self, equipment_id: str, work_order_id: str, pre_baseline: dict[str, Any], post_baseline: dict[str, Any]
    ) -> TriggerResult:
        """
        Validate repair effectiveness by comparing baselines.

        Compares pre/post repair baselines to calculate effectiveness.
        Creates follow-up task if repair unsuccessful.
        Records ML feedback for continuous learning.
        """
        logger.info(f"Effectiveness validation trigger: {equipment_id} - WO {work_order_id}")

        try:
            # 1. Get baseline values
            pre_values = pre_baseline.get("baseline_values", {})
            post_values = post_baseline.get("baseline_values", {})

            if not pre_values or not post_values:
                result = TriggerResult(
                    success=False,
                    trigger_type=TriggerType.REPAIR_VALIDATION,
                    equipment_id=equipment_id,
                    action_taken="missing_baselines",
                    details={"error": "Missing pre or post repair baseline values"},
                )
                await self._record_event(
                    trigger_type=TriggerType.REPAIR_VALIDATION,
                    equipment_id=equipment_id,
                    action_taken=result.action_taken,
                    details=result.details,
                    work_order_id=work_order_id,
                    success=False,
                )
                return result

            # 2. Calculate improvements for each metric
            improvements = {}
            for metric, pre_value in pre_values.items():
                post_value = post_values.get(metric)
                if post_value is not None and pre_value != 0:
                    # For metrics where lower is better (vibration, noise)
                    improvement = ((pre_value - post_value) / abs(pre_value)) * 100
                    improvements[metric] = {
                        "pre_value": pre_value,
                        "post_value": post_value,
                        "improvement_percent": improvement,
                        "back_to_baseline": abs(improvement) < self.baseline_tolerance,
                    }

            # 3. Calculate average improvement
            if improvements:
                avg_improvement = sum(v["improvement_percent"] for v in improvements.values()) / len(improvements)
            else:
                avg_improvement = 0.0

            # 4. Determine effectiveness
            is_successful = avg_improvement > self.effectiveness_success_threshold or any(
                v.get("improvement_percent", 0.0) > self.effectiveness_success_threshold for v in improvements.values()
            )
            effectiveness = EffectivenessResult(
                work_order_id=work_order_id,
                equipment_id=equipment_id,
                effectiveness_score=avg_improvement,
                improvements=improvements,
                repair_successful=is_successful,
                back_to_baseline=all(v.get("back_to_baseline", False) for v in improvements.values()),
            )
            self._effectiveness_results[work_order_id] = effectiveness

            # 5. If repair unsuccessful, create follow-up task
            follow_up_created = False
            if not effectiveness.repair_successful:
                follow_up_task = InspectionTask(
                    equipment_id=equipment_id,
                    task_name=f"Failed Repair Follow-up - {equipment_id}",
                    priority="critical",
                    reason=f"Repair validation failed: only {avg_improvement:.1f}% improvement",
                    work_order_reference=work_order_id,
                )
                if equipment_id not in self._inspection_tasks:
                    self._inspection_tasks[equipment_id] = []
                self._inspection_tasks[equipment_id].append(follow_up_task)
                follow_up_created = True

                await self._send_alert(
                    f"Repair validation FAILED for WO {work_order_id}. "
                    f"Only {avg_improvement:.1f}% improvement. Follow-up inspection scheduled."
                )

            # 6. Record ML feedback
            ml_feedback_recorded = await self._record_ml_feedback(
                equipment_id=equipment_id, work_order_id=work_order_id, effectiveness=effectiveness
            )

            # 6b. Schedule follow-up and calculate cost-benefit
            followup_scheduled = False
            cost_benefit_calculated = False
            try:
                from app.services.followup_scheduler import get_followup_scheduler

                scheduler = get_followup_scheduler()
                scheduler.schedule_followup(
                    equipment_id=equipment_id,
                    work_order_id=work_order_id,
                    effectiveness_score=avg_improvement,
                    repair_successful=effectiveness.repair_successful,
                )
                followup_scheduled = True

                scheduler.calculate_cost_benefit(
                    work_order_id=work_order_id,
                    equipment_id=equipment_id,
                    repair_cost=0.0,
                    effectiveness_score=avg_improvement,
                )
                cost_benefit_calculated = True
            except Exception as e:
                logger.warning(f"Follow-up scheduling failed (non-critical): {e}")

            # 7. Audit log
            await self._audit_log(
                trigger_type=TriggerType.REPAIR_VALIDATION,
                equipment_id=equipment_id,
                action="validated_repair_effectiveness",
                details={
                    "work_order_id": work_order_id,
                    "effectiveness_score": avg_improvement,
                    "repair_successful": effectiveness.repair_successful,
                    "follow_up_created": follow_up_created,
                    "ml_feedback_recorded": ml_feedback_recorded,
                    "followup_scheduled": followup_scheduled,
                    "cost_benefit_calculated": cost_benefit_calculated,
                },
            )

            result = TriggerResult(
                success=True,
                trigger_type=TriggerType.REPAIR_VALIDATION,
                equipment_id=equipment_id,
                action_taken="validated_repair_effectiveness",
                details={
                    "effectiveness_score": avg_improvement,
                    "repair_successful": effectiveness.repair_successful,
                    "back_to_baseline": effectiveness.back_to_baseline,
                    "improvements": improvements,
                    "follow_up_created": follow_up_created,
                    "ml_feedback_recorded": ml_feedback_recorded,
                    "followup_scheduled": followup_scheduled,
                    "cost_benefit_calculated": cost_benefit_calculated,
                },
                follow_up_scheduled=follow_up_created or followup_scheduled,
            )
            await self._record_event(
                trigger_type=TriggerType.REPAIR_VALIDATION,
                equipment_id=equipment_id,
                action_taken=result.action_taken,
                details={"work_order_id": work_order_id, **result.details},
                work_order_id=work_order_id,
                success=True,
            )
            self._trigger_history.append(result)
            return result

        except Exception as e:
            logger.error(f"Error in effectiveness validation trigger: {e}")
            await self._record_event(
                trigger_type=TriggerType.REPAIR_VALIDATION,
                equipment_id=equipment_id,
                action_taken="error",
                details={"error": str(e)},
                work_order_id=work_order_id,
                success=False,
            )
            return TriggerResult(
                success=False,
                trigger_type=TriggerType.REPAIR_VALIDATION,
                equipment_id=equipment_id,
                action_taken="error",
                details={"error": str(e)},
            )

    # ========================================================================
    # Query Methods
    # ========================================================================

    def get_pending_inspections(self, equipment_id: str) -> list[InspectionTask]:
        """Get pending inspection tasks for equipment."""
        return self._inspection_tasks.get(equipment_id, [])

    def get_pending_work_orders(self, equipment_id: str) -> list[WorkOrderCreate]:
        """Get pending work orders for equipment."""
        return self._work_orders.get(equipment_id, [])

    def get_pending_baseline_tasks(self, equipment_id: str) -> list[BaselineCaptureTask]:
        """Get pending baseline capture tasks for equipment."""
        return self._baseline_tasks.get(equipment_id, [])

    def get_effectiveness_result(self, work_order_id: str) -> EffectivenessResult | None:
        """Get effectiveness result for work order."""
        return self._effectiveness_results.get(work_order_id)

    def get_trigger_history(self, equipment_id: str | None = None) -> list[TriggerResult]:
        """Get trigger history, optionally filtered by equipment."""
        if equipment_id:
            return [t for t in self._trigger_history if t.equipment_id == equipment_id]
        return self._trigger_history

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _find_pending_inspection(self, equipment_id: str) -> InspectionTask | None:
        """Find pending inspection for equipment."""
        tasks = self._inspection_tasks.get(equipment_id, [])
        for task in tasks:
            # Check if task is still pending (scheduled in future)
            if task.scheduled_date > datetime.now():
                return task
        return None

    def _cooldown_key(self, trigger_type: TriggerType, equipment_id: str) -> str:
        return f"{trigger_type.value}:{equipment_id}"

    def _reference_key(
        self, trigger_type: TriggerType, equipment_id: str, reference_id: str | None
    ) -> str | None:
        if not reference_id:
            return None
        return f"{trigger_type.value}:{equipment_id}:{reference_id}"

    def _is_duplicate_trigger(
        self, trigger_type: TriggerType, equipment_id: str, reference_id: str | None = None
    ) -> tuple[bool, dict[str, Any]]:
        now = datetime.now()
        cooldown = self._cooldowns.get(trigger_type)
        details: dict[str, Any] = {}

        if cooldown:
            last_triggered = self._last_triggered.get(self._cooldown_key(trigger_type, equipment_id))
            if last_triggered:
                elapsed = now - last_triggered
                if elapsed < cooldown:
                    details["last_triggered_at"] = last_triggered.isoformat()
                    details["cooldown_seconds_remaining"] = int((cooldown - elapsed).total_seconds())
                    return True, details

        ref_key = self._reference_key(trigger_type, equipment_id, reference_id)
        if ref_key and cooldown:
            last_reference = self._recent_trigger_refs.get(ref_key)
            if last_reference:
                elapsed = now - last_reference
                if elapsed < cooldown:
                    details["reference_id"] = reference_id
                    details["last_reference_at"] = last_reference.isoformat()
                    details["cooldown_seconds_remaining"] = int((cooldown - elapsed).total_seconds())
                    return True, details

        return False, details

    def _mark_trigger(self, trigger_type: TriggerType, equipment_id: str, reference_id: str | None = None) -> None:
        now = datetime.now()
        self._last_triggered[self._cooldown_key(trigger_type, equipment_id)] = now
        ref_key = self._reference_key(trigger_type, equipment_id, reference_id)
        if ref_key:
            self._recent_trigger_refs[ref_key] = now

    def _calculate_priority(self, probability: float) -> str:
        """Calculate priority based on anomaly probability."""
        if probability >= 0.9:
            return TriggerPriority.CRITICAL.value
        elif probability >= 0.7:
            return TriggerPriority.HIGH.value
        elif probability >= 0.5:
            return TriggerPriority.MEDIUM.value
        return TriggerPriority.LOW.value

    async def _generate_maintenance_recommendation(
        self, equipment_id: str, comparison: BaselineComparison
    ) -> dict[str, Any]:
        """Generate AI maintenance recommendation."""
        # Locally assembled recommendation
        recommendation_id = f"rec-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Determine urgency based on deviation
        urgency = "high" if comparison.max_deviation_percent > 20 else "medium"

        # Build deviating metrics description
        metric_descriptions = []
        for metric, deviation in comparison.deviating_metrics.items():
            metric_descriptions.append(f"{metric}: {deviation:.1f}% deviation")

        return {
            "id": recommendation_id,
            "equipment_id": equipment_id,
            "urgency": urgency,
            "summary": f"Baseline deviation detected: {comparison.max_deviation_percent:.1f}% max deviation",
            "deviating_metrics": metric_descriptions,
            "recommended_actions": [
                "Schedule inspection within 24-48 hours",
                "Check sensor calibration",
                "Review recent operational changes",
                "Compare with similar equipment",
            ],
            "generated_at": datetime.now().isoformat(),
        }

    async def _record_ml_feedback(
        self, equipment_id: str, work_order_id: str, effectiveness: EffectivenessResult
    ) -> bool:
        """Record repair outcome for ML training via MLFeedbackService."""
        try:
            from app.services.ml_feedback_service import get_ml_feedback_service

            ml_service = get_ml_feedback_service()
            ml_service.record_repair_feedback(
                equipment_id=equipment_id,
                work_order_id=work_order_id,
                effectiveness_score=effectiveness.effectiveness_score,
                repair_successful=effectiveness.repair_successful,
                failure_type=None,
                prediction_id=None,
            )
            return True
        except Exception as e:
            logger.warning(f"ML feedback recording failed (non-critical): {e}")
            return False

    async def _send_alert(self, message: str):
        """Send alert notification."""
        # Log locally until notification service integration is wired in
        logger.info(f"ALERT: {message}")

    async def _record_event(
        self,
        trigger_type: TriggerType,
        equipment_id: str,
        action_taken: str,
        details: dict[str, Any],
        success: bool,
        work_order_id: str | None = None,
        inspection_id: str | None = None,
    ) -> None:
        event_payload = {
            "equipment_id": equipment_id,
            "trigger_type": trigger_type.value,
            "action_taken": action_taken,
            "source": "workflow_triggers",
            "work_order_id": work_order_id,
            "inspection_id": inspection_id,
            "details": details,
            "success": success,
        }

        try:
            self._event_repository.create(event_payload)
        except Exception as e:
            logger.warning(f"Workflow event logging failed (non-critical): {e}")

    async def _audit_log(self, trigger_type: TriggerType, equipment_id: str, action: str, details: dict[str, Any]):
        """Log trigger action to audit log."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "trigger_type": trigger_type.value,
            "equipment_id": equipment_id,
            "action": action,
            "details": details,
        }
        logger.info(f"AUDIT: {log_entry}")


# ============================================================================
# Singleton Instance
# ============================================================================

_trigger_engine_instance: WorkflowTriggerEngine | None = None


def get_trigger_engine() -> WorkflowTriggerEngine:
    """Get singleton trigger engine instance."""
    global _trigger_engine_instance
    if _trigger_engine_instance is None:
        _trigger_engine_instance = WorkflowTriggerEngine()
    return _trigger_engine_instance
