"""Tests for HA-specific AEGIS rules in residential_aegis."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.adapters.residential.schemas import EnergySnapshot
from app.services.residential.residential_aegis import evaluate


def _snapshot(source_system="home_assistant", **kwargs):
    defaults = dict(
        site_id="res-123",
        device_id="test-device",
        timestamp=datetime.now(UTC),
        pv_power_w=2000.0,
        battery_soc_pct=50.0,
        battery_power_w=500.0,
        grid_power_w=0.0,
        load_power_w=1500.0,
        grid_voltage_v=230.0,
        geyser_power_w=1500.0,
        geyser_state="off",
        ev_charger_power_w=None,
    )
    defaults.update(kwargs)
    return EnergySnapshot(source_system=source_system, **defaults)


def _area_schedule(stage=2, minutes_to_next=30):
    """Mock area schedule with correct next_slot_start."""

    class MockArea:
        def __init__(self, stage, minutes):
            self.stage = stage
            self.next_slot_start = datetime.now(UTC) + timedelta(minutes=minutes)

    return MockArea(stage, minutes_to_next)


class TestGeyserOnPreShed:
    def test_fires_when_geyser_on_and_shed_imminent(self):
        snap = _snapshot(
            geyser_state="on",
            geyser_power_w=1500.0,
            battery_soc_pct=50.0,
        )
        results = evaluate(
            snap,
            area_schedule=_area_schedule(stage=2, minutes_to_next=30),
            recent_snapshots=[],
            alarms=[],
            platform_name="Home Assistant",
            polling_interval_seconds=300,
        )
        assert "RES_GEYSER_ON_PRE_SHED" in [r.rule_id for r in results]

    def test_does_not_fire_when_geyser_off(self):
        snap = _snapshot(geyser_state="off")
        results = evaluate(
            snap,
            area_schedule=_area_schedule(stage=2, minutes_to_next=30),
            recent_snapshots=[],
            alarms=[],
            platform_name="Home Assistant",
            polling_interval_seconds=300,
        )
        assert "RES_GEYSER_ON_PRE_SHED" not in [r.rule_id for r in results]

    def test_does_not_fire_when_soc_above_threshold(self):
        snap = _snapshot(geyser_state="on", battery_soc_pct=75.0)
        results = evaluate(
            snap,
            area_schedule=_area_schedule(stage=2, minutes_to_next=30),
            recent_snapshots=[],
            alarms=[],
            platform_name="Home Assistant",
            polling_interval_seconds=300,
        )
        assert "RES_GEYSER_ON_PRE_SHED" not in [r.rule_id for r in results]

    def test_does_not_fire_for_solarman(self):
        """HA-specific rules must not fire for SOLARMAN."""
        snap = _snapshot(source_system="solarman", geyser_state="on")
        results = evaluate(
            snap,
            area_schedule=_area_schedule(stage=2, minutes_to_next=30),
            recent_snapshots=[],
            alarms=[],
            platform_name="SOLARMAN",
            polling_interval_seconds=300,
        )
        assert "RES_GEYSER_ON_PRE_SHED" not in [r.rule_id for r in results]


class TestEVChargerBatteryDrain:
    def test_fires_when_ev_draining_battery_during_outage(self):
        snap = _snapshot(
            ev_charger_power_w=7000.0,
            grid_power_w=0.0,
            battery_soc_pct=30.0,
        )
        results = evaluate(snap, None, [], [], "Home Assistant", 300)
        assert "RES_EV_CHARGER_BATTERY_DRAIN" in [r.rule_id for r in results]

    def test_does_not_fire_when_grid_present(self):
        snap = _snapshot(
            ev_charger_power_w=7000.0,
            grid_power_w=100.0,
            battery_soc_pct=30.0,
        )
        results = evaluate(snap, None, [], [], "Home Assistant", 300)
        assert "RES_EV_CHARGER_BATTERY_DRAIN" not in [r.rule_id for r in results]

    def test_does_not_fire_for_victron(self):
        snap = _snapshot(source_system="victron", ev_charger_power_w=7000.0, grid_power_w=0.0)
        results = evaluate(snap, None, [], [], "Victron", 300)
        assert "RES_EV_CHARGER_BATTERY_DRAIN" not in [r.rule_id for r in results]


class TestSolarSurplusGeyser:
    def test_fires_at_high_surplus_and_high_soc(self):
        snap = _snapshot(
            geyser_state="off",
            pv_power_w=4000.0,
            load_power_w=1500.0,
            battery_soc_pct=90.0,
        )
        prev = _snapshot(
            geyser_state="off",
            pv_power_w=2000.0,
            load_power_w=1500.0,
            battery_soc_pct=85.0,
        )
        results = evaluate(snap, None, [prev], [], "Home Assistant", 300)
        assert "RES_SOLAR_SURPLUS_GEYSER" in [r.rule_id for r in results]

    def test_does_not_fire_when_geyser_already_on(self):
        snap = _snapshot(geyser_state="on", pv_power_w=4000.0, load_power_w=1500.0)
        results = evaluate(snap, None, [], [], "Home Assistant", 300)
        assert "RES_SOLAR_SURPLUS_GEYSER" not in [r.rule_id for r in results]
