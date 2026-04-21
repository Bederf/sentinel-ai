"""
Device Control Service
======================
Unified interface for controlling all BMS equipment.
Integrates with ApprovalWorkflow for supervised device control.

Supports:
- HVAC: FCU, VAV, AHU, CHILLER, PUMP, SPLIT
- Lighting: DALI (controllers and luminaires)
- Power: GEN, UPS
- Monitoring: Equipment sensors
"""

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class EquipmentType(StrEnum):
    """Equipment types with control capabilities."""

    # HVAC
    FCU = "FCU"  # Fan Coil Unit
    VAV = "VAV"  # Variable Air Volume
    AHU = "AHU"  # Air Handling Unit
    CHILLER = "CHILLER"
    PUMP = "PUMP"
    SPLIT = "SPLIT"  # Split AC
    CT = "CT"  # Cooling Tower

    # Lighting
    DALI = "DALI"  # DALI controller
    LUM = "LUM"  # Luminaire/fixture

    # Power
    GEN = "GEN"  # Generator
    UPS = "UPS"  # Uninterruptible Power Supply

    # Energy Storage
    BESS = "BESS"  # Battery Energy Storage System
    INV = "INV"  # Inverter

    # Other
    MTR = "MTR"  # Meter


@dataclass
class ControlPoint:
    """Definition of a controllable point on equipment."""

    name: str  # e.g., "cooling_setpoint"
    description: str
    data_type: str  # "float", "int", "bool", "enum"
    min_value: float | None = None
    max_value: float | None = None
    unit: str = ""
    writable: bool = True
    enum_values: list[str] | None = None  # For enum types


@dataclass
class ControlAction:
    """A control action to be executed."""

    equipment_code: str
    equipment_id: str
    control_point: str
    target_value: Any
    reason: str  # Why this control is needed
    estimated_impact: str  # What will happen (e.g., "Zone will cool down")


# Define control points for each equipment type
EQUIPMENT_CONTROL_POINTS = {
    EquipmentType.FCU: [
        ControlPoint(
            name="cooling_setpoint",
            description="Cooling setpoint temperature",
            data_type="float",
            min_value=16.0,
            max_value=28.0,
            unit="°C",
            writable=True,
        ),
        ControlPoint(
            name="heating_setpoint",
            description="Heating setpoint temperature",
            data_type="float",
            min_value=16.0,
            max_value=28.0,
            unit="°C",
            writable=True,
        ),
        ControlPoint(
            name="fan_mode",
            description="Fan operation mode",
            data_type="enum",
            enum_values=["auto", "on", "off"],
            writable=True,
        ),
        ControlPoint(
            name="fan_speed",
            description="Fan speed (0-100%)",
            data_type="int",
            min_value=0,
            max_value=100,
            unit="%",
            writable=True,
        ),
    ],
    EquipmentType.VAV: [
        ControlPoint(
            name="airflow_setpoint",
            description="Supply airflow setpoint",
            data_type="float",
            min_value=0.0,
            max_value=5.0,
            unit="m³/s",
            writable=True,
        ),
        ControlPoint(
            name="damper_position",
            description="Damper opening position",
            data_type="int",
            min_value=0,
            max_value=100,
            unit="%",
            writable=True,
        ),
        ControlPoint(
            name="cooling_setpoint",
            description="Zone cooling setpoint",
            data_type="float",
            min_value=16.0,
            max_value=28.0,
            unit="°C",
            writable=True,
        ),
    ],
    EquipmentType.AHU: [
        ControlPoint(
            name="supply_temp_setpoint",
            description="Supply air temperature setpoint",
            data_type="float",
            min_value=10.0,
            max_value=30.0,
            unit="°C",
            writable=True,
        ),
        ControlPoint(
            name="return_temp_setpoint",
            description="Return air temperature setpoint",
            data_type="float",
            min_value=10.0,
            max_value=30.0,
            unit="°C",
            writable=True,
        ),
        ControlPoint(
            name="fan_mode", description="Fan mode", data_type="enum", enum_values=["auto", "on", "off"], writable=True
        ),
        ControlPoint(
            name="economizer_mode",
            description="Economizer operation",
            data_type="enum",
            enum_values=["enabled", "disabled", "auto"],
            writable=True,
        ),
    ],
    EquipmentType.CHILLER: [
        ControlPoint(
            name="chw_setpoint",
            description="Chilled water setpoint",
            data_type="float",
            min_value=4.0,
            max_value=12.0,
            unit="°C",
            writable=True,
        ),
        ControlPoint(
            name="mode",
            description="Chiller operation mode",
            data_type="enum",
            enum_values=["auto", "cooling_only", "off", "shutdown"],
            writable=True,
        ),
        ControlPoint(
            name="capacity_percent",
            description="Chiller capacity limit",
            data_type="int",
            min_value=0,
            max_value=100,
            unit="%",
            writable=True,
        ),
    ],
    EquipmentType.PUMP: [
        ControlPoint(
            name="flow_setpoint",
            description="Pump flow setpoint",
            data_type="float",
            min_value=0.0,
            max_value=10.0,
            unit="m³/h",
            writable=True,
        ),
        ControlPoint(
            name="speed_percent",
            description="Pump speed percentage",
            data_type="int",
            min_value=0,
            max_value=100,
            unit="%",
            writable=True,
        ),
        ControlPoint(
            name="mode",
            description="Pump operation mode",
            data_type="enum",
            enum_values=["auto", "on", "off"],
            writable=True,
        ),
    ],
    EquipmentType.DALI: [
        ControlPoint(
            name="brightness_level",
            description="Lighting brightness",
            data_type="int",
            min_value=0,
            max_value=100,
            unit="%",
            writable=True,
        ),
        ControlPoint(
            name="scene",
            description="Preset lighting scene",
            data_type="enum",
            enum_values=["off", "working", "conference", "presentation", "relaxed"],
            writable=True,
        ),
        ControlPoint(
            name="color_temp",
            description="Color temperature",
            data_type="int",
            min_value=2700,
            max_value=6500,
            unit="K",
            writable=True,
        ),
    ],
    EquipmentType.LUM: [
        ControlPoint(
            name="brightness_level",
            description="Luminaire brightness",
            data_type="int",
            min_value=0,
            max_value=100,
            unit="%",
            writable=True,
        ),
    ],
    EquipmentType.GEN: [
        ControlPoint(
            name="load_mode",
            description="Generator load mode",
            data_type="enum",
            enum_values=["auto", "standby", "load_shed", "peak_load", "off"],
            writable=True,
        ),
        ControlPoint(
            name="frequency_setpoint",
            description="Output frequency",
            data_type="float",
            min_value=49.0,
            max_value=51.0,
            unit="Hz",
            writable=True,
        ),
        ControlPoint(
            name="voltage_setpoint",
            description="Output voltage",
            data_type="float",
            min_value=400.0,
            max_value=440.0,
            unit="V",
            writable=True,
        ),
    ],
    EquipmentType.UPS: [
        ControlPoint(
            name="output_mode",
            description="UPS output mode",
            data_type="enum",
            enum_values=["auto", "battery", "eco", "bypass"],
            writable=True,
        ),
        ControlPoint(
            name="battery_charge_mode",
            description="Battery charging mode",
            data_type="enum",
            enum_values=["fast", "normal", "trickle", "off"],
            writable=True,
        ),
        ControlPoint(name="load_shed_enable", description="Enable load shedding", data_type="bool", writable=True),
    ],
    EquipmentType.BESS: [
        ControlPoint(
            name="dispatch_command",
            description="AEGIS dispatch command (structured JSON payload)",
            data_type="json",
            writable=True,
        ),
        ControlPoint(
            name="mode",
            description="BESS operating mode",
            data_type="enum",
            enum_values=["peak_shaving", "load_shifting", "grid_export", "backup", "idle"],
            writable=True,
        ),
        ControlPoint(
            name="charge_rate_kw",
            description="Charge rate in kW",
            data_type="float",
            min_value=0.0,
            max_value=100.0,
            unit="kW",
            writable=True,
        ),
        ControlPoint(
            name="discharge_rate_kw",
            description="Discharge rate in kW",
            data_type="float",
            min_value=0.0,
            max_value=100.0,
            unit="kW",
            writable=True,
        ),
        ControlPoint(
            name="soc_target_pct",
            description="Target state of charge",
            data_type="float",
            min_value=10.0,
            max_value=95.0,
            unit="%",
            writable=True,
        ),
    ],
}


class DeviceControlService:
    """Service for device control operations."""

    @staticmethod
    def get_equipment_type(equipment_code: str) -> EquipmentType | None:
        """Extract equipment type from equipment code.

        Format: {site}-{TYPE}-{location}
        Example: S002-FCU-203 → FCU
        """
        if not equipment_code:
            return None

        parts = equipment_code.split("-")
        if len(parts) < 2:
            return None

        type_str = parts[1].upper()

        try:
            return EquipmentType(type_str)
        except ValueError:
            logger.warning(f"Unknown equipment type in code: {equipment_code}")
            return None

    @staticmethod
    def get_control_points(equipment_code: str) -> dict[str, ControlPoint]:
        """Get all controllable points for equipment."""
        eq_type = DeviceControlService.get_equipment_type(equipment_code)
        if not eq_type:
            return {}

        points = EQUIPMENT_CONTROL_POINTS.get(eq_type, [])
        return {p.name: p for p in points}

    @staticmethod
    def is_controllable(equipment_code: str) -> bool:
        """Check if equipment type is controllable."""
        eq_type = DeviceControlService.get_equipment_type(equipment_code)
        return eq_type in EQUIPMENT_CONTROL_POINTS

    @staticmethod
    def validate_control_value(equipment_code: str, point_name: str, value: Any) -> dict[str, Any]:
        """Validate a control value against point constraints.

        Returns: {"valid": bool, "errors": [str], "warning": Optional[str]}
        """
        points = DeviceControlService.get_control_points(equipment_code)

        if point_name not in points:
            return {"valid": False, "errors": [f"Unknown control point: {point_name}"], "warning": None}

        point = points[point_name]
        errors = []
        warning = None

        # Type checking
        if point.data_type == "float":
            try:
                value = float(value)
            except (ValueError, TypeError):
                errors.append(f"Expected float, got {type(value).__name__}")
        elif point.data_type == "int":
            try:
                value = int(value)
            except (ValueError, TypeError):
                errors.append(f"Expected int, got {type(value).__name__}")
        elif point.data_type == "bool":
            if not isinstance(value, bool):
                errors.append(f"Expected bool, got {type(value).__name__}")
        elif point.data_type == "enum" and value not in point.enum_values:
            errors.append(f"Invalid value. Allowed: {point.enum_values}")

        # Range checking
        if not errors and point.min_value is not None and value < point.min_value:
            errors.append(f"Value {value} below minimum {point.min_value}")
        if not errors and point.max_value is not None and value > point.max_value:
            errors.append(f"Value {value} above maximum {point.max_value}")

        # Warnings (not errors, but noteworthy)
        if not errors and point.data_type in ["float", "int"]:
            if point.min_value and value == point.min_value:
                warning = f"Value at minimum threshold ({point.min_value})"
            elif point.max_value and value == point.max_value:
                warning = f"Value at maximum threshold ({point.max_value})"

        return {"valid": len(errors) == 0, "errors": errors, "warning": warning}


# Singleton instance
_service: DeviceControlService | None = None


def get_device_control_service() -> DeviceControlService:
    """Get singleton device control service."""
    global _service
    if _service is None:
        _service = DeviceControlService()
    return _service
