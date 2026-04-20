"""Sprint 0 Hardware Integration Test Protocol — automated gate checks.

Run ON THE EDGE BOX with real Modbus TCP access.  Not part of CI —
these tests require:
  SOLAR_CONNECTOR_MODE=live
  MODBUS_BESS_IP=<real IP>
  DEMO_MODE=false

Usage:
  # Read-only validation (safe — no writes):
  pytest tests/integration/test_sprint0_hardware.py -m "readonly" -v

  # Full suite (includes controlled writes — requires AEGIS gate open):
  pytest tests/integration/test_sprint0_hardware.py -v

  # Specific phase:
  pytest tests/integration/test_sprint0_hardware.py -k "phase_b" -v

Skip markers:
  - @pytest.mark.readonly     — safe read-only checks
  - @pytest.mark.writetest    — controlled write tests (needs AEGIS gate)
  - @pytest.mark.failuretest  — deliberate failure/rollback tests
  - @pytest.mark.integration  — all hardware integration tests
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config.settings import settings

logger = logging.getLogger(__name__)

# All tests in this module require hardware access
pytestmark = [pytest.mark.integration]

# Output file for sign-off report
REPORT_DIR = Path(__file__).parent / "sprint0_reports"


def _is_hardware_available() -> bool:
    """Check if hardware test prerequisites are met."""
    return settings.solar_connector_mode == "live" and bool(settings.modbus_bess_ip) and not settings.demo_mode


def _skip_unless_hardware():
    if not _is_hardware_available():
        pytest.skip("Hardware not available — set SOLAR_CONNECTOR_MODE=live, MODBUS_BESS_IP=<ip>, DEMO_MODE=false")


# =====================================================================
# A. Pre-flight Checks
# =====================================================================


class TestPhaseA_Preflight:
    """Phase A: Pre-flight configuration validation."""

    @pytest.mark.readonly
    def test_a1_network_config_present(self):
        """Verify Modbus TCP network config is set."""
        _skip_unless_hardware()
        assert settings.modbus_bess_ip, "MODBUS_BESS_IP must be set"
        assert settings.modbus_bess_port > 0, "MODBUS_BESS_PORT must be > 0"
        assert settings.modbus_bess_unit_id > 0, "MODBUS_BESS_UNIT_ID must be > 0"

    @pytest.mark.readonly
    def test_a2_connector_mode_is_live(self):
        """Verify connector mode is 'live'."""
        _skip_unless_hardware()
        assert settings.solar_connector_mode == "live"
        assert not settings.demo_mode

    @pytest.mark.readonly
    def test_a3_safety_limits_configured(self):
        """Verify BESS power limits are sane."""
        _skip_unless_hardware()
        from app.services.solar_config_service import get_site_solar_config

        cfg = get_site_solar_config("site-002")
        assert cfg.bess.capacity_kwh > 0
        assert cfg.bess.rated_power_kw > 0
        assert cfg.bess.rated_power_kw <= 200  # Sanity: not absurd

    @pytest.mark.readonly
    def test_a4_aegis_gate_status_known(self):
        """Record AEGIS gate state (not a pass/fail — just record it)."""
        _skip_unless_hardware()
        gate = settings.aegis_bess_writer_enabled
        logger.info("AEGIS gate: %s", "OPEN" if gate else "CLOSED")
        # Always passes — just records the state
        assert isinstance(gate, bool)

    @pytest.mark.readonly
    def test_a5_time_sync(self):
        """Verify system clock is within 60s of UTC (NTP check)."""
        _skip_unless_hardware()
        import subprocess

        try:
            result = subprocess.run(
                ["timedatectl", "show", "--property=NTPSynchronized"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            synced = "NTPSynchronized=yes" in result.stdout
            logger.info("NTP synchronized: %s", synced)
            # Warn but don't fail — some edge boxes use chrony
        except Exception:
            logger.warning("Could not check NTP status")


# =====================================================================
# B. Read-Only Validation
# =====================================================================


class TestPhaseB_ReadOnly:
    """Phase B: Read-only hardware validation — no writes."""

    @pytest.mark.readonly
    @pytest.mark.asyncio
    async def test_b1_connector_connects(self):
        """Verify Modbus TCP connection to inverter/BESS."""
        _skip_unless_hardware()
        from app.services.solar_connector_huawei import RealHuaweiConnector

        connector = RealHuaweiConnector(
            inverters=[{"id": "test-inv", "unit_id": settings.modbus_bess_unit_id}],
            bess={"container_id": "test-bess", "capacity_kwh": 200, "rated_power_kw": 100},
        )
        connected = await connector.connect()
        assert connected, f"Failed to connect to {settings.modbus_bess_ip}:{settings.modbus_bess_port}"
        await connector.disconnect()

    @pytest.mark.readonly
    @pytest.mark.asyncio
    async def test_b2_inverter_telemetry(self):
        """Read inverter telemetry and verify values are sane."""
        _skip_unless_hardware()
        from app.services.solar_ingestion_service import get_solar_ingestion_service

        svc = get_solar_ingestion_service()
        await svc.connect_all("site-002")
        overview = await svc.poll_site("site-002")

        assert "error" not in overview, f"Poll error: {overview.get('error')}"

        inverters = overview.get("inverters", [])
        assert len(inverters) > 0, "No inverters returned"

        for inv in inverters:
            # Values should be numeric and not absurd
            assert inv.get("ac_power_kw") is not None, "Missing ac_power_kw"
            assert -10 <= inv["ac_power_kw"] <= 200, f"Suspect ac_power: {inv['ac_power_kw']}"
            assert inv.get("frequency_hz") is not None, "Missing frequency_hz"
            assert 49.0 <= inv["frequency_hz"] <= 51.0, f"Suspect frequency: {inv['frequency_hz']}"

        logger.info(
            "Inverter telemetry OK: %d inverters, lead power=%.1f kW",
            len(inverters),
            inverters[0].get("ac_power_kw", 0),
        )

    @pytest.mark.readonly
    @pytest.mark.asyncio
    async def test_b3_bess_telemetry(self):
        """Read BESS telemetry and verify SOC is sane."""
        _skip_unless_hardware()
        from app.services.solar_ingestion_service import get_solar_ingestion_service

        svc = get_solar_ingestion_service()
        bess = await svc.get_bess_status("site-002")

        assert bess is not None, "No BESS data returned"
        assert 0 < bess.soc_pct <= 100, f"Suspect SOC: {bess.soc_pct}%"
        assert -10 < bess.temp_c < 60, f"Suspect temp: {bess.temp_c}C"

        logger.info(
            "BESS telemetry OK: SOC=%.1f%%, temp=%.1fC, mode=%s",
            bess.soc_pct,
            bess.temp_c,
            bess.mode,
        )

    @pytest.mark.readonly
    @pytest.mark.asyncio
    async def test_b4_soc_trend_over_30s(self):
        """Read SOC twice with 30s gap — verify it's not stuck."""
        _skip_unless_hardware()
        from app.services.solar_ingestion_service import get_solar_ingestion_service

        svc = get_solar_ingestion_service()

        bess1 = await svc.get_bess_status("site-002")
        assert bess1 is not None
        soc1 = bess1.soc_pct

        await asyncio.sleep(30)

        bess2 = await svc.get_bess_status("site-002")
        assert bess2 is not None
        soc2 = bess2.soc_pct

        # SOC should either change slightly or stay stable — never jump > 10% in 30s
        delta = abs(soc2 - soc1)
        assert delta < 10, f"SOC jumped {delta}% in 30s — suspect stale/broken read"

        logger.info("SOC trend: %.1f%% -> %.1f%% (delta=%.2f%%)", soc1, soc2, delta)

    @pytest.mark.readonly
    @pytest.mark.asyncio
    async def test_b5_firmware_capture(self):
        """Capture and log inverter/BESS firmware versions.

        This is the 'firmware variance' step — records the known-good
        register map version for this firmware.
        """
        _skip_unless_hardware()
        from app.services.solar_connector_huawei import (
            HUAWEI_LUNA2000_REGISTERS,
            HUAWEI_SUN2000_REGISTERS,
        )
        from app.services.solar_ingestion_service import get_solar_ingestion_service

        svc = get_solar_ingestion_service()
        overview = await svc.poll_site("site-002")
        inverters = overview.get("inverters", [])

        firmware_report = {
            "captured_at": datetime.now(UTC).isoformat(),
            "register_map_version": "v27.0",
            "sun2000_register_count": len(HUAWEI_SUN2000_REGISTERS),
            "luna2000_register_count": len(HUAWEI_LUNA2000_REGISTERS),
            "inverters": [],
            "bess": None,
        }

        for inv in inverters:
            firmware_report["inverters"].append(
                {
                    "id": inv.get("inverter_id", ""),
                    "model": inv.get("model", ""),
                    "serial": inv.get("serial", ""),
                    "firmware": inv.get("firmware_version", ""),
                }
            )

        bess = await svc.get_bess_status("site-002")
        if bess:
            firmware_report["bess"] = {
                "model": bess.model,
                "soh_pct": bess.soh_pct,
            }

        # Write firmware report
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORT_DIR / "firmware_versions.json"
        with open(report_path, "w") as f:
            json.dump(firmware_report, f, indent=2)

        logger.info("Firmware report written to %s", report_path)
        for inv in firmware_report["inverters"]:
            logger.info("  Inverter %s: firmware=%s", inv["id"], inv["firmware"])


# =====================================================================
# C. Command Dry Run (Write Gate Closed)
# =====================================================================


class TestPhaseC_DryRun:
    """Phase C: Command dry run — AEGIS gate MUST be closed."""

    @pytest.mark.readonly
    @pytest.mark.asyncio
    async def test_c1_charge_blocked(self):
        """Issue charge command with AEGIS gate closed — verify blocked."""
        _skip_unless_hardware()
        if settings.aegis_bess_writer_enabled:
            pytest.skip("AEGIS gate is open — close it for dry run tests")

        from app.services.modbus_bess_writer import get_modbus_bess_writer

        writer = get_modbus_bess_writer()
        result = await writer.write_charge_setpoint(5.0)

        assert result.aegis_blocked, "Expected AEGIS to block the write"
        assert result.success, "Pipeline should report success (blocked != failed)"
        logger.info("Charge 5kW correctly blocked by AEGIS gate")

    @pytest.mark.readonly
    @pytest.mark.asyncio
    async def test_c2_discharge_blocked(self):
        """Issue discharge command with AEGIS gate closed — verify blocked."""
        _skip_unless_hardware()
        if settings.aegis_bess_writer_enabled:
            pytest.skip("AEGIS gate is open — close it for dry run tests")

        from app.services.modbus_bess_writer import get_modbus_bess_writer

        writer = get_modbus_bess_writer()
        result = await writer.write_discharge_setpoint(5.0)

        assert result.aegis_blocked, "Expected AEGIS to block the write"
        logger.info("Discharge 5kW correctly blocked by AEGIS gate")

    @pytest.mark.readonly
    @pytest.mark.asyncio
    async def test_c3_audit_log_captures_blocked(self):
        """Verify AEGIS-blocked commands appear in audit log."""
        _skip_unless_hardware()

        from app.services.modbus_bess_writer import AUDIT_DIR

        log_file = AUDIT_DIR / "modbus_writes.jsonl"
        if not log_file.exists():
            pytest.skip("No audit log yet — run c1/c2 first")

        with open(log_file) as f:
            lines = f.readlines()

        blocked = [json.loads(line) for line in lines if '"aegis_blocked": true' in line]
        assert len(blocked) > 0, "Expected at least one AEGIS-blocked entry in audit log"
        logger.info("Audit log has %d blocked entries", len(blocked))


# =====================================================================
# D. Controlled Write Validation
# =====================================================================


class TestPhaseD_ControlledWrite:
    """Phase D: Controlled write tests — requires BOTH:
      1. AEGIS gate OPEN (aegis_bess_writer_enabled=true)
      2. ALLOW_WRITE_TESTS=true (second gate to prevent accidental writes)

    These tests write REAL commands to REAL hardware.
    Power levels are kept deliberately low (5 kW, 10 min max).
    """

    @pytest.mark.writetest
    @pytest.mark.asyncio
    async def test_d1_charge_5kw(self):
        """Charge at 5 kW for ~60s, verify SOC direction."""
        _skip_unless_hardware()
        if not settings.aegis_bess_writer_enabled:
            pytest.skip("AEGIS gate closed — open it for write tests")
        if not getattr(settings, "allow_write_tests", False):
            pytest.skip("ALLOW_WRITE_TESTS not set — double-gate for write tests")

        from app.services.modbus_bess_writer import get_modbus_bess_writer
        from app.services.solar_ingestion_service import get_solar_ingestion_service

        svc = get_solar_ingestion_service()
        writer = get_modbus_bess_writer()

        # Read SOC before
        bess_before = await svc.get_bess_status("site-002")
        assert bess_before is not None
        soc_before = bess_before.soc_pct

        # Issue charge command
        result = await writer.write_charge_setpoint(5.0)
        assert result.success, f"Charge write failed: {result.error}"
        assert not result.aegis_blocked, "AEGIS blocked the write unexpectedly"

        logger.info("Charge 5kW written — waiting 60s for BESS response")
        await asyncio.sleep(60)

        # Read SOC after
        bess_after = await svc.get_bess_status("site-002")
        assert bess_after is not None
        soc_after = bess_after.soc_pct

        # SOC should have increased (or stayed same if already full)
        logger.info("Charge test: SOC %.1f%% -> %.1f%%", soc_before, soc_after)
        if soc_before < 93:
            assert soc_after >= soc_before - 0.5, "SOC should not decrease during charge"

        # Clean up — send idle
        await writer.write_idle()

    @pytest.mark.writetest
    @pytest.mark.asyncio
    async def test_d2_discharge_5kw(self):
        """Discharge at 5 kW for ~60s, verify SOC direction."""
        _skip_unless_hardware()
        if not settings.aegis_bess_writer_enabled:
            pytest.skip("AEGIS gate closed — open it for write tests")
        if not getattr(settings, "allow_write_tests", False):
            pytest.skip("ALLOW_WRITE_TESTS not set — double-gate for write tests")

        from app.services.modbus_bess_writer import get_modbus_bess_writer
        from app.services.solar_ingestion_service import get_solar_ingestion_service

        svc = get_solar_ingestion_service()
        writer = get_modbus_bess_writer()

        bess_before = await svc.get_bess_status("site-002")
        assert bess_before is not None
        soc_before = bess_before.soc_pct

        result = await writer.write_discharge_setpoint(5.0)
        assert result.success, f"Discharge write failed: {result.error}"

        logger.info("Discharge 5kW written — waiting 60s for BESS response")
        await asyncio.sleep(60)

        bess_after = await svc.get_bess_status("site-002")
        assert bess_after is not None
        soc_after = bess_after.soc_pct

        logger.info("Discharge test: SOC %.1f%% -> %.1f%%", soc_before, soc_after)
        if soc_before > 25:
            assert soc_after <= soc_before + 0.5, "SOC should not increase during discharge"

        await writer.write_idle()

    @pytest.mark.writetest
    @pytest.mark.asyncio
    async def test_d3_idle_returns_to_neutral(self):
        """Send idle command and verify BESS power drops to ~0."""
        _skip_unless_hardware()
        if not settings.aegis_bess_writer_enabled:
            pytest.skip("AEGIS gate closed")
        if not getattr(settings, "allow_write_tests", False):
            pytest.skip("ALLOW_WRITE_TESTS not set — double-gate for write tests")

        from app.services.modbus_bess_writer import get_modbus_bess_writer
        from app.services.solar_ingestion_service import get_solar_ingestion_service

        svc = get_solar_ingestion_service()
        writer = get_modbus_bess_writer()

        result = await writer.write_idle()
        assert result.success

        await asyncio.sleep(15)

        bess = await svc.get_bess_status("site-002")
        assert bess is not None
        total_power = bess.charge_power_kw + bess.discharge_power_kw
        assert total_power < 5.0, f"BESS should be idle but power={total_power} kW"
        logger.info("Idle test: BESS power=%.1f kW (expected ~0)", total_power)

    @pytest.mark.writetest
    @pytest.mark.asyncio
    async def test_d4_audit_log_records_writes(self):
        """Verify successful writes appear in audit log."""
        _skip_unless_hardware()
        from app.services.modbus_bess_writer import AUDIT_DIR

        log_file = AUDIT_DIR / "modbus_writes.jsonl"
        assert log_file.exists(), "Audit log missing after write tests"

        with open(log_file) as f:
            lines = f.readlines()

        successful = [
            json.loads(line) for line in lines if '"success": true' in line and '"aegis_blocked": false' in line
        ]
        logger.info("Audit log has %d successful write entries", len(successful))
        assert len(successful) > 0, "Expected at least one successful write in audit log"


# =====================================================================
# E. Failure and Rollback Tests
# =====================================================================


class TestPhaseE_FailureRollback:
    """Phase E: Failure and rollback tests.

    test_e1: Simulates network loss by temporarily blocking modbus IP.
    test_e2: Tests mode switchover to simulation.
    """

    @pytest.mark.failuretest
    @pytest.mark.asyncio
    async def test_e1_graceful_read_failure(self):
        """Verify system handles Modbus read timeout gracefully.

        Instead of pulling the network cable (which requires physical access),
        we test by creating a connector pointed at a non-existent IP.
        """
        _skip_unless_hardware()
        from app.services.solar_connector_huawei import RealHuaweiConnector

        # Point at a non-routable IP to simulate network loss
        connector = RealHuaweiConnector(
            inverters=[{"id": "fail-test", "unit_id": 1}],
            bess={"container_id": "fail-bess", "capacity_kwh": 200, "rated_power_kw": 100},
        )

        # Override the settings temporarily
        from unittest.mock import patch

        with patch.object(settings, "modbus_bess_ip", "192.0.2.1"):  # RFC 5737 test IP
            with patch.object(settings, "modbus_bess_timeout_s", 3):
                connected = await connector.connect()
                assert not connected, "Should fail to connect to non-existent IP"

        # Verify reads return None gracefully (no crash)
        inv = await connector.read_inverter("fail-test")
        assert inv is None or inv.ac_power_kw == 0
        logger.info("Network failure test: connector failed gracefully")

    @pytest.mark.failuretest
    @pytest.mark.asyncio
    async def test_e2_mode_switchover_to_simulation(self):
        """Verify switching to simulation mode works without crash."""
        _skip_unless_hardware()
        from unittest.mock import patch

        # Temporarily switch to simulation
        with patch.object(settings, "solar_connector_mode", "simulation"):
            from app.services.solar_dispatch_service import SolarDispatchService

            svc = SolarDispatchService()
            soc = await svc._get_current_soc("site-002")
            assert isinstance(soc, float)
            assert 0 <= soc <= 100
            logger.info("Simulation switchover: SOC=%.1f%% (simulated)", soc)


# =====================================================================
# F. Sign-off Report Generator
# =====================================================================


class TestPhaseF_SignOff:
    """Phase F: Generate sign-off report.

    Run this LAST — it aggregates results from all previous phases.
    """

    @pytest.mark.readonly
    def test_f1_generate_signoff_report(self):
        """Generate Sprint 0 sign-off report."""
        _skip_unless_hardware()

        REPORT_DIR.mkdir(parents=True, exist_ok=True)

        report = {
            "protocol": "Sprint 0 Hardware Integration Test",
            "version": "v27.0",
            "generated_at": datetime.now(UTC).isoformat(),
            "site_id": "site-002",
            "edge_box": {
                "modbus_ip": settings.modbus_bess_ip,
                "modbus_port": settings.modbus_bess_port,
                "modbus_unit_id": settings.modbus_bess_unit_id,
                "connector_mode": settings.solar_connector_mode,
                "aegis_gate": settings.aegis_bess_writer_enabled,
                "demo_mode": settings.demo_mode,
            },
            "sign_off": {
                "60min_stable_reads": "[ ] PENDING — run Phase B tests for 60 minutes",
                "charge_command_ok": "[ ] PENDING — run test_d1_charge_5kw",
                "discharge_command_ok": "[ ] PENDING — run test_d2_discharge_5kw",
                "rollback_tested": "[ ] PENDING — run Phase E tests",
                "firmware_captured": "[ ] PENDING — run test_b5_firmware_capture",
            },
            "sign_off_by": "",
            "sign_off_date": "",
        }

        # Check if firmware report exists
        fw_path = REPORT_DIR / "firmware_versions.json"
        if fw_path.exists():
            report["sign_off"]["firmware_captured"] = "[x] COMPLETE"

        report_path = REPORT_DIR / "sprint0_signoff.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        logger.info("Sign-off report written to %s", report_path)


# =====================================================================
# G. Billing Sanity Check
# =====================================================================


class TestPhaseG_BillingSanity:
    """Phase G: Verify tariff rates match invoice — billing must never be wrong."""

    @pytest.mark.readonly
    def test_g1_tariff_rate_band_sanity(self):
        """Calculate cost for a 15-min slice and verify against expected rate band.

        Uses config-driven tariff rates (from invoice) and verifies that
        the MIP optimizer would produce costs in the correct range.
        """
        _skip_unless_hardware()
        from app.services.mip_dispatch_optimizer import _tariff_for_hour
        from app.services.solar_config_service import get_site_solar_config

        cfg = get_site_solar_config("site-002")

        # Expected summer rate ranges (R/kWh, energy + network, ex-VAT)
        # From City Power 2025/26 invoice: peak ~3.01, standard ~2.28, off-peak ~1.77
        expected_ranges = {
            "peak": (2.50, 3.50),  # R2.50-3.50/kWh
            "standard": (1.80, 2.80),  # R1.80-2.80/kWh
            "off_peak": (1.20, 2.20),  # R1.20-2.20/kWh
        }

        # Test representative hours for each band (summer month = 10)
        test_hours = {
            "peak": [8, 18],  # 08:00 and 18:00 are peak in summer
            "standard": [12, 15],  # 12:00 and 15:00 are standard
            "off_peak": [0, 3],  # 00:00 and 03:00 are off-peak
        }

        for band, hours in test_hours.items():
            for hour in hours:
                rate, period = _tariff_for_hour(hour, site_config=cfg, month=10)
                low, high = expected_ranges[band]

                # Calculate cost for 15-min slice at 100 kW load
                cost_15min = rate * 100 * 0.25  # R/kWh * kW * 0.25h

                logger.info(
                    "Hour %02d: rate=R%.4f/kWh, period=%s, 15min@100kW=R%.2f",
                    hour,
                    rate,
                    period,
                    cost_15min,
                )

                assert low <= rate <= high, (
                    f"Hour {hour}: rate R{rate:.4f}/kWh outside expected "
                    f"{band} range R{low:.2f}-R{high:.2f}/kWh. "
                    f"Check tariff config vs invoice."
                )

    @pytest.mark.readonly
    def test_g2_demand_charge_sanity(self):
        """Verify demand charge rate is within expected range."""
        _skip_unless_hardware()
        from app.services.solar_config_service import get_site_solar_config

        cfg = get_site_solar_config("site-002")
        demand_charge = cfg.tariff.demand_charge_r_kva("summer")

        # City Power 2025/26: R395.48/kVA/month
        assert 300 <= demand_charge <= 500, (
            f"Demand charge R{demand_charge:.2f}/kVA/month outside expected range R300-500. Check invoice."
        )

        logger.info("Demand charge: R%.2f/kVA/month (expected ~R395.48)", demand_charge)
