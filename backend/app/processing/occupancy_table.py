"""Occupancy event tabular processing.

Owns the room-level aggregation of raw occupancy events into occupied/empty
minutes and occupancy-percent features.

Polars adoption path
--------------------
``aggregate_window()`` does a group-by-room + sort + state-machine scan.
The state machine over ordered events is the most natural target — replace
the Python loop in ``compute_room_occupied_minutes()`` with a Polars
``shift``/``cumsum`` expression once the data lands in a DataFrame.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any


def _to_naive_utc(dt: datetime) -> datetime:
    """Convert to UTC and strip tzinfo for deterministic arithmetic."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC)
    return dt.replace(tzinfo=None)


def compute_room_occupied_minutes(
    events: list[dict[str, Any]],
    window_end_utc: datetime,
) -> tuple[int, int]:
    """Return (occupied_minutes, empty_minutes) for one room's events.

    Args:
        events:          Ordered-ascending rows for a single room.
                         Each row must have keys ``_ts`` (datetime with tz)
                         and ``_ts_naive`` (naive UTC datetime) pre-populated,
                         plus an ``occupied`` bool.
        window_end_utc:  The exclusive window end (timezone-aware).

    Returns:
        (occupied_minutes, empty_minutes) — both non-negative ints.
    """
    if not events:
        return 0, 0

    start_naive = _to_naive_utc(events[0]["_ts"])
    end_naive = _to_naive_utc(window_end_utc)
    total_seconds = (end_naive - start_naive).total_seconds()

    occupied_seconds = 0.0
    segment_start: datetime | None = None
    for e in events:
        et = e["_ts_naive"]
        if e.get("occupied", False) and segment_start is None:
            segment_start = et
        elif not e.get("occupied", False) and segment_start is not None:
            occupied_seconds += (et - segment_start).total_seconds()
            segment_start = None

    if segment_start is not None:
        occupied_seconds += (end_naive - segment_start).total_seconds()

    occupied_minutes = max(0, int(occupied_seconds / 60))
    empty_minutes = max(0, int((total_seconds - occupied_seconds) / 60))
    return occupied_minutes, empty_minutes


def aggregate_window(
    site_events: list[dict[str, Any]],
    window_end_utc: datetime,
) -> dict[str, Any]:
    """Aggregate raw occupancy events into per-room feature rows.

    Args:
        site_events:    All raw event rows for the site and time window.
                        Each row needs ``room_code``, ``timestamp`` (ISO str),
                        and ``occupied`` (bool).
        window_end_utc: Exclusive window end (timezone-aware).

    Returns:
        Dict with keys ``window``, ``rooms`` (list of room feature dicts),
        and ``rooms_total``.
    """
    by_room: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)

    for e in site_events:
        ts_str = e.get("timestamp")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        e["_ts"] = ts
        e["_ts_naive"] = _to_naive_utc(ts)
        by_room[str(e.get("room_code", ""))].append(e)

    results_rooms: list[dict[str, Any]] = []
    for room_code, room_events in by_room.items():
        room_events.sort(key=lambda r: r["_ts_naive"])
        occupied_minutes, empty_minutes = compute_room_occupied_minutes(room_events, window_end_utc)

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
        "window": {"end_utc": window_end_utc.isoformat()},
        "rooms": results_rooms,
        "rooms_total": len(results_rooms),
    }
