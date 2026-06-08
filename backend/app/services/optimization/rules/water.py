"""Water optimization rules — leak detection, consumption anomaly, pressure."""

from __future__ import annotations

from typing import Any

from app.services.optimization.rule import OptimizationRule


def _flow_anomaly_condition(t: dict[str, dict[str, Any]]) -> bool:
    water = t.get("water", {})
    flow = water.get("flow_rate_lpm") or water.get("meter_flow_lpm")
    return flow is not None


def _flow_anomaly_action(t: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    water = t.get("water", {})
    flow = float(water.get("flow_rate_lpm", 0) or water.get("meter_flow_lpm", 0) or 0)
    occ = float(t.get("site_aggregate", {}).get("total_occupancy", 0) or 0)
    if flow > 50 and occ == 0:
        return {
            "target_equipment": "Water main",
            "action": {"point": "inspection", "value": "leak_check"},
            "reason": (
                f"Flow rate {flow:.1f} L/min with zero occupancy — possible leak. "
                f"Schedule inspection of water main and branch lines."
            ),
            "expected_impact": {"type": "leak_prevention", "flow_lpm": flow},
            "confidence": 0.72,
            "profile": "asset_preservation",
            "priority": 7,
        }
    return None


RULES: list[OptimizationRule] = [
    OptimizationRule(
        module="water",
        name="flow_anomaly",
        condition=_flow_anomaly_condition,
        action=_flow_anomaly_action,
        description="Detect continuous water flow during unoccupied periods (potential leak)",
        profile="asset_preservation",
        priority=7,
    ),
]
