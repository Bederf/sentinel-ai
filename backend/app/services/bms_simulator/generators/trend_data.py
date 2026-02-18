"""
Trend Data Generator

Generates realistic time-series trend data for BMS points.
Applies diurnal patterns, weekend variation, and degradation curves.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from ..models import (
    SimulationConfig,
    POINT_VALUE_RANGES,
)
from ..patterns.diurnal import DiurnalPattern, DiurnalConfig
from ..patterns.degradation import DegradationPattern
from .point_list import PointListExporter


class TrendDataGenerator:
    """Generates trend data for BMS points."""

    # Base paths
    DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
    OUTPUT_DIR = DATA_DIR / "bms_simulator" / "trends"

    # Point type to pattern type mapping
    PATTERN_TYPE_MAP = {
        # Temperature points follow temperature patterns
        "supply_air_temp": "temperature",
        "return_air_temp": "temperature",
        "room_temp": "temperature",
        "zone_temp": "temperature",
        "chw_supply_temp": "temperature",
        "chw_return_temp": "temperature",
        "discharge_air_temp": "temperature",
        # Load-following points
        "airflow_actual": "load",
        "airflow_cfm": "load",
        "compressor_amps": "load",
        "fan_speed": "load",
        "valve_position": "load",
        "damper_position": "load",
        # Occupancy-driven
        "occupancy": "occupancy",
        "co2_level": "load",
        "light_level": "load",
        # Setpoints (relatively stable)
        "room_temp_setpoint": "setpoint",
        "cooling_setpoint": "setpoint",
        "chw_supply_temp_setpoint": "setpoint",
        "airflow_setpoint": "setpoint",
    }

    # Points that should degrade on specified equipment
    DEGRADING_POINTS = {
        "chiller": ["compressor_amps", "chw_supply_temp"],
        "ahu": ["filter_pressure"],
        "fcu": ["valve_position"],
        "vav": ["damper_position"],
    }

    def __init__(self, config: Optional[SimulationConfig] = None):
        """
        Initialize the trend data generator.

        Args:
            config: Simulation configuration
        """
        self.config = config or SimulationConfig()
        self.point_exporter = PointListExporter(config)
        self.diurnal = DiurnalPattern(seed=self.config.seed)
        self.degradation = DegradationPattern(seed=self.config.seed)

    def generate_timestamps(self) -> np.ndarray:
        """
        Generate array of timestamps for trend data.

        Returns:
            Array of datetime objects
        """
        start = datetime.combine(self.config.start_date, datetime.min.time())
        n_intervals = self.config.days * 24 * 60 // self.config.interval_minutes

        timestamps = np.array([
            start + timedelta(minutes=i * self.config.interval_minutes)
            for i in range(n_intervals)
        ])

        return timestamps

    def generate_device_trends(
        self,
        device: Dict[str, Any],
        timestamps: np.ndarray,
    ) -> pd.DataFrame:
        """
        Generate trend data for all points of a device.

        Args:
            device: Device definition dictionary
            timestamps: Array of timestamps

        Returns:
            DataFrame with timestamp and point value columns
        """
        device_id = device.get("id", "")
        device_type = device.get("hvac_type", device.get("device_type", "unknown"))
        points = device.get("points", {})

        # Check if this device should have degradation
        should_degrade = (
            self.config.include_degradation and
            device_id in self.config.degradation_equipment
        )

        # Generate degradation factors if needed
        degradation_factors = None
        if should_degrade:
            degradation_factors, _ = self.degradation.generate_fault_sequence(
                equipment_id=device_id,
                equipment_type=device_type,
                start_date=timestamps[0],
                days=self.config.days,
                interval_minutes=self.config.interval_minutes,
            )

        # Build DataFrame
        data = {"timestamp": timestamps}

        for point_name, point_def in points.items():
            values = self._generate_point_values(
                point_name=point_name,
                point_def=point_def,
                timestamps=timestamps,
                device_type=device_type,
                degradation_factors=degradation_factors,
            )
            data[point_name] = values

        df = pd.DataFrame(data)
        df["device_id"] = device_id
        df["site_id"] = device.get("site_id", self.config.site_id)

        return df

    def _generate_point_values(
        self,
        point_name: str,
        point_def: Dict[str, Any],
        timestamps: np.ndarray,
        device_type: str,
        degradation_factors: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """
        Generate values for a single point.

        Args:
            point_name: Name of the point
            point_def: Point definition
            timestamps: Array of timestamps
            device_type: Device type for context
            degradation_factors: Optional degradation factors to apply

        Returns:
            Array of point values
        """
        n = len(timestamps)

        # Get value range
        default_value = point_def.get("default_value", 0)
        min_val = point_def.get("min_value")
        max_val = point_def.get("max_value")

        # Handle boolean/binary points
        if isinstance(default_value, bool) or point_def.get("point_type") in ["binary_input", "binary_value"]:
            return self._generate_binary_values(point_name, timestamps)

        # Handle multistate points
        if point_def.get("point_type") == "multistate_value":
            return self._generate_multistate_values(point_def, timestamps)

        # Get value range from lookup or point definition
        if point_name in POINT_VALUE_RANGES:
            value_range = POINT_VALUE_RANGES[point_name]
        elif min_val is not None and max_val is not None:
            value_range = (min_val, max_val)
        else:
            # Default to +/- 20% of default value
            if default_value != 0:
                value_range = (default_value * 0.8, default_value * 1.2)
            else:
                value_range = (0, 100)

        # Get pattern type
        pattern_type = self.PATTERN_TYPE_MAP.get(point_name, "temperature")

        # Generate base values with diurnal pattern
        base_value = default_value if default_value else (value_range[0] + value_range[1]) / 2
        values = self.diurnal.generate(
            base_value=base_value,
            value_range=value_range,
            timestamps=timestamps,
            pattern_type=pattern_type,
        )

        # Apply degradation if this point should degrade
        if degradation_factors is not None:
            degrading_points = self.DEGRADING_POINTS.get(device_type, [])
            if point_name in degrading_points:
                values = self.degradation.apply_to_point(
                    base_values=values,
                    degradation_factors=degradation_factors,
                    point_type=point_name,
                )

        return values

    def _generate_binary_values(
        self,
        point_name: str,
        timestamps: np.ndarray,
    ) -> np.ndarray:
        """Generate binary (0/1) values for occupancy, status, etc."""
        if "occupancy" in point_name.lower():
            # Occupancy follows diurnal pattern
            return self.diurnal.generate(
                base_value=0.5,
                value_range=(0, 1),
                timestamps=timestamps,
                pattern_type="occupancy",
            ).astype(int)
        elif "status" in point_name.lower() or "enable" in point_name.lower():
            # Status points mostly on during work hours
            config = DiurnalConfig(work_start=6, work_end=20)
            pattern = DiurnalPattern(seed=self.config.seed, config=config)
            values = pattern.generate(
                base_value=0.8,
                value_range=(0, 1),
                timestamps=timestamps,
                pattern_type="occupancy",
            )
            return (values > 0.5).astype(int)
        else:
            # Default: mostly true/on
            rng = np.random.default_rng(self.config.seed)
            return (rng.random(len(timestamps)) > 0.1).astype(int)

    def _generate_multistate_values(
        self,
        point_def: Dict[str, Any],
        timestamps: np.ndarray,
    ) -> np.ndarray:
        """Generate multistate values (e.g., fan speed low/med/high)."""
        n = len(timestamps)
        rng = np.random.default_rng(self.config.seed)

        # Get states from metadata
        states = point_def.get("metadata", {}).get("states", {})
        n_states = len(states) if states else 4
        default = point_def.get("default_value", 1)

        # Generate values clustered around default
        values = np.zeros(n, dtype=int)
        for i, ts in enumerate(timestamps):
            hour = ts.hour
            day_of_week = ts.weekday()

            # Higher states during peak hours
            if 9 <= hour <= 17 and day_of_week < 5:
                # Work hours - bias toward higher values
                values[i] = min(n_states - 1, default + rng.integers(-1, 2))
            elif day_of_week >= 5:
                # Weekend - lower values
                values[i] = max(0, default - rng.integers(0, 2))
            else:
                # Off hours
                values[i] = max(0, rng.integers(0, default + 1))

        return np.clip(values, 0, n_states - 1)

    def generate_all_trends(
        self,
        site_id: Optional[str] = None,
        include_diffusers: bool = True,
        output_format: str = "csv",
    ) -> List[str]:
        """
        Generate trend data for all devices in a site.

        Args:
            site_id: Site ID to generate trends for
            include_diffusers: Include generated Rickard diffusers
            output_format: Output format ("csv" or "parquet")

        Returns:
            List of output file paths
        """
        site_id = site_id or self.config.site_id

        # Load devices
        devices = self.point_exporter.load_devices(site_id)
        if include_diffusers:
            diffusers = self.point_exporter.generate_diffusers(site_id)
            devices = devices + diffusers

        # Generate timestamps
        timestamps = self.generate_timestamps()

        # Ensure output directory exists
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        output_files = []
        all_data = []

        for device in devices:
            device_id = device.get("id", "")
            df = self.generate_device_trends(device, timestamps)
            all_data.append(df)

        # Combine all data
        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)

            # Generate output filename
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"trends_{site_id}_{self.config.days}d_{timestamp_str}"

            if output_format == "csv":
                output_path = self.OUTPUT_DIR / f"{filename}.csv"
                combined_df.to_csv(output_path, index=False)
            else:  # parquet
                output_path = self.OUTPUT_DIR / f"{filename}.parquet"
                combined_df.to_parquet(output_path, index=False)

            output_files.append(str(output_path))

        return output_files

    def generate_equipment_trends(
        self,
        equipment_id: str,
        days: Optional[int] = None,
        output_path: Optional[Path] = None,
    ) -> str:
        """
        Generate trend data for a specific equipment.

        Args:
            equipment_id: Equipment ID to generate trends for
            days: Number of days (overrides config)
            output_path: Custom output path

        Returns:
            Output file path
        """
        # Find the device
        all_devices = self.point_exporter.load_devices()
        device = next((d for d in all_devices if d.get("id") == equipment_id), None)

        if device is None:
            raise ValueError(f"Equipment {equipment_id} not found")

        # Override days if specified
        if days:
            original_days = self.config.days
            self.config.days = days

        # Generate timestamps and trends
        timestamps = self.generate_timestamps()
        df = self.generate_device_trends(device, timestamps)

        # Restore original config
        if days:
            self.config.days = original_days

        # Determine output path
        if output_path is None:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"trends_{equipment_id}_{timestamp_str}.csv"
            output_path = self.OUTPUT_DIR / filename

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write output
        df.to_csv(output_path, index=False)

        return str(output_path)

    def export_chiller_telemetry_format(
        self,
        device_id: str,
        output_path: Optional[Path] = None,
    ) -> str:
        """
        Export chiller trend data in the existing chiller_telemetry.csv format.

        This format is compatible with the existing ML training pipeline.

        Args:
            device_id: Chiller device ID
            output_path: Custom output path

        Returns:
            Output file path
        """
        # Find chiller device
        all_devices = self.point_exporter.load_devices()
        device = next((d for d in all_devices if d.get("id") == device_id), None)

        if device is None or device.get("hvac_type") != "chiller":
            raise ValueError(f"Chiller {device_id} not found")

        # Generate base trends
        timestamps = self.generate_timestamps()
        df = self.generate_device_trends(device, timestamps)

        # Map to chiller_telemetry format
        site_id = device.get("site_id", "").upper().replace("-", "-")
        equipment = device.get("equipment", {})
        location = device.get("device_location", {})

        telemetry_df = pd.DataFrame({
            "timestamp": df["timestamp"],
            "site_id": site_id,
            "site_name": location.get("building", "Unknown"),
            "asset_id": device_id.replace("-", "-").upper(),
            "asset_tag": f"{site_id[:2]}-HVAC-CH-001",
            "chiller_type": "centrifugal",
            "chiller_make": equipment.get("manufacturer", "Unknown"),
            "chiller_model": equipment.get("model", "Unknown"),
            "capacity_tons": int(device.get("capacity", 200)),
            "reading_source": "bacnet-scheduled",
            "chw_supply_temp_c": df.get("chw_supply_temp", 7.0),
            "chw_return_temp_c": df.get("chw_return_temp", 12.0),
            "chw_setpoint_c": df.get("chw_supply_temp_setpoint", 7.0),
            "chw_flow_lps": 50.0 + np.random.default_rng(self.config.seed).normal(0, 5, len(df)),
            "cond_water_in_c": 30.0 + np.random.default_rng(self.config.seed).normal(0, 2, len(df)),
            "cond_water_out_c": 35.0 + np.random.default_rng(self.config.seed).normal(0, 2, len(df)),
            "compressor_status": "RUNNING",
            "compressor_load_pct": df.get("compressor_amps", 145) / 2,  # Approximate
            "compressor_current_a": df.get("compressor_amps", 145),
            "power_kw": df.get("compressor_amps", 145) * 0.8,  # Approximate
            "efficiency_kw_ton": 0.6,
            "alarm_code": "",
            "alarm_description": "",
        })

        # Determine output path
        if output_path is None:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"chiller_telemetry_{device_id}_{timestamp_str}.csv"
            output_path = self.OUTPUT_DIR / filename

        output_path.parent.mkdir(parents=True, exist_ok=True)
        telemetry_df.to_csv(output_path, index=False)

        return str(output_path)
