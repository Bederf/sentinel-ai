"""Daily occupancy ML processing + raw retention deletion.

This implements the workflow:
1) At an off-hours time (e.g. 02:00 Johannesburg), process yesterday's
   occupancy events for each activated site.
2) Persist derived/ML-ready outputs into a dedicated long-lived table.
3) After a configurable grace period (e.g. 2 days), delete the raw
   `space_occupancy_events` rows for windows that were successfully processed.

At the moment, the "ML" step stores aggregate features (room-level
occupied minutes/percent and event counts). This keeps the pipeline
POPIA-minimization friendly while leaving room for plugging in an actual
occupancy ML model later.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.config.settings import settings
from app.core.site_resolver import get_registered_site_ids
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

TABLE_DAILY_OUTPUTS = "space_occupancy_daily_ml_outputs"


def _ensure_timezone() -> ZoneInfo:
    # Hard-code to match your operational requirement.
    return ZoneInfo("Africa/Johannesburg")


def _to_naive_utc(dt: datetime) -> datetime:
    # Convert to UTC and strip tzinfo for deterministic arithmetic.
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC)
    return dt.replace(tzinfo=None)


def _compute_yesterday_window_utc(now_utc: datetime) -> tuple[datetime, datetime, date]:
    tz = _ensure_timezone()
    now_local = now_utc.astimezone(tz)
    yesterday_local_date = now_local.date() - timedelta(days=1)
    start_local = datetime.combine(yesterday_local_date, datetime.min.time(), tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC), yesterday_local_date


@dataclass(frozen=True)
class DailyWindow:
    site_id: str
    window_start_utc: datetime
    window_end_utc: datetime
    window_local_date: date


def _try_ensure_daily_outputs_table(client: Any) -> None:
    """Best-effort table creation.

    Preferred: Supabase `exec_sql` RPC.
    Fallback: direct Postgres DDL via `settings.database_url`.
    """
    # Table is intentionally simple: one row per site per processed day window.
    # Use `id` as text primary key because we generate IDs in Python.
    sql = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_DAILY_OUTPUTS} (
      id TEXT PRIMARY KEY,
      site_id TEXT NOT NULL,
      window_start TIMESTAMPTZ NOT NULL,
      window_end TIMESTAMPTZ NOT NULL,
      window_local_date DATE NOT NULL,
      status TEXT NOT NULL DEFAULT 'success',
      processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      results JSONB NOT NULL DEFAULT '{{}}'::jsonb,
      raw_deleted BOOLEAN NOT NULL DEFAULT FALSE,
      raw_deleted_at TIMESTAMPTZ,
      last_error TEXT
    );
    CREATE UNIQUE INDEX IF NOT EXISTS {TABLE_DAILY_OUTPUTS}_site_window_unique
      ON {TABLE_DAILY_OUTPUTS}(site_id, window_start);
    """
    try:
        client.rpc("exec_sql", {"sql": sql}).execute()
        return
    except Exception as exc:
        # Many Supabase projects don't expose an `exec_sql` RPC.
        # If so, fall back to direct SQL using DATABASE_URL.
        logger.warning("Supabase exec_sql RPC missing/unavailable: %s", exc)

    try:
        import psycopg2

        if not settings.database_url:
            raise ValueError("settings.database_url is empty; cannot create tables via Postgres")

        conn = psycopg2.connect(settings.database_url)
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.error("Failed to ensure %s via fallback DDL: %s", TABLE_DAILY_OUTPUTS, exc)
        raise


def _get_edge_site_scope(site_ids: list[str]) -> list[str]:
    if not settings.edge_mode:
        return site_ids
    # Edge devices should only process the single activated site.
    if settings.space_default_site_id in site_ids:
        return [settings.space_default_site_id]
    # Fallback: still attempt the configured site (useful if registration lags).
    return [settings.space_default_site_id]


def _pg_connect():
    import psycopg2

    if not settings.database_url:
        raise ValueError("settings.database_url is empty")
    return psycopg2.connect(settings.database_url)


def _output_exists(site_id: str, window_start_iso: str) -> bool:
    conn = _pg_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT 1 FROM {TABLE_DAILY_OUTPUTS} WHERE site_id=%s AND window_start=%s LIMIT 1",
                (site_id, window_start_iso),
            )
            row = cur.fetchone()
            return bool(row)
    finally:
        conn.close()


def _output_insert(row: dict[str, Any]) -> None:
    import json

    conn = _pg_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE_DAILY_OUTPUTS}
                  (id, site_id, window_start, window_end, window_local_date, status, processed_at, results, raw_deleted)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                ON CONFLICT (site_id, window_start) DO NOTHING
                """,
                (
                    row["id"],
                    row["site_id"],
                    row["window_start"],
                    row["window_end"],
                    row["window_local_date"],
                    row["status"],
                    row["processed_at"],
                    json.dumps(row["results"]),
                    row["raw_deleted"],
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _output_candidates_for_deletion(site_id: str, cutoff_iso: str, limit: int = 10) -> list[dict[str, Any]]:
    conn = _pg_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, window_start::text, window_end::text
                FROM {TABLE_DAILY_OUTPUTS}
                WHERE site_id=%s
                  AND status='success'
                  AND raw_deleted=false
                  AND processed_at < %s
                ORDER BY processed_at ASC
                LIMIT %s
                """,
                (site_id, cutoff_iso, limit),
            )
            rows = cur.fetchall()
            return [{"id": r[0], "window_start": r[1], "window_end": r[2]} for r in rows]
    finally:
        conn.close()


def _output_mark_deleted(out_id: str, deleted_at_iso: str) -> None:
    conn = _pg_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {TABLE_DAILY_OUTPUTS} SET raw_deleted=true, raw_deleted_at=%s WHERE id=%s",
                (deleted_at_iso, out_id),
            )
        conn.commit()
    finally:
        conn.close()


def _compute_room_occupied_minutes(events: list[dict[str, Any]], window_end_utc: datetime) -> tuple[int, int]:
    """Return (occupied_minutes, empty_minutes) using simple transition logic.

    Assumes `events` are ordered by timestamp ascending and contain:
    - timestamp (ISO string)
    - occupied (bool)
    """
    if not events:
        return 0, 0

    total_seconds = 0.0
    occupied_seconds = 0.0

    # Use window_end and first event time as the effective start.
    # (We could extend precision by querying one event before the window,
    # but for the current POPIA minimization use-case this approximation is OK.)
    start_naive = _to_naive_utc(events[0]["_ts"])
    end_naive = _to_naive_utc(window_end_utc)
    total_seconds = (end_naive - start_naive).total_seconds()

    segment_start: datetime | None = None
    for e in events:
        et = e["_ts_naive"]
        if e.get("occupied", False) and segment_start is None:
            segment_start = et
        elif (not e.get("occupied", False)) and segment_start is not None:
            occupied_seconds += (et - segment_start).total_seconds()
            segment_start = None

    if segment_start is not None:
        occupied_seconds += (end_naive - segment_start).total_seconds()

    occupied_minutes = max(0, int(occupied_seconds / 60))
    # empty_minutes for completeness; may be slightly approximate.
    empty_minutes = max(0, int((total_seconds - occupied_seconds) / 60))
    return occupied_minutes, empty_minutes


def _aggregate_window(site_events: list[dict[str, Any]], window_end_utc: datetime) -> dict[str, Any]:
    by_room: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in site_events:
        # Normalize timestamps for arithmetic.
        ts_str = e.get("timestamp")
        if not ts_str:
            continue
        try:
            # Support timestamps like 2026-03-25T14:32:55+00:00
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        e["_ts"] = ts
        e["_ts_naive"] = _to_naive_utc(ts)
        by_room[str(e.get("room_code", ""))].append(e)

    results_rooms: list[dict[str, Any]] = []
    for room_code, room_events in by_room.items():
        room_events.sort(key=lambda r: r["_ts_naive"])
        occupied_minutes, empty_minutes = _compute_room_occupied_minutes(room_events, window_end_utc)

        total_minutes = occupied_minutes + empty_minutes
        occupied_percent = round((occupied_minutes / total_minutes * 100.0) if total_minutes else 0.0, 2)

        results_rooms.append(
            {
                "room_code": room_code,
                "events_count": len(room_events),
                "occupied_minutes": occupied_minutes,
                "empty_minutes": empty_minutes,
                "occupied_percent": occupied_percent,
            }
        )

    return {
        "window": {
            "end_utc": window_end_utc.isoformat(),
        },
        "rooms": results_rooms,
        "rooms_total": len(results_rooms),
    }


async def run_daily_occupancy_processing(*, grace_days: int) -> None:
    client = get_supabase_client()
    _try_ensure_daily_outputs_table(client)

    now_utc = datetime.now(UTC)
    window_start_utc, window_end_utc, window_local_date = _compute_yesterday_window_utc(now_utc)

    all_sites = get_registered_site_ids()
    sites = _get_edge_site_scope(all_sites)
    if not sites:
        logger.info("Daily occupancy ML processing: no sites to process")
        return

    for site_id in sites:
        window = DailyWindow(
            site_id=site_id,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            window_local_date=window_local_date,
        )
        await _process_and_maybe_delete_for_site(
            client=client,
            window=window,
            processed_at=now_utc,
            grace_days=grace_days,
        )


async def _process_and_maybe_delete_for_site(
    *,
    client: Any,
    window: DailyWindow,
    processed_at: datetime,
    grace_days: int,
) -> None:
    # Idempotency: if the site+window is already processed, don't re-run.
    if _output_exists(window.site_id, window.window_start_utc.isoformat()):
        return

    # Pull raw events for the window.
    resp = (
        client.table("space_occupancy_events")
        .select("room_code,timestamp,occupied")
        .eq("site_id", window.site_id)
        .gte("timestamp", window.window_start_utc.isoformat())
        .lt("timestamp", window.window_end_utc.isoformat())
        .execute()
    )
    events = resp.data or []

    # Aggregate.
    results = _aggregate_window(events, window.window_end_utc)

    row = {
        "id": str(uuid4()),
        "site_id": window.site_id,
        "window_start": window.window_start_utc.isoformat(),
        "window_end": window.window_end_utc.isoformat(),
        "window_local_date": str(window.window_local_date),
        "status": "success",
        "processed_at": processed_at.isoformat(),
        "results": results,
        "raw_deleted": False,
    }
    _output_insert(row)

    # Grace deletion: delete raw windows that were processed > grace_days ago.
    await _delete_raw_windows_eligible(
        client=client,
        site_id=window.site_id,
        cutoff_processed_at=processed_at - timedelta(days=grace_days),
    )


async def _delete_raw_windows_eligible(
    *,
    client: Any,
    site_id: str,
    cutoff_processed_at: datetime,
) -> None:
    cutoff_iso = cutoff_processed_at.isoformat()
    rows = _output_candidates_for_deletion(site_id, cutoff_iso, limit=10)
    if not rows:
        return

    now_utc = datetime.now(UTC)
    for row in rows:
        start_iso = row.get("window_start")
        end_iso = row.get("window_end")
        out_id = row.get("id")
        if not start_iso or not end_iso or not out_id:
            continue

        # Delete raw occupancy events for that processed window.
        client.table("space_occupancy_events").delete().eq("site_id", site_id).gte("timestamp", start_iso).lt(
            "timestamp", end_iso
        ).execute()

        # Mark deletion complete to prevent repeated deletes.
        _output_mark_deleted(out_id, now_utc.isoformat())

        logger.info("Deleted raw occupancy events for %s window [%s, %s)", site_id, start_iso, end_iso)
