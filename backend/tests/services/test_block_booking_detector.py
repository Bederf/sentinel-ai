"""Tests for the Block Booking Detection module."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from unittest.mock import MagicMock


from app.models.booking_record import (
    BlockBookingAlert,
    BlockBookingConfig,
    BookingRecord,
)
from app.services.block_booking_detector.email_parser import (
    is_cancellation,
    parse_booking_confirmation,
)
from app.services.block_booking_detector.overlap_detector import detect_overlaps


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SITE_ID = "site-002"

SAMPLE_CONFIRMATION_EMAIL = """\
From: Shaun Grose <shaun.grose@example.com>
To: boardroom1@resource.example.com
Subject: Accepted: Project Review - Boardroom 1
Date: Mon, 02 Mar 2026 08:00:00 +0200
Content-Type: text/plain; charset="utf-8"

Your meeting has been confirmed.

Organizer: Shaun Grose <shaun.grose@example.com>
Location: Boardroom 1
Start: Monday, 02 March 2026 09:00
End: Monday, 02 March 2026 11:00

This is an automated message from the room booking system.
"""

SAMPLE_CANCELLATION_EMAIL = """\
From: Shaun Grose <shaun.grose@example.com>
To: boardroom1@resource.example.com
Subject: Cancelled: Project Review - Boardroom 1
Date: Mon, 02 Mar 2026 08:30:00 +0200
Content-Type: text/plain; charset="utf-8"

Your meeting has been cancelled.

Location: Boardroom 1
Start: Monday, 02 March 2026 09:00
End: Monday, 02 March 2026 11:00
"""

NON_BOOKING_EMAIL = """\
From: newsletter@company.com
To: all@company.com
Subject: Weekly Newsletter - March Edition
Date: Mon, 02 Mar 2026 07:00:00 +0200
Content-Type: text/plain; charset="utf-8"

Here are this week's highlights...
"""


def _make_booking(
    organiser: str = "shaun@example.com",
    room: str = "Boardroom 1",
    day: date | None = None,
    start_hour: int = 9,
    end_hour: int = 11,
    booking_id: str | None = None,
) -> BookingRecord:
    """Helper to create a BookingRecord for testing."""
    d = day or date(2026, 3, 2)
    return BookingRecord(
        id=booking_id or str(uuid.uuid4()),
        site_id=SITE_ID,
        organiser_email=organiser,
        organiser_name=organiser.split("@")[0],
        room_id=room.lower().replace(" ", "-"),
        room_name=room,
        booking_date=d,
        start_time=datetime(d.year, d.month, d.day, start_hour, 0),
        end_time=datetime(d.year, d.month, d.day, end_hour, 0),
        raw_email_hash=f"hash-{uuid.uuid4().hex[:8]}",
    )


DEFAULT_CONFIG = BlockBookingConfig(
    site_id=SITE_ID,
    min_rooms_for_alert=2,
    enabled=True,
)


# ---------------------------------------------------------------------------
# 1. email_parser: parse a valid confirmation email
# ---------------------------------------------------------------------------


class TestEmailParser:
    def test_parse_valid_confirmation(self):
        record = parse_booking_confirmation(SAMPLE_CONFIRMATION_EMAIL, SITE_ID)
        assert record is not None
        assert record.organiser_email == "shaun.grose@example.com"
        assert record.organiser_name == "Shaun Grose"
        assert record.room_name == "Boardroom 1"
        assert record.booking_date == date(2026, 3, 2)
        assert record.start_time.hour == 9
        assert record.end_time.hour == 11
        assert record.site_id == SITE_ID
        assert len(record.raw_email_hash) == 64  # SHA-256

    # 2. email_parser: return None for non-booking email
    def test_parse_non_booking_returns_none(self):
        record = parse_booking_confirmation(NON_BOOKING_EMAIL, SITE_ID)
        # Non-booking email has no Start/End fields, should return None
        assert record is None

    # 3. email_parser: cancellation returns None
    def test_parse_cancellation_returns_none(self):
        record = parse_booking_confirmation(SAMPLE_CANCELLATION_EMAIL, SITE_ID)
        assert record is None

    def test_is_cancellation(self):
        assert is_cancellation(SAMPLE_CANCELLATION_EMAIL) is True
        assert is_cancellation(SAMPLE_CONFIRMATION_EMAIL) is False

    # 3b. email_parser: dedup via hash
    def test_dedup_same_email_same_hash(self):
        r1 = parse_booking_confirmation(SAMPLE_CONFIRMATION_EMAIL, SITE_ID)
        r2 = parse_booking_confirmation(SAMPLE_CONFIRMATION_EMAIL, SITE_ID)
        assert r1 is not None
        assert r2 is not None
        assert r1.raw_email_hash == r2.raw_email_hash


# ---------------------------------------------------------------------------
# 4-7. overlap_detector tests
# ---------------------------------------------------------------------------


class TestOverlapDetector:
    # 4. Two rooms, same organiser, same time -> alert
    def test_two_rooms_same_time_same_organiser(self):
        bookings = [
            _make_booking(room="Boardroom 1", start_hour=9, end_hour=11),
            _make_booking(room="Boardroom 2", start_hour=9, end_hour=11),
        ]
        alerts = detect_overlaps(SITE_ID, bookings, DEFAULT_CONFIG)
        assert len(alerts) == 1
        assert alerts[0].room_count == 2
        assert set(alerts[0].rooms) == {"Boardroom 1", "Boardroom 2"}
        assert alerts[0].organiser_email == "shaun@example.com"

    # 5. Two rooms, same organiser, non-overlapping times -> no alert
    def test_two_rooms_non_overlapping(self):
        bookings = [
            _make_booking(room="Boardroom 1", start_hour=9, end_hour=10),
            _make_booking(room="Boardroom 2", start_hour=10, end_hour=11),
        ]
        alerts = detect_overlaps(SITE_ID, bookings, DEFAULT_CONFIG)
        assert len(alerts) == 0

    # 6. Two rooms, different organisers, same time -> no alert
    def test_two_rooms_different_organisers(self):
        bookings = [
            _make_booking(
                organiser="shaun@example.com",
                room="Boardroom 1",
                start_hour=9,
                end_hour=11,
            ),
            _make_booking(
                organiser="jane@example.com",
                room="Boardroom 2",
                start_hour=9,
                end_hour=11,
            ),
        ]
        alerts = detect_overlaps(SITE_ID, bookings, DEFAULT_CONFIG)
        assert len(alerts) == 0

    # 7. Existing open alert -> no duplicate
    def test_no_duplicate_alert(self):
        bookings = [
            _make_booking(room="Boardroom 1", start_hour=9, end_hour=11),
            _make_booking(room="Boardroom 2", start_hour=9, end_hour=11),
        ]
        mock_store = MagicMock()
        mock_store.has_open_alert_for.return_value = True

        alerts = detect_overlaps(SITE_ID, bookings, DEFAULT_CONFIG, store=mock_store)
        assert len(alerts) == 0

    def test_three_rooms_same_organiser(self):
        """Three rooms overlapping should produce one alert with room_count=3."""
        bookings = [
            _make_booking(room="Boardroom 1", start_hour=9, end_hour=11),
            _make_booking(room="Boardroom 2", start_hour=10, end_hour=12),
            _make_booking(room="Boardroom 3", start_hour=9, end_hour=10),
        ]
        alerts = detect_overlaps(SITE_ID, bookings, DEFAULT_CONFIG)
        assert len(alerts) == 1
        assert alerts[0].room_count == 3

    def test_disabled_config_returns_no_alerts(self):
        """When config.enabled is False, no alerts should be generated."""
        bookings = [
            _make_booking(room="Boardroom 1", start_hour=9, end_hour=11),
            _make_booking(room="Boardroom 2", start_hour=9, end_hour=11),
        ]
        config = BlockBookingConfig(site_id=SITE_ID, enabled=False)
        alerts = detect_overlaps(SITE_ID, bookings, config)
        assert len(alerts) == 0

    def test_partial_overlap(self):
        """Bookings that partially overlap should still trigger an alert."""
        bookings = [
            _make_booking(room="Boardroom 1", start_hour=9, end_hour=11),
            _make_booking(room="Boardroom 2", start_hour=10, end_hour=12),
        ]
        alerts = detect_overlaps(SITE_ID, bookings, DEFAULT_CONFIG)
        assert len(alerts) == 1

    def test_min_rooms_threshold(self):
        """Only flag when room count meets min_rooms_for_alert."""
        bookings = [
            _make_booking(room="Boardroom 1", start_hour=9, end_hour=11),
            _make_booking(room="Boardroom 2", start_hour=9, end_hour=11),
        ]
        config = BlockBookingConfig(site_id=SITE_ID, min_rooms_for_alert=3, enabled=True)
        alerts = detect_overlaps(SITE_ID, bookings, config)
        assert len(alerts) == 0


# ---------------------------------------------------------------------------
# 8. notifier: message format
# ---------------------------------------------------------------------------


class TestNotifier:
    def test_message_format(self):
        from app.services.block_booking_detector.notifier import format_alert_message

        alert = BlockBookingAlert(
            site_id=SITE_ID,
            organiser_email="shaun@example.com",
            organiser_name="Shaun Grose",
            overlap_window_start=datetime(2026, 3, 2, 9, 0),
            overlap_window_end=datetime(2026, 3, 2, 11, 0),
            rooms=["Boardroom 1", "Boardroom 2"],
            room_count=2,
            booking_ids=["b1", "b2"],
        )
        msg = format_alert_message(alert, site_name="Sandton City")
        assert "Block Booking Detected" in msg
        assert "Shaun Grose" in msg
        assert "shaun@example.com" in msg
        assert "Boardroom 1" in msg
        assert "Boardroom 2" in msg
        assert "2 rooms" in msg
        assert "Sandton City" in msg
        assert "cannot occupy multiple rooms" in msg
