"""Recommendation tracking models for control tier workflow.

Defines recommendation status, risk classification, and lifecycle tracking.
Used by RecommendationService to manage approval workflow and execution.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class RecommendationStatus(StrEnum):
    """Status of a recommendation in the approval/execution workflow."""

    PENDING = "pending"  # Generated, awaiting action
    APPROVED = "approved"  # Operator approved (Tier 2)
    REJECTED = "rejected"  # Operator rejected (Tier 2)
    AUTO_EXECUTED = "auto_executed"  # Auto-executed (Tier 3)
    EXPIRED = "expired"  # Time window passed, no action
    EXECUTED = "executed"  # Successfully applied to BMS
    ROLLED_BACK = "rolled_back"  # Previously executed change was rolled back
    FAILED = "failed"  # Execution failed


class MilestoneStatus(StrEnum):
    """4-milestone SLA lifecycle for Fairlands maintenance tickets.


    Tracks which phase of the SLA workflow a recommendation is in.
    Each milestone has its own SLA deadline (configured per-site).
    """

    ASSIGNED = "assigned"  # Ticket assigned, awaiting action
    IN_PROGRESS = "in_progress"  # Work started
    RESOLVED = "resolved"  # Work completed, awaiting verification
    VERIFIED = "verified"  # Customer confirmed, milestone complete


class ActionRiskLevel(StrEnum):
    """Risk level classification for recommended actions."""

    LOW = "low"  # Setpoint adjustments, dimming
    MEDIUM = "medium"  # Chiller staging, VAV overrides
    HIGH = "high"  # Generator start, BESS dispatch
    CRITICAL = "critical"  # Fire, access control, emergency


@dataclass
class Recommendation:
    """Recommendation for a building control action.

    Tracks a single recommended action through its lifecycle:
    - Creation by AI optimizer
    - Approval (if required by control tier)
    - Execution to BMS
    - Result tracking

    Fields:
        id: Unique identifier (UUID)
        site_id: Building identifier
        timestamp: When recommendation was created
        action_type: Type of action (e.g., "hvac_setpoint_change")
        risk_level: ActionRiskLevel classification
        target_equipment: Equipment ID (e.g., "S002-CHILLER-B1-001")
        action: Dict specifying what to change (e.g., {"point": "...", "value": ...})
        reason: Explanation from AI for this recommendation
        expected_impact: Projected impact (cost_zar, comfort_delta, energy_kwh)
        confidence: Confidence level ("high" | "medium" | "low")
        profile: Optimization profile that generated this (e.g., "cost", "comfort")
        multi_objective_score: Ranking score (0-1) from RecommendationScorer
        status: Current lifecycle status
        requires_approval: Whether control tier requires operator approval
        approved_by: User ID who approved (if approved)
        approval_reason: Why operator approved/rejected
        executed_at: Timestamp of execution
        execution_result: Result dict from device manager
        rejection_reason: Why operator rejected (if rejected)
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    site_id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    action_type: str = ""
    risk_level: ActionRiskLevel = ActionRiskLevel.MEDIUM
    target_equipment: str = ""
    action: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    expected_impact: dict[str, Any] = field(default_factory=dict)
    confidence: str = "medium"  # "high" | "medium" | "low"
    confidence_score: float = 0.0  # Numeric confidence (0.0-1.0) for tier routing
    profile: str = ""
    multi_objective_score: float = 0.0
    status: RecommendationStatus = RecommendationStatus.PENDING
    requires_approval: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None
    approval_reason: str | None = None
    executed_at: datetime | None = None
    execution_result: dict[str, Any] | None = None
    rejection_reason: str | None = None
    source: str = ""  # "ai_optimizer", "health_alert", "financial_roi", "anomaly_detector", "rule_engine"
    source_type: str = ""  # "ml_model", "rule_based", "user_input"
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    outcome_validated: bool | None = None
    outcome_notes: str | None = None
    outcome_validated_at: datetime | None = None
    shadow_mode: bool = False  # If True, stored but hidden from frontend UI
    metadata: dict[str, Any] = field(
        default_factory=dict
    )  # Additional context (e.g., affected_equipment for grouped recs)

    # --- 4-milestone SLA fields ---
    milestone_status: MilestoneStatus = MilestoneStatus.ASSIGNED
    assigned_at: datetime = field(default_factory=datetime.utcnow)
    in_progress_at: datetime | None = None
    resolved_at: datetime | None = None
    verified_at: datetime | None = None
    sla_hours: dict[str, int] = field(default_factory=dict)  # {"assigned": 24, "in_progress": 48, ...}
    sla_deadline_at: datetime | None = None  # Materialised deadline, updated on advance
    external_ticket_id: str | None = None  # FSI/external ticket correlation
    is_consumable: bool = False  # True if issue is a consumable replace, not a fault

    # Consumables correction metadata (populated by SemanticPriorityClassifier)
    priority_corrected: bool = False  # True if priority was downgraded from original
    priority_reason: str | None = None  # Explanation from classifier

    # Cluster detection metadata (Phase 207-04: cluster alert at 3rd occurrence)
    is_cluster_alert: bool = False  # True if equipment has >= 3 occurrences in 90-day window
    cluster_count: int = 1  # Running count of occurrences in sliding window

    def get_numeric_confidence(self) -> float:
        """Return numeric confidence, converting string if needed.

        Returns numeric confidence (0.0-1.0) from either confidence_score field
        or by mapping the string confidence value. Ensures PARASITE tier routing
        always has numeric confidence.

        Returns:
            Float between 0.0 and 1.0
        """
        # If numeric confidence_score is set, use it
        if self.confidence_score > 0:
            return self.confidence_score

        # Fallback: map string confidence to numeric
        mapping = {"high": 0.90, "medium": 0.75, "low": 0.50}
        return mapping.get(self.confidence, 0.50)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON storage.

        Converts datetime objects to ISO format strings and enums to values.
        """
        return {
            "id": self.target_equipment or self.id,
            "site_id": self.site_id,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            "action_type": self.action_type,
            "risk_level": self.risk_level.value if isinstance(self.risk_level, ActionRiskLevel) else self.risk_level,
            "target_equipment": self.target_equipment,
            "action": self.action,
            "reason": self.reason,
            "expected_impact": self.expected_impact,
            "confidence": self.confidence,
            "confidence_score": self.confidence_score,
            "profile": self.profile,
            "multi_objective_score": self.multi_objective_score,
            "status": self.status.value if isinstance(self.status, RecommendationStatus) else self.status,
            "requires_approval": self.requires_approval,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if isinstance(self.approved_at, datetime) else self.approved_at,
            "approval_reason": self.approval_reason,
            "executed_at": self.executed_at.isoformat() if isinstance(self.executed_at, datetime) else self.executed_at,
            "execution_result": self.execution_result,
            "rejection_reason": self.rejection_reason,
            "source": self.source,
            "source_type": self.source_type,
            "outcome_validated": self.outcome_validated,
            "outcome_notes": self.outcome_notes,
            "outcome_validated_at": (
                self.outcome_validated_at.isoformat()
                if isinstance(self.outcome_validated_at, datetime)
                else self.outcome_validated_at
            ),
            "shadow_mode": self.shadow_mode,
            "metadata": self.metadata,
            "milestone_status": self.milestone_status.value
            if isinstance(self.milestone_status, MilestoneStatus)
            else self.milestone_status,
            "assigned_at": self.assigned_at.isoformat() if isinstance(self.assigned_at, datetime) else self.assigned_at,
            "in_progress_at": self.in_progress_at.isoformat()
            if isinstance(self.in_progress_at, datetime)
            else self.in_progress_at,
            "resolved_at": self.resolved_at.isoformat() if isinstance(self.resolved_at, datetime) else self.resolved_at,
            "verified_at": self.verified_at.isoformat() if isinstance(self.verified_at, datetime) else self.verified_at,
            "sla_hours": self.sla_hours,
            "sla_deadline_at": self.sla_deadline_at.isoformat()
            if isinstance(self.sla_deadline_at, datetime)
            else self.sla_deadline_at,
            "external_ticket_id": self.external_ticket_id,
            "is_cluster_alert": self.is_cluster_alert,
            "cluster_count": self.cluster_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Recommendation":
        """Deserialize from dictionary.

        Converts ISO format strings back to datetime objects and values to enums.
        """
        # Parse datetime fields
        timestamp = data.get("timestamp", "")
        if isinstance(timestamp, str) and timestamp:
            try:
                timestamp = datetime.fromisoformat(timestamp)
            except (ValueError, TypeError):
                timestamp = datetime.utcnow()
        else:
            timestamp = datetime.utcnow()

        executed_at = data.get("executed_at")
        if isinstance(executed_at, str) and executed_at:
            try:
                executed_at = datetime.fromisoformat(executed_at)
            except (ValueError, TypeError):
                executed_at = None

        approved_at = data.get("approved_at")
        if isinstance(approved_at, str) and approved_at:
            try:
                approved_at = datetime.fromisoformat(approved_at)
            except (ValueError, TypeError):
                approved_at = None

        outcome_validated_at = data.get("outcome_validated_at")
        if isinstance(outcome_validated_at, str) and outcome_validated_at:
            try:
                outcome_validated_at = datetime.fromisoformat(outcome_validated_at)
            except (ValueError, TypeError):
                outcome_validated_at = None

        # Parse enums
        risk_level = data.get("risk_level", "medium")
        if isinstance(risk_level, str):
            try:
                risk_level = ActionRiskLevel(risk_level)
            except ValueError:
                risk_level = ActionRiskLevel.MEDIUM

        status = data.get("status", "pending")
        if isinstance(status, str):
            try:
                status = RecommendationStatus(status)
            except ValueError:
                status = RecommendationStatus.PENDING

        # Parse milestone status
        milestone_status = data.get("milestone_status", "assigned")
        if isinstance(milestone_status, str):
            try:
                milestone_status = MilestoneStatus(milestone_status)
            except ValueError:
                milestone_status = MilestoneStatus.ASSIGNED

        # Parse milestone timestamps
        def _parse_ts(key: str) -> datetime | None:
            val = data.get(key)
            if isinstance(val, str) and val:
                try:
                    return datetime.fromisoformat(val)
                except (ValueError, TypeError):
                    return None
            return val

        assigned_at = _parse_ts("assigned_at") or datetime.utcnow()
        in_progress_at = _parse_ts("in_progress_at")
        resolved_at = _parse_ts("resolved_at")
        verified_at = _parse_ts("verified_at")
        sla_deadline_at = _parse_ts("sla_deadline_at")

        # Parse SLA hours dict
        sla_hours_raw = data.get("sla_hours", {})
        if isinstance(sla_hours_raw, dict):
            sla_hours = {k: int(v) for k, v in sla_hours_raw.items()}
        else:
            sla_hours = {}

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            site_id=data.get("site_id", ""),
            timestamp=timestamp,
            action_type=data.get("action_type", ""),
            risk_level=risk_level,
            target_equipment=data.get("target_equipment", ""),
            action=data.get("action", {}),
            reason=data.get("reason", ""),
            expected_impact=data.get("expected_impact", {}),
            confidence=data.get("confidence", "medium"),
            confidence_score=float(data.get("confidence_score", 0.0)),
            profile=data.get("profile", ""),
            multi_objective_score=float(data.get("multi_objective_score", 0.0)),
            status=status,
            requires_approval=data.get("requires_approval", False),
            approved_by=data.get("approved_by"),
            approved_at=approved_at,
            approval_reason=data.get("approval_reason"),
            executed_at=executed_at,
            execution_result=data.get("execution_result"),
            rejection_reason=data.get("rejection_reason"),
            outcome_validated=data.get("outcome_validated"),
            outcome_notes=data.get("outcome_notes"),
            outcome_validated_at=outcome_validated_at,
            shadow_mode=data.get("shadow_mode", False),
            metadata=data.get("metadata", {}),
            # 4-milestone SLA fields
            milestone_status=milestone_status,
            assigned_at=assigned_at,
            in_progress_at=in_progress_at,
            resolved_at=resolved_at,
            verified_at=verified_at,
            sla_hours=sla_hours,
            sla_deadline_at=sla_deadline_at,
            external_ticket_id=data.get("external_ticket_id"),
            # Cluster detection metadata
            is_cluster_alert=data.get("is_cluster_alert", False),
            cluster_count=data.get("cluster_count", 1),
        )
