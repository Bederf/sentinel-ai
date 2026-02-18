"""Recommendation tracking models for control tier workflow.

Defines recommendation status, risk classification, and lifecycle tracking.
Used by RecommendationService to manage approval workflow and execution.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
import uuid


class RecommendationStatus(str, Enum):
    """Status of a recommendation in the approval/execution workflow."""

    PENDING = "pending"  # Generated, awaiting action
    APPROVED = "approved"  # Operator approved (Tier 2)
    REJECTED = "rejected"  # Operator rejected (Tier 2)
    AUTO_EXECUTED = "auto_executed"  # Auto-executed (Tier 3)
    EXPIRED = "expired"  # Time window passed, no action
    EXECUTED = "executed"  # Successfully applied to BMS
    ROLLED_BACK = "rolled_back"  # Previously executed change was rolled back
    FAILED = "failed"  # Execution failed


class ActionRiskLevel(str, Enum):
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
    action: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    expected_impact: Dict[str, Any] = field(default_factory=dict)
    confidence: str = "medium"  # "high" | "medium" | "low"
    confidence_score: float = 0.0  # Numeric confidence (0.0-1.0) for tier routing
    profile: str = ""
    multi_objective_score: float = 0.0
    status: RecommendationStatus = RecommendationStatus.PENDING
    requires_approval: bool = False
    approved_by: Optional[str] = None
    approval_reason: Optional[str] = None
    executed_at: Optional[datetime] = None
    execution_result: Optional[Dict[str, Any]] = None
    rejection_reason: Optional[str] = None

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

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage.

        Converts datetime objects to ISO format strings and enums to values.
        """
        return {
            "id": self.id,
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
            "approval_reason": self.approval_reason,
            "executed_at": self.executed_at.isoformat() if isinstance(self.executed_at, datetime) else self.executed_at,
            "execution_result": self.execution_result,
            "rejection_reason": self.rejection_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Recommendation":
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
            approval_reason=data.get("approval_reason"),
            executed_at=executed_at,
            execution_result=data.get("execution_result"),
            rejection_reason=data.get("rejection_reason"),
        )
