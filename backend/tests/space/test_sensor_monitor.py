"""Tests for sensor_monitor.py — background sensor health checker."""

from __future__ import annotations

import os
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch


os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")

from app.space.sensor_monitor import check_sensor_health


def _run(coro):
    return asyncio.run(coro)


def _now():
    """Fresh timestamp for each test to avoid stale module-level NOW."""
    return datetime.now(timezone.utc)


@patch("app.space.sensor_monitor.repo")
def test_sensor_marked_offline_after_threshold(mock_repo):
    """A sensor with last_seen_at > 180s ago should be marked offline."""
    NOW = _now()
    device = {
        "sensor_id": "LD2410C-FA1-1Q1-MR1",
        "room_code": "FA1-1Q1-MR1",
        "enabled": True,
        "last_seen_at": (NOW - timedelta(seconds=200)).isoformat(),
    }
    current_state = {
        "room_code": "FA1-1Q1-MR1",
        "sensor_online": True,
    }

    mock_repo.get_all_devices = AsyncMock(return_value=[device])
    mock_repo.get_room_current_state = AsyncMock(return_value=current_state)
    mock_repo.upsert_room_current_state = AsyncMock()
    mock_repo.insert_finding = AsyncMock()
    mock_repo.resolve_finding = AsyncMock()

    result = _run(check_sensor_health(site_id="FLN02"))
    assert result["offline_detected"] == 1
    mock_repo.insert_finding.assert_called_once()
    finding_arg = mock_repo.insert_finding.call_args[0][0]
    assert finding_arg["finding_type"] == "sensor_offline"


@patch("app.space.sensor_monitor.repo")
def test_online_sensor_not_marked_offline(mock_repo):
    """A sensor with recent last_seen_at should NOT be marked offline."""
    NOW = _now()
    device = {
        "sensor_id": "LD2410C-FA1-1Q1-MR1",
        "room_code": "FA1-1Q1-MR1",
        "enabled": True,
        "last_seen_at": (NOW - timedelta(seconds=30)).isoformat(),
    }
    current_state = {
        "room_code": "FA1-1Q1-MR1",
        "sensor_online": True,
    }

    mock_repo.get_all_devices = AsyncMock(return_value=[device])
    mock_repo.get_room_current_state = AsyncMock(return_value=current_state)
    mock_repo.upsert_room_current_state = AsyncMock()
    mock_repo.insert_finding = AsyncMock()
    mock_repo.resolve_finding = AsyncMock()

    result = _run(check_sensor_health(site_id="FLN02"))
    assert result["offline_detected"] == 0
    mock_repo.insert_finding.assert_not_called()


@patch("app.space.sensor_monitor.repo")
def test_recovery_on_new_event(mock_repo):
    """A sensor that was offline but now has recent last_seen should be recovered."""
    NOW = _now()
    device = {
        "sensor_id": "LD2410C-FA1-1Q1-MR1",
        "room_code": "FA1-1Q1-MR1",
        "enabled": True,
        "last_seen_at": (NOW - timedelta(seconds=30)).isoformat(),
    }
    current_state = {
        "room_code": "FA1-1Q1-MR1",
        "sensor_online": False,  # was offline
    }

    mock_repo.get_all_devices = AsyncMock(return_value=[device])
    mock_repo.get_room_current_state = AsyncMock(return_value=current_state)
    mock_repo.upsert_room_current_state = AsyncMock()
    mock_repo.insert_finding = AsyncMock()
    mock_repo.resolve_finding = AsyncMock()

    result = _run(check_sensor_health(site_id="FLN02"))
    assert result["recovered"] == 1
    mock_repo.resolve_finding.assert_called_once_with("FA1-1Q1-MR1", "sensor_offline")

    # Verify state was set back to online
    upsert_call = mock_repo.upsert_room_current_state.call_args[0][0]
    assert upsert_call["sensor_online"] is True
