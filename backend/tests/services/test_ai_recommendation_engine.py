"""Unit tests for AIRecommendationEngine.

Tests cover:
    - Lighting optimization ROI (3 tests)
    - Water efficiency ROI (3 tests)
    - HVAC maintenance ROI (3 tests)
    - Occupancy optimization ROI (2 tests)
    - Recommendation ranking (3 tests)
    - Priority assignment (2 tests)
    - Financial math verification (3 tests)
    - Edge cases (3 tests)

Total: 22 tests

All tests mock external calls and test the ROI calculation pipeline.
"""

import pytest

from app.services.ai_recommendation_engine import (
    BASELINE_HVAC_COP,
    BASELINE_LIGHTING_KWH_PER_DAY,
    BASELINE_WATER_LITERS_PER_DAY,
    DALI_RETROFIT_COST_R,
    ENERGY_RATE_R_PER_KWH,
    MAINTENANCE_COST_R,
    WATER_EFFICIENCY_RETROFIT_COST_R,
    WATER_RATE_R_PER_LITER,
    WATER_SEWERAGE_RATE_R_PER_LITER,
    AIRecommendationEngine,
    RecommendationType,
    get_ai_recommendation_engine,
)

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def engine():
    """Create an AIRecommendationEngine instance."""
    return AIRecommendationEngine("site-002")


# ------------------------------------------------------------------
# 1. Lighting Optimization ROI
# ------------------------------------------------------------------


class TestLightingOptimization:
    """Verify DALI lighting optimization recommendation."""

    @pytest.mark.asyncio
    async def test_lighting_savings_calculation(self, engine):
        """Lighting savings = (baseline - current) * 365 * rate."""
        rec = await engine._calculate_lighting_recommendation(150.0)
        assert rec is not None
        # (200 - 150) * 365 * 2.159 = 50 * 365 * 2.159 = 39,402.5
        expected_savings = (BASELINE_LIGHTING_KWH_PER_DAY - 150.0) * 365 * ENERGY_RATE_R_PER_KWH
        assert abs(rec["annual_savings_r"] - round(expected_savings, 2)) < 1.0

    @pytest.mark.asyncio
    async def test_lighting_payback_calculation(self, engine):
        """Payback = investment / (annual_savings / 12)."""
        rec = await engine._calculate_lighting_recommendation(150.0)
        assert rec is not None
        expected_savings = (200.0 - 150.0) * 365 * ENERGY_RATE_R_PER_KWH
        expected_payback = DALI_RETROFIT_COST_R / expected_savings * 12
        assert abs(rec["payback_months"] - round(expected_payback, 1)) < 0.5

    @pytest.mark.asyncio
    async def test_lighting_insufficient_savings_returns_none(self, engine):
        """If current close to baseline (<1 kWh savings), no recommendation."""
        rec = await engine._calculate_lighting_recommendation(199.5)
        assert rec is None


# ------------------------------------------------------------------
# 2. Water Efficiency ROI
# ------------------------------------------------------------------


class TestWaterEfficiency:
    """Verify water efficiency recommendation."""

    @pytest.mark.asyncio
    async def test_water_savings_calculation(self, engine):
        """Water savings uses combined water + sewerage rate."""
        rec = await engine._calculate_water_recommendation(6000.0)
        assert rec is not None
        combined_rate = WATER_RATE_R_PER_LITER + WATER_SEWERAGE_RATE_R_PER_LITER
        expected_savings = (BASELINE_WATER_LITERS_PER_DAY - 6000.0) * 365 * combined_rate
        assert abs(rec["annual_savings_r"] - round(expected_savings, 2)) < 1.0

    @pytest.mark.asyncio
    async def test_water_payback_calculation(self, engine):
        """Payback = R35,000 / (annual_savings / 12)."""
        rec = await engine._calculate_water_recommendation(6000.0)
        assert rec is not None
        combined_rate = WATER_RATE_R_PER_LITER + WATER_SEWERAGE_RATE_R_PER_LITER
        expected_savings = (8000.0 - 6000.0) * 365 * combined_rate
        expected_payback = WATER_EFFICIENCY_RETROFIT_COST_R / expected_savings * 12
        assert abs(rec["payback_months"] - round(expected_payback, 1)) < 0.5

    @pytest.mark.asyncio
    async def test_water_insufficient_savings_returns_none(self, engine):
        """If savings < 100 liters/day, no recommendation."""
        rec = await engine._calculate_water_recommendation(7950.0)
        assert rec is None


# ------------------------------------------------------------------
# 3. HVAC Maintenance ROI
# ------------------------------------------------------------------


class TestHVACMaintenance:
    """Verify HVAC maintenance recommendation for COP degradation."""

    @pytest.mark.asyncio
    async def test_hvac_degraded_cop_generates_recommendation(self, engine):
        """COP 3.0 (below design 3.5) -> recommendation generated."""
        rec = await engine._calculate_hvac_recommendation(3.0)
        assert rec is not None
        assert rec["type"] == RecommendationType.HVAC_MAINTENANCE
        assert rec["investment_cost_r"] == MAINTENANCE_COST_R

    @pytest.mark.asyncio
    async def test_hvac_savings_from_cop_recovery(self, engine):
        """Savings = (power_degraded - power_design) * 24 * 365 * rate."""
        current_cop = 3.0
        rec = await engine._calculate_hvac_recommendation(current_cop)
        assert rec is not None
        baseline_power = 45.0 / BASELINE_HVAC_COP
        current_power = 45.0 / current_cop
        additional_kw = current_power - baseline_power
        expected_savings = additional_kw * 24 * 365 * ENERGY_RATE_R_PER_KWH
        assert abs(rec["annual_savings_r"] - round(expected_savings, 2)) < 5.0

    @pytest.mark.asyncio
    async def test_hvac_minimal_degradation_returns_none(self, engine):
        """COP loss < 5% -> no recommendation."""
        # COP 3.4 -> loss = (1 - 3.4/3.5) * 100 = 2.86% < 5%
        rec = await engine._calculate_hvac_recommendation(3.4)
        assert rec is None


# ------------------------------------------------------------------
# 4. Occupancy Optimization ROI
# ------------------------------------------------------------------


class TestOccupancyOptimization:
    """Verify occupancy-based optimization recommendation."""

    @pytest.mark.asyncio
    async def test_anomalies_trigger_recommendation(self, engine):
        """Power anomalies detected -> occupancy optimization recommended."""
        rec = await engine._calculate_occupancy_recommendation(anomalies_count=5, cost_variance_pct=3.0)
        assert rec is not None
        assert rec["type"] == RecommendationType.OCCUPANCY_OPTIMIZATION
        assert rec["investment_cost_r"] == 8000.0

    @pytest.mark.asyncio
    async def test_no_issues_returns_none(self, engine):
        """No anomalies and low variance -> no recommendation."""
        rec = await engine._calculate_occupancy_recommendation(anomalies_count=0, cost_variance_pct=0.5)
        assert rec is None


# ------------------------------------------------------------------
# 5. Recommendation Ranking
# ------------------------------------------------------------------


class TestRecommendationRanking:
    """Verify recommendations are ranked by ROI."""

    @pytest.mark.asyncio
    async def test_recommendations_sorted_by_roi_descending(self, engine):
        """Recommendations sorted by ROI percentage (highest first)."""
        result = await engine.generate_recommendations(
            lighting_kwh_current=150.0,
            water_liters_current=6000.0,
            hvac_cop_current=3.0,
            power_anomalies_count=5,
            cost_variance_pct=3.0,
        )
        recs = result["recommendations"]
        assert len(recs) >= 3
        roi_values = [r["roi_pct"] for r in recs]
        assert roi_values == sorted(roi_values, reverse=True)

    @pytest.mark.asyncio
    async def test_rank_numbers_assigned(self, engine):
        """Each recommendation gets a rank number (1, 2, 3...)."""
        result = await engine.generate_recommendations(
            lighting_kwh_current=150.0,
            water_liters_current=6000.0,
            hvac_cop_current=3.0,
            power_anomalies_count=5,
        )
        recs = result["recommendations"]
        for i, rec in enumerate(recs, 1):
            assert rec["rank"] == i

    @pytest.mark.asyncio
    async def test_total_savings_is_sum_of_individual(self, engine):
        """total_annual_savings_r equals sum of individual savings."""
        result = await engine.generate_recommendations(
            lighting_kwh_current=150.0,
            water_liters_current=6000.0,
            hvac_cop_current=3.0,
            power_anomalies_count=5,
        )
        individual_sum = sum(r["annual_savings_r"] for r in result["recommendations"])
        assert abs(result["total_annual_savings_r"] - round(individual_sum, 2)) < 0.01


# ------------------------------------------------------------------
# 6. Priority Assignment
# ------------------------------------------------------------------


class TestPriorityAssignment:
    """Verify priority labels assigned to recommendations."""

    def test_rank_1_is_urgent(self, engine):
        """Rank 1 recommendation should be 'urgent'."""
        assert engine._get_priority(1, 4) == "urgent"

    def test_last_rank_is_low(self, engine):
        """Last rank should be 'low'."""
        assert engine._get_priority(4, 4) == "low"


# ------------------------------------------------------------------
# 7. Financial Math Verification
# ------------------------------------------------------------------


class TestFinancialMath:
    """Cross-check financial formulas with golden outputs."""

    @pytest.mark.asyncio
    async def test_roi_formula(self, engine):
        """ROI = (annual_savings / investment) * 100."""
        rec = await engine._calculate_lighting_recommendation(150.0)
        assert rec is not None
        calculated_roi = rec["annual_savings_r"] / rec["investment_cost_r"] * 100
        assert abs(rec["roi_pct"] - round(calculated_roi, 1)) < 0.1

    @pytest.mark.asyncio
    async def test_payback_formula(self, engine):
        """Payback months = investment / annual_savings * 12."""
        rec = await engine._calculate_lighting_recommendation(150.0)
        assert rec is not None
        calculated_payback = rec["investment_cost_r"] / rec["annual_savings_r"] * 12
        assert abs(rec["payback_months"] - round(calculated_payback, 1)) < 0.5

    @pytest.mark.asyncio
    async def test_co2_savings_calculation(self, engine):
        """CO2 savings = kWh_saved * 0.35 (SA grid intensity)."""
        rec = await engine._calculate_lighting_recommendation(150.0)
        assert rec is not None
        expected_kwh_saved = (200.0 - 150.0) * 365
        expected_co2 = round(expected_kwh_saved * 0.35, 0)
        assert rec["annual_savings_co2_kg"] == expected_co2


# ------------------------------------------------------------------
# 8. Edge Cases
# ------------------------------------------------------------------


class TestEdgeCases:
    """Verify edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_healthy_system_minimal_recommendations(self, engine):
        """All systems optimal -> minimal recommendations."""
        result = await engine.generate_recommendations(
            lighting_kwh_current=199.5,
            water_liters_current=7950.0,
            hvac_cop_current=3.5,
            power_anomalies_count=0,
            cost_variance_pct=0.1,
        )
        # Only lighting/water have >0 savings thresholds
        # With near-baseline values, should get 0 or very few recs
        assert result["recommendation_count"] <= 1

    @pytest.mark.asyncio
    async def test_confidence_within_range(self, engine):
        """All confidence scores should be between 0.50 and 0.95."""
        result = await engine.generate_recommendations(
            lighting_kwh_current=150.0,
            water_liters_current=6000.0,
            hvac_cop_current=3.0,
            power_anomalies_count=5,
        )
        for rec in result["recommendations"]:
            assert 0.50 <= rec["confidence"] <= 0.95

    def test_get_engine_returns_instance(self):
        """get_ai_recommendation_engine returns correct instance."""
        eng = get_ai_recommendation_engine("site-002")
        assert isinstance(eng, AIRecommendationEngine)
