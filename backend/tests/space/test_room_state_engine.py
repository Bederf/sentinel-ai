"""Tests for room_state_engine.py — rules engine for space occupancy."""

from __future__ import annotations

import os
import asyncio
from datetime import datetime, timedelta, timezone


os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")

from app.space.models import SensorEventPayload
from app.space.room_state_engine import evaluate_room_state


def _make_event(
    occupied: bool = True,
    event_type: str = "state_change",
    room_code: str = "FA1-1Q1-MR1",
) -> SensorEventPayload:
    return SensorEventPayload(
        device_token="tkn_test",
        room_code=room_code,
        sensor_id="LD2410C-test",
        occupied=occupied,
        event_type=event_type,
        timestamp=datetime.now(timezone.utc),
    )


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Rule 1: ghost_booking
# ---------------------------------------------------------------------------


def test_ghost_booking_detected_after_grace():
    """Ghost booking: room empty >20 min after booking start."""
    now = datetime.now(timezone.utc)
    booking = {
        "active_booking": True,
        "booking_start": (now - timedelta(minutes=25)).isoformat(),
        "booking_end": (now + timedelta(minutes=35)).isoformat(),
    }
    state = {"site_id": "FLN02", "sensor_online": True, "last_heartbeat_at": now.isoformat()}
    event = _make_event(occupied=False)

    findings = _run(evaluate_room_state("FA1-1Q1-MR1", state, event, booking_data=booking))
    types = [f.finding_type for f in findings]
    assert "ghost_booking" in types


def test_ghost_booking_not_detected_within_grace():
    """No ghost booking within the configured grace period."""
    from app.space.room_state_engine import GHOST_BOOKING_GRACE_MINUTES

    now = datetime.now(timezone.utc)
    # Use half the configured grace period so we're clearly within it
    minutes_elapsed = max(1, GHOST_BOOKING_GRACE_MINUTES // 2)
    booking = {
        "active_booking": True,
        "booking_start": (now - timedelta(minutes=minutes_elapsed)).isoformat(),
        "booking_end": (now + timedelta(minutes=50)).isoformat(),
    }
    state = {"site_id": "FLN02", "sensor_online": True, "last_heartbeat_at": now.isoformat()}
    event = _make_event(occupied=False)

    findings = _run(evaluate_room_state("FA1-1Q1-MR1", state, event, booking_data=booking))
    types = [f.finding_type for f in findings]
    assert "ghost_booking" not in types


def test_no_ghost_booking_when_no_booking_data():
    """Booking-dependent rules silently skip when booking_data is None."""
    now = datetime.now(timezone.utc)
    state = {"site_id": "FLN02", "sensor_online": True, "last_heartbeat_at": now.isoformat()}
    event = _make_event(occupied=False)

    findings = _run(evaluate_room_state("FA1-1Q1-MR1", state, event, booking_data=None))
    types = [f.finding_type for f in findings]
    assert "ghost_booking" not in types
    assert "overstay" not in types
    assert "early_vacate" not in types


# ---------------------------------------------------------------------------
# Rule 2: overstay
# ---------------------------------------------------------------------------


def test_overstay_detected():
    """Overstay: room occupied >15 min after last booking ended."""
    now = datetime.now(timezone.utc)
    booking = {
        "active_booking": False,
        "last_booking_end": (now - timedelta(minutes=20)).isoformat(),
    }
    state = {"site_id": "FLN02", "sensor_online": True, "last_heartbeat_at": now.isoformat()}
    event = _make_event(occupied=True)

    findings = _run(evaluate_room_state("FA1-1Q1-MR1", state, event, booking_data=booking))
    types = [f.finding_type for f in findings]
    assert "overstay" in types


def test_overstay_not_detected_within_grace():
    """No overstay within 15-min grace."""
    now = datetime.now(timezone.utc)
    booking = {
        "active_booking": False,
        "last_booking_end": (now - timedelta(minutes=10)).isoformat(),
    }
    state = {"site_id": "FLN02", "sensor_online": True, "last_heartbeat_at": now.isoformat()}
    event = _make_event(occupied=True)

    findings = _run(evaluate_room_state("FA1-1Q1-MR1", state, event, booking_data=booking))
    types = [f.finding_type for f in findings]
    assert "overstay" not in types


# ---------------------------------------------------------------------------
# Rule 3: early_vacate
# ---------------------------------------------------------------------------


def test_early_vacate_detected():
    """Early vacate: room empty with >90 min remaining on booking."""
    now = datetime.now(timezone.utc)
    booking = {
        "active_booking": True,
        "booking_start": (now - timedelta(minutes=10)).isoformat(),
        "booking_end": (now + timedelta(minutes=110)).isoformat(),
    }
    state = {"site_id": "FLN02", "sensor_online": True, "last_heartbeat_at": now.isoformat()}
    event = _make_event(occupied=False)

    findings = _run(evaluate_room_state("FA1-1Q1-MR1", state, event, booking_data=booking))
    types = [f.finding_type for f in findings]
    assert "early_vacate" in types


def test_early_vacate_not_detected_within_threshold():
    """No early_vacate when <90 min remaining."""
    now = datetime.now(timezone.utc)
    booking = {
        "active_booking": True,
        "booking_start": (now - timedelta(minutes=30)).isoformat(),
        "booking_end": (now + timedelta(minutes=30)).isoformat(),
    }
    state = {"site_id": "FLN02", "sensor_online": True, "last_heartbeat_at": now.isoformat()}
    event = _make_event(occupied=False)

    findings = _run(evaluate_room_state("FA1-1Q1-MR1", state, event, booking_data=booking))
    types = [f.finding_type for f in findings]
    assert "early_vacate" not in types


# ---------------------------------------------------------------------------
# Rule 4: sensor_offline
# ---------------------------------------------------------------------------


def test_sensor_offline_detected():
    """Sensor offline when last heartbeat exceeds threshold."""
    now = datetime.now(timezone.utc)
    state = {
        "site_id": "FLN02",
        "sensor_online": True,
        "last_heartbeat_at": (now - timedelta(seconds=200)).isoformat(),
    }
    event = _make_event(event_type="heartbeat")

    findings = _run(evaluate_room_state("FA1-1Q1-MR1", state, event))
    types = [f.finding_type for f in findings]
    assert "sensor_offline" in types


# ---------------------------------------------------------------------------
# Rule 5: sensor_recovery
# ---------------------------------------------------------------------------


def test_sensor_recovery_creates_finding():
    """Recovery finding when sensor was offline and new event arrives."""
    now = datetime.now(timezone.utc)
    state = {
        "site_id": "FLN02",
        "sensor_online": False,
        "last_heartbeat_at": (now - timedelta(seconds=300)).isoformat(),
    }
    event = _make_event(event_type="heartbeat")

    findings = _run(evaluate_room_state("FA1-1Q1-MR1", state, event))
    types = [f.finding_type for f in findings]
    assert "sensor_recovery" in types


# ---------------------------------------------------------------------------
# Normal operation
# ---------------------------------------------------------------------------


def test_no_findings_for_normal_heartbeat():
    """No findings when sensor is online and heartbeat is within threshold."""
    now = datetime.now(timezone.utc)
    state = {
        "site_id": "FLN02",
        "sensor_online": True,
        "last_heartbeat_at": (now - timedelta(seconds=30)).isoformat(),
    }
    event = _make_event(occupied=True, event_type="heartbeat")

    findings = _run(evaluate_room_state("FA1-1Q1-MR1", state, event))
    assert len(findings) == 0
