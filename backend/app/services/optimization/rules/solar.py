"""Solar/BESS optimization rules — arbitrage, self-consumption, curtailment."""

from __future__ import annotations

from typing import Any

from app.services.optimization.rule import OptimizationRule


def _bess_arbitrage_condition(t: dict[str, dict[str, Any]]) -> bool:
    solar = t.get("solar", {})
    soc = solar.get("bess_soc") or solar.get("bess_soc_pct")
    grid = solar.get("grid_import_kw") or solar.get("import_kwh")
    return soc is not None and grid is not None


def _bess_arbitrage_action(t: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    solar = t.get("solar", {})
    soc = float(solar.get("bess_soc", 0) or solar.get("bess_soc_pct", 0) or 0)
    pv = float(solar.get("pv_power_kw", 0) or 0)
    grid = float(solar.get("grid_import_kw", 0) or solar.get("import_kwh", 0) or 0)
    hvac = t.get("hvac", {})
    load = float(hvac.get("total_kw", 0) or hvac.get("hvac_kw", 0) or 0)

    if soc > 80 and pv > 0:
        return {
            "target_equipment": "BESS",
            "action": {"point": "bess_mode", "value": "discharge"},
            "reason": (
                f"BESS at {soc:.0f}% SOC with PV generating {pv:.1f} kW "
                f"and building load {load:.1f} kW. Discharge into peak tariff window."
            ),
            "expected_impact": {"type": "tariff_arbitrage", "soc": soc, "pv_kw": pv},
            "confidence": 0.78,
            "profile": "cost_saving",
            "priority": 6,
        }
    if soc < 30 and grid > 0 and pv < 5:
        return {
            "target_equipment": "BESS",
            "action": {"point": "bess_mode", "value": "charge"},
            "reason": f"BESS at {soc:.0f}% — charge during off-peak to prepare for next peak window.",
            "expected_impact": {"type": "tariff_arbitrage", "soc": soc},
            "confidence": 0.75,
            "profile": "cost_saving",
            "priority": 5,
        }
    return None


def _self_consume_condition(t: dict[str, dict[str, Any]]) -> bool:
    solar = t.get("solar", {})
    pv = solar.get("pv_power_kw") or solar.get("inv_ac_output_power_kw")
    grid = solar.get("grid_import_kw") or solar.get("import_kwh")
    return pv is not None and grid is not None


def _self_consume_action(t: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    solar = t.get("solar", {})
    pv = float(solar.get("pv_power_kw", 0) or solar.get("inv_ac_output_power_kw", 0) or 0)
    grid = float(solar.get("grid_import_kw", 0) or solar.get("import_kwh", 0) or 0)
    if pv > 10 and grid > 5:
        return {
            "target_equipment": "Inverter",
            "action": {"point": "export_limit", "value": "maximize"},
            "reason": (
                f"Solar generating {pv:.1f} kW while importing {grid:.1f} kW from grid. "
                f"Increase self-consumption by shifting non-critical loads to solar hours."
            ),
            "expected_impact": {"type": "self_consumption", "pv_kw": pv, "grid_kw": grid},
            "confidence": 0.68,
            "profile": "cost_saving",
            "priority": 4,
        }
    return None


RULES: list[OptimizationRule] = [
    OptimizationRule(
        module="solar",
        name="bess_arbitrage",
        condition=_bess_arbitrage_condition,
        action=_bess_arbitrage_action,
        description="Charge BESS in off-peak, discharge during peak tariff windows",
        profile="cost_saving",
        priority=6,
    ),
    OptimizationRule(
        module="solar",
        name="self_consumption",
        condition=_self_consume_condition,
        action=_self_consume_action,
        description="Maximize on-site solar consumption when exporting",
        profile="cost_saving",
        priority=4,
    ),
]
