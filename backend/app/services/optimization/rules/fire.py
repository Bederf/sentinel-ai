"""Fire optimization rules — panel communication loss, alarm correlation."""

from __future__ import annotations

from typing import Any

from app.services.optimization.rule import OptimizationRule


def _panel_comms_condition(t: dict[str, dict[str, Any]]) -> bool:
    fire = t.get("fire", {})
    status = fire.get("panel_online") or fire.get("communication_status")
    return status is not None


def _panel_comms_action(t: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    fire = t.get("fire", {})
    online = str(fire.get("panel_online", "") or fire.get("communication_status", ""))
    if online.lower() in ("false", "0", "offline", "lost"):
        return {
            "target_equipment": "Fire panel",
            "action": {"point": "inspection", "value": "comms_check"},
            "reason": "Fire panel communication lost — immediate inspection required.",
            "expected_impact": {"type": "safety", "component": "fire_panel_comms"},
            "confidence": 0.9,
            "profile": "asset_preservation",
            "priority": 10,
        }
    return None


RULES: list[OptimizationRule] = [
    OptimizationRule(
        module="fire",
        name="panel_communication_loss",
        condition=_panel_comms_condition,
        action=_panel_comms_action,
        description="Alert when fire panel communication is lost",
        profile="asset_preservation",
        priority=10,
    ),
]
