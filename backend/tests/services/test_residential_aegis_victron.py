from __future__ import annotations

from datetime import UTC, datetime

import app.services.residential.residential_aegis as aegis
from app.adapters.residential.schemas import EnergySnapshot


def _snap(**overrides) -> EnergySnapshot:
    base = dict(
        site_id="site-test",
        device_id="dev-001",
        timestamp=datetime.now(UTC),
        pv_power_w=3000.0,
        battery_soc_pct=75.0,
        battery_power_w=0.0,
        grid_power_w=100.0,
        load_power_w=3100.0,
        grid_voltage_v=231.0,
        battery_soh_pct=None,
        source_system="victron",
    )
    base.update(overrides)
    return EnergySnapshot(**base)


def _eval(snap: EnergySnapshot, **kwargs):
    return aegis.evaluate(
        snapshot=snap,
        area_schedule=None,
        recent_snapshots=[],
        alarms=[],
        platform_name="Victron VRM",
        **kwargs,
    )


def _rule_ids(results) -> list[str]:
    return [r.rule_id for r in results]


# ── RES_BATTERY_DEGRADED ──────────────────────────────────────────────────────

def test_battery_degraded_fires_below_70_pct():
    snap = _snap(battery_soh_pct=69.0)
    results = _eval(snap)
    assert "RES_BATTERY_DEGRADED" in _rule_ids(results)


def test_battery_degraded_fires_at_exactly_69():
    snap = _snap(battery_soh_pct=69.9)
    assert "RES_BATTERY_DEGRADED" in _rule_ids(_eval(snap))


def test_battery_degraded_silent_at_70_pct():
    snap = _snap(battery_soh_pct=70.0)
    assert "RES_BATTERY_DEGRADED" not in _rule_ids(_eval(snap))


def test_battery_degraded_silent_at_71_pct():
    snap = _snap(battery_soh_pct=71.0)
    assert "RES_BATTERY_DEGRADED" not in _rule_ids(_eval(snap))


def test_battery_degraded_silent_when_soh_none():
    snap = _snap(battery_soh_pct=None)
    assert "RES_BATTERY_DEGRADED" not in _rule_ids(_eval(snap))


def test_battery_degraded_has_p2_severity():
    snap = _snap(battery_soh_pct=50.0)
    results = _eval(snap)
    degraded = next(r for r in results if r.rule_id == "RES_BATTERY_DEGRADED")
    assert degraded.severity == "P2"


def test_battery_degraded_message_includes_soh_value():
    snap = _snap(battery_soh_pct=55.0)
    results = _eval(snap)
    degraded = next(r for r in results if r.rule_id == "RES_BATTERY_DEGRADED")
    assert "55" in degraded.message


# ── RES_INPUT_VOLTAGE_LOW (Victron-specific) ──────────────────────────────────

def test_input_voltage_low_fires_below_195v():
    snap = _snap(grid_voltage_v=194.0)
    assert "RES_INPUT_VOLTAGE_LOW" in _rule_ids(_eval(snap))


def test_input_voltage_low_fires_at_exactly_194():
    snap = _snap(grid_voltage_v=194.9)
    assert "RES_INPUT_VOLTAGE_LOW" in _rule_ids(_eval(snap))


def test_input_voltage_low_silent_at_195v():
    snap = _snap(grid_voltage_v=195.0)
    assert "RES_INPUT_VOLTAGE_LOW" not in _rule_ids(_eval(snap))


def test_input_voltage_low_silent_at_196v():
    snap = _snap(grid_voltage_v=196.0)
    assert "RES_INPUT_VOLTAGE_LOW" not in _rule_ids(_eval(snap))


def test_input_voltage_low_has_p1_severity():
    snap = _snap(grid_voltage_v=190.0)
    results = _eval(snap)
    rule = next(r for r in results if r.rule_id == "RES_INPUT_VOLTAGE_LOW")
    assert rule.severity == "P1"


def test_input_voltage_low_silent_when_voltage_none():
    snap = _snap(grid_voltage_v=None)
    assert "RES_INPUT_VOLTAGE_LOW" not in _rule_ids(_eval(snap))


def test_input_voltage_low_silent_when_voltage_zero():
    """0V is not a real reading — skip (grid absent, not dangerously low)."""
    snap = _snap(grid_voltage_v=0.0)
    assert "RES_INPUT_VOLTAGE_LOW" not in _rule_ids(_eval(snap))


# ── Platform scoping: Victron rules must NOT fire for solarman ────────────────

def test_battery_degraded_does_not_fire_for_solarman():
    snap = _snap(battery_soh_pct=50.0, source_system="solarman")
    assert "RES_BATTERY_DEGRADED" not in _rule_ids(_eval(snap))


def test_input_voltage_low_does_not_fire_for_solarman():
    snap = _snap(grid_voltage_v=180.0, source_system="solarman")
    assert "RES_INPUT_VOLTAGE_LOW" not in _rule_ids(_eval(snap))


def test_battery_degraded_does_not_fire_for_growatt():
    snap = _snap(battery_soh_pct=30.0, source_system="growatt")
    assert "RES_BATTERY_DEGRADED" not in _rule_ids(_eval(snap))


# ── Existing generic rules still fire for Victron snapshots ───────────────────

def test_battery_critical_low_still_fires_for_victron():
    snap = _snap(battery_soc_pct=8.0, source_system="victron")
    assert "RES_BATTERY_CRITICAL_LOW" in _rule_ids(_eval(snap))


def test_grid_voltage_anomaly_still_fires_for_victron():
    """Generic rule covers 210–250V range; Victron-specific covers < 195V separately."""
    snap = _snap(grid_voltage_v=255.0, source_system="victron")
    assert "RES_GRID_VOLTAGE_ANOMALY" in _rule_ids(_eval(snap))


# ── Existing generic rules still fire for solarman (no regression) ───────────

def test_battery_critical_low_fires_for_solarman():
    snap = _snap(battery_soc_pct=5.0, source_system="solarman")
    assert "RES_BATTERY_CRITICAL_LOW" in _rule_ids(_eval(snap))


def test_battery_critical_low_silent_above_threshold_solarman():
    snap = _snap(battery_soc_pct=50.0, source_system="solarman")
    assert "RES_BATTERY_CRITICAL_LOW" not in _rule_ids(_eval(snap))
