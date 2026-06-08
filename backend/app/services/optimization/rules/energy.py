"""Energy optimization rules — generator run-time, peak shaving, UPS health."""

from __future__ import annotations

from typing import Any

from app.services.optimization.rule import OptimizationRule


def _gen_run_time_condition(t: dict[str, dict[str, Any]]) -> bool:
    gen = t.get("energy", {}) or t.get("generator", {})
    fuel = gen.get("fuel_level_pct") or gen.get("gen_fuel")
    load = gen.get("load_pct") or gen.get("gen_kw")
    return fuel is not None and load is not None


def _gen_run_time_action(t: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    gen = t.get("energy", {}) or t.get("generator", {})
    fuel = float(gen.get("fuel_level_pct", 0) or gen.get("gen_fuel", 0) or 0)
    load = float(gen.get("load_pct", 0) or gen.get("gen_kw", 0) or 0)
    solar = t.get("solar", {})
    pv = float(solar.get("pv_power_kw", 0) or 0)
    bess = float(solar.get("bess_soc", 0) or 0)
    if fuel < 30:
        return {
            "target_equipment": "Generator",
            "action": {"point": "gen_run", "value": "stop"},
            "reason": (
                f"Generator fuel at {fuel}% at {load}% load. "
                f"{'Solar generating ' + str(pv) + ' kW and BESS at ' + str(bess) + '% — consider transferring load.' if pv > 0 or bess > 20 else ''}"
            ),
            "expected_impact": {"type": "fuel_conservation"},
            "confidence": 0.75,
            "profile": "asset_preservation",
            "priority": 7,
        }
    return None


def _peak_shave_condition(t: dict[str, dict[str, Any]]) -> bool:
    hvac = t.get("hvac", {})
    total = float(hvac.get("total_kw", 0) or hvac.get("hvac_kw", 0) or 0)
    solar = t.get("solar", {})
    grid = float(solar.get("grid_import_kw", 0) or 0)
    return total > 50 and grid > 0


def _peak_shave_action(t: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    hvac_t = t.get("hvac", {})
    total = float(hvac_t.get("total_kw", 0) or hvac_t.get("hvac_kw", 0) or 0)
    solar = t.get("solar", {})
    bess = float(solar.get("bess_soc", 0) or 0)
    if bess > 30:
        return {
            "target_equipment": "BESS",
            "action": {"point": "bess_discharge", "value": "peak_shave"},
            "reason": (
                f"Total load {total:.1f} kW — BESS at {bess:.0f}% available for peak shaving. "
                f"Discharge during peak tariff period to reduce demand charges."
            ),
            "expected_impact": {"type": "demand_reduction", "kw_target": round(total * 0.2, 1)},
            "confidence": 0.7,
            "profile": "cost_saving",
            "priority": 6,
        }
    return None


def _ups_health_condition(t: dict[str, dict[str, Any]]) -> bool:
    ups = t.get("energy", {}) or t.get("ups", {})
    battery = ups.get("battery_pct") or ups.get("ups_battery")
    return battery is not None and float(battery) < 70


def _ups_health_action(t: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    ups = t.get("energy", {}) or t.get("ups", {})
    battery = float(ups.get("battery_pct", 0) or ups.get("ups_battery", 0) or 0)
    return {
        "target_equipment": "UPS",
        "action": {"point": "inspection", "value": "schedule"},
        "reason": f"UPS battery at {battery:.0f}% — below 70% health threshold. Schedule replacement before next outage.",
        "expected_impact": {"type": "maintenance", "component": "battery"},
        "confidence": 0.85,
        "profile": "asset_preservation",
        "priority": 5,
    }


def _pf_correction_condition(t: dict[str, dict[str, Any]]) -> bool:
    energy = t.get("energy", {})
    pf = energy.get("pf") or energy.get("power_factor")
    return pf is not None and float(pf) < 0.90


def _pf_correction_action(t: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    energy = t.get("energy", {})
    pf = float(energy.get("pf", 0) or energy.get("power_factor", 0) or 0)
    return {
        "target_equipment": "PFC bank",
        "action": {"point": "pf_target", "value": 0.95},
        "reason": f"Power factor at {pf:.2f} — below 0.90 threshold. Engage PFC to avoid utility penalties.",
        "expected_impact": {"type": "cost_saving", "component": "pf_penalty"},
        "confidence": 0.72,
        "profile": "cost_saving",
        "priority": 4,
    }


RULES: list[OptimizationRule] = [
    OptimizationRule(
        module="energy",
        name="generator_run_time",
        condition=_gen_run_time_condition,
        action=_gen_run_time_action,
        description="Monitor generator fuel and load — recommend stop when solar/BESS can carry load",
        profile="asset_preservation",
        priority=7,
    ),
    OptimizationRule(
        module="energy",
        name="peak_shave",
        condition=_peak_shave_condition,
        action=_peak_shave_action,
        description="Discharge BESS during peak load to reduce demand charges",
        profile="cost_saving",
        priority=6,
    ),
    OptimizationRule(
        module="energy",
        name="ups_health",
        condition=_ups_health_condition,
        action=_ups_health_action,
        description="Alert when UPS battery drops below 70%",
        profile="asset_preservation",
        priority=5,
    ),
    OptimizationRule(
        module="energy",
        name="pf_correction",
        condition=_pf_correction_condition,
        action=_pf_correction_action,
        description="Engage PFC when power factor drops below 0.90",
        profile="cost_saving",
        priority=4,
    ),
]
