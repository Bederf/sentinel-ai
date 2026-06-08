"""HVAC optimization rules — free cooling, load shed, setpoint tuning."""

from __future__ import annotations

from typing import Any

from app.services.optimization.rule import OptimizationRule


def _free_cooling_condition(t: dict[str, dict[str, Any]]) -> bool:
    hvac = t.get("hvac", {})
    outdoor = hvac.get("outdoor_temp") or hvac.get("oat_celsius")
    indoor = hvac.get("indoor_temp") or hvac.get("zone_temp")
    if outdoor is None or indoor is None:
        return False
    diff = abs(float(outdoor) - float(indoor))
    return diff <= 5.0


def _free_cooling_action(t: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    hvac = t.get("hvac", {})
    outdoor = float(hvac.get("outdoor_temp", 0) or hvac.get("oat_celsius", 0))
    indoor = float(hvac.get("indoor_temp", 0) or hvac.get("zone_temp", 0))
    solar = t.get("solar", {})
    pv_power = solar.get("pv_power_kw", 0) or 0
    occupancy = t.get("site_aggregate", {}).get("total_occupancy", 0) or 0
    occupancy_note = f", occupancy {occupancy}" if occupancy else ""
    solar_note = f", solar generating {pv_power} kW" if pv_power and float(pv_power) > 5 else ""
    return {
        "target_equipment": "AHU supply",
        "action": {"point": "supply_setpoint", "value": 18.0},
        "reason": (
            f"Free cooling opportunity — outdoor {outdoor}°C within {abs(outdoor - indoor):.1f}°C "
            f"of indoor {indoor}°C.{solar_note}{occupancy_note}"
        ),
        "expected_impact": {"type": "energy_savings", "kwh_estimate": "variable"},
        "confidence": 0.74,
        "profile": "cost_saving",
        "priority": 4,
    }


def _load_shed_condition(t: dict[str, dict[str, Any]]) -> bool:
    hvac = t.get("hvac", {})
    total = float(hvac.get("total_kw", 0) or hvac.get("hvac_kw", 0) or 0)
    solar = t.get("solar", {})
    gen = t.get("energy", {})
    on_generator = gen.get("ats_position") == "generator" or solar.get("grid_import_kw", 1) == 0
    return total > 0 and (on_generator or float(solar.get("grid_import_kw", 0) or 0) < 5)


def _load_shed_action(t: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    hvac = t.get("hvac", {})
    total = float(hvac.get("total_kw", 0) or hvac.get("hvac_kw", 0) or 0)
    return {
        "target_equipment": "Chiller plant",
        "action": {"point": "chws_setpoint", "value": 8.0},
        "reason": (
            f"Load shed opportunity — HVAC drawing {total:.1f} kW while on backup power. "
            f"Increase CHWS setpoint by 2°C to reduce load."
        ),
        "expected_impact": {"type": "load_reduction", "kw_reduction": round(total * 0.15, 1)},
        "confidence": 0.7,
        "profile": "asset_preservation",
        "priority": 6,
    }


def _setpoint_tuning_condition(t: dict[str, dict[str, Any]]) -> bool:
    hvac = t.get("hvac", {})
    indoor = hvac.get("indoor_temp") or hvac.get("zone_temp")
    outdoor = hvac.get("outdoor_temp") or hvac.get("oat_celsius")
    return indoor is not None and outdoor is not None


def _setpoint_tuning_action(t: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    hvac = t.get("hvac", {})
    indoor = float(hvac.get("indoor_temp", 0) or hvac.get("zone_temp", 0))
    outdoor = float(hvac.get("outdoor_temp", 0) or hvac.get("oat_celsius", 0))
    solar = t.get("solar", {})
    pv = float(solar.get("pv_power_kw", 0) or 0)
    target = 23.0 if outdoor > 28 else (21.0 if outdoor < 10 else None)
    if target is None:
        return None
    return {
        "target_equipment": "FCU zone setpoint",
        "action": {"point": "zone_setpoint", "value": target},
        "reason": (
            f"Outdoor {outdoor}°C, indoor {indoor}°C — adjust setpoint to {target}°C. "
            f"{'Solar generating ' + str(pv) + ' kW — excess available.' if pv > 5 else ''}"
        ),
        "expected_impact": {"type": "comfort_optimization", "setpoint_adjustment": target},
        "confidence": 0.65,
        "profile": "balanced",
        "priority": 5,
    }


def _hvac_staging_condition(t: dict[str, dict[str, Any]]) -> bool:
    hvac = t.get("hvac", {})
    cooling_load = float(hvac.get("chiller_kw", 0) or 0)
    return cooling_load < 30 and cooling_load > 0


def _hvac_staging_action(t: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    return {
        "target_equipment": "Chiller plant",
        "action": {"point": "chiller_staging", "value": "reduce"},
        "reason": "Cooling load is low — consider shedding one chiller to reduce energy consumption.",
        "expected_impact": {"type": "energy_savings", "kwh_estimate": "~5% of chiller power"},
        "confidence": 0.65,
        "profile": "cost_saving",
        "priority": 5,
    }


RULES: list[OptimizationRule] = [
    OptimizationRule(
        module="hvac",
        name="free_cooling",
        condition=_free_cooling_condition,
        action=_free_cooling_action,
        description="Enable economizer when outdoor air is within 5°C of indoor setpoint",
        profile="cost_saving",
        priority=4,
    ),
    OptimizationRule(
        module="hvac",
        name="load_shed",
        condition=_load_shed_condition,
        action=_load_shed_action,
        description="Reduce HVAC load when on backup power or grid import is low",
        profile="asset_preservation",
        priority=6,
    ),
    OptimizationRule(
        module="hvac",
        name="setpoint_tuning",
        condition=_setpoint_tuning_condition,
        action=_setpoint_tuning_action,
        description="Adjust zone setpoints based on outdoor temperature",
        profile="balanced",
        priority=5,
    ),
    OptimizationRule(
        module="hvac",
        name="chiller_staging",
        condition=_hvac_staging_condition,
        action=_hvac_staging_action,
        description="Reduce chiller count when cooling load is low",
        profile="cost_saving",
        priority=5,
    ),
]
