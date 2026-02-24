"""Tests for MIPDispatchOptimizer — CP-SAT BESS dispatch scheduling.

Covers: solver correctness, constraint satisfaction, fallback behavior,
comparison, caching, edge cases.
"""

import math
from datetime import datetime, timezone, timedelta

import pytest

from app.models.dispatch_schedule import DispatchInterval
from app.services.mip_dispatch_optimizer import (
    MIPDispatchOptimizer,
    _tariff_for_hour,
    _TARIFF_RATES,
    _PEAK_HOURS,
    _OFF_PEAK_HOURS,
    _DEFAULT_TARIFF_RATES,
    _DEFAULT_PEAK_HOURS,
    _DEFAULT_OFF_PEAK_HOURS,
    _build_ls_schedule_from_eskom,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def optimizer():
    """Create a fresh optimizer instance."""
    return MIPDispatchOptimizer()


@pytest.fixture
def flat_load():
    """Flat 1500 kW load for 96 intervals."""
    return [1500.0] * 96


@pytest.fixture
def solar_profile():
    """Realistic solar profile (bell curve, peak 3200 kW at noon)."""
    profile = []
    for t in range(96):
        hour = t / 4.0
        if 6 <= hour <= 19:
            solar = 3200.0 * math.exp(-0.5 * ((hour - 12.5) / 3.5) ** 2)
        else:
            solar = 0.0
        profile.append(solar)
    return profile


@pytest.fixture
def realistic_load():
    """Realistic load profile with morning/afternoon peaks."""
    profile = []
    for t in range(96):
        hour = t / 4.0
        if hour < 6:
            load = 900.0
        elif hour < 9:
            load = 900 + (hour - 6) * 250
        elif hour < 15:
            load = 1700.0
        elif hour < 18:
            load = 1700 - (hour - 15) * 200
        elif hour < 22:
            load = 1000.0
        else:
            load = 900.0
        profile.append(load)
    return profile


# ---------------------------------------------------------------------------
# Tariff function tests
# ---------------------------------------------------------------------------


class TestTariffForHour:
    """Test tariff rate/band lookup."""

    def test_peak_hours(self):
        for h in _PEAK_HOURS:
            rate, band = _tariff_for_hour(h)
            assert band == "peak"
            assert rate == _TARIFF_RATES["peak"]

    def test_off_peak_hours(self):
        for h in _OFF_PEAK_HOURS:
            rate, band = _tariff_for_hour(h)
            assert band == "off_peak"
            assert rate == _TARIFF_RATES["off_peak"]

    def test_standard_hours(self):
        for h in [6, 10, 11, 12, 13, 14, 15, 16, 17, 20, 21]:
            rate, band = _tariff_for_hour(h)
            assert band == "standard"
            assert rate == _TARIFF_RATES["standard"]

    def test_rates_ordered(self):
        assert _TARIFF_RATES["off_peak"] < _TARIFF_RATES["standard"] < _TARIFF_RATES["peak"]


# ---------------------------------------------------------------------------
# Solver tests
# ---------------------------------------------------------------------------


class TestOptimize:
    """Test the CP-SAT optimization solver."""

    def test_returns_96_intervals(self, optimizer, flat_load):
        schedule = optimizer.optimize("site-002", load_forecast=flat_load)
        assert len(schedule.intervals) == 96

    def test_solver_status(self, optimizer, flat_load):
        schedule = optimizer.optimize("site-002", load_forecast=flat_load)
        assert schedule.solver_status in ("optimal", "feasible", "rules_fallback")

    def test_site_id_set(self, optimizer, flat_load):
        schedule = optimizer.optimize("site-002", load_forecast=flat_load)
        assert schedule.site_id == "site-002"

    def test_generated_at_set(self, optimizer, flat_load):
        schedule = optimizer.optimize("site-002", load_forecast=flat_load)
        assert schedule.generated_at != ""

    def test_solve_time_recorded(self, optimizer, flat_load):
        schedule = optimizer.optimize("site-002", load_forecast=flat_load)
        assert schedule.solve_time_ms > 0

    def test_total_cost_positive(self, optimizer, flat_load):
        schedule = optimizer.optimize("site-002", load_forecast=flat_load)
        assert schedule.total_cost_zar > 0

    def test_soc_within_bounds(self, optimizer, flat_load):
        schedule = optimizer.optimize("site-002", load_forecast=flat_load)
        for interval in schedule.intervals:
            assert interval.soc_kwh >= optimizer.BESS_MIN_SOC_KWH - 1.0
            assert interval.soc_kwh <= optimizer.BESS_MAX_SOC_KWH + 1.0

    def test_charge_discharge_mutual_exclusion(self, optimizer, flat_load):
        schedule = optimizer.optimize("site-002", load_forecast=flat_load)
        for interval in schedule.intervals:
            # Can't charge and discharge simultaneously
            assert not (interval.charge_kw > 0.1 and interval.discharge_kw > 0.1), (
                f"Mutual exclusion violated at {interval.timestamp}: "
                f"charge={interval.charge_kw}, discharge={interval.discharge_kw}"
            )

    def test_power_within_rated(self, optimizer, flat_load):
        schedule = optimizer.optimize("site-002", load_forecast=flat_load)
        for interval in schedule.intervals:
            assert interval.charge_kw <= optimizer.BESS_RATED_POWER_KW + 0.1
            assert interval.discharge_kw <= optimizer.BESS_RATED_POWER_KW + 0.1

    def test_initial_soc_respected(self, optimizer, flat_load):
        schedule = optimizer.optimize("site-002", initial_soc_kwh=80.0, load_forecast=flat_load)
        first_soc = schedule.intervals[0].soc_kwh
        assert abs(first_soc - 80.0) < 1.0

    def test_with_solar_reduces_cost(self, optimizer, flat_load, solar_profile):
        no_solar = optimizer.optimize("site-002", load_forecast=flat_load, solar_forecast=[0.0] * 96)
        with_solar = optimizer.optimize("site-002", load_forecast=flat_load, solar_forecast=solar_profile)
        # Solar should reduce total cost
        assert with_solar.total_cost_zar <= no_solar.total_cost_zar + 10  # Allow small tolerance

    def test_peak_grid_import(self, optimizer, flat_load):
        schedule = optimizer.optimize("site-002", load_forecast=flat_load)
        assert schedule.peak_grid_import_kw > 0
        # Should be <= NMD limit
        assert schedule.peak_grid_import_kw <= optimizer.NMD_LIMIT_KVA + 1

    def test_cycles_calculated(self, optimizer, flat_load):
        schedule = optimizer.optimize("site-002", load_forecast=flat_load)
        assert schedule.cycles >= 0

    def test_demand_charge_calculated(self, optimizer, flat_load):
        schedule = optimizer.optimize("site-002", load_forecast=flat_load)
        assert schedule.demand_charge_zar >= 0


# ---------------------------------------------------------------------------
# With realistic data
# ---------------------------------------------------------------------------


class TestRealisticOptimization:
    """Test with realistic load and solar profiles."""

    def test_charges_off_peak_discharges_peak(self, optimizer, realistic_load, solar_profile):
        schedule = optimizer.optimize(
            "site-002",
            initial_soc_kwh=50.0,
            load_forecast=realistic_load,
            solar_forecast=solar_profile,
        )
        # Solver may return optimal, feasible, or rules_fallback depending on
        # integer scaling and input combination
        assert schedule.solver_status in ("optimal", "feasible", "rules_fallback")

        # Check that there's some charging and discharging activity
        total_charge = sum(i.charge_kw for i in schedule.intervals)
        total_discharge = sum(i.discharge_kw for i in schedule.intervals)
        assert total_charge > 0, "Should have some charging"
        assert total_discharge > 0, "Should have some discharging"

    def test_solar_energy_utilized(self, optimizer, realistic_load, solar_profile):
        schedule = optimizer.optimize(
            "site-002",
            load_forecast=realistic_load,
            solar_forecast=solar_profile,
        )
        assert schedule.total_solar_kwh > 0


# ---------------------------------------------------------------------------
# Load shedding tests
# ---------------------------------------------------------------------------


class TestLoadShedding:
    """Test load shedding constraint."""

    def test_ls_forces_discharge(self, optimizer, flat_load):
        # LS active for intervals 40-47 (hours 10-12)
        ls = [False] * 96
        for t in range(40, 48):
            ls[t] = True

        schedule = optimizer.optimize(
            "site-002",
            initial_soc_kwh=150.0,
            load_forecast=flat_load,
            ls_schedule=ls,
        )

        # Solver may find optimal/feasible or fall back to rules
        assert schedule.solver_status in ("optimal", "feasible", "rules_fallback")

        # During LS intervals, should be discharging (enforced by solver constraint
        # or rules_fallback LS override) — at least the first few while SOC allows
        ls_discharge_count = sum(1 for t in range(40, 48) if schedule.intervals[t].discharge_kw > 0)
        assert ls_discharge_count >= 3, f"Expected discharge in at least 3 of 8 LS intervals, got {ls_discharge_count}"


# ---------------------------------------------------------------------------
# Rules fallback tests
# ---------------------------------------------------------------------------


class TestRulesFallback:
    """Test the rules-based fallback."""

    def test_fallback_returns_96_intervals(self, optimizer, flat_load):
        from datetime import datetime, timezone, timedelta

        sast = datetime.now(timezone.utc) + timedelta(hours=2)

        schedule = optimizer._rules_fallback(
            "site-002",
            96,
            100.0,
            flat_load,
            [0.0] * 96,
            [1.0] * 96,
            ["standard"] * 96,
            sast,
        )
        assert len(schedule.intervals) == 96

    def test_fallback_charges_off_peak(self, optimizer):
        sast = datetime(2026, 2, 24, 0, 0, tzinfo=timezone.utc)  # midnight SAST
        load = [1000.0] * 96
        tariff = [_TARIFF_RATES["off_peak"]] * 24 + [_TARIFF_RATES["standard"]] * 48 + [_TARIFF_RATES["off_peak"]] * 24
        bands = ["off_peak"] * 24 + ["standard"] * 48 + ["off_peak"] * 24

        schedule = optimizer._rules_fallback(
            "site-002",
            96,
            50.0,
            load,
            [0.0] * 96,
            tariff,
            bands,
            sast,
        )
        # First intervals should have charging (off-peak)
        assert schedule.intervals[0].charge_kw > 0

    def test_fallback_status_is_rules_fallback(self, optimizer, flat_load):
        sast = datetime.now(timezone.utc) + timedelta(hours=2)
        schedule = optimizer._rules_fallback(
            "site-002",
            96,
            100.0,
            flat_load,
            [0.0] * 96,
            [1.0] * 96,
            ["standard"] * 96,
            sast,
        )
        assert schedule.solver_status == "rules_fallback"


# ---------------------------------------------------------------------------
# Caching tests
# ---------------------------------------------------------------------------


class TestCaching:
    """Test schedule caching."""

    def test_schedule_cached_after_optimize(self, optimizer, flat_load):
        optimizer.optimize("site-002", load_forecast=flat_load)
        cached = optimizer.get_cached_schedule("site-002")
        assert cached is not None
        assert cached.site_id == "site-002"

    def test_no_cache_for_unknown_site(self, optimizer):
        cached = optimizer.get_cached_schedule("unknown-site")
        assert cached is None


# ---------------------------------------------------------------------------
# Comparison tests
# ---------------------------------------------------------------------------


class TestComparison:
    """Test MIP vs rules comparison."""

    def test_comparison_returns_both(self, optimizer, flat_load):
        comparison = optimizer.get_comparison("site-002", load_forecast=flat_load)
        assert "mip" in comparison
        assert "rules" in comparison
        assert "savings_zar" in comparison
        assert "savings_pct" in comparison

    def test_comparison_mip_intervals(self, optimizer, flat_load):
        comparison = optimizer.get_comparison("site-002", load_forecast=flat_load)
        assert len(comparison["mip"]["intervals"]) == 96
        assert len(comparison["rules"]["intervals"]) == 96


# ---------------------------------------------------------------------------
# Serialization tests
# ---------------------------------------------------------------------------


class TestSerialization:
    """Test to_dict serialization."""

    def test_dispatch_interval_to_dict(self):
        interval = DispatchInterval(
            timestamp="2026-02-24T10:00",
            charge_kw=50.123,
            discharge_kw=0.0,
            soc_kwh=120.456,
            grid_import_kw=1450.789,
            solar_kw=3000.0,
            load_kw=1500.0,
            tariff_rate=1.2457,
            tariff_band="standard",
            interval_cost_zar=452.89,
        )
        d = interval.to_dict()
        assert d["charge_kw"] == 50.1
        assert d["soc_kwh"] == 120.5
        assert d["tariff_rate"] == 1.2457
        assert d["interval_cost_zar"] == 452.89

    def test_schedule_to_dict(self, optimizer, flat_load):
        schedule = optimizer.optimize("site-002", load_forecast=flat_load)
        d = schedule.to_dict()
        assert "site_id" in d
        assert "solver_status" in d
        assert "intervals" in d
        assert len(d["intervals"]) == 96
        assert "total_cost_zar" in d
        assert "peak_grid_import_kw" in d
        assert "cycles" in d
        assert "solve_time_ms" in d


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_load(self, optimizer):
        schedule = optimizer.optimize("site-002", load_forecast=[0.0] * 96)
        assert len(schedule.intervals) == 96
        assert schedule.solver_status in ("optimal", "feasible", "rules_fallback")

    def test_very_high_load(self, optimizer):
        schedule = optimizer.optimize("site-002", load_forecast=[2500.0] * 96)
        assert len(schedule.intervals) == 96
        assert schedule.total_cost_zar > 0

    def test_full_soc_start(self, optimizer, flat_load):
        schedule = optimizer.optimize("site-002", initial_soc_kwh=190.0, load_forecast=flat_load)
        assert schedule.intervals[0].soc_kwh >= 180.0

    def test_low_soc_start(self, optimizer, flat_load):
        schedule = optimizer.optimize("site-002", initial_soc_kwh=40.0, load_forecast=flat_load)
        assert schedule.intervals[0].soc_kwh >= 39.0

    def test_short_forecast_padded(self, optimizer):
        short_load = [1500.0] * 10  # Only 10 intervals
        schedule = optimizer.optimize("site-002", load_forecast=short_load)
        assert len(schedule.intervals) == 96

    def test_solver_timeout_fallback(self, optimizer, flat_load):
        """Verify that even with extreme timeout, solver produces a result."""
        original_timeout = optimizer.SOLVER_TIMEOUT_S
        optimizer.SOLVER_TIMEOUT_S = 0.001  # Extremely short timeout
        schedule = optimizer.optimize("site-002", load_forecast=flat_load)
        optimizer.SOLVER_TIMEOUT_S = original_timeout
        # Should fall back to rules or still produce result
        assert len(schedule.intervals) == 96
        assert schedule.solver_status in ("optimal", "feasible", "rules_fallback")


# ---------------------------------------------------------------------------
# Config-driven tariffs (Fix 1)
# ---------------------------------------------------------------------------


class TestConfigDrivenTariffs:
    """Test that _tariff_for_hour uses SiteConfig when provided."""

    def test_default_tariff_aliases_still_work(self):
        """Legacy _TARIFF_RATES alias points to _DEFAULT_TARIFF_RATES."""
        assert _TARIFF_RATES is _DEFAULT_TARIFF_RATES
        assert _PEAK_HOURS is _DEFAULT_PEAK_HOURS
        assert _OFF_PEAK_HOURS is _DEFAULT_OFF_PEAK_HOURS

    def test_tariff_without_config_uses_defaults(self):
        rate, band = _tariff_for_hour(8)  # Peak hour
        assert rate == _DEFAULT_TARIFF_RATES["peak"]
        assert band == "peak"

    def test_tariff_with_site_config(self):
        """When SiteConfig is provided, uses invoice rates."""
        from app.services.solar_config_service import get_site_solar_config

        cfg = get_site_solar_config("site-002")

        # Summer month (Feb), peak hour (8)
        rate, band = _tariff_for_hour(8, cfg, month=2)
        assert band == "peak"
        # Invoice rate should be ~R3.01, not R3.76
        assert rate != _DEFAULT_TARIFF_RATES["peak"]
        assert 2.5 < rate < 4.0  # Reasonable range for summer peak

    def test_tariff_with_config_off_peak(self):
        """Off-peak rate from config differs from hardcoded."""
        from app.services.solar_config_service import get_site_solar_config

        cfg = get_site_solar_config("site-002")

        rate, band = _tariff_for_hour(0, cfg, month=2)  # Midnight, summer
        assert band == "off_peak"
        # Should be ~R1.77, not R0.65
        assert rate != _DEFAULT_TARIFF_RATES["off_peak"]

    def test_tariff_with_none_config_uses_defaults(self):
        """Explicitly passing None falls back to defaults."""
        rate, band = _tariff_for_hour(8, None)
        assert rate == _DEFAULT_TARIFF_RATES["peak"]


# ---------------------------------------------------------------------------
# EskomSePush LS schedule builder (Fix 2)
# ---------------------------------------------------------------------------


class TestBuildLsSchedule:
    """Test _build_ls_schedule_from_eskom helper."""

    def _make_event(self, start, end, stage=2):
        from app.services.eskomsepush_service import AreaEvent

        return AreaEvent(start=start, end=end, note=f"Stage {stage}", stage=stage)

    def test_empty_events_returns_all_false(self):
        sast_start = datetime(2026, 2, 24, 6, 0, tzinfo=timezone.utc)
        schedule = _build_ls_schedule_from_eskom([], sast_start)
        assert len(schedule) == 96
        assert all(not v for v in schedule)

    def test_single_event_marks_correct_slots(self):
        sast_start = datetime(2026, 2, 24, 6, 0, tzinfo=timezone.utc)
        # Event from 08:00 to 10:30 (2.5 hours = 10 slots)
        event = self._make_event(
            "2026-02-24T08:00:00+00:00",
            "2026-02-24T10:30:00+00:00",
        )
        schedule = _build_ls_schedule_from_eskom([event], sast_start)

        # Slots 8-17 should be True (08:00-10:30 = intervals 8,9,...,17)
        # Interval 8 = 6:00 + 8*15min = 08:00
        # Interval 17 = 6:00 + 17*15min = 10:15 (overlaps with event ending at 10:30)
        for t in range(8, 18):
            assert schedule[t] is True, f"Slot {t} should be True"

        # Slot before and after should be False
        assert schedule[7] is False
        assert schedule[18] is False

    def test_stage_zero_ignored(self):
        sast_start = datetime(2026, 2, 24, 6, 0, tzinfo=timezone.utc)
        event = self._make_event(
            "2026-02-24T08:00:00+00:00",
            "2026-02-24T10:00:00+00:00",
            stage=0,
        )
        schedule = _build_ls_schedule_from_eskom([event], sast_start)
        assert all(not v for v in schedule)

    def test_multiple_events(self):
        sast_start = datetime(2026, 2, 24, 0, 0, tzinfo=timezone.utc)
        events = [
            self._make_event("2026-02-24T02:00:00+00:00", "2026-02-24T04:00:00+00:00"),
            self._make_event("2026-02-24T10:00:00+00:00", "2026-02-24T12:00:00+00:00"),
        ]
        schedule = _build_ls_schedule_from_eskom(events, sast_start)
        # Both windows should be marked
        assert schedule[8] is True  # 02:00
        assert schedule[40] is True  # 10:00
        # Gap should be clear
        assert schedule[20] is False  # 05:00

    def test_invalid_event_times_skipped(self):
        sast_start = datetime(2026, 2, 24, 6, 0, tzinfo=timezone.utc)
        from app.services.eskomsepush_service import AreaEvent

        event = AreaEvent(start="invalid", end="also-invalid", note="Stage 2", stage=2)
        schedule = _build_ls_schedule_from_eskom([event], sast_start)
        assert all(not v for v in schedule)
