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

# Fallback occupancy heuristic and shared holiday calendar — single definitions,
# must not diverge from drift detection's. The primary occupancy source is the
# site's configured operating hours (onboarding wizard / settings page).
from ml.monitoring.drift import _get_occupancy_mode, _is_sa_holiday

logger = logging.getLogger(__name__)

# Variance gate — a required feature whose training column is (near-)constant
# carries no learnable signal (pinned sensor, dead point alias, bridge default);
# training on it bakes that flatline into the model's "normal". Block, not warn.
MIN_FEATURE_DISTINCT_VALUES = 2
MIN_FEATURE_CV = 1e-4  # std/|mean| floor for non-zero-mean features
FFILL_LIMIT_HOURS = 3

# Temporal pinning — a channel can pass the global variance floor while being
# flat most of the time (dead point that occasionally bursts, sensor saturating
# for whole days). Evaluated per calendar day; legitimate steady state (plant
# off over a weekend ≈ 2/7 flat days) must pass, so only a majority of
# degenerate windows blocks.
MIN_EVALUABLE_WINDOW_HOURS = 6
MAX_DEGENERATE_WINDOW_FRACTION = 0.5
# Occupied-hours segments use a stricter floor: shadow-mode learning defines the
# baseline "normal", so a channel dead through a third of business days is
# block-worthy at learning time even where it would only be noise-worthy in
# production monitoring.
MAX_DEGENERATE_OCCUPIED_WINDOW_FRACTION = 0.3


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

    def _load_site_operating_hours(self) -> dict | None:
        """Operating hours configured at onboarding (wizard / settings page).

        Reads sites.operating_hours, e.g. {"weekday": "07:00-18:00", "weekend": "closed"}.
        Returns None when unset or unavailable (callers fall back to the heuristic).
        """
        if not self.site_id:
            return None
        database_url = self._database_url()
        if not database_url:
            return None
        try:
            import psycopg2

            conn = psycopg2.connect(database_url)
            try:
                cur = conn.cursor()
                cur.execute("SELECT operating_hours FROM sites WHERE code = %s", (self.site_id,))
                row = cur.fetchone()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("[DATA LOADER] Could not load operating hours for %s: %s", self.site_id, e)
            return None
        hours = row[0] if row else None
        if isinstance(hours, str):
            try:
                import json

                hours = json.loads(hours)
            except ValueError:
                return None
        return hours if isinstance(hours, dict) and hours else None

    @staticmethod
    def _parse_hours_window(window: Any) -> tuple[int, int] | None:
        """'07:00-18:00' -> (7, 18); '00:00-24:00' -> (0, 24); 'closed'/None/invalid -> None."""
        if not isinstance(window, str) or "-" not in window:
            return None
        try:
            start_s, end_s = window.split("-", 1)
            return int(start_s.split(":")[0]), int(end_s.split(":")[0])
        except ValueError:
            return None

    def _occupied_predicate(self) -> tuple[Any, str]:
        """Return (ts -> occupied bool, source description).

        Site-configured operating hours take priority — a hospital's 24/7 wards
        or a mall's weekend trading must not inherit the office heuristic. The
        shared drift heuristic is only the fallback. Hours are interpreted in
        SAST (UTC+2), matching the heuristic; holidays use the shared dynamic
        calendar and fall under the weekend window.
        """
        hours = self._load_site_operating_hours()
        if not hours:
            if self.site_id:
                logger.warning(
                    "[DATA LOADER] %s has no operating_hours configured (wizard/settings) — "
                    "occupied-hours variance gate falling back to office heuristic; "
                    "wrong for 24/7 or non-office sites",
                    self.site_id,
                )
            return (lambda ts: _get_occupancy_mode(ts) == "occupied"), "heuristic weekday 06:00-22:00 SAST"

        weekday_window = self._parse_hours_window(hours.get("weekday"))
        weekend_window = self._parse_hours_window(hours.get("weekend"))

        def occupied(ts) -> bool:
            sa_hour = (ts.hour + 2) % 24
            window = weekend_window if (ts.weekday() >= 5 or _is_sa_holiday(ts.date())) else weekday_window
            if window is None:
                return False
            start_h, end_h = window
            if start_h == end_h:
                return False
            if end_h < start_h:  # overnight window, e.g. 22:00-06:00
                return sa_hour >= start_h or sa_hour < end_h
            return start_h <= sa_hour < end_h

        return occupied, f"sites.operating_hours {hours} (SAST)"

    @staticmethod
    def _is_degenerate_series(col: pd.Series) -> bool:
        """Constant, or so close to constant that std/|mean| falls below MIN_FEATURE_CV."""
        mean = float(col.mean())
        std = float(col.std()) if len(col) > 1 else 0.0
        if np.isnan(std):
            std = 0.0
        cv = (std / abs(mean)) if abs(mean) > 1e-9 else (float("inf") if std > 0 else 0.0)
        return int(col.nunique()) < MIN_FEATURE_DISTINCT_VALUES or cv < MIN_FEATURE_CV

    def _feature_variance_stats(
        self,
        df: pd.DataFrame,
        required_features: list[str],
        timestamp_col: str = "timestamp",
    ) -> tuple[list[str], dict[str, dict[str, Any]], str | None]:
        """Per-feature variance floor plus a stats snapshot for provenance.

        Three failure modes block:
        - constant/near-constant over the whole load (pinned sensor, dead alias)
        - temporally pinned: passes the global floor but degenerate in most
          per-day windows (dead point with occasional real bursts)
        - occupied-hours pinned: full-day windows pass (night-time variation)
          but the channel is flat through most occupied-hours segments —
          legitimate flatness (night setback, weekend shutdown) is unoccupied
          by definition and never counts against a feature
        """
        day = df[timestamp_col].dt.floor("D") if timestamp_col in df.columns else None
        occupied_mask = None
        occupancy_source: str | None = None
        if day is not None:
            occupied_fn, occupancy_source = self._occupied_predicate()
            occupied_mask = df[timestamp_col].map(occupied_fn)
        degenerate: list[str] = []
        stats: dict[str, dict[str, Any]] = {}
        for feature in required_features:
            col = df[feature].astype(float)
            mean = float(col.mean())
            std = float(col.std()) if len(col) > 1 else 0.0
            if np.isnan(std):
                std = 0.0
            distinct = int(col.nunique())
            globally_degenerate = self._is_degenerate_series(col)

            # Longest run of consecutive identical values (hourly rows ≈ hours)
            runs = col.groupby((col != col.shift()).cumsum()).size()
            longest_flat_run = int(runs.max()) if len(runs) else 0

            windows_evaluated = 0
            windows_degenerate = 0
            if day is not None:
                for _, window_col in col.groupby(day):
                    if len(window_col) < MIN_EVALUABLE_WINDOW_HOURS:
                        continue
                    windows_evaluated += 1
                    if self._is_degenerate_series(window_col):
                        windows_degenerate += 1
            window_fraction = (windows_degenerate / windows_evaluated) if windows_evaluated else 0.0
            temporally_pinned = (
                not globally_degenerate and windows_evaluated > 0 and window_fraction > MAX_DEGENERATE_WINDOW_FRACTION
            )

            occ_windows_evaluated = 0
            occ_windows_degenerate = 0
            longest_occ_flat_run = 0
            if occupied_mask is not None and occupied_mask.any():
                assert day is not None  # occupied_mask is only set when timestamp_col present, so is day
                occ_col = col[occupied_mask]
                occ_runs = occ_col.groupby((occ_col != occ_col.shift()).cumsum()).size()
                longest_occ_flat_run = int(occ_runs.max()) if len(occ_runs) else 0
                for _, segment in occ_col.groupby(day[occupied_mask]):
                    if len(segment) < MIN_EVALUABLE_WINDOW_HOURS:
                        continue
                    occ_windows_evaluated += 1
                    if self._is_degenerate_series(segment):
                        occ_windows_degenerate += 1
            occ_window_fraction = (occ_windows_degenerate / occ_windows_evaluated) if occ_windows_evaluated else 0.0
            occupied_hours_pinned = (
                not globally_degenerate
                and not temporally_pinned
                and occ_windows_evaluated > 0
                and occ_window_fraction > MAX_DEGENERATE_OCCUPIED_WINDOW_FRACTION
            )

            is_degenerate = globally_degenerate or temporally_pinned or occupied_hours_pinned
            stats[feature] = {
                "mean": round(mean, 6),
                "std": round(std, 6),
                "min": round(float(col.min()), 6),
                "max": round(float(col.max()), 6),
                "distinct_values": distinct,
                "longest_flat_run_hours": longest_flat_run,
                "windows_evaluated": windows_evaluated,
                "degenerate_window_fraction": round(window_fraction, 3),
                "occupied_windows_evaluated": occ_windows_evaluated,
                "degenerate_occupied_window_fraction": round(occ_window_fraction, 3),
                "longest_occupied_flat_run_hours": longest_occ_flat_run,
                "degenerate": is_degenerate,
                "degenerate_reason": (
                    "constant_or_near_constant"
                    if globally_degenerate
                    else (
                        "temporally_pinned"
                        if temporally_pinned
                        else ("occupied_hours_pinned" if occupied_hours_pinned else None)
                    )
                ),
            }
            if is_degenerate:
                degenerate.append(feature)
        return degenerate, stats, occupancy_source

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
        pre_fill = cleaned[required_features]
        cleaned_features = pre_fill.ffill(limit=FFILL_LIMIT_HOURS).dropna()
        # Cells that were NaN before the fill in surviving rows are the
        # forward-filled ones — provenance, per feature.
        forward_filled = pre_fill.loc[cleaned_features.index].isna().sum()
        df = cleaned.loc[cleaned_features.index].copy()
        df[required_features] = cleaned_features
        df = df.reset_index(drop=True)

        # Check we have enough feature-complete data
        if len(df) < min_hours:
            logger.warning(
                "[DATA LOADER] Insufficient data for %s: %d hours (need %d)", equipment_type, len(df), min_hours
            )
            return None

        if df.empty:
            return df

        degenerate_features, feature_stats, occupancy_source = self._feature_variance_stats(df, required_features)

        self.last_load_metadata = {
            "data_source": "telemetry_hourly",
            "site_id": self.site_id,
            "equipment_type": equipment_type,
            "model_type": model_type,
            "real_hours_available": len(df),
            "real_data_start": df["timestamp"].min().isoformat(),
            "real_data_end": df["timestamp"].max().isoformat(),
            "feature_columns": list(required_features),
            "forward_fill_limit_hours": FFILL_LIMIT_HOURS,
            "forward_filled_cells": {feature: int(count) for feature, count in forward_filled.items()},
            "forward_filled_cells_total": int(forward_filled.sum()),
            "feature_stats": feature_stats,
            "variance_gate": {
                "passed": not degenerate_features,
                "degenerate_features": degenerate_features,
                "min_distinct_values": MIN_FEATURE_DISTINCT_VALUES,
                "min_cv": MIN_FEATURE_CV,
                "window": "1 day",
                "min_evaluable_window_hours": MIN_EVALUABLE_WINDOW_HOURS,
                "max_degenerate_window_fraction": MAX_DEGENERATE_WINDOW_FRACTION,
                "max_degenerate_occupied_window_fraction": MAX_DEGENERATE_OCCUPIED_WINDOW_FRACTION,
                "occupancy_source": occupancy_source,
            },
        }

        if degenerate_features:
            logger.error(
                "[DATA LOADER] Variance gate blocked %s/%s training for %s: degenerate features %s — "
                "pinned or dead points carry no learnable signal",
                equipment_type,
                model_type,
                self.site_id or "all sites",
                degenerate_features,
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

        # Forward-fill small gaps (up to FFILL_LIMIT_HOURS) then drop remaining NaNs
        data = df[features].ffill(limit=FFILL_LIMIT_HOURS).dropna()

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
