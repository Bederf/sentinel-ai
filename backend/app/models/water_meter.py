"""Water meter models for consumption tracking and leak detection.

This module defines data models for water meter integration including:
- WaterMeter: Physical meter device configuration
- WaterConsumption: Time-series consumption readings
- WaterAlert: Leak detection alerts
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional
from uuid import uuid4


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
        unit_cost_per_liter: Tariff rate at time of reading (optional)
        total_cost: Consumption volume * unit_cost_per_liter (optional)
        cost_center: For accounting attribution (optional)
        billing_period_id: Links to billing cycle (optional)
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
    unit_cost_per_liter: Optional[float] = None
    total_cost: Optional[float] = None
    cost_center: Optional[str] = None
    billing_period_id: Optional[str] = None

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
            "unit_cost_per_liter": self.unit_cost_per_liter,
            "total_cost": round(self.total_cost, 2) if self.total_cost else None,
            "cost_center": self.cost_center,
            "billing_period_id": self.billing_period_id,
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
            unit_cost_per_liter=data.get("unit_cost_per_liter"),
            total_cost=data.get("total_cost"),
            cost_center=data.get("cost_center"),
            billing_period_id=data.get("billing_period_id"),
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


@dataclass
class WaterTariff:
    """Water tariff configuration with tiered pricing.

    Attributes:
        id: Unique tariff identifier
        site: Building site code
        name: Tariff name (e.g., "Q1 2026 Summer Rate")
        effective_date: Date tariff becomes active
        end_date: Optional date tariff expires
        tier_1_liters: Free/included consumption threshold
        tier_1_rate_per_liter: Rate for tier 1 consumption
        tier_2_liters: Overage threshold for tier 2
        tier_2_rate_per_liter: Rate for tier 2 consumption
        tier_3_rate_per_liter: Rate for consumption beyond tier 2
        fixed_monthly_charge: Fixed monthly charge
        notes: Additional notes about tariff
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    site: str = ""
    name: str = ""
    effective_date: datetime = field(default_factory=datetime.now)
    end_date: Optional[datetime] = None
    tier_1_liters: float = 0.0
    tier_1_rate_per_liter: float = 0.0
    tier_2_liters: float = 1000.0
    tier_2_rate_per_liter: float = 0.0
    tier_3_rate_per_liter: float = 0.0
    fixed_monthly_charge: float = 0.0
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "site": self.site,
            "name": self.name,
            "effective_date": self.effective_date.isoformat(),
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "tier_1_liters": round(self.tier_1_liters, 2),
            "tier_1_rate_per_liter": round(self.tier_1_rate_per_liter, 4),
            "tier_2_liters": round(self.tier_2_liters, 2),
            "tier_2_rate_per_liter": round(self.tier_2_rate_per_liter, 4),
            "tier_3_rate_per_liter": round(self.tier_3_rate_per_liter, 4),
            "fixed_monthly_charge": round(self.fixed_monthly_charge, 2),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WaterTariff":
        """Create instance from dictionary."""
        return cls(
            id=data.get("id", str(uuid4())),
            site=data["site"],
            name=data["name"],
            effective_date=datetime.fromisoformat(data["effective_date"]) if isinstance(data["effective_date"], str) else data["effective_date"],
            end_date=datetime.fromisoformat(data["end_date"]) if data.get("end_date") and isinstance(data["end_date"], str) else data.get("end_date"),
            tier_1_liters=data.get("tier_1_liters", 0.0),
            tier_1_rate_per_liter=data.get("tier_1_rate_per_liter", 0.0),
            tier_2_liters=data.get("tier_2_liters", 1000.0),
            tier_2_rate_per_liter=data.get("tier_2_rate_per_liter", 0.0),
            tier_3_rate_per_liter=data.get("tier_3_rate_per_liter", 0.0),
            fixed_monthly_charge=data.get("fixed_monthly_charge", 0.0),
            notes=data.get("notes", ""),
        )


@dataclass
class WaterCost:
    """Water cost breakdown by tariff tier.

    Attributes:
        id: Unique cost record identifier
        site: Building site code
        consumption_id: Reference to consumption record
        zone_id: Zone identifier for attribution
        period_date: Date for cost period
        consumption_liters: Total consumption for period
        tariff_id: Reference to tariff used
        tier_1_cost: Cost for tier 1 consumption
        tier_2_cost: Cost for tier 2 consumption
        tier_3_cost: Cost for tier 3 consumption
        fixed_charge: Fixed monthly charge
        total_cost: Total cost (tier costs + fixed charge)
        calculated_at: Timestamp of calculation
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    site: str = ""
    consumption_id: str = ""
    zone_id: Optional[str] = None
    period_date: datetime = field(default_factory=datetime.now)
    consumption_liters: float = 0.0
    tariff_id: str = ""
    tier_1_cost: float = 0.0
    tier_2_cost: float = 0.0
    tier_3_cost: float = 0.0
    fixed_charge: float = 0.0
    total_cost: float = 0.0
    calculated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "site": self.site,
            "consumption_id": self.consumption_id,
            "zone_id": self.zone_id,
            "period_date": self.period_date.isoformat(),
            "consumption_liters": round(self.consumption_liters, 2),
            "tariff_id": self.tariff_id,
            "tier_1_cost": round(self.tier_1_cost, 4),
            "tier_2_cost": round(self.tier_2_cost, 4),
            "tier_3_cost": round(self.tier_3_cost, 4),
            "fixed_charge": round(self.fixed_charge, 2),
            "total_cost": round(self.total_cost, 2),
            "calculated_at": self.calculated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WaterCost":
        """Create instance from dictionary."""
        return cls(
            id=data.get("id", str(uuid4())),
            site=data["site"],
            consumption_id=data["consumption_id"],
            zone_id=data.get("zone_id"),
            period_date=datetime.fromisoformat(data["period_date"]) if isinstance(data["period_date"], str) else data["period_date"],
            consumption_liters=data.get("consumption_liters", 0.0),
            tariff_id=data["tariff_id"],
            tier_1_cost=data.get("tier_1_cost", 0.0),
            tier_2_cost=data.get("tier_2_cost", 0.0),
            tier_3_cost=data.get("tier_3_cost", 0.0),
            fixed_charge=data.get("fixed_charge", 0.0),
            total_cost=data.get("total_cost", 0.0),
            calculated_at=datetime.fromisoformat(data["calculated_at"]) if isinstance(data.get("calculated_at"), str) else data.get("calculated_at", datetime.now()),
        )
