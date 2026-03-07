"""Tests for app.plant.notification_throttle — flood detection and rate limiting."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.plant.models import AlarmSeverity, DesigoBuildingAlarm
from app.plant.notification_throttle import (
    NotificationThrottle,
    ThrottleAction,
    format_flood_summary,
    reset_throttle,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_alarm(equipment: str = "Roof Atrium Extract Fan", **overrides) -> DesigoBuildingAlarm:
    defaults = {
        "id": "test-001",
        "site_id": "FLN02",
        "building": "Fairland 2",
        "raw_subject": f"{equipment} Fail Status (Fault)",
        "raw_body": "body",
        "equipment_description": equipment,
        "alarm_type": "Fail Status",
        "status": "Fault",
        "severity": AlarmSeverity.CRITICAL,
        "equipment_category": "hvac",
        "received_at": datetime(2026, 3, 7, 10, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return DesigoBuildingAlarm(**defaults)


@pytest.fixture(autouse=True)
def _reset():
    """Reset singleton throttle between tests."""
    reset_throttle()
    yield
    reset_throttle()


# ---------------------------------------------------------------------------
# Normal flow
# ---------------------------------------------------------------------------


def test_normal_alarm_sends():
    """Single alarm below flood threshold returns SEND."""
    throttle = NotificationThrottle(flood_threshold=5)
    alarm = _make_alarm()
    decision = throttle.check_alarm(alarm)
    assert decision.action == ThrottleAction.SEND


def test_multiple_different_equipment_sends():
    """Different equipment descriptions don't trigger flood."""
    throttle = NotificationThrottle(flood_threshold=3)
    for i in range(5):
        alarm = _make_alarm(equipment=f"Equipment-{i}")
        decision = throttle.check_alarm(alarm)
        assert decision.action == ThrottleAction.SEND


# ---------------------------------------------------------------------------
# Flood detection
# ---------------------------------------------------------------------------


def test_flood_triggers_summary():
    """Exceeding flood threshold sends SEND_FLOOD_SUMMARY on the Nth alarm."""
    throttle = NotificationThrottle(flood_threshold=3, flood_window_minutes=10)
    equipment = "AHU 1 Reheat OHS"

    # First 2 alarms: normal
    for _ in range(2):
        d = throttle.check_alarm(_make_alarm(equipment=equipment))
        assert d.action == ThrottleAction.SEND

    # 3rd alarm: triggers flood summary
    d = throttle.check_alarm(_make_alarm(equipment=equipment))
    assert d.action == ThrottleAction.SEND_FLOOD_SUMMARY
    assert d.flood_count == 3
    assert d.equipment == equipment


def test_flood_suppresses_after_summary():
    """After flood summary sent, subsequent alarms are suppressed."""
    throttle = NotificationThrottle(flood_threshold=3, flood_window_minutes=10)
    equipment = "FD 5"

    # Trigger flood
    for _ in range(3):
        throttle.check_alarm(_make_alarm(equipment=equipment))

    # 4th and 5th alarms: suppressed
    for _ in range(2):
        d = throttle.check_alarm(_make_alarm(equipment=equipment))
        assert d.action == ThrottleAction.SUPPRESS
        assert "suppressed" in d.reason.lower()


def test_flood_only_one_summary():
    """Only one flood summary is sent per flood episode."""
    throttle = NotificationThrottle(flood_threshold=3, flood_window_minutes=10)
    equipment = "Generator 1"

    summaries = 0
    for _ in range(10):
        d = throttle.check_alarm(_make_alarm(equipment=equipment))
        if d.action == ThrottleAction.SEND_FLOOD_SUMMARY:
            summaries += 1

    assert summaries == 1


def test_flood_status_api():
    """get_flood_status returns correct tracking data."""
    throttle = NotificationThrottle(flood_threshold=3, flood_window_minutes=10)
    equipment = "UPS Room"

    for _ in range(4):
        throttle.check_alarm(_make_alarm(equipment=equipment))

    status = throttle.get_flood_status()
    assert equipment in status
    assert status[equipment]["flood_active"] is True
    assert status[equipment]["recent_alarms"] == 4
    assert status[equipment]["suppressed_count"] == 1  # 4th alarm suppressed


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_rate_limit_blocks_after_threshold():
    """After N sends in an hour, further notifications are suppressed."""
    throttle = NotificationThrottle(flood_threshold=100, hourly_limit=5)

    # Record 5 sends
    for _ in range(5):
        throttle.record_send()

    # Next alarm should be rate-limited
    d = throttle.check_alarm(_make_alarm(equipment="equip-unique"))
    assert d.action == ThrottleAction.SUPPRESS
    assert "rate limit" in d.reason.lower()


def test_rate_limit_status_api():
    """get_rate_status returns correct counts."""
    throttle = NotificationThrottle(hourly_limit=30)

    for _ in range(5):
        throttle.record_send()

    status = throttle.get_rate_status()
    assert status["messages_this_hour"] == 5
    assert status["hourly_limit"] == 30
    assert status["remaining"] == 25


# ---------------------------------------------------------------------------
# Flood summary formatting
# ---------------------------------------------------------------------------


def test_format_flood_summary_content():
    """Flood summary message contains equipment name, count, and sensor fault warning."""
    msg = format_flood_summary("Roof Atrium Extract Fan", 47, 10)
    assert "ALARM FLOOD DETECTED" in msg
    assert "Roof Atrium Extract Fan" in msg
    assert "47 alarms" in msg
    assert "10 minutes" in msg
    assert "sensor fault" in msg.lower()


def test_format_flood_summary_has_warning_emoji():
    """Flood summary starts with warning emoji."""
    msg = format_flood_summary("Test", 5, 10)
    assert msg.startswith("\u26a0")
