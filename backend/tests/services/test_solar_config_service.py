"""Tests for solar_config_service — single source of truth for solar/BESS/tariff parameters."""

import pytest
from app.services.solar_config_service import (
    get_site_solar_config,
    clear_config_cache,
    SiteConfig,
)


@pytest.fixture(autouse=True)
def fresh_cache():
    """Clear config cache before each test."""
    clear_config_cache()
    yield
    clear_config_cache()


class TestSiteConfigLoading:
    """Verify site-002 config loads correct values from JSON files."""

    def test_loads_site_002(self):
        cfg = get_site_solar_config("site-002")
        assert isinstance(cfg, SiteConfig)
        assert cfg.site_id == "site-002"

    def test_bess_capacity_200kwh(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.bess.capacity_kwh == 200.0

    def test_bess_rated_power_100kw(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.bess.rated_power_kw == 100.0

    def test_bess_model(self):
        cfg = get_site_solar_config("site-002")
        assert "LUNA2000" in cfg.bess.model

    def test_pv_total_capacity_297kwp(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.pv.total_capacity_kwp == 297.0

    def test_pv_all_roof_no_carport(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.pv.roof_capacity_kwp == 297.0
        assert cfg.pv.carport_capacity_kwp == 0.0
        assert cfg.pv.roof_capacity_kwp == cfg.pv.total_capacity_kwp

    def test_grid_nmd_1820(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.grid.nmd_limit_kva == 1820.0

    def test_grid_max_export_297(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.grid.max_export_kw == 297.0

    def test_grid_sseg_category_b(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.grid.sseg_category == "B"


class TestTariffRates:
    """Verify City Power LPU-TOU 2025/26 tariff rates."""

    def test_demand_charge_395_48(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.tariff.demand_charge_r_kva() == 395.48

    def test_summer_peak_295_39(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.tariff.summer_peak_c_kwh == 295.39

    def test_summer_standard_222_39(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.tariff.summer_standard_c_kwh == 222.39

    def test_summer_off_peak_170_95(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.tariff.summer_off_peak_c_kwh == 170.95

    def test_winter_peak_827_09(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.tariff.winter_peak_c_kwh == 827.09

    def test_network_charge_flat_6(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.tariff.network_charge_c_kwh == 6.0

    def test_feed_in_rate_78_5(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.tariff.feed_in_rate_c_kwh == 78.5

    def test_service_charge(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.tariff.service_charge_r_month == 11658.08

    def test_rate_r_kwh_summer_peak(self):
        """Summer peak R/kWh = (295.39 + 6.0) / 100 = 3.0139."""
        cfg = get_site_solar_config("site-002")
        rate = cfg.tariff.summer_peak_r_kwh
        assert abs(rate - 3.0139) < 0.001

    def test_rate_r_kwh_summer_standard(self):
        """Summer standard R/kWh = (222.39 + 6.0) / 100 = 2.2839."""
        cfg = get_site_solar_config("site-002")
        rate = cfg.tariff.summer_standard_r_kwh
        assert abs(rate - 2.2839) < 0.001

    def test_rate_r_kwh_summer_off_peak(self):
        """Summer off-peak R/kWh = (170.95 + 6.0) / 100 = 1.7695."""
        cfg = get_site_solar_config("site-002")
        rate = cfg.tariff.summer_off_peak_r_kwh
        assert abs(rate - 1.7695) < 0.001


class TestTimeBands:
    """Verify TOU time band classification."""

    def test_summer_months(self):
        cfg = get_site_solar_config("site-002")
        assert 1 in cfg.time_bands.summer_months  # Jan
        assert 12 in cfg.time_bands.summer_months  # Dec

    def test_winter_months(self):
        cfg = get_site_solar_config("site-002")
        assert 6 in cfg.time_bands.winter_months
        assert 7 in cfg.time_bands.winter_months
        assert 8 in cfg.time_bands.winter_months

    def test_summer_peak_at_8am(self):
        cfg = get_site_solar_config("site-002")
        period = cfg.time_bands.get_period(8, 1)  # 8am January
        assert period == "peak"

    def test_summer_standard_at_noon(self):
        cfg = get_site_solar_config("site-002")
        period = cfg.time_bands.get_period(12, 2)  # noon February
        assert period == "standard"

    def test_summer_off_peak_at_midnight(self):
        cfg = get_site_solar_config("site-002")
        period = cfg.time_bands.get_period(0, 1)  # midnight January
        assert period == "off_peak"

    def test_winter_peak_at_7am(self):
        cfg = get_site_solar_config("site-002")
        period = cfg.time_bands.get_period(7, 7)  # 7am July
        assert period == "peak"

    def test_get_season(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.time_bands.get_season(7) == "winter"
        assert cfg.time_bands.get_season(1) == "summer"


class TestConfigCaching:
    """Verify caching behaviour."""

    def test_same_object_returned(self):
        cfg1 = get_site_solar_config("site-002")
        cfg2 = get_site_solar_config("site-002")
        assert cfg1 is cfg2

    def test_cache_clear(self):
        cfg1 = get_site_solar_config("site-002")
        clear_config_cache()
        cfg2 = get_site_solar_config("site-002")
        assert cfg1 is not cfg2
        assert cfg1.bess.capacity_kwh == cfg2.bess.capacity_kwh


class TestNoStaleConstants:
    """Acceptance: no remaining wrong constants in the config path."""

    def test_no_5015(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.bess.capacity_kwh != 5015.0

    def test_no_2507(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.bess.rated_power_kw != 2507.0

    def test_no_6000_nmd(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.grid.nmd_limit_kva != 6000.0

    def test_no_155_50(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.tariff.demand_charge_r_kva() != 155.50

    def test_no_3875(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.pv.total_capacity_kwp != 3875.0

    def test_no_946_pv(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.pv.total_capacity_kwp != 946.0

    def test_no_500_bess(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.bess.capacity_kwh != 500.0

    def test_no_250_bess_power(self):
        cfg = get_site_solar_config("site-002")
        assert cfg.bess.rated_power_kw != 250.0
