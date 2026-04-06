"""
Follow-up Scheduler Service (Phase 57-03)

Automated follow-up scheduling, cost-benefit analysis, and escalation
for ineffective repairs. Connects repair effectiveness with ML feedback
into a cohesive automated workflow.

Features:
- Auto-schedule re-inspections based on repair effectiveness
- Cost-benefit analysis with ZAR figures by equipment type
- 3-level escalation for recurring failures
- Integration with workflow triggers for full feedback loop

Currency: South African Rand (ZAR)
"""

import logging
import uuid
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================================
# Models
# ============================================================================


class FollowupTask(BaseModel):
    """A scheduled follow-up task for post-repair monitoring."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    equipment_id: str
    work_order_id: str
    followup_type: str  # re_inspection, re_repair, escalation
    scheduled_date: datetime
    reason: str
    priority: str  # low, medium, high, critical
    status: str = "scheduled"  # scheduled, completed, cancelled
    created_at: datetime = Field(default_factory=datetime.now)


class CostBenefitAnalysis(BaseModel):
    """Cost-benefit analysis for a repair action."""

    work_order_id: str
    equipment_id: str
    repair_cost: float
    estimated_failure_cost: float
    cost_avoidance: float
    roi_percent: float
    effectiveness_score: float
    cost_effective: bool
    analysis_date: datetime = Field(default_factory=datetime.now)


class EscalationRecord(BaseModel):
    """Escalation record for recurring repair failures."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    equipment_id: str
    escalation_level: int  # 1-3
    reason: str
    failed_repair_count: int
    total_repair_cost: float
    recommended_action: str  # re_repair, specialist_review, replacement_assessment
    created_at: datetime = Field(default_factory=datetime.now)


# ============================================================================
# Default Failure Costs (ZAR) by Equipment Type
# ============================================================================

DEFAULT_FAILURE_COSTS: dict[str, float] = {
    "CHILLER": 50_000.0,
    "AHU": 30_000.0,
    "FCU": 15_000.0,
    "GEN": 40_000.0,
    "GENERATOR": 40_000.0,
    "PUMP": 10_000.0,
    "VAV": 8_000.0,
    "DALI": 5_000.0,
    "MTR": 12_000.0,
}

DEFAULT_FAILURE_COST = 20_000.0  # Fallback for unknown types


# ============================================================================
# Service
# ============================================================================


class FollowupSchedulerService:
    """
    Manages follow-up scheduling, cost-benefit analysis, and escalation
    for repair effectiveness tracking.

    Scheduling rules:
    - Successful repair (score >= 80): re-inspection in 30 days (low priority)
    - Successful but marginal (score < 80): re-inspection in 7 days (medium)
    - Failed repair (1st failure): re-repair in 3 days (high priority)
    - Failed repair (2nd+ failure): escalation (critical priority)

    Escalation levels:
    - Level 1: 1 failed repair → recommend re-repair
    - Level 2: 2 failed repairs → recommend specialist review
    - Level 3: 3+ failed repairs → recommend replacement assessment
    """

    def __init__(self):
        self._scheduled_followups: list[FollowupTask] = []
        self._cost_analyses: dict[str, CostBenefitAnalysis] = {}  # work_order_id -> analysis
        self._escalations: dict[str, EscalationRecord] = {}  # equipment_id -> latest escalation
        logger.info("FollowupSchedulerService initialized")

    def schedule_followup(
        self, equipment_id: str, work_order_id: str, effectiveness_score: float, repair_successful: bool
    ) -> FollowupTask:
        """
        Schedule appropriate follow-up based on repair outcome.

        Args:
            equipment_id: Equipment identifier
            work_order_id: Work order reference
            effectiveness_score: Repair effectiveness score (0-100)
            repair_successful: Whether repair met success threshold

        Returns:
            FollowupTask with scheduled action
        """
        failed_count = self._count_failed_repairs(equipment_id)

        if repair_successful and effectiveness_score >= 80:
            # Good repair - routine follow-up
            task = FollowupTask(
                equipment_id=equipment_id,
                work_order_id=work_order_id,
                followup_type="re_inspection",
                scheduled_date=datetime.now() + timedelta(days=30),
                reason=f"Routine post-repair check (score: {effectiveness_score:.1f}%)",
                priority="low",
            )
        elif repair_successful and effectiveness_score < 80:
            # Marginal repair - closer monitoring
            task = FollowupTask(
                equipment_id=equipment_id,
                work_order_id=work_order_id,
                followup_type="re_inspection",
                scheduled_date=datetime.now() + timedelta(days=7),
                reason=f"Marginal repair effectiveness (score: {effectiveness_score:.1f}%), close monitoring needed",
                priority="medium",
            )
        elif not repair_successful and failed_count >= 1:
            # Repeated failure - escalate
            escalation = self._create_escalation(equipment_id=equipment_id, failed_count=failed_count + 1)
            self._escalations[equipment_id] = escalation

            task = FollowupTask(
                equipment_id=equipment_id,
                work_order_id=work_order_id,
                followup_type="escalation",
                scheduled_date=datetime.now() + timedelta(days=1),
                reason=f"Escalation level {escalation.escalation_level}: {escalation.recommended_action} "
                f"({failed_count + 1} failed repairs)",
                priority="critical",
            )
            logger.warning(
                f"ESCALATION: {equipment_id} - Level {escalation.escalation_level} ({failed_count + 1} failed repairs)"
            )
        else:
            # First failure - schedule re-repair
            task = FollowupTask(
                equipment_id=equipment_id,
                work_order_id=work_order_id,
                followup_type="re_repair",
                scheduled_date=datetime.now() + timedelta(days=3),
                reason=f"Repair failed (score: {effectiveness_score:.1f}%), re-repair needed",
                priority="high",
            )

        self._scheduled_followups.append(task)
        logger.info(
            f"Follow-up scheduled: {equipment_id} - {task.followup_type} "
            f"({task.priority}) on {task.scheduled_date.strftime('%Y-%m-%d')}"
        )
        return task

    def calculate_cost_benefit(
        self, work_order_id: str, equipment_id: str, repair_cost: float, effectiveness_score: float
    ) -> CostBenefitAnalysis:
        """
        Calculate cost-benefit analysis for a repair.

        Uses equipment-type-specific failure cost estimates (ZAR).

        Args:
            work_order_id: Work order reference
            equipment_id: Equipment identifier (type inferred from ID)
            repair_cost: Actual repair cost in ZAR
            effectiveness_score: Repair effectiveness score (0-100)

        Returns:
            CostBenefitAnalysis with ROI calculation
        """
        equipment_type = self._infer_equipment_type(equipment_id)
        estimated_failure_cost = DEFAULT_FAILURE_COSTS.get(equipment_type, DEFAULT_FAILURE_COST)

        # Cost avoidance = how much failure cost was avoided by the repair
        cost_avoidance = estimated_failure_cost * (effectiveness_score / 100) - repair_cost

        # ROI calculation
        if repair_cost > 0:
            roi_percent = (cost_avoidance / repair_cost) * 100
        else:
            # If repair cost is 0 (unknown), ROI is based purely on avoidance
            roi_percent = 100.0 if effectiveness_score > 0 else 0.0

        cost_effective = roi_percent > 0

        analysis = CostBenefitAnalysis(
            work_order_id=work_order_id,
            equipment_id=equipment_id,
            repair_cost=repair_cost,
            estimated_failure_cost=estimated_failure_cost,
            cost_avoidance=round(cost_avoidance, 2),
            roi_percent=round(roi_percent, 2),
            effectiveness_score=effectiveness_score,
            cost_effective=cost_effective,
        )

        self._cost_analyses[work_order_id] = analysis
        logger.info(
            f"Cost-benefit analysis: {equipment_id} WO {work_order_id} - "
            f"ROI: {roi_percent:.1f}%, cost-effective: {cost_effective}"
        )
        return analysis

    def check_escalation(self, equipment_id: str) -> EscalationRecord | None:
        """
        Check escalation status for equipment based on repair history.

        Escalation levels:
        - Level 1 (1 failed repair): Recommend re-repair
        - Level 2 (2 failed repairs): Recommend specialist review
        - Level 3 (3+ failed repairs): Recommend replacement assessment

        Args:
            equipment_id: Equipment identifier

        Returns:
            EscalationRecord if escalation needed, None otherwise
        """
        failed_count = self._count_failed_repairs(equipment_id)

        if failed_count == 0:
            return None

        return self._create_escalation(equipment_id, failed_count)

    def get_pending_followups(
        self, equipment_id: str | None = None, status: str | None = None
    ) -> list[FollowupTask]:
        """
        Get follow-up tasks, optionally filtered.

        Args:
            equipment_id: Filter by equipment (optional)
            status: Filter by status: scheduled/completed/cancelled (optional)

        Returns:
            List of matching FollowupTask entries
        """
        results = self._scheduled_followups

        if equipment_id:
            results = [f for f in results if f.equipment_id == equipment_id]

        if status:
            results = [f for f in results if f.status == status]

        return sorted(results, key=lambda f: f.scheduled_date)

    def get_cost_analyses(self, equipment_id: str | None = None) -> list[CostBenefitAnalysis]:
        """
        Get cost-benefit analyses, optionally filtered by equipment.

        Args:
            equipment_id: Filter by equipment (optional)

        Returns:
            List of CostBenefitAnalysis entries
        """
        analyses = list(self._cost_analyses.values())

        if equipment_id:
            analyses = [a for a in analyses if a.equipment_id == equipment_id]

        return sorted(analyses, key=lambda a: a.analysis_date, reverse=True)

    # ========================================================================
    # Private Helpers
    # ========================================================================

    def _count_failed_repairs(self, equipment_id: str) -> int:
        """Count failed repair follow-ups for equipment."""
        return sum(
            1
            for f in self._scheduled_followups
            if f.equipment_id == equipment_id and f.followup_type in ("re_repair", "escalation")
        )

    def _create_escalation(self, equipment_id: str, failed_count: int) -> EscalationRecord:
        """Create escalation record based on failure count."""
        total_cost = self._calculate_total_repair_cost(equipment_id)

        if failed_count >= 3:
            level = 3
            action = "replacement_assessment"
            reason = f"{failed_count} failed repairs - equipment replacement should be assessed"
        elif failed_count >= 2:
            level = 2
            action = "specialist_review"
            reason = f"{failed_count} failed repairs - specialist review recommended"
        else:
            level = 1
            action = "re_repair"
            reason = f"{failed_count} failed repair(s) - re-repair with different approach"

        return EscalationRecord(
            equipment_id=equipment_id,
            escalation_level=level,
            reason=reason,
            failed_repair_count=failed_count,
            total_repair_cost=total_cost,
            recommended_action=action,
        )

    def _calculate_total_repair_cost(self, equipment_id: str) -> float:
        """Sum repair costs for equipment from cost analyses."""
        return sum(a.repair_cost for a in self._cost_analyses.values() if a.equipment_id == equipment_id)

    def _infer_equipment_type(self, equipment_id: str) -> str:
        """
        Infer equipment type from v2.0 equipment ID.

        Format: S002-{TYPE}-{FLOOR}-{ZONE}
        Examples: S002-CHILLER-B1-001, S002-FCU-L1-A
        """
        parts = equipment_id.upper().split("-")
        if len(parts) >= 2:
            return parts[1]
        return "UNKNOWN"


# ============================================================================
# Singleton Instance
# ============================================================================

_followup_scheduler: FollowupSchedulerService | None = None


def get_followup_scheduler() -> FollowupSchedulerService:
    """Get singleton FollowupSchedulerService instance."""
    global _followup_scheduler
    if _followup_scheduler is None:
        _followup_scheduler = FollowupSchedulerService()
    return _followup_scheduler
