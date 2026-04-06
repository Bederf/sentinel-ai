"""
BMS Simulator Package

Mock BMS system that extrapolates from existing site-002 equipment to generate
realistic data (point lists, trends, alarms) for ingestion through the SIMBIOT pipeline.

Supported vendors:
- Siemens Desigo CC
- Niagara (Tridium)
- Rickard DALI (MLM controllers, MCU2 gateways)
"""

from .models import (
    DEGRADATION_PATTERNS,
    DIURNAL_PATTERNS,
    EQUIPMENT_ALARM_PROFILES,
    POINT_VALUE_RANGES,
    AlarmSeverity,
    DiffuserConfig,
    EquipmentType,
    PointDefinition,
    SimulationConfig,
    VendorType,
)
from .simulator import BMSSimulator

__all__ = [
    "DEGRADATION_PATTERNS",
    "DIURNAL_PATTERNS",
    "EQUIPMENT_ALARM_PROFILES",
    "POINT_VALUE_RANGES",
    "AlarmSeverity",
    "BMSSimulator",
    "DiffuserConfig",
    "EquipmentType",
    "PointDefinition",
    "SimulationConfig",
    "VendorType",
]
