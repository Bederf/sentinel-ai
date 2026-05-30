from __future__ import annotations

from datetime import datetime

import pytest

from app.adapters.residential.base import ResidentialEnergyAdapter
from app.adapters.residential.schemas import AlarmEvent, DeviceManifest, EnergySnapshot


class _ConcreteAdapter(ResidentialEnergyAdapter):
    async def authenticate(self) -> bool:
        return True

    async def discover_devices(self) -> list[DeviceManifest]:
        return []

    async def get_realtime(self, device_id: str) -> EnergySnapshot:
        return EnergySnapshot(
            site_id="site-test",
            device_id=device_id,
            timestamp=datetime.utcnow(),
            pv_power_w=1000.0,
            battery_soc_pct=80.0,
            battery_power_w=None,
            grid_power_w=0.0,
            load_power_w=900.0,
            grid_voltage_v=230.0,
            source_system="solarman",
        )

    async def get_historical(self, device_id, start, end):
        return []

    async def get_alarms(self, device_id):
        return []


def test_concrete_adapter_is_subclass():
    assert issubclass(_ConcreteAdapter, ResidentialEnergyAdapter)


@pytest.mark.asyncio
async def test_authenticate_returns_true():
    adapter = _ConcreteAdapter()
    assert await adapter.authenticate() is True


@pytest.mark.asyncio
async def test_get_realtime_returns_snapshot():
    adapter = _ConcreteAdapter()
    snap = await adapter.get_realtime("dev-001")
    assert snap.device_id == "dev-001"
    assert snap.pv_power_w == 1000.0
    assert snap.battery_power_w is None
    assert snap.source_system == "solarman"


def test_energy_snapshot_fields():
    snap = EnergySnapshot(
        site_id="s",
        device_id="d",
        timestamp=datetime.utcnow(),
        pv_power_w=500.0,
        battery_soc_pct=None,
        battery_power_w=None,
        grid_power_w=None,
        load_power_w=None,
        grid_voltage_v=None,
        source_system="victron",
    )
    assert snap.pv_power_w == 500.0
    assert snap.battery_soc_pct is None


def test_device_manifest_default_capabilities():
    m = DeviceManifest(
        device_id="d",
        device_name="Inverter 1",
        device_type="inverter",
        source_system="solarman",
    )
    assert m.capabilities == []


def test_alarm_event_defaults():
    alarm = AlarmEvent(
        device_id="d",
        alarm_code="E001",
        alarm_message="Grid fault",
        severity="error",
        timestamp=datetime.utcnow(),
    )
    assert alarm.is_active is True
