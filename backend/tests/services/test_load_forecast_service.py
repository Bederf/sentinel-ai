"""Tests for LoadForecastService — 15-minute building demand forecast.

Covers: model training, forecast generation, confidence bands, accuracy,
retraining, current load, caching, edge cases.
"""

import pytest

from app.models.load_forecast import LoadForecast, LoadInterval
from app.services.load_forecast_service import (
    LoadForecastService,
    _simulated_site_load,
    _synthetic_solar_kw,
    _SEASONAL_TEMPS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def service():
    """Create a shared service instance (training is slow, reuse)."""
    return LoadForecastService()


# ---------------------------------------------------------------------------
# Simulated building load tests
# ---------------------------------------------------------------------------


class TestSimulatedBuildingLoad:
    """Test the synthetic building load profile function."""

    def test_overnight_base_load(self):
        import random

        rng = random.Random(42)
        load = _simulated_site_load(2.0, rng)
        assert 850 <= load <= 950, f"Overnight load should be ~900 kW, got {load}"

    def test_morning_ramp(self):
        import random

        rng = random.Random(42)
        load_6am = _simulated_site_load(6.5, rng)
        load_3am = _simulated_site_load(3.0, rng)
        assert load_6am > load_3am, "Morning ramp should increase load"

    def test_afternoon_peak(self):
        import random

        rng = random.Random(42)
        load = _simulated_site_load(14.5, rng)
        assert 1700 <= load <= 1950, f"Afternoon peak should be ~1850 kW, got {load}"

    def test_evening_decline(self):
        import random

        rng = random.Random(42)
        load_8pm = _simulated_site_load(20.0, rng)
        load_2pm = _simulated_site_load(14.0, random.Random(42))
        assert load_8pm < load_2pm, "Evening load should be less than afternoon"

    def test_no_negative_loads(self):
        import random

        for hour_int in range(96):
            hour = hour_int / 4.0
            load = _simulated_site_load(hour, random.Random(hour_int))
            assert load >= 0, f"Load at hour {hour} should not be negative"

    def test_reproducible_with_rng(self):
        import random

        rng1 = random.Random(123)
        rng2 = random.Random(123)
        assert _simulated_site_load(10.0, rng1) == _simulated_site_load(10.0, rng2)


# ---------------------------------------------------------------------------
# Synthetic solar tests
# ---------------------------------------------------------------------------


class TestSyntheticSolarKw:
    """Test the synthetic solar generation function."""

    def test_zero_at_night(self):
        assert _synthetic_solar_kw(0.0) == 0.0
        assert _synthetic_solar_kw(5.0) == 0.0
        assert _synthetic_solar_kw(20.0) == 0.0

    def test_peak_at_noon(self):
        solar = _synthetic_solar_kw(12.5)
        assert 3100 <= solar <= 3300, f"Expected ~3200 kW at noon, got {solar}"

    def test_bell_curve_shape(self):
        morning = _synthetic_solar_kw(8.0)
        noon = _synthetic_solar_kw(12.5)
        afternoon = _synthetic_solar_kw(17.0)
        assert morning < noon
        assert afternoon < noon


# ---------------------------------------------------------------------------
# Model training tests
# ---------------------------------------------------------------------------


class TestModelTraining:
    """Test that models train successfully with reasonable accuracy."""

    def test_model_trained_on_init(self, service: LoadForecastService):
        assert "site-002" in service._models
        assert service._models["site-002"] is not None

    def test_accuracy_metrics_exist(self, service: LoadForecastService):
        accuracy = service.get_accuracy("site-002")
        assert accuracy is not None
        assert "rmse_kw" in accuracy
        assert "mae_kw" in accuracy
        assert "r2_score" in accuracy
        assert "training_samples" in accuracy

    def test_r2_above_threshold(self, service: LoadForecastService):
        accuracy = service.get_accuracy("site-002")
        assert accuracy["r2_score"] > 0.7, f"R² should be > 0.7, got {accuracy['r2_score']}"

    def test_rmse_reasonable(self, service: LoadForecastService):
        accuracy = service.get_accuracy("site-002")
        # RMSE should be well below the load range (~900-1850 kW)
        assert accuracy["rmse_kw"] < 300, f"RMSE should be < 300 kW, got {accuracy['rmse_kw']}"

    def test_training_sample_count(self, service: LoadForecastService):
        accuracy = service.get_accuracy("site-002")
        # 90 days * 96 intervals = 8640 samples
        assert accuracy["training_samples"] == 8640


# ---------------------------------------------------------------------------
# Forecast generation tests
# ---------------------------------------------------------------------------


class TestGetForecast:
    """Test forecast generation."""

    def test_default_96_intervals(self, service: LoadForecastService):
        forecast = service.get_forecast("site-002")
        assert len(forecast.intervals) == 96

    def test_custom_interval_count(self, service: LoadForecastService):
        forecast = service.get_forecast("site-002", intervals_ahead=48)
        assert len(forecast.intervals) == 48

    def test_forecast_metadata(self, service: LoadForecastService):
        forecast = service.get_forecast("site-002")
        assert forecast.site_id == "site-002"
        assert forecast.model == "gradient_boosting"
        assert forecast.generated_at != ""

    def test_peak_demand_calculated(self, service: LoadForecastService):
        forecast = service.get_forecast("site-002")
        assert forecast.peak_demand_kw > 0
        # Peak should be the max of all interval demands
        max_interval = max(i.demand_kw for i in forecast.intervals)
        assert abs(forecast.peak_demand_kw - max_interval) < 0.1

    def test_avg_demand_reasonable(self, service: LoadForecastService):
        forecast = service.get_forecast("site-002")
        assert 500 <= forecast.avg_demand_kw <= 2500

    def test_total_energy_calculated(self, service: LoadForecastService):
        forecast = service.get_forecast("site-002")
        # total_energy = sum(demand) * 0.25h
        expected = sum(i.demand_kw for i in forecast.intervals) * 0.25
        assert abs(forecast.total_energy_kwh - expected) < 1.0

    def test_demand_values_positive(self, service: LoadForecastService):
        forecast = service.get_forecast("site-002")
        for interval in forecast.intervals:
            assert interval.demand_kw >= 0, f"Demand should be >= 0 at {interval.timestamp}"

    def test_confidence_bands(self, service: LoadForecastService):
        forecast = service.get_forecast("site-002")
        for interval in forecast.intervals:
            assert interval.confidence_low_kw <= interval.demand_kw
            assert interval.confidence_high_kw >= interval.demand_kw

    def test_confidence_widens_with_horizon(self, service: LoadForecastService):
        forecast = service.get_forecast("site-002")
        if len(forecast.intervals) >= 2:
            first = forecast.intervals[0]
            last = forecast.intervals[-1]
            first_width = first.confidence_high_kw - first.confidence_low_kw
            last_width = last.confidence_high_kw - last.confidence_low_kw
            # Last interval should have wider bands (unless demand is very different)
            if first.demand_kw > 100 and last.demand_kw > 100:
                first_pct = first_width / first.demand_kw
                last_pct = last_width / last.demand_kw
                assert last_pct >= first_pct

    def test_tariff_bands_assigned(self, service: LoadForecastService):
        forecast = service.get_forecast("site-002")
        bands = {i.tariff_band for i in forecast.intervals}
        # Should have at least 2 different bands in a 24h window
        assert len(bands) >= 2

    def test_peak_hours_flagged(self, service: LoadForecastService):
        forecast = service.get_forecast("site-002")
        peak_count = sum(1 for i in forecast.intervals if i.is_peak_hour)
        # Should have some peak intervals in a 24h window
        assert peak_count > 0

    def test_to_dict(self, service: LoadForecastService):
        forecast = service.get_forecast("site-002")
        d = forecast.to_dict()
        assert "site_id" in d
        assert "intervals" in d
        assert "peak_demand_kw" in d
        assert len(d["intervals"]) == 96
        assert "demand_kw" in d["intervals"][0]


# ---------------------------------------------------------------------------
# Current load tests
# ---------------------------------------------------------------------------


class TestGetCurrentLoad:
    """Test current load estimation."""

    def test_returns_positive_value(self, service: LoadForecastService):
        load = service.get_current_load("site-002")
        assert load > 0

    def test_reasonable_range(self, service: LoadForecastService):
        load = service.get_current_load("site-002")
        assert 0 <= load <= 3000, f"Current load should be 0-3000 kW, got {load}"

    def test_unknown_site_fallback(self, service: LoadForecastService):
        load = service.get_current_load("unknown-site")
        assert load > 0, "Should fall back to simulated load for unknown site"


# ---------------------------------------------------------------------------
# Caching tests
# ---------------------------------------------------------------------------


class TestCaching:
    """Test forecast caching."""

    def test_forecast_cached_after_generation(self, service: LoadForecastService):
        service.get_forecast("site-002")
        cached = service.get_cached_forecast("site-002")
        assert cached is not None
        assert cached.site_id == "site-002"

    def test_no_cache_for_unknown_site(self, service: LoadForecastService):
        cached = service.get_cached_forecast("unknown-site")
        assert cached is None


# ---------------------------------------------------------------------------
# Retraining tests
# ---------------------------------------------------------------------------


class TestRetrain:
    """Test model retraining."""

    def test_retrain_success(self, service: LoadForecastService):
        result = service.retrain("site-002")
        assert result is True

    def test_retrain_updates_accuracy(self, service: LoadForecastService):
        accuracy_before = service.get_accuracy("site-002")
        service.retrain("site-002")
        accuracy_after = service.get_accuracy("site-002")
        # Accuracy should be present after retrain
        assert accuracy_after is not None
        assert "r2_score" in accuracy_after

    def test_retrain_unknown_site(self):
        # Fresh service instance for isolation
        svc = LoadForecastService()
        result = svc.retrain("unknown-site")
        # Should still succeed — trains on synthetic data regardless of site
        assert result is True

    def test_retrain_clears_cache(self, service: LoadForecastService):
        service.get_forecast("site-002")
        assert service.get_cached_forecast("site-002") is not None
        service.retrain("site-002")
        assert service.get_cached_forecast("site-002") is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_single_interval_forecast(self, service: LoadForecastService):
        forecast = service.get_forecast("site-002", intervals_ahead=1)
        assert len(forecast.intervals) == 1

    def test_empty_forecast_for_unmodeled_site(self):
        svc = LoadForecastService()
        # Unknown site without model
        svc._models.pop("unknown", None)
        forecast = svc.get_forecast("unknown")
        assert len(forecast.intervals) == 0

    def test_interval_to_dict(self):
        interval = LoadInterval(
            timestamp="2026-02-24T10:00",
            demand_kw=1500.123,
            confidence_high_kw=1600.456,
            confidence_low_kw=1400.789,
            is_peak_hour=False,
            tariff_band="standard",
        )
        d = interval.to_dict()
        assert d["demand_kw"] == 1500.1
        assert d["confidence_high_kw"] == 1600.5
        assert d["confidence_low_kw"] == 1400.8

    def test_load_forecast_to_dict_without_accuracy(self):
        forecast = LoadForecast(
            site_id="test",
            generated_at="2026-02-24T00:00:00Z",
            model="gradient_boosting",
        )
        d = forecast.to_dict()
        assert "accuracy" not in d

    def test_seasonal_temps_all_months(self):
        for month in range(1, 13):
            assert month in _SEASONAL_TEMPS
            assert 10 <= _SEASONAL_TEMPS[month] <= 30
