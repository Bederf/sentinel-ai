"""
Autoencoder Data Preparation - Prepare NORMAL operation data for training.

Key principle: Autoencoders learn "normal" behavior, so we EXCLUDE
failure periods from training data. High reconstruction error = anomaly.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any
import numpy as np

try:
    from sklearn.preprocessing import StandardScaler
    import pandas as pd
except ImportError:
    raise ImportError("Install ML dependencies: pip install -r ml/requirements.txt")

logger = logging.getLogger(__name__)


class AutoencoderDataPrep:
    """Prepare normal operation data for autoencoder training."""

    def __init__(
        self,
        window_size: int = 24,  # 24 hours
        overlap: float = 0.5  # 50% window overlap
    ):
        """
        Initialize data preparation.

        Args:
            window_size: Hours in each window (default 24)
            overlap: Fraction of overlap between windows (0-1)
        """
        self.window_size = window_size
        self.overlap = overlap
        self.step_size = int(window_size * (1 - overlap))
        self.scaler = StandardScaler()
        self._scaler_fitted = False

    def create_windows(
        self,
        data: np.ndarray,
        exclude_periods: List[Tuple[int, int]] = None
    ) -> np.ndarray:
        """
        Create sliding windows from time-series data.

        Args:
            data: Array of shape (timesteps, features)
            exclude_periods: List of (start_idx, end_idx) tuples to exclude

        Returns:
            Windows of shape (n_windows, window_size, features)
        """
        windows = []
        exclude_periods = exclude_periods or []

        i = 0
        while i + self.window_size <= len(data):
            # Check if this window overlaps with any exclusion period
            window_start = i
            window_end = i + self.window_size
            excluded = False

            for ex_start, ex_end in exclude_periods:
                if not (window_end <= ex_start or window_start >= ex_end):
                    excluded = True
                    break

            if not excluded:
                window = data[i:i + self.window_size]
                windows.append(window)

            i += self.step_size

        return np.array(windows)

    def prepare_normal_data(
        self,
        df: pd.DataFrame,
        feature_cols: List[str],
        timestamp_col: str = "timestamp",
        failure_dates: List[datetime] = None,
        exclude_days_before: int = 7,
        exclude_days_after: int = 3
    ) -> np.ndarray:
        """
        Prepare training data from normal operation periods only.

        Args:
            df: DataFrame with sensor readings
            feature_cols: Column names to use as features
            timestamp_col: Name of timestamp column
            failure_dates: List of known failure dates to exclude
            exclude_days_before: Days before failure to exclude (degradation period)
            exclude_days_after: Days after failure to exclude (recovery period)

        Returns:
            Windows from normal operation periods
        """
        # Sort and set timestamp index
        df = df.sort_values(timestamp_col).copy()
        df[timestamp_col] = pd.to_datetime(df[timestamp_col])
        df = df.set_index(timestamp_col)

        # Resample to hourly
        df = df[feature_cols].resample("1H").mean()
        df = df.fillna(method="ffill", limit=3)
        df = df.dropna()

        # Convert failure dates to index ranges
        exclude_periods = []
        if failure_dates:
            for failure_date in failure_dates:
                start = failure_date - timedelta(days=exclude_days_before)
                end = failure_date + timedelta(days=exclude_days_after)

                # Convert to row indices
                try:
                    start_idx = df.index.get_loc(start, method="nearest")
                    end_idx = df.index.get_loc(end, method="nearest")
                    exclude_periods.append((start_idx, end_idx))
                    logger.info(f"Excluding failure period: {start} to {end}")
                except KeyError:
                    pass

        # Create windows
        windows = self.create_windows(df.values, exclude_periods)

        logger.info(
            f"Created {len(windows)} windows from {len(df)} hours of data "
            f"(excluded {len(exclude_periods)} failure periods)"
        )

        return windows

    def fit_scaler(self, X: np.ndarray) -> np.ndarray:
        """Fit scaler and transform data."""
        original_shape = X.shape
        X_flat = X.reshape(-1, X.shape[-1])
        X_scaled = self.scaler.fit_transform(X_flat)
        self._scaler_fitted = True
        return X_scaled.reshape(original_shape)

    def transform(self, X: np.ndarray) -> np.ndarray:
        """Transform data using fitted scaler."""
        if not self._scaler_fitted:
            raise ValueError("Scaler not fitted")
        original_shape = X.shape
        X_flat = X.reshape(-1, X.shape[-1])
        X_scaled = self.scaler.transform(X_flat)
        return X_scaled.reshape(original_shape)

    def inverse_transform(self, X: np.ndarray) -> np.ndarray:
        """Inverse transform scaled data."""
        if not self._scaler_fitted:
            raise ValueError("Scaler not fitted")
        original_shape = X.shape
        X_flat = X.reshape(-1, X.shape[-1])
        X_unscaled = self.scaler.inverse_transform(X_flat)
        return X_unscaled.reshape(original_shape)

    def save_scaler(self, path: str):
        """Save scaler for inference."""
        import joblib
        joblib.dump(self.scaler, path)

    def load_scaler(self, path: str):
        """Load scaler from disk."""
        import joblib
        self.scaler = joblib.load(path)
        self._scaler_fitted = True

    def generate_demo_data(
        self,
        n_hours: int = 2000,
        n_features: int = 5,
        n_anomalies: int = 5,
        anomaly_magnitude: float = 3.0
    ) -> Tuple[np.ndarray, np.ndarray, List[int]]:
        """
        Generate synthetic demo data with known anomalies.

        Returns:
            - Normal windows (for training)
            - All windows (for testing, includes anomalies)
            - Anomaly window indices (for evaluation)
        """
        np.random.seed(42)

        # Time index
        hours = np.arange(n_hours)

        # Generate multi-feature "normal" data
        data = np.zeros((n_hours, n_features))

        for i in range(n_features):
            # Daily pattern
            daily = 5 * np.sin(2 * np.pi * hours / 24 + i * np.pi / 4)
            # Slow trend
            trend = 0.0005 * hours
            # Normal noise
            noise = 0.5 * np.random.randn(n_hours)
            # Base value
            base = 20 + i * 3

            data[:, i] = base + daily + trend + noise

        # Inject anomalies at random positions
        anomaly_starts = np.random.choice(
            range(100, n_hours - 100),
            size=n_anomalies,
            replace=False
        )

        anomaly_windows = []
        for start in anomaly_starts:
            # Inject anomaly: sudden shift or spike
            duration = np.random.randint(3, 12)
            feature = np.random.randint(0, n_features)

            # Anomaly type: shift up, shift down, or spike
            anomaly_type = np.random.choice(["shift_up", "shift_down", "spike"])

            if anomaly_type == "shift_up":
                data[start:start + duration, feature] += anomaly_magnitude * 5
            elif anomaly_type == "shift_down":
                data[start:start + duration, feature] -= anomaly_magnitude * 5
            else:  # spike
                data[start, feature] += anomaly_magnitude * 10

        # Create all windows
        all_windows = self.create_windows(data)

        # Find which windows contain anomalies
        anomaly_window_indices = []
        for idx, start in enumerate(range(0, len(data) - self.window_size, self.step_size)):
            window_range = range(start, start + self.window_size)
            for anomaly_start in anomaly_starts:
                if anomaly_start in window_range:
                    if idx < len(all_windows):
                        anomaly_window_indices.append(idx)
                    break

        # Create normal windows (exclude anomaly periods)
        exclude_periods = [(s - 10, s + 20) for s in anomaly_starts]
        normal_windows = self.create_windows(data, exclude_periods)

        logger.info(
            f"Generated {len(normal_windows)} normal windows, "
            f"{len(all_windows)} total windows, "
            f"{len(anomaly_window_indices)} anomalous windows"
        )

        return normal_windows, all_windows, anomaly_window_indices


# Sensor configurations per equipment type
AUTOENCODER_SENSOR_CONFIGS: Dict[str, Dict[str, Any]] = {
    "chiller": {
        "features": [
            "chw_supply_temp",
            "chw_return_temp",
            "suction_pressure",
            "discharge_pressure",
            "compressor_current"
        ],
        "description": "Chiller operating pattern anomaly detection"
    },
    "ahu": {
        "features": [
            "supply_temp",
            "return_temp",
            "filter_dp",
            "fan_current",
            "mixed_air_temp"
        ],
        "description": "AHU operating pattern anomaly detection"
    },
    "generator": {
        "features": [
            "battery_voltage",
            "oil_pressure",
            "coolant_temp",
            "rpm",
            "load_pct"
        ],
        "description": "Generator operating pattern anomaly detection"
    },
    "fcu": {
        "features": [
            "supply_temp",
            "fan_current",
            "valve_position"
        ],
        "description": "FCU operating pattern anomaly detection"
    },
    "ups": {
        "features": [
            "battery_voltage",
            "load_pct",
            "temperature"
        ],
        "description": "UPS operating pattern anomaly detection"
    },
    "vav": {
        "features": [
            "airflow",
            "damper_position",
            "zone_temp",
            "supply_temp"
        ],
        "description": "VAV operating pattern anomaly detection"
    },
    "pump": {
        "features": [
            "flow_rate",
            "discharge_pressure",
            "motor_current",
            "vibration",
            "temperature"
        ],
        "description": "Pump operating pattern anomaly detection"
    }
}
