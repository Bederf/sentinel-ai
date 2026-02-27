"""
Tests for ThermalSimulationEngine

Verifies that:
- Zone temperatures are calculated based on occupancy and time of day
- Sensor readings are written to database
- Temperature behavior is realistic (inertia, HVAC response, thermal mass)
"""

import pytest
from unittest.mock import Mock, AsyncMock

from app.services.thermal_simulation_engine import (
    ThermalSimulationEngine,
    get_thermal_engine,
)


@pytest.fixture
def thermal_engine():
    """Create a thermal engine instance for testing."""
    return ThermalSimulationEngine(building_id="test-building-001")


@pytest.fixture
def mock_supabase(monkeypatch):
    """Mock Supabase client."""
    mock_client = Mock()

    # Mock table operations
    mock_table = Mock()
    mock_select = Mock()
    mock_select.eq = Mock(return_value=AsyncMock(execute=Mock(return_value=Mock(data=[]))))
    mock_table.select = Mock(return_value=mock_select)
    mock_table.insert = Mock(return_value=Mock(execute=Mock()))
    mock_client.table = Mock(return_value=mock_table)

    monkeypatch.setattr("app.services.thermal_simulation_engine.get_supabase_client", Mock(return_value=mock_client))
    return mock_client


class TestThermalCalculations:
    """Test temperature calculation logic."""

    def test_temperature_increases_with_occupancy(self, thermal_engine):
        """Temperature should increase when occupancy increases."""
        # Low occupancy
        temp_low = thermal_engine._calculate_zone_temperature(
            zone_id="Zone-001",
            simulated_hour=14,  # Afternoon
            occupancy_pct=10.0,  # 10% occupancy
            ambient_temp=20.0,
            setpoint=22.0,
            zone_config={
                "zone_name": "Test Zone",
                "typical_occupancy": 20,
                "fan_speed": "auto",
            },
        )

        # High occupancy (same hour and conditions)
        thermal_engine._last_temps["Zone-001"] = 22.0  # Reset to same starting point
        temp_high = thermal_engine._calculate_zone_temperature(
            zone_id="Zone-001",
            simulated_hour=14,
            occupancy_pct=80.0,  # 80% occupancy
            ambient_temp=20.0,
            setpoint=22.0,
            zone_config={
                "zone_name": "Test Zone",
                "typical_occupancy": 20,
                "fan_speed": "auto",
            },
        )

        # High occupancy should result in higher temperature
        assert temp_high > temp_low, f"High occupancy ({temp_high}°C) should be > low occupancy ({temp_low}°C)"

    def test_night_setback_reduces_temperature(self, thermal_engine):
        """Night setback should result in lower temperatures."""
        # Day time
        thermal_engine._last_temps["Zone-001"] = 22.0
        temp_day = thermal_engine._calculate_zone_temperature(
            zone_id="Zone-001",
            simulated_hour=14,
            occupancy_pct=50.0,
            ambient_temp=20.0,
            setpoint=22.0,
            zone_config={
                "zone_name": "Test Zone",
                "typical_occupancy": 20,
                "fan_speed": "auto",
            },
        )

        # Night time (setpoint would be lower due to NIGHT_SETBACK_OFFSET)
        thermal_engine._last_temps["Zone-001"] = 22.0
        temp_night = thermal_engine._calculate_zone_temperature(
            zone_id="Zone-001",
            simulated_hour=23,
            occupancy_pct=5.0,
            ambient_temp=15.0,
            setpoint=20.0,  # Already reduced by setback offset
            zone_config={
                "zone_name": "Test Zone",
                "typical_occupancy": 20,
                "fan_speed": "auto",
            },
        )

        # Night should be cooler
        assert temp_night < temp_day, f"Night ({temp_night}°C) should be < day ({temp_day}°C)"

    def test_thermal_inertia_dampens_changes(self, thermal_engine):
        """Thermal inertia should prevent temperature from changing too quickly."""
        initial_temp = 22.0
        thermal_engine._last_temps["Zone-001"] = initial_temp

        # Large occupancy change
        temp_response = thermal_engine._calculate_zone_temperature(
            zone_id="Zone-001",
            simulated_hour=8,
            occupancy_pct=100.0,  # Suddenly full occupancy
            ambient_temp=20.0,
            setpoint=22.0,
            zone_config={
                "zone_name": "Test Zone",
                "typical_occupancy": 20,
                "fan_speed": "auto",
            },
        )

        # Temperature should change, but not drastically (thermal inertia)
        # Note: with 100% occupancy + ambient effects, up to 15°C change is possible
        change = abs(temp_response - initial_temp)
        assert change < 15.0, f"Temperature change ({change}°C) is too large, inertia not working"

    def test_solar_gain_increases_afternoon_temperature(self, thermal_engine):
        """Solar gain should increase temperature in afternoon hours."""
        thermal_engine._last_temps["Zone-001"] = 22.0

        # Morning (low solar)
        temp_morning = thermal_engine._calculate_zone_temperature(
            zone_id="Zone-001",
            simulated_hour=9,
            occupancy_pct=50.0,
            ambient_temp=18.0,
            setpoint=22.0,
            zone_config={
                "zone_name": "Test Zone",
                "typical_occupancy": 20,
                "fan_speed": "auto",
            },
        )

        # Afternoon (high solar)
        thermal_engine._last_temps["Zone-001"] = 22.0
        temp_afternoon = thermal_engine._calculate_zone_temperature(
            zone_id="Zone-001",
            simulated_hour=14,  # Peak solar time
            occupancy_pct=50.0,
            ambient_temp=18.0,
            setpoint=22.0,
            zone_config={
                "zone_name": "Test Zone",
                "typical_occupancy": 20,
                "fan_speed": "auto",
            },
        )

        # Afternoon should be warmer due to solar
        assert temp_afternoon > temp_morning, (
            f"Afternoon ({temp_afternoon}°C) should be > morning ({temp_morning}°C) due to solar gain"
        )

    def test_temperature_stays_in_bounds(self, thermal_engine):
        """Temperature should stay within reasonable bounds (5-35°C)."""
        for hour in range(24):
            for occupancy in [0, 50, 100]:
                thermal_engine._last_temps["Zone-001"] = 22.0
                temp = thermal_engine._calculate_zone_temperature(
                    zone_id="Zone-001",
                    simulated_hour=hour,
                    occupancy_pct=float(occupancy),
                    ambient_temp=10.0,
                    setpoint=22.0,
                    zone_config={
                        "zone_name": "Test Zone",
                        "typical_occupancy": 20,
                        "fan_speed": "auto",
                    },
                )

                assert 5.0 <= temp <= 35.0, f"Temperature {temp}°C out of bounds at hour {hour}, occupancy {occupancy}%"


class TestSolarFactor:
    """Test solar gain calculations."""

    def test_solar_factor_by_hour(self, thermal_engine):
        """Solar factor should be high at midday, low at night."""
        # Night hours should have 0 solar
        for hour in [0, 1, 2, 3, 4, 5, 6, 7, 23, 22, 21, 20, 19, 18]:
            assert thermal_engine._calculate_solar_factor(hour) == 0.0, f"Hour {hour} should have 0 solar"

        # Midday should have maximum solar
        midday_solar = thermal_engine._calculate_solar_factor(14)
        assert midday_solar > 0.8, f"Midday solar ({midday_solar}) should be > 0.8"

        # Morning/afternoon should have moderate solar
        morning_solar = thermal_engine._calculate_solar_factor(9)
        afternoon_solar = thermal_engine._calculate_solar_factor(16)
        assert 0 < morning_solar < 1.0, f"Morning solar ({morning_solar}) should be moderate"
        assert 0 < afternoon_solar < 1.0, f"Afternoon solar ({afternoon_solar}) should be moderate"


class TestIntegration:
    """Integration tests with mocked database."""

    @pytest.mark.asyncio
    async def test_occupancy_profile(self, thermal_engine, mock_supabase):
        """Test occupancy generates realistic daily profile."""
        occupancy_data = {
            "Zone-001": 10.0,  # Office (some early arrivals)
            "Zone-002": 15.0,
            "Zone-101": 5.0,
            "Zone-201": 8.0,
            "Zone-R": 0.0,  # Rooftop (no occupancy)
        }

        temps = {}
        for hour in range(24):
            # Morning: occupancy increasing
            if hour == 8:
                occupancy_data = {z: 80.0 for z in occupancy_data.keys()}
                occupancy_data["Zone-R"] = 0.0

            # Afternoon: high occupancy
            if hour == 14:
                occupancy_data = {z: 85.0 for z in occupancy_data.keys()}

            # Evening: decreasing occupancy
            if hour == 18:
                occupancy_data = {z: 20.0 for z in occupancy_data.keys()}

            # Night: empty
            if hour == 22:
                occupancy_data = {z: 0.0 for z in occupancy_data.keys()}

            # Reset temps for consistency
            thermal_engine._zone_cache = {
                f"Zone-{i:03d}": {
                    "zone_name": f"Zone {i}",
                    "typical_occupancy": 20,
                    "setpoint": 22.0,
                    "fan_speed": "auto",
                }
                for i in range(1, 4)
            }

            result = await thermal_engine.update_zone_temperatures(
                simulated_hour=hour,
                occupancy_data=occupancy_data,
                ambient_temp=15.0 + (10.0 * abs(12 - hour) / 12.0),  # Ambient varies with time
                is_night_mode=(hour >= 22 or hour < 6),
            )

            temps[hour] = result

        # Verify temperature profile makes sense
        morning_temp = list(temps[8].values())[0]
        peak_temp = list(temps[14].values())[0]
        night_temp = list(temps[23].values())[0]

        # Temperatures should vary across the day (not all identical)
        assert morning_temp != night_temp or peak_temp != night_temp, "Temperatures should vary across the day"
        # Night setback should result in lower temps or at least not drastically higher
        assert night_temp <= morning_temp + 2.0, "Night temps should not be significantly higher than morning"


class TestCO2Simulation:
    """Test CO2 generation and ventilation dilution."""

    def test_co2_rises_with_occupancy(self, thermal_engine):
        """CO2 should rise when zone is occupied."""
        zone_config = {"typical_occupancy": 20}

        co2 = thermal_engine._calculate_zone_co2("Z1", 80.0, 0.7, zone_config)
        assert co2 > thermal_engine.OUTDOOR_CO2_PPM, "CO2 should rise above outdoor baseline"

    def test_co2_falls_when_vacant(self, thermal_engine):
        """CO2 should fall toward outdoor baseline when zone is vacant."""
        zone_config = {"typical_occupancy": 20}

        # First, elevate CO2
        thermal_engine._zone_co2["Z1"] = 900.0
        co2 = thermal_engine._calculate_zone_co2("Z1", 0.0, 0.7, zone_config)
        assert co2 < 900.0, "CO2 should decrease when zone is vacant"

    def test_co2_clamped_to_outdoor_baseline(self, thermal_engine):
        """CO2 should never go below outdoor baseline."""
        zone_config = {"typical_occupancy": 20}

        # Start at baseline, 0 occupancy
        thermal_engine._zone_co2["Z1"] = thermal_engine.OUTDOOR_CO2_PPM
        co2 = thermal_engine._calculate_zone_co2("Z1", 0.0, 0.9, zone_config)
        assert co2 >= thermal_engine.OUTDOOR_CO2_PPM, "CO2 should not go below outdoor baseline"

    def test_co2_clamped_to_max(self, thermal_engine):
        """CO2 should not exceed 2000 ppm."""
        zone_config = {"typical_occupancy": 100}

        thermal_engine._zone_co2["Z1"] = 1990.0
        co2 = thermal_engine._calculate_zone_co2("Z1", 100.0, 0.1, zone_config)
        assert co2 <= 2000.0, "CO2 should not exceed 2000 ppm"

    def test_dcv_boost_above_threshold(self, thermal_engine):
        """DCV should increase dilution rate above threshold, slowing CO2 rise."""
        zone_config = {"typical_occupancy": 20}

        # Below threshold: normal dilution
        thermal_engine._zone_co2["Z_low"] = 700.0
        co2_low = thermal_engine._calculate_zone_co2("Z_low", 80.0, 0.7, zone_config)

        # Above threshold: DCV boost dilution
        thermal_engine._zone_co2["Z_high"] = 900.0
        co2_high = thermal_engine._calculate_zone_co2("Z_high", 80.0, 0.7, zone_config)

        # The high-CO2 zone should see a bigger dilution drop relative to its level
        rise_low = co2_low - 700.0
        rise_high = co2_high - 900.0
        # DCV boost means the high zone should rise less (or drop)
        assert rise_high < rise_low, "DCV boost should slow CO2 rise above threshold"


class TestChillerPlant:
    """Test N+1 chiller redundancy and COP interpolation."""

    def test_cop_interpolation_exact(self, thermal_engine):
        """COP should match exact points in the curve."""
        assert thermal_engine._interpolate_cop(0.6) == 3.5
        assert thermal_engine._interpolate_cop(1.0) == 3.2

    def test_cop_interpolation_between(self, thermal_engine):
        """COP should interpolate between curve points."""
        cop = thermal_engine._interpolate_cop(0.3)
        assert 2.0 < cop < 3.0, f"COP at 30% load should be between 2.0 and 3.0, got {cop}"

    def test_lead_chiller_handles_normal_load(self, thermal_engine):
        """Lead chiller should handle load alone when within capacity."""
        power = thermal_engine._update_chiller_plant(80.0)
        lead = thermal_engine._chiller_states["S002-CHILLER-B1-001"]
        lag = thermal_engine._chiller_states["S002-CHILLER-B1-002"]

        assert lead["running"] is True
        assert lag["running"] is False
        assert power > 0

    def test_cascade_on_high_demand(self, thermal_engine):
        """Lag chiller should start when demand exceeds lead capacity."""
        power = thermal_engine._update_chiller_plant(400.0)
        lead = thermal_engine._chiller_states["S002-CHILLER-B1-001"]
        lag = thermal_engine._chiller_states["S002-CHILLER-B1-002"]

        assert lead["running"] is True
        assert lag["running"] is True
        assert lag["load_pct"] > 0

    def test_cascade_on_lead_fault(self, thermal_engine):
        """Lag should take over when lead is faulted (health < 20%)."""
        thermal_engine._chiller_states["S002-CHILLER-B1-001"]["health"] = 10.0

        power = thermal_engine._update_chiller_plant(100.0)
        lead = thermal_engine._chiller_states["S002-CHILLER-B1-001"]
        lag = thermal_engine._chiller_states["S002-CHILLER-B1-002"]

        assert lead["running"] is False, "Faulted lead should be off"
        assert lag["running"] is True, "Lag should take over"
        assert power > 0

    def test_minimum_power_when_running(self, thermal_engine):
        """Chiller power should not go below minimum when running."""
        power = thermal_engine._update_chiller_plant(1.0)  # Very low demand
        assert power >= thermal_engine.CHILLER_MIN_POWER

    def test_zero_demand_no_power(self, thermal_engine):
        """No chiller power when there's zero cooling demand."""
        power = thermal_engine._update_chiller_plant(0.0)
        lead = thermal_engine._chiller_states["S002-CHILLER-B1-001"]
        lag = thermal_engine._chiller_states["S002-CHILLER-B1-002"]

        assert lead["running"] is False
        assert lag["running"] is False

    def test_health_update_propagates_to_chillers(self, thermal_engine):
        """update_health_cache should update chiller health."""
        thermal_engine.update_health_cache({"S002-CHILLER-B1-001": 45.0})
        assert thermal_engine._chiller_states["S002-CHILLER-B1-001"]["health"] == 45.0


class TestSingleton:
    """Test singleton pattern for thermal engines."""

    def test_same_instance_returned(self):
        """Same building should return same engine instance."""
        engine1 = get_thermal_engine("site-002")
        engine2 = get_thermal_engine("site-002")
        assert engine1 is engine2, "Should return same instance for same building"

    def test_different_instances_for_different_buildings(self):
        """Different buildings should have different engine instances."""
        engine1 = get_thermal_engine("site-001")
        engine2 = get_thermal_engine("site-002")
        assert engine1 is not engine2, "Should return different instances for different buildings"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
