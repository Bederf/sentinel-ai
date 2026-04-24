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
from typing import Any

import numpy as np

from app.services.ml_config import (
    MIN_ANOMALY_SCORING_HOURS,
    MIN_ANOMALY_TRAINING_HOURS,
    MIN_ENERGY_TRAINING_HOURS,
    MIN_LSTM_TRAINING_HOURS,
)

logger = logging.getLogger(__name__)

# How often to check LSTM training (every N hours ingested)
TRAINING_CHECK_INTERVAL = 24

# Map BMS sensor names → ML feature names per equipment type.
# ML expects specific feature names; BMS/SIMBIOT may use different names.
# This bridge ensures they match.
SENSOR_MAPPING: dict[str, dict[str, str]] = {
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
    # New equipment types — previously identity-mapped only
    "cooling_tower": {
        "ct_basin_temp": "basin_temp",
        "ct_fan_speed": "fan_speed",
        "ct_water_level": "water_level",
        "ct_fan_current": "fan_current",
    },
    "transformer": {
        "tx_winding_temp": "winding_temp",
        "tx_oil_temp": "oil_temp",
        "tx_load_percent": "load_pct",
        "tx_tap_position": "tap_position",
    },
    "crac": {
        "crac_supply_temp": "supply_temp",
        "crac_return_temp": "return_temp",
        "crac_humidity_pct": "humidity_pct",
        "crac_compressor_current": "compressor_current",
    },
    "ats": {
        "ats_mains_voltage": "mains_voltage",
        "ats_generator_voltage": "generator_voltage",
        "ats_position": "position",
        "ats_transfer_status": "transfer_status",
    },
    "pfc": {
        "pfc_power_factor": "power_factor",
        "pfc_reactive_power_kvar": "reactive_power_kvar",
        "pfc_current_a": "current_a",
        "pfc_voltage_v": "voltage_v",
    },
    # Site-wide aggregate from /telemetry bridge endpoint
    "site_aggregate": {
        "lighting_kw": "lighting_kw",
        "hvac_kw": "hvac_kw",
        "total_kw": "total_kw",
        "flow_lpm": "flow_lpm",
        "pressure_bar": "pressure_bar",
        "zone_count": "zone_count",
        "equip_online": "equip_online",
        # Occupancy from SecurityOccupancyService
        "total_occupancy": "total_occupancy",
        "occupied_zones": "occupied_zones",
        "peak_zone_density": "peak_zone_density",
        # Derived features (populated at ingest time, not from bridge)
        "hvac_ratio": "hvac_ratio",
        "lighting_ratio": "lighting_ratio",
        "non_hvac_kw": "non_hvac_kw",
    },
    "bess": {
        "bess_soc_pct": "soc_pct",
        "bess_charge_power_kw": "charge_power_kw",
        "bess_discharge_power_kw": "discharge_power_kw",
        "bess_cell_temp": "cell_temp",
    },
    "inverter": {
        "inv_dc_input_power_kw": "dc_input_power_kw",
        "inv_ac_output_power_kw": "ac_output_power_kw",
        "inv_efficiency_pct": "efficiency_pct",
        "inv_temp": "inverter_temp",
    },
    "split": {
        "room_temp": "room_temp",
        "supply_temp": "supply_temp",
        "fan_speed": "fan_speed",
        "valve_position": "valve_position",
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

    def __init__(self, min_hours: int = MIN_LSTM_TRAINING_HOURS):
        self.min_hours = min_hours
        self._hours_ingested = 0

        # Per equipment-type time series: {equip_type: {feature_name: [values]}}
        self._buffers: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        # Track which equipment codes map to which types
        self._code_to_type: dict[str, str] = {}
        self._training_results: list[dict[str, Any]] = []
        self._last_train_time: datetime | None = None
        # Tag each ingested hour with its source for model filtering
        self._data_sources: list[str] = []  # Parallel list to buffers
        # Fault event buffer — accumulates BACnet EventNotification records
        # from /alarms endpoint. When 500+ events are buffered, Fault Classifier trains.
        self._fault_events: list[dict[str, Any]] = []

    @property
    def fault_event_count(self) -> int:
        """Number of fault events currently buffered."""
        return len(self._fault_events)

    @property
    def min_lstm_hours(self) -> int:
        return MIN_LSTM_TRAINING_HOURS

    @property
    def min_anomaly_hours(self) -> int:
        return MIN_ANOMALY_TRAINING_HOURS

    @property
    def min_energy_hours(self) -> int:
        return MIN_ENERGY_TRAINING_HOURS

    @property
    def hours_ingested(self) -> int:
        return self._hours_ingested

    @property
    def is_ready_to_train(self) -> bool:
        """Check if enough data has been accumulated for training."""
        return self._hours_ingested >= self.min_hours

    def ingest(
        self,
        equipment_states: dict[str, dict[str, Any]],
        simulated_time: datetime,
        data_source: str = "bridge_poll",
    ) -> None:
        """Ingest one cycle of equipment sensor data (call once per poll/integration).

        Ingests everything always. Training is triggered separately per model type
        based on each model's own readiness criteria.

        Args:
            equipment_states: {code: {type, sensor_readings: {name: value}}}
            simulated_time: Current timestamp
            data_source: Tag for model filtering ("bridge_poll", "bms_event",
                         "inspection", "work_order_feedback")
        """
        for code, state in equipment_states.items():
            equip_type = state.get("type", "").lower()
            if not equip_type:
                continue

            readings = state.get("sensor_readings", {})
            if not readings:
                continue

            self._code_to_type[code] = equip_type

            # Use known mapping if available, otherwise identity-map every reading
            # (pass through all telemetry, not just the ~20 sensors in SENSOR_MAPPING)
            if equip_type in SENSOR_MAPPING:
                mapping = SENSOR_MAPPING[equip_type]
                for sim_key, ml_feature in mapping.items():
                    value = readings.get(sim_key)
                    if value is not None:
                        self._buffers[equip_type][ml_feature].append(float(value))

                # Derive site-level ratios for site_aggregate
                if equip_type == "site_aggregate":
                    hvac_kw = readings.get("hvac_kw")
                    lighting_kw = readings.get("lighting_kw")
                    total_kw = readings.get("total_kw")
                    if total_kw and total_kw != 0:
                        if hvac_kw is not None:
                            self._buffers[equip_type]["hvac_ratio"].append(round(float(hvac_kw) / float(total_kw), 4))
                        if lighting_kw is not None:
                            self._buffers[equip_type]["lighting_ratio"].append(
                                round(float(lighting_kw) / float(total_kw), 4)
                            )
                    if hvac_kw is not None and lighting_kw is not None and total_kw is not None:
                        non_hvac = float(total_kw) - float(hvac_kw) - float(lighting_kw)
                        self._buffers[equip_type]["non_hvac_kw"].append(round(max(0, non_hvac), 3))
            else:
                # Catch-all: store every sensor reading under its own name
                # so no telemetry is discarded even for unmapped equipment types
                # (CT, CRAC, split, electrical, fire, security, etc.)
                for sim_key, value in readings.items():
                    if value is not None:
                        self._buffers[equip_type][sim_key].append(float(value))

        self._hours_ingested += 1
        self._data_sources.append(data_source)

    def get_latest_site_power(self) -> dict[str, float] | None:
        """Return latest HVAC/lighting/total kW from site_aggregate buffer.

        Returns None when no bridge data has arrived yet, so the cockpit can
        display "No info" instead of fake zeros.
        """
        buf = self._buffers.get("site_aggregate")
        if not buf:
            return None
        if not buf.get("total_kw"):
            return None
        return {
            "hvac_kw": round(buf.get("hvac_kw", [0])[-1], 2),
            "lighting_kw": round(buf.get("lighting_kw", [0])[-1], 2),
            "total_kw": round(buf.get("total_kw", [0])[-1], 2),
        }

    def score_anomaly(self, hours_ingested: int | None = None) -> dict[str, float]:
        """Compute anomaly_score per equipment code from the latest buffer readings.

        Uses a simple z-score approach: for each sensor feature, compute
        (latest - rolling_mean) / rolling_std using the last 72 readings
        as the reference window. The max absolute z-score across features
        becomes the anomaly_score (clamped to [0, 1]).

        Requires MIN_ANOMALY_SCORING_HOURS (24h) of data before producing
        non-trivial scores. Below that threshold returns empty dict.

        Returns:
            Dict of {equipment_code: anomaly_score} for equipment with
            sufficient data. anomaly_score: 0.0 = normal, 1.0 = max anomaly.
        """
        if hours_ingested is None:
            hours_ingested = self._hours_ingested

        if hours_ingested < MIN_ANOMALY_SCORING_HOURS:
            return {}

        scores: dict[str, float] = {}

        for code, equip_type in self._code_to_type.items():
            buf = self._buffers.get(equip_type, {})
            if not buf:
                continue

            max_z = 0.0
            for _feature, values in buf.items():
                if len(values) < 12:  # Need at least 12 readings for a meaningful mean/std
                    continue
                # Use last 72 readings as rolling window
                window = values[-72:]
                mean = sum(window) / len(window)
                # Population std (ddof=0) — simple and stable
                variance = sum((v - mean) ** 2 for v in window) / len(window)
                std = variance**0.5
                if std < 1e-6:  # Avoid division by zero on constant signals
                    continue
                latest = values[-1]
                z = abs((latest - mean) / std)
                if z > max_z:
                    max_z = z

            # Normalise: z > 3 is extreme; clamp to [0, 1]
            anomaly_score = min(max_z / 3.0, 1.0)
            scores[code] = round(anomaly_score, 4)

        return scores

    def score_lstm_anomaly(self, hours_ingested: int | None = None) -> dict[str, float]:
        """Compute LSTM-derived anomaly scores per equipment code from prediction error.

        For each equipment code, uses the last N readings to predict the next value
        via a simple autoregressive baseline (last value as prediction). The absolute
        prediction error is then normalised against the training window's error
        distribution (min-max) to produce a score in [0.0, 1.0].

        Requires MIN_LSTM_TRAINING_HOURS (500h) of data before producing scores —
        this ensures the buffer has enough history for meaningful error statistics.
        Below that threshold returns empty dict.

        Returns:
            Dict of {equipment_code: lstm_anomaly_score} for equipment with
            sufficient data. 0.0 = perfectly on-model, 1.0 = maximally anomalous.
        """
        if hours_ingested is None:
            hours_ingested = self._hours_ingested

        if hours_ingested < MIN_LSTM_TRAINING_HOURS:
            return {}

        scores: dict[str, float] = {}

        for code, equip_type in self._code_to_type.items():
            buf = self._buffers.get(equip_type, {})
            if not buf:
                continue

            # Use the primary sensor feature for the equipment type
            primary_feature = next(iter(buf.keys()), None)
            if not primary_feature:
                continue

            values = buf[primary_feature]
            if len(values) < 24:
                continue

            # Simple autoregressive error: predict next = current
            # Compute errors over the last 72 readings (72h window)
            window = values[-72:]
            errors = [abs(window[i] - window[i - 1]) for i in range(1, len(window))]

            if not errors:
                continue

            mean_err = sum(errors) / len(errors)
            variance = sum((e - mean_err) ** 2 for e in errors) / len(errors)
            std_err = variance**0.5

            # Latest prediction error
            latest_error = abs(values[-1] - values[-2]) if len(values) >= 2 else 0.0

            # Min-max normalise: use mean + 2*std as the "high anomaly" threshold
            if std_err < 1e-6:
                # Constant signal — no anomaly possible
                lstm_anomaly_score = 0.0
            else:
                # z-score of latest error against the error distribution
                z = (latest_error - mean_err) / std_err
                lstm_anomaly_score = min(max(z / 3.0, 0.0), 1.0)

            scores[code] = round(lstm_anomaly_score, 4)

        return scores

    def score_autoencoder_anomaly(self, hours_ingested: int | None = None) -> dict[str, float]:
        """Compute autoencoder-derived anomaly scores per equipment code.

        Requires an autoencoder model to have been trained for the equipment type.
        Below that threshold returns empty dict.

        Returns:
            Dict of {equipment_code: autoencoder_anomaly_score} for equipment with
            trained models. 0.0 = normal reconstruction, 1.0 = maximally anomalous.
        """
        # Autoencoder scoring not yet implemented — placeholder until AE training
        # pipeline is complete. Remove this stub once score_autoencoder() is wired.
        return {}

    def ingest_fault_event(self, alarm: dict[str, Any]) -> None:
        """Ingest one BACnet alarm/fault event into the Fault Classifier buffer.

        Accumulates alarm records from the /alarms endpoint. When 500+ events are
        buffered, the Fault Classifier can be trained via train_fault_classifier().
        Each alarm record is expected to have at least:
          - alarm.active_text or alarm.message_text: fault description
          - alarm.source_object: equipment identifier
          - alarm.event_state or alarm.event_type: fault category
          - alarm.time_stamp: when it occurred

        Args:
            alarm: BACnet EventNotification dict from the bridge /alarms endpoint
        """
        self._fault_events.append(alarm)
        # Keep buffer bounded — 10 000 events max
        if len(self._fault_events) > 10_000:
            self._fault_events = self._fault_events[-5000:]

    def train_fault_classifier(self) -> list[dict[str, Any]]:
        """Train the Fault Classifier if sufficient labelled events are buffered.

        Requires MIN_FAULT_EVENTS (500) events in the buffer.
        Uses the fault event text + equipment ID + time features to train
        a multi-class Random Forest classifier.

        Returns:
            List of training result dicts
        """
        MIN_FAULT_EVENTS = 500
        if len(self._fault_events) < MIN_FAULT_EVENTS:
            logger.info(
                f"[ML FEEDER] Fault Classifier: {len(self._fault_events)} < {MIN_FAULT_EVENTS} events — "
                "skipping training"
            )
            return []

        logger.info(f"[ML FEEDER] Fault Classifier training: {len(self._fault_events)} events")
        results = []

        try:
            import numpy as np
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.feature_extraction.text import TfidfVectorizer

            # Build labelled dataset from fault events
            texts = []
            labels = []
            equipment_ids = []

            for event in self._fault_events:
                # Extract fault text
                msg = event.get("active_text") or event.get("message_text") or event.get("description", "") or ""
                # Extract equipment code from source_object
                src = event.get("source_object", "") or event.get("object_id", "")
                # Extract fault category
                category = event.get("event_type") or event.get("alarm_class") or event.get("event_state", "unknown")
                texts.append(f"{src} {msg}")
                labels.append(str(category))
                equipment_ids.append(src)

            # TF-IDF on combined text
            vectorizer = TfidfVectorizer(max_features=100, ngram_range=(1, 2))
            try:
                X = vectorizer.fit_transform(texts).toarray()
            except Exception:
                X = np.zeros((len(texts), 0))

            # Encode labels
            from sklearn.preprocessing import LabelEncoder

            le = LabelEncoder()
            y = le.fit_transform(labels)

            if X.shape[0] < 10 or len(le.classes_) < 2:
                logger.warning(
                    f"[ML FEEDER] Fault Classifier: insufficient diversity "
                    f"({X.shape[0]} samples, {len(le.classes_)} classes)"
                )
                return []

            # Train Random Forest
            clf = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                class_weight="balanced",
                random_state=42,
            )
            clf.fit(X, y)

            # Save model + vectorizer + label encoder
            import joblib

            model_dir = "/opt/bms-intelligence/backend/ml/models/classifier"
            import os

            os.makedirs(model_dir, exist_ok=True)
            joblib.dump(clf, f"{model_dir}/fault_rf.joblib")
            joblib.dump(vectorizer, f"{model_dir}/fault_vectorizer.joblib")
            joblib.dump(le, f"{model_dir}/fault_label_encoder.joblib")

            results.append(
                {
                    "model_type": "fault_classifier",
                    "samples": len(texts),
                    "classes": list(le.classes_),
                    "n_features": X.shape[1],
                }
            )
            logger.info(f"[ML FEEDER] Fault Classifier: trained on {len(texts)} events, {len(le.classes_)} fault types")

        except ImportError as e:
            logger.warning(f"[ML FEEDER] Fault Classifier skipped (sklearn unavailable): {e}")
        except Exception as e:
            logger.error(f"[ML FEEDER] Fault Classifier training failed: {e}")
            results.append({"model_type": "fault_classifier", "error": str(e)})

        self._training_results.extend(results)
        return results

    def get_buffer_stats(self) -> dict[str, Any]:
        """Get statistics about accumulated data."""
        stats = {
            "hours_ingested": self._hours_ingested,
            "ready_to_train": self.is_ready_to_train,
            "fault_events_buffered": len(self._fault_events),
            "equipment_types": {},
        }
        for equip_type, features in self._buffers.items():
            stats["equipment_types"][equip_type] = {
                "features": list(features.keys()),
                "samples_per_feature": {k: len(v) for k, v in features.items()},
            }
        return stats

    def prepare_lstm_data(self, equipment_type: str) -> tuple | None:
        """Prepare LSTM training data from accumulated buffer.

        Returns (X, y) numpy arrays or None if insufficient data.
        """
        from ml.lstm.data_prep import EquipmentDataLoader, LSTMDataPrep

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
            logger.warning(f"{equipment_type}: only {min_samples} samples, need 500+")
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

    def prepare_autoencoder_data(self, equipment_type: str) -> tuple | None:
        """Prepare autoencoder training data from accumulated buffer.

        Returns (X_normal, X_all, anomaly_indices) or None.
        """
        from ml.autoencoder.data_prep import AUTOENCODER_SENSOR_CONFIGS

        if equipment_type not in AUTOENCODER_SENSOR_CONFIGS:
            return None

        config = AUTOENCODER_SENSOR_CONFIGS[equipment_type]
        features = config["features"]

        buf = self._buffers.get(equipment_type, {})
        if not buf:
            return None

        min_samples = min(len(buf.get(f, [])) for f in features)
        if min_samples < 200:
            logger.warning(f"{equipment_type} autoencoder: only {min_samples} samples")
            return None

        n = min_samples
        data = np.column_stack([np.array(buf[f][:n]) for f in features])

        # Create windowed data (assumed normal operation)
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

    def train_if_ready(self, force: bool = False) -> list[dict[str, Any]]:
        """Train ML models based on each model's own readiness criteria.

        Architecture: ingest is decoupled from training. Every call to ingest()
        stores data. This method dispatches to per-model trainers, each of which
        checks its own minimum data threshold independently.

        Args:
            force: Train even if thresholds not reached (for end-of-sim / manual trigger)

        Returns:
            List of training result dicts across all model types
        """
        results = []

        # LSTM + Autoencoder — time-series models, need ~500h minimum
        lstm_results = self._train_lstm_if_ready(force=force)
        results.extend(lstm_results)

        # Anomaly Detection — needs ~72h, triggered by weekly schedule
        anomaly_results = self._train_anomaly_if_ready(force=force)
        results.extend(anomaly_results)

        # Energy Baseline — needs ~720h (30 days), triggered monthly
        energy_results = self._train_energy_baseline_if_ready(force=force)
        results.extend(energy_results)

        if results:
            self._training_results.extend(results)
            self._last_train_time = datetime.now()
            successful = [r for r in results if "error" not in r]
            logger.info(f"[ML FEEDER] Training complete: {len(successful)}/{len(results)} models trained")

        return results

    def _train_lstm_if_ready(self, force: bool = False) -> list[dict[str, Any]]:
        """Train LSTM + Autoencoder models — requires MIN_LSTM_TRAINING_HOURS."""
        if not force and self._hours_ingested < MIN_LSTM_TRAINING_HOURS:
            return []
        if not force and self._hours_ingested % TRAINING_CHECK_INTERVAL != 0:
            return []

        results = []
        logger.info(f"[ML FEEDER] LSTM/Autoencoder check: {self._hours_ingested}h available")

        # LSTM models
        try:
            from ml.lstm.data_prep import EquipmentDataLoader
            from ml.lstm.train import LSTMTrainer

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

        # Autoencoder models
        try:
            from ml.autoencoder.data_prep import AUTOENCODER_SENSOR_CONFIGS
            from ml.autoencoder.train import AutoencoderTrainer

            trainer = AutoencoderTrainer()
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

        return results

    def _train_anomaly_if_ready(self, force: bool = False) -> list[dict[str, Any]]:
        """Train Anomaly Detection (Isolation Forest) — requires MIN_ANOMALY_TRAINING_HOURS.

        Anomaly models train on 72+ hours of zone temperature + power data.
        They are triggered weekly via a separate scheduled job, not by this method.
        This method is a no-op — the weekly job calls train_anomaly() directly.
        """
        # Anomaly detection is triggered by a separate weekly scheduled job
        # to ensure consistent retraining regardless of data accumulation rate.
        return []

    def _train_energy_baseline_if_ready(self, force: bool = False) -> list[dict[str, Any]]:
        """Train Energy Baseline regression model — requires MIN_ENERGY_TRAINING_HOURS.

        Called by monthly scheduled job. Currently a placeholder — energy baseline
        training logic to be implemented.
        """
        if not force and self._hours_ingested < MIN_ENERGY_TRAINING_HOURS:
            return []

        logger.info(
            f"[ML FEEDER] Energy baseline check: {self._hours_ingested}h available (need {MIN_ENERGY_TRAINING_HOURS}h)"
        )
        # TODO: implement energy baseline regression training
        return []

    def train_anomaly(self) -> list[dict[str, Any]]:
        """Manually trigger anomaly detection training (called by weekly job).

        Trains Isolation Forest per zone using accumulated temperature + power data.
        Requires MIN_ANOMALY_TRAINING_HOURS (72h) before first training.
        """
        if self._hours_ingested < MIN_ANOMALY_TRAINING_HOURS:
            logger.info(
                f"[ML FEEDER] Anomaly: {self._hours_ingested}h < {MIN_ANOMALY_TRAINING_HOURS}h minimum — "
                "skipping weekly training"
            )
            return []

        results = []
        logger.info(f"[ML FEEDER] Anomaly training: {self._hours_ingested}h of data")

        # Build per-zone datasets from FCU buffers
        try:
            from sklearn.ensemble import IsolationForest

            fcu_buf = self._buffers.get("fcu", {})
            chiller_buf = self._buffers.get("chiller", {})

            # Zone-level temperature anomaly
            if "room_temp" in fcu_buf and len(fcu_buf["room_temp"]) >= 72:
                n = len(fcu_buf["room_temp"])
                X_zone = np.column_stack(
                    [
                        np.array(fcu_buf["room_temp"][:n]),
                        np.array(fcu_buf.get("co2_ppm", fcu_buf["room_temp"])[:n]),
                    ]
                )
                try:
                    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
                    model.fit(X_zone)
                    # Save model
                    import joblib

                    path = "/opt/bms-intelligence/backend/ml/models/anomaly/zone_temp_if.joblib"
                    joblib.dump(model, path)
                    results.append({"model_type": "anomaly", "sub_type": "zone_temp", "samples": n})
                    logger.info(f"[ML FEEDER] Anomaly zone_temp: trained on {n} samples")
                except Exception as e:
                    logger.error(f"[ML FEEDER] Anomaly zone_temp failed: {e}")
                    results.append({"model_type": "anomaly", "sub_type": "zone_temp", "error": str(e)})

            # HVAC power anomaly
            if chiller_buf and len(next(iter(chiller_buf.values()))) >= 72:
                n = len(next(iter(chiller_buf.values())))
                X_power = np.column_stack([np.array(v[:n]) for v in chiller_buf.values()])
                try:
                    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
                    model.fit(X_power)
                    path = "/opt/bms-intelligence/backend/ml/models/anomaly/hvac_power_if.joblib"
                    joblib.dump(model, path)
                    results.append({"model_type": "anomaly", "sub_type": "hvac_power", "samples": n})
                    logger.info(f"[ML FEEDER] Anomaly hvac_power: trained on {n} samples")
                except Exception as e:
                    logger.error(f"[ML FEEDER] Anomaly hvac_power failed: {e}")
                    results.append({"model_type": "anomaly", "sub_type": "hvac_power", "error": str(e)})

        except ImportError as e:
            logger.warning(f"[ML FEEDER] Anomaly training skipped (sklearn unavailable): {e}")

        self._training_results.extend(results)
        return results

    def reset(self):
        """Clear all accumulated data."""
        self._buffers.clear()
        self._code_to_type.clear()
        self._hours_ingested = 0
        self._data_sources.clear()
        self._fault_events.clear()
