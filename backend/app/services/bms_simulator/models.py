"""
BMS Simulator Models

Configuration models and constants for the mock BMS simulator.
Includes support for Siemens Desigo, Niagara, and Rickard DALI equipment.
"""

from datetime import date, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from pydantic import BaseModel, Field


class VendorType(str, Enum):
    """Supported BMS vendor formats."""

    SIEMENS_DESIGO = "siemens_desigo"
    NIAGARA = "niagara"
    RICKARD = "rickard"  # Rickard DALI diffusers with MLM controllers


class EquipmentType(str, Enum):
    """Equipment type categories."""

    CHILLER = "chiller"
    AHU = "ahu"
    FCU = "fcu"
    VAV = "vav"
    DIFFUSER = "diffuser"
    ZONE_CONTROLLER = "zone_controller"
    FIRE_SAFETY = "fire_safety"
    SECURITY = "security"
    DAMPER = "damper"
    PRESSURE_SENSOR = "pressure_sensor"
    CAMERA = "camera"
    ACCESS_CONTROL = "access_control"
    DALI_CONTROLLER = "dali_controller"
    MLM_CONTROLLER = "mlm_controller"
    MCU2_GATEWAY = "mcu2_gateway"
    # Hospital-specific equipment types
    THEATRE_AHU = "theatre_ahu"
    COLD_ROOM = "cold_room"
    GENERATOR = "generator"
    MEDICAL_GAS = "medical_gas"
    BOILER = "boiler"
    LIFT = "lift"
    COOLING_TOWER = "cooling_tower"
    UPS = "ups"
    PUMP = "pump"


class AlarmSeverity(str, Enum):
    """Alarm severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SimulationConfig(BaseModel):
    """Configuration for BMS simulation."""

    site_id: str = Field(default="site-002", description="Site ID to read equipment from")
    vendor: VendorType = Field(default=VendorType.SIEMENS_DESIGO, description="Target vendor format")
    seed: int = Field(default=42, description="Random seed for reproducibility")
    start_date: date = Field(default_factory=lambda: date.today() - timedelta(days=30))
    days: int = Field(default=30, description="Number of days of trend data to generate")
    interval_minutes: int = Field(default=15, description="Trend data interval in minutes")
    include_degradation: bool = Field(default=True, description="Include equipment degradation patterns")
    degradation_equipment: List[str] = Field(
        default_factory=lambda: ["S002-CHILLER-B1-001"], description="Equipment IDs to apply degradation to"
    )
    include_diffusers: bool = Field(default=True, description="Generate Rickard diffusers linked to VAVs")

    class Config:
        use_enum_values = True


class PointDefinition(BaseModel):
    """Point definition with value ranges and metadata."""

    name: str
    point_type: str  # analog_input, analog_value, binary_input, binary_value, multistate_value
    description: str
    unit: str = ""
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    default_value: Any = None
    writable: bool = False
    metadata: Optional[Dict[str, Any]] = None


class DiffuserConfig(BaseModel):
    """Configuration for a Rickard VAV diffuser."""

    equipment_id: str
    name: str
    connected_vav: str
    floor: str
    zone: str
    manufacturer: str = "Rickard"
    model: str = "VVD-Series"
    controller_type: str = "MLM"  # Master/slave MLM controller
    gateway: str = "MCU2"  # MCU2 gateway for BACnet output


# Value ranges by point type (extrapolated from mock_devices.json point definitions)
POINT_VALUE_RANGES: Dict[str, Tuple[float, float]] = {
    # Temperature points
    "supply_air_temp": (12.0, 18.0),
    "return_air_temp": (22.0, 26.0),
    "room_temp": (20.0, 25.0),
    "zone_temp": (20.0, 25.0),
    "chw_supply_temp": (5.0, 9.0),
    "chw_return_temp": (10.0, 14.0),
    "discharge_air_temp": (12.0, 18.0),
    # Flow and pressure points
    "airflow_actual": (100, 500),
    "airflow_setpoint": (150, 400),
    "airflow_cfm": (50, 400),  # Diffuser airflow in CFM
    "filter_pressure": (50, 300),
    "system_pressure": (2.0, 6.0),
    # Position points (0-100%)
    "damper_position": (0, 100),
    "valve_position": (0, 100),
    "heating_valve": (0, 100),
    "fan_speed": (0, 100),
    # Electrical points
    "compressor_amps": (50, 200),
    "reader_battery": (80, 100),
    "battery_voltage": (11.5, 14.5),
    # Lighting/DALI points
    "circuit1_level": (0, 100),
    "circuit2_level": (0, 100),
    "light_level": (100, 800),  # lux
    # Environmental points
    "co2_level": (400, 1200),  # ppm
    # Setpoint ranges
    "room_temp_setpoint": (20.0, 24.0),
    "cooling_setpoint": (22.0, 25.0),
    "chw_supply_temp_setpoint": (6.0, 9.0),
    # Hospital-specific points
    # Theatre AHU
    "supply_humidity": (40.0, 60.0),
    "return_humidity": (45.0, 65.0),
    "hepa_dp": (150, 450),  # HEPA filter differential pressure (Pa)
    "prefilter_dp": (50, 200),  # Prefilter differential pressure (Pa)
    "room_pressure": (5, 25),  # Positive pressure (Pa)
    "air_changes_per_hour": (15, 25),  # ACH for theatres
    # Cold room
    "cabinet_temp": (2.0, 8.0),  # Vaccine storage range
    "evaporator_temp": (-5.0, 5.0),
    "compressor_run_hours": (0, 100000),
    # Generator
    "fuel_level": (20, 100),
    "coolant_temp": (30, 95),
    "oil_pressure": (2.0, 6.0),
    "load_percent": (0, 100),
    "run_hours": (0, 50000),
    # Medical gas
    "o2_pressure": (8.0, 12.0),  # bar
    "n2o_pressure": (6.0, 10.0),  # bar
    "medical_air_pressure": (5.0, 8.0),  # bar
    # UPS
    "battery_charge": (80, 100),
    "battery_runtime": (10, 60),  # minutes
    # Cooling tower
    "approach_temp": (2.0, 8.0),  # degC
    "wet_bulb_temp": (18.0, 28.0),  # Durban wet bulb range
    "cw_supply_temp": (25.0, 35.0),
    "cw_return_temp": (30.0, 40.0),
    # Boiler
    "hw_supply_temp": (60.0, 80.0),
    "hw_return_temp": (45.0, 65.0),
    "flue_temp": (80.0, 180.0),
    # Pump
    "motor_amps": (10, 40),
    "dp_bar": (1.5, 4.5),
    # COP for chillers
    "cop": (3.5, 5.5),
}


# BACnet object type mapping from point_type
BACNET_OBJECT_TYPE_MAP: Dict[str, str] = {
    "analog_input": "analogInput",
    "analog_value": "analogValue",
    "analog_output": "analogOutput",
    "binary_input": "binaryInput",
    "binary_value": "binaryValue",
    "binary_output": "binaryOutput",
    "multistate_input": "multistateInput",
    "multistate_value": "multistateValue",
    "multistate_output": "multistateOutput",
}


# Equipment alarm profiles - typical alarms by equipment type
EQUIPMENT_ALARM_PROFILES: Dict[str, List[Dict[str, Any]]] = {
    "chiller": [
        {
            "code": "VIB_WARN",
            "severity": "warning",
            "description": "Compressor vibration warning",
            "trigger_point": "compressor_amps",
            "threshold_pct": 110,
        },
        {
            "code": "VIB_HIGH",
            "severity": "warning",
            "description": "Compressor vibration high",
            "trigger_point": "compressor_amps",
            "threshold_pct": 120,
        },
        {
            "code": "VIB_CRIT",
            "severity": "critical",
            "description": "Compressor vibration critical",
            "trigger_point": "compressor_amps",
            "threshold_pct": 130,
        },
        {
            "code": "TEMP_HI",
            "severity": "warning",
            "description": "Chilled water temperature high",
            "trigger_point": "chw_supply_temp",
            "threshold_pct": 115,
        },
        {
            "code": "PRESS_HI",
            "severity": "warning",
            "description": "Condenser pressure high",
            "trigger_point": None,
            "threshold_pct": 120,
        },
        {
            "code": "MOTOR_OVL",
            "severity": "critical",
            "description": "Motor overload",
            "trigger_point": "compressor_amps",
            "threshold_pct": 140,
        },
    ],
    "ahu": [
        {
            "code": "FILTER_DP",
            "severity": "warning",
            "description": "Filter differential pressure high",
            "trigger_point": "filter_pressure",
            "threshold_pct": 120,
        },
        {
            "code": "FAN_FAIL",
            "severity": "critical",
            "description": "Supply fan failure",
            "trigger_point": "fan_speed",
            "threshold_pct": 0,
        },
        {
            "code": "TEMP_HI",
            "severity": "warning",
            "description": "Supply air temperature high",
            "trigger_point": "supply_air_temp",
            "threshold_pct": 120,
        },
        {
            "code": "VIB_WARN",
            "severity": "warning",
            "description": "Fan vibration warning",
            "trigger_point": None,
            "threshold_pct": 110,
        },
    ],
    "fcu": [
        {
            "code": "VALVE_STUCK",
            "severity": "warning",
            "description": "Valve stuck or unresponsive",
            "trigger_point": "valve_position",
            "threshold_pct": None,
        },
        {
            "code": "TEMP_HI",
            "severity": "warning",
            "description": "Room temperature high",
            "trigger_point": "room_temp",
            "threshold_pct": 110,
        },
        {
            "code": "FAN_FAIL",
            "severity": "critical",
            "description": "Fan failure",
            "trigger_point": "fan_speed",
            "threshold_pct": 0,
        },
    ],
    "vav": [
        {
            "code": "DAMPER_FAIL",
            "severity": "warning",
            "description": "Damper actuator failure",
            "trigger_point": "damper_position",
            "threshold_pct": None,
        },
        {
            "code": "FLOW_LO",
            "severity": "warning",
            "description": "Airflow below minimum",
            "trigger_point": "airflow_actual",
            "threshold_pct": 50,
        },
        {
            "code": "FLOW_HI",
            "severity": "warning",
            "description": "Airflow above maximum",
            "trigger_point": "airflow_actual",
            "threshold_pct": 110,
        },
    ],
    "diffuser": [
        {
            "code": "DAMPER_FAIL",
            "severity": "warning",
            "description": "Diffuser damper failure",
            "trigger_point": "damper_position",
            "threshold_pct": None,
        },
        {
            "code": "FLOW_LO",
            "severity": "warning",
            "description": "Diffuser airflow low",
            "trigger_point": "airflow_cfm",
            "threshold_pct": 50,
        },
        {
            "code": "CO2_HI",
            "severity": "warning",
            "description": "CO2 level high",
            "trigger_point": "co2_level",
            "threshold_pct": 120,
        },
        {
            "code": "COMM_FAIL",
            "severity": "warning",
            "description": "MLM controller communication failure",
            "trigger_point": None,
            "threshold_pct": None,
        },
    ],
    "fire_safety": [
        {
            "code": "DETECTOR_FAULT",
            "severity": "critical",
            "description": "Smoke detector fault",
            "trigger_point": None,
            "threshold_pct": None,
        },
        {
            "code": "BATTERY_LOW",
            "severity": "warning",
            "description": "Panel battery low",
            "trigger_point": "battery_voltage",
            "threshold_pct": 85,
        },
        {
            "code": "PRESS_LO",
            "severity": "warning",
            "description": "System pressure low",
            "trigger_point": "system_pressure",
            "threshold_pct": 70,
        },
    ],
    "security": [
        {
            "code": "TAMPER",
            "severity": "warning",
            "description": "Tamper alarm",
            "trigger_point": "tamper_alarm",
            "threshold_pct": None,
        },
        {
            "code": "COMM_FAIL",
            "severity": "warning",
            "description": "Communication failure",
            "trigger_point": None,
            "threshold_pct": None,
        },
        {
            "code": "BATTERY_LOW",
            "severity": "warning",
            "description": "Reader battery low",
            "trigger_point": "reader_battery",
            "threshold_pct": 20,
        },
    ],
    # Hospital-specific alarm profiles
    "theatre_ahu": [
        {
            "code": "HEPA_DP_HI",
            "severity": "warning",
            "description": "HEPA filter DP high - schedule replacement",
            "trigger_point": "hepa_dp",
            "threshold_pct": 130,
        },
        {
            "code": "HEPA_DP_CRIT",
            "severity": "critical",
            "description": "HEPA filter DP critical - replace immediately",
            "trigger_point": "hepa_dp",
            "threshold_pct": 150,
        },
        {
            "code": "HUMIDITY_LO",
            "severity": "warning",
            "description": "Theatre humidity low",
            "trigger_point": "supply_humidity",
            "threshold_pct": 80,
        },
        {
            "code": "HUMIDITY_HI",
            "severity": "warning",
            "description": "Theatre humidity high",
            "trigger_point": "supply_humidity",
            "threshold_pct": 120,
        },
        {
            "code": "PRESSURE_LO",
            "severity": "critical",
            "description": "Theatre positive pressure lost",
            "trigger_point": "room_pressure",
            "threshold_pct": 50,
        },
        {
            "code": "ACH_LO",
            "severity": "warning",
            "description": "Air changes below minimum",
            "trigger_point": "air_changes_per_hour",
            "threshold_pct": 80,
        },
        {
            "code": "VIB_WARN",
            "severity": "warning",
            "description": "Fan vibration warning",
            "trigger_point": "fan_vibration",
            "threshold_pct": 150,
        },
        {
            "code": "VIB_CRIT",
            "severity": "critical",
            "description": "Fan vibration critical",
            "trigger_point": "fan_vibration",
            "threshold_pct": 200,
        },
    ],
    "cold_room": [
        {
            "code": "TEMP_HI",
            "severity": "warning",
            "description": "Cold room temperature high",
            "trigger_point": "cabinet_temp",
            "threshold_pct": 120,
        },
        {
            "code": "TEMP_CRIT",
            "severity": "critical",
            "description": "Cold room temperature critical - vaccine storage compromised",
            "trigger_point": "cabinet_temp",
            "threshold_pct": 140,
        },
        {
            "code": "DOOR_OPEN",
            "severity": "warning",
            "description": "Cold room door open too long",
            "trigger_point": "door_status",
            "threshold_pct": None,
        },
        {
            "code": "COMPRESSOR_FAIL",
            "severity": "critical",
            "description": "Compressor failure",
            "trigger_point": "compressor_status",
            "threshold_pct": None,
        },
        {
            "code": "DEFROST_FAIL",
            "severity": "warning",
            "description": "Defrost cycle failure",
            "trigger_point": "defrost_status",
            "threshold_pct": None,
        },
    ],
    "generator": [
        {
            "code": "FUEL_LO",
            "severity": "warning",
            "description": "Fuel level low",
            "trigger_point": "fuel_level",
            "threshold_pct": 30,
        },
        {
            "code": "FUEL_CRIT",
            "severity": "critical",
            "description": "Fuel level critical",
            "trigger_point": "fuel_level",
            "threshold_pct": 15,
        },
        {
            "code": "BATTERY_LO",
            "severity": "warning",
            "description": "Start battery voltage low",
            "trigger_point": "battery_voltage",
            "threshold_pct": 90,
        },
        {
            "code": "COOLANT_HI",
            "severity": "warning",
            "description": "Coolant temperature high",
            "trigger_point": "coolant_temp",
            "threshold_pct": 110,
        },
        {
            "code": "OIL_LO",
            "severity": "critical",
            "description": "Oil pressure low",
            "trigger_point": "oil_pressure",
            "threshold_pct": 60,
        },
        {
            "code": "OVERLOAD",
            "severity": "critical",
            "description": "Generator overload",
            "trigger_point": "load_percent",
            "threshold_pct": 105,
        },
    ],
    "medical_gas": [
        {
            "code": "O2_LO",
            "severity": "warning",
            "description": "O2 supply pressure low",
            "trigger_point": "o2_pressure",
            "threshold_pct": 80,
        },
        {
            "code": "O2_CRIT",
            "severity": "critical",
            "description": "O2 supply pressure critical",
            "trigger_point": "o2_pressure",
            "threshold_pct": 60,
        },
        {
            "code": "N2O_LO",
            "severity": "warning",
            "description": "N2O supply pressure low",
            "trigger_point": "n2o_pressure",
            "threshold_pct": 80,
        },
        {
            "code": "AIR_LO",
            "severity": "warning",
            "description": "Medical air pressure low",
            "trigger_point": "medical_air_pressure",
            "threshold_pct": 80,
        },
        {
            "code": "MANIFOLD_SWITCH",
            "severity": "info",
            "description": "Manifold switched to reserve bank",
            "trigger_point": None,
            "threshold_pct": None,
        },
    ],
    "ups": [
        {
            "code": "BATTERY_LO",
            "severity": "warning",
            "description": "UPS battery charge low",
            "trigger_point": "battery_charge",
            "threshold_pct": 50,
        },
        {
            "code": "RUNTIME_LO",
            "severity": "warning",
            "description": "UPS runtime low",
            "trigger_point": "battery_runtime",
            "threshold_pct": 50,
        },
        {
            "code": "RUNTIME_CRIT",
            "severity": "critical",
            "description": "UPS runtime critical",
            "trigger_point": "battery_runtime",
            "threshold_pct": 25,
        },
        {
            "code": "OVERLOAD",
            "severity": "warning",
            "description": "UPS load high",
            "trigger_point": "load_percent",
            "threshold_pct": 90,
        },
        {
            "code": "ON_BATTERY",
            "severity": "warning",
            "description": "UPS running on battery",
            "trigger_point": None,
            "threshold_pct": None,
        },
        {
            "code": "BATTERY_TEMP",
            "severity": "warning",
            "description": "Battery temperature high",
            "trigger_point": "battery_temp",
            "threshold_pct": 120,
        },
    ],
    "cooling_tower": [
        {
            "code": "APPROACH_HI",
            "severity": "warning",
            "description": "Approach temperature high - reduced efficiency",
            "trigger_point": "approach_temp",
            "threshold_pct": 150,
        },
        {
            "code": "BASIN_LO",
            "severity": "warning",
            "description": "Basin water level low",
            "trigger_point": "basin_level",
            "threshold_pct": 50,
        },
        {
            "code": "FAN_FAIL",
            "severity": "critical",
            "description": "Cooling tower fan failure",
            "trigger_point": "fan_status",
            "threshold_pct": None,
        },
    ],
    "boiler": [
        {
            "code": "FLUE_HI",
            "severity": "warning",
            "description": "Flue temperature high",
            "trigger_point": "flue_temp",
            "threshold_pct": 120,
        },
        {
            "code": "FLAME_FAIL",
            "severity": "critical",
            "description": "Burner flame failure",
            "trigger_point": None,
            "threshold_pct": None,
        },
        {
            "code": "GAS_LO",
            "severity": "warning",
            "description": "Gas pressure low",
            "trigger_point": "gas_pressure",
            "threshold_pct": 80,
        },
    ],
    "pump": [
        {
            "code": "VFD_FAULT",
            "severity": "warning",
            "description": "VFD fault detected",
            "trigger_point": "vfd_fault",
            "threshold_pct": None,
        },
        {
            "code": "MOTOR_HI",
            "severity": "warning",
            "description": "Motor current high",
            "trigger_point": "motor_amps",
            "threshold_pct": 115,
        },
        {
            "code": "DP_LO",
            "severity": "warning",
            "description": "Differential pressure low",
            "trigger_point": "dp_bar",
            "threshold_pct": 70,
        },
    ],
}


# Degradation patterns for specific equipment types
DEGRADATION_PATTERNS: Dict[str, Dict[str, Any]] = {
    "chiller": {
        "points": ["compressor_amps", "chw_supply_temp"],
        "rate_per_day": 0.002,  # 0.2% increase per day
        "max_increase": 0.35,  # Maximum 35% increase before failure
        "alarm_sequence": ["VIB_WARN", "VIB_HIGH", "VIB_CRIT"],
    },
    "ahu": {
        "points": ["filter_pressure"],
        "rate_per_day": 0.005,  # 0.5% increase per day (filter clogging)
        "max_increase": 0.50,  # 50% increase before filter change
        "alarm_sequence": ["FILTER_DP"],
    },
    "fcu": {
        "points": ["valve_position"],
        "rate_per_day": 0.001,  # Slow degradation
        "max_increase": 0.20,
        "alarm_sequence": ["VALVE_STUCK"],
    },
    # Hospital-specific degradation patterns
    "chiller_cop_decline": {
        "points": ["cop", "condenser_pressure"],
        "rate_per_day": 0.0017,  # COP declining 0.05/month (~0.0017/day)
        "max_increase": 0.25,  # 25% efficiency loss before major service
        "pattern_type": "exponential",
        "alarm_sequence": ["TEMP_HI", "PRESS_HI"],
        "description": "Gradual COP decline with condenser pressure rise",
    },
    "cooling_tower_approach": {
        "points": ["approach_temp"],
        "rate_per_day": 0.0,  # Stepped, not daily
        "max_increase": 0.80,  # 80% increase (4C to 7.2C)
        "pattern_type": "stepped",
        "step_interval_days": 90,  # Step change every 3 months
        "alarm_sequence": ["APPROACH_HI"],
        "description": "Approach temp step changes from fill degradation",
    },
    "theatre_ahu_vibration": {
        "points": ["fan_vibration"],
        "rate_per_day": 0.0067,  # +0.2mm/s per month (~0.0067/day)
        "max_increase": 0.80,  # 80% increase before bearing failure
        "pattern_type": "linear",
        "alarm_sequence": ["VIB_WARN", "VIB_CRIT"],
        "description": "Linear fan vibration increase from bearing wear",
    },
    "ward_ahu_co2_spike": {
        "points": ["co2_level"],
        "rate_per_day": 0.0,
        "max_increase": 0.60,  # 60% above normal
        "pattern_type": "diurnal_spike",
        "spike_hours": [10, 14],  # 10:00 and 14:00 visiting hours
        "spike_magnitude": 1.5,  # 50% spike
        "alarm_sequence": ["CO2_HI"],
        "description": "CO2 spikes during visiting hours >1000ppm",
    },
    "pump_vfd_intermittent": {
        "points": ["vfd_fault"],
        "rate_per_day": 0.0,
        "max_increase": 0.0,
        "pattern_type": "intermittent",
        "fault_probability": 0.015,  # 2-3 faults per week
        "fault_duration_minutes": 5,
        "alarm_sequence": ["VFD_FAULT"],
        "description": "Random VFD F1 faults 2-3x/week",
    },
    "cold_room_seasonal": {
        "points": ["compressor_run_hours"],
        "rate_per_day": 0.0,
        "max_increase": 0.50,  # 50% more runtime in summer
        "pattern_type": "seasonal",
        "summer_factor": 1.5,  # 18hr/day summer
        "winter_factor": 1.0,  # 12hr/day winter
        "alarm_sequence": ["TEMP_HI"],
        "description": "Seasonal compressor runtime variation",
    },
    "ups_battery_decline": {
        "points": ["battery_runtime"],
        "rate_per_day": 0.0005,  # -0.5 min/month (~0.015/month)
        "max_increase": -0.40,  # 40% reduction (negative = decline)
        "pattern_type": "linear",
        "direction": "decreasing",
        "alarm_sequence": ["RUNTIME_LO", "RUNTIME_CRIT"],
        "description": "Linear battery runtime decline with age",
    },
    "generator_battery_decline": {
        "points": ["battery_voltage"],
        "rate_per_day": 0.0,
        "max_increase": -0.15,  # 15% voltage drop
        "pattern_type": "stepped",
        "step_interval_days": 30,  # Drop after monthly tests
        "alarm_sequence": ["BATTERY_LO"],
        "description": "Battery voltage drops after monthly load tests",
    },
    "theatre_hepa_life": {
        "points": ["hepa_dp"],
        "rate_per_day": 0.003,  # Gradual pressure increase
        "max_increase": 0.60,  # 60% before replacement
        "pattern_type": "linear",
        "alarm_sequence": ["HEPA_DP_HI", "HEPA_DP_CRIT"],
        "description": "HEPA filter loading over 12-18 month lifecycle",
    },
}


# Diurnal pattern parameters
DIURNAL_PATTERNS: Dict[str, Dict[str, Any]] = {
    "temperature": {
        "peak_hour": 14,  # 2 PM peak
        "amplitude": 0.15,  # 15% variation
        "phase_shift": 0,
    },
    "load": {
        "peak_hour": 11,  # 11 AM peak (occupancy driven)
        "amplitude": 0.30,  # 30% variation
        "phase_shift": 0,
    },
    "occupancy": {
        "work_start": 8,
        "work_end": 18,
        "peak_hour": 10,
        "weekend_factor": 0.3,  # 30% activity on weekends
    },
}


# Site code mappings for vendor formatting
SITE_CODE_MAP: Dict[str, str] = {
    "site-001": "GWC",  # Gateway Centre
    "site-002": "STC",  # Sandton City
    "site-003": "RSB",  # Rosebank
    "site-004": "UMH",  # uMhlanga Private Hospital
    "site-005": "GWT",  # Gateway Theatre
    "site-006": "MCS",  # Mediclinic Sandton
}


# Floor code mappings
FLOOR_CODE_MAP: Dict[str, str] = {
    "B2": "B2",
    "B1": "B1",
    "G": "G",
    "L0": "L0",
    "L1": "L1",
    "L2": "L2",
    "L3": "L3",
    "L4": "L4",
    "L5": "L5",
    "L6": "L6",
    "L7": "L7",
    "L8": "L8",
    "L9": "L9",
    "R": "RF",
}

# Hospital site diffuser configuration (for site-004 uMhlanga Private Hospital)
HOSPITAL_DIFFUSER_CONFIG: Dict[str, Dict[str, Any]] = {
    "site-004": {
        "total_diffusers": 30,
        "gateways": {
            "UMH-MCU2-L2-001": {
                "floor": "L2",
                "zone": "Admin",
                "diffuser_count": 10,
                "zone_type": "office",
            },
            "UMH-MCU2-L5-001": {
                "floor": "L5",
                "zone": "Maternity",
                "diffuser_count": 10,
                "zone_type": "ward",
            },
            "UMH-MCU2-L8-001": {
                "floor": "L8",
                "zone": "Private Suites",
                "diffuser_count": 10,
                "zone_type": "patient_room",
            },
        },
    },
}


# Rickard diffuser configuration
RICKARD_DIFFUSER_TEMPLATE = {
    "device_type": "hvac",
    "protocol": "bacnet",
    "hvac_type": "diffuser",
    "points": {
        "airflow_cfm": {
            "name": "airflow_cfm",
            "point_type": "analog_input",
            "description": "Diffuser airflow rate",
            "unit": "CFM",
            "min_value": 50,
            "max_value": 400,
            "default_value": 200,
            "writable": False,
        },
        "damper_position": {
            "name": "damper_position",
            "point_type": "analog_value",
            "description": "Diffuser damper position",
            "unit": "%",
            "min_value": 0,
            "max_value": 100,
            "default_value": 50,
            "writable": True,
        },
        "room_temp": {
            "name": "room_temp",
            "point_type": "analog_input",
            "description": "Zone temperature",
            "unit": "°C",
            "min_value": 16,
            "max_value": 32,
            "default_value": 22.5,
            "writable": False,
        },
        "occupancy": {
            "name": "occupancy",
            "point_type": "binary_input",
            "description": "Zone occupancy status",
            "unit": "",
            "default_value": True,
            "writable": False,
        },
        "co2_level": {
            "name": "co2_level",
            "point_type": "analog_input",
            "description": "Zone CO2 level",
            "unit": "ppm",
            "min_value": 400,
            "max_value": 2000,
            "default_value": 650,
            "writable": False,
        },
    },
    "equipment": {
        "manufacturer": "Rickard",
        "model": "VVD-Series",
        "controller_type": "MLM",
        "gateway": "MCU2",
    },
}
