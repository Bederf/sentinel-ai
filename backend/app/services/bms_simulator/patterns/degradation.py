"""
Degradation Pattern Generator

Generates realistic equipment degradation trends for predictive maintenance simulation.
Includes:
- Gradual wear patterns (bearings, filters)
- Exponential failure approach
- Fault progression sequences
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np


@dataclass
class DegradationConfig:
    """Configuration for degradation patterns."""

    rate_per_day: float = 0.002  # Daily degradation rate (0.2%)
    max_increase: float = 0.35  # Maximum increase before failure (35%)
    start_day_offset: int = 0  # Days after start before degradation begins
    pattern_type: str = "linear"  # linear, exponential, stepped
    alarm_thresholds: list[float] = None  # Thresholds for alarm triggers

    def __post_init__(self):
        if self.alarm_thresholds is None:
            # Default thresholds at 10%, 20%, 30% increase
            self.alarm_thresholds = [0.10, 0.20, 0.30]


class DegradationPattern:
    """Generator for equipment degradation patterns."""

    # Predefined degradation profiles by equipment/point type
    PROFILES = {
        "chiller_vibration": DegradationConfig(
            rate_per_day=0.003,
            max_increase=0.40,
            pattern_type="exponential",
            alarm_thresholds=[0.10, 0.20, 0.35],  # VIB_WARN, VIB_HIGH, VIB_CRIT
        ),
        "chiller_temperature": DegradationConfig(
            rate_per_day=0.001,
            max_increase=0.20,
            pattern_type="linear",
            alarm_thresholds=[0.10, 0.15],
        ),
        "filter_pressure": DegradationConfig(
            rate_per_day=0.005,
            max_increase=0.50,
            pattern_type="linear",
            alarm_thresholds=[0.30, 0.45],  # FILTER_DP warning/critical
        ),
        "valve_stiction": DegradationConfig(
            rate_per_day=0.001,
            max_increase=0.15,
            pattern_type="stepped",
            alarm_thresholds=[0.08],
        ),
        "bearing_wear": DegradationConfig(
            rate_per_day=0.002,
            max_increase=0.35,
            pattern_type="exponential",
            alarm_thresholds=[0.15, 0.25, 0.32],
        ),
        "refrigerant_leak": DegradationConfig(
            rate_per_day=0.003,
            max_increase=0.25,  # Negative degradation (loss)
            pattern_type="linear",
            alarm_thresholds=[0.10, 0.20],
        ),
    }

    def __init__(
        self,
        seed: int = 42,
        config: DegradationConfig | None = None,
    ):
        """
        Initialize the degradation pattern generator.

        Args:
            seed: Random seed for reproducibility
            config: Degradation configuration
        """
        self.rng = np.random.default_rng(seed)
        self.config = config or DegradationConfig()

    @classmethod
    def from_profile(cls, profile_name: str, seed: int = 42) -> "DegradationPattern":
        """
        Create a degradation pattern from a predefined profile.

        Args:
            profile_name: Name of the profile (e.g., "chiller_vibration")
            seed: Random seed

        Returns:
            Configured DegradationPattern instance
        """
        config = cls.PROFILES.get(profile_name, DegradationConfig())
        return cls(seed=seed, config=config)

    def generate(
        self,
        base_value: float,
        value_range: tuple[float, float],
        timestamps: np.ndarray,
        noise_level: float = 0.02,
    ) -> tuple[np.ndarray, list[dict]]:
        """
        Generate values with degradation pattern.

        Args:
            base_value: Starting base value
            value_range: (min, max) allowed range
            timestamps: Array of datetime timestamps
            noise_level: Random noise as fraction of value

        Returns:
            Tuple of (values array, list of triggered alarms)
        """
        n = len(timestamps)
        values = np.zeros(n)
        alarms = []

        # Calculate day indices
        start_time = timestamps[0]
        days = np.array([(ts - start_time).total_seconds() / 86400 for ts in timestamps])

        # Apply start offset
        effective_days = np.maximum(0, days - self.config.start_day_offset)

        # Generate degradation curve
        if self.config.pattern_type == "exponential":
            degradation = self._exponential_degradation(effective_days)
        elif self.config.pattern_type == "stepped":
            degradation = self._stepped_degradation(effective_days)
        else:  # linear
            degradation = self._linear_degradation(effective_days)

        # Apply degradation to values
        for i, (ts, deg) in enumerate(zip(timestamps, degradation)):
            # Base value with degradation
            degraded_value = base_value * (1 + deg)

            # Add noise
            noise = self.rng.normal(0, noise_level * base_value)
            values[i] = degraded_value + noise

            # Check alarm thresholds
            for j, threshold in enumerate(self.config.alarm_thresholds):
                if deg >= threshold:
                    # Check if this is a new alarm (wasn't triggered in previous interval)
                    if i == 0 or degradation[i - 1] < threshold:
                        alarms.append(
                            {
                                "timestamp": ts,
                                "threshold_index": j,
                                "threshold_value": threshold,
                                "actual_degradation": deg,
                                "value": values[i],
                            }
                        )

        # Clip to range
        values = np.clip(values, value_range[0], value_range[1])

        return values, alarms

    def _linear_degradation(self, days: np.ndarray) -> np.ndarray:
        """
        Generate linear degradation curve.

        Simple linear increase bounded by max_increase.
        """
        degradation = self.config.rate_per_day * days
        return np.minimum(degradation, self.config.max_increase)

    def _exponential_degradation(self, days: np.ndarray) -> np.ndarray:
        """
        Generate exponential degradation curve.

        Slow initial degradation, accelerating toward failure.
        Models bearing wear and similar failure modes.
        """
        # Exponential: d = a * (e^(k*t) - 1)
        # Scaled so that at max_days we reach max_increase
        k = self.config.rate_per_day * 2  # Steeper exponential
        degradation = (np.exp(k * days) - 1) / (np.exp(k * 365) - 1) * self.config.max_increase

        return np.minimum(degradation, self.config.max_increase)

    def _stepped_degradation(self, days: np.ndarray) -> np.ndarray:
        """
        Generate stepped degradation curve.

        Sudden jumps followed by stable periods.
        Models valve stiction and similar discrete failure modes.
        """
        n = len(days)
        degradation = np.zeros(n)

        # Random step events
        n_steps = max(1, int(days[-1] / 30))  # One step per month on average
        step_days = np.sort(self.rng.choice(int(days[-1]) + 1, size=n_steps, replace=False))

        current_level = 0
        step_idx = 0

        for i, day in enumerate(days):
            # Check for step events
            while step_idx < len(step_days) and day >= step_days[step_idx]:
                step_size = self.rng.uniform(0.02, 0.08)  # 2-8% jump
                current_level = min(current_level + step_size, self.config.max_increase)
                step_idx += 1

            degradation[i] = current_level

        return degradation

    def generate_fault_sequence(
        self,
        equipment_id: str,
        equipment_type: str,
        start_date: datetime,
        days: int,
        interval_minutes: int = 15,
    ) -> tuple[np.ndarray, list[dict]]:
        """
        Generate a complete fault progression sequence for an equipment.

        This simulates the typical fault progression:
        1. Normal operation
        2. Early warning (subtle changes)
        3. Warning alarm
        4. High severity alarm
        5. Critical alarm / imminent failure

        Args:
            equipment_id: Equipment identifier
            equipment_type: Type of equipment
            start_date: Start date for simulation
            days: Number of days to simulate
            interval_minutes: Data interval in minutes

        Returns:
            Tuple of (degradation factors array, alarm events list)
        """
        # Generate timestamps
        n_intervals = days * 24 * 60 // interval_minutes
        timestamps = np.array([start_date + timedelta(minutes=i * interval_minutes) for i in range(n_intervals)])

        # Select appropriate profile based on equipment type
        if equipment_type == "chiller":
            profile = self.PROFILES["chiller_vibration"]
        elif equipment_type == "ahu":
            profile = self.PROFILES["filter_pressure"]
        elif equipment_type in ["fcu", "vav"]:
            profile = self.PROFILES["valve_stiction"]
        else:
            profile = DegradationConfig()

        # Create pattern generator with profile
        pattern = DegradationPattern(seed=self.rng.integers(0, 10000), config=profile)

        # Generate degradation curve (base value 1.0, range 1.0 to 1.0 + max_increase)
        degradation, alarms = pattern.generate(
            base_value=1.0,
            value_range=(0.5, 2.0),  # Wide range for factors
            timestamps=timestamps,
            noise_level=0.01,
        )

        # Convert to factor (subtract 1.0 to get pure degradation)
        degradation_factor = degradation - 1.0

        # Format alarms with equipment context
        formatted_alarms = []
        for alarm in alarms:
            severity = self._get_severity_from_threshold_index(alarm["threshold_index"])
            formatted_alarms.append(
                {
                    "timestamp": alarm["timestamp"].isoformat(),
                    "equipment_id": equipment_id,
                    "equipment_type": equipment_type,
                    "severity": severity,
                    "degradation_pct": alarm["actual_degradation"] * 100,
                }
            )

        return degradation_factor, formatted_alarms

    def _get_severity_from_threshold_index(self, index: int) -> str:
        """Map threshold index to alarm severity."""
        if index == 0:
            return "warning"
        elif index == 1:
            return "warning"  # High warning
        else:
            return "critical"

    def apply_to_point(
        self,
        base_values: np.ndarray,
        degradation_factors: np.ndarray,
        point_type: str,
    ) -> np.ndarray:
        """
        Apply degradation factors to point values.

        Args:
            base_values: Base point values (with diurnal pattern)
            degradation_factors: Degradation factors (0 = no degradation)
            point_type: Type of point for direction of degradation

        Returns:
            Degraded point values
        """
        # Determine degradation direction
        # Some points increase with degradation (vibration, pressure, current)
        # Some points decrease (efficiency, flow in case of restriction)
        increasing_points = [
            "compressor_amps",
            "filter_pressure",
            "vibration",
            "chw_supply_temp",
            "discharge_temp",
            "co2_level",
        ]

        if any(pt in point_type.lower() for pt in increasing_points):
            # Value increases with degradation
            return base_values * (1 + degradation_factors)
        else:
            # Value decreases with degradation (efficiency, flow)
            return base_values * (1 - degradation_factors * 0.5)
