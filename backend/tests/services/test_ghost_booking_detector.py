"""Tests for Ghost Booking & Right-Sizing Detection (Rev 1.2).

Tests cover:
- OccupancyEvent model: count field silently ignored, occupied stores correctly
- occupancy_store: get_occupied_minutes, get_current_vacancy_start, get_last_event
- Ghost booking detection: grace period, no-show, auto-resolve on occupation
- Right-sizing patterns: early_vacate, brief_occupation, sporadic_use
- Right-sizing edge cases: ghost precedence, no duplicates, auto-dismiss on reoccupation
- Notification formatting: human-readable patterns, available rooms
- API: count field ignored, occupied=True dismisses finding

Total: 17 tests
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.booking_record import BookingRecord
from app.models.space_occupancy import (
    GhostBookingFinding,
    OccupancyEvent,
    RightSizingFinding,
    RightSizingPattern,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_store(tmp_path):
    """Point occupancy_store to a temp directory to isolate tests."""
    with (
        patch("app.services.occupancy_store._DATA_DIR", tmp_path),
        patch("app.services.occupancy_store._EVENTS_FILE", tmp_path / "occupancy_events.json"),
        patch("app.services.occupancy_store._GHOST_FILE", tmp_path / "ghost_findings.json"),
        patch("app.services.occupancy_store._RIGHTSIZING_FILE", tmp_path / "rightsizing_findings.json"),
    ):
        yield


def _make_booking(
    room_id: str = "MR-01",
    room_name: str = "Meeting Room 1",
    start_offset_min: int = -60,
    duration_min: int = 120,
    now: datetime | None = None,
) -> BookingRecord:
    now = now or datetime.utcnow()
    return BookingRecord(
        id=str(uuid.uuid4()),
        site_id="site-002",
        organiser_email="alice@example.com",
        organiser_name="Alice Smith",
        room_id=room_id,
        room_name=room_name,
        start_time=now + timedelta(minutes=start_offset_min),
        end_time=now + timedelta(minutes=start_offset_min + duration_min),
    )


def _inject_events(room_code: str, events: list[tuple[int, bool]], base: datetime):
    """Inject occupancy events at relative minute offsets."""
    from app.services import occupancy_store

    for offset_min, occupied in events:
        evt = OccupancyEvent(
            site_id="site-002",
            room_code=room_code,
            sensor_id="LD2410C-test",
            occupied=occupied,
            timestamp=base + timedelta(minutes=offset_min),
            source="mmwave_ld2410c",
        )
        occupancy_store.save_event(evt)


# ---------------------------------------------------------------------------
# 1. OccupancyEvent model tests
# ---------------------------------------------------------------------------


class TestOccupancyEventModel:
    def test_no_count_field(self):
        """OccupancyEvent has no count field."""
        event = OccupancyEvent(occupied=True)
        assert not hasattr(event, "count")
        assert event.occupied is True

    def test_occupied_stores_correctly(self):
        """occupied=True stores and retrieves correctly."""
        from app.services import occupancy_store

        event = OccupancyEvent(
            site_id="site-002",
            room_code="MR-01",
            sensor_id="LD2410C-MR-01",
            occupied=True,
            source="mmwave_ld2410c",
        )
        saved = occupancy_store.save_event(event)
        retrieved = occupancy_store.get_last_event("MR-01")
        assert retrieved is not None
        assert retrieved.occupied is True
        assert retrieved.id == saved.id


# ---------------------------------------------------------------------------
# 2. Occupancy store query tests
# ---------------------------------------------------------------------------


class TestOccupancyStoreQueries:
    def test_get_occupied_minutes_basic(self):
        """Correct total for a sequence of on/off events."""
        from app.services import occupancy_store

        base = datetime(2026, 3, 7, 9, 0)
        _inject_events(
            "MR-01",
            [
                (0, True),  # 09:00 — occupied
                (10, False),  # 09:10 — vacant (10 min occupied)
                (20, True),  # 09:20 — occupied
                (35, False),  # 09:35 — vacant (15 min occupied)
            ],
            base,
        )

        result = occupancy_store.get_occupied_minutes("MR-01", base, base + timedelta(minutes=40))
        assert result == 25  # 10 + 15

    def test_get_occupied_minutes_still_occupied(self):
        """If still occupied at to_dt, count up to to_dt."""
        from app.services import occupancy_store

        base = datetime(2026, 3, 7, 9, 0)
        _inject_events(
            "MR-01",
            [
                (0, True),  # 09:00 — occupied, never goes false
            ],
            base,
        )

        result = occupancy_store.get_occupied_minutes("MR-01", base, base + timedelta(minutes=30))
        assert result == 30

    def test_get_current_vacancy_start(self):
        """Returns correct timestamp of last occupied=False."""
        from app.services import occupancy_store

        base = datetime(2026, 3, 7, 9, 0)
        _inject_events(
            "MR-01",
            [
                (0, True),
                (20, False),  # Vacancy starts at 09:20
            ],
            base,
        )

        result = occupancy_store.get_current_vacancy_start("MR-01")
        assert result is not None
        assert result == base + timedelta(minutes=20)

    def test_get_current_vacancy_start_occupied(self):
        """Returns None if room is currently occupied."""
        from app.services import occupancy_store

        base = datetime(2026, 3, 7, 9, 0)
        _inject_events(
            "MR-01",
            [
                (0, True),
            ],
            base,
        )

        result = occupancy_store.get_current_vacancy_start("MR-01")
        assert result is None

    def test_get_last_event(self):
        """Returns the most recent event."""
        from app.services import occupancy_store

        base = datetime(2026, 3, 7, 9, 0)
        _inject_events(
            "MR-01",
            [
                (0, True),
                (10, False),
            ],
            base,
        )

        result = occupancy_store.get_last_event("MR-01")
        assert result is not None
        assert result.occupied is False


# ---------------------------------------------------------------------------
# 3. Ghost booking detection
# ---------------------------------------------------------------------------


class TestGhostBookingDetection:
    def test_ghost_detected_after_grace(self):
        """Room empty after grace period -> ghost booking created."""
        from app.services.ghost_booking_detector import detect_ghost_booking

        now = datetime(2026, 3, 7, 10, 0)
        booking = _make_booking(start_offset_min=-30, duration_min=120, now=now)

        # No occupancy events at all
        finding = detect_ghost_booking(booking, now=now, room_code="MR-01")
        assert finding is not None
        assert finding.status == "open"
        assert finding.room_code == "MR-01"

    def test_no_ghost_before_grace(self):
        """Room empty but grace period not elapsed -> no ghost booking."""
        from app.services.ghost_booking_detector import detect_ghost_booking

        now = datetime(2026, 3, 7, 10, 0)
        booking = _make_booking(start_offset_min=-5, duration_min=120, now=now)

        finding = detect_ghost_booking(booking, now=now, room_code="MR-01")
        assert finding is None

    def test_no_ghost_if_occupied(self):
        """Room was occupied -> no ghost booking."""
        from app.services.ghost_booking_detector import detect_ghost_booking

        now = datetime(2026, 3, 7, 10, 0)
        booking = _make_booking(start_offset_min=-30, duration_min=120, now=now)

        # Room was occupied for 5 minutes
        _inject_events("MR-01", [(0, True), (5, False)], booking.start_time)

        finding = detect_ghost_booking(booking, now=now, room_code="MR-01")
        assert finding is None

    def test_auto_resolve_ghost_on_occupation(self):
        """occupied=True with open ghost finding -> auto-resolve."""
        from app.services.ghost_booking_detector import (
            auto_resolve_ghost_on_occupation,
            detect_ghost_booking,
        )

        now = datetime(2026, 3, 7, 10, 0)
        booking = _make_booking(start_offset_min=-30, duration_min=120, now=now)

        # Create ghost finding
        finding = detect_ghost_booking(booking, now=now, room_code="MR-01")
        assert finding is not None

        # Room becomes occupied -> auto-resolve
        resolved = auto_resolve_ghost_on_occupation(booking.id)
        assert resolved is not None
        assert resolved.status == "verified_occupied"


# ---------------------------------------------------------------------------
# 4. Right-sizing pattern detection
# ---------------------------------------------------------------------------


class TestRightSizingPatterns:
    def test_early_vacate(self):
        """Room occupied then vacated >90 min before booking end -> early_vacate."""
        from app.services.ghost_booking_detector import detect_right_sizing_patterns

        now = datetime(2026, 3, 7, 10, 0)
        # Booking: 08:00 - 12:00 (4 hours). Now is 10:00 (2h remaining > 90 min).
        booking = _make_booking(start_offset_min=-120, duration_min=240, now=now)

        # Room occupied 08:00-08:30, then vacant since 08:30 (90+ min ago)
        _inject_events(
            "MR-01",
            [
                (0, True),  # 08:00
                (30, False),  # 08:30 — vacant since
            ],
            booking.start_time,
        )

        findings = detect_right_sizing_patterns("site-002", [booking], now=now)
        assert len(findings) == 1
        assert findings[0].pattern_type == RightSizingPattern.EARLY_VACATE

    def test_brief_occupation(self):
        """Occupied < 30 min in booking running > 60 min -> brief_occupation."""
        from app.services.ghost_booking_detector import detect_right_sizing_patterns

        now = datetime(2026, 3, 7, 10, 0)
        # Booking: 08:30 - 11:30 (3 hours). Now is 10:00 (90 min elapsed, 90 min remaining).
        booking = _make_booking(start_offset_min=-90, duration_min=180, now=now)

        # Room occupied 08:30-08:48 (18 min), then vacant
        _inject_events(
            "MR-01",
            [
                (0, True),  # 08:30
                (18, False),  # 08:48 — 18 min occupied
            ],
            booking.start_time,
        )

        findings = detect_right_sizing_patterns("site-002", [booking], now=now)
        assert len(findings) == 1
        assert findings[0].pattern_type == RightSizingPattern.BRIEF_OCCUPATION
        assert findings[0].occupied_minutes == 18

    def test_sporadic_use(self):
        """Occupied < 25% over > 50% of booking -> sporadic_use."""
        from app.services.ghost_booking_detector import detect_right_sizing_patterns

        now = datetime(2026, 3, 7, 12, 0)
        # Booking: 08:00 - 13:00 (5 hours = 300 min). Now is 12:00 (4h elapsed = 80% > 50%).
        # Time remaining = 60 min (< 90 min threshold, so early_vacate won't match).
        booking = _make_booking(start_offset_min=-240, duration_min=300, now=now)

        # Room occupied sporadically but >= 30 min total to avoid brief_occupation:
        # 08:00-08:15 (15 min), 09:00-09:15 (15 min), 11:50-11:55 (5 min) = 35 min total
        # 35/300 = 11.7% < 25%.
        _inject_events(
            "MR-01",
            [
                (0, True),
                (15, False),  # 08:00-08:15
                (60, True),
                (75, False),  # 09:00-09:15
                (230, True),
                (235, False),  # 11:50-11:55
            ],
            booking.start_time,
        )

        findings = detect_right_sizing_patterns("site-002", [booking], now=now)
        assert len(findings) == 1
        assert findings[0].pattern_type == RightSizingPattern.SPORADIC_USE

    def test_ghost_booking_precedence(self):
        """occupied_minutes=0 -> NO right-sizing finding (ghost booking case)."""
        from app.services.ghost_booking_detector import detect_right_sizing_patterns

        now = datetime(2026, 3, 7, 10, 0)
        booking = _make_booking(start_offset_min=-120, duration_min=240, now=now)

        # No occupancy events at all — this is a ghost booking, not right-sizing
        findings = detect_right_sizing_patterns("site-002", [booking], now=now)
        assert len(findings) == 0

    def test_no_duplicate_finding(self):
        """Open finding already exists for booking_id -> no duplicate."""
        from app.services.ghost_booking_detector import detect_right_sizing_patterns

        now = datetime(2026, 3, 7, 10, 0)
        booking = _make_booking(start_offset_min=-120, duration_min=240, now=now)

        _inject_events(
            "MR-01",
            [
                (0, True),
                (30, False),
            ],
            booking.start_time,
        )

        # First call creates finding
        findings1 = detect_right_sizing_patterns("site-002", [booking], now=now)
        assert len(findings1) == 1

        # Second call should not create duplicate
        findings2 = detect_right_sizing_patterns("site-002", [booking], now=now)
        assert len(findings2) == 0

    def test_auto_dismiss_on_reoccupation(self):
        """Room reoccupied after right-sizing finding -> finding dismissed."""
        from app.services.ghost_booking_detector import (
            auto_dismiss_rightsizing_on_reoccupation,
            detect_right_sizing_patterns,
        )

        now = datetime(2026, 3, 7, 10, 0)
        booking = _make_booking(start_offset_min=-120, duration_min=240, now=now)

        _inject_events(
            "MR-01",
            [
                (0, True),
                (30, False),
            ],
            booking.start_time,
        )

        findings = detect_right_sizing_patterns("site-002", [booking], now=now)
        assert len(findings) == 1
        assert findings[0].status == "open"

        # Room reoccupied -> auto-dismiss
        dismissed = auto_dismiss_rightsizing_on_reoccupation(booking.id)
        assert dismissed is not None
        assert dismissed.status == "dismissed"


# ---------------------------------------------------------------------------
# 5. Notification formatting
# ---------------------------------------------------------------------------


class TestNotificationFormatting:
    def test_right_sizing_notification_human_readable(self):
        """Notification has human-readable pattern and available rooms."""
        from app.services.ghost_booking_detector import format_right_sizing_notification

        finding = RightSizingFinding(
            room_code="FA2-1Q1-MR-01",
            room_name="Board Room A",
            room_capacity=20,
            organiser_name="Alice Smith",
            booking_start=datetime(2026, 3, 7, 9, 0),
            booking_end=datetime(2026, 3, 7, 12, 0),
            booking_duration_minutes=180,
            occupied_minutes=18,
            consecutive_vacancy_minutes=95,
            pattern_type=RightSizingPattern.BRIEF_OCCUPATION,
        )

        msg = format_right_sizing_notification(
            finding,
            site_name="Sandton Tower",
            available_rooms=[
                {"room_code": "FA2-1Q1-MR-03", "capacity": 6, "available_until": "12:00"},
            ],
        )

        assert "Board Room A" in msg
        assert "20 seats" in msg
        assert "18 minutes" in msg
        assert "180-minute booking" in msg
        assert "FA2-1Q1-MR-03" in msg
        assert "6 seats" in msg
        assert "SENTINEL" in msg


# ---------------------------------------------------------------------------
# 6. API payload tests
# ---------------------------------------------------------------------------


class TestAPIPayload:
    def test_count_field_silently_ignored(self):
        """count field in OccupancyEventRequest payload is accepted without error."""
        from app.api.space import OccupancyEventRequest

        # Should not raise even with count present
        req = OccupancyEventRequest(
            room_code="MR-01",
            sensor_id="LD2410C-MR-01",
            occupied=True,
            count=5,  # type: ignore[call-arg]  — extra field, silently ignored
        )
        assert req.occupied is True
        assert not hasattr(req, "count")


# ---------------------------------------------------------------------------
# 7. Concierge Inspection Workflow
# ---------------------------------------------------------------------------


class TestConciergeInspectionWorkflow:
    """Full workflow: no movement -> notify concierge -> inspect -> confirm outcome."""

    def test_full_concierge_workflow(self):
        """Ghost detected -> concierge confirms empty -> confirmed_empty."""
        from app.services.ghost_booking_detector import (
            concierge_confirm_empty,
            detect_ghost_booking,
            mark_pending_inspection,
        )

        now = datetime(2026, 3, 7, 10, 0)
        booking = _make_booking(start_offset_min=-30, duration_min=120, now=now)

        # Step 1: Ghost detected (no movement for 30 min, past 15 min grace)
        finding = detect_ghost_booking(booking, now=now, room_code="MR-01")
        assert finding is not None
        assert finding.status == "open"

        # Step 2: Notification sent -> mark pending inspection
        updated = mark_pending_inspection(finding.id)
        assert updated is not None
        assert updated.status == "pending_inspection"

        # Step 3: Concierge inspects and confirms empty
        confirmed = concierge_confirm_empty(
            finding_id=finding.id,
            confirmed_by="John the Concierge",
        )
        assert confirmed is not None
        assert confirmed.status == "confirmed_empty"
        assert confirmed.inspected_by == "John the Concierge"
        assert "confirmed empty" in confirmed.charge_reason.lower()
        assert confirmed.resolved_at is not None

    def test_concierge_cannot_confirm_already_resolved(self):
        """Cannot confirm a finding that was already auto-resolved (room reoccupied)."""
        from app.services.ghost_booking_detector import (
            auto_resolve_ghost_on_occupation,
            concierge_confirm_empty,
            detect_ghost_booking,
        )

        now = datetime(2026, 3, 7, 10, 0)
        booking = _make_booking(start_offset_min=-30, duration_min=120, now=now)

        # Ghost detected
        finding = detect_ghost_booking(booking, now=now, room_code="MR-01")
        assert finding is not None

        # Room gets occupied before concierge arrives
        auto_resolve_ghost_on_occupation(booking.id)

        # Concierge tries to confirm — should fail
        result = concierge_confirm_empty(
            finding_id=finding.id,
            confirmed_by="John the Concierge",
        )
        assert result is None  # Cannot confirm already-resolved finding

    def test_auto_resolve_during_pending_inspection(self):
        """Room occupied while concierge is on the way -> auto-resolve."""
        from app.services.ghost_booking_detector import (
            auto_resolve_ghost_on_occupation,
            detect_ghost_booking,
            mark_pending_inspection,
        )

        now = datetime(2026, 3, 7, 10, 0)
        booking = _make_booking(start_offset_min=-30, duration_min=120, now=now)

        # Ghost detected and sent to concierge
        finding = detect_ghost_booking(booking, now=now, room_code="MR-01")
        mark_pending_inspection(finding.id)

        # Person arrives before concierge gets there
        resolved = auto_resolve_ghost_on_occupation(booking.id)
        assert resolved is not None
        assert resolved.status == "verified_occupied"

    def test_ghost_notification_includes_inspection_instructions(self):
        """Ghost notification tells concierge to physically inspect."""
        from app.services.ghost_booking_detector import format_ghost_booking_notification

        finding = GhostBookingFinding(
            id="test-finding-001",
            room_code="FA2-1Q1-MR-01",
            room_name="Board Room A",
            organiser_name="Alice Smith",
            organiser_email="alice@example.com",
            booking_start=datetime(2026, 3, 7, 9, 0),
            booking_end=datetime(2026, 3, 7, 11, 0),
            grace_period_minutes=20,
        )

        msg = format_ghost_booking_notification(
            finding,
            site_name="Sandton Tower",
            confirm_url="https://sentinel.example.com/space/confirm/test-finding-001",
        )

        assert "Inspection Required" in msg
        assert "no movement" in msg.lower()
        assert "20 minutes" in msg
        assert "Please inspect" in msg
        assert "occupied or empty" in msg.lower()
        assert "test-finding-001" in msg
        assert "https://sentinel.example.com" in msg
        assert "SENTINEL" in msg

    def test_confirmation_note_includes_details(self):
        """Inspection note contains room and concierge details."""
        from app.services.ghost_booking_detector import (
            concierge_confirm_empty,
            detect_ghost_booking,
        )

        now = datetime(2026, 3, 7, 10, 0)
        booking = _make_booking(
            room_id="MR-01",
            room_name="Board Room A",
            start_offset_min=-30,
            duration_min=120,
            now=now,
        )

        finding = detect_ghost_booking(booking, now=now, room_code="MR-01")
        confirmed = concierge_confirm_empty(
            finding_id=finding.id,
            confirmed_by="Sarah Concierge",
        )

        assert "Board Room A" in confirmed.charge_reason
        assert "MR-01" in confirmed.charge_reason
        assert "Sarah Concierge" in confirmed.charge_reason
