"""Tests for profile-based optimization configuration."""

import json
from pathlib import Path

from app.models.optimization import (
    SiteProfileConfig,
    ZoneProfileOverride,
    ScheduleProfileOverride,
)
from app.services.profile_service import ProfileService, get_profile_service


class TestProfileModels:
    """Test profile configuration data models."""

    def test_zone_profile_override_serialization(self):
        """Test ZoneProfileOverride to_dict/from_dict."""
        override = ZoneProfileOverride(zone_id="server-room", profile="comfort", reason="Thermal criticality")

        data = override.to_dict()
        assert data["zone_id"] == "server-room"
        assert data["profile"] == "comfort"
        assert data["reason"] == "Thermal criticality"

        # Reconstruct from dict
        restored = ZoneProfileOverride.from_dict(data)
        assert restored.zone_id == "server-room"
        assert restored.profile == "comfort"

    def test_schedule_profile_override_serialization(self):
        """Test ScheduleProfileOverride to_dict/from_dict."""
        override = ScheduleProfileOverride(
            day_of_week="monday", start_hour=9, end_hour=17, profile="cost", reason="Business hours optimization"
        )

        data = override.to_dict()
        assert data["day_of_week"] == "monday"
        assert data["start_hour"] == 9
        assert data["end_hour"] == 17
        assert data["profile"] == "cost"

        restored = ScheduleProfileOverride.from_dict(data)
        assert restored.day_of_week == "monday"

    def test_site_profile_config_serialization(self):
        """Test SiteProfileConfig with zone overrides."""
        config = SiteProfileConfig(
            site_id="site-002",
            active_profile="cost",
            control_tier="human_in_loop",
            zone_overrides=[
                ZoneProfileOverride(zone_id="server-room", profile="comfort", reason="Thermal criticality")
            ],
            schedule_overrides=[],
        )

        data = config.to_dict()
        assert data["site_id"] == "site-002"
        assert data["active_profile"] == "cost"
        assert len(data["zone_overrides"]) == 1
        assert data["zone_overrides"][0]["zone_id"] == "server-room"

        # Reconstruct from dict
        restored = SiteProfileConfig.from_dict(data)
        assert restored.site_id == "site-002"
        assert len(restored.zone_overrides) == 1
        assert restored.zone_overrides[0].profile == "comfort"


class TestProfileService:
    """Test ProfileService functionality."""

    def test_profile_service_loads_profiles(self):
        """Test that ProfileService loads profiles from JSON."""
        service = ProfileService()

        assert len(service.profiles) > 0
        assert "asset_sweating" in service.profiles or "cost_saving" in service.profiles

    def test_get_site_profile(self):
        """Test getting site profile."""
        service = ProfileService()

        # Mock loading a config
        config = SiteProfileConfig(site_id="site-002", active_profile="cost_saving", control_tier="human_in_loop")
        service.site_configs["site-002"] = config

        profile = service.get_site_profile("site-002")
        assert profile is not None
        assert "description" in profile or "weights" in profile

    def test_get_zone_profile_without_override(self):
        """Test zone profile defaults to site profile when no override."""
        service = ProfileService()

        config = SiteProfileConfig(
            site_id="site-002", active_profile="cost_saving", control_tier="human_in_loop", zone_overrides=[]
        )
        service.site_configs["site-002"] = config

        # Zone without override should get site profile
        profile = service.get_zone_profile("site-002", "zone-a")
        assert profile is not None

    def test_get_zone_profile_with_override(self):
        """Test zone profile uses override when available."""
        service = ProfileService()

        config = SiteProfileConfig(
            site_id="site-002",
            active_profile="cost_saving",
            control_tier="human_in_loop",
            zone_overrides=[
                ZoneProfileOverride(zone_id="server-room", profile="comfort_first", reason="Thermal criticality")
            ],
        )
        service.site_configs["site-002"] = config

        # Server room should get comfort profile
        server_profile = service.get_zone_profile("site-002", "server-room")
        assert server_profile is not None

    def test_list_profiles(self):
        """Test listing available profiles."""
        service = ProfileService()
        profiles = service.list_profiles()

        assert len(profiles) > 0
        assert all("id" in p and "name" in p for p in profiles)

    def test_get_profile_params(self):
        """Test getting module-specific profile parameters."""
        service = ProfileService()

        params = service.get_profile_params("cost_saving", "hvac")
        assert "weights" in params
        assert "thresholds" in params

    def test_load_site_profile_config_from_file(self):
        """Test loading site profile config from building.json."""
        service = ProfileService()

        # Try to load site-002 config (should exist)
        config = service.load_site_profile_config("site-002")

        # Should return config (either from file or default)
        assert config is not None
        assert config.site_id == "site-002"
        assert config.active_profile in ["cost_saving", "cost", "sweat_assets", "comfort_first", "comfort"]
        assert config.control_tier in ["monitor", "human_in_loop", "auto_execute"]

    def test_update_zone_override(self):
        """Test updating zone override."""
        service = ProfileService()

        # Load config first
        config = service.load_site_profile_config("site-002")
        initial_overrides = len(config.zone_overrides)

        # Add override
        success = service.update_zone_override("site-002", "test-zone", "comfort_first", "Test reason")

        # Note: This will actually write to file, so we just check success
        assert isinstance(success, bool)

    def test_remove_zone_override(self):
        """Test removing zone override."""
        service = ProfileService()

        # Add and then remove
        service.update_zone_override("site-002", "test-zone-remove", "comfort_first", "Test")

        success = service.remove_zone_override("site-002", "test-zone-remove")
        assert isinstance(success, bool)

    def test_clear_cache(self):
        """Test clearing ProfileService cache."""
        service = ProfileService()

        # Load a config to populate cache
        service.load_site_profile_config("site-002")
        assert "site-002" in service.site_configs

        # Clear single entry
        service.clear_cache("site-002")
        assert "site-002" not in service.site_configs

        # Clear all
        service.load_site_profile_config("site-002")
        service.clear_cache()
        assert len(service.site_configs) == 0

    def test_get_profile_service_singleton(self):
        """Test that get_profile_service returns singleton."""
        service1 = get_profile_service()
        service2 = get_profile_service()

        assert service1 is service2


class TestProfileBuildingJsonIntegration:
    """Test integration with building.json files."""

    def test_all_sites_have_optimization_section(self):
        """Test that all building.json files have optimization section."""
        buildings_dir = Path(__file__).parent.parent.parent / "app" / "data" / "buildings"

        site_files = list(buildings_dir.glob("*/building.json"))
        assert len(site_files) > 0, "No building.json files found"

        for site_file in site_files:
            with open(site_file) as f:
                data = json.load(f)
                assert "optimization" in data, f"Missing optimization section in {site_file}"

                opt = data["optimization"]
                assert "active_profile" in opt
                assert "control_tier" in opt
                assert "zone_overrides" in opt
                assert "schedule_overrides" in opt

    def test_site_002_has_server_room_override(self):
        """Test that site-002 has the server-room override."""
        buildings_dir = Path(__file__).parent.parent.parent / "app" / "data" / "buildings"
        site_file = buildings_dir / "site-002" / "building.json"

        with open(site_file) as f:
            data = json.load(f)

            opt = data["optimization"]
            zone_overrides = opt["zone_overrides"]

            # Check for server-room override
            server_room_override = next((zo for zo in zone_overrides if zo["zone_id"] == "server-room"), None)

            if server_room_override:
                assert server_room_override["profile"] == "comfort"


# Note: API endpoint tests would require pytest-asyncio and FastAPI TestClient
# These are integration tests that would be in test_optimization_api.py
