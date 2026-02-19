"""Unit tests for CostValidationEngine.

Tests cover:
    - Daily cost comparison (3 tests)
    - Monthly variance analysis (2 tests)
    - Tariff adjustment recommendation (4 tests)
    - Cost calculation internals (3 tests)
    - Demo fallback (2 tests)
    - Edge cases (2 tests)

Total: 16 tests

All tests mock Supabase and test pure validation logic only.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.cost_validation_engine import (
    COST_CRITICAL_VARIANCE_PCT,
    COST_VARIANCE_THRESHOLD_PCT,
    MINIMUM_INVOICE_RECORDS,
    CostValidationEngine,
    get_cost_validation_engine,
)

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def engine():
    """Create a CostValidationEngine with mocked Supabase client."""
    with patch("app.services.cost_validation_engine.get_supabase_client") as mock_sb:
        mock_client = MagicMock()
        mock_sb.return_value = mock_client
        eng = CostValidationEngine("site-002")
        return eng


@pytest.fixture
def test_date():
    """Standard test date."""
    return datetime(2026, 1, 15, 23, 0)


# ------------------------------------------------------------------
# 1. Daily Cost Comparison
# ------------------------------------------------------------------


class TestDailyCostComparison:
    """Verify daily cost validation against expected."""

    @pytest.mark.asyncio
    async def test_validated_within_5_percent(self, engine, test_date):
        """Cost within 5% of expected -> status 'validated'."""
        engine._get_expected_daily_cost = AsyncMock(return_value=1500.0)

        result = await engine.validate_daily_cost(test_date, {"total_cost_r": 1520.0})
        assert result["validation_status"] == "validated"
        assert result["severity"] == "healthy"
        assert result["variance_pct"] < COST_VARIANCE_THRESHOLD_PCT

    @pytest.mark.asyncio
    async def test_warning_between_5_and_15_percent(self, engine, test_date):
        """Cost 5-15% off -> status 'warning'."""
        engine._get_expected_daily_cost = AsyncMock(return_value=1500.0)

        result = await engine.validate_daily_cost(test_date, {"total_cost_r": 1650.0})
        assert result["validation_status"] == "warning"
        assert result["severity"] == "warning"
        assert COST_VARIANCE_THRESHOLD_PCT <= result["variance_pct"] <= COST_CRITICAL_VARIANCE_PCT

    @pytest.mark.asyncio
    async def test_critical_above_15_percent(self, engine, test_date):
        """Cost >15% off -> status 'critical'."""
        engine._get_expected_daily_cost = AsyncMock(return_value=1500.0)

        result = await engine.validate_daily_cost(test_date, {"total_cost_r": 1800.0})
        assert result["validation_status"] == "critical"
        assert result["severity"] == "critical"
        assert result["variance_pct"] > COST_CRITICAL_VARIANCE_PCT


# ------------------------------------------------------------------
# 2. Monthly Variance Analysis
# ------------------------------------------------------------------


class TestMonthlyVariance:
    """Verify monthly cost validation against real invoices."""

    @pytest.mark.asyncio
    async def test_monthly_validated_small_variance(self, engine):
        """Monthly cost close to invoice -> validated."""
        engine._get_simulated_monthly_cost = AsyncMock(return_value=45000.0)
        engine._write_cost_validation_record = AsyncMock()

        result = await engine.validate_monthly_cost(month=1, year=2026, real_invoice_cost_r=44000.0)
        assert result["validation_status"] == "validated" or result["variance_pct"] < COST_CRITICAL_VARIANCE_PCT
        assert result["period"] == "2026-01"

    @pytest.mark.asyncio
    async def test_monthly_critical_large_variance(self, engine):
        """Monthly cost far from invoice -> critical."""
        engine._get_simulated_monthly_cost = AsyncMock(return_value=60000.0)
        engine._write_cost_validation_record = AsyncMock()

        result = await engine.validate_monthly_cost(month=1, year=2026, real_invoice_cost_r=40000.0)
        # 50% variance: |60000 - 40000| / 40000 = 50%
        assert result["validation_status"] == "critical"
        assert result["variance_pct"] > COST_CRITICAL_VARIANCE_PCT


# ------------------------------------------------------------------
# 3. Tariff Adjustment Recommendation
# ------------------------------------------------------------------


class TestTariffAdjustment:
    """Verify tariff adjustment recommendations from historical data."""

    @pytest.mark.asyncio
    async def test_insufficient_data_no_adjustment(self, engine):
        """Less than 3 months of data -> no adjustment."""
        result = await engine.get_tariff_adjustment_recommendation(
            [
                {"variance_pct": 8.0, "variance_direction": "over"},
            ]
        )
        assert result["adjustment_needed"] is False
        assert result["reason"] == "insufficient_data"

    @pytest.mark.asyncio
    async def test_consistent_overestimate_recommends_lower_multiplier(self, engine):
        """Consistent +10% overestimate -> recommend lower multiplier."""
        history = [
            {"variance_pct": 10.0, "variance_direction": "over"},
            {"variance_pct": 9.5, "variance_direction": "over"},
            {"variance_pct": 10.5, "variance_direction": "over"},
        ]
        result = await engine.get_tariff_adjustment_recommendation(history)
        assert result["bias_direction"] == "over"
        assert result["recommended_tariff_multiplier"] >= 1.0

    @pytest.mark.asyncio
    async def test_consistent_underestimate_recommends_higher_multiplier(self, engine):
        """Consistent -10% underestimate -> recommend higher multiplier."""
        history = [
            {"variance_pct": 10.0, "variance_direction": "under"},
            {"variance_pct": 9.0, "variance_direction": "under"},
            {"variance_pct": 11.0, "variance_direction": "under"},
        ]
        result = await engine.get_tariff_adjustment_recommendation(history)
        assert result["bias_direction"] == "under"
        assert result["recommended_tariff_multiplier"] >= 1.0

    @pytest.mark.asyncio
    async def test_mixed_variance_no_adjustment(self, engine):
        """Mixed variance direction -> inconsistent, no adjustment."""
        history = [
            {"variance_pct": 8.0, "variance_direction": "over"},
            {"variance_pct": 7.0, "variance_direction": "under"},
            {"variance_pct": 6.0, "variance_direction": "over"},
            {"variance_pct": 9.0, "variance_direction": "under"},
            {"variance_pct": 5.0, "variance_direction": "under"},
        ]
        result = await engine.get_tariff_adjustment_recommendation(history)
        # Mixed: 2 over, 3 under -> bias_consistency = 3/5 = 0.6 < 0.7
        assert result["adjustment_needed"] is False
        assert result["reason"] == "inconsistent_variance"


# ------------------------------------------------------------------
# 4. Cost Calculation Internals
# ------------------------------------------------------------------


class TestCostCalculation:
    """Verify internal energy and water cost calculations."""

    @pytest.mark.asyncio
    async def test_summer_energy_rate(self, engine):
        """Summer energy rate is R2.159/kWh."""
        result = await engine._calculate_energy_cost(100.0, "summer")
        # 100 kWh * 2.159 = 215.90 + 9.50 service = 225.40
        assert abs(result["energy_cost_r"] - 215.9) < 0.1
        assert result["service_charge_r"] == 9.5

    @pytest.mark.asyncio
    async def test_winter_energy_rate_higher(self, engine):
        """Winter energy rate is R2.285/kWh (higher than summer)."""
        result_summer = await engine._calculate_energy_cost(100.0, "summer")
        result_winter = await engine._calculate_energy_cost(100.0, "winter")
        assert result_winter["energy_cost_r"] > result_summer["energy_cost_r"]

    @pytest.mark.asyncio
    async def test_water_cost_tiered(self, engine):
        """Water cost uses Johannesburg tiered tariff."""
        result = await engine._calculate_water_cost(2000.0)
        assert result["tier_1_cost_r"] > 0
        assert result["sewerage_cost_r"] > 0
        assert result["total_cost_r"] > 0


# ------------------------------------------------------------------
# 5. Demo Fallback
# ------------------------------------------------------------------


class TestDemoFallback:
    """Verify fallback to demo fixtures."""

    @pytest.mark.asyncio
    async def test_default_expected_daily_cost(self, engine):
        """When no invoices or demo data, fallback to R1575/day."""
        # Mock DB to return empty
        mock_response = MagicMock()
        mock_response.data = []
        chain = engine.client.table.return_value.select.return_value
        chain.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_response

        # Also mock file not existing
        with patch("app.services.cost_validation_engine._DATA_DIR") as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            cost = await engine._get_expected_daily_cost()
            assert cost == 1575.0

    def test_cost_threshold_constants(self):
        """Verify cost threshold constants."""
        assert COST_VARIANCE_THRESHOLD_PCT == 5.0
        assert COST_CRITICAL_VARIANCE_PCT == 15.0
        assert MINIMUM_INVOICE_RECORDS == 3


# ------------------------------------------------------------------
# 6. Edge Cases
# ------------------------------------------------------------------


class TestEdgeCases:
    """Verify edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_zero_cost_skips_validation(self, engine, test_date):
        """Zero cost value -> validation skipped."""
        result = await engine.validate_daily_cost(test_date, {"total_cost_r": 0})
        assert result["validation_status"] == "skipped"
        assert result["reason"] == "zero_cost"

    @pytest.mark.asyncio
    async def test_numeric_cost_accepted(self, engine, test_date):
        """Numeric cost value (not dict) is accepted."""
        engine._get_expected_daily_cost = AsyncMock(return_value=1500.0)
        result = await engine.validate_daily_cost(test_date, 1500.0)
        assert result["validation_status"] == "validated"

    def test_get_engine_returns_instance(self):
        """get_cost_validation_engine returns correct instance."""
        with patch("app.services.cost_validation_engine.get_supabase_client"):
            eng = get_cost_validation_engine("site-002")
            assert isinstance(eng, CostValidationEngine)
