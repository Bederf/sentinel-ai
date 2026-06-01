"""Tests for residential_solar profile loading."""

from __future__ import annotations

from app.services.profile_service import ProfileService


class TestResidentialSolarProfile:
    def setup_method(self):
        self.ps = ProfileService()

    def test_residential_solar_in_profiles(self):
        assert "residential_solar" in self.ps.profiles

    def test_residential_solar_has_weights(self):
        p = self.ps.profiles["residential_solar"]
        assert "weights" in p
        weights = p["weights"]
        assert weights["cost"] == 0.35
        assert weights["energy"] == 0.30
        assert weights["runtime"] == 0.20
        assert weights["comfort"] == 0.10
        assert weights["maintenance"] == 0.05

    def test_weights_sum_to_one(self):
        p = self.ps.profiles["residential_solar"]
        total = sum(p["weights"].values())
        assert abs(total - 1.0) < 1e-9

    def test_residential_solar_has_thresholds(self):
        p = self.ps.profiles["residential_solar"]
        t = p["thresholds"]
        assert t["battery_soc_critical"] == 10
        assert t["battery_soc_pre_shed"] == 30
        assert t["geyser_solar_threshold_w"] == 1500
        assert t["pv_surplus_opportunity_w"] == 1500

    def test_site_type_is_residential(self):
        p = self.ps.profiles["residential_solar"]
        assert p.get("site_type") == "residential"

    def test_auto_execute_false(self):
        p = self.ps.profiles["residential_solar"]
        assert p.get("auto_execute") is False

    def test_delivery_channel_telegram(self):
        p = self.ps.profiles["residential_solar"]
        assert p.get("delivery_channel") == "telegram"

    def test_dedup_window_4_hours(self):
        p = self.ps.profiles["residential_solar"]
        assert p.get("dedup_window_hours") == 4


class TestGetSiteProfileResidential:
    def setup_method(self):
        self.ps = ProfileService()

    def test_is_residential_site_true_for_res_prefix(self):
        assert self.ps.is_residential_site("res-123") is True
        assert self.ps.is_residential_site("res-999999") is True

    def test_is_residential_site_false_for_commercial(self):
        assert self.ps.is_residential_site("site-002") is False
        assert self.ps.is_residential_site("S002") is False
        assert self.ps.is_residential_site("BLDG-A") is False

    def test_get_residential_profile_returns_copy(self):
        p1 = self.ps.get_residential_profile()
        p2 = self.ps.get_residential_profile()
        assert p1 == p2
        # Modifying returned dict doesn't affect global
        p1["weights"]["cost"] = 99
        p3 = self.ps.get_residential_profile()
        assert p3["weights"]["cost"] == 0.35
