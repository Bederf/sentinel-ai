from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.residential.schemas import AlarmEvent, EnergySnapshot
from app.services.residential.eskomsepush_client import AreaSchedule
from app.services.residential.residential_aegis import evaluate


class TestResidentialAegisDispatchUsesResidentialTelegramSender:
    """Phase 214 — Verify AEGIS alerts dispatch via ResidentialTelegramSender, not commercial notifier."""

    def test_dispatch_results_uses_residential_telegram_sender(self):
        """dispatch_results must use ResidentialTelegramSender, not alert_notifier or TelegramMessageSender."""
        import inspect

        from app.services.residential import residential_aegis as aegis_mod

        source = inspect.getsource(aegis_mod)
        # Must reference ResidentialTelegramSender
        assert "ResidentialTelegramSender" in source
        # Must NOT use commercial alert notifier
        assert "alert_notifier" not in source.lower()
        assert "TelegramMessageSender" not in source

    @pytest.mark.asyncio
    async def test_dispatch_results_calls_residential_telegram_sender_send_alert(self):
        """dispatch_results must call ResidentialTelegramSender.send_alert for P1/P2 results."""
        from app.services.residential.residential_aegis import AEGISResult

        mock_result = AEGISResult(
            rule_id="RES_BATTERY_CRITICAL_LOW",
            severity="P1",
            message="Battery critical at 9%.",
            triggered=True,
        )

        with patch("app.services.residential.residential_aegis.get_supabase_client") as mock_sb:
            mock_client = MagicMock()
            # Build the chained call: table().select().eq().eq().maybe_execute()
            mock_result_obj = MagicMock()
            mock_result_obj.data = [{"chat_id": 12345}]
            mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_execute.return_value = mock_result_obj
            mock_sb.return_value = mock_client

            with patch("app.services.residential.residential_aegis.ResidentialTelegramSender") as mock_cls:
                mock_instance = MagicMock()
                mock_instance.send_alert = AsyncMock(return_value=True)
                mock_cls.return_value = mock_instance

                from app.services.residential.residential_aegis import dispatch_results
                await dispatch_results([mock_result], site_id="res-123", platform="SOLARMAN")

                mock_instance.send_alert.assert_called_once()
                call_kwargs = mock_instance.send_alert.call_args[1]
                assert call_kwargs["chat_id"] == 12345
                assert call_kwargs["severity"] == "P1"
                assert call_kwargs["platform"] == "SOLARMAN"

    @pytest.mark.asyncio
    async def test_dispatch_results_skips_when_no_chat_id(self):
        """dispatch_results must handle missing chat_id gracefully (wizard-onboarded, no Telegram)."""
        from app.services.residential.residential_aegis import AEGISResult

        mock_result = AEGISResult(
            rule_id="RES_BATTERY_CRITICAL_LOW",
            severity="P1",
            message="Battery critical.",
            triggered=True,
        )

        # Patch get_supabase_client so we control the full chain.
        # The problem: mock_client.table("x") creates a new MagicMock via __call__,
        # not via return_value. So we need a real-ish mock object.
        class FakeRow:
            data = [{"chat_id": None}]

        class FakeTable:
            def select(self, *args, **kwargs):
                class FakeSelect:
                    def eq(self, *args, **kwargs):
                        class FakeEq:
                            def maybe_execute(self):
                                return FakeRow()

                        return FakeEq()

                return FakeSelect()

        class FakeClient:
            def table(self, *args, **kwargs):
                return FakeTable()

        with patch("app.services.residential.residential_aegis.get_supabase_client") as mock_sb:
            mock_sb.return_value = FakeClient()

            with patch("app.services.residential.residential_aegis.logger") as mock_logger:
                from app.services.residential.residential_aegis import dispatch_results
                result = await dispatch_results([mock_result], site_id="res-123", platform="SOLARMAN")
                assert result is False
                # Warning must be logged for wizard-onboarded site with no Telegram
                mock_logger.warning.assert_called()
                warning_msg = mock_logger.warning.call_args[0][0]
                assert "wizard-onboarded" in warning_msg or "no active chat_id" in warning_msg

    @pytest.mark.asyncio
    async def test_dispatch_results_returns_false_when_send_alert_fails(self):
        """When send_alert returns False, dispatch_results must propagate failure."""
        from app.services.residential.residential_aegis import AEGISResult

        mock_result = AEGISResult(
            rule_id="RES_BATTERY_CRITICAL_LOW",
            severity="P1",
            message="Battery critical.",
            triggered=True,
        )

        with patch("app.services.residential.residential_aegis.get_supabase_client") as mock_sb:
            mock_client = MagicMock()
            mock_client.table.return_value.select.return_value.eq.return_value.maybe_execute.return_value = MagicMock(
                data=[{"chat_id": 12345}]
            )
            mock_sb.return_value = mock_client

            with patch("app.services.residential.residential_aegis.ResidentialTelegramSender") as mock_cls:
                mock_instance = MagicMock()
                mock_instance.send_alert = AsyncMock(return_value=False)
                mock_cls.return_value = mock_instance

                from app.services.residential.residential_aegis import dispatch_results
                result = await dispatch_results([mock_result], site_id="res-123", platform="SOLARMAN")
                assert result is False

    @pytest.mark.asyncio
    async def test_dispatch_results_ignores_non_p1_p2_severity(self):
        """dispatch_results must skip results with severity other than P1 or P2."""
        from app.services.residential.residential_aegis import AEGISResult

        mock_result = AEGISResult(
            rule_id="RES_PV_FAULT_SUSPECTED",
            severity="P2",  # P2 — should be sent
            message="PV very low.",
            triggered=True,
        )

        with patch("app.services.residential.residential_aegis.get_supabase_client") as mock_sb:
            mock_client = MagicMock()
            mock_client.table.return_value.select.return_value.eq.return_value.maybe_execute.return_value = MagicMock(
                data=[{"chat_id": 12345}]
            )
            mock_sb.return_value = mock_client

            with patch("app.services.residential.residential_aegis.ResidentialTelegramSender") as mock_cls:
                mock_instance = MagicMock()
                mock_instance.send_alert = AsyncMock(return_value=True)
                mock_cls.return_value = mock_instance

                from app.services.residential.residential_aegis import dispatch_results
                result = await dispatch_results([mock_result], site_id="res-123", platform="SOLARMAN")
                assert result is True
                mock_instance.send_alert.assert_called_once()


def _snap(**kwargs) -> EnergySnapshot:
    defaults = {
        "site_id": "site-test",
        "device_id": "dev-001",
        "timestamp": datetime.now(UTC),
        "pv_power_w": 2000.0,
        "battery_soc_pct": 80.0,
        "battery_power_w": 500.0,
        "grid_power_w": 0.0,
        "load_power_w": 1800.0,
        "grid_voltage_v": 230.0,
        "source_system": "solarman",
    }
    defaults.update(kwargs)
    return EnergySnapshot(**defaults)


def _schedule(stage=0, minutes_ahead=180) -> AreaSchedule:
    next_slot = datetime.now(UTC) + timedelta(minutes=minutes_ahead)
    return AreaSchedule(
        area_id="sandton-2",
        stage=stage,
        next_slot_start=next_slot,
        next_slot_end=next_slot + timedelta(hours=2),
        fetched_at=datetime.utcnow(),
    )


# ── Rule: RES_BATTERY_CRITICAL_LOW ────────────────────────────────────────────


def test_battery_critical_fires_at_9_pct():
    snap = _snap(battery_soc_pct=9.0)
    results = evaluate(snap, None, [], [], "SOLARMAN")
    ids = [r.rule_id for r in results]
    assert "RES_BATTERY_CRITICAL_LOW" in ids


def test_battery_critical_does_not_fire_at_11_pct():
    snap = _snap(battery_soc_pct=11.0)
    results = evaluate(snap, None, [], [], "SOLARMAN")
    ids = [r.rule_id for r in results]
    assert "RES_BATTERY_CRITICAL_LOW" not in ids


def test_battery_critical_severity_is_p1():
    snap = _snap(battery_soc_pct=5.0)
    results = evaluate(snap, None, [], [], "SOLARMAN")
    matched = [r for r in results if r.rule_id == "RES_BATTERY_CRITICAL_LOW"]
    assert matched and matched[0].severity == "P1"


def test_battery_critical_message_names_platform():
    snap = _snap(battery_soc_pct=5.0)
    results = evaluate(snap, None, [], [], "Victron VRM")
    matched = [r for r in results if r.rule_id == "RES_BATTERY_CRITICAL_LOW"]
    assert matched and "Victron VRM" in matched[0].message


# ── Rule: RES_BATTERY_PRE_SHED_RISK ──────────────────────────────────────────


def test_pre_shed_risk_fires_soc_28_stage2_60min():
    snap = _snap(battery_soc_pct=28.0)
    schedule = _schedule(stage=2, minutes_ahead=60)
    results = evaluate(snap, schedule, [], [], "SOLARMAN")
    ids = [r.rule_id for r in results]
    assert "RES_BATTERY_PRE_SHED_RISK" in ids


def test_pre_shed_risk_does_not_fire_stage_0():
    snap = _snap(battery_soc_pct=20.0)
    schedule = _schedule(stage=0, minutes_ahead=60)
    results = evaluate(snap, schedule, [], [], "SOLARMAN")
    ids = [r.rule_id for r in results]
    assert "RES_BATTERY_PRE_SHED_RISK" not in ids


def test_pre_shed_risk_does_not_fire_beyond_120min():
    snap = _snap(battery_soc_pct=20.0)
    schedule = _schedule(stage=2, minutes_ahead=180)
    results = evaluate(snap, schedule, [], [], "SOLARMAN")
    ids = [r.rule_id for r in results]
    assert "RES_BATTERY_PRE_SHED_RISK" not in ids


def test_pre_shed_risk_does_not_fire_soc_high():
    snap = _snap(battery_soc_pct=80.0)
    schedule = _schedule(stage=3, minutes_ahead=30)
    results = evaluate(snap, schedule, [], [], "SOLARMAN")
    ids = [r.rule_id for r in results]
    assert "RES_BATTERY_PRE_SHED_RISK" not in ids


# ── Rule: RES_GRID_VOLTAGE_ANOMALY ────────────────────────────────────────────


def test_voltage_fires_at_209v():
    snap = _snap(grid_voltage_v=209.0)
    results = evaluate(snap, None, [], [], "SOLARMAN")
    assert any(r.rule_id == "RES_GRID_VOLTAGE_ANOMALY" for r in results)


def test_voltage_fires_at_251v():
    snap = _snap(grid_voltage_v=251.0)
    results = evaluate(snap, None, [], [], "SOLARMAN")
    assert any(r.rule_id == "RES_GRID_VOLTAGE_ANOMALY" for r in results)


def test_voltage_clean_at_230v():
    snap = _snap(grid_voltage_v=230.0)
    results = evaluate(snap, None, [], [], "SOLARMAN")
    assert not any(r.rule_id == "RES_GRID_VOLTAGE_ANOMALY" for r in results)


def test_voltage_clean_at_none():
    snap = _snap(grid_voltage_v=None)
    results = evaluate(snap, None, [], [], "SOLARMAN")
    assert not any(r.rule_id == "RES_GRID_VOLTAGE_ANOMALY" for r in results)


# ── Rule: RES_INVERTER_ALARM ──────────────────────────────────────────────────


def test_inverter_alarm_fires_on_fault():
    alarm = AlarmEvent("dev-001", "E001", "Grid fault detected", "fault", datetime.utcnow(), "solarman")
    results = evaluate(_snap(), None, [], [alarm], "SOLARMAN")
    assert any(r.rule_id == "RES_INVERTER_ALARM" and r.severity == "P1" for r in results)


def test_inverter_alarm_does_not_fire_on_warning():
    alarm = AlarmEvent("dev-001", "W001", "Fan speed low", "warning", datetime.utcnow(), "solarman")
    results = evaluate(_snap(), None, [], [alarm], "SOLARMAN")
    assert not any(r.rule_id == "RES_INVERTER_ALARM" for r in results)


# ── Rule: RES_DATA_STALE ──────────────────────────────────────────────────────


def test_data_stale_fires_beyond_2_5x_interval():
    old_snap = _snap(timestamp=datetime.now(UTC) - timedelta(seconds=800))
    results = evaluate(old_snap, None, [], [], "SOLARMAN", polling_interval_seconds=300)
    assert any(r.rule_id == "RES_DATA_STALE" for r in results)


def test_data_stale_does_not_fire_within_interval():
    fresh_snap = _snap(timestamp=datetime.now(UTC) - timedelta(seconds=200))
    results = evaluate(fresh_snap, None, [], [], "SOLARMAN", polling_interval_seconds=300)
    assert not any(r.rule_id == "RES_DATA_STALE" for r in results)


# ── Rule IDs are prefixed RES_ ───────────────────────────────────────────────


def test_all_rule_ids_prefixed_res():
    snap = _snap(
        battery_soc_pct=5.0,
        grid_voltage_v=200.0,
        timestamp=datetime.now(UTC) - timedelta(seconds=900),
    )
    alarm = AlarmEvent("d", "E1", "fault msg", "critical", datetime.utcnow(), "solarman")
    schedule = _schedule(stage=3, minutes_ahead=30)
    results = evaluate(snap, schedule, [], [alarm], "SOLARMAN", polling_interval_seconds=300)
    for r in results:
        assert r.rule_id.startswith("RES_"), f"Rule ID not prefixed: {r.rule_id}"
