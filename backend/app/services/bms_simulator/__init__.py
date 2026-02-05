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
    VendorType,
    EquipmentType,
    AlarmSeverity,
    SimulationConfig,
    PointDefinition,
    DiffuserConfig,
    POINT_VALUE_RANGES,
    EQUIPMENT_ALARM_PROFILES,
    DEGRADATION_PATTERNS,
    DIURNAL_PATTERNS,
)
from .simulator import BMSSimulator

__all__ = [
    "BMSSimulator",
    "VendorType",
    "EquipmentType",
    "AlarmSeverity",
    "SimulationConfig",
    "PointDefinition",
    "DiffuserConfig",
    "POINT_VALUE_RANGES",
    "EQUIPMENT_ALARM_PROFILES",
    "DEGRADATION_PATTERNS",
    "DIURNAL_PATTERNS",
]
