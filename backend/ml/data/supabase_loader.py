"""
Supabase Data Loader — Load real aggregate equipment telemetry for ML training.

Reads from `telemetry_hourly`, which is populated from short-retention raw
`equipment_sensor_readings`, and pivots into wide-format DataFrames suitable for
LSTMDataPrep.prepare_from_dataframe() and autoencoder training.

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
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np

try:
    import pandas as pd
except ImportError:
    raise ImportError("pandas required: pip install pandas")

from app.services.sentinel_ml_feeder import SENSOR_MAPPING
from ml.lstm.data_prep import EquipmentDataLoader
from ml.model_config import _resolve_config, get_autoencoder_features, get_lstm_features, list_ml_trainable_types

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
    """Load training data from Supabase aggregate telemetry tables."""

    def __init__(self, site_id: str | None = None):
        """
        Args:
            site_id: Optional site filter (site_id in the table). If None, loads all sites.
        """
        self.site_id = site_id
        self.client = _get_supabase_client()
        self.last_load_metadata: dict[str, Any] = {}

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

    def _database_url(self) -> str | None:
        try:
            from app.config.settings import settings

            return settings.database_url
        except Exception as e:
            logger.warning("[DATA LOADER] settings unavailable: %s", e)
            return None

    def _feature_contract(self, equipment_type: str, model_type: str) -> tuple[list[str], dict[str, str]]:
        """Return required ML features and source point -> output feature mapping."""
        if model_type == "autoencoder":
            features = get_autoencoder_features(equipment_type, self.site_id)
        else:
            features = get_lstm_features(equipment_type, self.site_id)

        site_config = _resolve_config(equipment_type, self.site_id) if self.site_id else None
        if self.site_id and site_config and site_config.get("site_id") == self.site_id and features:
            return features, {feature: feature for feature in features}

        bms_to_ml = SENSOR_MAPPING.get(equipment_type, {})
        if bms_to_ml:
            mapped_features = [ml_name for ml_name in bms_to_ml.values() if not features or ml_name in features]
            return mapped_features or features, bms_to_ml

        return features, {feature: feature for feature in features}

    def _query_hourly_aggregates(
        self,
        equipment_type: str,
        source_points: list[str],
        min_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Query long-retention hourly aggregate telemetry for training."""
        if not source_points:
            return []

        database_url = self._database_url()
        if not database_url:
            logger.warning("[DATA LOADER] DATABASE_URL not set; cannot query telemetry_hourly")
            return []

        try:
            import psycopg2
            import psycopg2.extras

            conn = psycopg2.connect(database_url)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        except Exception as e:
            logger.warning("[DATA LOADER] telemetry_hourly connection unavailable: %s", e)
            return []

        type_upper = equipment_type.upper()
        params: list[Any] = [f"%-{type_upper}-%", source_points]
        where = ["equipment_id LIKE %s", "point_name = ANY(%s)"]
        if self.site_id:
            where.append("site_id = %s")
            params.append(self.site_id)
        if min_date:
            where.append("hour_bucket >= %s")
            params.append(min_date)

        try:
            cur.execute(
                f"""
                SELECT equipment_id,
                       point_name AS sensor_type,
                       value_avg::float AS value,
                       hour_bucket AS recorded_at
                FROM telemetry_hourly
                WHERE {" AND ".join(where)}
                  AND value_avg IS NOT NULL
                ORDER BY hour_bucket ASC
                """,
                params,
            )
            return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error("[DATA LOADER] Failed to query telemetry_hourly: %s", e)
            return []
        finally:
            cur.close()
            conn.close()

    def _pivot_to_dataframe(
        self,
        rows: list[dict[str, Any]],
        equipment_type: str,
        source_to_feature: dict[str, str] | None = None,
    ) -> pd.DataFrame | None:
        """Pivot long-format sensor readings into wide-format DataFrame.

        Input rows: [{equipment_id, sensor_type, value, recorded_at}, ...]
        Output: DataFrame with columns [timestamp, ml_feature_1, ml_feature_2, ...]
        """
        if not rows:
            return None

        df = pd.DataFrame(rows)
        df["recorded_at"] = pd.to_datetime(df["recorded_at"])

        # Map source point names to ML feature names.
        source_to_feature = source_to_feature or SENSOR_MAPPING.get(equipment_type, {})
        df["ml_feature"] = df["sensor_type"].map(source_to_feature)

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
        """Check feature-complete distinct hourly coverage for an equipment type."""
        df = self.load_equipment_type_dataframe(equipment_type, min_hours=0)
        return 0 if df is None else len(df)

    def load_equipment_type_dataframe(
        self,
        equipment_type: str,
        min_hours: int = 500,
        lookback_days: int = 365,
        delete_after_load: bool = False,
        model_type: str = "lstm",
        required_features: list[str] | None = None,
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
        feature_names, source_to_feature = self._feature_contract(equipment_type, model_type)
        if required_features is None:
            required_features = feature_names
        source_points = [source for source, feature in source_to_feature.items() if feature in set(required_features)]
        if not source_points:
            logger.warning("[DATA LOADER] No aggregate feature mapping for equipment type: %s", equipment_type)
            return None

        min_date = datetime.now(UTC) - timedelta(days=lookback_days)

        logger.info(
            "[DATA LOADER] Querying %s telemetry_hourly (site=%s, points=%s, since=%s)",
            equipment_type,
            self.site_id or "all",
            source_points,
            min_date.date(),
        )

        rows = self._query_hourly_aggregates(
            equipment_type=equipment_type,
            source_points=source_points,
            min_date=min_date,
        )

        if not rows:
            logger.warning("[DATA LOADER] No telemetry_hourly rows found for %s", equipment_type)
            return None

        logger.info("[DATA LOADER] Got %d aggregate rows for %s", len(rows), equipment_type)

        df = self._pivot_to_dataframe(rows, equipment_type, source_to_feature=source_to_feature)
        if df is None:
            return None

        logger.info("[DATA LOADER] Pivoted to %d hourly rows, columns: %s", len(df), list(df.columns))

        # Check all required features are present
        missing = [f for f in required_features if f not in df.columns]
        if missing:
            logger.warning(
                f"[DATA LOADER] Missing features for {equipment_type}: {missing}. "
                f"Available: {[c for c in df.columns if c != 'timestamp']}"
            )
            return None

        cleaned = df[["timestamp", *required_features]].copy()
        cleaned_features = cleaned[required_features].ffill(limit=3).dropna()
        df = cleaned.loc[cleaned_features.index].reset_index(drop=True)

        # Check we have enough feature-complete data
        if len(df) < min_hours:
            logger.warning(
                "[DATA LOADER] Insufficient data for %s: %d hours (need %d)", equipment_type, len(df), min_hours
            )
            return None

        if not df.empty:
            self.last_load_metadata = {
                "data_source": "telemetry_hourly",
                "site_id": self.site_id,
                "equipment_type": equipment_type,
                "model_type": model_type,
                "real_hours_available": len(df),
                "real_data_start": df["timestamp"].min().isoformat(),
                "real_data_end": df["timestamp"].max().isoformat(),
                "feature_columns": list(required_features),
            }

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
            model_type="autoencoder",
        )
        if df is None:
            return None

        features, _source_to_feature = self._feature_contract(equipment_type, "autoencoder")

        # Extract only the feature columns in the right order
        available = [f for f in features if f in df.columns]
        if len(available) < len(features):
            logger.warning(
                f"[DATA LOADER] Only {len(available)}/{len(features)} features available for {equipment_type}"
            )
            return None

        # Forward-fill small gaps (up to 3 hours) then drop remaining NaNs
        data = df[features].ffill(limit=3).dropna()

        if len(data) < min_hours:
            logger.warning(
                f"[DATA LOADER] After cleaning, only {len(data)} hours (need {min_hours}) for {equipment_type}"
            )
            return None

        return data.values

    def get_data_summary(self) -> dict[str, Any]:
        """Get a summary of available training data per equipment type."""
        summary = {}
        for eq_type in list_ml_trainable_types(self.site_id):
            hours = self.get_available_hours(eq_type)
            lstm_features = get_lstm_features(eq_type, self.site_id)
            ae_features = get_autoencoder_features(eq_type, self.site_id)
            target = (
                EquipmentDataLoader.get_config(eq_type).get("target")
                if eq_type in EquipmentDataLoader.SENSOR_CONFIGS
                else None
            )
            summary[eq_type] = {
                "available_hours": hours,
                "required_features": lstm_features,
                "autoencoder_features": ae_features,
                "target": target if target in lstm_features else (lstm_features[0] if lstm_features else None),
                "data_source": "telemetry_hourly",
                "site_id": self.site_id,
                "ready_for_lstm": hours >= 500,
                "ready_for_autoencoder": hours >= 200,
            }
        return summary
