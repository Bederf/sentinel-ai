"""Tests for ResidentialRecommendationContext."""

from __future__ import annotations

from app.services.residential.residential_recommendation_context import (
    _PLATFORM_APP_NAMES,
    ENERGY_FIELDS,
    ResidentialRecommendationContext,
)


class TestPlatformAppNames:
    def test_solarman(self):
        assert _PLATFORM_APP_NAMES["solarman"] == "SOLARMAN app"

    def test_victron(self):
        assert _PLATFORM_APP_NAMES["victron"] == "Victron VRM portal"

    def test_home_assistant(self):
        assert _PLATFORM_APP_NAMES["home_assistant"] == "Home Assistant"

    def test_unknown_platform_falls_back(self):
        assert _PLATFORM_APP_NAMES.get("unknown", "unknown") == "unknown"


class TestContextDataclass:
    def test_defaults(self):
        ctx = ResidentialRecommendationContext(
            site_id="res-123",
            platform="solarman",
            platform_app_name="SOLARMAN app",
        )
        assert ctx.site_id == "res-123"
        assert ctx.loadshedding_stage == 0
        assert ctx.battery_soc_pct is None
        assert ctx.geyser_state is None

    def test_all_energy_fields_present(self):
        ctx = ResidentialRecommendationContext(
            site_id="res-456",
            platform="home_assistant",
            platform_app_name="Home Assistant",
            battery_soc_pct=75.0,
            pv_power_w=3000.0,
            grid_power_w=0.0,
            load_power_w=2000.0,
            geyser_state="off",
            geyser_power_w=0.0,
            ev_charger_power_w=0.0,
            loadshedding_stage=2,
            minutes_to_next_slot=45,
            eskom_area_code="jhb-central",
        )
        assert ctx.battery_soc_pct == 75.0
        assert ctx.pv_power_w == 3000.0
        assert ctx.geyser_state == "off"
        assert ctx.loadshedding_stage == 2
        assert ctx.minutes_to_next_slot == 45

    def test_energy_fields_list(self):
        assert "pv_power_w" in ENERGY_FIELDS
        assert "battery_soc_pct" in ENERGY_FIELDS
        assert "geyser_state" in ENERGY_FIELDS
        assert "ev_charger_power_w" in ENERGY_FIELDS
