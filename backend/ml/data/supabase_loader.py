"""
Supabase Data Loader — Load real equipment sensor data for ML training.

Reads from the `equipment_sensor_readings` table (populated by SimulationPersistence
or real BMS via SIMBIOT) and pivots into wide-format DataFrames suitable for
LSTMDataPrep.prepare_from_dataframe() and autoencoder training.

The sensor_type names stored in Supabase are the RAW BMS/simulation point names
(e.g., "supply_temp", "load_pct"), which need mapping to ML feature names via
the SENSOR_MAPPING from sentinel_ml_feeder.py.

Usage:
    loader = SupabaseTrainingDataLoader()

    # For LSTM
    df = loader.load_equipment_type_dataframe("chiller", min_hours=500)
    # Returns DataFrame with columns: [timestamp, chw_supply_temp, chw_return_temp, ...]

    # For autoencoder (numpy)
    X = loader.load_equipment_type_array("ahu", min_hours=200)
    # Returns array of shape (hours, n_features)
"""

import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np

try:
    import pandas as pd
except ImportError:
    raise ImportError("pandas required: pip install pandas")

from app.services.sentinel_ml_feeder import SENSOR_MAPPING
from ml.lstm.data_prep import EquipmentDataLoader

logger = logging.getLogger(__name__)


def _get_supabase_client():
    """Get Supabase client, or None if unavailable."""
    try:
        from app.database.supabase_client import get_supabase_client

        return get_supabase_client()
    except Exception as e:
        logger.warning(f"Supabase client unavailable: {e}")
        return None


def _invert_sensor_mapping(equipment_type: str) -> dict[str, str]:
    """Invert SENSOR_MAPPING: ml_feature_name -> bms_point_name.

    The mapping in sentinel_ml_feeder is bms_name -> ml_name.
    We need ml_name -> bms_name to know which sensor_type values to query.
    """
    mapping = SENSOR_MAPPING.get(equipment_type, {})
    # bms_name -> ml_name  =>  ml_name -> bms_name
    return {ml_name: bms_name for bms_name, ml_name in mapping.items()}


def _get_bms_sensor_types(equipment_type: str) -> list[str]:
    """Get the list of BMS sensor_type values stored in Supabase for an equipment type."""
    mapping = SENSOR_MAPPING.get(equipment_type, {})
    return list(mapping.keys())


class SupabaseTrainingDataLoader:
    """Load training data from Supabase equipment_sensor_readings table."""

    def __init__(self, site_id: str | None = None):
        """
        Args:
            site_id: Optional site filter (site_id in the table). If None, loads all sites.
        """
        self.site_id = site_id
        self.client = _get_supabase_client()

    def delete_readings(self) -> int:
        """Delete all sensor readings for the configured site_id.

        Call this after successful training to free up storage.
        Training data is not needed once models are trained.

        Returns:
            Number of rows deleted.

        Raises:
            RuntimeError: If no site_id is set (would delete data for all sites).
        """
        if not self.site_id:
            raise RuntimeError("delete_readings requires a site_id — refusing to delete all sites")

        if not self.client:
            logger.warning("Supabase client unavailable — cannot delete readings")
            return 0

        try:
            result = self.client.table("equipment_sensor_readings").delete().eq("site_id", self.site_id).execute()
            deleted = len(result.data) if result.data else 0
            logger.info("[DATA LOADER] Deleted %d readings for site_id=%s", deleted, self.site_id)
            return deleted
        except Exception as e:
            logger.error("Failed to delete equipment_sensor_readings for %s: %s", self.site_id, e)
            return 0

    def _query_readings(
        self,
        equipment_type: str,
        sensor_types: list[str],
        min_date: datetime | None = None,
        limit: int = 50000,
    ) -> list[dict[str, Any]]:
        """Query equipment_sensor_readings for a given type's sensors.

        We identify equipment by matching codes that contain the type prefix.
        E.g., chiller equipment codes contain "CHILLER": S002-CHILLER-B1-001.
        """
        if not self.client:
            return []

        # Map equipment_type to code pattern
        type_upper = equipment_type.upper()

        # Build query — get readings for all equipment of this type
        query = (
            self.client.table("equipment_sensor_readings")
            .select("equipment_id, sensor_type, value, recorded_at")
            .like("equipment_id", f"%-{type_upper}-%")
            .in_("sensor_type", sensor_types)
            .order("recorded_at", desc=False)
            .limit(limit)
        )

        if self.site_id:
            query = query.eq("site_id", self.site_id)

        if min_date:
            query = query.gte("recorded_at", min_date.isoformat())

        try:
            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to query equipment_sensor_readings: {e}")
            return []

    def _pivot_to_dataframe(
        self,
        rows: list[dict[str, Any]],
        equipment_type: str,
    ) -> pd.DataFrame | None:
        """Pivot long-format sensor readings into wide-format DataFrame.

        Input rows: [{equipment_id, sensor_type, value, recorded_at}, ...]
        Output: DataFrame with columns [timestamp, ml_feature_1, ml_feature_2, ...]
        """
        if not rows:
            return None

        df = pd.DataFrame(rows)
        df["recorded_at"] = pd.to_datetime(df["recorded_at"])

        # Map BMS sensor_type names to ML feature names
        bms_to_ml = SENSOR_MAPPING.get(equipment_type, {})
        df["ml_feature"] = df["sensor_type"].map(bms_to_ml)

        # Drop rows where sensor_type didn't map (shouldn't happen but be safe)
        df = df.dropna(subset=["ml_feature"])

        if df.empty:
            return None

        # Round timestamps to nearest hour for grouping
        df["hour"] = df["recorded_at"].dt.floor("h")

        # For multiple equipment of the same type, average their readings per hour
        # This gives us a type-level signal, which is what the ML models expect
        pivot = df.pivot_table(
            index="hour",
            columns="ml_feature",
            values="value",
            aggfunc="mean",
        )

        # Reset index and rename
        pivot = pivot.reset_index().rename(columns={"hour": "timestamp"})
        pivot = pivot.sort_values("timestamp")

        return pivot

    def get_available_hours(self, equipment_type: str) -> int:
        """Check how many hours of data are available for an equipment type."""
        if not self.client:
            return 0

        type_upper = equipment_type.upper()
        sensor_types = _get_bms_sensor_types(equipment_type)
        if not sensor_types:
            return 0

        try:
            query = (
                self.client.table("equipment_sensor_readings")
                .select("recorded_at", count="exact")
                .like("equipment_id", f"%-{type_upper}-%")
                .in_("sensor_type", [sensor_types[0]])  # Check one sensor as proxy
            )
            if self.site_id:
                query = query.eq("site_id", self.site_id)

            result = query.execute()
            return result.count or 0
        except Exception as e:
            logger.warning(f"Failed to count available hours for {equipment_type}: {e}")
            return 0

    def load_equipment_type_dataframe(
        self,
        equipment_type: str,
        min_hours: int = 500,
        lookback_days: int = 365,
        delete_after_load: bool = False,
    ) -> pd.DataFrame | None:
        """Load sensor data as a wide-format DataFrame for LSTM training.

        Args:
            equipment_type: Equipment type (chiller, ahu, etc.)
            min_hours: Minimum hours of data required
            lookback_days: How far back to query
            delete_after_load: If True, delete all sensor readings for this site after
                successful loading and validation. Used to free storage after training
                data has been consumed. Raises RuntimeError if site_id is not set.

        Returns:
            DataFrame with columns [timestamp, feature_1, feature_2, ...] or None
        """
        if delete_after_load and not self.site_id:
            raise RuntimeError("delete_after_load=True requires site_id to be set")
        sensor_types = _get_bms_sensor_types(equipment_type)
        if not sensor_types:
            logger.warning(f"No sensor mapping for equipment type: {equipment_type}")
            return None

        config = EquipmentDataLoader.get_config(equipment_type)
        required_features = config["features"]

        min_date = datetime.utcnow() - timedelta(days=lookback_days)

        logger.info(
            f"[DATA LOADER] Querying {equipment_type} readings (sensors: {sensor_types}, since: {min_date.date()})"
        )

        rows = self._query_readings(
            equipment_type=equipment_type,
            sensor_types=sensor_types,
            min_date=min_date,
            limit=100000,  # Up to 100k rows
        )

        if not rows:
            logger.warning(f"[DATA LOADER] No readings found for {equipment_type}")
            return None

        logger.info(f"[DATA LOADER] Got {len(rows)} raw readings for {equipment_type}")

        df = self._pivot_to_dataframe(rows, equipment_type)
        if df is None:
            return None

        logger.info(f"[DATA LOADER] Pivoted to {len(df)} hourly rows, columns: {list(df.columns)}")

        # Check we have enough data
        if len(df) < min_hours:
            logger.warning(f"[DATA LOADER] Insufficient data for {equipment_type}: {len(df)} hours (need {min_hours})")
            return None

        # Check all required features are present
        missing = [f for f in required_features if f not in df.columns]
        if missing:
            logger.warning(
                f"[DATA LOADER] Missing features for {equipment_type}: {missing}. "
                f"Available: {[c for c in df.columns if c != 'timestamp']}"
            )
            return None

        if delete_after_load:
            self.delete_readings()

        return df

    def load_equipment_type_array(
        self,
        equipment_type: str,
        min_hours: int = 200,
        lookback_days: int = 365,
        delete_after_load: bool = False,
    ) -> np.ndarray | None:
        """Load sensor data as a numpy array (hours, features) for autoencoder.

        Args:
            equipment_type: Equipment type
            min_hours: Minimum hours required
            lookback_days: How far back to look
            delete_after_load: Passed through to load_equipment_type_dataframe.
                Set to True after training to free storage.

        Returns:
            Array of shape (hours, n_features) or None
        """
        df = self.load_equipment_type_dataframe(
            equipment_type,
            min_hours=min_hours,
            lookback_days=lookback_days,
            delete_after_load=delete_after_load,
        )
        if df is None:
            return None

        config = EquipmentDataLoader.get_config(equipment_type)
        features = config["features"]

        # Extract only the feature columns in the right order
        available = [f for f in features if f in df.columns]
        if len(available) < len(features):
            logger.warning(
                f"[DATA LOADER] Only {len(available)}/{len(features)} features available for {equipment_type}"
            )
            return None

        # Forward-fill small gaps (up to 3 hours) then drop remaining NaNs
        data = df[features].fillna(method="ffill", limit=3).dropna()

        if len(data) < min_hours:
            logger.warning(
                f"[DATA LOADER] After cleaning, only {len(data)} hours (need {min_hours}) for {equipment_type}"
            )
            return None

        return data.values

    def get_data_summary(self) -> dict[str, Any]:
        """Get a summary of available training data per equipment type."""
        summary = {}
        for eq_type in EquipmentDataLoader.list_equipment_types():
            hours = self.get_available_hours(eq_type)
            config = EquipmentDataLoader.get_config(eq_type)
            summary[eq_type] = {
                "available_hours": hours,
                "required_features": config["features"],
                "target": config["target"],
                "ready_for_lstm": hours >= 500,
                "ready_for_autoencoder": hours >= 200,
            }
        return summary
