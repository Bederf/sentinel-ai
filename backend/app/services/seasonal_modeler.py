"""
South African Seasonal Modeling for Annual Building Simulations

Provides realistic seasonal variations for:
- Ambient temperature by month
- Solar generation efficiency
- Rainfall patterns and cloud cover
- Occupancy variations (holidays, school breaks)
- Equipment stress and fault probability
- HVAC load demand by season
"""

from datetime import date
from typing import Dict, Optional
from enum import Enum
from dataclasses import dataclass
import random


class Season(str, Enum):
    """South African seasons."""

    SUMMER = "summer"  # Dec-Feb: Hot, rainy (summer rainfall regions)
    AUTUMN = "autumn"  # Mar-May: Cooling, dry
    WINTER = "winter"  # Jun-Aug: Cool, drier
    SPRING = "spring"  # Sep-Nov: Warming, occasional rain


@dataclass
class SeasonalConfig:
    """Configuration for a month in South Africa."""

    month: int  # 1-12
    month_name: str  # "January", "February", etc.
    season: Season

    # Temperature (Celsius)
    ambient_temp_min: float  # Typical minimum
    ambient_temp_max: float  # Typical maximum
    ambient_temp_avg: float  # Average

    # Rainfall
    rainfall_probability: float  # 0.0-1.0: chance of rain on any day
    rainfall_avg_days: int  # Average rainy days in month
    avg_rainfall_mm: float  # Average total rainfall
    cloud_cover_percent: float  # 0.0-1.0: average cloud cover

    # Solar generation (relative to optimal)
    solar_efficiency: float  # 0.0-1.0: efficiency vs peak
    daylight_hours: float  # Sunrise to sunset

    # Occupancy
    school_holidays: bool  # School breaks
    summer_break: bool  # Dec 16 - Jan 15
    occupancy_variance: float  # ±% from baseline

    # Equipment
    hvac_load_percent: float  # % of peak load
    fault_probability_multiplier: float  # × base probability

    # Public holidays (South Africa)
    public_holidays: int  # Number of public holidays


# South African Seasonal Configuration
SA_SEASONAL_DATA = {
    1: SeasonalConfig(
        month=1,
        month_name="January",
        season=Season.SUMMER,
        ambient_temp_min=18,
        ambient_temp_max=29,
        ambient_temp_avg=24,
        rainfall_probability=0.35,
        rainfall_avg_days=12,
        avg_rainfall_mm=85,
        cloud_cover_percent=0.45,
        solar_efficiency=0.75,
        daylight_hours=14.5,
        school_holidays=True,  # Still in summer break (until ~Jan 15)
        summer_break=True,
        occupancy_variance=0.20,  # 20% lower: summer break
        hvac_load_percent=95,
        fault_probability_multiplier=1.8,
        public_holidays=1,  # New Year's Day (Jan 1)
    ),
    2: SeasonalConfig(
        month=2,
        month_name="February",
        season=Season.SUMMER,
        ambient_temp_min=18,
        ambient_temp_max=28,
        ambient_temp_avg=23,
        rainfall_probability=0.30,
        rainfall_avg_days=10,
        avg_rainfall_mm=75,
        cloud_cover_percent=0.40,
        solar_efficiency=0.80,
        daylight_hours=14.0,
        school_holidays=False,
        summer_break=False,
        occupancy_variance=-0.05,  # 5% lower: tail end of summer
        hvac_load_percent=90,
        fault_probability_multiplier=1.6,
        public_holidays=1,  # Human Rights Day (Feb 21)
    ),
    3: SeasonalConfig(
        month=3,
        month_name="March",
        season=Season.AUTUMN,
        ambient_temp_min=16,
        ambient_temp_max=26,
        ambient_temp_avg=21,
        rainfall_probability=0.20,
        rainfall_avg_days=7,
        avg_rainfall_mm=60,
        cloud_cover_percent=0.35,
        solar_efficiency=0.85,
        daylight_hours=13.0,
        school_holidays=True,  # Easter break (varies)
        summer_break=False,
        occupancy_variance=0.15,  # 15% lower: Easter holiday
        hvac_load_percent=70,
        fault_probability_multiplier=1.1,
        public_holidays=2,  # Good Friday, Family Day
    ),
    4: SeasonalConfig(
        month=4,
        month_name="April",
        season=Season.AUTUMN,
        ambient_temp_min=14,
        ambient_temp_max=24,
        ambient_temp_avg=19,
        rainfall_probability=0.15,
        rainfall_avg_days=5,
        avg_rainfall_mm=40,
        cloud_cover_percent=0.30,
        solar_efficiency=0.90,
        daylight_hours=12.5,
        school_holidays=False,
        summer_break=False,
        occupancy_variance=0.0,  # Normal
        hvac_load_percent=60,
        fault_probability_multiplier=0.9,
        public_holidays=1,  # Workers Day (May 1 - near)
    ),
    5: SeasonalConfig(
        month=5,
        month_name="May",
        season=Season.AUTUMN,
        ambient_temp_min=12,
        ambient_temp_max=22,
        ambient_temp_avg=17,
        rainfall_probability=0.12,
        rainfall_avg_days=4,
        avg_rainfall_mm=35,
        cloud_cover_percent=0.28,
        solar_efficiency=0.92,
        daylight_hours=12.0,
        school_holidays=False,
        summer_break=False,
        occupancy_variance=0.0,  # Normal
        hvac_load_percent=55,
        fault_probability_multiplier=0.8,
        public_holidays=1,  # Workers Day (May 1)
    ),
    6: SeasonalConfig(
        month=6,
        month_name="June",
        season=Season.WINTER,
        ambient_temp_min=8,
        ambient_temp_max=18,
        ambient_temp_avg=13,
        rainfall_probability=0.08,
        rainfall_avg_days=3,
        avg_rainfall_mm=25,
        cloud_cover_percent=0.25,
        solar_efficiency=0.95,
        daylight_hours=11.5,
        school_holidays=True,  # School break (Jun 27 - Jul 6)
        summer_break=False,
        occupancy_variance=-0.25,  # 25% lower: school holidays
        hvac_load_percent=30,
        fault_probability_multiplier=0.7,
        public_holidays=1,  # Youth Day (Jun 16)
    ),
    7: SeasonalConfig(
        month=7,
        month_name="July",
        season=Season.WINTER,
        ambient_temp_min=7,
        ambient_temp_max=17,
        ambient_temp_avg=12,
        rainfall_probability=0.10,
        rainfall_avg_days=3,
        avg_rainfall_mm=28,
        cloud_cover_percent=0.28,
        solar_efficiency=0.94,
        daylight_hours=11.5,
        school_holidays=True,  # Winter break continues (Jun 27 - Jul 6)
        summer_break=False,
        occupancy_variance=-0.20,  # 20% lower: school holidays (first week)
        hvac_load_percent=25,
        fault_probability_multiplier=0.6,
        public_holidays=0,  # No public holidays in July
    ),
    8: SeasonalConfig(
        month=8,
        month_name="August",
        season=Season.WINTER,
        ambient_temp_min=8,
        ambient_temp_max=19,
        ambient_temp_avg=13,
        rainfall_probability=0.12,
        rainfall_avg_days=4,
        avg_rainfall_mm=32,
        cloud_cover_percent=0.30,
        solar_efficiency=0.90,
        daylight_hours=12.0,
        school_holidays=False,
        summer_break=False,
        occupancy_variance=0.0,  # Normal: back to school
        hvac_load_percent=30,
        fault_probability_multiplier=0.7,
        public_holidays=1,  # Women's Day (Aug 9)
    ),
    9: SeasonalConfig(
        month=9,
        month_name="September",
        season=Season.SPRING,
        ambient_temp_min=11,
        ambient_temp_max=23,
        ambient_temp_avg=17,
        rainfall_probability=0.15,
        rainfall_avg_days=5,
        avg_rainfall_mm=40,
        cloud_cover_percent=0.32,
        solar_efficiency=0.88,
        daylight_hours=12.5,
        school_holidays=False,
        summer_break=False,
        occupancy_variance=0.0,  # Normal
        hvac_load_percent=50,
        fault_probability_multiplier=0.8,
        public_holidays=1,  # Heritage Day (Sep 24)
    ),
    10: SeasonalConfig(
        month=10,
        month_name="October",
        season=Season.SPRING,
        ambient_temp_min=14,
        ambient_temp_max=25,
        ambient_temp_avg=20,
        rainfall_probability=0.18,
        rainfall_avg_days=6,
        avg_rainfall_mm=50,
        cloud_cover_percent=0.35,
        solar_efficiency=0.85,
        daylight_hours=13.0,
        school_holidays=False,
        summer_break=False,
        occupancy_variance=0.0,  # Normal
        hvac_load_percent=65,
        fault_probability_multiplier=0.9,
        public_holidays=0,  # No public holidays
    ),
    11: SeasonalConfig(
        month=11,
        month_name="November",
        season=Season.SPRING,
        ambient_temp_min=17,
        ambient_temp_max=28,
        ambient_temp_avg=22,
        rainfall_probability=0.25,
        rainfall_avg_days=8,
        avg_rainfall_mm=65,
        cloud_cover_percent=0.38,
        solar_efficiency=0.82,
        daylight_hours=13.5,
        school_holidays=False,
        summer_break=False,
        occupancy_variance=0.0,  # Normal
        hvac_load_percent=80,
        fault_probability_multiplier=1.1,
        public_holidays=0,  # No public holidays
    ),
    12: SeasonalConfig(
        month=12,
        month_name="December",
        season=Season.SUMMER,
        ambient_temp_min=19,
        ambient_temp_max=30,
        ambient_temp_avg=25,
        rainfall_probability=0.35,
        rainfall_avg_days=12,
        avg_rainfall_mm=85,
        cloud_cover_percent=0.42,
        solar_efficiency=0.78,
        daylight_hours=14.5,
        school_holidays=True,  # School break (Dec 16 - Jan 15)
        summer_break=True,
        occupancy_variance=-0.25,  # 25% lower: Christmas/New Year holidays
        hvac_load_percent=100,
        fault_probability_multiplier=1.9,
        public_holidays=2,  # Christmas Day, Day of Goodwill
    ),
}


class SeasonalModeler:
    """Applies South African seasonal modeling to simulations."""

    def __init__(self, seed: Optional[int] = None):
        """Initialize with optional seed for reproducibility."""
        self.rng = random.Random(seed)

    def get_config_for_date(self, simulated_date: date) -> SeasonalConfig:
        """Get seasonal configuration for a specific date."""
        month = simulated_date.month
        return SA_SEASONAL_DATA[month]

    def get_ambient_temperature(self, simulated_date: date, hour: int, rain_today: bool = False) -> float:
        """
        Get ambient temperature for a specific date and hour.

        Temperature varies by:
        - Time of day (cooler at night, peak in afternoon)
        - Month (seasonal)
        - Rain (cooler when raining)
        """
        config = self.get_config_for_date(simulated_date)

        # Daily temperature curve: coldest at 6am, warmest at 3pm
        # Temperature at hour = min + (max - min) * sin((hour - 6) * π / 12)
        import math

        hour_factor = math.sin((hour - 6) * math.pi / 12)
        temp_range = config.ambient_temp_max - config.ambient_temp_min
        temperature = config.ambient_temp_min + (temp_range / 2) + (temp_range / 2) * hour_factor

        # Rain reduces temperature by 2-4°C
        if rain_today:
            temperature -= self.rng.uniform(2, 4)

        # Add small random variation (±0.5°C)
        temperature += self.rng.uniform(-0.5, 0.5)

        return round(temperature, 1)

    def should_rain_today(self, simulated_date: date) -> bool:
        """Determine if it rains on a given day."""
        config = self.get_config_for_date(simulated_date)
        return self.rng.random() < config.rainfall_probability

    def get_cloud_cover_percent(self, simulated_date: date) -> float:
        """
        Get cloud cover percentage (0-100) for a day.

        Used to reduce solar generation efficiency.
        """
        config = self.get_config_for_date(simulated_date)

        # Base cloud cover ± variation
        variation = self.rng.uniform(-0.15, 0.15)  # ±15%
        cloud_cover = max(0.0, min(1.0, config.cloud_cover_percent + variation))

        return cloud_cover * 100  # Return as percentage

    def get_solar_generation_factor(self, simulated_date: date, cloud_cover: float) -> float:
        """
        Get solar generation efficiency factor (0-1).

        Accounts for:
        - Seasonal variation (winter shorter days, less intense sun)
        - Cloud cover (rainy days reduce output)
        - Latitude effects already in monthly config
        """
        config = self.get_config_for_date(simulated_date)

        # Base efficiency from month
        efficiency = config.solar_efficiency

        # Cloud cover reduces efficiency by 30-70%
        # 0% cloud = no reduction
        # 100% cloud = 70% reduction
        cloud_factor = 1.0 - (cloud_cover / 100.0) * 0.70

        return efficiency * cloud_factor

    def get_occupancy_factor(self, simulated_date: date, hour: int, rain_today: bool = False) -> float:
        """
        Get occupancy factor (0-1) for a specific date and hour.

        Accounts for:
        - Time of day (0-8 low, 8-18 peak, 18+ declining)
        - Day of week (weekends lower)
        - Holidays and school breaks
        - Rain (some people WFH on rainy days)
        """
        config = self.get_config_for_date(simulated_date)

        # Base occupancy by hour
        if hour < 8 or hour >= 20:
            base_occupancy = 0.0  # Outside working hours
        elif hour < 9:
            base_occupancy = 0.3  # Morning arrival
        elif hour < 12:
            base_occupancy = 0.8  # Mid-morning peak
        elif hour < 14:
            base_occupancy = 0.6  # Lunch dip
        elif hour < 17:
            base_occupancy = 0.85  # Afternoon peak
        else:
            base_occupancy = 0.3  # Evening departure

        # Day of week variation
        weekday = simulated_date.weekday()  # 0=Monday, 6=Sunday
        if weekday == 4:  # Friday
            base_occupancy *= 0.80  # Early departures
        elif weekday in (5, 6):  # Weekend
            base_occupancy *= 0.30  # Minimal occupancy

        # Holiday/school break impact
        variance = config.occupancy_variance
        base_occupancy *= 1.0 + variance

        # Rain impact: 10% more WFH (reduced occupancy)
        if rain_today and 8 <= hour <= 18:
            base_occupancy *= 0.85  # 15% fewer in building

        return max(0.0, min(1.0, base_occupancy))

    def get_hvac_load_factor(self, simulated_date: date, occupancy_factor: float, ambient_temp: float) -> float:
        """
        Get HVAC load factor (0-1) based on seasonal demand and occupancy.

        Accounts for:
        - Season (winter low, summer high)
        - Occupancy level
        - Temperature deviation from setpoint
        """
        config = self.get_config_for_date(simulated_date)

        # Base seasonal load
        base_load = config.hvac_load_percent / 100.0

        # Occupancy contribution (more people = more load)
        occupancy_component = occupancy_factor * 0.7  # 70% of load from occupancy

        # Temperature deviation (too hot/cold = more work)
        # Assume setpoint 22°C, range 16-28°C for comfort
        temp_deviation = abs(ambient_temp - 22.0)
        if temp_deviation > 6:
            temp_factor = 1.0 + (temp_deviation - 6) / 10  # Extra load for extreme temps
        else:
            temp_factor = max(0.3, 1.0 - (6 - temp_deviation) / 10)

        # Combined: base (constant) + occupancy + temp effects
        hvac_load = (base_load * 0.3) + (occupancy_component * 0.4) + (temp_factor * 0.3)

        return max(0.0, min(1.0, hvac_load))

    def get_fault_probability_multiplier(self, simulated_date: date, is_rainy: bool = False) -> float:
        """
        Get equipment fault probability multiplier.

        Summer higher (chillers work hard), rain increases moisture faults.
        """
        config = self.get_config_for_date(simulated_date)
        multiplier = config.fault_probability_multiplier

        # Rain increases electrical/moisture faults
        if is_rainy:
            multiplier *= 1.3

        return multiplier

    def get_season_name(self, simulated_date: date) -> str:
        """Get human-readable season name."""
        config = self.get_config_for_date(simulated_date)
        return config.season.value.capitalize()

    def get_month_summary(self, month: int) -> Dict[str, any]:
        """Get summary statistics for a month."""
        config = SA_SEASONAL_DATA[month]
        return {
            "month": config.month_name,
            "season": config.season.value,
            "temp_range": f"{config.ambient_temp_min}°C - {config.ambient_temp_max}°C",
            "rainfall_days": config.rainfall_avg_days,
            "rainfall_mm": config.avg_rainfall_mm,
            "solar_efficiency": f"{config.solar_efficiency * 100:.0f}%",
            "hvac_load": f"{config.hvac_load_percent:.0f}%",
            "school_holidays": config.school_holidays,
            "public_holidays": config.public_holidays,
        }
