"""Parity tests for SolarTableProcessor.

Verifies that monthly aggregation, learning-curve calculation, and seasonal
rollup match the original logic in SolarAnnualAggregator before the refactor.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.processing.solar_table import _SEASON_MAP, SolarTableProcessor
from app.services.solar_annual_aggregator import HourlySnapshot, MonthSummary

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _snapshot(hour: int, month: int, day_of_year: int, **kwargs) -> HourlySnapshot:
    """Build a minimal HourlySnapshot with sensible defaults."""
    defaults = dict(
        solar_gen_kw=10.0,
        site_load_kw=20.0,
        bess_soc_pct=50.0,
        bess_charge_kw=2.0,
        bess_discharge_kw=1.0,
        grid_import_kw=15.0,
        grid_export_kw=3.0,
        tariff_band="standard",
        tariff_rate_c_kwh=2.12,
    )
    defaults.update(kwargs)
    return HourlySnapshot(
        hour=hour,
        date=datetime(2026, month, 1),
        month=month,
        day_of_year=day_of_year,
        **defaults,
    )


def _month_summary(month: int, **kwargs) -> MonthSummary:
    defaults = dict(
        month_name=["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][month - 1],
        season=_SEASON_MAP[month],
        solar_generated_kwh=1000.0,
        bess_charged_kwh=200.0,
        bess_discharged_kwh=150.0,
        grid_import_kwh=500.0,
        grid_export_kwh=100.0,
        site_load_kwh=1400.0,
        self_consumption_kwh=900.0,
        peak_demand_kw=50.0,
        total_cost_standard_ems_zar=5000.0,
        total_cost_sentinel_ai_zar=4250.0,
        savings_zar=750.0,
        savings_pct=15.0,
        avg_bess_soc_pct=55.0,
        capacity_factor_pct=80.0,
    )
    defaults.update(kwargs)
    return MonthSummary(month=month, **defaults)


# ---------------------------------------------------------------------------
# aggregate_months
# ---------------------------------------------------------------------------


class TestAggregateMonths:
    def test_empty_input_returns_empty(self):
        result = SolarTableProcessor.aggregate_months([])
        assert result == []

    def test_returns_one_month_summary_per_month_present(self):
        snapshots = [_snapshot(h, month=1, day_of_year=h + 1) for h in range(24)]
        result = SolarTableProcessor.aggregate_months(snapshots)
        assert len(result) == 1
        assert result[0].month == 1

    def test_solar_kwh_sums_hourly(self):
        # 10 hours × 5 kW solar = 50 kWh
        snapshots = [_snapshot(h, month=3, day_of_year=h + 60, solar_gen_kw=5.0) for h in range(10)]
        result = SolarTableProcessor.aggregate_months(snapshots)
        assert result[0].solar_generated_kwh == pytest.approx(50.0)

    def test_season_assignment_correct(self):
        # Month 7 = winter in SA
        snapshots = [_snapshot(h, month=7, day_of_year=h + 181) for h in range(24)]
        result = SolarTableProcessor.aggregate_months(snapshots)
        assert result[0].season == "winter"

    def test_multiple_months_aggregated_separately(self):
        jan = [_snapshot(h, month=1, day_of_year=h + 1, solar_gen_kw=8.0) for h in range(24)]
        feb = [_snapshot(h, month=2, day_of_year=h + 32, solar_gen_kw=9.0) for h in range(24)]
        result = SolarTableProcessor.aggregate_months(jan + feb)
        assert len(result) == 2
        months = {m.month for m in result}
        assert months == {1, 2}

    def test_peak_demand_is_max(self):
        snapshots = [
            _snapshot(0, month=6, day_of_year=152, grid_import_kw=10.0, site_load_kw=20.0),
            _snapshot(1, month=6, day_of_year=152, grid_import_kw=5.0, site_load_kw=15.0),
        ]
        result = SolarTableProcessor.aggregate_months(snapshots)
        # peak = max(10+20, 5+15) = 30
        assert result[0].peak_demand_kw == pytest.approx(30.0)

    def test_self_consumption_is_solar_minus_export(self):
        snapshots = [_snapshot(0, month=4, day_of_year=91, solar_gen_kw=10.0, grid_export_kw=3.0)]
        result = SolarTableProcessor.aggregate_months(snapshots)
        assert result[0].self_consumption_kwh == pytest.approx(7.0)

    def test_avg_bess_soc_is_mean(self):
        snapshots = [
            _snapshot(0, month=9, day_of_year=244, bess_soc_pct=40.0),
            _snapshot(1, month=9, day_of_year=244, bess_soc_pct=60.0),
        ]
        result = SolarTableProcessor.aggregate_months(snapshots)
        assert result[0].avg_bess_soc_pct == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# calculate_learning_curve
# ---------------------------------------------------------------------------


class TestCalculateLearningCurve:
    def test_length_matches_monthly_data(self):
        months = [_month_summary(m) for m in range(1, 13)]
        curve = SolarTableProcessor.calculate_learning_curve(months)
        assert len(curve) == 12

    def test_savings_pct_increases_over_time(self):
        months = [_month_summary(m) for m in range(1, 13)]
        curve = SolarTableProcessor.calculate_learning_curve(months)
        savings = [c["savings_pct"] for c in curve]
        # Each month should be >= previous month
        for i in range(1, len(savings)):
            assert savings[i] >= savings[i - 1]

    def test_month_1_is_lowest_savings(self):
        months = [_month_summary(m) for m in range(1, 13)]
        curve = SolarTableProcessor.calculate_learning_curve(months)
        assert curve[0]["savings_pct"] < curve[-1]["savings_pct"]

    def test_month_12_savings_near_18_percent(self):
        months = [_month_summary(m) for m in range(1, 13)]
        curve = SolarTableProcessor.calculate_learning_curve(months)
        assert curve[-1]["savings_pct"] == pytest.approx(18.0, abs=0.1)

    def test_each_entry_has_required_keys(self):
        months = [_month_summary(1)]
        curve = SolarTableProcessor.calculate_learning_curve(months)
        assert {"month", "month_name", "savings_pct", "learning_factor"} <= curve[0].keys()

    def test_learning_factor_in_0_to_1(self):
        months = [_month_summary(m) for m in range(1, 13)]
        curve = SolarTableProcessor.calculate_learning_curve(months)
        for entry in curve:
            assert 0 <= entry["learning_factor"] <= 1


# ---------------------------------------------------------------------------
# aggregate_seasons
# ---------------------------------------------------------------------------


class TestAggregateSeasons:
    def test_returns_four_seasons_for_full_year(self):
        months = [_month_summary(m) for m in range(1, 13)]
        # Apply savings_pct so seasonal avg makes sense
        for m in months:
            m.savings_pct = 15.0
        seasons = SolarTableProcessor.aggregate_seasons(months)
        assert len(seasons) == 4

    def test_season_names_present(self):
        months = [_month_summary(m) for m in range(1, 13)]
        seasons = SolarTableProcessor.aggregate_seasons(months)
        season_names = {s.season for s in seasons}
        assert season_names == {"summer", "autumn", "winter", "spring"}

    def test_solar_kwh_is_sum_of_months(self):
        months = [_month_summary(m, solar_generated_kwh=100.0) for m in range(1, 13)]
        seasons = SolarTableProcessor.aggregate_seasons(months)
        # Summer = months 12, 1, 2 = 3 × 100 kWh = 300
        summer = next(s for s in seasons if s.season == "summer")
        assert summer.total_solar_kwh == pytest.approx(300.0)

    def test_avg_savings_pct_is_mean_of_months(self):
        months = [_month_summary(m, savings_pct=10.0) for m in range(1, 13)]
        seasons = SolarTableProcessor.aggregate_seasons(months)
        for s in seasons:
            assert s.avg_savings_pct == pytest.approx(10.0)

    def test_partial_year_skips_missing_season(self):
        # Only January and February — summer months only
        months = [_month_summary(1), _month_summary(2)]
        seasons = SolarTableProcessor.aggregate_seasons(months)
        # Only summer should appear (months 12, 1, 2 — but 12 missing)
        # Still produces summer entry because 1 and 2 match
        season_names = {s.season for s in seasons}
        assert "summer" in season_names
        assert "winter" not in season_names


# ---------------------------------------------------------------------------
# _calculate_standard_ems_cost
# ---------------------------------------------------------------------------


class TestCalculateStandardEmsCost:
    def test_cost_positive_for_nonzero_import(self):
        cost = SolarTableProcessor._calculate_standard_ems_cost(month=1, grid_import_kwh=1000.0, peak_demand_kw=50.0)
        assert cost > 0

    def test_winter_cost_higher_than_summer_for_same_load(self):
        """Winter tariffs are higher so cost should be greater."""
        summer_cost = SolarTableProcessor._calculate_standard_ems_cost(
            month=1, grid_import_kwh=1000.0, peak_demand_kw=50.0
        )
        winter_cost = SolarTableProcessor._calculate_standard_ems_cost(
            month=7, grid_import_kwh=1000.0, peak_demand_kw=50.0
        )
        assert winter_cost > summer_cost

    def test_zero_import_still_has_demand_charge(self):
        """Even with no energy, demand charge applies."""
        cost = SolarTableProcessor._calculate_standard_ems_cost(month=3, grid_import_kwh=0.0, peak_demand_kw=100.0)
        assert cost > 0
