"""Audit Log Models.

Data models for audit logging of all control actions, safety validations,
and system events. Audit logs are immutable records for compliance and
troubleshooting.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AuditActionType(str, Enum):
    """Types of actions that can be audited."""

    DEVICE_CONTROL = "device_control"
    SAFETY_VALIDATION = "safety_validation"
    SYSTEM_EVENT = "system_event"
    CONFIG_CHANGE = "config_change"


class AuditResultType(str, Enum):
    """Result types for audit log entries."""

    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    WARNING = "warning"
    SHADOW = "shadow"
    CANCELLED = "cancelled"


@dataclass
class AuditLogEntry:
    """Audit log entry for tracking all system actions."""

    # Action details (required fields without defaults)
    action: AuditActionType
    user: str  # User ID or "system" for automated actions
    result: AuditResultType

    # Core identification (fields with defaults)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)

    # Device details (optional)
    device_id: str | None = None  # Device involved, if applicable
    point_name: str | None = None  # Device point involved, if applicable

    # Value changes (for device control actions)
    old_value: Any | None = None
    new_value: Any | None = None

    # Validation and error details
    safety_validation: dict[str, Any] | None = None  # Safety validation details
    error_message: str | None = None  # Error details if failed/blocked

    # Context and metadata
    correlation_id: str | None = None  # For grouping related actions
    metadata: dict[str, Any] = field(default_factory=dict)  # Additional context

    def to_dict(self) -> dict[str, Any]:
        """Convert audit log entry to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "action": self.action.value,
            "user": self.user,
            "device_id": self.device_id,
            "point_name": self.point_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "result": self.result.value,
            "safety_validation": self.safety_validation,
            "error_message": self.error_message,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditLogEntry":
        """Create audit log entry from dictionary."""
        # Parse timestamp
        timestamp = (
            datetime.fromisoformat(data["timestamp"]) if isinstance(data["timestamp"], str) else data["timestamp"]
        )

        return cls(
            action=AuditActionType(data["action"]),
            user=data["user"],
            result=AuditResultType(data["result"]),
            id=data.get("id", str(uuid.uuid4())),
            timestamp=timestamp,
            device_id=data.get("device_id"),
            point_name=data.get("point_name"),
            old_value=data.get("old_value"),
            new_value=data.get("new_value"),
            safety_validation=data.get("safety_validation"),
            error_message=data.get("error_message"),
            correlation_id=data.get("correlation_id"),
            metadata=data.get("metadata", {}),
        )
