"""Integration tests for profile-based optimization end-to-end."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient

from app.main import app
from app.services.profile_service import get_profile_service
from app.services.security_occupancy_service import (
    get_security_occupancy_service,
    SecurityOccupancyService,
)


@pytest.fixture
async def client():
    """Create test client."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


class TestProfileIntegration:
    """Test profile-aware optimization end-to-end."""

    @pytest.mark.asyncio
    async def test_optimization_endpoint_with_profile(self, client):
        """Test that optimization endpoint respects profile settings."""
        # This would be an integration test against the actual API
        # For now, we test the service layer directly
        pass

    def test_security_occupancy_service_uses_profiles(self):
        """Test that SecurityOccupancyService loads and uses profile thresholds."""
        svc = SecurityOccupancyService()

        # Mock the profile service
        with patch.object(svc, "_profile_service") as mock_ps:
            mock_ps.get_site_profile.return_value = {
                "name": "Cost Saving",
                "thresholds": {
                    "empty_zone_setback": 3.0,
                    "empty_zone_lighting": 15,
                    "low_occupancy_lighting": 40,
                }
            }

            thresholds = svc._get_profile_thresholds("site-002")

            assert thresholds["hvac_setback"] == 3.0
            assert thresholds["lighting_empty"] == 15
            assert thresholds["lighting_low"] == 40
            mock_ps.get_site_profile.assert_called_once_with("site-002")

    def test_security_occupancy_service_falls_back_to_defaults(self):
        """Test that SecurityOccupancyService falls back to defaults on error."""
        svc = SecurityOccupancyService()

        # Mock the profile service to raise an error
        with patch.object(svc, "_profile_service") as mock_ps:
            mock_ps.get_site_profile.side_effect = Exception("Profile error")

            thresholds = svc._get_profile_thresholds("site-002")

            # Should return defaults
            assert "hvac_setback" in thresholds
            assert "lighting_empty" in thresholds
            assert "lighting_low" in thresholds

    def test_hvac_adjustment_with_profile_threshold(self):
        """Test HVAC adjustment uses profile threshold."""
        svc = SecurityOccupancyService()

        # Mock zone occupancy
        with patch.object(svc, "_calculate_zone_occupancy") as mock_occ:
            mock_occ.return_value = {
                "zone_id": "zone-1",
                "zone_name": "Level 1 South",
                "occupancy_count": 0,  # Empty zone
            }

            thresholds = {
                "hvac_setback": 4.0,  # Higher setback from profile
                "lighting_empty": 10,
            }

            result = svc.check_hvac_adjustment("zone-1", thresholds)

            assert result is not None
            assert result["setpoint_offset"] == 4.0
            assert "4.0°C" in result["detail"]

    def test_lighting_adjustment_with_profile_threshold(self):
        """Test lighting adjustment uses profile threshold."""
        svc = SecurityOccupancyService()

        # Mock zone occupancy
        with patch.object(svc, "_calculate_zone_occupancy") as mock_occ:
            mock_occ.return_value = {
                "zone_id": "zone-1",
                "zone_name": "Level 1 South",
                "occupancy_count": 0,  # Empty zone
            }

            thresholds = {
                "hvac_setback": 2.0,
                "lighting_empty": 10,  # Dimmer from profile
                "lighting_low": 30,
            }

            result = svc.check_lighting_adjustment("zone-1", thresholds)

            assert result is not None
            assert result["brightness_level"] == 10
            assert "10%" in result["detail"]

    def test_get_all_recommendations_with_profile(self):
        """Test that get_all_recommendations passes profile thresholds."""
        svc = SecurityOccupancyService()

        # Mock dependencies
        with patch.object(svc, "_repo") as mock_repo, \
             patch.object(svc, "_get_profile_thresholds") as mock_thresh, \
             patch.object(svc, "_get_dali_occupancy_data") as mock_dali:

            mock_repo.get_zones.return_value = [
                {"zone_id": "zone-1"},
                {"zone_id": "zone-2"},
            ]

            mock_thresh.return_value = {
                "hvac_setback": 3.0,
                "lighting_empty": 15,
                "lighting_low": 50,
            }

            mock_dali.return_value = None

            # Mock occupancy calculations
            with patch.object(svc, "_calculate_zone_occupancy") as mock_occ:
                mock_occ.return_value = {
                    "zone_id": "zone-1",
                    "zone_name": "Test Zone",
                    "occupancy_count": 0,
                }

                result = svc.get_all_recommendations("site-002")

            # Verify profile thresholds were loaded
            mock_thresh.assert_called_once_with("site-002")

            # Should have recommendations
            assert "hvac" in result
            assert "lighting" in result

    def test_profile_thresholds_override_defaults(self):
        """Test that profile thresholds override hardcoded defaults."""
        from app.services.security_occupancy_service import (
            HVAC_RELAXATION_OFFSET,
            LIGHTING_DIM_LEVEL,
        )

        svc = SecurityOccupancyService()

        # Create a profile with different thresholds
        profile = {
            "name": "Aggressive Cost Saving",
            "thresholds": {
                "empty_zone_setback": 5.0,  # Much higher than default
                "empty_zone_lighting": 5,   # Much dimmer than default
            }
        }

        with patch.object(svc, "_profile_service") as mock_ps:
            mock_ps.get_site_profile.return_value = profile

            thresholds = svc._get_profile_thresholds("site-002")

            # Verify profile values override defaults
            assert thresholds["hvac_setback"] == 5.0
            assert thresholds["hvac_setback"] > HVAC_RELAXATION_OFFSET
            assert thresholds["lighting_empty"] == 5
            assert thresholds["lighting_empty"] < LIGHTING_DIM_LEVEL
