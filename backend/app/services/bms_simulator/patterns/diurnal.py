"""
Diurnal Pattern Generator

Generates realistic time-of-day and day-of-week patterns for BMS data.
Includes:
- Temperature peaks in afternoon
- Load following occupancy patterns
- Weekend vs weekday variation
"""

import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class DiurnalConfig:
    """Configuration for diurnal patterns."""

    peak_hour: int = 14  # Hour of peak value (0-23)
    amplitude: float = 0.15  # Variation as fraction of base value
    work_start: int = 8  # Occupancy start hour
    work_end: int = 18  # Occupancy end hour
    weekend_factor: float = 0.3  # Activity level on weekends (0-1)
    noise_level: float = 0.02  # Random noise as fraction


class DiurnalPattern:
    """Generator for diurnal (daily cycle) patterns."""

    def __init__(
        self,
        seed: int = 42,
        config: Optional[DiurnalConfig] = None,
    ):
        """
        Initialize the diurnal pattern generator.

        Args:
            seed: Random seed for reproducibility
            config: Pattern configuration
        """
        self.rng = np.random.default_rng(seed)
        self.config = config or DiurnalConfig()

    def generate(
        self,
        base_value: float,
        value_range: Tuple[float, float],
        timestamps: np.ndarray,
        pattern_type: str = "temperature",
    ) -> np.ndarray:
        """
        Generate values with diurnal pattern.

        Args:
            base_value: Base/mean value
            value_range: (min, max) allowed range
            timestamps: Array of datetime timestamps
            pattern_type: Type of pattern ("temperature", "load", "occupancy")

        Returns:
            Array of values with diurnal variation
        """
        n = len(timestamps)

        if pattern_type == "temperature":
            values = self._temperature_pattern(base_value, timestamps)
        elif pattern_type == "load":
            values = self._load_pattern(base_value, timestamps)
        elif pattern_type == "occupancy":
            values = self._occupancy_pattern(timestamps)
        elif pattern_type == "setpoint":
            # Setpoints are relatively stable with minor adjustments
            values = self._setpoint_pattern(base_value, timestamps)
        else:
            # Default: simple sinusoidal variation
            values = self._sinusoidal_pattern(base_value, timestamps)

        # Add noise (use absolute value for scale to handle negative base values)
        noise_scale = abs(self.config.noise_level * base_value)
        if noise_scale > 0:
            noise = self.rng.normal(0, noise_scale, n)
            values = values + noise

        # Clip to range
        values = np.clip(values, value_range[0], value_range[1])

        return values

    def _temperature_pattern(
        self,
        base_value: float,
        timestamps: np.ndarray,
    ) -> np.ndarray:
        """
        Generate temperature pattern with afternoon peak.

        Temperature typically peaks around 14:00-15:00 due to:
        - Solar heat gain
        - Accumulated internal loads
        - Lag from outdoor temperature peak
        """
        n = len(timestamps)
        values = np.zeros(n)

        for i, ts in enumerate(timestamps):
            hour = ts.hour + ts.minute / 60.0
            day_of_week = ts.weekday()

            # Sinusoidal daily pattern peaking at configured hour
            phase = 2 * np.pi * (hour - self.config.peak_hour) / 24
            daily_factor = np.cos(phase)

            # Weekend reduction
            if day_of_week >= 5:  # Saturday, Sunday
                daily_factor *= self.config.weekend_factor

            # Calculate value
            variation = self.config.amplitude * base_value * daily_factor
            values[i] = base_value + variation

        return values

    def _load_pattern(
        self,
        base_value: float,
        timestamps: np.ndarray,
    ) -> np.ndarray:
        """
        Generate load pattern following occupancy.

        Load patterns typically:
        - Ramp up starting at work_start
        - Peak around late morning (10-11 AM)
        - Slight dip at lunch
        - Gradual decline after lunch
        - Sharp drop at work_end
        """
        n = len(timestamps)
        values = np.zeros(n)

        for i, ts in enumerate(timestamps):
            hour = ts.hour + ts.minute / 60.0
            day_of_week = ts.weekday()

            # Base occupancy pattern
            if day_of_week >= 5:  # Weekend
                occupancy = self.config.weekend_factor * self._occupancy_curve(hour)
            else:
                occupancy = self._occupancy_curve(hour)

            # Load follows occupancy with some lag and internal gains
            variation = self.config.amplitude * base_value * occupancy
            values[i] = base_value * (0.3 + 0.7 * occupancy) + variation

        return values

    def _occupancy_curve(self, hour: float) -> float:
        """
        Get occupancy factor for a given hour (0-1).

        Returns continuous occupancy factor based on typical office schedule.
        """
        # Before work
        if hour < self.config.work_start - 1:
            return 0.05  # Security/cleaning

        # Ramp up
        elif hour < self.config.work_start:
            return 0.05 + 0.2 * (hour - (self.config.work_start - 1))

        # Morning ramp to peak
        elif hour < 10:
            return 0.25 + 0.75 * (hour - self.config.work_start) / (10 - self.config.work_start)

        # Peak morning
        elif hour < 12:
            return 0.9 + 0.1 * np.sin(np.pi * (hour - 10) / 2)

        # Lunch dip
        elif hour < 13:
            return 0.7 + 0.1 * np.cos(np.pi * (hour - 12))

        # Afternoon
        elif hour < 16:
            return 0.85

        # Wind down
        elif hour < self.config.work_end:
            return 0.85 - 0.6 * (hour - 16) / (self.config.work_end - 16)

        # After hours
        elif hour < self.config.work_end + 2:
            return 0.25 - 0.2 * (hour - self.config.work_end) / 2

        # Night
        else:
            return 0.05

    def _occupancy_pattern(
        self,
        timestamps: np.ndarray,
    ) -> np.ndarray:
        """
        Generate binary occupancy pattern with realistic transitions.

        Returns 0/1 values for occupancy sensors.
        """
        n = len(timestamps)
        values = np.zeros(n)

        for i, ts in enumerate(timestamps):
            hour = ts.hour + ts.minute / 60.0
            day_of_week = ts.weekday()

            # Get occupancy probability
            if day_of_week >= 5:  # Weekend
                prob = self.config.weekend_factor * self._occupancy_curve(hour)
            else:
                prob = self._occupancy_curve(hour)

            # Convert to binary with some randomness
            values[i] = 1 if self.rng.random() < prob else 0

        return values

    def _setpoint_pattern(
        self,
        base_value: float,
        timestamps: np.ndarray,
    ) -> np.ndarray:
        """
        Generate setpoint pattern with scheduled adjustments.

        Setpoints typically:
        - Lower during unoccupied hours (energy saving)
        - Stable during occupied hours
        - May have small adjustments for pre-conditioning
        """
        n = len(timestamps)
        values = np.zeros(n)

        for i, ts in enumerate(timestamps):
            hour = ts.hour
            day_of_week = ts.weekday()

            # Temperature setpoint adjustments
            if day_of_week >= 5:  # Weekend
                # Wider deadband on weekends
                adjustment = 2.0
            elif hour < self.config.work_start - 1:
                # Night setback
                adjustment = 2.0
            elif hour < self.config.work_start:
                # Pre-conditioning
                adjustment = 0.5
            elif hour >= self.config.work_end:
                # Evening setback
                adjustment = 1.5
            else:
                # Normal operation
                adjustment = 0.0

            # For cooling setpoint, adjustment is positive (higher = less cooling)
            # For heating setpoint, adjustment would be negative
            values[i] = base_value + adjustment * 0.3  # Subtle adjustment

        return values

    def _sinusoidal_pattern(
        self,
        base_value: float,
        timestamps: np.ndarray,
    ) -> np.ndarray:
        """
        Generate simple sinusoidal pattern.

        Used as fallback for points without specific patterns.
        """
        n = len(timestamps)
        values = np.zeros(n)

        for i, ts in enumerate(timestamps):
            hour = ts.hour + ts.minute / 60.0
            phase = 2 * np.pi * (hour - self.config.peak_hour) / 24
            variation = self.config.amplitude * base_value * np.cos(phase)
            values[i] = base_value + variation

        return values

    def apply_seasonality(
        self,
        values: np.ndarray,
        timestamps: np.ndarray,
        seasonality_amplitude: float = 0.1,
    ) -> np.ndarray:
        """
        Apply seasonal variation to values.

        Args:
            values: Base values with diurnal pattern
            timestamps: Timestamps for the values
            seasonality_amplitude: Seasonal variation amplitude

        Returns:
            Values with seasonal adjustment
        """
        # Simple seasonal adjustment based on day of year
        # Peak in summer (day ~180), minimum in winter (day ~0/365)
        seasonal_factors = np.array([
            np.sin(2 * np.pi * ts.timetuple().tm_yday / 365)
            for ts in timestamps
        ])

        # Apply seasonal variation
        adjustment = seasonality_amplitude * values * seasonal_factors
        return values + adjustment
