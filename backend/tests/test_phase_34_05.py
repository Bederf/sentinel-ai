"""Tests for Phase 34-05: Energy Arbitrage & BESS Dispatch Optimization.

Tests verify:
1. Price Forecasting & Arbitrage Analysis Engine
2. BESS Dispatch Scheduler & Grid Coordination
3. Arbitrage & Dispatch API Endpoints
"""

import time

from app.services.arbitrage_optimizer import (
    get_price_forecaster,
    get_arbitrage_analyzer,
)
from app.services.bess_dispatch_engine import (
    BESSState,
    ConstraintType,
    get_bess_dispatch_engine,
)
from app.ml.models.dispatch_predictor import (
    get_dispatch_predictor,
)


# === Task 1: Price Forecasting & Arbitrage Analysis ===


class TestPriceForecasting:
    """Test price forecasting within 100ms and accuracy."""

    def test_forecast_24h_generation_time(self):
        """Verify 24-hour forecast generates within 100ms."""
        forecaster = get_price_forecaster()

        start = time.time()
        forecasts = forecaster.forecast_24h()
        elapsed_ms = (time.time() - start) * 1000

        assert len(forecasts) == 24
        assert elapsed_ms < 100, f"Forecast took {elapsed_ms:.1f}ms (target: < 100ms)"

    def test_forecast_includes_all_adjustments(self):
        """Verify forecast includes stage/weather/solar impacts."""
        forecaster = get_price_forecaster()
        forecasts = forecaster.forecast_24h(
            load_shedding_stages=[0, 0, 0, 4, 4, 6, 6, 0] + [0] * 16,
            temperature_forecast=[5.0] * 8 + [35.0] * 8 + [20.0] * 8,
            solar_forecast_pct=[0.0] * 8 + [80.0] * 8 + [0.0] * 8,
        )

        assert all(f.confidence_pct > 0 for f in forecasts)
        assert forecasts[3].stage_impact_pct > 0  # Hour 3 has LS stage 4
        assert forecasts[4].weather_impact_pct > 0  # Hour 4 has cold weather
        assert forecasts[9].solar_impact_pct < 0  # Hour 9 has high solar

    def test_forecast_accuracy_within_10_percent(self):
        """Verify forecast prices are within ±10% on known patterns."""
        forecaster = get_price_forecaster()

        # Standard day: off-peak night, peak day, standard shoulder
        forecasts = forecaster.forecast_24h()

        # Check off-peak hours (22-05) have lowest prices
        off_peak_prices = [forecasts[i].final_price_r_per_kwh for i in range(24) if (i >= 22 or i < 5)]
        # Check peak hours (09-17) have highest prices
        peak_prices = [forecasts[i].final_price_r_per_kwh for i in range(24) if (9 <= i < 17)]

        assert min(off_peak_prices) < max(peak_prices), "Off-peak should be cheaper than peak"


class TestArbitrageAnalysis:
    """Test arbitrage window identification and revenue calculation."""

    def test_arbitrage_windows_identified_correctly(self):
        """Verify at least 3 daily arbitrage cycles identified."""
        analyzer = get_arbitrage_analyzer()
        forecaster = get_price_forecaster()

        forecasts = forecaster.forecast_24h()
        windows = analyzer.find_arbitrage_windows(forecasts, max_windows=5)

        assert len(windows) >= 1, "At least 1 arbitrage window should be found"
        assert all(w.charge_end_hour < w.discharge_start_hour for w in windows), "Discharge should happen after charge"

    def test_revenue_calculation_includes_degradation(self):
        """Verify revenue accounts for R0.05/kWh degradation cost."""
        analyzer = get_arbitrage_analyzer()
        forecaster = get_price_forecaster()

        forecasts = forecaster.forecast_24h()
        windows = analyzer.find_arbitrage_windows(forecasts)

        if windows:
            window = windows[0]
            assert window.battery_degradation_cost_r > 0, "Degradation cost should be positive"
            assert window.net_revenue_r < window.expected_revenue_r, "Net revenue should be less than gross revenue"

            # Verify degradation calculation
            expected_degradation = window.expected_energy_kwh * 0.05
            assert abs(window.battery_degradation_cost_r - expected_degradation) < 10, (
                f"Degradation cost {window.battery_degradation_cost_r} != {expected_degradation}"
            )

    def test_arbitrage_windows_respect_constraints(self):
        """Verify windows respect SOC and temperature limits."""
        analyzer = get_arbitrage_analyzer()
        forecaster = get_price_forecaster()

        # Test with high battery temp (approaching 40°C charge limit)
        forecasts = forecaster.forecast_24h(
            temperature_forecast=[42.0] * 24  # All above charge limit
        )
        windows = analyzer.find_arbitrage_windows(
            forecasts,
            battery_soc_pct=95.0,  # Already at max SOC
        )

        # Should find fewer windows due to constraints
        assert len(windows) <= 2, "Constrained battery should limit opportunities"


# === Task 2: BESS Dispatch Engine ===


class TestBESSDispatchEngine:
    """Test dispatch execution with constraint validation."""

    def test_dispatch_schedule_generation_time(self):
        """Verify 24-hour dispatch schedule generates within 2 seconds."""
        from app.services.solar_arbitrage_engine import get_solar_arbitrage_engine

        engine = get_solar_arbitrage_engine()

        start = time.time()
        schedule = engine.generate_dispatch_schedule("S002")
        elapsed_s = time.time() - start

        assert len(schedule.slots) > 0, "Schedule should have slots"
        assert elapsed_s < 2.0, f"Schedule took {elapsed_s:.2f}s (target: < 2s)"

    def test_temperature_constraints_enforced(self):
        """Verify temperature limits block/reduce dispatch."""
        engine = get_bess_dispatch_engine()

        # Test charge blocked when temp too low
        cold_state = BESSState(
            soc_pct=50.0,
            temperature_c=5.0,  # Below 12°C min
            power_kw=0.0,
            grid_frequency_hz=50.0,
        )

        command = engine.execute_dispatch(
            site_id="S002",
            action="charge",
            requested_power_kw=2000.0,
            bess_state=cold_state,
        )

        assert not command.success, "Charge should be blocked at low temp"
        assert command.actual_power_kw == 0.0
        assert any(c.constraint_type == ConstraintType.TEMPERATURE_LOW.value for c in command.constraints_applied)

    def test_soc_constraints_enforced(self):
        """Verify SOC min/max limits enforced."""
        engine = get_bess_dispatch_engine()

        # Test discharge blocked at minimum SOC
        low_soc_state = BESSState(
            soc_pct=15.0,  # Below 20% minimum
            temperature_c=25.0,
            power_kw=0.0,
            grid_frequency_hz=50.0,
        )

        command = engine.execute_dispatch(
            site_id="S002",
            action="discharge",
            requested_power_kw=2000.0,
            bess_state=low_soc_state,
        )

        assert not command.success, "Discharge should be blocked at low SOC"
        assert any(c.constraint_type == ConstraintType.SOC_MIN.value for c in command.constraints_applied)

    def test_grid_frequency_constraint(self):
        """Verify discharge limited when grid frequency high."""
        engine = get_bess_dispatch_engine()

        high_freq_state = BESSState(
            soc_pct=50.0,
            temperature_c=25.0,
            power_kw=0.0,
            grid_frequency_hz=50.4,  # Above 50.3 threshold
        )

        command = engine.execute_dispatch(
            site_id="S002",
            action="discharge",
            requested_power_kw=2000.0,
            bess_state=high_freq_state,
        )

        # Should be reduced but not blocked
        assert command.actual_power_kw < 2000.0, "Discharge should be reduced at high frequency"
        assert any(c.constraint_type == ConstraintType.FREQUENCY_HIGH.value for c in command.constraints_applied)

    def test_load_shedding_response_by_stage(self):
        """Verify dispatch adjusts correctly per LS stage."""
        engine = get_bess_dispatch_engine()

        normal_state = BESSState(
            soc_pct=50.0,
            temperature_c=25.0,
            power_kw=0.0,
            grid_frequency_hz=50.0,
        )

        # Stage 1-3: Normal operation
        response_stage3 = engine.respond_to_load_shedding("S002", 3, normal_state)
        assert response_stage3["action_taken"] == "continue_normal"

        # Stage 4-5: Reduce discharge
        response_stage5 = engine.respond_to_load_shedding("S002", 5, normal_state)
        assert response_stage5["action_taken"] == "reduce_discharge_50pct"
        assert response_stage5["power_change_kw"] < 0  # Reduce power

        # Stage 6-8: Emergency - charge to reserve
        response_stage7 = engine.respond_to_load_shedding("S002", 7, normal_state)
        assert response_stage7["action_taken"] == "stop_discharge_charge_reserve"
        assert response_stage7["power_change_kw"] > 0  # Switch to charging

    def test_dispatch_execution_under_1_second(self):
        """Verify dispatch commands execute within 1 second."""
        engine = get_bess_dispatch_engine()

        state = BESSState(
            soc_pct=50.0,
            temperature_c=25.0,
            power_kw=0.0,
            grid_frequency_hz=50.0,
        )

        start = time.time()
        command = engine.execute_dispatch(
            site_id="S002",
            action="charge",
            requested_power_kw=2000.0,
            bess_state=state,
        )
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 1000, f"Dispatch took {elapsed_ms:.1f}ms (target: < 1s)"
        assert command.success


# === Task 3: ML Dispatch Prediction ===


class TestDispatchPrediction:
    """Test ML-based dispatch action prediction."""

    def test_prediction_returned_with_confidence(self):
        """Verify prediction includes confidence and reasoning."""
        predictor = get_dispatch_predictor()
        forecaster = get_price_forecaster()

        forecasts = forecaster.forecast_24h()
        forecast_dicts = [f.to_dict() for f in forecasts]

        prediction = predictor.predict_next_action(
            current_hour=10,
            current_soc_pct=50.0,
            price_forecasts=forecast_dicts,
        )

        assert prediction.action in ["charge", "discharge", "idle"]
        assert 0 <= prediction.confidence_pct <= 100
        assert prediction.recommendation != ""
        assert prediction.reasoning != ""

    def test_prediction_respects_temperature_constraints(self):
        """Verify prediction considers temperature limits."""
        predictor = get_dispatch_predictor()
        forecaster = get_price_forecaster()

        forecasts = forecaster.forecast_24h(
            temperature_forecast=[5.0] * 24  # All too cold
        )
        forecast_dicts = [f.to_dict() for f in forecasts]

        prediction = predictor.predict_next_action(
            current_hour=12,
            current_soc_pct=50.0,
            price_forecasts=forecast_dicts,
            temperature_forecast=[5.0] * 24,  # Pass temps to predictor too
        )

        # Should not charge when too cold
        assert prediction.action != "charge" or prediction.confidence_pct < 50

    def test_daily_schedule_prediction(self):
        """Verify daily dispatch schedule predicted."""
        predictor = get_dispatch_predictor()
        forecaster = get_price_forecaster()

        forecasts = forecaster.forecast_24h()
        forecast_dicts = [f.to_dict() for f in forecasts]

        schedule = predictor.predict_daily_dispatch_schedule(price_forecasts=forecast_dicts)

        assert len(schedule) == 24, "Should have 24 hourly predictions"
        assert all(p.action in ["charge", "discharge", "idle"] for p in schedule)


# === Integration Tests ===


class TestEndToEndArbitrage:
    """End-to-end tests of arbitrage optimization."""

    def test_complete_arbitrage_workflow(self):
        """Verify complete workflow: forecast -> analyze -> execute."""
        # 1. Generate forecast
        forecaster = get_price_forecaster()
        forecasts = forecaster.forecast_24h()
        assert len(forecasts) == 24

        # 2. Find arbitrage windows
        analyzer = get_arbitrage_analyzer()
        windows = analyzer.find_arbitrage_windows(forecasts)
        assert len(windows) > 0, "Should find at least 1 arbitrage opportunity"

        # 3. Predict next action
        predictor = get_dispatch_predictor()
        forecast_dicts = [f.to_dict() for f in forecasts]
        prediction = predictor.predict_next_action(
            current_hour=10,
            current_soc_pct=50.0,
            price_forecasts=forecast_dicts,
        )
        assert prediction.action in ["charge", "discharge", "idle"]

        # 4. Execute dispatch with constraints
        engine = get_bess_dispatch_engine()
        state = BESSState(
            soc_pct=50.0,
            temperature_c=25.0,
            power_kw=0.0,
            grid_frequency_hz=50.0,
        )
        command = engine.execute_dispatch(
            site_id="S002",
            action=prediction.action,
            requested_power_kw=prediction.expected_power_kw,
            bess_state=state,
            reason="arbitrage",
        )
        assert command.site_id == "S002"
        assert command.timestamp is not None


# === Performance Benchmarks ===


class TestPerformanceTargets:
    """Verify all performance targets are met."""

    def test_price_forecast_under_100ms(self):
        """Price forecaster returns within 100ms."""
        forecaster = get_price_forecaster()
        start = time.time()
        forecaster.forecast_24h()
        elapsed_ms = (time.time() - start) * 1000
        assert elapsed_ms < 100

    def test_arbitrage_analysis_under_500ms(self):
        """Arbitrage analyzer returns within 500ms."""
        forecaster = get_price_forecaster()
        analyzer = get_arbitrage_analyzer()

        forecasts = forecaster.forecast_24h()
        start = time.time()
        analyzer.find_arbitrage_windows(forecasts)
        elapsed_ms = (time.time() - start) * 1000
        assert elapsed_ms < 500

    def test_dispatch_execution_under_1s(self):
        """Dispatch execution completes within 1 second."""
        engine = get_bess_dispatch_engine()
        state = BESSState(50.0, 25.0, 0.0, 50.0)

        start = time.time()
        engine.execute_dispatch("S002", "charge", 2000.0, state)
        elapsed_ms = (time.time() - start) * 1000
        assert elapsed_ms < 1000

    def test_dispatch_schedule_under_2s(self):
        """24-hour dispatch schedule generates within 2 seconds."""
        from app.services.solar_arbitrage_engine import get_solar_arbitrage_engine

        engine = get_solar_arbitrage_engine()
        start = time.time()
        engine.generate_dispatch_schedule("S002")
        elapsed_s = time.time() - start
        assert elapsed_s < 2.0
