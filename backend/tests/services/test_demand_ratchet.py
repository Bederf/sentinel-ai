"""Tests for demand_ratchet — rolling multi-month demand billing calculator."""

import pytest
from app.services.demand_ratchet import (
    DemandRatchetService,
    get_demand_ratchet_service,
)
from app.services.solar_config_service import clear_config_cache


@pytest.fixture(autouse=True)
def fresh_state():
    """Reset state before each test."""
    clear_config_cache()
    yield


@pytest.fixture
def ratchet_service():
    return DemandRatchetService()


class TestDemandRatchetBasic:
    """Core ratchet calculation tests."""

    def test_calculate_ratchet_returns_result(self, ratchet_service):
        result = ratchet_service.calculate_ratchet("site-002")
        assert result.site_id == "site-002"
        assert result.billing_demand_kva > 0

    def test_billing_demand_gte_current(self, ratchet_service):
        """Billing demand must be >= current month peak (ratchet can only lift)."""
        result = ratchet_service.calculate_ratchet("site-002", current_month_peak_kva=1500.0)
        assert result.billing_demand_kva >= result.current_month_peak_kva

    def test_demand_charge_is_395_48(self, ratchet_service):
        result = ratchet_service.calculate_ratchet("site-002")
        assert result.demand_charge_r_kva == 395.48

    def test_monthly_cost_is_billing_times_charge(self, ratchet_service):
        result = ratchet_service.calculate_ratchet("site-002")
        expected = round(result.billing_demand_kva * result.demand_charge_r_kva, 2)
        assert result.monthly_demand_cost_r == expected

    def test_spike_cost_zero_when_below_target(self, ratchet_service):
        """If current peak is below shaving target, spike cost should be 0."""
        result = ratchet_service.calculate_ratchet("site-002", current_month_peak_kva=1000.0)
        assert result.spike_cost_r == 0.0

    def test_spike_cost_positive_when_above_target(self, ratchet_service):
        """If current peak exceeds shaving target, spike cost should be positive."""
        result = ratchet_service.calculate_ratchet("site-002", current_month_peak_kva=2500.0)
        assert result.spike_cost_r > 0


class TestRatchetMechanism:
    """Test the 12-month ratchet lookback."""

    def test_ratchet_from_history(self, ratchet_service):
        """Ratchet demand should come from the max of trailing months."""
        result = ratchet_service.calculate_ratchet("site-002")
        history = result.ratchet_history
        if history:
            max_trailing = max(r.peak_demand_kva for r in history)
            assert result.ratchet_demand_kva == round(max_trailing, 1)

    def test_ratchet_active_when_history_higher(self, ratchet_service):
        """Ratchet should be active when trailing peak > current month."""
        result = ratchet_service.calculate_ratchet("site-002", current_month_peak_kva=1000.0)
        # Demo history has peaks in 1500-1900 range, so ratchet should be active
        assert result.ratchet_active is True

    def test_ratchet_inactive_when_current_higher(self, ratchet_service):
        """Ratchet should be inactive when current exceeds all trailing months."""
        result = ratchet_service.calculate_ratchet("site-002", current_month_peak_kva=5000.0)
        assert result.ratchet_active is False

    def test_shaving_target_equals_ratchet(self, ratchet_service):
        """Shaving target should equal ratchet demand when ratchet exists."""
        result = ratchet_service.calculate_ratchet("site-002")
        if result.ratchet_demand_kva > 0:
            assert result.shaving_target_kva == result.ratchet_demand_kva

    def test_ratchet_expires_field(self, ratchet_service):
        """Ratchet expiry should be set when ratchet is present."""
        result = ratchet_service.calculate_ratchet("site-002")
        if result.ratchet_demand_kva > 0:
            assert result.ratchet_expires is not None
            # Format: YYYY-MM
            assert len(result.ratchet_expires) == 7
            assert "-" in result.ratchet_expires


class TestDemandHistory:
    """Test demand history management."""

    def test_demo_history_has_12_months(self, ratchet_service):
        history = ratchet_service.get_demand_history("site-002")
        assert len(history) == 12

    def test_demo_peaks_realistic(self, ratchet_service):
        """Demo peaks should be in 1480-1850 kVA range (realistic for site-002)."""
        history = ratchet_service.get_demand_history("site-002")
        for rec in history:
            assert (
                1300 <= rec.peak_demand_kva <= 2000
            ), f"Peak {rec.peak_demand_kva} kVA in {rec.year}-{rec.month:02d} out of range"

    def test_update_current_peak(self, ratchet_service):
        """Updating current peak should create/update a record."""
        ratchet_service.update_current_peak("site-002", 1900.0)
        history = ratchet_service.get_demand_history("site-002")
        from datetime import datetime

        now = datetime.now()
        current_records = [r for r in history if r.year == now.year and r.month == now.month]
        assert len(current_records) >= 1
        assert current_records[0].peak_demand_kva >= 1900.0


class TestSingleton:
    """Test singleton access."""

    def test_get_service_returns_same(self):
        s1 = get_demand_ratchet_service()
        s2 = get_demand_ratchet_service()
        assert s1 is s2
