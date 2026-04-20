"""
LSTM Data Preparation - Prepare time-series data for LSTM training.

Creates sliding window sequences from sensor data for forecasting.
"""

import logging
from typing import Any

import numpy as np

try:
    import pandas as pd
    from sklearn.preprocessing import StandardScaler
except ImportError:
    raise ImportError("Install ML dependencies: pip install -r ml/requirements.txt")

logger = logging.getLogger(__name__)


class LSTMDataPrep:
    """Prepare time-series data for LSTM training."""

    def __init__(
        self,
        window_size: int = 168,  # 7 days of hourly data
        forecast_horizons: list[int] = None,
    ):
        """
        Initialize data preparation.

        Args:
            window_size: Number of timesteps in input window (default 168 = 7 days hourly)
            forecast_horizons: Hours ahead to predict (default [24, 48, 72])
        """
        self.window_size = window_size
        self.forecast_horizons = forecast_horizons or [24, 48, 72]
        self.scaler = StandardScaler()
        self._scaler_fitted = False

    def create_sequences(self, data: np.ndarray, target_col: int = 0) -> tuple[np.ndarray, np.ndarray]:
        """
        Create sliding window sequences for training.

        Args:
            data: Array of shape (timesteps, features)
            target_col: Column index to predict (default 0)

        Returns:
            X: Input sequences of shape (samples, window_size, features)
            y: Target values of shape (samples, len(forecast_horizons))
        """
        X, y = [], []
        max_horizon = max(self.forecast_horizons)

        for i in range(len(data) - self.window_size - max_horizon):
            # Input window
            window = data[i : i + self.window_size]

            # Target values at each forecast horizon
            targets = [data[i + self.window_size + h - 1, target_col] for h in self.forecast_horizons]

            X.append(window)
            y.append(targets)

        return np.array(X), np.array(y)

    def prepare_from_dataframe(
        self, df: pd.DataFrame, feature_cols: list[str], target_col: str, timestamp_col: str = "timestamp"
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Prepare training data from a pandas DataFrame.

        Args:
            df: DataFrame with sensor readings
            feature_cols: Column names to use as features
            target_col: Column name to predict
            timestamp_col: Name of timestamp column

        Returns:
            X, y arrays ready for training
        """
        # Sort by timestamp
        df = df.sort_values(timestamp_col).copy()

        # Resample to hourly if needed
        df[timestamp_col] = pd.to_datetime(df[timestamp_col])
        df = df.set_index(timestamp_col)
        df = df[feature_cols].resample("1H").mean()

        # Forward fill small gaps (up to 3 hours)
        df = df.fillna(method="ffill", limit=3)

        # Drop remaining NaN rows
        df = df.dropna()

        if len(df) < self.window_size + max(self.forecast_horizons) + 100:
            raise ValueError(
                f"Insufficient data: {len(df)} rows, need at least "
                f"{self.window_size + max(self.forecast_horizons) + 100}"
            )

        # Get target column index
        target_idx = feature_cols.index(target_col)

        # Create sequences
        X, y = self.create_sequences(df.values, target_col=target_idx)

        return X, y

    def fit_scaler(self, X: np.ndarray) -> np.ndarray:
        """
        Fit scaler and transform data.

        Args:
            X: Input array of shape (samples, window_size, features)

        Returns:
            Scaled X array
        """
        # Reshape for scaler: (samples * window_size, features)
        original_shape = X.shape
        X_flat = X.reshape(-1, X.shape[-1])

        # Fit and transform
        X_scaled = self.scaler.fit_transform(X_flat)
        self._scaler_fitted = True

        # Reshape back
        return X_scaled.reshape(original_shape)

    def transform(self, X: np.ndarray) -> np.ndarray:
        """Transform data using fitted scaler."""
        if not self._scaler_fitted:
            raise ValueError("Scaler not fitted. Call fit_scaler first.")

        original_shape = X.shape
        X_flat = X.reshape(-1, X.shape[-1])
        X_scaled = self.scaler.transform(X_flat)
        return X_scaled.reshape(original_shape)

    def inverse_transform(self, X: np.ndarray) -> np.ndarray:
        """Inverse transform scaled data."""
        if not self._scaler_fitted:
            raise ValueError("Scaler not fitted.")

        original_shape = X.shape
        X_flat = X.reshape(-1, X.shape[-1])
        X_unscaled = self.scaler.inverse_transform(X_flat)
        return X_unscaled.reshape(original_shape)

    def save_scaler(self, path: str):
        """Save scaler for inference."""
        import joblib

        joblib.dump(self.scaler, path)
        logger.info(f"Saved scaler to {path}")

    def load_scaler(self, path: str):
        """Load scaler from disk."""
        import joblib

        self.scaler = joblib.load(path)
        self._scaler_fitted = True
        logger.info(f"Loaded scaler from {path}")

    def generate_demo_data(
        self, n_samples: int = 5000, n_features: int = 3, noise_level: float = 0.1
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Generate synthetic demo data for testing/development.

        Creates realistic-looking sensor data with:
        - Daily patterns (sinusoidal)
        - Weekly patterns
        - Trend component
        - Random noise

        Returns:
            X, y arrays for training
        """
        np.random.seed(42)

        # Time index
        hours = np.arange(n_samples + self.window_size + max(self.forecast_horizons))

        # Generate multi-feature data
        data = np.zeros((len(hours), n_features))

        for i in range(n_features):
            # Daily cycle (24-hour period)
            daily = 5 * np.sin(2 * np.pi * hours / 24 + i * np.pi / 4)

            # Weekly cycle
            weekly = 2 * np.sin(2 * np.pi * hours / (24 * 7))

            # Slow trend
            trend = 0.001 * hours

            # Noise
            noise = noise_level * 10 * np.random.randn(len(hours))

            # Base value (different per feature)
            base = 20 + i * 5

            data[:, i] = base + daily + weekly + trend + noise

        # Create sequences
        X, y = self.create_sequences(data, target_col=0)

        return X, y


class EquipmentDataLoader:
    """Load sensor data for specific equipment types from database."""

    # Sensor configurations per equipment type
    SENSOR_CONFIGS: dict[str, dict[str, Any]] = {
        "chiller": {
            "features": [
                "chw_supply_temp",
                "chw_return_temp",
                "suction_pressure",
                "discharge_pressure",
                "compressor_current",
            ],
            "target": "chw_supply_temp",
            "description": "Chiller supply temperature prediction",
        },
        "ahu": {
            "features": ["supply_temp", "return_temp", "filter_dp", "fan_current", "mixed_air_temp"],
            "target": "supply_temp",
            "description": "AHU supply temperature prediction",
        },
        "generator": {
            "features": ["battery_voltage", "oil_pressure", "coolant_temp", "load_pct"],
            "target": "coolant_temp",
            "description": "Generator coolant temperature prediction",
        },
        "fcu": {
            "features": ["supply_temp", "fan_current", "valve_position"],
            "target": "supply_temp",
            "description": "FCU supply temperature prediction",
        },
        "ups": {
            "features": ["battery_voltage", "load_pct", "temperature"],
            "target": "temperature",
            "description": "UPS temperature prediction",
        },
        "vav": {
            "features": ["airflow", "damper_position", "zone_temp", "supply_temp"],
            "target": "zone_temp",
            "description": "VAV zone temperature prediction",
        },
        "pump": {
            "features": ["flow_rate", "discharge_pressure", "motor_current", "vibration", "temperature"],
            "target": "discharge_pressure",
            "description": "Pump discharge pressure prediction",
        },
        "cooling_tower": {
            "features": ["basin_temp", "fan_speed", "water_level", "fan_current"],
            "target": "basin_temp",
            "description": "Cooling tower basin temperature prediction",
        },
        "transformer": {
            "features": ["winding_temp", "oil_temp", "load_pct", "tap_position"],
            "target": "winding_temp",
            "description": "Transformer winding temperature prediction",
        },
        "crac": {
            "features": ["supply_temp", "return_temp", "humidity_pct", "compressor_current"],
            "target": "supply_temp",
            "description": "CRAC unit supply temperature prediction",
        },
        "ats": {
            "features": ["mains_voltage", "generator_voltage", "position", "transfer_status"],
            "target": "position",
            "description": "ATS transfer position prediction",
        },
        "pfc": {
            "features": ["power_factor", "reactive_power_kvar", "current_a", "voltage_v"],
            "target": "power_factor",
            "description": "PFC bank power factor prediction",
        },
        "bess": {
            "features": ["soc_pct", "charge_power_kw", "discharge_power_kw", "cell_temp"],
            "target": "soc_pct",
            "description": "BESS state-of-charge prediction",
        },
        "inverter": {
            "features": ["dc_input_power_kw", "ac_output_power_kw", "efficiency_pct", "inverter_temp"],
            "target": "ac_output_power_kw",
            "description": "Inverter AC output power prediction",
        },
        "split": {
            "features": ["room_temp", "supply_temp", "fan_speed", "valve_position"],
            "target": "room_temp",
            "description": "Split unit room temperature prediction",
        },
    }

    @classmethod
    def get_config(cls, equipment_type: str) -> dict[str, Any]:
        """Get sensor configuration for equipment type."""
        if equipment_type not in cls.SENSOR_CONFIGS:
            raise ValueError(f"Unknown equipment type: {equipment_type}. Available: {list(cls.SENSOR_CONFIGS.keys())}")
        return cls.SENSOR_CONFIGS[equipment_type]

    @classmethod
    def list_equipment_types(cls) -> list[str]:
        """List available equipment types."""
        return list(cls.SENSOR_CONFIGS.keys())
