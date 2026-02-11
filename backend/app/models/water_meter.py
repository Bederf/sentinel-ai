"""Water meter models for consumption tracking and leak detection.

This module defines data models for water meter integration including:
- WaterMeter: Physical meter device configuration
- WaterConsumption: Time-series consumption readings
- WaterAlert: Leak detection alerts
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List
from decimal import Decimal


class MeterType(Enum):
    """Types of water meters."""
    MAIN = "main"                    # Building main inlet
    SUBMETER = "submeter"            # Tenant/floor submeter
    IRRIGATION = "irrigation"        # Landscaping water
    COOLING_TOWER = "cooling_tower"  # HVAC makeup water
    DOMESTIC = "domestic"            # Restrooms/kitchens
    FIRE = "fire"                    # Fire suppression system


class AlertType(Enum):
    """Types of water leak alerts."""
    CONTINUOUS_FLOW = "continuous_flow"      # Flow during off-hours
    UNUSUAL_PATTERN = "unusual_pattern"      # Statistical anomaly
    SPIKE = "spike"                          # Sudden flow increase
    NIGHT_FLOW = "night_flow"                # Minimum night flow exceeded


class AlertSeverity(Enum):
    """Severity levels for water alerts."""
    LOW = "low"          # Informational, investigate soon
    MEDIUM = "medium"    # Potential issue, investigate today
    HIGH = "high"        # Likely leak, investigate immediately
    CRITICAL = "critical" # Major leak, emergency action required


class AlertStatus(Enum):
    """Status of water alerts."""
    ACTIVE = "active"          # Alert is current and unresolved
    ACKNOWLEDGED = "acknowledged"  # Alert seen but not resolved
    RESOLVED = "resolved"      # Issue fixed, alert closed
    FALSE_POSITIVE = "false_positive"  # Alert determined to be not a leak


@dataclass
class WaterMeter:
    """Physical water meter device configuration.

    Attributes:
        meter_id: Unique meter identifier (equipment code format: SXXX-MTR-W-XXX)
        site: Building site code (e.g., "site-002")
        meter_type: Type of meter (main, submeter, irrigation, etc.)
        pulse_weight: Liters per pulse (default 10L/pulse for common meters)
        installation_date: When meter was installed
        location: Physical location description
        protocol: Communication protocol (modbus, mock)
        register_address: Modbus register address for pulse count
        max_flow_rate_lpm: Maximum expected flow rate (for spike detection)
        baseline_flow_lpm: Expected minimum flow during off-hours
        metadata: Additional meter properties
    """
    meter_id: str
    site: str
    meter_type: MeterType
    pulse_weight: float = 10.0  # 10 liters per pulse default
    installation_date: datetime = field(default_factory=datetime.now)
    location: str = ""
    protocol: str = "modbus"
    register_address: int = 0
    max_flow_rate_lpm: float = 100.0
    baseline_flow_lpm: float = 2.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "meter_id": self.meter_id,
            "site": self.site,
            "meter_type": self.meter_type.value,
            "pulse_weight": self.pulse_weight,
            "installation_date": self.installation_date.isoformat(),
            "location": self.location,
            "protocol": self.protocol,
            "register_address": self.register_address,
            "max_flow_rate_lpm": self.max_flow_rate_lpm,
            "baseline_flow_lpm": self.baseline_flow_lpm,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WaterMeter":
        """Create instance from dictionary."""
        return cls(
            meter_id=data["meter_id"],
            site=data["site"],
            meter_type=MeterType(data["meter_type"]),
            pulse_weight=data.get("pulse_weight", 10.0),
            installation_date=datetime.fromisoformat(data.get("installation_date", datetime.now().isoformat())),
            location=data.get("location", ""),
            protocol=data.get("protocol", "modbus"),
            register_address=data.get("register_address", 0),
            max_flow_rate_lpm=data.get("max_flow_rate_lpm", 100.0),
            baseline_flow_lpm=data.get("baseline_flow_lpm", 2.0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class WaterConsumption:
    """Water consumption reading at a point in time.

    Attributes:
        meter_id: Meter identifier
        timestamp: Reading timestamp
        volume_liters: Cumulative volume in liters
        flow_rate_lpm: Current flow rate in liters per minute
        pulse_count: Raw pulse count from meter
        temperature: Water temperature (optional)
        pressure: Water pressure (optional)
        zone_id: Zone identifier for zone-aware consumption tracking (optional)
        zone_name: Zone display name (optional)
    """
    meter_id: str
    timestamp: datetime
    volume_liters: float
    flow_rate_lpm: float
    pulse_count: int = 0
    temperature: Optional[float] = None
    pressure: Optional[float] = None
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "meter_id": self.meter_id,
            "timestamp": self.timestamp.isoformat(),
            "volume_liters": round(self.volume_liters, 2),
            "flow_rate_lpm": round(self.flow_rate_lpm, 2),
            "pulse_count": self.pulse_count,
            "temperature": self.temperature,
            "pressure": self.pressure,
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WaterConsumption":
        """Create instance from dictionary."""
        return cls(
            meter_id=data["meter_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            volume_liters=data["volume_liters"],
            flow_rate_lpm=data["flow_rate_lpm"],
            pulse_count=data.get("pulse_count", 0),
            temperature=data.get("temperature"),
            pressure=data.get("pressure"),
            zone_id=data.get("zone_id"),
            zone_name=data.get("zone_name"),
        )


@dataclass
class WaterAlert:
    """Water leak detection alert.

    Attributes:
        alert_id: Unique alert identifier (UUID)
        meter_id: Meter that generated the alert
        site: Building site code
        alert_type: Type of leak detected
        severity: Alert severity level
        status: Alert resolution status
        timestamp: When alert was generated
        flow_rate_lpm: Flow rate at alert time
        threshold_lpm: Threshold that was exceeded
        duration_minutes: How long condition persisted
        description: Human-readable alert description
        resolved_at: When alert was resolved
        resolved_by: User who resolved the alert
        resolution_notes: Notes on how the issue was fixed
    """
    alert_id: str
    meter_id: str
    site: str
    alert_type: AlertType
    severity: AlertSeverity
    status: AlertStatus
    timestamp: datetime
    flow_rate_lpm: float
    threshold_lpm: float
    duration_minutes: float
    description: str
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "alert_id": self.alert_id,
            "meter_id": self.meter_id,
            "site": self.site,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "flow_rate_lpm": round(self.flow_rate_lpm, 2),
            "threshold_lpm": round(self.threshold_lpm, 2),
            "duration_minutes": round(self.duration_minutes, 1),
            "description": self.description,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
            "resolution_notes": self.resolution_notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WaterAlert":
        """Create instance from dictionary."""
        return cls(
            alert_id=data["alert_id"],
            meter_id=data["meter_id"],
            site=data["site"],
            alert_type=AlertType(data["alert_type"]),
            severity=AlertSeverity(data["severity"]),
            status=AlertStatus(data["status"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            flow_rate_lpm=data["flow_rate_lpm"],
            threshold_lpm=data["threshold_lpm"],
            duration_minutes=data["duration_minutes"],
            description=data["description"],
            resolved_at=datetime.fromisoformat(data["resolved_at"]) if data.get("resolved_at") else None,
            resolved_by=data.get("resolved_by"),
            resolution_notes=data.get("resolution_notes"),
        )


@dataclass
class WaterTrend:
    """Water consumption trend analysis.

    Attributes:
        site: Building site code
        period: Analysis period (day, week, month)
        start_date: Period start
        end_date: Period end
        total_volume_liters: Total consumption
        average_flow_rate_lpm: Average flow rate
        peak_flow_rate_lpm: Peak flow rate
        baseline_comparison_percent: Change from baseline
        trend_direction: "up", "down", or "stable"
    """
    site: str
    period: str
    start_date: datetime
    end_date: datetime
    total_volume_liters: float
    average_flow_rate_lpm: float
    peak_flow_rate_lpm: float
    baseline_comparison_percent: float
    trend_direction: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "site": self.site,
            "period": self.period,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "total_volume_liters": round(self.total_volume_liters, 2),
            "average_flow_rate_lpm": round(self.average_flow_rate_lpm, 2),
            "peak_flow_rate_lpm": round(self.peak_flow_rate_lpm, 2),
            "baseline_comparison_percent": round(self.baseline_comparison_percent, 1),
            "trend_direction": self.trend_direction,
        }
