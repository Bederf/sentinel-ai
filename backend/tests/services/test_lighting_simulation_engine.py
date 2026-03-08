"""Unit tests for LightingSimulationEngine.

Tests cover:
    - Baseline power calculation (2 tests)
    - Occupancy scaling (4 tests)
    - Daylight harvesting (4 tests)
    - Seasonal factors / zone classification (3 tests)
    - Edge cases (2 tests)

Total: 15 tests

All tests mock Supabase and test pure calculation logic only.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.lighting_simulation_engine import (
    LightingSimulationEngine,
    get_lighting_engine,
)

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def engine():
    """Create a LightingSimulationEngine with mocked Supabase client."""
    with patch("app.services.lighting_simulation_engine.get_supabase_client") as mock_sb:
        mock_sb.return_value = MagicMock()
        eng = LightingSimulationEngine("site-002")

        # Pre-populate zone cache so _load_zone_metadata is not called
        eng._zone_cache = {
            "Zone-001": {"zone_name": "L0 Zone A", "floor": 0, "typical_occupancy": 10, "area_sqm": 50},
            "Zone-002": {"zone_name": "L0 Zone B", "floor": 0, "typical_occupancy": 10, "area_sqm": 50},
            "Zone-101": {"zone_name": "L1 Zone A", "floor": 1, "typical_occupancy": 10, "area_sqm": 50},
            "Zone-102": {"zone_name": "L1 Zone B", "floor": 1, "typical_occupancy": 10, "area_sqm": 50},
            "Zone-201": {"zone_name": "L2 Zone A", "floor": 2, "typical_occupancy": 10, "area_sqm": 50},
            "Zone-202": {"zone_name": "L2 Zone B", "floor": 2, "typical_occupancy": 10, "area_sqm": 50},
            "Zone-R": {"zone_name": "Common", "floor": 0, "typical_occupancy": 10, "area_sqm": 50},
            "Entry": {"zone_name": "Entry", "floor": 0, "typical_occupancy": 10, "area_sqm": 50},
        }
        return eng


# ------------------------------------------------------------------
# 1. Baseline Power Calculation
# ------------------------------------------------------------------


class TestBaselinePower:
    """Verify baseline power constants and per-zone calculation."""

    def test_baseline_power_per_zone(self, engine):
        """450 sqm x 10 W/sqm = 4.5 kW baseline per zone."""
        assert engine.BASELINE_POWER_PER_ZONE == 4.5

    def test_total_building_baseline_8_zones(self, engine):
        """8 zones at full occupancy, no daylight -> 8 x 4.5 kW = 36.0 kW total."""
        total = 0.0
        for zone_id in engine._zone_cache:
            power = engine._calculate_zone_lighting_power(
                zone_id=zone_id,
                occupancy_pct=100.0,
                daylight_lux=0.0,
                cloud_cover_pct=0.0,
                is_raining=False,
                zone_config=engine._zone_cache[zone_id],
            )
            total += power
        assert abs(total - (4.5 * 8)) < 0.1, f"Expected ~36.0 kW, got {total:.2f} kW"


# ------------------------------------------------------------------
# 2. Occupancy Scaling
# ------------------------------------------------------------------


class TestOccupancyScaling:
    """Verify lighting response to occupancy levels."""

    def test_zero_occupancy_returns_standby(self, engine):
        """0% occupancy (below 30% threshold) -> standby 0.02 kW."""
        power = engine._calculate_zone_lighting_power(
            zone_id="Zone-002",
            occupancy_pct=0.0,
            daylight_lux=0.0,
            cloud_cover_pct=0.0,
            is_raining=False,
            zone_config=engine._zone_cache["Zone-002"],
        )
        assert power == 0.02

    def test_below_threshold_occupancy_returns_standby(self, engine):
        """0.2% occupancy (below 0.3 threshold) -> standby power.

        Note: OCCUPANCY_SENSOR_RESPONSE = 0.3, and occupancy_pct is 0-100 scale,
        so the threshold is effectively 0.3% occupancy (near-empty building).
        """
        power = engine._calculate_zone_lighting_power(
            zone_id="Zone-002",
            occupancy_pct=0.2,  # Below 0.3 threshold
            daylight_lux=0.0,
            cloud_cover_pct=0.0,
            is_raining=False,
            zone_config=engine._zone_cache["Zone-002"],
        )
        assert power == 0.02

    def test_50_percent_occupancy_gives_partial_power(self, engine):
        """50% occupancy -> ~60% power due to occupancy_power_scaling = 0.6."""
        power = engine._calculate_zone_lighting_power(
            zone_id="Zone-002",
            occupancy_pct=50.0,
            daylight_lux=0.0,
            cloud_cover_pct=0.0,
            is_raining=False,
            zone_config=engine._zone_cache["Zone-002"],
        )
        # Formula: 4.5 * (1.0 - 0.6 + 0.6 * 0.5) = 4.5 * (0.4 + 0.3) = 4.5 * 0.7 = 3.15
        assert abs(power - 3.15) < 0.01, f"Expected ~3.15 kW, got {power:.3f}"

    def test_100_percent_occupancy_gives_full_power(self, engine):
        """100% occupancy -> full baseline power."""
        power = engine._calculate_zone_lighting_power(
            zone_id="Zone-002",
            occupancy_pct=100.0,
            daylight_lux=0.0,
            cloud_cover_pct=0.0,
            is_raining=False,
            zone_config=engine._zone_cache["Zone-002"],
        )
        assert abs(power - 4.5) < 0.01


# ------------------------------------------------------------------
# 3. Daylight Harvesting
# ------------------------------------------------------------------


class TestDaylightHarvesting:
    """Verify DALI daylight harvesting behavior."""

    def test_window_zone_with_high_lux_dims_significantly(self, engine):
        """Window zone (Zone-001) with 500 lux -> significant dimming."""
        power = engine._calculate_zone_lighting_power(
            zone_id="Zone-001",
            occupancy_pct=100.0,
            daylight_lux=500.0,
            cloud_cover_pct=0.0,
            is_raining=False,
            zone_config=engine._zone_cache["Zone-001"],
        )
        # daylight_excess = 500 - 300 = 200
        # daylight_factor = max(0.05, 1.0 - (200/500) * 0.8) = max(0.05, 1.0 - 0.32) = 0.68
        # power = 4.5 * 0.68 = 3.06
        assert power < 4.5, "Window zone with 500 lux should dim below baseline"
        assert power > engine.DALI_MIN_DIM * 4.5, "Should not go below DALI minimum"

    def test_interior_zone_no_daylight_harvesting(self, engine):
        """Interior zone (Zone-002) ignores daylight."""
        power_dark = engine._calculate_zone_lighting_power(
            zone_id="Zone-002",
            occupancy_pct=100.0,
            daylight_lux=0.0,
            cloud_cover_pct=0.0,
            is_raining=False,
            zone_config=engine._zone_cache["Zone-002"],
        )
        power_bright = engine._calculate_zone_lighting_power(
            zone_id="Zone-002",
            occupancy_pct=100.0,
            daylight_lux=1000.0,
            cloud_cover_pct=0.0,
            is_raining=False,
            zone_config=engine._zone_cache["Zone-002"],
        )
        assert abs(power_dark - power_bright) < 0.01, "Interior zone should not respond to daylight"

    def test_below_threshold_lux_no_dimming(self, engine):
        """Daylight below 300 lux threshold -> no harvesting."""
        power = engine._calculate_zone_lighting_power(
            zone_id="Zone-001",
            occupancy_pct=100.0,
            daylight_lux=200.0,
            cloud_cover_pct=0.0,
            is_raining=False,
            zone_config=engine._zone_cache["Zone-001"],
        )
        assert abs(power - 4.5) < 0.01, "Below 300 lux should give full power"

    def test_cloud_cover_reduces_effective_daylight(self, engine):
        """High cloud cover reduces effective lux via CLOUDY_REDUCTION."""
        power_clear = engine._calculate_zone_lighting_power(
            zone_id="Zone-001",
            occupancy_pct=100.0,
            daylight_lux=500.0,
            cloud_cover_pct=0.0,
            is_raining=False,
            zone_config=engine._zone_cache["Zone-001"],
        )
        power_cloudy = engine._calculate_zone_lighting_power(
            zone_id="Zone-001",
            occupancy_pct=100.0,
            daylight_lux=500.0,
            cloud_cover_pct=80.0,
            is_raining=False,
            zone_config=engine._zone_cache["Zone-001"],
        )
        # Cloudy reduces effective lux, so less dimming, so MORE power
        assert power_cloudy > power_clear, "Cloudy weather should reduce harvesting (more power)"


# ------------------------------------------------------------------
# 4. Zone Classification & Weather Effects
# ------------------------------------------------------------------


class TestZoneClassification:
    """Verify window/interior zone classification."""

    def test_window_zones_identified_correctly(self, engine):
        """Perimeter zones (North, East, South) are window zones."""
        assert engine.WINDOW_ZONES["Zone-001"] is True  # L0 North
        assert engine.WINDOW_ZONES["Zone-101"] is True  # L1 North
        assert engine.WINDOW_ZONES["Zone-201"] is True  # L2 North
        assert engine.WINDOW_ZONES["Zone-081"] is True  # L0 South

    def test_interior_zones_identified_correctly(self, engine):
        """Central/West zones are interior (no windows)."""
        assert engine.WINDOW_ZONES["Zone-041"] is False  # L0 Central
        assert engine.WINDOW_ZONES["Zone-141"] is False  # L1 Central
        assert engine.WINDOW_ZONES["Zone-061"] is False  # L0 West
        assert engine.WINDOW_ZONES["Zone-161"] is False  # L1 West

    def test_rain_reduces_effective_daylight_further(self, engine):
        """Rain reduces daylight by 60%, leading to less harvesting."""
        power_dry = engine._calculate_zone_lighting_power(
            zone_id="Zone-001",
            occupancy_pct=100.0,
            daylight_lux=600.0,
            cloud_cover_pct=0.0,
            is_raining=False,
            zone_config=engine._zone_cache["Zone-001"],
        )
        power_rain = engine._calculate_zone_lighting_power(
            zone_id="Zone-001",
            occupancy_pct=100.0,
            daylight_lux=600.0,
            cloud_cover_pct=0.0,
            is_raining=True,
            zone_config=engine._zone_cache["Zone-001"],
        )
        # Rain reduces effective lux by 60%, so less dimming -> more power needed
        assert power_rain > power_dry, "Rain should reduce harvesting (more power needed)"


# ------------------------------------------------------------------
# 5. Edge Cases
# ------------------------------------------------------------------


class TestEdgeCases:
    """Verify edge cases and boundary conditions."""

    def test_dali_minimum_dim_clamp(self, engine):
        """Extreme daylight does not go below DALI minimum dim (5%)."""
        power = engine._calculate_zone_lighting_power(
            zone_id="Zone-001",
            occupancy_pct=100.0,
            daylight_lux=5000.0,  # Extremely bright
            cloud_cover_pct=0.0,
            is_raining=False,
            zone_config=engine._zone_cache["Zone-001"],
        )
        min_power = engine.DALI_MIN_DIM * engine.BASELINE_POWER_PER_ZONE  # 0.05 * 4.5 = 0.225
        assert power >= min_power, f"Power {power} should not go below DALI min {min_power}"

    def test_singleton_returns_same_instance(self):
        """get_lighting_engine returns same instance for same building."""
        with patch("app.services.lighting_simulation_engine.get_supabase_client"):
            from app.services.lighting_simulation_engine import _lighting_engines

            _lighting_engines.clear()
            eng1 = get_lighting_engine("site-002")
            eng2 = get_lighting_engine("site-002")
            assert eng1 is eng2
            _lighting_engines.clear()
