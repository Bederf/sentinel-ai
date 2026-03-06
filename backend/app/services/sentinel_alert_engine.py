"""SENTINEL Alert Engine — equipment-type-aware safety boundary evaluator.

Extracted from lifecycle_orchestrator._scan_safety_boundaries() to enforce the
architecture rule: "SENTINEL does NOT simulate. It receives data and responds."

The orchestrator produces telemetry. This engine consumes telemetry and returns
safety violations. It does NOT own the alert queue, cooldown, or dashboard push —
the caller handles that.

Key intelligence fixes over the old orchestrator method:
1. Pump DP gets pump-specific action text (not AHU "check filter and fan speed")
2. Chiller ramp-up suppression: supply_temp alerts suppressed when chiller is
   cold-starting (load < 50% and supply_temp > 15°C)
3. Equipment-type-aware action text lookup with _default fallback
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AlertContext:
    """Context about building state when evaluating alerts."""

    simulated_hour: int
    is_peak: bool
    site_state: str
    occupancy_pct: float
    hvac_mode: str


@dataclass
class SafetyViolation:
    """A single safety boundary violation detected by the engine."""

    equipment_code: str
    equipment_type: str
    point_name: str
    value: float
    unit: str
    severity: str  # "warning" | "critical"
    recommended_action: str
    operational_context: dict = field(default_factory=dict)
    limit_desc: str = ""
    approach_pct: int = 0
    limit_min: float = 0.0
    limit_max: float = 0.0


class SentinelAlertEngine:
    """Stateless evaluator: takes equipment states + context, returns violations.

    Usage::

        engine = SentinelAlertEngine()
        violations = engine.evaluate(equipment_states, alert_context)
        # caller handles: _emit_event(), _push_alert_to_dashboard(), Sentry notify
    """

    # Physical safety boundaries — readings outside these ranges indicate danger.
    SAFETY_LIMITS = {
        "zone_temp": {"min": 16.0, "max": 28.0, "unit": "°C"},
        "room_temp": {"min": 16.0, "max": 28.0, "unit": "°C"},
        "supply_temp": {"min": 4.0, "max": 25.0, "unit": "°C"},
        "supply_air_temp": {"min": 12.0, "max": 22.0, "unit": "°C"},
        "battery_pct": {"min": 30.0, "max": 100.0, "unit": "%"},
        "load_pct": {"min": 0.0, "max": 95.0, "unit": "%"},
        "differential_pressure_kpa": {"min": 0.0, "max": 200.0, "unit": "kPa"},
    }

    # Normal operating bands — values within these are expected and should NOT
    # trigger alerts, even if near a safety limit.
    # Structure: point_name → equip_type (or "_default") → time_period → (min, max)
    NORMAL_BANDS = {
        "supply_temp": {
            "chiller": {"default": (5.0, 8.5)},  # Design supply 6-7°C
            "ahu": {"default": (12.5, 18.0)},
        },
        "supply_air_temp": {
            "_default": {"default": (13.0, 20.0)},
        },
        "zone_temp": {
            "_default": {
                "peak": (20.0, 24.0),
                "off_peak": (18.0, 26.0),
            },
        },
        "room_temp": {
            "_default": {
                "peak": (20.0, 24.0),
                "off_peak": (18.0, 26.0),
            },
        },
        "load_pct": {
            "chiller": {"peak": (0.0, 92.0), "off_peak": (0.0, 70.0)},
            "ups": {"default": (0.0, 80.0)},
            "_default": {"default": (0.0, 85.0)},
        },
        "battery_pct": {
            "_default": {"default": (50.0, 100.0)},
        },
        "differential_pressure_kpa": {
            "pump": {"default": (0.5, 180.0)},  # Pumps: low DP is normal at partial load
            "_default": {"default": (20.0, 150.0)},
        },
    }

    # Recommended actions — tells operators WHAT TO DO.
    # Structure: point_name → equip_type (or "_default") → severity → action_text
    SAFETY_ACTIONS = {
        "supply_temp": {
            "chiller": {
                "warning": "Check chiller staging and condenser water temps. Consider staging up if load demands it.",
                "critical": (
                    "IMMEDIATE: Verify chiller refrigerant charge and compressor operation."
                    " Risk of coil freeze below 4°C."
                ),
            },
            "ahu": {
                "warning": "Check AHU coil valve position and mixed air dampers.",
                "critical": "IMMEDIATE: Check AHU heating/cooling coil for failure. Verify supply fan operation.",
            },
            "_default": {
                "warning": "Check equipment supply temperature trending and control setpoints.",
                "critical": "IMMEDIATE: Investigate supply temperature deviation. Check control loop and actuators.",
            },
        },
        "supply_air_temp": {
            "_default": {
                "warning": "Check AHU mixed air damper position and cooling coil valve.",
                "critical": (
                    "IMMEDIATE: Supply air temperature out of range. Check AHU cooling/heating coils and control loop."
                ),
            },
        },
        "zone_temp": {
            "_default": {
                "warning": "Check zone FCU/VAV operation and thermostat setpoint. Verify occupancy schedule.",
                "critical": "IMMEDIATE: Zone temperature out of comfort range. Check FCU/VAV and AHU supply.",
            },
        },
        "room_temp": {
            "_default": {
                "warning": "Check room FCU operation and thermostat setpoint.",
                "critical": "IMMEDIATE: Room temperature out of comfort range. Check HVAC supply to this zone.",
            },
        },
        "load_pct": {
            "chiller": {
                "warning": "Monitor chiller load trend. Consider staging another chiller online if available.",
                "critical": "Stage additional chiller ASAP. Current unit at risk of trip on high pressure.",
            },
            "ups": {
                "warning": "Review connected loads on this UPS. Plan load shedding if trend continues.",
                "critical": "IMMEDIATE: Shed non-critical loads. UPS at risk of overload trip.",
            },
            "_default": {
                "warning": "Monitor equipment load trend. Consider load redistribution.",
                "critical": "IMMEDIATE: Equipment overloaded. Reduce load or bring standby online.",
            },
        },
        "battery_pct": {
            "_default": {
                "warning": "Check charger operation and battery voltage. Schedule battery test.",
                "critical": (
                    "IMMEDIATE: Check charger operation. Prepare for mains transfer if battery continues to discharge."
                ),
            },
        },
        "differential_pressure_kpa": {
            "pump": {
                "warning": "Check pump impeller and strainer condition. Verify system valve positions.",
                "critical": "IMMEDIATE: Check pump impeller and strainer condition. Verify system valve positions.",
            },
            "ahu": {
                "warning": "Check filter condition and fan speed. Schedule filter inspection.",
                "critical": "IMMEDIATE: Differential pressure critical. Check for blocked filters or duct obstruction.",
            },
            "_default": {
                "warning": "Check filter condition and fan speed. Schedule filter inspection.",
                "critical": "IMMEDIATE: Differential pressure critical. Check for blocked filters or duct obstruction.",
            },
        },
    }

    def evaluate(self, equipment_states: dict, context: AlertContext) -> list[SafetyViolation]:
        """Evaluate all equipment against safety thresholds.

        Args:
            equipment_states: Dict mapping equipment code to state dict with sensor_readings.
            context: Building context (hour, peak, occupancy, etc.).

        Returns:
            List of SafetyViolation objects, capped at 3 to prevent alarm fatigue.
        """
        violations: list[SafetyViolation] = []

        for code, state in equipment_states.items():
            # Skip equipment that is off — zero values are expected, not violations
            if not state.get("is_running", False):
                continue

            readings = state.get("sensor_readings", {})
            equip_type = state.get("type", "unknown").lower()

            for point_name, value in readings.items():
                if point_name not in self.SAFETY_LIMITS:
                    continue

                if not isinstance(value, (int, float)):
                    continue

                limits = self.SAFETY_LIMITS[point_name]
                safe_min = limits["min"]
                safe_max = limits["max"]
                safe_range = safe_max - safe_min

                # --- Chiller ramp-up suppression ---
                # When a chiller just started, supply_temp is high and load is low.
                # This is normal — not a safety concern.
                if point_name == "supply_temp" and equip_type == "chiller":
                    load_pct = readings.get("load_pct", 100)
                    if isinstance(load_pct, (int, float)) and load_pct < 50 and value > 15.0:
                        continue

                # Check proximity to boundaries
                if value < safe_min:
                    approach_pct = 100  # Already violated
                elif value > safe_max:
                    approach_pct = 100
                elif value < safe_min + safe_range * 0.1:
                    approach_pct = 90  # Within 10% of lower limit
                elif value > safe_max - safe_range * 0.1:
                    approach_pct = 90  # Within 10% of upper limit
                else:
                    approach_pct = 0  # Safe

                if approach_pct < 90:
                    continue

                # Suppress alerts for values within normal operating bands
                normal_band = self._get_normal_band(point_name, equip_type, context.is_peak)
                if normal_band and normal_band[0] <= value <= normal_band[1]:
                    continue

                severity = "critical" if approach_pct >= 100 else "warning"
                recommended_action = self._get_safety_action(point_name, equip_type, severity)

                # Determine which limit is being approached
                if value <= safe_min or value < safe_min + safe_range * 0.1:
                    limit_desc = f"limit: {safe_min}{limits['unit']}"
                else:
                    limit_desc = f"limit: {safe_max}{limits['unit']}"

                operational_context = {
                    "site_state": context.site_state,
                    "is_peak_hours": context.is_peak,
                    "occupancy_pct": context.occupancy_pct,
                    "hvac_mode": context.hvac_mode,
                    "hour": context.simulated_hour,
                }

                violations.append(
                    SafetyViolation(
                        equipment_code=code,
                        equipment_type=equip_type,
                        point_name=point_name,
                        value=value,
                        unit=limits["unit"],
                        severity=severity,
                        recommended_action=recommended_action,
                        operational_context=operational_context,
                        limit_desc=limit_desc,
                        approach_pct=approach_pct,
                        limit_min=safe_min,
                        limit_max=safe_max,
                    )
                )

        # Cap at 3 violations to prevent alarm fatigue
        return violations[:3]

    def _get_normal_band(self, point_name: str, equip_type: str, is_peak: bool) -> tuple | None:
        """Look up normal operating band for a point/equipment/time combination.

        Returns (min, max) tuple if a band exists, None otherwise.
        Tries equipment-specific band first, then _default.
        Tries peak/off_peak key first, then default.
        """
        point_bands = self.NORMAL_BANDS.get(point_name)
        if not point_bands:
            return None

        # Try equipment-specific first, then _default
        equip_bands = point_bands.get(equip_type) or point_bands.get("_default")
        if not equip_bands:
            return None

        # Try peak/off_peak key first, then default
        time_key = "peak" if is_peak else "off_peak"
        band = equip_bands.get(time_key) or equip_bands.get("default")
        return band

    def _get_safety_action(self, point_name: str, equip_type: str, severity: str) -> str:
        """Look up recommended action for a safety boundary alert.

        Returns action text string. Falls back to generic message.
        Checks equipment-specific key first, then _default.
        """
        point_actions = self.SAFETY_ACTIONS.get(point_name)
        if not point_actions:
            return f"Investigate {point_name} on this equipment."

        # Try equipment-specific first, then _default
        equip_actions = point_actions.get(equip_type) or point_actions.get("_default")
        if not equip_actions:
            return f"Investigate {point_name} on this equipment."

        return equip_actions.get(severity, f"Investigate {point_name} on this equipment.")
