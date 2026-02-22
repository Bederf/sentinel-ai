"""Models for autonomous decisions and decision history."""

from enum import Enum
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from app.models.audit_log import AuditResultType


class DecisionStatus(Enum):
    """Status of an autonomous decision."""

    PENDING = "pending"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class EscalationLevel(Enum):
    """Escalation levels for boundary approach."""

    NONE = 0  # Normal operation
    WARNING = 1  # 75% approach - Logged
    ALERT = 2  # 85% approach - Email
    CRITICAL = 3  # 95% approach - Slack + Dashboard
    EMERGENCY = 4  # 100% breach - Stop + Emergency


@dataclass
class AutonomousDecision:
    """Represents an autonomous decision made by the system."""

    id: str
    timestamp: datetime
    device_id: str
    device_name: str
    point_name: str
    current_value: float
    target_value: float
    decision_rationale: str
    rule_triggered: Optional[str]
    safety_validation: Dict[str, Any]
    status: DecisionStatus
    result: Optional[AuditResultType]
    execution_time_ms: Optional[float]
    escalation_level: EscalationLevel
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert decision to dictionary for serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "device_id": self.device_id,
            "device_name": self.device_name,
            "point_name": self.point_name,
            "current_value": self.current_value,
            "target_value": self.target_value,
            "decision_rationale": self.decision_rationale,
            "rule_triggered": self.rule_triggered,
            "safety_validation": self.safety_validation,
            "status": self.status.value,
            "result": self.result.value if self.result else None,
            "execution_time_ms": self.execution_time_ms,
            "escalation_level": self.escalation_level.value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AutonomousDecision":
        """Create decision from dictionary."""
        return cls(
            id=data["id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            device_id=data["device_id"],
            device_name=data["device_name"],
            point_name=data["point_name"],
            current_value=data["current_value"],
            target_value=data["target_value"],
            decision_rationale=data["decision_rationale"],
            rule_triggered=data.get("rule_triggered"),
            safety_validation=data.get("safety_validation", {}),
            status=DecisionStatus(data["status"]),
            result=AuditResultType(data["result"]) if data.get("result") else None,
            execution_time_ms=data.get("execution_time_ms"),
            escalation_level=EscalationLevel(data.get("escalation_level", 0)),
            metadata=data.get("metadata", {}),
        )


@dataclass
class BoundaryStatus:
    """Current boundary status for a device/point."""

    device_id: str
    point_name: str
    current_value: float
    boundary_min: Optional[float]
    boundary_max: Optional[float]
    approach_percentage: float  # 0-100, how close to boundary
    escalation_level: EscalationLevel
    warnings: List[str]
    last_updated: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "device_id": self.device_id,
            "point_name": self.point_name,
            "current_value": self.current_value,
            "boundary_min": self.boundary_min,
            "boundary_max": self.boundary_max,
            "approach_percentage": self.approach_percentage,
            "escalation_level": self.escalation_level.value,
            "warnings": self.warnings,
            "last_updated": self.last_updated.isoformat(),
        }


@dataclass
class EscalationEvent:
    """Represents an escalation event triggered by boundary approach."""

    id: str
    timestamp: datetime
    device_id: str
    device_name: str
    point_name: str
    current_value: float
    boundary_min: Optional[float]
    boundary_max: Optional[float]
    approach_percentage: float
    escalation_level: EscalationLevel
    acknowledged: bool
    acknowledged_by: Optional[str]
    acknowledged_at: Optional[datetime]
    auto_resolved: bool
    warnings: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "device_id": self.device_id,
            "device_name": self.device_name,
            "point_name": self.point_name,
            "current_value": self.current_value,
            "boundary_min": self.boundary_min,
            "boundary_max": self.boundary_max,
            "approach_percentage": self.approach_percentage,
            "escalation_level": self.escalation_level.value,
            "acknowledged": self.acknowledged,
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "auto_resolved": self.auto_resolved,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


@dataclass
class AutonomousSystemStatus:
    """Overall status of the autonomous system."""

    enabled: bool
    active_decisions: int
    total_decisions_today: int
    success_rate: float
    current_escalation_level: EscalationLevel
    last_decision_time: Optional[datetime]
    safety_score: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "active_decisions": self.active_decisions,
            "total_decisions_today": self.total_decisions_today,
            "success_rate": self.success_rate,
            "current_escalation_level": self.current_escalation_level.value,
            "last_decision_time": self.last_decision_time.isoformat() if self.last_decision_time else None,
            "safety_score": self.safety_score,
        }
