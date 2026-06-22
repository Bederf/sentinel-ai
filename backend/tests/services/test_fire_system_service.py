from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.module_registry import ModuleStatus, ModuleType
from app.services.fire_system_service import FireSystemService


class FakeFireRepo:
    def __init__(self):
        self.created_alarms = []
        self.logged_actions = []

    def get_zone(self, zone_id):
        return {"zone_id": zone_id, "zone_name": "Server Room"}

    def create_alarm(self, alarm_data):
        self.created_alarms.append(alarm_data)
        return alarm_data

    def log_action(self, action_data):
        self.logged_actions.append(action_data)
        return action_data


class FakeModuleRegistry:
    def __init__(self, active=True, config=None):
        self.active = active
        self.config = config or {}

    def is_module_active(self, site_id, module_type):
        assert module_type == ModuleType.FIRE
        return self.active

    def get_site_config(self, site_id):
        if not self.active:
            return None
        return SimpleNamespace(
            active_modules=[
                SimpleNamespace(
                    module_type=ModuleType.FIRE,
                    status=ModuleStatus.ACTIVE,
                    licensed=True,
                    config=self.config,
                )
            ]
        )


@pytest.mark.asyncio
async def test_fire_alarm_monitoring_only_when_auto_not_commissioned(monkeypatch):
    repo = FakeFireRepo()
    service = FireSystemService()
    service._repo = repo
    monkeypatch.setattr(service, "_notify_fire_alarm", AsyncMock(return_value={"sent": True}))

    monkeypatch.setattr(
        "app.services.module_registry_service.module_registry",
        FakeModuleRegistry(active=True, config={"auto_mode": False, "commissioned_cause_effect": False}),
    )
    coordinator = SimpleNamespace(execute_cause_effect=AsyncMock(), _mode="normal")
    monkeypatch.setattr("app.services.fire_hvac_coordinator.get_fire_hvac_coordinator", lambda: coordinator)

    result = await service.trigger_alarm("FZ-L1-C", "smoke", site_id="site-002")

    assert result["fire_control_gate"]["fire_module_active"] is True
    assert result["fire_control_gate"]["site_id"] == "site-002"
    assert result["fire_control_gate"]["control_allowed"] is False
    assert result["notification"]["sent"] is True
    assert result["cause_effect"]["skipped"] is True
    assert result["coordinator_mode"] == "monitoring_only"
    assert (
        result["authority"] == "fire_panel_and_bms" or result["fire_control_gate"]["authority"] == "fire_panel_and_bms"
    )
    coordinator.execute_cause_effect.assert_not_called()
    assert repo.logged_actions[-1]["action_type"] == "fire_alarm_monitoring_only"


@pytest.mark.asyncio
async def test_fire_alarm_executes_only_when_auto_and_commissioned(monkeypatch):
    repo = FakeFireRepo()
    service = FireSystemService()
    service._repo = repo
    monkeypatch.setattr(service, "_notify_fire_alarm", AsyncMock(return_value={"sent": True}))

    monkeypatch.setattr(
        "app.services.module_registry_service.module_registry",
        FakeModuleRegistry(active=True, config={"auto_mode": True, "commissioned_cause_effect": True}),
    )
    cause_effect = MagicMock()
    cause_effect.to_dict.return_value = {
        "triggered_effects": [{"target_id": "AHU-L1", "action": "shutdown"}],
        "devices_affected": 1,
        "execution_time_ms": 12.0,
        "any_failures": False,
        "failures": [],
    }
    coordinator = SimpleNamespace(execute_cause_effect=AsyncMock(return_value=cause_effect), _mode="fire_mode")
    monkeypatch.setattr("app.services.fire_hvac_coordinator.get_fire_hvac_coordinator", lambda: coordinator)

    result = await service.trigger_alarm("FZ-L1-C", "smoke", site_id="site-002")

    assert result["fire_control_gate"]["control_allowed"] is True
    assert result["notification"]["sent"] is True
    assert result["fire_control_gate"]["authority"] == "fire_panel_and_bms"
    assert result["authority"] == "fire_panel_and_bms"
    assert result["cause_effect"]["devices_affected"] == 1
    assert "fire panel/BMS remains authoritative" in result["operator_message"]
    coordinator.execute_cause_effect.assert_awaited_once_with("FZ-L1-C", "smoke")
