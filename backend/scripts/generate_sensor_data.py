#!/usr/bin/env python3
"""
Sensor Data Generator for BMS Intelligence Platform.

Generates realistic time-series sensor data for building equipment
with daily patterns, weekend variations, and embedded anomalies.

Usage:
    python generate_sensor_data.py
"""

import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

# Seed for reproducibility
RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# Data directory
DATA_DIR = Path(__file__).parent.parent / "app" / "data"

# Time parameters
START_DATE = datetime(2025, 12, 24)  # 30 days before "today"
END_DATE = datetime(2026, 1, 23)  # "Today"
HOURS_PER_DAY = 24

# Equipment with anomalies (to be injected in T8)
ANOMALY_EQUIPMENT = {
    "eqp-003": "bearing_degradation",  # AHU-7 at Sandton
    "eqp-017": "fuel_consumption_spike",  # Generator at Rosebank
    "eqp-055": "refrigerant_leak",  # Chiller at V&A
    "eqp-095": "battery_degradation",  # UPS at Umhlanga
}


def load_equipment() -> list[dict]:
    """Load equipment from JSON file."""
    with open(DATA_DIR / "equipment.json") as f:
        return json.load(f)


def load_sites() -> list[dict]:
    """Load sites from JSON file."""
    with open(DATA_DIR / "sites.json") as f:
        return json.load(f)


def get_site_hours(sites: list[dict], site_id: str) -> tuple[int, int]:
    """Get operating hours for a site."""
    site = next((s for s in sites if s["id"] == site_id), None)
    if site:
        start = int(site["operating_hours"]["start"].split(":")[0])
        end = int(site["operating_hours"]["end"].split(":")[0])
        return start, end
    return 8, 17  # Default office hours


def is_weekend(dt: datetime) -> bool:
    """Check if date is a weekend."""
    return dt.weekday() >= 5


def is_public_holiday(dt: datetime) -> bool:
    """Check if date is a South African public holiday (simplified)."""
    holidays = [
        (12, 25),  # Christmas
        (12, 26),  # Day of Goodwill
        (1, 1),    # New Year
    ]
    return (dt.month, dt.day) in holidays


def get_occupancy_factor(dt: datetime, start_hour: int, end_hour: int) -> float:
    """
    Calculate occupancy factor (0-1) based on time of day.

    Returns a value representing building occupancy which affects
    HVAC loads, power consumption, etc.
    """
    hour = dt.hour

    # Weekends and holidays have minimal occupancy
    if is_weekend(dt) or is_public_holiday(dt):
        if 8 <= hour <= 14:  # Some weekend activity
            return 0.15
        return 0.05

    # Weekday patterns
    if hour < start_hour:
        return 0.1  # Night security, essential systems
    elif hour == start_hour:
        return 0.3  # Early arrivals
    elif start_hour < hour < start_hour + 2:
        return 0.5 + (hour - start_hour) * 0.25  # Morning ramp-up
    elif start_hour + 2 <= hour <= end_hour - 2:
        return 1.0  # Peak occupancy
    elif end_hour - 2 < hour <= end_hour:
        return 0.8 - (hour - (end_hour - 2)) * 0.2  # Evening wind-down
    elif end_hour < hour <= end_hour + 2:
        return 0.3  # Late workers
    else:
        return 0.1  # Night


def get_seasonal_factor(dt: datetime) -> float:
    """
    Calculate seasonal factor for cooling loads.

    Summer (Dec-Feb) in South Africa = higher cooling demand
    Winter (Jun-Aug) = lower cooling demand
    """
    month = dt.month
    if month in [12, 1, 2]:  # Summer
        return 1.2
    elif month in [6, 7, 8]:  # Winter
        return 0.7
    elif month in [3, 4, 5]:  # Autumn
        return 0.9
    else:  # Spring
        return 1.0


def generate_temperature(
    dt: datetime,
    base_temp: float,
    occupancy: float,
    equipment_type: str,
) -> float:
    """
    Generate realistic temperature reading.

    Temperature varies with:
    - Time of day (cooler at night)
    - Occupancy (more people = more heat)
    - Random noise
    """
    # Daily temperature cycle (warmer in afternoon)
    hour_factor = math.sin((dt.hour - 6) * math.pi / 12) * 1.5

    # Occupancy heat
    occupancy_heat = occupancy * 1.5

    # Random noise
    noise = random.gauss(0, 0.3)

    temp = base_temp + hour_factor + occupancy_heat + noise
    return round(temp, 1)


def generate_humidity(dt: datetime, temp: float) -> float:
    """
    Generate realistic humidity reading.

    Higher humidity in morning, inversely related to temperature.
    """
    # Morning humidity peak
    hour_factor = math.sin((dt.hour + 6) * math.pi / 12) * 5

    # Temperature inverse relationship
    temp_factor = (22 - temp) * 0.5

    # Random noise
    noise = random.gauss(0, 2)

    humidity = 50 + hour_factor + temp_factor + noise
    return round(max(30, min(70, humidity)), 1)


def generate_power(
    dt: datetime,
    base_power: float,
    occupancy: float,
    equipment_type: str,
) -> float:
    """
    Generate realistic power consumption reading.

    Power varies with:
    - Occupancy
    - Equipment cycling
    - Random load variations
    """
    # Base load (always on)
    base = base_power * 0.3

    # Occupancy-driven load
    occ_load = base_power * 0.6 * occupancy

    # Equipment cycling (small variations)
    cycle = math.sin(dt.hour * math.pi / 3 + random.random()) * base_power * 0.05

    # Random noise
    noise = random.gauss(0, base_power * 0.02)

    power = base + occ_load + cycle + noise
    return round(max(0, power), 2)


def generate_vibration(
    dt: datetime,
    base_vibration: float,
    equipment_id: str,
    day_index: int,
) -> float:
    """
    Generate vibration reading with potential anomaly pattern.

    For AHU-7 (eqp-003), gradually increase vibration to simulate
    bearing degradation.
    """
    # Normal operation noise
    noise = random.gauss(0, base_vibration * 0.1)
    vibration = base_vibration + noise

    # Add anomaly pattern for bearing degradation
    if equipment_id == "eqp-003":
        # Vibration increases by ~40% over 3 weeks (21 days)
        # Start degradation from day 7
        if day_index > 7:
            degradation_days = day_index - 7
            degradation_factor = 1 + (degradation_days / 21) * 0.4
            vibration *= degradation_factor
            # Add occasional spikes
            if random.random() < 0.1:  # 10% chance of spike
                vibration *= 1.15

    return round(vibration, 2)


def generate_efficiency(
    dt: datetime,
    base_efficiency: float,
    equipment_id: str,
    day_index: int,
) -> float:
    """
    Generate efficiency reading with potential anomaly pattern.

    For Chiller at V&A (eqp-055), gradually decrease efficiency
    to simulate refrigerant leak.
    """
    # Normal variation
    noise = random.gauss(0, 1)
    efficiency = base_efficiency + noise

    # Add anomaly pattern for refrigerant leak
    if equipment_id == "eqp-055":
        # Efficiency drops by ~2% per week
        # Start leak from day 5
        if day_index > 5:
            leak_days = day_index - 5
            efficiency_drop = (leak_days / 7) * 2  # 2% per week
            efficiency -= efficiency_drop

    return round(max(50, efficiency), 1)


def generate_battery_runtime(
    dt: datetime,
    base_runtime: float,
    equipment_id: str,
    day_index: int,
) -> float:
    """
    Generate UPS battery runtime with potential anomaly pattern.

    For UPS at Umhlanga (eqp-095), gradually decrease runtime
    to simulate battery degradation.
    """
    # Temperature affects battery life (warmer = shorter)
    temp_factor = 1 - (get_seasonal_factor(dt) - 1) * 0.05

    # Normal variation
    noise = random.gauss(0, base_runtime * 0.02)
    runtime = base_runtime * temp_factor + noise

    # Add anomaly pattern for battery degradation
    if equipment_id == "eqp-095":
        # Runtime decreases ~1 minute per day
        # Start degradation from day 10
        if day_index > 10:
            degradation_days = day_index - 10
            runtime -= degradation_days * 1  # 1 minute per day

    return round(max(5, runtime), 1)


def generate_fuel_consumption(
    dt: datetime,
    base_consumption: float,
    occupancy: float,
    equipment_id: str,
    day_index: int,
) -> float:
    """
    Generate generator fuel consumption with potential anomaly pattern.

    For Generator at Rosebank (eqp-017), show fuel consumption spike
    to simulate injector issue.
    """
    # Load-based consumption
    load_factor = 0.3 + occupancy * 0.7

    # Normal variation
    noise = random.gauss(0, base_consumption * 0.03)
    consumption = base_consumption * load_factor + noise

    # Add anomaly pattern for fuel consumption spike
    if equipment_id == "eqp-017":
        # Consumption spikes by 25% after day 15
        if day_index > 15:
            consumption *= 1.25
            # Occasional larger spikes
            if random.random() < 0.15:
                consumption *= 1.1

    return round(consumption, 2)


def generate_sensors(equipment: list[dict]) -> list[dict]:
    """Generate sensor definitions for all equipment."""
    sensors = []
    sensor_id = 1

    sensor_templates = {
        "ahu": [
            {"type": "temperature", "unit": "°C", "location": "supply_air"},
            {"type": "temperature", "unit": "°C", "location": "return_air"},
            {"type": "humidity", "unit": "%RH", "location": "supply_air"},
            {"type": "power", "unit": "kW", "location": "main"},
            {"type": "vibration", "unit": "mm/s", "location": "motor"},
        ],
        "chiller": [
            {"type": "temperature", "unit": "°C", "location": "supply_water"},
            {"type": "temperature", "unit": "°C", "location": "return_water"},
            {"type": "power", "unit": "kW", "location": "main"},
            {"type": "efficiency", "unit": "COP", "location": "system"},
            {"type": "pressure", "unit": "kPa", "location": "refrigerant"},
        ],
        "cooling_tower": [
            {"type": "temperature", "unit": "°C", "location": "water_in"},
            {"type": "temperature", "unit": "°C", "location": "water_out"},
            {"type": "power", "unit": "kW", "location": "fan"},
        ],
        "ups": [
            {"type": "power", "unit": "kW", "location": "load"},
            {"type": "battery_voltage", "unit": "V", "location": "battery"},
            {"type": "battery_runtime", "unit": "min", "location": "battery"},
            {"type": "temperature", "unit": "°C", "location": "cabinet"},
        ],
        "generator": [
            {"type": "fuel_level", "unit": "%", "location": "tank"},
            {"type": "fuel_consumption", "unit": "L/hr", "location": "engine"},
            {"type": "power", "unit": "kW", "location": "output"},
            {"type": "temperature", "unit": "°C", "location": "engine"},
            {"type": "runtime", "unit": "hrs", "location": "engine"},
        ],
        "transformer": [
            {"type": "temperature", "unit": "°C", "location": "winding"},
            {"type": "power", "unit": "kW", "location": "load"},
        ],
        "fire_panel": [
            {"type": "status", "unit": "boolean", "location": "main"},
            {"type": "battery_voltage", "unit": "V", "location": "backup"},
        ],
        "fcu": [
            {"type": "temperature", "unit": "°C", "location": "room"},
            {"type": "power", "unit": "kW", "location": "fan"},
        ],
        "crac": [
            {"type": "temperature", "unit": "°C", "location": "supply_air"},
            {"type": "temperature", "unit": "°C", "location": "return_air"},
            {"type": "humidity", "unit": "%RH", "location": "room"},
            {"type": "power", "unit": "kW", "location": "compressor"},
        ],
        "split_unit": [
            {"type": "temperature", "unit": "°C", "location": "room"},
            {"type": "power", "unit": "kW", "location": "outdoor"},
        ],
        "vrf": [
            {"type": "temperature", "unit": "°C", "location": "outdoor"},
            {"type": "power", "unit": "kW", "location": "compressor"},
        ],
        "vesda": [
            {"type": "smoke_level", "unit": "obs/m", "location": "main"},
            {"type": "airflow", "unit": "L/min", "location": "sampling"},
        ],
        "bms_controller": [
            {"type": "cpu_usage", "unit": "%", "location": "main"},
            {"type": "points_online", "unit": "count", "location": "network"},
        ],
        "water_heater": [
            {"type": "temperature", "unit": "°C", "location": "water"},
            {"type": "power", "unit": "kW", "location": "element"},
        ],
    }

    for eq in equipment:
        eq_type = eq["type"]
        templates = sensor_templates.get(eq_type, [])

        for template in templates:
            sensors.append({
                "id": f"sensor-{sensor_id:04d}",
                "equipment_id": eq["id"],
                "site_id": eq["site_id"],
                "type": template["type"],
                "unit": template["unit"],
                "location": template["location"],
                "name": f"{eq['name']} {template['type'].replace('_', ' ').title()}",
            })
            sensor_id += 1

    return sensors


def generate_readings(
    sensors: list[dict],
    equipment: list[dict],
    sites: list[dict],
) -> list[dict]:
    """Generate 30 days of hourly readings for all sensors."""
    readings = []

    # Create equipment lookup
    eq_lookup = {eq["id"]: eq for eq in equipment}

    # Generate readings for each sensor
    for sensor in sensors:
        eq = eq_lookup.get(sensor["equipment_id"])
        if not eq:
            continue

        site_id = eq["site_id"]
        start_hour, end_hour = get_site_hours(sites, site_id)

        # Get base values based on equipment capacity
        capacity_str = eq.get("capacity", "10kW")
        try:
            if "kW" in capacity_str:
                base_power = float(capacity_str.replace("kW", ""))
            elif "kVA" in capacity_str:
                base_power = float(capacity_str.replace("kVA", "")) * 0.8
            else:
                base_power = 10
        except:
            base_power = 10

        current = START_DATE
        day_index = 0

        while current <= END_DATE:
            occupancy = get_occupancy_factor(current, start_hour, end_hour)
            seasonal = get_seasonal_factor(current)

            # Generate reading based on sensor type
            value = None

            if sensor["type"] == "temperature":
                if "supply" in sensor["location"] or "room" in sensor["location"]:
                    base_temp = 20.0  # Setpoint
                elif "return" in sensor["location"]:
                    base_temp = 23.0  # Return air warmer
                elif "water" in sensor["location"] and "supply" in sensor["location"]:
                    base_temp = 7.0  # Chilled water supply
                elif "water" in sensor["location"] and "return" in sensor["location"]:
                    base_temp = 12.0  # Chilled water return
                elif "outdoor" in sensor["location"]:
                    base_temp = 25.0 * seasonal
                elif "engine" in sensor["location"]:
                    base_temp = 85.0 if occupancy > 0.3 else 25.0
                elif "winding" in sensor["location"]:
                    base_temp = 50.0 + occupancy * 20
                elif "cabinet" in sensor["location"]:
                    base_temp = 30.0
                else:
                    base_temp = 22.0
                value = generate_temperature(current, base_temp, occupancy, eq["type"])

            elif sensor["type"] == "humidity":
                temp = generate_temperature(current, 22, occupancy, eq["type"])
                value = generate_humidity(current, temp)

            elif sensor["type"] == "power":
                value = generate_power(current, base_power, occupancy, eq["type"])

            elif sensor["type"] == "vibration":
                base_vib = 2.0  # mm/s normal
                value = generate_vibration(current, base_vib, eq["id"], day_index)

            elif sensor["type"] == "efficiency":
                base_eff = 92.0  # % or COP normalized
                value = generate_efficiency(current, base_eff, eq["id"], day_index)

            elif sensor["type"] == "battery_runtime":
                base_runtime = 30.0  # minutes
                value = generate_battery_runtime(current, base_runtime, eq["id"], day_index)

            elif sensor["type"] == "fuel_consumption":
                base_consumption = 15.0  # L/hr
                value = generate_fuel_consumption(
                    current, base_consumption, occupancy, eq["id"], day_index
                )

            elif sensor["type"] == "battery_voltage":
                value = round(random.gauss(220, 2), 1)

            elif sensor["type"] == "fuel_level":
                # Simulate fuel being used and refilled
                value = round(50 + random.gauss(0, 10) + 30 * math.sin(day_index * 0.3), 1)
                value = max(10, min(100, value))

            elif sensor["type"] == "pressure":
                value = round(random.gauss(450, 10), 1)

            elif sensor["type"] == "status":
                value = 1.0 if random.random() > 0.001 else 0.0  # Rarely false

            elif sensor["type"] == "runtime":
                value = round(12000 + day_index * 0.5 + occupancy * 2, 1)

            elif sensor["type"] == "smoke_level":
                value = round(random.gauss(0.01, 0.002), 4)

            elif sensor["type"] == "airflow":
                value = round(random.gauss(120, 5), 1)

            elif sensor["type"] == "cpu_usage":
                value = round(15 + occupancy * 30 + random.gauss(0, 5), 1)

            elif sensor["type"] == "points_online":
                capacity_points = int(eq.get("capacity", "100 points").split()[0])
                value = round(capacity_points * (0.95 + random.gauss(0, 0.02)))

            else:
                value = round(random.gauss(50, 10), 1)

            if value is not None:
                readings.append({
                    "sensor_id": sensor["id"],
                    "timestamp": current.isoformat(),
                    "value": value,
                })

            current += timedelta(hours=1)
            if current.hour == 0:
                day_index += 1

    return readings


def main():
    """Main entry point."""
    print("Loading equipment data...")
    equipment = load_equipment()
    sites = load_sites()

    print(f"Generating sensors for {len(equipment)} equipment items...")
    sensors = generate_sensors(equipment)

    print(f"Generated {len(sensors)} sensors")

    # Save sensors
    with open(DATA_DIR / "sensors.json", "w") as f:
        json.dump(sensors, f, indent=2)
    print("Saved sensors.json")

    print("Generating 30 days of hourly readings...")
    readings = generate_readings(sensors, equipment, sites)

    print(f"Generated {len(readings):,} readings")

    # Save readings
    with open(DATA_DIR / "readings.json", "w") as f:
        json.dump(readings, f)
    print("Saved readings.json")

    # Print summary
    print("\n=== Generation Summary ===")
    print(f"Sensors: {len(sensors)}")
    print(f"Readings: {len(readings):,}")
    print(f"Date range: {START_DATE.date()} to {END_DATE.date()}")
    print(f"Random seed: {RANDOM_SEED}")
    print("\nAnomalies embedded in:")
    for eq_id, anomaly_type in ANOMALY_EQUIPMENT.items():
        eq = next((e for e in equipment if e["id"] == eq_id), None)
        if eq:
            print(f"  - {eq['name']} at site {eq['site_id']}: {anomaly_type}")


if __name__ == "__main__":
    main()
