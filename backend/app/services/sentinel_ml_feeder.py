"""
SENTINEL ML Feeder — Accumulates sensor data in-memory and feeds ML trainers.

SENTINEL is data-source agnostic: it receives equipment readings from whatever
source is active (real BMS via SIMBIOT, or simulation engine). This feeder
accumulates that data and triggers ML training when enough has been collected.

Architecture:
  Data source (BMS / Simulation) → SENTINEL receives readings → SentinelMLFeeder.ingest()
  SentinelMLFeeder accumulates windowed data per equipment type.
  After sufficient data (configurable), triggers ML training directly (numpy arrays).
  No Supabase round-trip for ML training data.
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Minimum hours of data before ML training can be triggered
MIN_TRAINING_HOURS = 500  # ~21 days of hourly data
# How often to check if training should happen (every N sim hours)
TRAINING_CHECK_INTERVAL = 24  # Check daily

# Map BMS sensor names → ML feature names per equipment type.
# ML expects specific feature names; BMS/SIMBIOT may use different names.
# This bridge ensures they match.
SENSOR_MAPPING: Dict[str, Dict[str, str]] = {
    "chiller": {
        # BMS key → ml feature name
        "supply_temp": "chw_supply_temp",
        "return_temp": "chw_return_temp",
        "load_pct": "compressor_current",  # proxy: load correlates with current
        "cop": "suction_pressure",  # proxy: COP tracks refrigerant cycle
        "compressor_status": "discharge_pressure",  # proxy
    },
    "ahu": {
        "supply_air_temp": "supply_temp",
        "fan_speed_pct": "fan_current",  # proxy: fan speed ∝ current
        "fan_status": "filter_dp",  # proxy
        "supply_temp": "return_temp",  # sim uses supply_air_temp for supply
        "return_temp": "mixed_air_temp",  # proxy
    },
    "fcu": {
        "room_temp": "supply_temp",
        "fan_speed": "fan_current",  # proxy
        "valve_position": "valve_position",
    },
    "vav": {
        "zone_temp": "zone_temp",
        "damper_position": "damper_position",
        "airflow_lps": "airflow",
        "supply_temp": "supply_temp",
    },
    "generator": {
        "fuel_level_pct": "battery_voltage",  # proxy
        "oil_pressure_kpa": "oil_pressure",
        "coolant_temp": "coolant_temp",
        "load_pct": "load_pct",
    },
    "ups": {
        "battery_pct": "battery_voltage",  # proxy
        "load_pct": "load_pct",
        "temperature": "temperature",
    },
    "pump": {
        "flow_rate": "flow_rate",
        "dp_kpa": "discharge_pressure",
        "motor_current_pct": "motor_current",
        "vibration_mms": "vibration",
        "temperature": "temperature",
    },
}


class SentinelMLFeeder:
    """Accumulates equipment sensor data and feeds ML trainers directly.

    Usage:
        self.ml_feeder = SentinelMLFeeder()

        # Each data cycle (hourly from BMS or simulation):
        self.ml_feeder.ingest(equipment_states, timestamp)

        # Periodically:
        results = self.ml_feeder.train_if_ready()
    """

    def __init__(self, min_hours: int = MIN_TRAINING_HOURS):
        self.min_hours = min_hours
        self._hours_ingested = 0

        # Per equipment-type time series: {equip_type: {feature_name: [values]}}
        self._buffers: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        # Track which equipment codes map to which types
        self._code_to_type: Dict[str, str] = {}
        self._training_results: List[Dict[str, Any]] = []
        self._last_train_time: Optional[datetime] = None

    @property
    def hours_ingested(self) -> int:
        return self._hours_ingested

    @property
    def is_ready_to_train(self) -> bool:
        """Check if enough data has been accumulated for training."""
        return self._hours_ingested >= self.min_hours

    def ingest(
        self,
        equipment_states: Dict[str, Dict[str, Any]],
        simulated_time: datetime,
    ) -> None:
        """Ingest one hour of equipment sensor data.

        Args:
            equipment_states: {code: {type, sensor_readings: {name: value}}}
            timestamp: Current timestamp (simulated or real)
        """
        for code, state in equipment_states.items():
            equip_type = state.get("type", "").lower()
            if not equip_type or equip_type not in SENSOR_MAPPING:
                continue

            readings = state.get("sensor_readings", {})
            if not readings:
                continue

            self._code_to_type[code] = equip_type
            mapping = SENSOR_MAPPING[equip_type]

            # Map BMS sensor names to ML feature names
            for sim_key, ml_feature in mapping.items():
                value = readings.get(sim_key)
                if value is not None:
                    self._buffers[equip_type][ml_feature].append(float(value))

        self._hours_ingested += 1

    def get_buffer_stats(self) -> Dict[str, Any]:
        """Get statistics about accumulated data."""
        stats = {
            "hours_ingested": self._hours_ingested,
            "ready_to_train": self.is_ready_to_train,
            "equipment_types": {},
        }
        for equip_type, features in self._buffers.items():
            stats["equipment_types"][equip_type] = {
                "features": list(features.keys()),
                "samples_per_feature": {k: len(v) for k, v in features.items()},
            }
        return stats

    def prepare_lstm_data(self, equipment_type: str) -> Optional[tuple]:
        """Prepare LSTM training data from accumulated buffer.

        Returns (X, y) numpy arrays or None if insufficient data.
        """
        from ml.lstm.data_prep import LSTMDataPrep, EquipmentDataLoader

        config = EquipmentDataLoader.get_config(equipment_type)
        features = config["features"]
        target = config["target"]

        buf = self._buffers.get(equipment_type, {})
        if not buf:
            logger.warning(f"No data for {equipment_type}")
            return None

        # Check all features have data
        min_samples = min(len(buf.get(f, [])) for f in features)
        if min_samples < 500:
            logger.warning(
                f"{equipment_type}: only {min_samples} samples, need 500+"
            )
            return None

        # Build DataFrame-like array: (timesteps, n_features)
        n = min_samples
        data = np.column_stack([np.array(buf[f][:n]) for f in features])

        # Use LSTMDataPrep to create windowed sequences
        data_prep = LSTMDataPrep(window_size=168, forecast_horizons=[24, 48, 72])
        target_idx = features.index(target)

        try:
            X, y = data_prep.create_sequences(data, target_col=target_idx)
            if len(X) < 100:
                logger.warning(f"{equipment_type}: only {len(X)} sequences")
                return None
            return X, y
        except Exception as e:
            logger.error(f"Failed to prepare LSTM data for {equipment_type}: {e}")
            return None

    def prepare_autoencoder_data(self, equipment_type: str) -> Optional[tuple]:
        """Prepare autoencoder training data from accumulated buffer.

        Returns (X_normal, X_all, anomaly_indices) or None.
        """
        from ml.autoencoder.data_prep import AutoencoderDataPrep, AUTOENCODER_SENSOR_CONFIGS

        if equipment_type not in AUTOENCODER_SENSOR_CONFIGS:
            return None

        config = AUTOENCODER_SENSOR_CONFIGS[equipment_type]
        features = config["features"]

        buf = self._buffers.get(equipment_type, {})
        if not buf:
            return None

        min_samples = min(len(buf.get(f, [])) for f in features)
        if min_samples < 200:
            logger.warning(
                f"{equipment_type} autoencoder: only {min_samples} samples"
            )
            return None

        n = min_samples
        data = np.column_stack([np.array(buf[f][:n]) for f in features])

        # Create windowed data (assumed normal operation)
        data_prep = AutoencoderDataPrep(window_size=24)
        try:
            windows = []
            for i in range(len(data) - 24):
                windows.append(data[i : i + 24])
            X_normal = np.array(windows)
            # No known anomalies in accumulated data
            return X_normal, X_normal, []
        except Exception as e:
            logger.error(f"Failed to prepare autoencoder data for {equipment_type}: {e}")
            return None

    def train_if_ready(self, force: bool = False) -> List[Dict[str, Any]]:
        """Train ML models if sufficient data has accumulated.

        Args:
            force: Train even if min_hours not reached (for end-of-sim)

        Returns:
            List of training result dicts
        """
        if not force and not self.is_ready_to_train:
            return []

        if not force and self._hours_ingested % TRAINING_CHECK_INTERVAL != 0:
            return []

        results = []
        logger.info(
            f"[ML FEEDER] Training with {self._hours_ingested} hours of data"
        )

        # Train LSTM models
        try:
            from ml.lstm.train import LSTMTrainer
            from ml.lstm.data_prep import EquipmentDataLoader

            trainer = LSTMTrainer()
            for eq_type in EquipmentDataLoader.list_equipment_types():
                data = self.prepare_lstm_data(eq_type)
                if data is None:
                    continue
                X, y = data
                try:
                    result = trainer.train_with_data(eq_type, X, y, epochs=30)
                    results.append(result)
                    logger.info(f"[ML FEEDER] LSTM {eq_type}: OK")
                except Exception as e:
                    logger.error(f"[ML FEEDER] LSTM {eq_type} failed: {e}")
                    results.append({"equipment_type": eq_type, "model_type": "lstm", "error": str(e)})
        except Exception as e:
            logger.error(f"[ML FEEDER] LSTM training error: {e}")

        # Train autoencoder models
        try:
            from ml.autoencoder.train import AutoencoderTrainer

            trainer = AutoencoderTrainer()
            from ml.autoencoder.data_prep import AUTOENCODER_SENSOR_CONFIGS
            for eq_type in AUTOENCODER_SENSOR_CONFIGS:
                data = self.prepare_autoencoder_data(eq_type)
                if data is None:
                    continue
                X_normal, _, _ = data
                try:
                    result = trainer.train_with_data(eq_type, X_normal, epochs=30)
                    results.append(result)
                    logger.info(f"[ML FEEDER] Autoencoder {eq_type}: OK")
                except Exception as e:
                    logger.error(f"[ML FEEDER] Autoencoder {eq_type} failed: {e}")
                    results.append({"equipment_type": eq_type, "model_type": "autoencoder", "error": str(e)})
        except Exception as e:
            logger.error(f"[ML FEEDER] Autoencoder training error: {e}")

        self._training_results.extend(results)
        self._last_train_time = datetime.now()

        successful = [r for r in results if "error" not in r]
        logger.info(
            f"[ML FEEDER] Training complete: {len(successful)}/{len(results)} models trained"
        )
        return results

    def reset(self):
        """Clear all accumulated data."""
        self._buffers.clear()
        self._code_to_type.clear()
        self._hours_ingested = 0
