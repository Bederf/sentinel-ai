"""
SENTINEL Auto-Dashboard Generator — Core engine.

Classifies equipment from BMS discovery, generates tailored dashboard cards,
monitoring rules, health scoring weights, module suggestions, and AI chat
context. All template-driven — no hardcoded equipment.

Phase 141-01: Core service.
"""

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("sentinel.dashboard_generator")


# =============================================================================
# Equipment Classification
# =============================================================================


class EquipmentClass(str, Enum):
    """Equipment categories for dashboard generation."""

    CHILLER = "chiller"
    AHU = "ahu"
    FCU = "fcu"
    VAV = "vav"
    BOILER = "boiler"
    COOLING_TOWER = "cooling_tower"
    PUMP = "pump"
    GENERATOR = "generator"
    UPS = "ups"
    TRANSFORMER = "transformer"
    ATS = "ats"
    SOLAR_INVERTER = "solar_inverter"
    BESS = "bess"
    SOLAR_PANEL = "solar_panel"
    METER_ENERGY = "meter_energy"
    METER_WATER = "meter_water"
    METER_GAS = "meter_gas"
    LIGHTING = "lighting"
    PIR = "pir"
    ACCESS_POINT = "access_point"
    CCTV = "cctv"
    FIRE_PANEL = "fire_panel"
    FIRE_DETECTOR = "fire_detector"
    ELEVATOR = "elevator"
    UNKNOWN = "unknown"


# Maps equipment ID prefixes to classes.
# SENTINEL naming: {SITE}-{TYPE}-{LOCATION}-{NUM}
# Sorted longest-first so MTR-R-SOLAR matches before MTR.
EQUIPMENT_TYPE_MAP: List[tuple] = sorted(
    [
        # HVAC
        ("AHU", EquipmentClass.AHU),
        ("FCU", EquipmentClass.FCU),
        ("VAV", EquipmentClass.VAV),
        ("CHILLER", EquipmentClass.CHILLER),
        ("CH", EquipmentClass.CHILLER),
        ("BOILER", EquipmentClass.BOILER),
        ("BLR", EquipmentClass.BOILER),
        ("CT", EquipmentClass.COOLING_TOWER),
        ("CWP", EquipmentClass.PUMP),
        ("CHWP", EquipmentClass.PUMP),
        ("PUMP", EquipmentClass.PUMP),
        # Electrical
        ("GEN", EquipmentClass.GENERATOR),
        ("UPS", EquipmentClass.UPS),
        ("XFMR", EquipmentClass.TRANSFORMER),
        ("TRF", EquipmentClass.TRANSFORMER),
        ("ATS", EquipmentClass.ATS),
        # Solar & BESS
        ("INV", EquipmentClass.SOLAR_INVERTER),
        ("BESS", EquipmentClass.BESS),
        ("BAT", EquipmentClass.BESS),
        ("PV", EquipmentClass.SOLAR_PANEL),
        # Meters — longest first
        ("MTR-R-SOLAR", EquipmentClass.METER_ENERGY),
        ("MTR-E", EquipmentClass.METER_ENERGY),
        ("MTR-W", EquipmentClass.METER_WATER),
        ("MTR-G", EquipmentClass.METER_GAS),
        # Lighting & Occupancy
        ("LTG", EquipmentClass.LIGHTING),
        ("DALI", EquipmentClass.LIGHTING),
        ("PIR", EquipmentClass.PIR),
        ("OCC", EquipmentClass.PIR),
        # Security
        ("ACC", EquipmentClass.ACCESS_POINT),
        ("DOOR", EquipmentClass.ACCESS_POINT),
        ("CAM", EquipmentClass.CCTV),
        ("CCTV", EquipmentClass.CCTV),
        # Fire
        ("FIRE", EquipmentClass.FIRE_PANEL),
        ("SMOKE", EquipmentClass.FIRE_DETECTOR),
        # Elevators
        ("LIFT", EquipmentClass.ELEVATOR),
        ("ELV", EquipmentClass.ELEVATOR),
    ],
    key=lambda x: len(x[0]),
    reverse=True,
)


def classify_equipment(equipment_id: str, equipment_type: Optional[str] = None) -> EquipmentClass:
    """Classify equipment from ID or type string.

    Tries explicit type field first, then extracts type segment from the
    SENTINEL equipment ID format: {SITE}-{TYPE}-{LOCATION}-{NUM}.

    Args:
        equipment_id: Equipment code (e.g., "S002-CHILLER-B1-001")
        equipment_type: Optional explicit type string (e.g., "chiller")

    Returns:
        EquipmentClass enum value
    """
    # Try explicit type field first
    if equipment_type:
        type_upper = equipment_type.upper().replace(" ", "_")
        for member in EquipmentClass:
            if member.value.upper() == type_upper or member.name == type_upper:
                return member
        # Also check prefix map against the type string
        for prefix, eq_class in EQUIPMENT_TYPE_MAP:
            if type_upper == prefix or type_upper.startswith(prefix):
                return eq_class

    # Extract type segment from equipment ID
    # Format: {SITE}-{TYPE}-{LOCATION}-{NUM} or {SITE}-{TYPE}-{ZONE}
    if equipment_id:
        # Remove the site prefix (first segment before hyphen)
        parts = equipment_id.split("-", 1)
        if len(parts) > 1:
            remainder = parts[1]  # Everything after site prefix
            # Match against prefix map (longest first)
            for prefix, eq_class in EQUIPMENT_TYPE_MAP:
                if remainder.startswith(prefix):
                    return eq_class

    return EquipmentClass.UNKNOWN


# =============================================================================
# Dashboard Card
# =============================================================================


@dataclass
class DashboardCard:
    """A dashboard card configuration."""

    card_id: str
    title: str
    card_type: str  # kpi, chart, status_grid, gauge, list
    domain: str
    priority: int
    equipment_classes: List[EquipmentClass]
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "card_id": self.card_id,
            "title": self.title,
            "card_type": self.card_type,
            "domain": self.domain,
            "priority": self.priority,
            "equipment_classes": [ec.value for ec in self.equipment_classes],
            "config": self.config,
        }


# Card templates per equipment class
CARD_TEMPLATES: Dict[EquipmentClass, List[Dict[str, Any]]] = {
    EquipmentClass.CHILLER: [
        {
            "suffix": "status",
            "title": "Chiller Status",
            "card_type": "status_grid",
            "domain": "hvac",
            "priority": 10,
            "config": {"metrics": ["status", "load_pct", "supply_temp", "return_temp", "efficiency"]},
        },
        {
            "suffix": "efficiency",
            "title": "Chiller Efficiency Trend",
            "card_type": "chart",
            "domain": "hvac",
            "priority": 20,
            "config": {"chart_type": "line", "metric": "cop", "period": "7d"},
        },
    ],
    EquipmentClass.AHU: [
        {
            "suffix": "status",
            "title": "AHU Status",
            "card_type": "status_grid",
            "domain": "hvac",
            "priority": 15,
            "config": {"metrics": ["status", "supply_temp", "return_temp", "filter_dp", "fan_speed"]},
        },
    ],
    EquipmentClass.FCU: [
        {
            "suffix": "zones",
            "title": "Zone Temperatures",
            "card_type": "kpi",
            "domain": "hvac",
            "priority": 25,
            "config": {"metric": "zone_temp", "unit": "\u00b0C", "thresholds": {"warning": 26, "critical": 28}},
        },
    ],
    EquipmentClass.VAV: [
        {
            "suffix": "status",
            "title": "VAV Box Status",
            "card_type": "status_grid",
            "domain": "hvac",
            "priority": 30,
            "config": {"metrics": ["status", "damper_position", "airflow", "zone_temp"], "compact": True},
        },
    ],
    EquipmentClass.GENERATOR: [
        {
            "suffix": "status",
            "title": "Backup Power Status",
            "card_type": "status_grid",
            "domain": "electrical",
            "priority": 8,
            "config": {"metrics": ["status", "fuel_level", "runtime_hours", "load_pct", "battery_voltage"]},
        },
    ],
    EquipmentClass.UPS: [
        {
            "suffix": "battery",
            "title": "UPS Battery Status",
            "card_type": "kpi",
            "domain": "electrical",
            "priority": 12,
            "config": {"metric": "battery_pct", "unit": "%", "thresholds": {"warning": 50, "critical": 20}},
        },
    ],
    EquipmentClass.SOLAR_INVERTER: [
        {
            "suffix": "generation",
            "title": "Solar Generation",
            "card_type": "gauge",
            "domain": "solar",
            "priority": 5,
            "config": {"metric": "power_kw", "max_metric": "rated_kw", "unit": "kW"},
        },
        {
            "suffix": "daily-curve",
            "title": "Solar Daily Curve",
            "card_type": "chart",
            "domain": "solar",
            "priority": 18,
            "config": {"chart_type": "area", "metric": "power_kw", "period": "1d"},
        },
    ],
    EquipmentClass.BESS: [
        {
            "suffix": "storage",
            "title": "Battery Storage",
            "card_type": "gauge",
            "domain": "solar",
            "priority": 6,
            "config": {"metric": "soc_pct", "max_value": 100, "unit": "%"},
        },
    ],
    EquipmentClass.METER_ENERGY: [
        {
            "suffix": "consumption",
            "title": "Energy Consumption",
            "card_type": "kpi",
            "domain": "energy",
            "priority": 3,
            "config": {"metric": "total_kwh", "unit": "kWh", "show_cost": True, "rate_per_kwh": 5.0},
        },
    ],
    EquipmentClass.METER_WATER: [
        {
            "suffix": "consumption",
            "title": "Water Consumption",
            "card_type": "kpi",
            "domain": "water",
            "priority": 22,
            "config": {"metric": "total_litres", "unit": "L", "leak_detection": True},
        },
    ],
    EquipmentClass.LIGHTING: [
        {
            "suffix": "status",
            "title": "Lighting Status",
            "card_type": "status_grid",
            "domain": "lighting",
            "priority": 28,
            "config": {"metrics": ["status", "brightness", "power_w", "driver_temp"]},
        },
    ],
    EquipmentClass.PIR: [
        {
            "suffix": "occupancy",
            "title": "Occupancy",
            "card_type": "kpi",
            "domain": "occupancy",
            "priority": 26,
            "config": {"metric": "occupied_zones", "unit": "zones"},
        },
    ],
    EquipmentClass.ACCESS_POINT: [
        {
            "suffix": "events",
            "title": "Access Events",
            "card_type": "list",
            "domain": "security",
            "priority": 32,
            "config": {"max_items": 20, "show_timestamp": True, "show_direction": True},
        },
    ],
    EquipmentClass.FIRE_PANEL: [
        {
            "suffix": "status",
            "title": "Fire System Status",
            "card_type": "status_grid",
            "domain": "fire",
            "priority": 2,
            "config": {"metrics": ["alarm_status", "detector_count", "fault_count", "last_test"]},
        },
    ],
    EquipmentClass.ELEVATOR: [
        {
            "suffix": "status",
            "title": "Elevator Status",
            "card_type": "status_grid",
            "domain": "vertical_transport",
            "priority": 35,
            "config": {"metrics": ["status", "current_floor", "door_status", "mode"]},
        },
    ],
}


# =============================================================================
# Monitoring Rule
# =============================================================================


@dataclass
class MonitoringRule:
    """A monitoring rule definition."""

    rule_id: str
    name: str
    description: str
    equipment_class: EquipmentClass
    metric: str
    condition: str  # gt, lt, eq, ne, change
    threshold: float
    severity: str  # critical, warning, info
    evaluation_window: str  # e.g., "5m", "15m", "1h"
    cooldown_minutes: int = 30

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "equipment_class": self.equipment_class.value,
            "metric": self.metric,
            "condition": self.condition,
            "threshold": self.threshold,
            "severity": self.severity,
            "evaluation_window": self.evaluation_window,
            "cooldown_minutes": self.cooldown_minutes,
        }


# Default monitoring rules per equipment class
DEFAULT_RULES: Dict[EquipmentClass, List[Dict[str, Any]]] = {
    EquipmentClass.CHILLER: [
        {
            "suffix": "high-load",
            "name": "Chiller High Load",
            "description": "Chiller load exceeds 85% for sustained period",
            "metric": "load_pct",
            "condition": "gt",
            "threshold": 85.0,
            "severity": "warning",
            "evaluation_window": "15m",
            "cooldown_minutes": 60,
        },
        {
            "suffix": "overload",
            "name": "Chiller Overload",
            "description": "Chiller load exceeds 95% — risk of trip",
            "metric": "load_pct",
            "condition": "gt",
            "threshold": 95.0,
            "severity": "critical",
            "evaluation_window": "5m",
            "cooldown_minutes": 15,
        },
        {
            "suffix": "efficiency-degraded",
            "name": "Chiller Efficiency Degraded",
            "description": "COP dropped below 3.0 — check condenser and refrigerant",
            "metric": "cop",
            "condition": "lt",
            "threshold": 3.0,
            "severity": "warning",
            "evaluation_window": "1h",
            "cooldown_minutes": 120,
        },
        {
            "suffix": "supply-temp-high",
            "name": "Chiller Supply Temp High",
            "description": "Chilled water supply temperature above setpoint",
            "metric": "supply_temp",
            "condition": "gt",
            "threshold": 8.0,
            "severity": "warning",
            "evaluation_window": "10m",
            "cooldown_minutes": 30,
        },
    ],
    EquipmentClass.AHU: [
        {
            "suffix": "filter-dp-warning",
            "name": "AHU Filter DP Warning",
            "description": "Filter differential pressure above normal — schedule replacement",
            "metric": "filter_dp",
            "condition": "gt",
            "threshold": 250.0,
            "severity": "warning",
            "evaluation_window": "1h",
            "cooldown_minutes": 240,
        },
        {
            "suffix": "filter-dp-critical",
            "name": "AHU Filter DP Critical",
            "description": "Filter differential pressure critically high — replace immediately",
            "metric": "filter_dp",
            "condition": "gt",
            "threshold": 400.0,
            "severity": "critical",
            "evaluation_window": "15m",
            "cooldown_minutes": 60,
        },
        {
            "suffix": "supply-temp-deviation",
            "name": "AHU Supply Temp Deviation",
            "description": "Supply air temperature deviating from setpoint",
            "metric": "supply_temp_deviation",
            "condition": "gt",
            "threshold": 3.0,
            "severity": "warning",
            "evaluation_window": "15m",
            "cooldown_minutes": 30,
        },
    ],
    EquipmentClass.FCU: [
        {
            "suffix": "zone-temp-warning",
            "name": "Zone Temperature Warning",
            "description": "Zone temperature exceeds comfort range",
            "metric": "zone_temp",
            "condition": "gt",
            "threshold": 26.0,
            "severity": "warning",
            "evaluation_window": "15m",
            "cooldown_minutes": 30,
        },
        {
            "suffix": "zone-temp-critical",
            "name": "Zone Temperature Critical",
            "description": "Zone temperature significantly outside comfort range",
            "metric": "zone_temp",
            "condition": "gt",
            "threshold": 28.0,
            "severity": "critical",
            "evaluation_window": "10m",
            "cooldown_minutes": 15,
        },
    ],
    EquipmentClass.GENERATOR: [
        {
            "suffix": "fuel-low",
            "name": "Generator Fuel Low",
            "description": "Fuel level below 30% — schedule refuelling",
            "metric": "fuel_level_pct",
            "condition": "lt",
            "threshold": 30.0,
            "severity": "warning",
            "evaluation_window": "1h",
            "cooldown_minutes": 240,
        },
        {
            "suffix": "fuel-critical",
            "name": "Generator Fuel Critical",
            "description": "Fuel level below 10% — immediate refuelling required",
            "metric": "fuel_level_pct",
            "condition": "lt",
            "threshold": 10.0,
            "severity": "critical",
            "evaluation_window": "15m",
            "cooldown_minutes": 60,
        },
        {
            "suffix": "runtime-high",
            "name": "Generator Runtime High",
            "description": "Continuous runtime exceeds 8 hours — check load transfer",
            "metric": "continuous_runtime_hours",
            "condition": "gt",
            "threshold": 8.0,
            "severity": "warning",
            "evaluation_window": "30m",
            "cooldown_minutes": 120,
        },
    ],
    EquipmentClass.SOLAR_INVERTER: [
        {
            "suffix": "underperforming",
            "name": "Inverter Underperforming",
            "description": "Inverter output below expected for current irradiance",
            "metric": "performance_ratio",
            "condition": "lt",
            "threshold": 0.75,
            "severity": "warning",
            "evaluation_window": "1h",
            "cooldown_minutes": 120,
        },
        {
            "suffix": "fault",
            "name": "Inverter Fault",
            "description": "Inverter reporting fault condition",
            "metric": "fault_code",
            "condition": "ne",
            "threshold": 0,
            "severity": "critical",
            "evaluation_window": "5m",
            "cooldown_minutes": 15,
        },
    ],
    EquipmentClass.BESS: [
        {
            "suffix": "battery-low",
            "name": "Battery Low",
            "description": "Battery SOC below 20% — limit discharge",
            "metric": "soc_pct",
            "condition": "lt",
            "threshold": 20.0,
            "severity": "warning",
            "evaluation_window": "15m",
            "cooldown_minutes": 30,
        },
        {
            "suffix": "battery-critical",
            "name": "Battery Critical",
            "description": "Battery SOC below 10% — stop discharge immediately",
            "metric": "soc_pct",
            "condition": "lt",
            "threshold": 10.0,
            "severity": "critical",
            "evaluation_window": "5m",
            "cooldown_minutes": 15,
        },
        {
            "suffix": "temp-high",
            "name": "Battery Temperature High",
            "description": "Battery temperature exceeds safe operating range",
            "metric": "battery_temp_c",
            "condition": "gt",
            "threshold": 45.0,
            "severity": "critical",
            "evaluation_window": "5m",
            "cooldown_minutes": 15,
        },
    ],
    EquipmentClass.METER_WATER: [
        {
            "suffix": "leak-detected",
            "name": "Water Leak Detected",
            "description": "Flow detected during expected zero-flow period",
            "metric": "flow_rate",
            "condition": "gt",
            "threshold": 0.5,
            "severity": "warning",
            "evaluation_window": "30m",
            "cooldown_minutes": 60,
        },
        {
            "suffix": "consumption-spike",
            "name": "Water Consumption Spike",
            "description": "Water usage exceeds 3x rolling average",
            "metric": "consumption_ratio",
            "condition": "gt",
            "threshold": 3.0,
            "severity": "warning",
            "evaluation_window": "1h",
            "cooldown_minutes": 120,
        },
    ],
    EquipmentClass.FIRE_PANEL: [
        {
            "suffix": "alarm-active",
            "name": "Fire Alarm Active",
            "description": "Fire alarm triggered — immediate response required",
            "metric": "alarm_active",
            "condition": "eq",
            "threshold": 1,
            "severity": "critical",
            "evaluation_window": "1m",
            "cooldown_minutes": 5,
        },
        {
            "suffix": "detector-fault",
            "name": "Fire Detector Fault",
            "description": "One or more fire detectors reporting fault",
            "metric": "detector_fault_count",
            "condition": "gt",
            "threshold": 0,
            "severity": "warning",
            "evaluation_window": "15m",
            "cooldown_minutes": 60,
        },
    ],
}


# =============================================================================
# Module Suggestions
# =============================================================================

MODULE_SUGGESTIONS: Dict[EquipmentClass, Dict[str, Any]] = {
    EquipmentClass.CHILLER: {
        "module": "hvac_control",
        "reason": "Chiller staging and setpoint optimization for energy savings",
        "savings_hint": "5-15% reduction in chiller energy consumption",
    },
    EquipmentClass.SOLAR_INVERTER: {
        "module": "solar",
        "reason": "Solar performance monitoring, curtailment optimization, and grid export management",
        "savings_hint": "Maximize self-consumption, reduce grid export losses",
    },
    EquipmentClass.BESS: {
        "module": "solar",
        "reason": "Battery arbitrage optimization and peak demand shaving",
        "savings_hint": "10-20% reduction in peak demand charges",
    },
    EquipmentClass.LIGHTING: {
        "module": "lighting",
        "reason": "DALI-2 scene control, daylight harvesting, and occupancy-based dimming",
        "savings_hint": "20-40% lighting energy reduction",
    },
    EquipmentClass.PIR: {
        "module": "lighting",
        "reason": "Occupancy-driven HVAC setback and lighting control",
        "savings_hint": "15-25% energy savings in unoccupied zones",
    },
    EquipmentClass.METER_WATER: {
        "module": "water",
        "reason": "Leak detection, consumption trending, and cost allocation",
        "savings_hint": "Early leak detection saves 5-15% water costs",
    },
    EquipmentClass.ACCESS_POINT: {
        "module": "security",
        "reason": "Access control analytics, tailgating detection, and visitor management",
        "savings_hint": "Improved security posture and audit compliance",
    },
}


# =============================================================================
# Health Weights
# =============================================================================

HEALTH_WEIGHTS: Dict[EquipmentClass, int] = {
    EquipmentClass.CHILLER: 15,
    EquipmentClass.AHU: 10,
    EquipmentClass.FCU: 5,
    EquipmentClass.VAV: 5,
    EquipmentClass.BOILER: 10,
    EquipmentClass.COOLING_TOWER: 8,
    EquipmentClass.PUMP: 6,
    EquipmentClass.GENERATOR: 12,
    EquipmentClass.UPS: 10,
    EquipmentClass.TRANSFORMER: 8,
    EquipmentClass.ATS: 7,
    EquipmentClass.SOLAR_INVERTER: 10,
    EquipmentClass.BESS: 10,
    EquipmentClass.SOLAR_PANEL: 5,
    EquipmentClass.METER_ENERGY: 4,
    EquipmentClass.METER_WATER: 4,
    EquipmentClass.METER_GAS: 4,
    EquipmentClass.LIGHTING: 3,
    EquipmentClass.PIR: 2,
    EquipmentClass.ACCESS_POINT: 3,
    EquipmentClass.CCTV: 3,
    EquipmentClass.FIRE_PANEL: 15,
    EquipmentClass.FIRE_DETECTOR: 8,
    EquipmentClass.ELEVATOR: 10,
    EquipmentClass.UNKNOWN: 1,
}


# =============================================================================
# Domain groupings for AI context generation
# =============================================================================

_DOMAIN_MAP: Dict[str, List[EquipmentClass]] = {
    "HVAC": [
        EquipmentClass.CHILLER,
        EquipmentClass.AHU,
        EquipmentClass.FCU,
        EquipmentClass.VAV,
        EquipmentClass.BOILER,
        EquipmentClass.COOLING_TOWER,
        EquipmentClass.PUMP,
    ],
    "Electrical": [
        EquipmentClass.GENERATOR,
        EquipmentClass.UPS,
        EquipmentClass.TRANSFORMER,
        EquipmentClass.ATS,
    ],
    "Solar/BESS": [
        EquipmentClass.SOLAR_INVERTER,
        EquipmentClass.BESS,
        EquipmentClass.SOLAR_PANEL,
    ],
    "Energy": [EquipmentClass.METER_ENERGY],
    "Water": [EquipmentClass.METER_WATER, EquipmentClass.METER_GAS],
    "Lighting": [EquipmentClass.LIGHTING],
    "Occupancy": [EquipmentClass.PIR],
    "Security": [EquipmentClass.ACCESS_POINT, EquipmentClass.CCTV],
    "Fire": [EquipmentClass.FIRE_PANEL, EquipmentClass.FIRE_DETECTOR],
    "Elevators": [EquipmentClass.ELEVATOR],
}


# =============================================================================
# Dashboard Generator
# =============================================================================


class DashboardGenerator:
    """Core auto-dashboard generation engine.

    Classifies equipment, generates tailored dashboard cards, monitoring
    rules, health scoring weights, module suggestions, and AI context.
    """

    def __init__(self) -> None:
        """Initialize the dashboard generator."""
        self._equipment_repo = None

    @property
    def equipment_repo(self):
        """Lazy-load equipment repository to avoid import at module level."""
        if self._equipment_repo is None:
            from app.database.repositories.equipment_repository import get_equipment_repository

            self._equipment_repo = get_equipment_repository()
        return self._equipment_repo

    def generate_for_site(
        self,
        site_id: str,
        equipment_list: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Generate a complete dashboard configuration for a site.

        Args:
            site_id: Site code (e.g., "site-002")
            equipment_list: Optional pre-loaded equipment list. If None,
                loads from equipment repository.

        Returns:
            Complete dashboard configuration dict.
        """
        if equipment_list is None:
            equipment_list = self._load_equipment(site_id)

        classified = self._classify_all(equipment_list)

        # Build equipment summary
        summary: Dict[str, int] = {}
        for item in classified:
            cls_name = item["equipment_class"].value
            summary[cls_name] = summary.get(cls_name, 0) + 1

        cards = self._generate_cards(site_id, classified)
        rules = self._generate_rules(site_id, classified)
        weights = self._calculate_health_weights(classified)
        suggestions = self._suggest_modules(classified)
        ai_context = self._generate_ai_context(site_id, classified, equipment_list)

        logger.info(
            "Generated dashboard for %s: %d equipment, %d cards, %d rules, %d suggestions",
            site_id,
            len(equipment_list),
            len(cards),
            len(rules),
            len(suggestions),
        )

        return {
            "site_id": site_id,
            "status": "generated",
            "equipment_summary": summary,
            "dashboard_cards": [c.to_dict() for c in cards],
            "monitoring_rules": [r.to_dict() for r in rules],
            "health_weights": weights,
            "module_suggestions": suggestions,
            "ai_context": ai_context,
        }

    def _classify_all(self, equipment_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Classify all equipment in the list.

        Args:
            equipment_list: List of equipment dicts with 'code' and optionally 'type'.

        Returns:
            List of dicts with added 'equipment_class' key.
        """
        result = []
        for eq in equipment_list:
            code = eq.get("code", "")
            eq_type = eq.get("type")
            eq_class = classify_equipment(code, eq_type)
            result.append({**eq, "equipment_class": eq_class})
        return result

    def _generate_cards(self, site_id: str, classified: List[Dict[str, Any]]) -> List[DashboardCard]:
        """Generate dashboard cards from classified equipment.

        Always includes health score gauge and active alerts KPI.
        Adds equipment-specific cards with count in title.
        Uses compact mode for >10 units of a type.

        Args:
            site_id: Site code
            classified: Classified equipment list

        Returns:
            List of DashboardCard instances
        """
        cards: List[DashboardCard] = []

        # Always-present cards
        cards.append(
            DashboardCard(
                card_id=f"{site_id}-health-score",
                title="Building Health Score",
                card_type="gauge",
                domain="overview",
                priority=1,
                equipment_classes=[],
                config={"metric": "health_score", "max_value": 100, "unit": "%"},
            )
        )
        cards.append(
            DashboardCard(
                card_id=f"{site_id}-active-alerts",
                title="Active Alerts",
                card_type="kpi",
                domain="overview",
                priority=2,
                equipment_classes=[],
                config={"metric": "active_alert_count", "thresholds": {"warning": 3, "critical": 5}},
            )
        )

        # Group by class
        class_groups: Dict[EquipmentClass, List[Dict[str, Any]]] = {}
        for item in classified:
            cls = item["equipment_class"]
            if cls == EquipmentClass.UNKNOWN:
                continue
            class_groups.setdefault(cls, []).append(item)

        # Generate equipment-specific cards
        for eq_class, items in class_groups.items():
            templates = CARD_TEMPLATES.get(eq_class, [])
            count = len(items)
            for tmpl in templates:
                title = tmpl["title"]
                if count > 1:
                    title = f"{title} ({count})"

                config = dict(tmpl["config"])
                if count > 10:
                    config["compact"] = True

                cards.append(
                    DashboardCard(
                        card_id=f"{site_id}-{eq_class.value}-{tmpl['suffix']}",
                        title=title,
                        card_type=tmpl["card_type"],
                        domain=tmpl["domain"],
                        priority=tmpl["priority"],
                        equipment_classes=[eq_class],
                        config=config,
                    )
                )

        # Sort by priority (lower = higher priority)
        cards.sort(key=lambda c: c.priority)
        return cards

    def _generate_rules(self, site_id: str, classified: List[Dict[str, Any]]) -> List[MonitoringRule]:
        """Generate monitoring rules from templates.

        Args:
            site_id: Site code
            classified: Classified equipment list

        Returns:
            List of MonitoringRule instances
        """
        rules: List[MonitoringRule] = []
        seen_classes: set = set()

        for item in classified:
            cls = item["equipment_class"]
            if cls in seen_classes or cls == EquipmentClass.UNKNOWN:
                continue
            seen_classes.add(cls)

            rule_templates = DEFAULT_RULES.get(cls, [])
            for tmpl in rule_templates:
                rules.append(
                    MonitoringRule(
                        rule_id=f"{site_id}-{cls.value}-{tmpl['suffix']}",
                        name=tmpl["name"],
                        description=tmpl["description"],
                        equipment_class=cls,
                        metric=tmpl["metric"],
                        condition=tmpl["condition"],
                        threshold=tmpl["threshold"],
                        severity=tmpl["severity"],
                        evaluation_window=tmpl["evaluation_window"],
                        cooldown_minutes=tmpl.get("cooldown_minutes", 30),
                    )
                )

        return rules

    def _calculate_health_weights(self, classified: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate normalised health scoring weights.

        Uses base weights per class with diminishing returns for multiple
        units of the same type (sqrt scaling).

        Args:
            classified: Classified equipment list

        Returns:
            Dict mapping equipment class name to normalised weight (sums to 100).
        """
        class_counts: Dict[EquipmentClass, int] = {}
        for item in classified:
            cls = item["equipment_class"]
            if cls == EquipmentClass.UNKNOWN:
                continue
            class_counts[cls] = class_counts.get(cls, 0) + 1

        raw_weights: Dict[EquipmentClass, float] = {}
        for cls, count in class_counts.items():
            base = HEALTH_WEIGHTS.get(cls, 1)
            # Diminishing returns: sqrt scaling for multiple units
            raw_weights[cls] = base * math.sqrt(count)

        total = sum(raw_weights.values())
        if total == 0:
            return {}

        return {cls.value: round((w / total) * 100, 2) for cls, w in raw_weights.items()}

    def _suggest_modules(self, classified: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Suggest add-on modules based on discovered equipment.

        Deduplicates by module name.

        Args:
            classified: Classified equipment list

        Returns:
            List of module suggestion dicts.
        """
        seen_modules: set = set()
        suggestions: List[Dict[str, Any]] = []

        for item in classified:
            cls = item["equipment_class"]
            suggestion = MODULE_SUGGESTIONS.get(cls)
            if suggestion and suggestion["module"] not in seen_modules:
                seen_modules.add(suggestion["module"])
                equipment_codes = [i["code"] for i in classified if i["equipment_class"] == cls and "code" in i]
                suggestions.append(
                    {
                        "module": suggestion["module"],
                        "reason": suggestion["reason"],
                        "savings_hint": suggestion["savings_hint"],
                        "triggered_by": cls.value,
                        "equipment_count": len(equipment_codes),
                    }
                )

        return suggestions

    def _generate_ai_context(
        self,
        site_id: str,
        classified: List[Dict[str, Any]],
        equipment_list: List[Dict[str, Any]],
    ) -> str:
        """Generate natural language AI context summary.

        Groups equipment by domain for Claude's recommendation engine.

        Args:
            site_id: Site code
            classified: Classified equipment list
            equipment_list: Original equipment list

        Returns:
            Multi-line natural language summary string.
        """
        lines: List[str] = [
            f"Site {site_id} has {len(equipment_list)} equipment items discovered.",
            "",
        ]

        # Group classified items by domain
        for domain_name, domain_classes in _DOMAIN_MAP.items():
            domain_items = [item for item in classified if item["equipment_class"] in domain_classes]
            if not domain_items:
                continue

            # Count per class within domain
            counts: Dict[str, int] = {}
            for item in domain_items:
                cls_name = item["equipment_class"].value
                counts[cls_name] = counts.get(cls_name, 0) + 1

            parts = [f"{count} {cls}" for cls, count in counts.items()]
            lines.append(f"{domain_name}: {', '.join(parts)}")

        unknown_count = sum(1 for item in classified if item["equipment_class"] == EquipmentClass.UNKNOWN)
        if unknown_count:
            lines.append(f"\n{unknown_count} unclassified equipment items.")

        return "\n".join(lines)

    def _load_equipment(self, site_id: str) -> List[Dict[str, Any]]:
        """Load equipment list with 3-tier fallback.

        Tier 1: Supabase via equipment repository
        Tier 2: JSON building data files
        Tier 3: Empty list (graceful degradation)

        Args:
            site_id: Site code (e.g., "site-002")

        Returns:
            List of equipment dicts.
        """
        # Tier 1: Supabase via equipment repository
        try:
            from app.database.repositories.equipment_repository import get_equipment_repository

            repo = get_equipment_repository()
            equipment = repo.get_by_site_code(site_id)
            if equipment:
                logger.debug("Loaded %d equipment from repository for %s", len(equipment), site_id)
                return equipment
        except Exception as e:
            logger.warning("Equipment repository unavailable for %s: %s", site_id, e)

        # Tier 2: JSON building data files
        try:
            from pathlib import Path
            import json

            equipment_dir = Path(__file__).parent.parent / "data" / "sites" / site_id / "equipment"
            if equipment_dir.is_dir():
                equipment = []
                for json_file in sorted(equipment_dir.glob("*.json")):
                    try:
                        data = json.loads(json_file.read_text())
                        # Normalise: ensure 'code' key exists (some files use 'id')
                        if "code" not in data and "id" in data:
                            data["code"] = data["id"]
                        if "type" not in data and "equipment_type" in data:
                            data["type"] = data["equipment_type"]
                        equipment.append(data)
                    except Exception as file_err:
                        logger.debug("Skipping %s: %s", json_file.name, file_err)
                if equipment:
                    logger.info("Loaded %d equipment from JSON for %s", len(equipment), site_id)
                    return equipment
        except Exception as e:
            logger.warning("JSON equipment loading failed for %s: %s", site_id, e)

        # Tier 3: Empty list
        logger.warning("No equipment found for %s (all sources exhausted)", site_id)
        return []


# =============================================================================
# Singleton
# =============================================================================

_instance: Optional[DashboardGenerator] = None


def get_dashboard_generator() -> DashboardGenerator:
    """Get or create the singleton DashboardGenerator instance."""
    global _instance
    if _instance is None:
        _instance = DashboardGenerator()
    return _instance
