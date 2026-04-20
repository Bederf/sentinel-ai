"""Solar PV and BESS data models for SENTINEL Solar Module.

Equipment hierarchy: Site > Plant > Inverter > String (PV)
                     Site > BESSContainer > BESSRack (storage)
                     Site > GridMeter (metering)

Follows the dataclass pattern established in energy_centre.py.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# === Enums ===


class SolarEquipmentType(str, Enum):
    """Types of solar/BESS equipment."""

    INVERTER = "inverter"
    STRING = "string"
    BESS_CONTAINER = "bess_container"
    BESS_RACK = "bess_rack"
    GRID_METER = "grid_meter"
    PLANT = "plant"


class InverterStatus(str, Enum):
    """Inverter operational status."""

    ONLINE = "online"
    WARNING = "warning"
    FAULT = "fault"
    OFFLINE = "offline"


class BESSMode(str, Enum):
    """BESS operating mode."""

    CHARGING = "charging"
    DISCHARGING = "discharging"
    IDLE = "idle"
    STANDBY = "standby"


class QualityFlag(str, Enum):
    """Data quality flags for normalised readings."""

    GOOD = "good"  # Fresh data, < 30s old
    STALE = "stale"  # Data > 60s old
    INTERPOLATED = "interpolated"  # Gap-filled
    SUSPECT = "suspect"  # Out of expected range


class ReadingType(str, Enum):
    """Types of normalised readings."""

    POWER = "power"
    ENERGY = "energy"
    VOLTAGE = "voltage"
    CURRENT = "current"
    TEMPERATURE = "temperature"
    SOC = "soc"
    IRRADIANCE = "irradiance"
    FREQUENCY = "frequency"
    POWER_FACTOR = "power_factor"
    THD = "thd"


class DataSource(str, Enum):
    """Source of data."""

    MODBUS = "modbus"
    CLOUD_API = "cloud_api"
    BMS = "bms"
    SIMULATED = "simulated"


class ConnectorProtocol(str, Enum):
    """Communication protocol for connectors."""

    MODBUS_TCP = "modbus_tcp"
    CLOUD_API = "cloud_api"
    BACNET = "bacnet"


# === Plant ===


@dataclass
class SolarPlant:
    """Top-level solar plant entity (L1 in hierarchy)."""

    plant_id: str
    name: str
    site_id: str
    capacity_kwp: float
    panel_count: int
    inverter_count: int

    # Configuration
    panel_model: str = ""
    panel_rating_w: float = 0.0
    commissioning_date: str | None = None
    latitude: float = -26.2  # Johannesburg default
    longitude: float = 28.0
    orientation: float = 0.0  # Azimuth degrees (0 = north)
    tilt: float = 20.0  # Degrees from horizontal

    def to_dict(self) -> dict[str, Any]:
        return {
            "plant_id": self.plant_id,
            "name": self.name,
            "site_id": self.site_id,
            "capacity_kwp": self.capacity_kwp,
            "panel_count": self.panel_count,
            "inverter_count": self.inverter_count,
            "panel_model": self.panel_model,
            "panel_rating_w": self.panel_rating_w,
            "commissioning_date": self.commissioning_date,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "orientation": self.orientation,
            "tilt": self.tilt,
        }


# === Inverter ===


@dataclass
class SolarInverter:
    """Solar inverter entity (L3 in hierarchy)."""

    inverter_id: str
    plant_id: str
    site_id: str
    name: str
    manufacturer: str
    model: str
    rated_power_kva: float

    # Configuration
    serial: str = ""
    mppt_count: int = 1
    firmware_version: str = ""
    protocol: str = "modbus_tcp"
    ip_address: str | None = None
    port: int = 502
    unit_id: int = 1

    # Runtime state
    dc_power_kw: float = 0.0
    ac_power_kw: float = 0.0
    efficiency_pct: float = 0.0
    temp_c: float = 25.0
    status: str = "online"  # online/warning/fault/offline
    frequency_hz: float = 50.0
    power_factor: float = 1.0
    daily_yield_kwh: float = 0.0
    total_yield_mwh: float = 0.0
    alarms: list[str] = field(default_factory=list)
    last_poll: str | None = None

    # Map backend status values to frontend-expected values
    _STATUS_MAP = {"online": "normal", "standby": "offline"}

    def to_dict(self) -> dict[str, Any]:
        frontend_status = self._STATUS_MAP.get(self.status, self.status)
        return {
            "inverter_id": self.inverter_id,
            "plant_id": self.plant_id,
            "site_id": self.site_id,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial": self.serial,
            "rated_power_kva": self.rated_power_kva,
            "rated_power_kw": self.rated_power_kva,  # Alias for frontend
            "mppt_count": self.mppt_count,
            "string_count": self.mppt_count,  # Frontend expects string_count
            "firmware_version": self.firmware_version,
            "protocol": self.protocol,
            "ip_address": self.ip_address,
            "port": self.port,
            "unit_id": self.unit_id,
            "dc_power_kw": self.dc_power_kw,
            "ac_power_kw": self.ac_power_kw,
            "current_power_kw": self.ac_power_kw,  # Alias for frontend
            "efficiency_pct": self.efficiency_pct,
            "efficiency_percent": self.efficiency_pct,  # Alias for frontend
            "temp_c": self.temp_c,
            "temperature_c": self.temp_c,  # Alias for frontend
            "status": frontend_status,
            "frequency_hz": self.frequency_hz,
            "power_factor": self.power_factor,
            "daily_yield_kwh": self.daily_yield_kwh,
            "total_yield_mwh": self.total_yield_mwh,
            "alarms": self.alarms,
            "last_poll": self.last_poll,
        }


# === String ===


@dataclass
class SolarString:
    """PV string entity (L4 in hierarchy)."""

    string_id: str
    inverter_id: str
    mppt_tracker: int
    panel_count: int

    # Configuration
    panel_model: str = ""
    panel_rating_w: float = 0.0

    # Runtime state
    dc_voltage_v: float = 0.0
    dc_current_a: float = 0.0
    dc_power_kw: float = 0.0
    irradiance_w_m2: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "string_id": self.string_id,
            "inverter_id": self.inverter_id,
            "mppt_tracker": self.mppt_tracker,
            "panel_count": self.panel_count,
            "panel_model": self.panel_model,
            "panel_rating_w": self.panel_rating_w,
            "dc_voltage_v": self.dc_voltage_v,
            "dc_current_a": self.dc_current_a,
            "dc_power_kw": self.dc_power_kw,
            "irradiance_w_m2": self.irradiance_w_m2,
        }


# === BESS Container ===


@dataclass
class BESSContainer:
    """Battery Energy Storage System container (L5 in hierarchy)."""

    container_id: str
    site_id: str
    name: str
    manufacturer: str
    model: str
    capacity_kwh: float
    rated_power_kw: float

    # Configuration
    rack_count: int = 1
    cell_chemistry: str = "LFP"  # LFP, NMC, LTO
    protocol: str = "modbus_tcp"

    # Runtime state
    soc_pct: float = 50.0
    soh_pct: float = 100.0
    charge_power_kw: float = 0.0
    discharge_power_kw: float = 0.0
    mode: str = "idle"  # charging/discharging/idle/standby
    temp_c: float = 25.0
    cell_min_v: float = 3.2
    cell_max_v: float = 3.4
    cell_imbalance_mv: float = 20.0
    cycles_count: int = 0
    alarms: list[str] = field(default_factory=list)
    last_poll: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bess_id": self.container_id,
            "site_id": self.site_id,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "total_capacity_kwh": self.capacity_kwh,
            "usable_capacity_kwh": self.capacity_kwh * 0.9,  # Assume 90% usable
            "soc_percent": self.soc_pct,
            "soh_percent": self.soh_pct,
            "mode": self.mode,
            "charge_power_kw": self.charge_power_kw,
            "discharge_power_kw": self.discharge_power_kw,
            "current_power_kw": self.discharge_power_kw
            if self.mode == "discharging"
            else (self.charge_power_kw if self.mode == "charging" else 0.0),
            "temperature_c": self.temp_c,
            "cycle_count": self.cycles_count,
            "estimated_runtime_min": int(
                (self.capacity_kwh * self.soc_pct / 100) / max(self.discharge_power_kw, 1.0) * 60
            )
            if self.discharge_power_kw > 0
            else 0,
            "rack_count": self.rack_count,
            "alarms": self.alarms,
            "status": "fault" if self.alarms else "normal",
        }


# === BESS Rack ===


@dataclass
class BESSRack:
    """Individual BESS rack within a container."""

    rack_id: str
    container_id: str
    capacity_kwh: float

    # Runtime state
    soc_pct: float = 50.0
    temp_c: float = 25.0
    cell_count: int = 0
    status: str = "online"  # online/warning/fault/offline

    def to_dict(self) -> dict[str, Any]:
        return {
            "rack_id": self.rack_id,
            "container_id": self.container_id,
            "capacity_kwh": self.capacity_kwh,
            "soc_pct": self.soc_pct,
            "temp_c": self.temp_c,
            "cell_count": self.cell_count,
            "status": self.status,
        }


# === Grid Meter ===


@dataclass
class GridMeter:
    """Grid interface meter for import/export monitoring."""

    meter_id: str
    site_id: str
    name: str
    manufacturer: str
    model: str
    protocol: str = "modbus_tcp"

    # Runtime state
    import_kw: float = 0.0
    export_kw: float = 0.0
    voltage_v: float = 400.0
    current_a: float = 0.0
    frequency_hz: float = 50.0
    power_factor: float = 1.0
    thd_pct: float = 0.0
    daily_import_kwh: float = 0.0
    daily_export_kwh: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "meter_id": self.meter_id,
            "site_id": self.site_id,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "protocol": self.protocol,
            "import_kw": self.import_kw,
            "export_kw": self.export_kw,
            "voltage_v": self.voltage_v,
            "current_a": self.current_a,
            "frequency_hz": self.frequency_hz,
            "power_factor": self.power_factor,
            "thd_pct": self.thd_pct,
            "daily_import_kwh": self.daily_import_kwh,
            "daily_export_kwh": self.daily_export_kwh,
        }


# === Normalised Reading ===


@dataclass
class NormalisedReading:
    """Protocol-agnostic normalised reading from any solar/BESS equipment."""

    timestamp: str
    equipment_id: str
    equipment_type: str  # inverter/bess/meter/string
    reading_type: str  # power/energy/voltage/current/temp/soc/irradiance
    value: float
    unit: str
    quality_flag: str = "good"  # good/stale/interpolated/suspect
    source: str = "modbus"  # modbus/cloud_api/bms/simulated

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "equipment_id": self.equipment_id,
            "equipment_type": self.equipment_type,
            "reading_type": self.reading_type,
            "value": self.value,
            "unit": self.unit,
            "quality_flag": self.quality_flag,
            "source": self.source,
        }


# === Connector Status ===


@dataclass
class ConnectorStatus:
    """Status of a manufacturer connector."""

    connected: bool = False
    last_poll: str | None = None
    error_count: int = 0
    stale_threshold_seconds: int = 60

    def to_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "last_poll": self.last_poll,
            "error_count": self.error_count,
            "stale_threshold_seconds": self.stale_threshold_seconds,
        }


# === Grid Compliance Models (Phase 34, Module 8) ===


class GridCode(str, Enum):
    """Grid compliance standards."""

    NRS_097_2_3 = "nrs_097_2_3"  # South African grid code
    IEC_61727 = "iec_61727"  # International standard
    IEEE_1547 = "ieee_1547"  # US standard


class GridParameter(str, Enum):
    """Grid parameters being monitored."""

    FREQUENCY = "frequency"
    VOLTAGE = "voltage"
    CURRENT = "current"
    POWER_FACTOR = "power_factor"
    THD = "thd"
    RAMP_RATE = "ramp_rate"


class ComplianceSeverity(str, Enum):
    """Severity of compliance violations."""

    CRITICAL = "critical"  # Immediate action required, trip threshold
    WARNING = "warning"  # Action recommended, pre-violation
    INFO = "info"  # Informational only


@dataclass
class FrequencyBand:
    """Frequency operating band for a grid code."""

    band_name: str  # "normal", "recovery", "emergency"
    min_hz: float
    max_hz: float
    trip_low_hz: float | None = None  # Mandatory disconnect point
    trip_high_hz: float | None = None
    disconnect_delay_ms: int = 200  # Max time before mandatory disconnect


@dataclass
class VoltageBand:
    """Voltage operating band for a grid code (per phase)."""

    band_name: str  # "normal", "recovery", "emergency"
    nominal_v: float
    min_v: float
    max_v: float
    trip_low_v: float | None = None
    trip_high_v: float | None = None
    disconnect_delay_ms: int = 500


@dataclass
class RampRateLimit:
    """Maximum rate of power change (percentage per minute)."""

    condition: str  # "normal", "curtailment", "recovery"
    max_pct_per_min: float
    applies_to: str = "ac_power"  # Which power measurement


@dataclass
class ComplianceViolation:
    """Record of a grid code violation."""

    timestamp: str  # ISO 8601 datetime
    system_id: str  # Inverter or site ID
    parameter: str  # frequency, voltage, ramp_rate, etc.
    measured_value: float
    limit_value: float
    violation_type: str  # exceeds_max, below_min, ramp_too_fast
    severity: str  # critical, warning, info
    auto_action: str | None = None  # "curtailment", "standby", "droop", etc.
    duration_ms: int | None = None  # Time until resolution
    resolved: bool = False
    resolution_time: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "system_id": self.system_id,
            "parameter": self.parameter,
            "measured_value": self.measured_value,
            "limit_value": self.limit_value,
            "violation_type": self.violation_type,
            "severity": self.severity,
            "auto_action": self.auto_action,
            "duration_ms": self.duration_ms,
            "resolved": self.resolved,
            "resolution_time": self.resolution_time,
        }


@dataclass
class GridComplianceStatus:
    """Current grid compliance status snapshot."""

    system_id: str
    grid_code: str
    compliant: bool
    last_check: str  # ISO 8601 datetime
    next_check: str  # ISO 8601 datetime
    active_violations: list[ComplianceViolation] = field(default_factory=list)
    frequency_hz: float = 50.0
    voltage_v: float = 400.0
    current_a: float = 0.0
    power_factor: float = 1.0
    temperature_c: float = 25.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_id": self.system_id,
            "grid_code": self.grid_code,
            "compliant": self.compliant,
            "last_check": self.last_check,
            "next_check": self.next_check,
            "active_violations": [v.to_dict() for v in self.active_violations],
            "measurements": {
                "frequency_hz": self.frequency_hz,
                "voltage_v": self.voltage_v,
                "current_a": self.current_a,
                "power_factor": self.power_factor,
                "temperature_c": self.temperature_c,
            },
        }


@dataclass
class LoadShedEvent:
    """Load shedding stage transition event."""

    timestamp: str  # ISO 8601 datetime
    frequency_hz: float
    previous_stage: int
    current_stage: int
    dispatch_action: str  # "bess_discharge", "solar_curtailment", "standby", "ramp_up"
    affected_systems: list[str] = field(default_factory=list)  # equipment IDs
    expected_reduction_kw: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "frequency_hz": self.frequency_hz,
            "previous_stage": self.previous_stage,
            "current_stage": self.current_stage,
            "dispatch_action": self.dispatch_action,
            "affected_systems": self.affected_systems,
            "expected_reduction_kw": self.expected_reduction_kw,
        }
