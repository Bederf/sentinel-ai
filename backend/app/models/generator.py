"""Generator Models for DeepSea DSE Controller Integration.

Defines data structures for generator sets with Modbus/SCADA monitoring.
Supports N+1 redundancy, diesel fuel tracking, and predictive maintenance.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional


class GeneratorStatus(str, Enum):
    """Operating status of a generator."""
    STANDBY = "standby"           # Ready to start
    RUNNING = "running"           # Engine running, not on load
    ON_LOAD = "on_load"           # Running and supplying load
    COOLING = "cooling"           # Post-run cooldown
    MAINTENANCE = "maintenance"   # Out of service
    FAULT = "fault"               # Alarm condition
    OFFLINE = "offline"           # Not communicating


class ControllerModel(str, Enum):
    """DeepSea controller models."""
    DSE7320 = "DSE7320"           # Standard AMF/ATS controller
    DSE7420 = "DSE7420"           # Advanced with load share
    DSE8610 = "DSE8610"           # Parallel/synchronizing
    DSE8660 = "DSE8660"           # Advanced parallel


class TransferMode(str, Enum):
    """ATS transfer mode."""
    OPEN = "open"                 # Open transition (break before make)
    CLOSED = "closed"             # Closed transition (brief parallel)
    SOFT_LOAD = "soft_load"       # Ramped load transfer


@dataclass
class DieselTank:
    """Diesel fuel storage tank."""

    tank_id: str
    name: str
    capacity_liters: float
    current_level_liters: float
    current_level_pct: float
    low_level_alarm_pct: float = 20.0
    reorder_level_pct: float = 30.0
    last_fill_date: Optional[str] = None
    last_fill_liters: Optional[float] = None
    daily_consumption_avg: float = 0.0  # Average L/day based on runtime
    days_remaining: Optional[float] = None  # Estimated days until empty
    supplier: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tank_id": self.tank_id,
            "name": self.name,
            "capacity_liters": self.capacity_liters,
            "current_level_liters": self.current_level_liters,
            "current_level_pct": self.current_level_pct,
            "low_level_alarm_pct": self.low_level_alarm_pct,
            "reorder_level_pct": self.reorder_level_pct,
            "last_fill_date": self.last_fill_date,
            "last_fill_liters": self.last_fill_liters,
            "daily_consumption_avg": self.daily_consumption_avg,
            "days_remaining": self.days_remaining,
            "supplier": self.supplier,
        }


@dataclass
class GeneratorEngine:
    """Engine parameters from DeepSea controller."""

    rpm: int = 0
    oil_pressure_kpa: float = 0.0
    coolant_temp_c: float = 0.0
    oil_temp_c: Optional[float] = None
    exhaust_temp_c: Optional[float] = None
    turbo_pressure_kpa: Optional[float] = None
    run_hours: float = 0.0
    total_starts: int = 0
    current_runtime_sec: int = 0
    fuel_rate_lph: float = 0.0  # Liters per hour

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "rpm": self.rpm,
            "oil_pressure_kpa": self.oil_pressure_kpa,
            "coolant_temp_c": self.coolant_temp_c,
            "oil_temp_c": self.oil_temp_c,
            "exhaust_temp_c": self.exhaust_temp_c,
            "turbo_pressure_kpa": self.turbo_pressure_kpa,
            "run_hours": self.run_hours,
            "total_starts": self.total_starts,
            "current_runtime_sec": self.current_runtime_sec,
            "fuel_rate_lph": self.fuel_rate_lph,
        }


@dataclass
class GeneratorElectrical:
    """Electrical output parameters."""

    voltage_l1: float = 0.0
    voltage_l2: float = 0.0
    voltage_l3: float = 0.0
    voltage_l1_l2: float = 0.0
    voltage_l2_l3: float = 0.0
    voltage_l3_l1: float = 0.0
    current_l1: float = 0.0
    current_l2: float = 0.0
    current_l3: float = 0.0
    frequency_hz: float = 0.0
    power_kw: float = 0.0
    power_kva: float = 0.0
    power_factor: float = 0.0
    total_kwh: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "voltage_l1": self.voltage_l1,
            "voltage_l2": self.voltage_l2,
            "voltage_l3": self.voltage_l3,
            "voltage_l1_l2": self.voltage_l1_l2,
            "voltage_l2_l3": self.voltage_l2_l3,
            "voltage_l3_l1": self.voltage_l3_l1,
            "current_l1": self.current_l1,
            "current_l2": self.current_l2,
            "current_l3": self.current_l3,
            "frequency_hz": self.frequency_hz,
            "power_kw": self.power_kw,
            "power_kva": self.power_kva,
            "power_factor": self.power_factor,
            "total_kwh": self.total_kwh,
        }


@dataclass
class GeneratorAlarm:
    """Active alarm or warning."""

    code: str
    description: str
    severity: str  # "warning", "alarm", "shutdown"
    timestamp: str
    acknowledged: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "code": self.code,
            "description": self.description,
            "severity": self.severity,
            "timestamp": self.timestamp,
            "acknowledged": self.acknowledged,
        }


@dataclass
class Generator:
    """Generator set with DeepSea controller."""

    generator_id: str
    name: str
    site_id: str
    building: str
    location: str  # Physical location (e.g., "Basement Plant Room")

    # Controller
    controller_model: str
    controller_ip: str

    # Ratings (required - no defaults)
    rated_power_kw: float
    rated_power_kva: float

    # Controller defaults
    modbus_port: int = 502
    modbus_unit_id: int = 1

    # Rating defaults
    rated_voltage: float = 400.0
    rated_frequency: float = 50.0

    # Status
    status: str = "standby"
    mains_available: bool = True
    engine_running: bool = False
    on_load: bool = False

    # Battery/starter
    battery_voltage: float = 27.0
    charger_current: float = 2.0
    start_attempts: int = 0

    # Fuel
    fuel_level_pct: float = 100.0
    fuel_tank_id: Optional[str] = None  # Reference to shared tank

    # Sub-structures (populated from telemetry)
    engine: Optional[Dict] = None
    electrical: Optional[Dict] = None
    alarms: List[Dict] = field(default_factory=list)

    # Maintenance
    next_service_hours: float = 500.0
    last_service_date: Optional[str] = None

    # Redundancy group
    group_id: Optional[str] = None  # For N+1 grouping
    priority: int = 1  # Start priority within group (1=primary)

    # Communication
    last_poll: Optional[str] = None
    poll_errors: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "generator_id": self.generator_id,
            "name": self.name,
            "site_id": self.site_id,
            "building": self.building,
            "location": self.location,
            "controller_model": self.controller_model,
            "controller_ip": self.controller_ip,
            "modbus_port": self.modbus_port,
            "modbus_unit_id": self.modbus_unit_id,
            "rated_power_kw": self.rated_power_kw,
            "rated_power_kva": self.rated_power_kva,
            "rated_voltage": self.rated_voltage,
            "rated_frequency": self.rated_frequency,
            "status": self.status,
            "mains_available": self.mains_available,
            "engine_running": self.engine_running,
            "on_load": self.on_load,
            "battery_voltage": self.battery_voltage,
            "charger_current": self.charger_current,
            "start_attempts": self.start_attempts,
            "fuel_level_pct": self.fuel_level_pct,
            "fuel_tank_id": self.fuel_tank_id,
            "engine": self.engine,
            "electrical": self.electrical,
            "alarms": self.alarms,
            "next_service_hours": self.next_service_hours,
            "last_service_date": self.last_service_date,
            "group_id": self.group_id,
            "priority": self.priority,
            "last_poll": self.last_poll,
            "poll_errors": self.poll_errors,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Generator":
        """Create instance from dictionary."""
        return cls(
            generator_id=data.get("generator_id", ""),
            name=data.get("name", ""),
            site_id=data.get("site_id", ""),
            building=data.get("building", ""),
            location=data.get("location", ""),
            controller_model=data.get("controller_model", "DSE7320"),
            controller_ip=data.get("controller_ip", ""),
            modbus_port=data.get("modbus_port", 502),
            modbus_unit_id=data.get("modbus_unit_id", 1),
            rated_power_kw=data.get("rated_power_kw", 0),
            rated_power_kva=data.get("rated_power_kva", 0),
            rated_voltage=data.get("rated_voltage", 400.0),
            rated_frequency=data.get("rated_frequency", 50.0),
            status=data.get("status", "standby"),
            mains_available=data.get("mains_available", True),
            engine_running=data.get("engine_running", False),
            on_load=data.get("on_load", False),
            battery_voltage=data.get("battery_voltage", 27.0),
            charger_current=data.get("charger_current", 2.0),
            start_attempts=data.get("start_attempts", 0),
            fuel_level_pct=data.get("fuel_level_pct", 100.0),
            fuel_tank_id=data.get("fuel_tank_id"),
            engine=data.get("engine"),
            electrical=data.get("electrical"),
            alarms=data.get("alarms", []),
            next_service_hours=data.get("next_service_hours", 500.0),
            last_service_date=data.get("last_service_date"),
            group_id=data.get("group_id"),
            priority=data.get("priority", 1),
            last_poll=data.get("last_poll"),
            poll_errors=data.get("poll_errors", 0),
        )


@dataclass
class GeneratorGroup:
    """N+1 redundancy group for multiple generators."""

    group_id: str
    name: str
    site_id: str
    building: str

    # Configuration
    total_generators: int
    required_running: int  # N (e.g., 2 out of 4)
    transfer_mode: str = "open"  # "open", "closed", "soft_load"

    # Generator references
    generator_ids: List[str] = field(default_factory=list)

    # Current state
    generators_running: int = 0
    total_load_kw: float = 0.0
    total_capacity_kw: float = 0.0
    load_percent: float = 0.0

    # ATS status
    ats_position: str = "mains"  # "mains", "generator", "transitioning"
    mains_healthy: bool = True

    # Shared fuel
    diesel_tank_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "group_id": self.group_id,
            "name": self.name,
            "site_id": self.site_id,
            "building": self.building,
            "total_generators": self.total_generators,
            "required_running": self.required_running,
            "transfer_mode": self.transfer_mode,
            "generator_ids": self.generator_ids,
            "generators_running": self.generators_running,
            "total_load_kw": self.total_load_kw,
            "total_capacity_kw": self.total_capacity_kw,
            "load_percent": self.load_percent,
            "ats_position": self.ats_position,
            "mains_healthy": self.mains_healthy,
            "diesel_tank_id": self.diesel_tank_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GeneratorGroup":
        """Create instance from dictionary."""
        return cls(
            group_id=data.get("group_id", ""),
            name=data.get("name", ""),
            site_id=data.get("site_id", ""),
            building=data.get("building", ""),
            total_generators=data.get("total_generators", 0),
            required_running=data.get("required_running", 0),
            transfer_mode=data.get("transfer_mode", "open"),
            generator_ids=data.get("generator_ids", []),
            generators_running=data.get("generators_running", 0),
            total_load_kw=data.get("total_load_kw", 0.0),
            total_capacity_kw=data.get("total_capacity_kw", 0.0),
            load_percent=data.get("load_percent", 0.0),
            ats_position=data.get("ats_position", "mains"),
            mains_healthy=data.get("mains_healthy", True),
            diesel_tank_id=data.get("diesel_tank_id"),
        )


@dataclass
class PredictiveIndicator:
    """Predictive maintenance indicator."""

    parameter: str
    current_value: float
    threshold_low: Optional[float] = None
    threshold_high: Optional[float] = None
    trend: str = "stable"  # "improving", "stable", "degrading", "critical"
    days_to_threshold: Optional[int] = None
    recommendation: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "parameter": self.parameter,
            "current_value": self.current_value,
            "threshold_low": self.threshold_low,
            "threshold_high": self.threshold_high,
            "trend": self.trend,
            "days_to_threshold": self.days_to_threshold,
            "recommendation": self.recommendation,
        }


@dataclass
class GeneratorHealth:
    """Health assessment for a generator."""

    generator_id: str
    overall_score: float  # 0-100
    status: str  # "healthy", "attention", "warning", "critical"
    indicators: List[PredictiveIndicator] = field(default_factory=list)
    last_assessment: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "generator_id": self.generator_id,
            "overall_score": self.overall_score,
            "status": self.status,
            "indicators": [i.to_dict() for i in self.indicators],
            "last_assessment": self.last_assessment,
        }
