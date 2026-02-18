"""Energy Centre Models for Complete Electrical Infrastructure.

Covers MV/LV switchgear, ATS, transformers, power metering, PFC, and UPS.
Typical South African commercial building configuration.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional


# === Enums ===

class ATSType(str, Enum):
    """ATS changeover mechanism type."""
    MECHANICAL = "mechanical"         # Motorized contactors (Socomec, ABB)
    ELECTRONIC = "electronic"         # Solid-state/static transfer
    HYBRID = "hybrid"                 # Mechanical with electronic control


class ATSPosition(str, Enum):
    """ATS position states."""
    MAINS = "mains"
    GENERATOR = "generator"
    OFF = "off"                       # Both open (break-before-make)
    TRANSITIONING = "transitioning"
    PARALLEL = "parallel"             # Brief parallel for closed-transition
    FAULT = "fault"


class BreakerState(str, Enum):
    """Circuit breaker states."""
    OPEN = "open"
    CLOSED = "closed"
    TRIPPED = "tripped"
    RACKING_IN = "racking_in"
    RACKING_OUT = "racking_out"
    WITHDRAWN = "withdrawn"


class TransformerTapPosition(str, Enum):
    """Transformer tap changer positions."""
    LOWER = "lower"      # -5% to -2.5%
    NOMINAL = "nominal"  # 0%
    RAISE = "raise"      # +2.5% to +5%


# === ATS / Transfer Switch ===

@dataclass
class ATSUnit:
    """Automatic Transfer Switch unit."""

    ats_id: str
    name: str
    site_id: str
    location: str

    # Configuration
    ats_type: str = "mechanical"      # mechanical, electronic, hybrid
    rated_current_a: float = 2500.0
    rated_voltage: float = 400.0
    poles: int = 4                    # 3P+N
    transfer_mode: str = "closed"     # open, closed, soft_load

    # Current state
    position: str = "mains"           # mains, generator, off, transitioning, parallel
    mains_available: bool = True
    generator_available: bool = True

    # Breaker states (for motorized ACB type)
    mains_breaker: str = "closed"     # open, closed, tripped
    gen_breaker: str = "open"
    bus_coupler: Optional[str] = None  # For split-bus configurations

    # Transfer metrics
    last_transfer_time_ms: int = 0    # Time taken for last transfer
    transfer_count: int = 0           # Total transfer operations
    last_transfer_timestamp: Optional[str] = None
    last_transfer_reason: Optional[str] = None  # "mains_fail", "test", "scheduled"

    # Interlocks
    mechanical_interlock_ok: bool = True
    electrical_interlock_ok: bool = True

    # Communication
    controller_ip: Optional[str] = None
    protocol: str = "modbus"          # modbus, bacnet, proprietary
    last_poll: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ats_id": self.ats_id,
            "name": self.name,
            "site_id": self.site_id,
            "location": self.location,
            "ats_type": self.ats_type,
            "rated_current_a": self.rated_current_a,
            "rated_voltage": self.rated_voltage,
            "poles": self.poles,
            "transfer_mode": self.transfer_mode,
            "position": self.position,
            "mains_available": self.mains_available,
            "generator_available": self.generator_available,
            "mains_breaker": self.mains_breaker,
            "gen_breaker": self.gen_breaker,
            "bus_coupler": self.bus_coupler,
            "last_transfer_time_ms": self.last_transfer_time_ms,
            "transfer_count": self.transfer_count,
            "last_transfer_timestamp": self.last_transfer_timestamp,
            "last_transfer_reason": self.last_transfer_reason,
            "mechanical_interlock_ok": self.mechanical_interlock_ok,
            "electrical_interlock_ok": self.electrical_interlock_ok,
            "controller_ip": self.controller_ip,
            "protocol": self.protocol,
            "last_poll": self.last_poll,
        }


# === MV Switchgear ===

@dataclass
class MVIncomer:
    """Medium Voltage incomer (typically 11kV from Eskom)."""

    incomer_id: str
    name: str
    site_id: str
    location: str

    # Ratings
    nominal_voltage_kv: float = 11.0
    rated_current_a: float = 630.0
    fault_level_mva: float = 250.0

    # Current readings
    voltage_kv: float = 11.0
    current_a: float = 0.0
    power_kw: float = 0.0
    power_factor: float = 0.95
    frequency_hz: float = 50.0

    # Status
    breaker_state: str = "closed"     # open, closed, tripped
    healthy: bool = True

    # Protection relay (e.g., Siemens SIPROTEC, ABB REF615)
    protection_relay_model: Optional[str] = None
    overcurrent_pickup_a: float = 800.0
    earth_fault_pickup_a: float = 50.0
    last_trip_timestamp: Optional[str] = None
    last_trip_code: Optional[str] = None

    # Eskom supply point
    supply_point_id: Optional[str] = None  # NRS number
    tariff_type: Optional[str] = None      # Megaflex, Miniflex, etc.

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incomer_id": self.incomer_id,
            "name": self.name,
            "site_id": self.site_id,
            "location": self.location,
            "nominal_voltage_kv": self.nominal_voltage_kv,
            "rated_current_a": self.rated_current_a,
            "fault_level_mva": self.fault_level_mva,
            "voltage_kv": self.voltage_kv,
            "current_a": self.current_a,
            "power_kw": self.power_kw,
            "power_factor": self.power_factor,
            "frequency_hz": self.frequency_hz,
            "breaker_state": self.breaker_state,
            "healthy": self.healthy,
            "protection_relay_model": self.protection_relay_model,
            "overcurrent_pickup_a": self.overcurrent_pickup_a,
            "earth_fault_pickup_a": self.earth_fault_pickup_a,
            "last_trip_timestamp": self.last_trip_timestamp,
            "last_trip_code": self.last_trip_code,
            "supply_point_id": self.supply_point_id,
            "tariff_type": self.tariff_type,
        }


# === Transformers ===

@dataclass
class Transformer:
    """MV/LV Transformer."""

    transformer_id: str
    name: str
    site_id: str
    location: str

    # Ratings
    rated_power_kva: float = 2000.0
    primary_voltage_kv: float = 11.0
    secondary_voltage_v: float = 400.0
    vector_group: str = "Dyn11"
    impedance_pct: float = 6.0

    # Current state
    load_kva: float = 0.0
    load_percent: float = 0.0

    # Temperatures
    oil_temp_c: Optional[float] = None
    winding_temp_c: Optional[float] = None
    ambient_temp_c: Optional[float] = None

    # Tap changer
    tap_position: int = 0            # -2, -1, 0, +1, +2 typical
    tap_range_pct: float = 5.0       # +/- 5%
    on_load_tap_changer: bool = False

    # Status
    healthy: bool = True
    oil_level_ok: bool = True
    buchholz_alarm: bool = False     # Gas accumulation alarm
    pressure_relief_ok: bool = True

    # Cooling
    cooling_type: str = "ONAN"       # ONAN, ONAF, etc.
    fans_running: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transformer_id": self.transformer_id,
            "name": self.name,
            "site_id": self.site_id,
            "location": self.location,
            "rated_power_kva": self.rated_power_kva,
            "primary_voltage_kv": self.primary_voltage_kv,
            "secondary_voltage_v": self.secondary_voltage_v,
            "vector_group": self.vector_group,
            "impedance_pct": self.impedance_pct,
            "load_kva": self.load_kva,
            "load_percent": self.load_percent,
            "oil_temp_c": self.oil_temp_c,
            "winding_temp_c": self.winding_temp_c,
            "ambient_temp_c": self.ambient_temp_c,
            "tap_position": self.tap_position,
            "tap_range_pct": self.tap_range_pct,
            "on_load_tap_changer": self.on_load_tap_changer,
            "healthy": self.healthy,
            "oil_level_ok": self.oil_level_ok,
            "buchholz_alarm": self.buchholz_alarm,
            "pressure_relief_ok": self.pressure_relief_ok,
            "cooling_type": self.cooling_type,
            "fans_running": self.fans_running,
        }


# === LV Switchboard ===

@dataclass
class LVSwitchboard:
    """Low Voltage Main Switchboard (MSB)."""

    switchboard_id: str
    name: str
    site_id: str
    location: str

    # Ratings
    rated_voltage: float = 400.0
    rated_current_a: float = 4000.0
    fault_rating_ka: float = 50.0

    # Bus configuration
    bus_sections: int = 2            # Split bus typical
    bus_coupler_closed: bool = False

    # Current readings (main bus)
    voltage_l1_n: float = 230.0
    voltage_l2_n: float = 230.0
    voltage_l3_n: float = 230.0
    voltage_l1_l2: float = 400.0
    voltage_l2_l3: float = 400.0
    voltage_l3_l1: float = 400.0
    frequency_hz: float = 50.0

    # Incomer status
    mains_incomer_closed: bool = True
    gen_incomer_closed: bool = False

    # Power readings
    total_power_kw: float = 0.0
    total_power_kva: float = 0.0
    power_factor: float = 0.95
    total_kwh: float = 0.0

    # Health
    healthy: bool = True
    temperature_c: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "switchboard_id": self.switchboard_id,
            "name": self.name,
            "site_id": self.site_id,
            "location": self.location,
            "rated_voltage": self.rated_voltage,
            "rated_current_a": self.rated_current_a,
            "fault_rating_ka": self.fault_rating_ka,
            "bus_sections": self.bus_sections,
            "bus_coupler_closed": self.bus_coupler_closed,
            "voltage_l1_n": self.voltage_l1_n,
            "voltage_l2_n": self.voltage_l2_n,
            "voltage_l3_n": self.voltage_l3_n,
            "voltage_l1_l2": self.voltage_l1_l2,
            "voltage_l2_l3": self.voltage_l2_l3,
            "voltage_l3_l1": self.voltage_l3_l1,
            "frequency_hz": self.frequency_hz,
            "mains_incomer_closed": self.mains_incomer_closed,
            "gen_incomer_closed": self.gen_incomer_closed,
            "total_power_kw": self.total_power_kw,
            "total_power_kva": self.total_power_kva,
            "power_factor": self.power_factor,
            "total_kwh": self.total_kwh,
            "healthy": self.healthy,
            "temperature_c": self.temperature_c,
        }


# === Power Metering ===

@dataclass
class PowerMeter:
    """Power/Energy meter (main incomer, sub-meter, check meter)."""

    meter_id: str
    name: str
    site_id: str
    location: str
    meter_type: str = "main"         # main, sub, check, generator

    # Meter info
    manufacturer: str = "Schneider"  # Schneider ION, Satec, Elster
    model: Optional[str] = None
    serial_number: Optional[str] = None
    ct_ratio: str = "2000/5"
    vt_ratio: Optional[str] = None   # For MV metering

    # Instantaneous readings
    voltage_l1_n: float = 230.0
    voltage_l2_n: float = 230.0
    voltage_l3_n: float = 230.0
    current_l1: float = 0.0
    current_l2: float = 0.0
    current_l3: float = 0.0
    current_n: float = 0.0

    # Power readings
    active_power_kw: float = 0.0
    reactive_power_kvar: float = 0.0
    apparent_power_kva: float = 0.0
    power_factor: float = 1.0
    frequency_hz: float = 50.0

    # Energy totals
    kwh_import: float = 0.0
    kwh_export: float = 0.0
    kvarh_import: float = 0.0
    kvarh_export: float = 0.0

    # Demand
    max_demand_kw: float = 0.0
    max_demand_timestamp: Optional[str] = None

    # Power quality (if supported)
    thd_voltage_pct: Optional[float] = None  # Total harmonic distortion
    thd_current_pct: Optional[float] = None
    voltage_unbalance_pct: Optional[float] = None

    # Tariff (for billing meters)
    tariff_type: Optional[str] = None        # Megaflex, Miniflex, Nightsave
    tou_period: Optional[str] = None         # peak, standard, off-peak

    # Communication
    protocol: str = "modbus"
    ip_address: Optional[str] = None
    last_poll: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meter_id": self.meter_id,
            "name": self.name,
            "site_id": self.site_id,
            "location": self.location,
            "meter_type": self.meter_type,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial_number": self.serial_number,
            "ct_ratio": self.ct_ratio,
            "vt_ratio": self.vt_ratio,
            "voltage_l1_n": self.voltage_l1_n,
            "voltage_l2_n": self.voltage_l2_n,
            "voltage_l3_n": self.voltage_l3_n,
            "current_l1": self.current_l1,
            "current_l2": self.current_l2,
            "current_l3": self.current_l3,
            "current_n": self.current_n,
            "active_power_kw": self.active_power_kw,
            "reactive_power_kvar": self.reactive_power_kvar,
            "apparent_power_kva": self.apparent_power_kva,
            "power_factor": self.power_factor,
            "frequency_hz": self.frequency_hz,
            "kwh_import": self.kwh_import,
            "kwh_export": self.kwh_export,
            "kvarh_import": self.kvarh_import,
            "kvarh_export": self.kvarh_export,
            "max_demand_kw": self.max_demand_kw,
            "max_demand_timestamp": self.max_demand_timestamp,
            "thd_voltage_pct": self.thd_voltage_pct,
            "thd_current_pct": self.thd_current_pct,
            "voltage_unbalance_pct": self.voltage_unbalance_pct,
            "tariff_type": self.tariff_type,
            "tou_period": self.tou_period,
            "protocol": self.protocol,
            "ip_address": self.ip_address,
            "last_poll": self.last_poll,
        }


# === Power Factor Correction ===

@dataclass
class PFCBank:
    """Power Factor Correction capacitor bank."""

    pfc_id: str
    name: str
    site_id: str
    location: str

    # Ratings
    total_kvar: float = 600.0        # Total bank capacity
    steps: int = 12                   # Number of switching steps
    step_size_kvar: float = 50.0     # kVAR per step

    # Current state
    active_steps: int = 0
    active_kvar: float = 0.0
    target_power_factor: float = 0.95
    current_power_factor: float = 0.95

    # Controller
    controller_model: Optional[str] = None  # Epcos, Schneider Varlogic
    auto_mode: bool = True

    # Health
    healthy: bool = True
    capacitor_temps_ok: bool = True
    fuse_status_ok: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pfc_id": self.pfc_id,
            "name": self.name,
            "site_id": self.site_id,
            "location": self.location,
            "total_kvar": self.total_kvar,
            "steps": self.steps,
            "step_size_kvar": self.step_size_kvar,
            "active_steps": self.active_steps,
            "active_kvar": self.active_kvar,
            "target_power_factor": self.target_power_factor,
            "current_power_factor": self.current_power_factor,
            "controller_model": self.controller_model,
            "auto_mode": self.auto_mode,
            "healthy": self.healthy,
            "capacitor_temps_ok": self.capacitor_temps_ok,
            "fuse_status_ok": self.fuse_status_ok,
        }


# === UPS Systems ===

@dataclass
class UPSSystem:
    """Uninterruptible Power Supply system."""

    ups_id: str
    name: str
    site_id: str
    location: str

    # Ratings
    rated_power_kva: float = 200.0
    rated_power_kw: float = 180.0
    topology: str = "online"         # online (double-conversion), line-interactive, offline

    # Input
    input_voltage: float = 400.0
    input_frequency: float = 50.0
    input_healthy: bool = True

    # Output
    output_voltage: float = 400.0
    output_frequency: float = 50.0
    load_kw: float = 0.0
    load_percent: float = 0.0

    # Battery
    battery_voltage: float = 480.0
    battery_current: float = 0.0
    battery_charge_pct: float = 100.0
    battery_runtime_min: float = 30.0
    battery_temp_c: Optional[float] = None
    battery_health_pct: float = 100.0
    battery_test_date: Optional[str] = None
    battery_replace_date: Optional[str] = None  # Recommended replacement

    # Status
    mode: str = "online"             # online, battery, bypass, standby, fault
    on_battery: bool = False
    on_bypass: bool = False
    overload: bool = False

    # Alarms
    alarms: List[str] = field(default_factory=list)

    # Communication
    protocol: str = "snmp"           # snmp, modbus
    ip_address: Optional[str] = None
    last_poll: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ups_id": self.ups_id,
            "name": self.name,
            "site_id": self.site_id,
            "location": self.location,
            "rated_power_kva": self.rated_power_kva,
            "rated_power_kw": self.rated_power_kw,
            "topology": self.topology,
            "input_voltage": self.input_voltage,
            "input_frequency": self.input_frequency,
            "input_healthy": self.input_healthy,
            "output_voltage": self.output_voltage,
            "output_frequency": self.output_frequency,
            "load_kw": self.load_kw,
            "load_percent": self.load_percent,
            "battery_voltage": self.battery_voltage,
            "battery_current": self.battery_current,
            "battery_charge_pct": self.battery_charge_pct,
            "battery_runtime_min": self.battery_runtime_min,
            "battery_temp_c": self.battery_temp_c,
            "battery_health_pct": self.battery_health_pct,
            "battery_test_date": self.battery_test_date,
            "battery_replace_date": self.battery_replace_date,
            "mode": self.mode,
            "on_battery": self.on_battery,
            "on_bypass": self.on_bypass,
            "overload": self.overload,
            "alarms": self.alarms,
            "protocol": self.protocol,
            "ip_address": self.ip_address,
            "last_poll": self.last_poll,
        }


# === Energy Centre Overview ===

@dataclass
class EnergyCentre:
    """Complete energy centre configuration."""

    centre_id: str
    name: str
    site_id: str
    building: str
    location: str

    # Equipment references
    mv_incomer_ids: List[str] = field(default_factory=list)
    transformer_ids: List[str] = field(default_factory=list)
    lv_switchboard_ids: List[str] = field(default_factory=list)
    ats_ids: List[str] = field(default_factory=list)
    generator_group_ids: List[str] = field(default_factory=list)
    pfc_ids: List[str] = field(default_factory=list)
    ups_ids: List[str] = field(default_factory=list)
    meter_ids: List[str] = field(default_factory=list)

    # Overall status
    mains_healthy: bool = True
    on_generator: bool = False
    total_load_kw: float = 0.0
    total_capacity_kw: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "centre_id": self.centre_id,
            "name": self.name,
            "site_id": self.site_id,
            "building": self.building,
            "location": self.location,
            "mv_incomer_ids": self.mv_incomer_ids,
            "transformer_ids": self.transformer_ids,
            "lv_switchboard_ids": self.lv_switchboard_ids,
            "ats_ids": self.ats_ids,
            "generator_group_ids": self.generator_group_ids,
            "pfc_ids": self.pfc_ids,
            "ups_ids": self.ups_ids,
            "meter_ids": self.meter_ids,
            "mains_healthy": self.mains_healthy,
            "on_generator": self.on_generator,
            "total_load_kw": self.total_load_kw,
            "total_capacity_kw": self.total_capacity_kw,
        }
