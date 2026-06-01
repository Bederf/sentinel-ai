from __future__ import annotations

from datetime import UTC, datetime

from app.adapters.residential.schemas import EnergySnapshot
from app.services.residential.residential_aegis import evaluate


def _snap(**kwargs):
    defaults = dict(
        site_id="res-123",
        device_id="dev-1",
        timestamp=datetime.now(UTC),
        pv_power_w=2000.0,
        battery_soc_pct=80.0,
        battery_power_w=500.0,
        grid_power_w=0.0,
        load_power_w=1500.0,
        grid_voltage_v=230.0,
        battery_soh_pct=None,
        source_system="home_assistant",
    )
    defaults.update(kwargs)
    return EnergySnapshot(**defaults)


class TestDeyePylontechRules:
    def test_inverter_mismatch_fires_when_one_below_40pct(self):
        s = _snap(pv_powers=[2000.0, 700.0])
        res = evaluate(s, None, [], [], "Home Assistant")
        assert any(r.rule_id == "RES_INVERTER_MISMATCH" for r in res)

    def test_battery_overtemp_p1(self):
        s = _snap(battery_temp_c=46.0)
        res = evaluate(s, None, [], [], "Home Assistant")
        assert any(r.rule_id == "RES_BATTERY_OVERTEMP" and r.severity == "P1" for r in res)

    def test_battery_soh_low_p2(self):
        s = _snap(battery_soh_pct=69.0)
        res = evaluate(s, None, [], [], "Home Assistant")
        assert any(r.rule_id == "RES_BATTERY_SOH_LOW" and r.severity == "P2" for r in res)
