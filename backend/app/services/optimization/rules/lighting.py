"""Lighting optimization rules — daylight harvesting, occupancy dimming, schedule."""

from __future__ import annotations

from typing import Any

from app.services.optimization.rule import OptimizationRule


def _daylight_harvest_condition(t: dict[str, dict[str, Any]]) -> bool:
    lighting = t.get("lighting", {})
    lux = lighting.get("lux_level") or lighting.get("luminaire_level")
    return lux is not None


def _daylight_harvest_action(t: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    lighting = t.get("lighting", {})
    lux = float(lighting.get("lux_level", 0) or lighting.get("luminaire_level", 0) or 0)
    power = float(lighting.get("power_consumption", 0) or lighting.get("luminaire_power_kw", 0) or 0)
    if lux > 500 and power > 0:
        return {
            "target_equipment": "DALI zone",
            "action": {"point": "dim_level", "value": "50%"},
            "reason": (
                f"Ambient light at {lux:.0f} lux — sufficient for occupied spaces. "
                f"Dim lighting to 50% to save {power:.2f} kW."
            ),
            "expected_impact": {"type": "energy_savings", "kw_reduction": round(power * 0.5, 2)},
            "confidence": 0.72,
            "profile": "cost_saving",
            "priority": 4,
        }
    return None


def _occupancy_dim_condition(t: dict[str, dict[str, Any]]) -> bool:
    lighting = t.get("lighting", {})
    occupancy = lighting.get("occupancy") or t.get("site_aggregate", {}).get("total_occupancy")
    return occupancy is not None


def _occupancy_dim_action(t: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    occ = float(t.get("lighting", {}).get("occupancy", 0) or t.get("site_aggregate", {}).get("total_occupancy", 0) or 0)
    power = float(t.get("lighting", {}).get("power_consumption", 0) or 0)
    if occ == 0 and power > 0:
        return {
            "target_equipment": "DALI zone",
            "action": {"point": "dim_level", "value": "10%"},
            "reason": "No occupancy detected — dim lighting to minimum. Saves energy in unoccupied spaces.",
            "expected_impact": {"type": "energy_savings", "kw_reduction": round(power * 0.9, 2)},
            "confidence": 0.8,
            "profile": "cost_saving",
            "priority": 5,
        }
    return None


RULES: list[OptimizationRule] = [
    OptimizationRule(
        module="lighting",
        name="daylight_harvesting",
        condition=_daylight_harvest_condition,
        action=_daylight_harvest_action,
        description="Dim luminaires when ambient daylight is sufficient",
        profile="cost_saving",
        priority=4,
    ),
    OptimizationRule(
        module="lighting",
        name="occupancy_based_dim",
        condition=_occupancy_dim_condition,
        action=_occupancy_dim_action,
        description="Dim or turn off lighting in unoccupied zones",
        profile="cost_saving",
        priority=5,
    ),
]
