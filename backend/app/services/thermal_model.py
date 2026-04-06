"""Thermal model simulation service for building comfort calculations.

This service calculates building thermal behavior during load shedding outages,
including thermal runway (time until comfort breach) and pre-cooling benefits.
"""

import logging

logger = logging.getLogger(__name__)


def calculate_thermal_runway(
    current_temp: float, comfort_limit: float, building_params: dict, weather_forecast: dict
) -> int:
    """
    Calculate minutes until building temperature breaches comfort limit.

    Uses simplified physics model:
    temperature_change = (outside_temp - inside_temp) × heat_transfer_coefficient + internal_heat_gain

    Args:
        current_temp: Current inside temperature in °C
        comfort_limit: Comfort temperature limit in °C
        building_params: Dictionary with thermal_mass, insulation_factor, internal_heat_gain
        weather_forecast: Dictionary with outside_temp, solar_load, humidity

    Returns:
        Minutes until temperature reaches comfort limit
    """
    # Extract parameters with defaults
    thermal_mass = building_params.get("thermal_mass", 0.8)
    insulation_factor = building_params.get("insulation_factor", 0.6)
    internal_heat_gain = building_params.get("internal_heat_gain", 0.5)

    outside_temp = weather_forecast.get("outside_temp", 32.0)
    solar_load = weather_forecast.get("solar_load", 0.7)
    _humidity = weather_forecast.get("humidity", 65)

    # Calculate heat transfer coefficient based on insulation and solar load
    base_transfer = 0.05  # Base heat transfer coefficient (°C/min per °C difference)
    heat_transfer_coefficient = base_transfer * (1.0 - insulation_factor) * (1.0 + solar_load * 0.3)

    # Adjust for thermal mass (higher mass = slower temperature change)
    mass_factor = 1.0 / thermal_mass

    # Calculate temperature rise per minute
    temp_difference = outside_temp - current_temp
    temp_change_per_minute = temp_difference * heat_transfer_coefficient * mass_factor + internal_heat_gain * 0.01

    # Ensure minimum positive temperature change
    if temp_change_per_minute <= 0:
        temp_change_per_minute = 0.01

    # Calculate minutes to reach comfort limit
    temp_to_limit = comfort_limit - current_temp
    if temp_to_limit <= 0:
        return 0  # Already at or above comfort limit

    minutes_to_limit = int(temp_to_limit / temp_change_per_minute)

    # Add some randomness for realism but keep deterministic for local seeded mode
    # Use building params as seed for deterministic results
    deterministic_factor = int((thermal_mass * 100 + insulation_factor * 10) % 20)
    minutes_to_limit = max(10, min(180, minutes_to_limit + deterministic_factor))

    logger.debug(
        f"Thermal runway calculation: {current_temp}°C → {comfort_limit}°C, "
        f"outside: {outside_temp}°C, transfer: {heat_transfer_coefficient:.4f}, "
        f"result: {minutes_to_limit} minutes"
    )

    return minutes_to_limit


def calculate_precooling_benefit(building_params: dict, pre_cooling_temp: float, pre_cooling_duration: int) -> int:
    """
    Calculate extended thermal runway minutes from pre-cooling.

    Pre-cooling lowers the starting temperature, providing more buffer before
    reaching comfort limit. The benefit depends on building thermal mass and
    pre-cooling depth/duration.

    Args:
        building_params: Dictionary with thermal_mass, insulation_factor
        pre_cooling_temp: Target pre-cooling temperature in °C
        pre_cooling_duration: Duration of pre-cooling in minutes

    Returns:
        Additional minutes of thermal runway gained from pre-cooling
    """
    thermal_mass = building_params.get("thermal_mass", 0.8)
    insulation_factor = building_params.get("insulation_factor", 0.6)

    # Base benefit calculation
    # Higher thermal mass = more benefit from pre-cooling (stores more "coolth")
    mass_factor = thermal_mass * 1.5

    # Better insulation = longer benefit retention
    insulation_factor_benefit = insulation_factor * 0.8

    # Calculate benefit based on pre-cooling parameters
    # Typical pre-cooling drops temperature 2-4°C below normal
    temp_drop = 22.4 - pre_cooling_temp  # Assuming normal temp is 22.4°C
    temp_drop_factor = max(0.5, min(2.0, temp_drop / 2.0))

    # Duration factor: longer pre-cooling = more uniform cooling
    duration_factor = min(1.5, pre_cooling_duration / 60.0)

    # Calculate total benefit
    base_benefit = 30  # Base 30 minutes benefit
    additional_benefit = int(
        base_benefit * mass_factor * insulation_factor_benefit * temp_drop_factor * duration_factor
    )

    # Ensure reasonable range
    additional_benefit = max(20, min(120, additional_benefit))

    logger.debug(
        f"Pre-cooling benefit: temp_drop={temp_drop:.1f}°C, duration={pre_cooling_duration}min, "
        f"mass_factor={mass_factor:.2f}, benefit={additional_benefit}min"
    )

    return additional_benefit


def generate_thermal_curve(
    start_temp: float, comfort_limit: float, outage_duration: int, building_params: dict
) -> list[tuple[float, float]]:
    """
    Generate temperature points over time during an outage.

    Args:
        start_temp: Starting temperature in °C
        comfort_limit: Comfort temperature limit in °C
        outage_duration: Outage duration in minutes
        building_params: Dictionary with thermal parameters

    Returns:
        List of (time_minutes, temperature) points
    """
    # Use default weather forecast for curve generation
    weather_forecast = {"outside_temp": 32.0, "solar_load": 0.7, "humidity": 65}

    # Calculate temperature at each time point
    points = []
    _current_temp = start_temp

    # Time points: every 15 minutes for first hour, then every 30 minutes
    time_points = []
    for t in range(0, min(60, outage_duration) + 1, 15):
        time_points.append(t)
    for t in range(60, outage_duration + 1, 30):
        if t not in time_points:
            time_points.append(t)

    # Ensure we include the endpoint
    if outage_duration not in time_points:
        time_points.append(outage_duration)
        time_points.sort()

    # Calculate temperature at each time point
    for time_minutes in time_points:
        if time_minutes == 0:
            points.append((0.0, start_temp))
            continue

        # Calculate temperature using the runway function
        # For curve generation, we need incremental calculation
        # Simplified: linear interpolation based on runway calculation
        runway = calculate_thermal_runway(start_temp, comfort_limit, building_params, weather_forecast)

        if runway == 0:
            # Already at comfort limit
            temp = comfort_limit
        else:
            # Linear temperature rise (simplified)
            progress = min(1.0, time_minutes / runway)
            temp = start_temp + (comfort_limit - start_temp) * progress

            # Add some curvature for realism
            if progress > 0.5:
                # Accelerate toward the end
                acceleration = 1.0 + (progress - 0.5) * 0.5
                temp = start_temp + (comfort_limit - start_temp) * progress * acceleration

        # Ensure we don't exceed comfort limit
        temp = min(temp, comfort_limit * 1.1)  # Allow slight overshoot

        points.append((float(time_minutes), round(temp, 1)))

    logger.debug(
        f"Generated thermal curve: {len(points)} points, {start_temp}°C → {points[-1][1]}°C over {outage_duration}min"
    )

    return points


def get_gateway_theatre_params() -> dict:
    """
    Get hardcoded building parameters for Gateway Theatre (seed consistency).

    Returns:
        Dictionary with thermal parameters for Gateway Theatre
    """
    return {
        "thermal_mass": 0.8,  # High thermal mass (concrete construction)
        "insulation_factor": 0.6,  # Moderate insulation
        "internal_heat_gain": 0.5,  # Moderate internal heat from people/equipment
        "site_type": "shopping_mall",
        "floor_area_sqm": 85000,
        "occupancy": 1200,
    }


def get_sandton_city_params() -> dict:
    """
    Get building parameters for Sandton City (medium complexity).

    Returns:
        Dictionary with thermal parameters for Sandton City
    """
    return {
        "thermal_mass": 0.7,
        "insulation_factor": 0.7,  # Better insulation (modern building)
        "internal_heat_gain": 0.6,  # Higher internal heat (more equipment)
        "site_type": "office_tower",
        "floor_area_sqm": 65000,
        "occupancy": 800,
    }


def get_centurion_mall_params() -> dict:
    """
    Get building parameters for Centurion Mall (complex scenario).

    Returns:
        Dictionary with thermal parameters for Centurion Mall
    """
    return {
        "thermal_mass": 0.9,  # Very high thermal mass
        "insulation_factor": 0.5,  # Poorer insulation (older building)
        "internal_heat_gain": 0.7,  # High internal heat
        "site_type": "mixed_use",
        "floor_area_sqm": 95000,
        "occupancy": 1500,
    }


# Example usage and test
if __name__ == "__main__":
    # Configure logging
    import sys

    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

    # Test with Gateway Theatre parameters
    building_params = get_gateway_theatre_params()
    weather_forecast = {"outside_temp": 32.0, "solar_load": 0.7, "humidity": 65}

    print("Testing thermal model service...")
    print(f"Building params: {building_params}")

    # Test thermal runway calculation
    runway = calculate_thermal_runway(22.4, 26.0, building_params, weather_forecast)
    print(f"Thermal runway: {runway} minutes")

    # Test pre-cooling benefit
    benefit = calculate_precooling_benefit(building_params, 20.0, 45)
    print(f"Pre-cooling benefit: +{benefit} minutes")

    # Test thermal curve generation
    curve = generate_thermal_curve(22.4, 26.0, 180, building_params)
    print(f"Thermal curve points: {len(curve)}")
    for time, temp in curve[:5]:  # Show first 5 points
        print(f"  {time}min: {temp}°C")

    print("Thermal model service test complete!")
