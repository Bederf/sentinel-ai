"""Tests for ModbusBESSWriter — Modbus TCP writer for Huawei LUNA2000.

All tests run with DEMO_MODE or mocked TCP — no real Modbus connections.
Covers: AEGIS gating, demo writes, register encoding, write verification,
        watchdog, audit logging, dispatch integration, edge cases.
"""

import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.services.modbus_bess_writer import (
    ModbusBESSWriter,
    WriteResult,
    REGISTER_CHARGE_POWER,
    REGISTER_DISCHARGE_POWER,
    REGISTER_SCALE,
    execute_dispatch_with_write,
)
from app.config.settings import settings
from app.services.bess_dispatch_engine import (
    BESSState,
    DispatchCommand,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _relax_sprint0_limits():
    """Relax Sprint 0 hard limits for unit tests (they test general behavior).

    Sprint 0 limits are tested separately in integration/test_sprint0_hardware.py.
    """
    original_power = settings.sprint0_max_power_kw
    original_dur = settings.sprint0_max_duration_min
    settings.sprint0_max_power_kw = 1000.0  # Effectively no limit for unit tests
    settings.sprint0_max_duration_min = 1440
    yield
    settings.sprint0_max_power_kw = original_power
    settings.sprint0_max_duration_min = original_dur


@pytest.fixture
def writer():
    """Create a fresh writer instance."""
    return ModbusBESSWriter()


@pytest.fixture
def bess_state():
    """Normal BESS operating state."""
    return BESSState(
        soc_pct=60.0,
        temperature_c=25.0,
        power_kw=0.0,
        grid_frequency_hz=50.0,
    )


@pytest.fixture
def successful_command():
    """A pre-validated successful DispatchCommand."""
    return DispatchCommand(
        site_id="site-002",
        timestamp=datetime.now(timezone.utc).isoformat(),
        action="discharge",
        requested_power_kw=50.0,
        actual_power_kw=50.0,
        duration_minutes=15,
        reason="peak_arbitrage",
        success=True,
    )


@pytest.fixture
def blocked_command():
    """A dispatch command blocked by constraints."""
    return DispatchCommand(
        site_id="site-002",
        timestamp=datetime.now(timezone.utc).isoformat(),
        action="discharge",
        requested_power_kw=50.0,
        actual_power_kw=0.0,
        duration_minutes=15,
        reason="peak_arbitrage",
        success=False,
        error_message="Discharge blocked: SOC at minimum",
    )


# ---------------------------------------------------------------------------
# WriteResult tests
# ---------------------------------------------------------------------------


class TestWriteResult:
    """Test WriteResult dataclass."""

    def test_to_dict(self):
        result = WriteResult(
            success=True,
            register=37001,
            value_kw=50.5,
            register_value=50500,
            verified=True,
            timestamp="2026-02-24T10:00:00",
            write_latency_ms=12.345,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["register"] == 37001
        assert d["value_kw"] == 50.5
        assert d["register_value"] == 50500
        assert d["verified"] is True
        assert d["write_latency_ms"] == 12.35

    def test_to_dict_aegis_blocked(self):
        result = WriteResult(
            success=True,
            register=37001,
            value_kw=50.0,
            register_value=50000,
            aegis_blocked=True,
            timestamp="2026-02-24T10:00:00",
        )
        d = result.to_dict()
        assert d["aegis_blocked"] is True

    def test_to_dict_error(self):
        result = WriteResult(
            success=False,
            register=37001,
            value_kw=50.0,
            register_value=50000,
            error="Connection refused",
            timestamp="2026-02-24T10:00:00",
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["error"] == "Connection refused"


# ---------------------------------------------------------------------------
# AEGIS gate tests
# ---------------------------------------------------------------------------


class TestAegisGating:
    """Test AEGIS gate blocking behavior."""

    @pytest.mark.asyncio
    async def test_aegis_blocks_when_disabled(self, writer):
        """When aegis_bess_writer_enabled=False, writes are blocked."""
        with patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: False)):
            result = await writer.write_charge_setpoint(50.0)
            assert result.aegis_blocked is True
            assert result.success is True  # Pipeline succeeded, write was blocked

    @pytest.mark.asyncio
    async def test_aegis_blocked_has_register_info(self, writer):
        """Blocked writes still record register and value info."""
        with patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: False)):
            result = await writer.write_charge_setpoint(75.0)
            assert result.register == REGISTER_CHARGE_POWER
            assert result.value_kw == 75.0
            assert result.register_value == 75000

    @pytest.mark.asyncio
    async def test_aegis_blocked_discharge(self, writer):
        """Discharge writes are also blocked by AEGIS."""
        with patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: False)):
            result = await writer.write_discharge_setpoint(80.0)
            assert result.aegis_blocked is True
            assert result.register == REGISTER_DISCHARGE_POWER


# ---------------------------------------------------------------------------
# Demo mode tests
# ---------------------------------------------------------------------------


class TestDemoMode:
    """Test demo mode write behavior (no TCP, always succeeds)."""

    @pytest.mark.asyncio
    async def test_demo_write_succeeds(self, writer):
        """Demo mode writes succeed without TCP."""
        with (
            patch.object(type(writer), "_is_demo", new_callable=lambda: property(lambda self: True)),
            patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: True)),
        ):
            result = await writer.write_charge_setpoint(50.0)
            assert result.success is True
            assert result.demo_mode is True
            assert result.verified is True

    @pytest.mark.asyncio
    async def test_demo_discharge_succeeds(self, writer):
        """Demo discharge writes succeed."""
        with (
            patch.object(type(writer), "_is_demo", new_callable=lambda: property(lambda self: True)),
            patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: True)),
        ):
            result = await writer.write_discharge_setpoint(80.0)
            assert result.success is True
            assert result.register == REGISTER_DISCHARGE_POWER
            assert result.register_value == 80000

    @pytest.mark.asyncio
    async def test_demo_idle_succeeds(self, writer):
        """Demo idle writes succeed."""
        with (
            patch.object(type(writer), "_is_demo", new_callable=lambda: property(lambda self: True)),
            patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: True)),
        ):
            result = await writer.write_idle()
            assert result.success is True
            assert result.value_kw == 0.0

    @pytest.mark.asyncio
    async def test_demo_register_scaling(self, writer):
        """Register values are correctly scaled in demo mode."""
        with (
            patch.object(type(writer), "_is_demo", new_callable=lambda: property(lambda self: True)),
            patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: True)),
        ):
            result = await writer.write_charge_setpoint(100.0)
            assert result.register_value == 100000  # 100 kW * 1000


# ---------------------------------------------------------------------------
# Register encoding tests
# ---------------------------------------------------------------------------


class TestRegisterEncoding:
    """Test register address and value encoding."""

    def test_charge_register_address(self):
        assert REGISTER_CHARGE_POWER == 37001

    def test_discharge_register_address(self):
        assert REGISTER_DISCHARGE_POWER == 37003

    def test_register_scale_factor(self):
        assert REGISTER_SCALE == 1000

    def test_scaling_zero(self):
        assert int(0.0 * REGISTER_SCALE) == 0

    def test_scaling_fractional(self):
        assert int(50.5 * REGISTER_SCALE) == 50500

    def test_scaling_max_power(self):
        assert int(100.0 * REGISTER_SCALE) == 100000


# ---------------------------------------------------------------------------
# Dispatch command integration
# ---------------------------------------------------------------------------


class TestDispatchCommandExecution:
    """Test execute_dispatch_command with pre-validated commands."""

    @pytest.mark.asyncio
    async def test_successful_discharge_command(self, writer, successful_command):
        """Successful discharge command triggers write."""
        with patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: False)):
            result = await writer.execute_dispatch_command(successful_command)
            assert result.register == REGISTER_DISCHARGE_POWER
            assert result.value_kw == 50.0

    @pytest.mark.asyncio
    async def test_blocked_command_returns_failure(self, writer, blocked_command):
        """Blocked commands return failure without attempting write."""
        result = await writer.execute_dispatch_command(blocked_command)
        assert result.success is False
        assert "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_charge_command(self, writer):
        """Charge command writes to charge register."""
        command = DispatchCommand(
            site_id="site-002",
            timestamp=datetime.now(timezone.utc).isoformat(),
            action="charge",
            requested_power_kw=60.0,
            actual_power_kw=60.0,
            duration_minutes=15,
            reason="off_peak_charge",
            success=True,
        )
        with patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: False)):
            result = await writer.execute_dispatch_command(command)
            assert result.register == REGISTER_CHARGE_POWER
            assert result.value_kw == 60.0

    @pytest.mark.asyncio
    async def test_idle_command(self, writer):
        """Idle action writes zero to charge register."""
        command = DispatchCommand(
            site_id="site-002",
            timestamp=datetime.now(timezone.utc).isoformat(),
            action="idle",
            requested_power_kw=0.0,
            actual_power_kw=0.0,
            duration_minutes=15,
            reason="standard_idle",
            success=True,
        )
        with patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: False)):
            result = await writer.execute_dispatch_command(command)
            assert result.value_kw == 0.0


# ---------------------------------------------------------------------------
# Watchdog tests
# ---------------------------------------------------------------------------


class TestWatchdog:
    """Test watchdog timer behavior."""

    @pytest.mark.asyncio
    async def test_watchdog_no_trigger_initially(self, writer):
        """Watchdog doesn't trigger when no commands have been sent."""
        result = await writer.check_watchdog()
        assert result is None

    @pytest.mark.asyncio
    async def test_watchdog_no_trigger_recent(self, writer):
        """Watchdog doesn't trigger when last command was recent."""
        writer._last_command_time = time.monotonic()
        result = await writer.check_watchdog()
        assert result is None

    @pytest.mark.asyncio
    async def test_watchdog_triggers_on_timeout(self, writer):
        """Watchdog sends idle when timeout exceeded."""
        writer._last_command_time = time.monotonic() - 400  # 400s > 300s timeout
        with patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: False)):
            result = await writer.check_watchdog()
            assert result is not None
            assert result.value_kw == 0.0

    def test_watchdog_timeout_constant(self, writer):
        """Watchdog timeout is 5 minutes."""
        assert writer.WATCHDOG_TIMEOUT_S == 300


# ---------------------------------------------------------------------------
# Write history tests
# ---------------------------------------------------------------------------


class TestWriteHistory:
    """Test write history tracking."""

    @pytest.mark.asyncio
    async def test_history_recorded(self, writer):
        """Writes are recorded in history."""
        with patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: False)):
            await writer.write_charge_setpoint(50.0)
            history = writer.get_write_history()
            assert len(history) >= 1
            assert history[-1]["value_kw"] == 50.0

    @pytest.mark.asyncio
    async def test_history_limit(self, writer):
        """History respects limit parameter."""
        with patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: False)):
            for i in range(5):
                await writer.write_charge_setpoint(float(i * 10))
            history = writer.get_write_history(limit=3)
            assert len(history) == 3

    @pytest.mark.asyncio
    async def test_empty_history(self, writer):
        """Empty history returns empty list."""
        history = writer.get_write_history()
        assert history == []


# ---------------------------------------------------------------------------
# execute_dispatch_with_write integration
# ---------------------------------------------------------------------------


class TestExecuteDispatchWithWrite:
    """Test the unified dispatch + write function."""

    @pytest.mark.asyncio
    async def test_returns_both_results(self, bess_state):
        """Returns both dispatch_command and write_result."""
        result = await execute_dispatch_with_write(
            site_id="site-002",
            action="discharge",
            requested_power_kw=50.0,
            bess_state=bess_state,
        )
        assert "dispatch_command" in result
        assert "write_result" in result

    @pytest.mark.asyncio
    async def test_dispatch_command_populated(self, bess_state):
        """Dispatch command has expected fields."""
        result = await execute_dispatch_with_write(
            site_id="site-002",
            action="charge",
            requested_power_kw=60.0,
            bess_state=bess_state,
        )
        cmd = result["dispatch_command"]
        assert cmd["site_id"] == "site-002"
        assert cmd["action"] == "charge"

    @pytest.mark.asyncio
    async def test_write_result_populated(self, bess_state):
        """Write result has expected fields."""
        result = await execute_dispatch_with_write(
            site_id="site-002",
            action="discharge",
            requested_power_kw=50.0,
            bess_state=bess_state,
        )
        wr = result["write_result"]
        assert "success" in wr
        assert "register" in wr
        assert "timestamp" in wr


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test boundary and edge cases."""

    @pytest.mark.asyncio
    async def test_negative_power_normalized(self, writer):
        """Negative power values are normalized to absolute value."""
        with patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: False)):
            result = await writer.write_charge_setpoint(-50.0)
            assert result.value_kw == 50.0
            assert result.register_value == 50000

    @pytest.mark.asyncio
    async def test_zero_power(self, writer):
        """Zero power write succeeds."""
        with patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: False)):
            result = await writer.write_charge_setpoint(0.0)
            assert result.success is True
            assert result.register_value == 0

    @pytest.mark.asyncio
    async def test_max_power(self, writer):
        """Maximum power write uses correct register value."""
        with patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: False)):
            result = await writer.write_discharge_setpoint(100.0)
            assert result.register_value == 100000

    def test_is_demo_when_no_ip(self, writer):
        """Writer is in demo mode when modbus_bess_ip is empty."""
        with patch("app.services.modbus_bess_writer.settings") as mock_settings:
            mock_settings.demo_mode = False
            mock_settings.modbus_bess_ip = ""
            assert writer._is_demo is True

    def test_is_demo_when_demo_mode(self, writer):
        """Writer is in demo mode when DEMO_MODE=true."""
        with patch("app.services.modbus_bess_writer.settings") as mock_settings:
            mock_settings.demo_mode = True
            mock_settings.modbus_bess_ip = "192.168.1.100"
            assert writer._is_demo is True

    @pytest.mark.asyncio
    async def test_disconnect_safe_when_not_connected(self, writer):
        """Disconnect is safe when not connected."""
        await writer.disconnect()  # Should not raise
        assert writer._connected is False


# ---------------------------------------------------------------------------
# Sprint 0 hard limits
# ---------------------------------------------------------------------------


class TestSprint0HardLimits:
    """Test Sprint 0 safety hard limits enforced in code."""

    @pytest.mark.asyncio
    async def test_power_clamped_to_sprint0_limit(self, writer):
        """Power above sprint0_max_power_kw is clamped."""
        settings.sprint0_max_power_kw = 5.0  # Override the relaxed limit
        with patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: False)):
            result = await writer.write_charge_setpoint(50.0)
            assert result.value_kw == 5.0
            assert result.requested_kw == 50.0
            assert result.clamped_kw == 5.0

    @pytest.mark.asyncio
    async def test_power_below_limit_unchanged(self, writer):
        """Power below sprint0_max_power_kw passes through unchanged."""
        settings.sprint0_max_power_kw = 10.0
        with patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: False)):
            result = await writer.write_charge_setpoint(3.0)
            assert result.value_kw == 3.0
            assert result.requested_kw == 3.0
            assert result.clamped_kw == 3.0

    @pytest.mark.asyncio
    async def test_duration_clamped_in_dispatch(self):
        """Duration above sprint0_max_duration_min is clamped."""
        settings.sprint0_max_duration_min = 10
        bess = BESSState(soc_pct=60.0, temperature_c=25.0, power_kw=0.0, grid_frequency_hz=50.0)
        result = await execute_dispatch_with_write(
            site_id="site-002",
            action="charge",
            requested_power_kw=3.0,
            bess_state=bess,
            duration_minutes=60,
        )
        assert result["dispatch_command"]["duration_minutes"] == 10

    @pytest.mark.asyncio
    async def test_audit_fields_populated(self, writer):
        """Audit-friendly fields are populated on every write."""
        with patch.object(type(writer), "_aegis_enabled", new_callable=lambda: property(lambda self: False)):
            result = await writer.write_charge_setpoint(3.0)
            assert result.correlation_id  # Non-empty
            assert len(result.correlation_id) == 12
            assert result.who == "sentinel"
            assert result.reason  # Non-empty
            assert result.end_timestamp  # Non-empty
            assert result.timestamp  # Non-empty
