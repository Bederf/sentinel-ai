"""Tests for profile-aware AI optimizer recommendations."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from app.models.optimization import OptimizationRecommendation
from app.services.ai_optimizer import AIOptimizerService, ensure_device_manager_initialized
from app.services.profile_service import get_profile_service


@pytest.fixture
def ai_optimizer():
    """Create AIOptimizerService instance for testing."""
    return AIOptimizerService()


@pytest.fixture
def mock_profile_service():
    """Create mock profile service."""
    service = MagicMock()

    # Mock cost profile
    service.get_site_profile.return_value = {
        "name": "Cost Saving",
        "description": "Minimize operational spend",
        "weights": {
            "runtime": 0.10,
            "comfort": 0.15,
            "cost": 0.35,
            "maintenance": 0.10,
            "energy": 0.30
        },
        "thresholds": {
            "max_comfort_deviation_c": 2.0,
            "empty_zone_setback": 3.0,
            "empty_zone_lighting": 15,
        }
    }
    return service


class TestProfileAwareOptimizer:
    """Test profile-aware optimization prompt building."""

    def test_build_prompt_without_profile(self, ai_optimizer):
        """Test prompt building without profile (backward compatibility)."""
        site = {
            "id": "site-002",
            "name": "Test Building",
            "type": "commercial",
            "sqm": 5000,
            "floors": 3,
        }

        conditions = {
            "indoor_temp": 22.0,
            "outdoor_temp": 28.0,
            "humidity": 55.0,
            "occupancy": "high",
            "equipment_status": "normal",
        }

        weather = {
            "forecast": "sunny",
            "temperature": 28,
        }

        energy_prices = {
            "current": 2.50,
            "peak": 4.00,
        }

        equipment_inventory = {
            "hvac": [],
            "lighting": [],
            "power": [],
            "meter": [],
        }

        prompt = ai_optimizer._build_optimization_prompt(
            site, conditions, weather, energy_prices, equipment_inventory
        )

        assert "Test Building" in prompt
        assert "Equipment Inventory" in prompt
        # Without profile, should not have profile section
        assert "ACTIVE OPTIMIZATION PROFILE" not in prompt

    def test_build_prompt_with_cost_profile(self, ai_optimizer):
        """Test prompt building with cost profile."""
        site = {
            "id": "site-002",
            "name": "Test Building",
            "type": "commercial",
            "sqm": 5000,
            "floors": 3,
        }

        conditions = {
            "indoor_temp": 22.0,
            "outdoor_temp": 28.0,
            "humidity": 55.0,
            "occupancy": "high",
            "equipment_status": "normal",
        }

        weather = {
            "forecast": "sunny",
            "temperature": 28,
        }

        energy_prices = {
            "current": 2.50,
            "peak": 4.00,
        }

        equipment_inventory = {
            "hvac": [],
            "lighting": [],
            "power": [],
            "meter": [],
        }

        cost_profile = {
            "name": "Cost Saving",
            "description": "Minimize operational spend",
            "weights": {
                "runtime": 0.10,
                "comfort": 0.15,
                "cost": 0.35,
                "maintenance": 0.10,
                "energy": 0.30
            },
            "thresholds": {
                "max_comfort_deviation_c": 2.0,
            }
        }

        prompt = ai_optimizer._build_optimization_prompt(
            site, conditions, weather, energy_prices, equipment_inventory,
            profile=cost_profile
        )

        assert "Cost Saving" in prompt
        assert "ACTIVE OPTIMIZATION PROFILE" in prompt
        assert "Cost: 35%" in prompt  # 0.35 formatted as 35%
        assert "MINIMIZE operational costs" in prompt

    def test_build_prompt_with_comfort_profile(self, ai_optimizer):
        """Test prompt building with comfort profile."""
        site = {
            "id": "site-002",
            "name": "Test Building",
            "type": "commercial",
            "sqm": 5000,
            "floors": 3,
        }

        conditions = {
            "indoor_temp": 22.0,
            "outdoor_temp": 28.0,
            "humidity": 55.0,
            "occupancy": "high",
            "equipment_status": "normal",
        }

        weather = {"forecast": "sunny"}
        energy_prices = {"current": 2.50}

        equipment_inventory = {
            "hvac": [],
            "lighting": [],
            "power": [],
            "meter": [],
        }

        comfort_profile = {
            "name": "Comfort First",
            "description": "Prioritize occupant comfort",
            "weights": {
                "runtime": 0.10,
                "comfort": 0.40,
                "cost": 0.10,
                "maintenance": 0.20,
                "energy": 0.20
            },
            "thresholds": {
                "max_comfort_deviation_c": 1.0,
            }
        }

        prompt = ai_optimizer._build_optimization_prompt(
            site, conditions, weather, energy_prices, equipment_inventory,
            profile=comfort_profile
        )

        assert "Comfort First" in prompt
        assert "Comfort: 40%" in prompt
        assert "tight temperature control" in prompt

    def test_recommendation_includes_profile_info(self, ai_optimizer):
        """Test that OptimizationRecommendation includes profile information."""
        rec = OptimizationRecommendation(
            site_id="site-002",
            timestamp="2026-02-09T10:00:00",
            recommendations=[],
            projected_savings={},
            confidence=0.8,
            reasoning="Test",
            profile="cost",
            profile_applied=True,
        )

        assert rec.profile == "cost"
        assert rec.profile_applied is True

        # Check serialization
        data = rec.to_dict()
        assert data["profile"] == "cost"
        assert data["profile_applied"] is True

    def test_recommendation_from_dict_with_profile(self):
        """Test OptimizationRecommendation.from_dict preserves profile info."""
        data = {
            "site_id": "site-002",
            "timestamp": "2026-02-09T10:00:00",
            "recommendations": [],
            "projected_savings": {},
            "confidence": 0.8,
            "reasoning": "Test",
            "profile": "comfort",
            "profile_applied": True,
        }

        rec = OptimizationRecommendation.from_dict(data)
        assert rec.profile == "comfort"
        assert rec.profile_applied is True

    @pytest.mark.asyncio
    async def test_rule_based_analysis_with_profile(self, ai_optimizer):
        """Test rule-based optimization respects profile."""
        # Ensure device manager is initialized
        await ensure_device_manager_initialized()

        site_id = "site-002"
        conditions = {
            "indoor_temp": 22.0,
            "outdoor_temp": 28.0,
            "humidity": 55.0,
            "occupancy": "high",
            "equipment_status": "normal",
        }

        weather = {"forecast": "sunny"}
        energy_prices = {"current": 2.50}
        equipment_inventory = {
            "hvac": [],
            "lighting": [],
            "power": [],
            "meter": [],
        }

        cost_profile = {
            "name": "Cost Saving",
            "description": "Minimize operational spend",
            "weights": {
                "runtime": 0.10,
                "comfort": 0.15,
                "cost": 0.35,
                "maintenance": 0.10,
                "energy": 0.30
            },
        }

        result = ai_optimizer._analyze_with_rules(
            site_id, conditions, weather, energy_prices,
            equipment_inventory, profile=cost_profile
        )

        assert isinstance(result, OptimizationRecommendation)
        assert result.profile == "Cost Saving"
        assert result.profile_applied is True
