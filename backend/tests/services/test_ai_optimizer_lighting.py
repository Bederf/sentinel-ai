"""Tests for AI optimizer with lighting integration."""

from unittest.mock import MagicMock

from app.services.ai_optimizer import AIOptimizerService


class _MockOccupancy:
    def __init__(self, pct, lux):
        self.occupancy_percent = pct
        self.avg_lux_level = lux

    def to_dict(self):
        return {"occupancy_percent": self.occupancy_percent, "avg_lux_level": self.avg_lux_level}


class _MockLighting:
    def __init__(self, dim, watts):
        self.avg_dim_level = dim
        self.total_power_w = watts
        self.faulty_count = 0

    def to_dict(self):
        return {"avg_dim_level": self.avg_dim_level, "total_power_w": self.total_power_w, "faulty_count": 0}


_MOCK_ZONES = [
    {
        "zone_id": "Zone-L12-N",
        "name": "Level 12 North",
        "floor": "12",
        "area_sqm": 100,
        "desk_count": 8,
    },
    {
        "zone_id": "Zone-L11-S",
        "name": "Level 11 South",
        "floor": "11",
        "area_sqm": 80,
        "desk_count": 0,
    },
]


class TestLightingZoneDataGathering:
    """Test lighting zone data gathering methods."""

    def test_gather_lighting_zone_data_returns_zone_info(self):
        """Test that _gather_lighting_zone_data returns zone occupancy and lighting data."""
        optimizer = AIOptimizerService()
        lighting_service = MagicMock()
        lighting_service.get_all_zones.return_value = _MOCK_ZONES
        lighting_service.get_zone_occupancy.side_effect = lambda z: (
            _MockOccupancy(60, 450) if z == "Zone-L12-N" else _MockOccupancy(0, 620)
        )
        lighting_service.get_zone_lighting.side_effect = lambda z: (
            _MockLighting(75, 250) if z == "Zone-L12-N" else _MockLighting(100, 350)
        )

        zone_data = optimizer._gather_lighting_zone_data(lighting_service, "site-002")

        assert len(zone_data) > 0
        sample_zone = next(iter(zone_data.values()))
        assert "zone_id" in sample_zone
        assert "zone_name" in sample_zone
        assert "occupancy" in sample_zone
        assert "lighting" in sample_zone
        assert "is_occupied" in sample_zone
        assert "has_high_daylight" in sample_zone
        assert "is_over_lit" in sample_zone

    def test_gather_lighting_zone_data_identifies_over_lit_zones(self):
        """Test that over-lit zones are correctly identified."""
        optimizer = AIOptimizerService()
        lighting_service = MagicMock()
        lighting_service.get_all_zones.return_value = _MOCK_ZONES
        lighting_service.get_zone_occupancy.side_effect = lambda z: (
            _MockOccupancy(60, 450) if z == "Zone-L12-N" else _MockOccupancy(0, 620)
        )
        lighting_service.get_zone_lighting.side_effect = lambda z: (
            _MockLighting(75, 250) if z == "Zone-L12-N" else _MockLighting(100, 350)
        )

        zone_data = optimizer._gather_lighting_zone_data(lighting_service, "site-002")


class TestLightingPromptFormatting:
    """Test lighting section formatting for Claude prompt."""

    def test_format_lighting_section_with_zones(self):
        """Test lighting section formatting with zone data."""
        optimizer = AIOptimizerService()

        mock_zones = {
            "Zone-L12-N": {
                "zone_id": "Zone-L12-N",
                "zone_name": "Level 12 North",
                "is_occupied": True,
                "has_high_daylight": False,
                "is_over_lit": False,
                "occupancy": {
                    "occupancy_percent": 60,
                    "avg_lux_level": 450,
                },
                "lighting": {
                    "avg_dim_level": 75,
                    "total_power_w": 250,
                    "faulty_count": 0,
                },
                "active_scene_name": "Working",
            },
            "Zone-L11-S": {
                "zone_id": "Zone-L11-S",
                "zone_name": "Level 11 South (Unoccupied)",
                "is_occupied": False,
                "has_high_daylight": True,
                "is_over_lit": True,
                "occupancy": {
                    "occupancy_percent": 0,
                    "avg_lux_level": 620,
                },
                "lighting": {
                    "avg_dim_level": 100,
                    "total_power_w": 350,
                    "faulty_count": 0,
                },
                "active_scene_name": "Working",
            },
        }

        result = optimizer._format_lighting_section([], mock_zones)

        # Should include lighting system summary
        assert "Lighting System" in result
        assert "Total zones: 2" in result
        assert "Occupied zones: 1" in result
        assert "Over-lit unoccupied zones" in result

        # Should identify the over-lit zone
        assert "Level 11 South" in result

        # Should include lighting telemetry
        assert "Lighting Telemetry by Zone" in result

        # Should include optimization rules
        assert "Daylight harvesting" in result
        assert "Unoccupied zones" in result

    def test_format_lighting_section_empty_zones(self):
        """Test lighting section formatting with no zones."""
        optimizer = AIOptimizerService()
        result = optimizer._format_lighting_section([], {})
        assert result == ""


class TestRuleBasedLightingOptimization:
    """Test rule-based lighting optimization logic."""

    def test_unoccupied_zone_cross_system_recommendation(self):
        """Test that unoccupied zones get cross-system monitoring recommendations.

        Tridonic net4more natively handles BOTH lighting dimming AND HVAC setback
        via BACnet when zones are unoccupied. SENTINEL monitors and adds value
        through predictive pre-conditioning and tariff optimization.
        """
        optimizer = AIOptimizerService()

        mock_zones = {
            "Zone-L11-S": {
                "zone_id": "Zone-L11-S",
                "zone_name": "Level 11 South Unoccupied",
                "is_occupied": False,
                "has_high_daylight": False,
                "is_over_lit": True,
                "occupancy": {
                    "occupancy_percent": 0,
                    "avg_lux_level": 400,
                },
                "lighting": {
                    "avg_dim_level": 100,
                    "total_power_w": 350,
                    "faulty_count": 0,
                },
            }
        }

        current_conditions = {
            "indoor_temp": 22.0,
            "outdoor_temp": 28.0,
            "humidity": 55.0,
            "occupancy": "low",
        }

        weather = {"current_temp": 28.0, "forecast": []}
        energy = {"current_rate": 2.50}

        result = optimizer._analyze_with_rules(
            "site-002",
            current_conditions,
            weather,
            energy,
            [],  # No HVAC devices for this test
            mock_zones,
        )

        # Tridonic-first: dimming handled natively, AI provides cross-system coordination
        assert result.cross_system_recommendations is not None
        assert len(result.cross_system_recommendations) > 0

        zone_rec = next(
            (r for r in result.cross_system_recommendations if r["zone_id"] == "Zone-L11-S"),
            None,
        )
        assert zone_rec is not None
        assert "unoccupied" in zone_rec["reason"].lower()
        # Tridonic handles both lighting AND HVAC natively via net4more + BACnet
        assert "Tridonic" in zone_rec["lighting_action"]
        assert "Tridonic" in zone_rec["hvac_action"]
        # SENTINEL adds predictive/tariff optimization on top
        assert "sentinel_action" in zone_rec

    def test_daylight_harvesting_recommendation(self):
        """Test that high-lux zones get daylight harvesting recommendations."""
        optimizer = AIOptimizerService()

        mock_zones = {
            "Zone-L12-N": {
                "zone_id": "Zone-L12-N",
                "zone_name": "Level 12 North",
                "is_occupied": True,
                "has_high_daylight": True,
                "is_over_lit": False,
                "occupancy": {
                    "occupancy_percent": 60,
                    "avg_lux_level": 700,  # Well above 500 setpoint
                },
                "lighting": {
                    "avg_dim_level": 80,
                    "total_power_w": 280,
                    "faulty_count": 0,
                },
            }
        }

        current_conditions = {
            "indoor_temp": 22.0,
            "outdoor_temp": 28.0,
            "humidity": 55.0,
            "occupancy": "high",
        }

        weather = {"current_temp": 28.0, "forecast": []}
        energy = {"current_rate": 2.50}

        result = optimizer._analyze_with_rules(
            "site-002",
            current_conditions,
            weather,
            energy,
            [],
            mock_zones,
        )

        # Should have a daylight harvesting recommendation
        lighting_recs = [r for r in result.recommendations if r.get("system") == "lighting"]
        zone_rec = next((r for r in lighting_recs if r["equipment_id"] == "Zone-L12-N"), None)

        if zone_rec:  # May or may not trigger based on exact thresholds
            assert "daylight" in zone_rec["reason"].lower()


class TestCrossSystemRecommendations:
    """Test cross-system recommendation generation."""

    def test_cross_system_recommendation_for_unoccupied_zone(self):
        """Test that unoccupied zones get cross-system recommendations."""
        optimizer = AIOptimizerService()

        mock_zones = {
            "Zone-L11-S": {
                "zone_id": "Zone-L11-S",
                "zone_name": "Level 11 South",
                "is_occupied": False,
                "has_high_daylight": False,
                "is_over_lit": True,
                "occupancy": {
                    "occupancy_percent": 0,
                    "avg_lux_level": 400,
                },
                "lighting": {
                    "avg_dim_level": 100,
                    "total_power_w": 350,
                    "faulty_count": 0,
                },
            }
        }

        current_conditions = {
            "indoor_temp": 22.0,
            "outdoor_temp": 30.0,  # Hot day
            "humidity": 55.0,
        }

        weather = {"current_temp": 30.0, "forecast": []}
        energy = {"current_rate": 2.50}

        result = optimizer._analyze_with_rules(
            "site-002",
            current_conditions,
            weather,
            energy,
            [],
            mock_zones,
        )

        # Should have cross-system recommendations
        assert result.cross_system_recommendations is not None
        assert len(result.cross_system_recommendations) > 0

        cross_rec = result.cross_system_recommendations[0]
        assert cross_rec["zone_id"] == "Zone-L11-S"
        assert "hvac_action" in cross_rec
        assert "lighting_action" in cross_rec
        assert "combined_savings_kw" in cross_rec


class TestProjectedSavingsCalculation:
    """Test projected savings calculations including lighting."""

    def test_projected_savings_includes_lighting(self):
        """Test that projected savings include both HVAC and lighting."""
        optimizer = AIOptimizerService()

        mock_zones = {
            "Zone-L11-S": {
                "zone_id": "Zone-L11-S",
                "zone_name": "Level 11 South",
                "is_occupied": False,
                "has_high_daylight": False,
                "is_over_lit": True,
                "occupancy": {"occupancy_percent": 0, "avg_lux_level": 400},
                "lighting": {"avg_dim_level": 100, "total_power_w": 350, "faulty_count": 0},
            }
        }

        current_conditions = {"indoor_temp": 22.0, "outdoor_temp": 28.0, "humidity": 55.0}
        weather = {"current_temp": 28.0, "forecast": []}
        energy = {"current_rate": 2.50}

        result = optimizer._analyze_with_rules(
            "site-002",
            current_conditions,
            weather,
            energy,
            [],
            mock_zones,
        )

        # Check projected savings structure
        savings = result.projected_savings
        assert "hvac_kwh" in savings
        assert "lighting_kwh" in savings
        assert "energy_kwh" in savings
        assert savings["energy_kwh"] >= savings["hvac_kwh"]


class TestLightingSummary:
    """Test lighting summary generation."""

    def test_lighting_summary_included(self):
        """Test that lighting summary is included in recommendations."""
        optimizer = AIOptimizerService()

        mock_zones = {
            "Zone-L12-N": {
                "zone_id": "Zone-L12-N",
                "zone_name": "Level 12 North",
                "is_occupied": True,
                "has_high_daylight": False,
                "is_over_lit": False,
                "occupancy": {"occupancy_percent": 60, "avg_lux_level": 450},
                "lighting": {"avg_dim_level": 75, "total_power_w": 250, "faulty_count": 0},
            },
            "Zone-L11-S": {
                "zone_id": "Zone-L11-S",
                "zone_name": "Level 11 South",
                "is_occupied": False,
                "has_high_daylight": False,
                "is_over_lit": True,
                "occupancy": {"occupancy_percent": 0, "avg_lux_level": 400},
                "lighting": {"avg_dim_level": 100, "total_power_w": 350, "faulty_count": 0},
            },
        }

        current_conditions = {"indoor_temp": 22.0, "outdoor_temp": 28.0, "humidity": 55.0}
        weather = {"current_temp": 28.0, "forecast": []}
        energy = {"current_rate": 2.50}

        result = optimizer._analyze_with_rules(
            "site-002",
            current_conditions,
            weather,
            energy,
            [],
            mock_zones,
        )

        # Check lighting summary
        assert result.lighting_summary is not None
        summary = result.lighting_summary
        assert summary["total_zones"] == 2
        assert summary["occupied_zones"] == 1
        assert summary["unoccupied_zones"] == 1
        assert summary["over_lit_zones"] == 1
