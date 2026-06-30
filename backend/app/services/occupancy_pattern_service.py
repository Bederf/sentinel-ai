"""
Occupancy Pattern Service

Learns building arrival/departure times per day-of-week from historical
telemetry. Enables predictive recommendations:

  - HVAC pre-conditioning: start N minutes before first expected arrival
  - Lighting schedule audit: flag lights still on past last expected departure
  - Any time-based control that should align with actual occupancy patterns

The service is the building's "security guard who notices patterns" —
it observes what actually happens (HVAC off every morning, lights on every
night) and surfaces recommendations to change schedules accordingly.

Signal sources (in priority order):
  1. co2_ppm > 550 — reliable 08:00-18:00 signal, 11+ days history
  2. A_Occupancy / B_Occupancy / Occupancy (DALI PIR) > 0.5 — binary, sparse

Timezone: Africa/Johannesburg (UTC+2 = SAST)
DOW convention: PostgreSQL — 0=Sunday, 1=Monday ... 6=Saturday
"""

from __future__ import annotations

import logging
from datetime import datetime, UTC
from typing import Any

import psycopg2
import psycopg2.extras

from app.config.settings import settings

logger = logging.getLogger(__name__)

# CO2 rises above baseline (~415 ppm) once people arrive; 550 splits night
# baseline (415-462) from first-arrival signal (hour 7 avg 559, hour 8 avg 732).
CO2_OCCUPIED_THRESHOLD = 550

# Business hours window (local): avoid midnight sensor glitches.
BUSINESS_HOUR_START = 5  # 05:00 local
BUSINESS_HOUR_END = 22  # 22:00 local

# Minimum occupied readings on a day to treat it as a real workday.
MIN_OCCUPIED_READINGS = 10

# Minimum sample days per DOW before a percentile is considered reliable.
# Set to 2 so patterns build from the first two weeks of data; confidence
# score (sample_count / CONFIDENCE_FULL_AT) communicates reliability.
MIN_SAMPLE_DAYS = 2

# Full confidence at this many sample days.
CONFIDENCE_FULL_AT = 10

# Thermal lead-time model constants.
# Minutes per °C deficit (how long HVAC needs per degree of temp recovery).
LEAD_TIME_MIN_PER_DEG = 5.0
# Additional minutes per °C below 16 °C outdoor (cold weather slows recovery).
COLD_BOOST_MIN_PER_DEG = 2.0
LEAD_TIME_MIN_FLOOR = 15
LEAD_TIME_MIN_CAP = 120

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS site_occupancy_patterns (
    id          SERIAL PRIMARY KEY,
    site_id     TEXT    NOT NULL,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    first_arrival_p05_mins  INTEGER,
    first_arrival_p50_mins  INTEGER,
    last_departure_p95_mins INTEGER,
    sample_count INTEGER NOT NULL DEFAULT 0,
    confidence   FLOAT   NOT NULL DEFAULT 0.0,
    signals      TEXT[]  NOT NULL DEFAULT '{}',
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (site_id, day_of_week)
);
CREATE INDEX IF NOT EXISTS idx_site_occ_patterns_site
    ON site_occupancy_patterns (site_id);
"""

_EXTRACT_SQL = """
WITH occupied_readings AS (
    SELECT
        recorded_at AT TIME ZONE 'Africa/Johannesburg' AS local_ts,
        CASE
            WHEN sensor_type = 'co2_ppm' THEN value::numeric > %(co2_thresh)s
            ELSE value::numeric > 0.5
        END AS is_occupied,
        sensor_type
    FROM equipment_sensor_readings
    WHERE site_id = %(site_id)s
      AND sensor_type IN ('co2_ppm', 'A_Occupancy', 'B_Occupancy', 'Occupancy')
      AND recorded_at >= NOW() - (%(lookback_days)s || ' days')::INTERVAL
      AND EXTRACT(HOUR FROM recorded_at AT TIME ZONE 'Africa/Johannesburg')
              BETWEEN %(hour_start)s AND %(hour_end)s
),
daily_bounds AS (
    SELECT
        DATE(local_ts)                          AS local_date,
        EXTRACT(DOW FROM local_ts)::int         AS dow,
        MIN(CASE WHEN is_occupied THEN local_ts END) AS first_occupied_ts,
        MAX(CASE WHEN is_occupied THEN local_ts END) AS last_occupied_ts,
        COUNT(CASE WHEN is_occupied THEN 1 END) AS occupied_count,
        array_agg(DISTINCT sensor_type)
            FILTER (WHERE is_occupied)          AS contributing_signals
    FROM occupied_readings
    GROUP BY local_date, dow
    HAVING COUNT(CASE WHEN is_occupied THEN 1 END) >= %(min_readings)s
),
daily_minutes AS (
    SELECT
        dow,
        local_date,
        (EXTRACT(HOUR FROM first_occupied_ts) * 60
            + EXTRACT(MINUTE FROM first_occupied_ts))::int AS first_arrival_mins,
        (EXTRACT(HOUR FROM last_occupied_ts) * 60
            + EXTRACT(MINUTE FROM last_occupied_ts))::int  AS last_departure_mins,
        contributing_signals
    FROM daily_bounds
    WHERE first_occupied_ts IS NOT NULL
),
dow_stats AS (
    SELECT
        dow,
        PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY first_arrival_mins)  AS p05_arrival,
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY first_arrival_mins)  AS p50_arrival,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY last_departure_mins) AS p95_departure,
        COUNT(*)                                                           AS sample_count
    FROM daily_minutes
    GROUP BY dow
    HAVING COUNT(*) >= %(min_samples)s
),
dow_signals AS (
    SELECT dm.dow,
           array_agg(DISTINCT sig) FILTER (WHERE sig IS NOT NULL) AS signals
    FROM daily_minutes dm,
         LATERAL UNNEST(dm.contributing_signals) AS sig
    GROUP BY dm.dow
)
SELECT s.dow, s.p05_arrival, s.p50_arrival, s.p95_departure, s.sample_count,
       sg.signals
FROM dow_stats s
JOIN dow_signals sg ON sg.dow = s.dow
ORDER BY s.dow
"""


class OccupancyPatternService:
    """Learns and exposes building occupancy timing patterns per DOW."""

    def __init__(self) -> None:
        self._conn_str = settings.database_url

    # ------------------------------------------------------------------
    # Table bootstrap
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        with psycopg2.connect(self._conn_str) as conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_TABLE_SQL)
            conn.commit()

    # ------------------------------------------------------------------
    # Pattern extraction
    # ------------------------------------------------------------------

    def extract_patterns(
        self,
        site_id: str,
        lookback_days: int = 60,
    ) -> dict[int, dict[str, Any]]:
        """Mine historical telemetry and persist arrival/departure patterns.

        Returns a dict keyed by day_of_week (0=Sun … 6=Sat):
          {
            0: {"first_arrival_p05_mins": 480, "first_arrival_p50_mins": 495,
                "last_departure_p95_mins": 1080, "sample_count": 8,
                "confidence": 0.8, "signals": ["co2_ppm"]},
            ...
          }
        Days with fewer than MIN_SAMPLE_DAYS samples are excluded.
        """
        self._ensure_table()

        params = {
            "site_id": site_id,
            "lookback_days": lookback_days,
            "co2_thresh": CO2_OCCUPIED_THRESHOLD,
            "hour_start": BUSINESS_HOUR_START,
            "hour_end": BUSINESS_HOUR_END,
            "min_readings": MIN_OCCUPIED_READINGS,
            "min_samples": MIN_SAMPLE_DAYS,
        }

        rows: list[dict[str, Any]] = []
        try:
            with psycopg2.connect(self._conn_str) as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                    cur.execute(_EXTRACT_SQL, params)
                    rows = [dict(r) for r in cur.fetchall()]
        except Exception:
            logger.exception("[OccupancyPattern] SQL extract failed for %s", site_id)
            return {}

        if not rows:
            logger.info(
                "[OccupancyPattern] No pattern data for %s (lookback=%dd, min_samples=%d)",
                site_id,
                lookback_days,
                MIN_SAMPLE_DAYS,
            )
            return {}

        results: dict[int, dict[str, Any]] = {}
        upsert_rows: list[dict[str, Any]] = []

        for row in rows:
            dow = int(row["dow"])
            sample_count = int(row["sample_count"])
            confidence = min(1.0, sample_count / CONFIDENCE_FULL_AT)
            signals = list(row["signals"] or [])

            p05 = int(row["p05_arrival"]) if row["p05_arrival"] is not None else None
            p50 = int(row["p50_arrival"]) if row["p50_arrival"] is not None else None
            p95 = int(row["p95_departure"]) if row["p95_departure"] is not None else None

            pattern = {
                "day_of_week": dow,
                "first_arrival_p05_mins": p05,
                "first_arrival_p50_mins": p50,
                "last_departure_p95_mins": p95,
                "sample_count": sample_count,
                "confidence": round(confidence, 2),
                "signals": signals,
            }
            results[dow] = pattern

            upsert_rows.append(
                {
                    "site_id": site_id,
                    "day_of_week": dow,
                    "first_arrival_p05_mins": p05,
                    "first_arrival_p50_mins": p50,
                    "last_departure_p95_mins": p95,
                    "sample_count": sample_count,
                    "confidence": round(confidence, 2),
                    "signals": signals,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            )

        self._upsert_patterns(upsert_rows)
        logger.info(
            "[OccupancyPattern] %s: extracted patterns for %d day(s): %s",
            site_id,
            len(results),
            sorted(results.keys()),
        )
        return results

    def _upsert_patterns(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        sql = """
        INSERT INTO site_occupancy_patterns
            (site_id, day_of_week, first_arrival_p05_mins, first_arrival_p50_mins,
             last_departure_p95_mins, sample_count, confidence, signals, updated_at)
        VALUES
            (%(site_id)s, %(day_of_week)s, %(first_arrival_p05_mins)s,
             %(first_arrival_p50_mins)s, %(last_departure_p95_mins)s,
             %(sample_count)s, %(confidence)s, %(signals)s, %(updated_at)s)
        ON CONFLICT (site_id, day_of_week) DO UPDATE SET
            first_arrival_p05_mins  = EXCLUDED.first_arrival_p05_mins,
            first_arrival_p50_mins  = EXCLUDED.first_arrival_p50_mins,
            last_departure_p95_mins = EXCLUDED.last_departure_p95_mins,
            sample_count            = EXCLUDED.sample_count,
            confidence              = EXCLUDED.confidence,
            signals                 = EXCLUDED.signals,
            updated_at              = EXCLUDED.updated_at
        """
        try:
            with psycopg2.connect(self._conn_str) as conn:
                with conn.cursor() as cur:
                    psycopg2.extras.execute_batch(cur, sql, rows)
                conn.commit()
        except Exception:
            logger.exception("[OccupancyPattern] Failed to upsert patterns")

    # ------------------------------------------------------------------
    # Pattern retrieval
    # ------------------------------------------------------------------

    def get_patterns(self, site_id: str) -> dict[int, dict[str, Any]]:
        """Return stored patterns for a site keyed by DOW (0=Sun…6=Sat)."""
        sql = """
        SELECT day_of_week, first_arrival_p05_mins, first_arrival_p50_mins,
               last_departure_p95_mins, sample_count, confidence, signals, updated_at
        FROM site_occupancy_patterns
        WHERE site_id = %s
        ORDER BY day_of_week
        """
        try:
            with psycopg2.connect(self._conn_str) as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                    cur.execute(sql, (site_id,))
                    return {
                        row["day_of_week"]: {
                            "day_of_week": row["day_of_week"],
                            "first_arrival_p05_mins": row["first_arrival_p05_mins"],
                            "first_arrival_p50_mins": row["first_arrival_p50_mins"],
                            "last_departure_p95_mins": row["last_departure_p95_mins"],
                            "sample_count": row["sample_count"],
                            "confidence": row["confidence"],
                            "signals": list(row["signals"] or []),
                            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                        }
                        for row in cur.fetchall()
                    }
        except Exception:
            logger.exception("[OccupancyPattern] Failed to fetch patterns for %s", site_id)
            return {}

    # ------------------------------------------------------------------
    # Pre-conditioning start time
    # ------------------------------------------------------------------

    def get_pre_condition_start_time(
        self,
        site_id: str,
        target_weekday: int,
        outdoor_temp_c: float,
        setpoint_c: float,
        current_indoor_temp_c: float,
    ) -> dict[str, Any] | None:
        """Compute when HVAC should start to reach setpoint before first arrival.

        Args:
            site_id:              Site identifier.
            target_weekday:       PostgreSQL DOW (0=Sun, 1=Mon … 6=Sat).
            outdoor_temp_c:       Current outdoor temperature.
            setpoint_c:           Target indoor setpoint.
            current_indoor_temp_c: Current indoor temperature.

        Returns:
            Dict with:
              - pre_condition_start_mins: minutes since midnight (local)
              - first_arrival_p05_mins: the target arrival time used
              - lead_time_mins: computed thermal lead time
              - confidence: pattern confidence (0-1)
            Or None if no pattern exists for the given day.
        """
        patterns = self.get_patterns(site_id)
        pattern = patterns.get(target_weekday)
        if not pattern or pattern.get("first_arrival_p05_mins") is None:
            return None

        p05 = pattern["first_arrival_p05_mins"]

        temp_delta = max(0.0, setpoint_c - current_indoor_temp_c)
        cold_boost = max(0.0, 16.0 - outdoor_temp_c) * COLD_BOOST_MIN_PER_DEG
        lead_time = min(
            LEAD_TIME_MIN_CAP,
            max(LEAD_TIME_MIN_FLOOR, temp_delta * LEAD_TIME_MIN_PER_DEG + cold_boost),
        )

        start_mins = max(0, p05 - int(lead_time))

        return {
            "pre_condition_start_mins": start_mins,
            "first_arrival_p05_mins": p05,
            "lead_time_mins": int(lead_time),
            "confidence": pattern["confidence"],
            "sample_count": pattern["sample_count"],
        }

    def get_lighting_schedule_audit(
        self,
        site_id: str,
        target_weekday: int,
    ) -> dict[str, Any] | None:
        """Return expected last-departure time for lighting schedule review.

        Used to detect when lights are on past the typical last departure —
        the same "security guard" pattern applied to lighting.

        Returns:
            Dict with last_departure_p95_mins, confidence, sample_count.
            None if no pattern for this DOW.
        """
        patterns = self.get_patterns(site_id)
        pattern = patterns.get(target_weekday)
        if not pattern or pattern.get("last_departure_p95_mins") is None:
            return None

        return {
            "last_departure_p95_mins": pattern["last_departure_p95_mins"],
            "lights_off_suggested_mins": pattern["last_departure_p95_mins"] + 30,
            "confidence": pattern["confidence"],
            "sample_count": pattern["sample_count"],
        }


# Singleton
_service: OccupancyPatternService | None = None


def get_occupancy_pattern_service() -> OccupancyPatternService:
    global _service
    if _service is None:
        _service = OccupancyPatternService()
    return _service
