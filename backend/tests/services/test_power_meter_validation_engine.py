"""Unit tests for PowerMeterValidationEngine.

Tests cover:
    - Baseline calculation (3 tests)
    - Anomaly detection / variance (4 tests)
    - COP degradation analysis (3 tests)
    - Demo fallback (2 tests)
    - Daily validation (3 tests)

Total: 15 tests

All tests mock Supabase and test pure validation logic only.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.power_meter_validation_engine import (
    COP_ACCEPTABLE_RANGE,
    COP_CRITICAL_THRESHOLD,
    COP_WARNING_THRESHOLD,
    CRITICAL_VARIANCE_PCT,
    EXPECTED_CHILLER_COP,
    MINIMUM_READINGS_FOR_BASELINE,
    VARIANCE_THRESHOLD_PCT,
    PowerMeterValidationEngine,
    get_power_meter_validation_engine,
)

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def engine():
    """Create a PowerMeterValidationEngine with mocked Supabase client."""
    with patch("app.services.power_meter_validation_engine.get_supabase_client") as mock_sb:
        mock_client = MagicMock()
        mock_sb.return_value = mock_client
        eng = PowerMeterValidationEngine("site-002")
        return eng


@pytest.fixture
def mock_readings_sufficient():
    """Mock sufficient meter readings (>7 days) for baseline calculation."""
    return [{"energy_kwh": v} for v in [30.0, 28.5, 32.0, 25.0, 35.0, 27.0, 31.0, 29.0, 33.0, 26.0]]


@pytest.fixture
def mock_readings_insufficient():
    """Mock insufficient meter readings (<7 days) for baseline calculation."""
    return [{"energy_kwh": v} for v in [30.0, 28.5, 32.0]]


# ------------------------------------------------------------------
# 1. Baseline Calculation
# ------------------------------------------------------------------


class TestBaselineCalculation:
    """Verify baseline statistics from meter readings."""

    @pytest.mark.asyncio
    async def test_sufficient_readings_produces_baseline(self, engine, mock_readings_sufficient):
        """7+ readings produce mean, stdev, min, max, p95."""
        mock_response = MagicMock()
        mock_response.data = mock_readings_sufficient
        chain = engine.client.table.return_value.select.return_value
        chain.eq.return_value.gte.return_value.order.return_value.execute.return_value = mock_response

        baseline = await engine.get_power_baseline("S002-MTR-B1-HVAC")
        assert "mean_kw" in baseline
        assert "stdev_kw" in baseline
        assert "min_kw" in baseline
        assert "max_kw" in baseline
        assert "p95_kw" in baseline
        assert baseline["samples"] == 10

    @pytest.mark.asyncio
    async def test_insufficient_readings_returns_default(self, engine, mock_readings_insufficient):
        """Fewer than 7 readings returns default baseline."""
        mock_response = MagicMock()
        mock_response.data = mock_readings_insufficient
        chain = engine.client.table.return_value.select.return_value
        chain.eq.return_value.gte.return_value.order.return_value.execute.return_value = mock_response

        baseline = await engine.get_power_baseline("S002-MTR-B1-HVAC")
        # Should return default baseline (either from fixture or hardcoded)
        assert baseline["samples"] == 168  # Default lookback

    @pytest.mark.asyncio
    async def test_no_readings_returns_default(self, engine):
        """No readings at all returns default baseline."""
        mock_response = MagicMock()
        mock_response.data = []
        chain = engine.client.table.return_value.select.return_value
        chain.eq.return_value.gte.return_value.order.return_value.execute.return_value = mock_response

        baseline = await engine.get_power_baseline("S002-MTR-B1-HVAC")
        assert baseline["mean_kw"] > 0
        assert baseline["samples"] == 168


# ------------------------------------------------------------------
# 2. Anomaly Detection (Variance Analysis)
# ------------------------------------------------------------------


class TestAnomalyDetection:
    """Verify Z-score and variance-based anomaly detection."""

    @pytest.mark.asyncio
    async def test_normal_within_15_percent(self, engine):
        """Reading within 15% of real -> status 'normal'."""
        engine._baseline_cache["S002-MTR-B1-HVAC"] = {
            "mean_kw": 30.0,
            "stdev_kw": 5.0,
            "min_kw": 20.0,
            "max_kw": 40.0,
            "median_kw": 29.0,
            "p95_kw": 38.0,
            "samples": 168,
            "lookback_days": 7,
        }
        # Mock get_power_baseline to use cache
        engine.get_power_baseline = AsyncMock(return_value=engine._baseline_cache["S002-MTR-B1-HVAC"])

        result = await engine.validate_hourly_power(
            meter_id="S002-MTR-B1-HVAC",
            simulated_power_kw=31.0,
            real_power_kw=30.0,
            simulated_hour=10,
            simulated_date=datetime(2026, 1, 15, 10, 0),
        )
        assert result["validation_status"] == "normal"
        assert result["variance_pct"] < VARIANCE_THRESHOLD_PCT

    @pytest.mark.asyncio
    async def test_anomaly_between_15_and_25_percent(self, engine):
        """Reading 15-25% from real -> status 'anomaly'."""
        engine.get_power_baseline = AsyncMock(
            return_value={"mean_kw": 30.0, "stdev_kw": 5.0, "min_kw": 20.0, "max_kw": 40.0}
        )
        # Mock _write_validation_record to avoid DB call
        engine._write_validation_record = AsyncMock()

        result = await engine.validate_hourly_power(
            meter_id="S002-MTR-B1-HVAC",
            simulated_power_kw=36.0,
            real_power_kw=30.0,  # 20% variance
            simulated_hour=10,
            simulated_date=datetime(2026, 1, 15, 10, 0),
        )
        assert result["validation_status"] == "anomaly"
        assert result["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_critical_above_25_percent(self, engine):
        """Reading >25% from real -> status 'critical'."""
        engine.get_power_baseline = AsyncMock(
            return_value={"mean_kw": 30.0, "stdev_kw": 5.0, "min_kw": 20.0, "max_kw": 40.0}
        )
        engine._write_validation_record = AsyncMock()

        result = await engine.validate_hourly_power(
            meter_id="S002-MTR-B1-HVAC",
            simulated_power_kw=40.0,
            real_power_kw=30.0,  # 33% variance
            simulated_hour=10,
            simulated_date=datetime(2026, 1, 15, 10, 0),
        )
        assert result["validation_status"] == "critical"
        assert result["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_no_real_data_skips_validation(self, engine):
        """No real meter reading -> validation skipped."""
        result = await engine.validate_hourly_power(
            meter_id="S002-MTR-B1-HVAC",
            simulated_power_kw=30.0,
            real_power_kw=None,
            simulated_hour=10,
        )
        assert result["validation_status"] == "skipped"
        assert result["reason"] == "no_real_meter_data"


# ------------------------------------------------------------------
# 3. COP Degradation Analysis
# ------------------------------------------------------------------


class TestCOPDegradation:
    """Verify COP analysis and adjustment recommendations."""

    def test_cop_thresholds_configured_correctly(self):
        """Verify COP threshold constants."""
        assert EXPECTED_CHILLER_COP == 3.5
        assert COP_ACCEPTABLE_RANGE == (2.8, 4.2)
        assert COP_WARNING_THRESHOLD == 2.9
        assert COP_CRITICAL_THRESHOLD == 2.5

    @pytest.mark.asyncio
    async def test_healthy_cop_no_adjustment(self, engine):
        """COP within acceptable range -> no adjustment needed."""
        # Mock readings that produce COP of ~3.5 (45/12.86 = 3.5)
        readings = [{"energy_kwh": 12.86} for _ in range(10)]
        mock_response = MagicMock()
        mock_response.data = readings
        engine.client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = (
            mock_response
        )

        result = await engine.calculate_cop_adjustment("S002-MTR-B1-HVAC")
        assert result["status"] == "healthy"
        assert result["adjustment_needed"] is False

    @pytest.mark.asyncio
    async def test_degraded_cop_triggers_adjustment(self, engine):
        """COP below warning threshold -> adjustment recommended."""
        # Mock readings that produce COP ~2.5 (45/18 = 2.5)
        readings = [{"energy_kwh": 18.0} for _ in range(10)]
        mock_response = MagicMock()
        mock_response.data = readings
        engine.client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = (
            mock_response
        )

        result = await engine.calculate_cop_adjustment("S002-MTR-B1-HVAC")
        assert result["status"] == "degraded"
        assert result["adjustment_needed"] is True
        assert result["estimated_cop"] < COP_WARNING_THRESHOLD


# ------------------------------------------------------------------
# 4. Demo Fallback
# ------------------------------------------------------------------


class TestDemoFallback:
    """Verify fallback to demo fixtures and hardcoded defaults."""

    def test_hardcoded_default_baseline_values(self, engine):
        """When no demo file exists, hardcoded defaults are returned."""
        with patch("app.services.power_meter_validation_engine._DATA_DIR") as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            baseline = engine._get_default_baseline()
            assert baseline["mean_kw"] == 28.2
            assert baseline["stdev_kw"] == 8.5
            assert baseline["samples"] == 168

    def test_variance_threshold_constants(self):
        """Verify anomaly threshold constants."""
        assert VARIANCE_THRESHOLD_PCT == 15.0
        assert CRITICAL_VARIANCE_PCT == 25.0
        assert MINIMUM_READINGS_FOR_BASELINE == 7


# ------------------------------------------------------------------
# 5. Daily Validation
# ------------------------------------------------------------------


class TestDailyValidation:
    """Verify daily power validation aggregation."""

    @pytest.mark.asyncio
    async def test_empty_hourly_data_skipped(self, engine):
        """Empty hourly data -> validation skipped."""
        result = await engine.validate_daily_power(datetime(2026, 1, 15), {})
        assert result["validation_status"] == "skipped"
        assert result["reason"] == "no_hourly_data"

    @pytest.mark.asyncio
    async def test_normal_daily_power(self, engine):
        """Daily power within baseline -> status 'normal'."""
        # Mock baseline to match hourly data
        engine.get_power_baseline = AsyncMock(return_value={"mean_kw": 30.0, "stdev_kw": 5.0})
        hourly = dict.fromkeys(range(24), 30.0)  # avg = 30 kW, matches baseline
        result = await engine.validate_daily_power(datetime(2026, 1, 15), hourly)
        assert result["validation_status"] == "normal"

    @pytest.mark.asyncio
    async def test_anomaly_daily_power(self, engine):
        """Daily power significantly off baseline -> anomaly detected."""
        engine.get_power_baseline = AsyncMock(return_value={"mean_kw": 30.0, "stdev_kw": 5.0})
        hourly = dict.fromkeys(range(24), 45.0)  # avg = 45 kW, 50% over baseline
        result = await engine.validate_daily_power(datetime(2026, 1, 15), hourly)
        assert result["validation_status"] == "critical"

    def test_get_engine_returns_instance(self):
        """get_power_meter_validation_engine returns correct instance."""
        with patch("app.services.power_meter_validation_engine.get_supabase_client"):
            eng = get_power_meter_validation_engine("site-002")
            assert isinstance(eng, PowerMeterValidationEngine)
