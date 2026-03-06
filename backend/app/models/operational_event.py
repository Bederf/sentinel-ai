"""Operational event models for the Event Intelligence layer.

Defines structured operational events derived from telemetry signals.
These sit between raw telemetry and the reasoning layer, providing
classified, enriched event objects that can be emitted to the EventBus.

Phase 145: Operational Event Intelligence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from app.services.event_bus import Importance, SentinelEvent


class OperationalEventType(str, Enum):
    """Classified operational event types."""

    TEMPERATURE_DEVIATION = "temperature_deviation"
    PRESSURE_ANOMALY = "pressure_anomaly"
    SETPOINT_DRIFT = "setpoint_drift"
    EQUIPMENT_FAULT = "equipment_fault"
    ENERGY_SPIKE = "energy_spike"
    COMFORT_VIOLATION = "comfort_violation"
    MAINTENANCE_DUE = "maintenance_due"
    SENSOR_FAILURE = "sensor_failure"
    THRESHOLD_BREACH = "threshold_breach"
    PATTERN_ANOMALY = "pattern_anomaly"  # ML-detected


class EventSeverity(str, Enum):
    """Severity levels for operational events."""

    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


# Mapping from EventSeverity to Importance for event bus emission
_SEVERITY_TO_IMPORTANCE = {
    EventSeverity.INFO: Importance.INFO,
    EventSeverity.WARNING: Importance.MEDIUM,
    EventSeverity.HIGH: Importance.HIGH,
    EventSeverity.CRITICAL: Importance.CRITICAL,
}


def _generate_event_id() -> str:
    """Generate a unique event ID in the format EVT-{timestamp}-{short_uuid}."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    short = uuid.uuid4().hex[:8]
    return f"EVT-{ts}-{short}"


@dataclass
class OperationalEvent:
    """Structured operational event derived from telemetry signals.

    These events represent classified conditions detected by the
    EventIntelligenceService. Each event carries the raw signals
    that triggered it, a human-readable description, and optional
    trend/duration information for temporal context.
    """

    event_id: str
    event_type: OperationalEventType
    equipment_id: str
    site_id: str
    severity: EventSeverity
    timestamp: datetime
    signals: List[Dict[str, Any]]  # Raw signals that triggered this event
    description: str  # Human-readable description
    trend: Optional[str] = None  # "rising", "falling", "stable"
    duration_minutes: Optional[float] = None  # How long the condition has persisted
    threshold_value: Optional[float] = None  # The threshold that was breached
    actual_value: Optional[float] = None  # Current value
    correlation_id: Optional[str] = None  # Links to event chain
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_sentinel_event(self) -> SentinelEvent:
        """Convert to SentinelEvent for emission on the event bus.

        Maps EventSeverity to Importance and packages the operational
        event data into the SentinelEvent payload.

        Returns:
            SentinelEvent ready for emission via get_event_bus().emit()
        """
        importance = _SEVERITY_TO_IMPORTANCE.get(self.severity, Importance.INFO)

        payload = {
            "operational_event_id": self.event_id,
            "operational_event_type": self.event_type.value,
            "description": self.description,
            "signals": self.signals,
            "actual_value": self.actual_value,
            "threshold_value": self.threshold_value,
            "trend": self.trend,
            "duration_minutes": self.duration_minutes,
            "metadata": self.metadata,
        }

        return SentinelEvent(
            event_type=f"operational.{self.event_type.value}",
            source="event_intelligence_service",
            payload=payload,
            importance=importance,
            site_id=self.site_id,
            equipment_id=self.equipment_id,
            correlation_id=self.correlation_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the event to a dictionary for API responses.

        Returns:
            Dict with all event fields serialized.
        """
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "equipment_id": self.equipment_id,
            "site_id": self.site_id,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "signals": self.signals,
            "description": self.description,
            "trend": self.trend,
            "duration_minutes": self.duration_minutes,
            "threshold_value": self.threshold_value,
            "actual_value": self.actual_value,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
        }
