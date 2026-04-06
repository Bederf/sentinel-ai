"""Parity tests for occupancy_table processing functions.

Verifies that the extracted aggregate_window / compute_room_occupied_minutes
functions produce the same results as the original inline logic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.processing.occupancy_table import aggregate_window, compute_room_occupied_minutes

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts(offset_minutes: int = 0) -> str:
    """Return an ISO timestamp offset from a fixed reference time."""
    ref = datetime(2026, 3, 25, 6, 0, 0, tzinfo=UTC)
    return (ref + timedelta(minutes=offset_minutes)).isoformat()


def _window_end(offset_minutes: int = 480) -> datetime:
    """Return window_end as timezone-aware datetime."""
    ref = datetime(2026, 3, 25, 6, 0, 0, tzinfo=UTC)
    return ref + timedelta(minutes=offset_minutes)


# ---------------------------------------------------------------------------
# compute_room_occupied_minutes
# ---------------------------------------------------------------------------


class TestComputeRoomOccupiedMinutes:
    def test_empty_events_returns_zeros(self):
        occupied, empty = compute_room_occupied_minutes([], _window_end())
        assert occupied == 0
        assert empty == 0

    def test_always_occupied_single_event(self):
        """One 'occupied=True' event at t=0, window ends 60 minutes later."""
        ref = datetime(2026, 3, 25, 6, 0, 0, tzinfo=UTC)
        events = [
            {
                "_ts": ref,
                "_ts_naive": ref.replace(tzinfo=None),
                "occupied": True,
            }
        ]
        window_end = ref + timedelta(minutes=60)
        occupied, empty = compute_room_occupied_minutes(events, window_end)
        assert occupied == 60
        assert empty == 0

    def test_never_occupied_single_event(self):
        """One 'occupied=False' event — room empty for the whole window."""
        ref = datetime(2026, 3, 25, 6, 0, 0, tzinfo=UTC)
        events = [
            {
                "_ts": ref,
                "_ts_naive": ref.replace(tzinfo=None),
                "occupied": False,
            }
        ]
        window_end = ref + timedelta(minutes=60)
        occupied, empty = compute_room_occupied_minutes(events, window_end)
        assert occupied == 0
        assert empty == 60

    def test_occupied_then_empty(self):
        """Occupied for 30 minutes, then empty for 30 minutes."""
        ref = datetime(2026, 3, 25, 6, 0, 0, tzinfo=UTC)
        events = [
            {"_ts": ref, "_ts_naive": ref.replace(tzinfo=None), "occupied": True},
            {
                "_ts": ref + timedelta(minutes=30),
                "_ts_naive": (ref + timedelta(minutes=30)).replace(tzinfo=None),
                "occupied": False,
            },
        ]
        window_end = ref + timedelta(minutes=60)
        occupied, empty = compute_room_occupied_minutes(events, window_end)
        assert occupied == 30
        assert empty == 30

    def test_multiple_segments(self):
        """Occupied 10 min, empty 10 min, occupied 10 min."""
        ref = datetime(2026, 3, 25, 6, 0, 0, tzinfo=UTC)
        events = [
            {"_ts": ref, "_ts_naive": ref.replace(tzinfo=None), "occupied": True},
            {
                "_ts": ref + timedelta(minutes=10),
                "_ts_naive": (ref + timedelta(minutes=10)).replace(tzinfo=None),
                "occupied": False,
            },
            {
                "_ts": ref + timedelta(minutes=20),
                "_ts_naive": (ref + timedelta(minutes=20)).replace(tzinfo=None),
                "occupied": True,
            },
        ]
        window_end = ref + timedelta(minutes=30)
        occupied, empty = compute_room_occupied_minutes(events, window_end)
        assert occupied == 20
        assert empty == 10


# ---------------------------------------------------------------------------
# aggregate_window
# ---------------------------------------------------------------------------


class TestAggregateWindow:
    def test_empty_events_returns_empty_rooms(self):
        result = aggregate_window([], _window_end())
        assert result["rooms"] == []
        assert result["rooms_total"] == 0

    def test_groups_by_room_code(self):
        events = [
            {"room_code": "R1", "timestamp": _ts(0), "occupied": True},
            {"room_code": "R2", "timestamp": _ts(5), "occupied": False},
            {"room_code": "R1", "timestamp": _ts(30), "occupied": False},
        ]
        result = aggregate_window(events, _window_end())
        room_codes = {r["room_code"] for r in result["rooms"]}
        assert room_codes == {"R1", "R2"}
        assert result["rooms_total"] == 2

    def test_event_count_per_room(self):
        events = [
            {"room_code": "R1", "timestamp": _ts(0), "occupied": True},
            {"room_code": "R1", "timestamp": _ts(30), "occupied": False},
            {"room_code": "R1", "timestamp": _ts(60), "occupied": True},
        ]
        result = aggregate_window(events, _window_end())
        r1 = next(r for r in result["rooms"] if r["room_code"] == "R1")
        assert r1["events_count"] == 3

    def test_occupied_percent_between_0_and_100(self):
        events = [
            {"room_code": "R1", "timestamp": _ts(0), "occupied": True},
            {"room_code": "R1", "timestamp": _ts(120), "occupied": False},
        ]
        result = aggregate_window(events, _window_end(480))
        r1 = next(r for r in result["rooms"] if r["room_code"] == "R1")
        assert 0 <= r1["occupied_percent"] <= 100

    def test_invalid_timestamp_skipped(self):
        events = [
            {"room_code": "R1", "timestamp": "not-a-date", "occupied": True},
            {"room_code": "R2", "timestamp": _ts(0), "occupied": False},
        ]
        result = aggregate_window(events, _window_end())
        room_codes = {r["room_code"] for r in result["rooms"]}
        assert "R1" not in room_codes
        assert "R2" in room_codes

    def test_missing_timestamp_skipped(self):
        events = [
            {"room_code": "R1", "occupied": True},  # no timestamp
            {"room_code": "R2", "timestamp": _ts(0), "occupied": False},
        ]
        result = aggregate_window(events, _window_end())
        room_codes = {r["room_code"] for r in result["rooms"]}
        assert "R1" not in room_codes

    def test_window_end_in_output(self):
        window_end = _window_end(240)
        result = aggregate_window([], window_end)
        assert result["window"]["end_utc"] == window_end.isoformat()

    def test_z_suffix_timestamp_accepted(self):
        events = [
            {"room_code": "R1", "timestamp": "2026-03-25T06:00:00Z", "occupied": True},
        ]
        result = aggregate_window(events, _window_end(60))
        assert result["rooms_total"] == 1
