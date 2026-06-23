"""Telemetry tiered aggregation service.

Tier 1 -> Tier 2: Aggregate equipment_sensor_readings into telemetry_hourly.
                  Run nightly. Processes readings older than 24h not yet aggregated.
Tier 2 -> Tier 3: Aggregate telemetry_hourly into telemetry_daily.
                  Run weekly. Processes hours older than 7 days not yet aggregated.

After aggregation completes, raw rows within the aggregated window are eligible
for deletion by SupabaseRetentionService (10-day operational window).
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Any

logger = logging.getLogger(__name__)


class TelemetryAggregationService:
    """Aggregate raw telemetry into hourly/daily buckets using direct SQL."""

    def __init__(self) -> None:
        self._db_url: str = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@127.0.0.1:55322/postgres",
        )

    def _get_connection(self):
        import psycopg2

        conn = psycopg2.connect(self._db_url)
        conn.autocommit = True
        return conn

    def aggregate_tier1_to_tier2(self, site_id: str | None = None) -> dict[str, Any]:
        """Aggregate raw sensor readings into telemetry_hourly.

        Processes rows older than 24h. Uses INSERT ... ON CONFLICT DO NOTHING
        so repeated runs are idempotent.

        Args:
            site_id: Optional site filter (e.g. "site-002"). If None, processes all sites.

        Returns:
            dict with rows_processed, rows_written, errors
        """
        result: dict[str, Any] = {"rows_processed": 0, "rows_written": 0, "errors": []}

        try:
            conn = self._get_connection()
            cur = conn.cursor()

            site_filter = ""
            params: list[Any] = [timedelta(hours=24)]
            if site_id:
                site_filter = "AND site_id = %s"
                params.append(site_id)

            cur.execute(
                f"""
                INSERT INTO telemetry_hourly
                    (site_id, equipment_id, point_name, hour_bucket,
                     value_min, value_max, value_avg, value_count, unit)
                SELECT
                    site_id,
                    equipment_id,
                    sensor_type AS point_name,
                    date_trunc('hour', recorded_at) AS hour_bucket,
                    MIN(value) AS value_min,
                    MAX(value) AS value_max,
                    AVG(value) AS value_avg,
                    COUNT(*) AS value_count,
                    mode() WITHIN GROUP (ORDER BY unit) AS unit
                FROM equipment_sensor_readings
                WHERE recorded_at < NOW() - %s
                {site_filter}
                GROUP BY site_id, equipment_id, sensor_type, date_trunc('hour', recorded_at)
                ON CONFLICT (site_id, equipment_id, point_name, hour_bucket) DO NOTHING
                """,
                params,
            )
            result["rows_processed"] = cur.rowcount if cur.rowcount > 0 else 0
            result["rows_written"] = cur.rowcount if cur.rowcount > 0 else 0

            cur.close()
            conn.close()

            logger.info(
                "[TIER1->TIER2] Aggregated %s rows into telemetry_hourly (site=%s)",
                result["rows_written"],
                site_id or "all",
            )
        except Exception as e:
            logger.error("[TIER1->TIER2] Aggregation failed: %s", e, exc_info=True)
            result["errors"].append(str(e))

        return result

    def aggregate_tier2_to_tier3(self, site_id: str | None = None) -> dict[str, Any]:
        """Aggregate telemetry_hourly into telemetry_daily.

        Processes hours older than 7 days. Idempotent via ON CONFLICT DO NOTHING.

        Args:
            site_id: Optional site filter. If None, processes all sites.

        Returns:
            dict with rows_processed, rows_written, errors
        """
        result: dict[str, Any] = {"rows_processed": 0, "rows_written": 0, "errors": []}

        try:
            conn = self._get_connection()
            cur = conn.cursor()

            site_filter = ""
            params: list[Any] = [timedelta(days=7)]
            if site_id:
                site_filter = "AND site_id = %s"
                params.append(site_id)

            cur.execute(
                f"""
                INSERT INTO telemetry_daily
                    (site_id, equipment_id, point_name, day_bucket,
                     value_min, value_max, value_avg, value_count, unit)
                SELECT
                    site_id,
                    equipment_id,
                    point_name,
                    hour_bucket::date AS day_bucket,
                    MIN(value_min) AS value_min,
                    MAX(value_max) AS value_max,
                    AVG(value_avg) AS value_avg,
                    SUM(value_count) AS value_count,
                    mode() WITHIN GROUP (ORDER BY unit) AS unit
                FROM telemetry_hourly
                WHERE hour_bucket < NOW() - %s
                {site_filter}
                GROUP BY site_id, equipment_id, point_name, hour_bucket::date
                ON CONFLICT (site_id, equipment_id, point_name, day_bucket) DO NOTHING
                """,
                params,
            )
            result["rows_processed"] = cur.rowcount if cur.rowcount > 0 else 0
            result["rows_written"] = cur.rowcount if cur.rowcount > 0 else 0

            cur.close()
            conn.close()

            logger.info(
                "[TIER2->TIER3] Aggregated %s rows into telemetry_daily (site=%s)",
                result["rows_written"],
                site_id or "all",
            )
        except Exception as e:
            logger.error("[TIER2->TIER3] Aggregation failed: %s", e, exc_info=True)
            result["errors"].append(str(e))

        return result


def get_telemetry_aggregation_service() -> TelemetryAggregationService:
    """Build telemetry aggregation service instance."""
    return TelemetryAggregationService()
