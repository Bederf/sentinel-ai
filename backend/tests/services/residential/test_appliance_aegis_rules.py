from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.adapters.residential.schemas import EnergySnapshot
from app.services.residential.residential_aegis import _in_time_window, evaluate


def _tuya_snap(**kwargs) -> EnergySnapshot:
    defaults = {
        "site_id": "res-123",
        "device_id": "aircon-1",
        "timestamp": datetime.now(UTC),
        "pv_power_w": None,
        "battery_soc_pct": None,
        "battery_power_w": None,
        "grid_power_w": None,
        "load_power_w": None,
        "grid_voltage_v": None,
        "source_system": "tuya",
        "appliance_power_state": "on",
        "appliance_runtime_minutes": 7 * 60,
    }
    defaults.update(kwargs)
    return EnergySnapshot(**defaults)


def _solar_snap(**kwargs) -> EnergySnapshot:
    defaults = {
        "site_id": "res-123",
        "device_id": "inv-1",
        "timestamp": datetime.now(UTC),
        "pv_power_w": 2000,
        "battery_soc_pct": 5,
        "battery_power_w": 100,
        "grid_power_w": 0,
        "load_power_w": 1500,
        "grid_voltage_v": 230,
        "source_system": "solarman",
    }
    defaults.update(kwargs)
    return EnergySnapshot(**defaults)


def test_runaway_rule_defaults_enabled_for_tuya():
    results = evaluate(_tuya_snap(), None, [], [], "Tuya")
    assert any(r.rule_id == "RES_APPLIANCE_RUNAWAY" for r in results)


def test_runaway_rule_respects_disabled_alert_config():
    results = evaluate(_tuya_snap(), None, [], [], "Tuya", alert_config={"runaway_enabled": False})
    assert not any(r.rule_id == "RES_APPLIANCE_RUNAWAY" for r in results)


def test_cost_limit_rule_math():
    results = evaluate(
        _tuya_snap(appliance_runtime_minutes=4 * 60),
        None,
        [],
        [],
        "Tuya",
        alert_config={
            "cost_limit_enabled": True,
            "appliance_kw_rating": 2.0,
            "tariff_zar_per_kwh": 4.0,
            "cost_limit_zar": 20,
        },
    )
    match = [r for r in results if r.rule_id == "RES_APPLIANCE_COST_LIMIT"]
    assert match
    assert "R32" in match[0].message


def test_overnight_window_wraparound_helper():
    assert _in_time_window("23:30", "22:00", "06:00") is True
    assert _in_time_window("05:30", "22:00", "06:00") is True
    assert _in_time_window("12:00", "22:00", "06:00") is False


def test_existing_rules_default_enabled_with_empty_alert_config():
    results = evaluate(_solar_snap(), None, [], [], "SOLARMAN", alert_config={})
    assert any(r.rule_id == "RES_BATTERY_CRITICAL_LOW" for r in results)


def test_existing_rules_default_enabled_with_none_alert_config():
    results = evaluate(_solar_snap(), None, [], [], "SOLARMAN", alert_config=None)
    assert any(r.rule_id == "RES_BATTERY_CRITICAL_LOW" for r in results)


def test_existing_rule_can_be_disabled_by_alert_config():
    results = evaluate(_solar_snap(), None, [], [], "SOLARMAN", alert_config={"battery_critical_enabled": False})
    assert not any(r.rule_id == "RES_BATTERY_CRITICAL_LOW" for r in results)


def test_data_stale_rule_can_be_disabled_without_affecting_other_rules():
    snap = _solar_snap(timestamp=datetime.now(UTC) - timedelta(minutes=30))
    results = evaluate(snap, None, [], [], "SOLARMAN", alert_config={"data_stale_enabled": False})
    ids = [r.rule_id for r in results]
    assert "RES_DATA_STALE" not in ids
    assert "RES_BATTERY_CRITICAL_LOW" in ids
