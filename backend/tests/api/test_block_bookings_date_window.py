from datetime import date

from app.api.block_bookings import _default_booking_window


def test_default_booking_window_returns_28_day_window():
    start, end = _default_booking_window("site-002")
    assert (end - start).days == 28


def test_default_booking_window_start_is_today():
    start, _ = _default_booking_window("site-002")
    assert start == date.today()
