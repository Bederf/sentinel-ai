"""Tests for Focus Room Session Service (Phase 2).

Tests session lifecycle: create, close, noise filtering, extended use detection,
analytics, and API integration.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.space_occupancy import OccupancyEvent
from app.models.space_occupancy import FocusRoomSession
from tests.services.fake_space_store import FakeSpaceSupabase

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_store():
    """Use an isolated in-memory canonical store for focus-room tests."""
    fake = FakeSpaceSupabase()
    with patch("app.services.occupancy_store._client", return_value=fake):
        yield


def _ts(hour: int, minute: int = 0) -> datetime:
    """Quick helper to create timestamps on a fixed date."""
    return datetime(2026, 3, 10, hour, minute, 0)


def _save_event(room_code: str, sensor_id: str, occupied: bool, timestamp: datetime) -> None:
    from app.services import occupancy_store

    occupancy_store.save_event(
        OccupancyEvent(
            site_id="site-002",
            room_code=room_code,
            sensor_id=sensor_id,
            occupied=occupied,
            timestamp=timestamp,
            received_at=timestamp,
            source="test",
        )
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestFocusRoomSessionModel:
    def test_new_session_is_active(self):
        s = FocusRoomSession(room_code="FR-01", start_time=_ts(9))
        assert s.is_active
        assert s.end_time is None
        assert s.duration_seconds == 0

    def test_close_session_computes_duration(self):
        s = FocusRoomSession(room_code="FR-01", start_time=_ts(9))
        s.close(_ts(10, 30))  # 1.5 hours
        assert not s.is_active
        assert s.duration_seconds == 5400
        assert not s.extended_use

    def test_close_session_flags_extended_use(self):
        s = FocusRoomSession(room_code="FR-01", start_time=_ts(9))
        s.close(_ts(11, 30), extended_threshold=7200)  # 2.5 hours > 2h
        assert s.extended_use
        assert s.duration_seconds == 9000

    def test_close_at_exact_threshold_is_not_extended(self):
        s = FocusRoomSession(room_code="FR-01", start_time=_ts(9))
        s.close(_ts(11), extended_threshold=7200)  # exactly 2 hours
        assert not s.extended_use
        assert s.duration_seconds == 7200

    def test_room_type_defaults_to_focus(self):
        s = FocusRoomSession(room_code="FR-01")
        assert s.room_type == "focus"


# ---------------------------------------------------------------------------
# Session service tests
# ---------------------------------------------------------------------------


class TestFocusRoomSessionService:
    def test_active_session_turns_red_light_on_after_two_hours(self):
        from app.services.focus_room_session_service import describe_focus_session_state

        session = FocusRoomSession(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            start_time=_ts(9),
        )

        state = describe_focus_session_state(
            session,
            now=_ts(11, 5),
            extended_use_seconds=7200,
        )

        assert state["duration_seconds"] == 7500
        assert state["extended_use"] is True
        assert state["red_light_on"] is True
        assert state["max_allowed_minutes"] == 120
        assert state["red_light_cooldown_seconds"] == 300
        assert state["red_light_cooldown_remaining_seconds"] == 0

    def test_closed_extended_session_keeps_red_light_on_for_cooldown(self):
        from app.services.focus_room_session_service import describe_focus_session_state

        session = FocusRoomSession(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            start_time=_ts(9),
        )
        session.close(_ts(11, 10), extended_threshold=7200)

        state = describe_focus_session_state(
            session,
            now=_ts(11, 13),
            extended_use_seconds=7200,
            red_light_cooldown_seconds=300,
        )

        assert state["extended_use"] is True
        assert state["red_light_on"] is True
        assert state["red_light_cooldown_remaining_seconds"] == 120

    def test_closed_extended_session_turns_red_light_off_after_cooldown(self):
        from app.services.focus_room_session_service import describe_focus_session_state

        session = FocusRoomSession(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            start_time=_ts(9),
        )
        session.close(_ts(11, 10), extended_threshold=7200)

        state = describe_focus_session_state(
            session,
            now=_ts(11, 16),
            extended_use_seconds=7200,
            red_light_cooldown_seconds=300,
        )

        assert state["extended_use"] is True
        assert state["red_light_on"] is False
        assert state["red_light_cooldown_remaining_seconds"] == 0

    def test_occupied_true_starts_session(self):
        from app.services.focus_room_session_service import process_focus_room_event

        result = process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=True,
            timestamp=_ts(9),
        )
        assert result["action"] == "session_started"
        assert result["room_code"] == "FR-01"
        assert "session_id" in result

    def test_occupied_false_closes_session(self):
        from app.services.focus_room_session_service import process_focus_room_event

        # Start
        r1 = process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=True,
            timestamp=_ts(9),
        )
        # Close after 45 minutes
        r2 = process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=False,
            timestamp=_ts(9, 45),
            min_session_seconds=180,
            vacancy_grace_seconds=0,
        )
        assert r2["action"] == "session_closed"
        assert r2["duration_seconds"] == 2700  # 45 min
        assert r2["extended_use"] is False

    def test_short_session_discarded_as_noise(self):
        from app.services.focus_room_session_service import process_focus_room_event

        # Start
        process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=True,
            timestamp=_ts(9),
        )
        # Close after 2 minutes (< 3 min threshold)
        r2 = process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=False,
            timestamp=_ts(9) + timedelta(minutes=2),
            min_session_seconds=180,
            vacancy_grace_seconds=0,
        )
        assert r2["action"] == "session_discarded"
        assert r2["duration_seconds"] == 120

    def test_extended_use_flagged(self):
        from app.services.focus_room_session_service import process_focus_room_event

        process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=True,
            timestamp=_ts(9),
        )
        r2 = process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=False,
            timestamp=_ts(11, 30),  # 2.5 hours
            min_session_seconds=180,
            extended_use_seconds=7200,
            vacancy_grace_seconds=0,
        )
        assert r2["action"] == "session_closed"
        assert r2["extended_use"] is True

    def test_short_coffee_break_does_not_reset_session(self):
        from app.services import occupancy_store
        from app.services.focus_room_session_service import process_focus_room_event

        process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=True,
            timestamp=_ts(9),
        )

        gap_started = process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=False,
            timestamp=_ts(10, 0),
            vacancy_grace_seconds=60,
        )
        _save_event("FR-01", "LD2410C-FR-01", False, _ts(10, 0))
        gap_started = process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=False,
            timestamp=_ts(10, 0),
            vacancy_grace_seconds=60,
        )
        assert gap_started["action"] == "vacancy_grace"

        _save_event("FR-01", "LD2410C-FR-01", False, _ts(10, 0) + timedelta(seconds=30))
        gap_continues = process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=False,
            timestamp=_ts(10, 0) + timedelta(seconds=30),
            vacancy_grace_seconds=60,
        )
        assert gap_continues["action"] == "vacancy_grace"

        resumed = process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=True,
            timestamp=_ts(10, 1),
        )
        assert resumed["action"] == "no_action"

        active = occupancy_store.get_active_session("FR-01")
        assert active is not None
        assert active.start_time == _ts(9)

    def test_long_vacancy_closes_session_at_first_empty_reading(self):
        from app.services.focus_room_session_service import process_focus_room_event

        process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=True,
            timestamp=_ts(9),
        )

        first_empty = _ts(10, 0)
        _save_event("FR-01", "LD2410C-FR-01", False, first_empty)
        gap_started = process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=False,
            timestamp=first_empty,
            vacancy_grace_seconds=60,
        )
        assert gap_started["action"] == "vacancy_grace"

        _save_event("FR-01", "LD2410C-FR-01", False, first_empty + timedelta(seconds=70))
        closed = process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=False,
            timestamp=first_empty + timedelta(seconds=70),
            vacancy_grace_seconds=60,
        )
        assert closed["action"] == "session_closed"
        assert closed["end_time"] == first_empty.isoformat()
        assert closed["duration_seconds"] == 3600

    def test_duplicate_occupied_no_action(self):
        from app.services.focus_room_session_service import process_focus_room_event

        process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=True,
            timestamp=_ts(9),
        )
        # Second occupied=True should be no-op
        r2 = process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=True,
            timestamp=_ts(9, 5),
        )
        assert r2["action"] == "no_action"

    def test_unmatched_vacant_no_action(self):
        from app.services.focus_room_session_service import process_focus_room_event

        # occupied=False with no active session
        r = process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=False,
            timestamp=_ts(9),
        )
        assert r["action"] == "no_action"

    def test_multiple_sessions_same_room(self):
        from app.services import occupancy_store
        from app.services.focus_room_session_service import process_focus_room_event

        # Session 1: 09:00 - 09:45
        process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=True,
            timestamp=_ts(9),
        )
        process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=False,
            timestamp=_ts(9, 45),
            min_session_seconds=180,
            vacancy_grace_seconds=0,
        )

        # Session 2: 10:30 - 12:00
        process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=True,
            timestamp=_ts(10, 30),
        )
        process_focus_room_event(
            site_id="site-002",
            room_code="FR-01",
            sensor_id="LD2410C-FR-01",
            occupied=False,
            timestamp=_ts(12),
            min_session_seconds=180,
            vacancy_grace_seconds=0,
        )

        sessions = occupancy_store.get_sessions_for_room("FR-01")
        assert len(sessions) == 2
        assert sessions[0].duration_seconds == 2700  # 45 min
        assert sessions[1].duration_seconds == 5400  # 1.5 hours


# ---------------------------------------------------------------------------
# Store persistence tests
# ---------------------------------------------------------------------------


class TestSessionStore:
    def test_save_and_retrieve_session(self):
        from app.services import occupancy_store

        session = FocusRoomSession(
            site_id="site-002",
            room_code="FR-03",
            sensor_id="LD2410C-FR-03",
            start_time=_ts(14),
        )
        occupancy_store.save_session(session)

        active = occupancy_store.get_active_session("FR-03")
        assert active is not None
        assert active.session_id == session.session_id
        assert active.is_active

    def test_close_session_persists(self):
        from app.services import occupancy_store

        session = FocusRoomSession(
            site_id="site-002",
            room_code="FR-03",
            sensor_id="LD2410C-FR-03",
            start_time=_ts(14),
        )
        occupancy_store.save_session(session)
        closed = occupancy_store.close_session(session.session_id, _ts(15, 30))

        assert closed is not None
        assert closed.duration_seconds == 5400
        assert not closed.extended_use

        # No longer active
        assert occupancy_store.get_active_session("FR-03") is None

    def test_discard_session_removes_it(self):
        from app.services import occupancy_store

        session = FocusRoomSession(
            site_id="site-002",
            room_code="FR-03",
            sensor_id="LD2410C-FR-03",
            start_time=_ts(14),
        )
        occupancy_store.save_session(session)
        assert occupancy_store.discard_session(session.session_id) is True
        assert occupancy_store.get_active_session("FR-03") is None

    def test_get_sessions_for_site(self):
        from app.services import occupancy_store

        for i, code in enumerate(["FR-01", "FR-02", "FR-03"]):
            s = FocusRoomSession(
                site_id="site-002",
                room_code=code,
                start_time=_ts(9 + i),
            )
            s.close(_ts(10 + i), extended_threshold=7200)
            occupancy_store.save_session(s)

        # Add one extended session
        ext = FocusRoomSession(
            site_id="site-002",
            room_code="FR-01",
            start_time=_ts(13),
        )
        ext.close(_ts(16), extended_threshold=7200)  # 3 hours
        occupancy_store.save_session(ext)

        all_sessions = occupancy_store.get_sessions_for_site("site-002")
        assert len(all_sessions) == 4

        extended = occupancy_store.get_sessions_for_site("site-002", extended_only=True)
        assert len(extended) == 1
        assert extended[0].room_code == "FR-01"


# ---------------------------------------------------------------------------
# Analytics tests
# ---------------------------------------------------------------------------


class TestFocusRoomAnalytics:
    def test_analytics_empty(self):
        from app.services.focus_room_session_service import get_focus_room_analytics

        result = get_focus_room_analytics("site-002")
        assert result["total_sessions"] == 0
        assert result["average_duration_minutes"] == 0

    def test_analytics_with_sessions(self):
        from app.services import occupancy_store
        from app.services.focus_room_session_service import get_focus_room_analytics

        # 3 sessions: 30 min, 60 min, 150 min (150 min = 2h30 > 2h = extended)
        for dur_min, code in [(30, "FR-01"), (60, "FR-02"), (150, "FR-01")]:
            s = FocusRoomSession(
                site_id="site-002",
                room_code=code,
                start_time=_ts(9),
            )
            s.close(_ts(9) + timedelta(minutes=dur_min), extended_threshold=7200)
            occupancy_store.save_session(s)

        result = get_focus_room_analytics("site-002")
        assert result["total_sessions"] == 3
        assert result["average_duration_minutes"] == 80.0  # (30+60+150)/3
        assert result["longest_session_minutes"] == 150.0
        assert result["extended_use_count"] == 1  # 150 min > 2h
        assert result["sessions_by_room"]["FR-01"] == 2
        assert result["sessions_by_room"]["FR-02"] == 1
        assert result["peak_hour"] == 9

    def test_analytics_counts_active_overstays(self):
        from app.services import occupancy_store
        from app.services.focus_room_session_service import get_focus_room_analytics

        active = FocusRoomSession(
            site_id="site-002",
            room_code="FR-02",
            sensor_id="LD2410C-FR-02",
            start_time=_ts(9),
        )
        occupancy_store.save_session(active)

        with patch("app.services.focus_room_session_service.datetime") as fake_datetime:
            fake_datetime.utcnow.return_value = _ts(11, 5)
            result = get_focus_room_analytics("site-002")

        assert result["active_sessions"] == 1
        assert result["completed_sessions"] == 0
        assert result["extended_use_sessions"] == 1


# ---------------------------------------------------------------------------
# API integration test
# ---------------------------------------------------------------------------


class TestFocusRoomAPI:
    def test_focus_room_event_creates_session(self):
        """Verify room_type=focus routes through session service."""
        from app.services.focus_room_session_service import process_focus_room_event

        r = process_focus_room_event(
            site_id="site-002",
            room_code="FR-05",
            sensor_id="LD2410C-FR-05",
            occupied=True,
            timestamp=_ts(10),
            room_type="focus",
        )
        assert r["action"] == "session_started"

    def test_vacancy_between_sessions(self):
        """Two sessions with a gap — verify vacancy time is computable."""
        from app.services import occupancy_store
        from app.services.focus_room_session_service import process_focus_room_event

        # Session 1: 09:00 - 10:00
        process_focus_room_event(
            site_id="site-002",
            room_code="FR-05",
            sensor_id="LD2410C-FR-05",
            occupied=True,
            timestamp=_ts(9),
        )
        process_focus_room_event(
            site_id="site-002",
            room_code="FR-05",
            sensor_id="LD2410C-FR-05",
            occupied=False,
            timestamp=_ts(10),
            min_session_seconds=180,
            vacancy_grace_seconds=0,
        )

        # Session 2: 11:00 - 12:00
        process_focus_room_event(
            site_id="site-002",
            room_code="FR-05",
            sensor_id="LD2410C-FR-05",
            occupied=True,
            timestamp=_ts(11),
        )
        process_focus_room_event(
            site_id="site-002",
            room_code="FR-05",
            sensor_id="LD2410C-FR-05",
            occupied=False,
            timestamp=_ts(12),
            min_session_seconds=180,
            vacancy_grace_seconds=0,
        )

        sessions = occupancy_store.get_sessions_for_room("FR-05")
        assert len(sessions) == 2

        # Vacancy between sessions = 11:00 - 10:00 = 1 hour
        vacancy_seconds = int((sessions[1].start_time - sessions[0].end_time).total_seconds())
        assert vacancy_seconds == 3600
