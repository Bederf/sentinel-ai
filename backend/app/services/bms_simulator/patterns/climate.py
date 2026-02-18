"""
Climate Pattern Generator

Generates climate-based variations for BMS simulation based on South African climate zones.
Includes temperature, humidity, and wet-bulb patterns for different regions.
"""

import numpy as np
from datetime import datetime
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class Season(str, Enum):
    """South African seasons."""
    SUMMER = "summer"      # Dec-Feb
    AUTUMN = "autumn"      # Mar-May
    WINTER = "winter"      # Jun-Aug
    SPRING = "spring"      # Sep-Nov


class ClimateZone(str, Enum):
    """South African climate zones."""
    JOHANNESBURG = "johannesburg"  # Highveld - hot summers, cool dry winters
    DURBAN = "durban"              # Subtropical - hot humid summers, mild winters
    CAPE_TOWN = "cape_town"        # Mediterranean - hot dry summers, cool wet winters
    PRETORIA = "pretoria"          # Similar to Johannesburg


@dataclass
class SeasonalClimate:
    """Climate parameters for a season."""
    temp_range: Tuple[float, float]      # Min/max outdoor temp (degC)
    humidity_range: Tuple[float, float]  # Min/max humidity (%RH)
    wet_bulb_range: Tuple[float, float]  # Min/max wet bulb (degC)
    solar_peak_hour: int = 14            # Hour of peak solar radiation
    solar_intensity: float = 1.0         # Relative solar intensity (0-1)


@dataclass
class ClimateProfile:
    """Complete climate profile for a location."""
    zone: ClimateZone
    summer: SeasonalClimate
    autumn: SeasonalClimate
    winter: SeasonalClimate
    spring: SeasonalClimate
    load_shedding_group: int = 1
    altitude_m: int = 0

    def get_season(self, dt: datetime) -> Season:
        """Determine season from datetime."""
        month = dt.month
        if month in [12, 1, 2]:
            return Season.SUMMER
        elif month in [3, 4, 5]:
            return Season.AUTUMN
        elif month in [6, 7, 8]:
            return Season.WINTER
        else:
            return Season.SPRING

    def get_seasonal_climate(self, dt: datetime) -> SeasonalClimate:
        """Get climate parameters for the given datetime."""
        season = self.get_season(dt)
        return {
            Season.SUMMER: self.summer,
            Season.AUTUMN: self.autumn,
            Season.WINTER: self.winter,
            Season.SPRING: self.spring,
        }[season]


# Climate profiles for South African regions
CLIMATE_PROFILES: Dict[str, ClimateProfile] = {
    "johannesburg": ClimateProfile(
        zone=ClimateZone.JOHANNESBURG,
        summer=SeasonalClimate(
            temp_range=(15.0, 30.0),
            humidity_range=(40.0, 75.0),
            wet_bulb_range=(16.0, 22.0),
            solar_peak_hour=14,
            solar_intensity=1.0,
        ),
        autumn=SeasonalClimate(
            temp_range=(10.0, 25.0),
            humidity_range=(35.0, 65.0),
            wet_bulb_range=(12.0, 18.0),
            solar_peak_hour=14,
            solar_intensity=0.85,
        ),
        winter=SeasonalClimate(
            temp_range=(2.0, 18.0),
            humidity_range=(25.0, 50.0),
            wet_bulb_range=(4.0, 12.0),
            solar_peak_hour=13,
            solar_intensity=0.7,
        ),
        spring=SeasonalClimate(
            temp_range=(12.0, 28.0),
            humidity_range=(30.0, 60.0),
            wet_bulb_range=(12.0, 20.0),
            solar_peak_hour=14,
            solar_intensity=0.9,
        ),
        load_shedding_group=4,
        altitude_m=1753,
    ),

    "durban": ClimateProfile(
        zone=ClimateZone.DURBAN,
        summer=SeasonalClimate(
            temp_range=(24.0, 32.0),
            humidity_range=(70.0, 95.0),
            wet_bulb_range=(24.0, 27.0),
            solar_peak_hour=14,
            solar_intensity=1.0,
        ),
        autumn=SeasonalClimate(
            temp_range=(18.0, 28.0),
            humidity_range=(55.0, 85.0),
            wet_bulb_range=(16.0, 22.0),
            solar_peak_hour=14,
            solar_intensity=0.85,
        ),
        winter=SeasonalClimate(
            temp_range=(14.0, 24.0),
            humidity_range=(50.0, 75.0),
            wet_bulb_range=(12.0, 18.0),
            solar_peak_hour=13,
            solar_intensity=0.75,
        ),
        spring=SeasonalClimate(
            temp_range=(18.0, 28.0),
            humidity_range=(55.0, 85.0),
            wet_bulb_range=(16.0, 22.0),
            solar_peak_hour=14,
            solar_intensity=0.9,
        ),
        load_shedding_group=5,
        altitude_m=8,
    ),

    "cape_town": ClimateProfile(
        zone=ClimateZone.CAPE_TOWN,
        summer=SeasonalClimate(
            temp_range=(16.0, 28.0),
            humidity_range=(35.0, 70.0),
            wet_bulb_range=(14.0, 20.0),
            solar_peak_hour=14,
            solar_intensity=1.0,
        ),
        autumn=SeasonalClimate(
            temp_range=(12.0, 22.0),
            humidity_range=(50.0, 80.0),
            wet_bulb_range=(12.0, 18.0),
            solar_peak_hour=14,
            solar_intensity=0.75,
        ),
        winter=SeasonalClimate(
            temp_range=(8.0, 17.0),
            humidity_range=(60.0, 90.0),
            wet_bulb_range=(8.0, 14.0),
            solar_peak_hour=13,
            solar_intensity=0.5,
        ),
        spring=SeasonalClimate(
            temp_range=(12.0, 22.0),
            humidity_range=(45.0, 75.0),
            wet_bulb_range=(12.0, 18.0),
            solar_peak_hour=14,
            solar_intensity=0.85,
        ),
        load_shedding_group=2,
        altitude_m=0,
    ),

    "pretoria": ClimateProfile(
        zone=ClimateZone.PRETORIA,
        summer=SeasonalClimate(
            temp_range=(17.0, 32.0),
            humidity_range=(45.0, 80.0),
            wet_bulb_range=(18.0, 24.0),
            solar_peak_hour=14,
            solar_intensity=1.0,
        ),
        autumn=SeasonalClimate(
            temp_range=(12.0, 26.0),
            humidity_range=(35.0, 65.0),
            wet_bulb_range=(12.0, 18.0),
            solar_peak_hour=14,
            solar_intensity=0.85,
        ),
        winter=SeasonalClimate(
            temp_range=(4.0, 20.0),
            humidity_range=(25.0, 50.0),
            wet_bulb_range=(5.0, 12.0),
            solar_peak_hour=13,
            solar_intensity=0.7,
        ),
        spring=SeasonalClimate(
            temp_range=(14.0, 30.0),
            humidity_range=(30.0, 60.0),
            wet_bulb_range=(14.0, 22.0),
            solar_peak_hour=14,
            solar_intensity=0.9,
        ),
        load_shedding_group=3,
        altitude_m=1339,
    ),
}


class ClimatePattern:
    """Generator for climate-based patterns in BMS data."""

    def __init__(
        self,
        climate_zone: str = "johannesburg",
        seed: int = 42,
    ):
        """
        Initialize the climate pattern generator.

        Args:
            climate_zone: Climate zone name (johannesburg, durban, cape_town, pretoria)
            seed: Random seed for reproducibility
        """
        self.profile = CLIMATE_PROFILES.get(
            climate_zone.lower(),
            CLIMATE_PROFILES["johannesburg"]
        )
        self.rng = np.random.default_rng(seed)

    def get_outdoor_temp(
        self,
        dt: datetime,
        noise_level: float = 0.05,
    ) -> float:
        """
        Get outdoor temperature for a given datetime.

        Temperature follows a sinusoidal diurnal pattern with seasonal variation.

        Args:
            dt: Datetime for the temperature
            noise_level: Random noise as fraction of range

        Returns:
            Outdoor temperature in degC
        """
        climate = self.profile.get_seasonal_climate(dt)
        temp_min, temp_max = climate.temp_range
        temp_range = temp_max - temp_min
        temp_mid = (temp_max + temp_min) / 2

        # Diurnal pattern: min at 6am, max at peak hour
        hour = dt.hour + dt.minute / 60
        phase = (hour - 6) / 24 * 2 * np.pi  # 6am = 0, peak = pi/2
        diurnal = np.sin(phase)

        # Adjust for solar peak hour
        peak_offset = (climate.solar_peak_hour - 14) / 24 * 2 * np.pi
        diurnal = np.sin(phase + peak_offset)

        # Base temperature
        temp = temp_mid + (temp_range / 2) * diurnal

        # Add noise
        noise = self.rng.normal(0, noise_level * temp_range)
        temp += noise

        return np.clip(temp, temp_min - 2, temp_max + 2)

    def get_outdoor_humidity(
        self,
        dt: datetime,
        outdoor_temp: Optional[float] = None,
        noise_level: float = 0.05,
    ) -> float:
        """
        Get outdoor humidity for a given datetime.

        Humidity is inversely related to temperature (higher temp = lower RH).

        Args:
            dt: Datetime for the humidity
            outdoor_temp: Outdoor temperature (calculated if not provided)
            noise_level: Random noise as fraction of range

        Returns:
            Outdoor humidity in %RH
        """
        climate = self.profile.get_seasonal_climate(dt)
        hum_min, hum_max = climate.humidity_range
        hum_range = hum_max - hum_min

        # Get temperature if not provided
        if outdoor_temp is None:
            outdoor_temp = self.get_outdoor_temp(dt, noise_level=0)

        # Inverse temperature relationship
        temp_min, temp_max = climate.temp_range
        temp_norm = (outdoor_temp - temp_min) / (temp_max - temp_min)
        temp_norm = np.clip(temp_norm, 0, 1)

        # Higher temp = lower humidity (inverse)
        humidity = hum_max - temp_norm * hum_range * 0.6

        # Add noise
        noise = self.rng.normal(0, noise_level * hum_range)
        humidity += noise

        return np.clip(humidity, hum_min, hum_max)

    def get_wet_bulb_temp(
        self,
        dt: datetime,
        outdoor_temp: Optional[float] = None,
        outdoor_humidity: Optional[float] = None,
    ) -> float:
        """
        Calculate wet bulb temperature.

        Uses simplified Stull formula for wet bulb approximation.

        Args:
            dt: Datetime for calculation
            outdoor_temp: Outdoor temperature (calculated if not provided)
            outdoor_humidity: Outdoor humidity (calculated if not provided)

        Returns:
            Wet bulb temperature in degC
        """
        climate = self.profile.get_seasonal_climate(dt)

        if outdoor_temp is None:
            outdoor_temp = self.get_outdoor_temp(dt)
        if outdoor_humidity is None:
            outdoor_humidity = self.get_outdoor_humidity(dt, outdoor_temp)

        # Stull formula approximation
        # Tw = T * atan(0.151977 * sqrt(RH + 8.313659))
        #    + atan(T + RH) - atan(RH - 1.676331)
        #    + 0.00391838 * RH^1.5 * atan(0.023101 * RH) - 4.686035

        T = outdoor_temp
        RH = outdoor_humidity

        wet_bulb = (
            T * np.arctan(0.151977 * np.sqrt(RH + 8.313659))
            + np.arctan(T + RH)
            - np.arctan(RH - 1.676331)
            + 0.00391838 * (RH ** 1.5) * np.arctan(0.023101 * RH)
            - 4.686035
        )

        # Clip to seasonal range
        wb_min, wb_max = climate.wet_bulb_range
        return np.clip(wet_bulb, wb_min, wb_max)

    def get_cooling_load_factor(
        self,
        dt: datetime,
        outdoor_temp: Optional[float] = None,
    ) -> float:
        """
        Calculate relative cooling load factor based on outdoor conditions.

        Returns a factor 0.0-1.0+ representing cooling demand relative to design.

        Args:
            dt: Datetime for calculation
            outdoor_temp: Outdoor temperature (calculated if not provided)

        Returns:
            Cooling load factor (1.0 = design day)
        """
        climate = self.profile.get_seasonal_climate(dt)

        if outdoor_temp is None:
            outdoor_temp = self.get_outdoor_temp(dt)

        # Design temperature (max summer temp)
        design_temp = self.profile.summer.temp_range[1]

        # Cooling load increases with outdoor temp
        # Below 22C = minimal cooling needed
        # Above design temp = 100%+ load
        if outdoor_temp < 22:
            factor = 0.2
        elif outdoor_temp < design_temp:
            factor = 0.2 + 0.8 * (outdoor_temp - 22) / (design_temp - 22)
        else:
            # Over design - load continues to increase
            factor = 1.0 + 0.2 * (outdoor_temp - design_temp) / 5

        # Adjust for solar intensity
        factor *= climate.solar_intensity

        # Add occupancy factor (higher during work hours)
        hour = dt.hour
        if 8 <= hour <= 18:
            factor *= 1.1
        elif 6 <= hour <= 20:
            factor *= 1.0
        else:
            factor *= 0.8

        return np.clip(factor, 0.1, 1.5)

    def apply_climate_to_chiller(
        self,
        base_value: float,
        point_name: str,
        dt: datetime,
        outdoor_temp: Optional[float] = None,
    ) -> float:
        """
        Apply climate effects to chiller point value.

        Args:
            base_value: Base point value
            point_name: Point name (chw_supply_temp, condenser_pressure, cop, etc.)
            dt: Datetime for calculation
            outdoor_temp: Outdoor temperature

        Returns:
            Climate-adjusted value
        """
        if outdoor_temp is None:
            outdoor_temp = self.get_outdoor_temp(dt)

        load_factor = self.get_cooling_load_factor(dt, outdoor_temp)

        if point_name in ["chw_supply_temp"]:
            # CHW temp slightly higher under high load
            return base_value * (1 + 0.05 * (load_factor - 0.5))

        elif point_name in ["condenser_pressure"]:
            # Condenser pressure increases with outdoor temp
            temp_factor = (outdoor_temp - 25) / 10 * 0.15  # 15% per 10C above 25C
            return base_value * (1 + max(0, temp_factor))

        elif point_name in ["cop"]:
            # COP decreases with outdoor temp (Carnot efficiency)
            # Higher condenser temp = lower COP
            temp_factor = (outdoor_temp - 25) / 10 * 0.08  # 8% loss per 10C
            return base_value * (1 - max(0, temp_factor))

        elif point_name in ["compressor_amps"]:
            # Current increases with load
            return base_value * load_factor

        return base_value

    def apply_climate_to_cooling_tower(
        self,
        base_value: float,
        point_name: str,
        dt: datetime,
        outdoor_temp: Optional[float] = None,
        outdoor_humidity: Optional[float] = None,
    ) -> float:
        """
        Apply climate effects to cooling tower point value.

        Args:
            base_value: Base point value
            point_name: Point name
            dt: Datetime for calculation
            outdoor_temp: Outdoor temperature
            outdoor_humidity: Outdoor humidity

        Returns:
            Climate-adjusted value
        """
        if outdoor_temp is None:
            outdoor_temp = self.get_outdoor_temp(dt)
        if outdoor_humidity is None:
            outdoor_humidity = self.get_outdoor_humidity(dt, outdoor_temp)

        wet_bulb = self.get_wet_bulb_temp(dt, outdoor_temp, outdoor_humidity)

        if point_name in ["wet_bulb_temp"]:
            return wet_bulb

        elif point_name in ["approach_temp"]:
            # Approach temp increases with humidity (harder to cool)
            humidity_factor = (outdoor_humidity - 50) / 50 * 0.3
            return base_value * (1 + max(0, humidity_factor))

        elif point_name in ["cw_supply_temp"]:
            # CW supply = wet bulb + approach
            approach = base_value if point_name != "approach_temp" else 4.0
            return wet_bulb + approach

        elif point_name in ["fan_speed"]:
            # Fan speed increases with outdoor temp
            load_factor = self.get_cooling_load_factor(dt, outdoor_temp)
            return min(100, base_value * load_factor)

        return base_value

    def generate_outdoor_conditions(
        self,
        timestamps: np.ndarray,
        noise_level: float = 0.05,
    ) -> Dict[str, np.ndarray]:
        """
        Generate complete outdoor conditions for a series of timestamps.

        Args:
            timestamps: Array of datetime timestamps
            noise_level: Random noise as fraction of range

        Returns:
            Dictionary with temp, humidity, wet_bulb, cooling_load arrays
        """
        n = len(timestamps)
        temps = np.zeros(n)
        humidity = np.zeros(n)
        wet_bulb = np.zeros(n)
        cooling_load = np.zeros(n)

        for i, ts in enumerate(timestamps):
            temps[i] = self.get_outdoor_temp(ts, noise_level)
            humidity[i] = self.get_outdoor_humidity(ts, temps[i], noise_level)
            wet_bulb[i] = self.get_wet_bulb_temp(ts, temps[i], humidity[i])
            cooling_load[i] = self.get_cooling_load_factor(ts, temps[i])

        return {
            "outdoor_temp": temps,
            "outdoor_humidity": humidity,
            "wet_bulb_temp": wet_bulb,
            "cooling_load_factor": cooling_load,
        }
