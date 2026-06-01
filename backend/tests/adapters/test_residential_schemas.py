from __future__ import annotations

from datetime import UTC, datetime

from app.adapters.residential.schemas import EnergySnapshot


def test_energy_snapshot_optional_fields_default_none():
    s = EnergySnapshot(
        site_id="res-1",
        device_id="dev-1",
        timestamp=datetime.now(UTC),
        pv_power_w=1000.0,
        battery_soc_pct=50.0,
        battery_power_w=200.0,
        grid_power_w=0.0,
        load_power_w=800.0,
        grid_voltage_v=230.0,
    )
    assert getattr(s, "battery_temp_c", None) is None
    assert getattr(s, "pv_powers", None) is None
