"""Unit tests for WaterConsumptionEngine.

Tests cover:
    - Baseline consumption (2 tests)
    - Occupancy scaling (2 tests)
    - Seasonal effects (4 tests)
    - Weather effects (3 tests)
    - Tariff tier calculation (4 tests)
    - Edge cases (2 tests)

Total: 17 tests

All tests mock Supabase and test pure calculation logic only.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.services.water_consumption_engine import (
    BASELINE_WATER_PER_ZONE,
    CLOUDY_IRRIGATION_REDUCTION,
    JOHANNESBURG_FIXED_MONTHLY_CHARGE,
    JOHANNESBURG_SEWERAGE_RATE_R_PER_LITER,
    JOHANNESBURG_TIER_1_LITERS,
    OCCUPANCY_WATER_SCALING,
    RAIN_IRRIGATION_REDUCTION,
    SUMMER_IRRIGATION_FACTOR,
    WINTER_REDUCTION_FACTOR,
    WaterConsumptionEngine,
    get_water_consumption_engine,
)

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def engine():
    """Create a WaterConsumptionEngine with mocked dependencies."""
    with (
        patch("app.services.water_consumption_engine.get_supabase_client") as mock_sb,
        patch("app.services.water_consumption_engine.WaterCostRepository"),
    ):
        mock_sb.return_value = MagicMock()
        eng = WaterConsumptionEngine("site-002")
        return eng


@pytest.fixture
def summer_date():
    """A summer date (Southern Hemisphere: Dec-Feb)."""
    return datetime(2026, 1, 15, 10, 0)


@pytest.fixture
def winter_date():
    """A winter date (Southern Hemisphere: Jun-Aug)."""
    return datetime(2026, 7, 15, 10, 0)


@pytest.fixture
def autumn_date():
    """An autumn date (Mar-May)."""
    return datetime(2026, 4, 15, 10, 0)


@pytest.fixture
def spring_date():
    """A spring date (Sep-Nov)."""
    return datetime(2026, 10, 15, 10, 0)


@pytest.fixture
def standard_occupancy():
    """Standard occupancy data for 8 zones."""
    return {
        "Zone-001": 80.0,
        "Zone-002": 70.0,
        "Zone-101": 85.0,
        "Zone-102": 75.0,
        "Zone-201": 60.0,
        "Zone-202": 65.0,
        "Zone-R": 50.0,
        "Entry": 40.0,
    }


# ------------------------------------------------------------------
# 1. Baseline Consumption
# ------------------------------------------------------------------


class TestBaselineConsumption:
    """Verify base water usage constants."""

    def test_baseline_per_zone_calculated_correctly(self):
        """45L/occupant/day * 100 occupants / 24 hours = 187.5 L/zone/hour."""
        expected = (45.0 * 100) / 24
        assert abs(BASELINE_WATER_PER_ZONE - expected) < 0.01

    def test_occupancy_scaling_is_40_percent(self):
        """40% of water usage varies with occupancy."""
        assert OCCUPANCY_WATER_SCALING == 0.40


# ------------------------------------------------------------------
# 2. Occupancy Scaling
# ------------------------------------------------------------------


class TestOccupancyScaling:
    """Verify water responds to occupancy levels."""

    def test_full_occupancy_higher_than_zero_occupancy(self, engine, summer_date):
        """100% occupancy should use more water than 0% occupancy."""
        occ_full = {"Zone-001": 100.0}
        occ_zero = {"Zone-001": 0.0}

        _, total_full = engine.calculate_water_consumption(
            simulated_hour=10, occupancy_data=occ_full, simulated_date=summer_date
        )
        _, total_zero = engine.calculate_water_consumption(
            simulated_hour=10, occupancy_data=occ_zero, simulated_date=summer_date
        )
        assert total_full > total_zero

    def test_zero_occupancy_still_has_standby_water(self, engine, summer_date):
        """0% occupancy -> standby component (60% of base)."""
        occ_zero = {"Zone-001": 0.0}
        _, total = engine.calculate_water_consumption(
            simulated_hour=10, occupancy_data=occ_zero, simulated_date=summer_date
        )
        assert total > 0, "Zero occupancy should still have standby water usage"


# ------------------------------------------------------------------
# 3. Seasonal Effects
# ------------------------------------------------------------------


class TestSeasonalEffects:
    """Verify seasonal factors for Southern Hemisphere."""

    def test_summer_factor_is_1_20(self, engine, summer_date):
        """Summer (Dec-Feb): +20% factor."""
        factor = engine._get_seasonal_factor(summer_date)
        assert factor == SUMMER_IRRIGATION_FACTOR
        assert factor == 1.20

    def test_winter_factor_is_0_85(self, engine, winter_date):
        """Winter (Jun-Aug): -15% factor."""
        factor = engine._get_seasonal_factor(winter_date)
        assert factor == WINTER_REDUCTION_FACTOR
        assert factor == 0.85

    def test_autumn_factor_is_1_05(self, engine, autumn_date):
        """Autumn (Mar-May): slight increase."""
        factor = engine._get_seasonal_factor(autumn_date)
        assert factor == 1.05

    def test_summer_uses_more_water_than_winter(self, engine, summer_date, winter_date, standard_occupancy):
        """Summer consumption should exceed winter consumption."""
        _, total_summer = engine.calculate_water_consumption(
            simulated_hour=10, occupancy_data=standard_occupancy, simulated_date=summer_date
        )
        _, total_winter = engine.calculate_water_consumption(
            simulated_hour=10, occupancy_data=standard_occupancy, simulated_date=winter_date
        )
        assert total_summer > total_winter


# ------------------------------------------------------------------
# 4. Weather Effects (Irrigation)
# ------------------------------------------------------------------


class TestWeatherEffects:
    """Verify rain and cloud cover effects on water consumption."""

    def test_rain_reduces_consumption(self, engine, summer_date, standard_occupancy):
        """Rain reduces irrigation by 60%."""
        _, total_dry = engine.calculate_water_consumption(
            simulated_hour=10, occupancy_data=standard_occupancy, is_raining=False, simulated_date=summer_date
        )
        _, total_rain = engine.calculate_water_consumption(
            simulated_hour=10, occupancy_data=standard_occupancy, is_raining=True, simulated_date=summer_date
        )
        assert total_rain < total_dry, "Rain should reduce water consumption"

    def test_rain_irrigation_factor(self, engine):
        """Rain irrigation factor = 1.0 - 0.60 = 0.40."""
        factor = engine._get_irrigation_factor(0.0, is_raining=True)
        expected = 1.0 - RAIN_IRRIGATION_REDUCTION
        assert abs(factor - expected) < 0.01
        assert abs(factor - 0.40) < 0.01

    def test_cloudy_reduces_irrigation_slightly(self, engine):
        """80% cloud cover -> cloud factor = 1.0 - (0.80 * 0.15) = 0.88."""
        factor = engine._get_irrigation_factor(80.0, is_raining=False)
        expected = 1.0 - (80.0 / 100.0) * CLOUDY_IRRIGATION_REDUCTION
        assert abs(factor - expected) < 0.01


# ------------------------------------------------------------------
# 5. Tariff Tier Calculation
# ------------------------------------------------------------------


class TestTariffTierCalculation:
    """Verify Johannesburg tiered water tariff calculation."""

    @pytest.mark.asyncio
    async def test_tier_1_only(self, engine, summer_date):
        """Consumption below tier 1 threshold -> tier 1 rate only."""
        daily_allocation = JOHANNESBURG_TIER_1_LITERS / 30.0  # ~3333 L/day
        hourly = dict.fromkeys(range(24), 100.0)  # 2400 L total (below tier 1)
        result = await engine.calculate_daily_water_cost(summer_date, hourly)
        assert result["tier_1_cost_r"] > 0
        assert result["tier_2_cost_r"] == 0
        assert result["tier_3_cost_r"] == 0
        assert result["total_liters"] == 2400.0

    @pytest.mark.asyncio
    async def test_tier_2_reached(self, engine, summer_date):
        """Consumption above tier 1 -> tier 2 kicks in."""
        # tier_1_daily = 100000/30 = 3333.33 L
        hourly = dict.fromkeys(range(24), 200.0)  # 4800 L total (above tier 1)
        result = await engine.calculate_daily_water_cost(summer_date, hourly)
        assert result["tier_1_cost_r"] > 0
        assert result["tier_2_cost_r"] > 0
        assert result["tier_3_cost_r"] == 0

    @pytest.mark.asyncio
    async def test_sewerage_always_charged(self, engine, summer_date):
        """Sewerage charge at R6.30/kL applies to all water consumption."""
        hourly = dict.fromkeys(range(24), 100.0)
        result = await engine.calculate_daily_water_cost(summer_date, hourly)
        expected_sewerage = 2400.0 * JOHANNESBURG_SEWERAGE_RATE_R_PER_LITER
        assert abs(result["sewerage_cost_r"] - round(expected_sewerage, 2)) < 0.01

    @pytest.mark.asyncio
    async def test_fixed_daily_charge_included(self, engine, summer_date):
        """Fixed monthly charge (R285/30) is included."""
        hourly = dict.fromkeys(range(24), 100.0)
        result = await engine.calculate_daily_water_cost(summer_date, hourly)
        expected_fixed = round(JOHANNESBURG_FIXED_MONTHLY_CHARGE / 30.0, 2)
        assert abs(result["fixed_charge_r"] - expected_fixed) < 0.01


# ------------------------------------------------------------------
# 6. Edge Cases
# ------------------------------------------------------------------


class TestEdgeCases:
    """Verify edge cases and boundary conditions."""

    def test_multiple_zones_accumulate(self, engine, summer_date):
        """Multiple zones should accumulate to higher total."""
        one_zone = {"Zone-001": 80.0}
        two_zones = {"Zone-001": 80.0, "Zone-002": 80.0}

        _, total_one = engine.calculate_water_consumption(
            simulated_hour=10, occupancy_data=one_zone, simulated_date=summer_date
        )
        _, total_two = engine.calculate_water_consumption(
            simulated_hour=10, occupancy_data=two_zones, simulated_date=summer_date
        )
        assert total_two > total_one

    def test_get_engine_returns_instance(self):
        """get_water_consumption_engine returns a WaterConsumptionEngine."""
        with (
            patch("app.services.water_consumption_engine.get_supabase_client"),
            patch("app.services.water_consumption_engine.WaterCostRepository"),
        ):
            eng = get_water_consumption_engine("site-002")
            assert isinstance(eng, WaterConsumptionEngine)
