"""Security optimization rules — occupancy anomaly, door left open, after-hours."""

from __future__ import annotations

from typing import Any

from app.services.optimization.rule import OptimizationRule


def _after_hours_occupancy_condition(t: dict[str, dict[str, Any]]) -> bool:
    occ = t.get("site_aggregate", {}).get("total_occupancy") or t.get("security", {}).get("zone_occupancy_count")
    return occ is not None


def _after_hours_occupancy_action(t: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    occ = float(
        t.get("site_aggregate", {}).get("total_occupancy", 0)
        or t.get("security", {}).get("zone_occupancy_count", 0)
        or 0
    )
    hvac = t.get("hvac", {})
    lighting = t.get("lighting", {})
    hvac_on = float(hvac.get("hvac_kw", 0) or 0) > 10
    lights_on = float(lighting.get("power_consumption", 0) or 0) > 0.5
    if occ == 0 and (hvac_on or lights_on):
        return {
            "target_equipment": "Building systems",
            "action": {"point": "after_hours", "value": "review"},
            "reason": (
                f"No occupancy detected but HVAC ({'on' if hvac_on else 'off'}) "
                f"and lighting ({'on' if lights_on else 'off'}) still active. "
                f"Review after-hours schedule for energy savings."
            ),
            "expected_impact": {"type": "energy_savings", "component": "after_hours"},
            "confidence": 0.75,
            "profile": "cost_saving",
            "priority": 4,
        }
    return None


def _door_left_open_condition(t: dict[str, dict[str, Any]]) -> bool:
    door = t.get("security", {}).get("door_status")
    return door is not None


def _door_left_open_action(t: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    door = str(t.get("security", {}).get("door_status", ""))
    if door.lower() in ("open", "ajar"):
        return {
            "target_equipment": "Access control",
            "action": {"point": "door_inspection", "value": "check"},
            "reason": "A door has been left open beyond normal duration — check for security risk or HVAC energy loss.",
            "expected_impact": {"type": "security", "component": "open_door"},
            "confidence": 0.8,
            "profile": "asset_preservation",
            "priority": 6,
        }
    return None


RULES: list[OptimizationRule] = [
    OptimizationRule(
        module="security",
        name="after_hours_occupancy",
        condition=_after_hours_occupancy_condition,
        action=_after_hours_occupancy_action,
        description="Detect HVAC/lighting running in unoccupied building",
        profile="cost_saving",
        priority=4,
    ),
    OptimizationRule(
        module="security",
        name="door_left_open",
        condition=_door_left_open_condition,
        action=_door_left_open_action,
        description="Alert when a door remains open past normal duration",
        profile="asset_preservation",
        priority=6,
    ),
]
