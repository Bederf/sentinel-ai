"""Solar PV and BESS data models for SENTINEL Solar Module.

Equipment hierarchy: Site > Plant > Inverter > String (PV)
                     Site > BESSContainer > BESSRack (storage)
                     Site > GridMeter (metering)

Follows the dataclass pattern established in energy_centre.py.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional


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
    GOOD = "good"              # Fresh data, < 30s old
    STALE = "stale"            # Data > 60s old
    INTERPOLATED = "interpolated"  # Gap-filled
    SUSPECT = "suspect"        # Out of expected range


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
    commissioning_date: Optional[str] = None
    latitude: float = -26.2  # Johannesburg default
    longitude: float = 28.0
    orientation: float = 0.0  # Azimuth degrees (0 = north)
    tilt: float = 20.0  # Degrees from horizontal

    def to_dict(self) -> Dict[str, Any]:
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
    ip_address: Optional[str] = None
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
    alarms: List[str] = field(default_factory=list)
    last_poll: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inverter_id": self.inverter_id,
            "plant_id": self.plant_id,
            "site_id": self.site_id,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial": self.serial,
            "rated_power_kva": self.rated_power_kva,
            "mppt_count": self.mppt_count,
            "firmware_version": self.firmware_version,
            "protocol": self.protocol,
            "ip_address": self.ip_address,
            "port": self.port,
            "unit_id": self.unit_id,
            "dc_power_kw": self.dc_power_kw,
            "ac_power_kw": self.ac_power_kw,
            "efficiency_pct": self.efficiency_pct,
            "temp_c": self.temp_c,
            "status": self.status,
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

    def to_dict(self) -> Dict[str, Any]:
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
    alarms: List[str] = field(default_factory=list)
    last_poll: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "container_id": self.container_id,
            "site_id": self.site_id,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "capacity_kwh": self.capacity_kwh,
            "rated_power_kw": self.rated_power_kw,
            "rack_count": self.rack_count,
            "cell_chemistry": self.cell_chemistry,
            "protocol": self.protocol,
            "soc_pct": self.soc_pct,
            "soh_pct": self.soh_pct,
            "charge_power_kw": self.charge_power_kw,
            "discharge_power_kw": self.discharge_power_kw,
            "mode": self.mode,
            "temp_c": self.temp_c,
            "cell_min_v": self.cell_min_v,
            "cell_max_v": self.cell_max_v,
            "cell_imbalance_mv": self.cell_imbalance_mv,
            "cycles_count": self.cycles_count,
            "alarms": self.alarms,
            "last_poll": self.last_poll,
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

    def to_dict(self) -> Dict[str, Any]:
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

    def to_dict(self) -> Dict[str, Any]:
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

    def to_dict(self) -> Dict[str, Any]:
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
    last_poll: Optional[str] = None
    error_count: int = 0
    stale_threshold_seconds: int = 60

    def to_dict(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "last_poll": self.last_poll,
            "error_count": self.error_count,
            "stale_threshold_seconds": self.stale_threshold_seconds,
        }
