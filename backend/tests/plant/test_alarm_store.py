"""Tests for app.plant.alarm_store — JSON fallback, CRUD, duplicate detection."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.plant.alarm_store import (
    check_duplicate,
    get_recent_alarms,
    mark_cleared,
    mark_notified,
    save_alarm,
)
from app.plant.models import AlarmSeverity, DesigoBuildingAlarm

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_alarm(**overrides) -> DesigoBuildingAlarm:
    defaults = {
        "id": "test-alarm-001",
        "site_id": "FLN02",
        "building": "Block A",
        "raw_subject": "FLN02: Fire Damper Fail",
        "raw_body": "Fire damper B2-FD-01 fault detected",
        "equipment_description": "Fire Damper B2-FD-01",
        "alarm_type": "Fail Status",
        "status": "Fault",
        "severity": AlarmSeverity.CRITICAL,
        "equipment_category": "fire_safety",
        "received_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return DesigoBuildingAlarm(**defaults)


@pytest.fixture(autouse=True)
def _clean_json(tmp_path, monkeypatch):
    """Redirect JSON storage to a temp file and ensure Supabase is unavailable."""
    tmp_json = tmp_path / "building_alarms.json"
    tmp_json.write_text("[]", encoding="utf-8")
    monkeypatch.setattr("app.plant.alarm_store._JSON_PATH", tmp_json)
    # Force JSON fallback by making _get_supabase return None
    monkeypatch.setattr("app.plant.alarm_store._get_supabase", lambda: None)
    yield tmp_json


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_alarm_json_fallback(_clean_json):
    """save_alarm persists to JSON when Supabase is unavailable."""
    alarm = _make_alarm()
    result = await save_alarm(alarm)
    assert result is True

    records = json.loads(_clean_json.read_text())
    assert len(records) == 1
    assert records[0]["id"] == "test-alarm-001"
    assert records[0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_get_recent_alarms_json(_clean_json):
    """get_recent_alarms returns alarms from JSON sorted by received_at desc."""
    now = datetime.now(UTC)
    a1 = _make_alarm(id="a1", received_at=now - timedelta(hours=2))
    a2 = _make_alarm(id="a2", received_at=now - timedelta(hours=1))
    a3 = _make_alarm(id="a3", received_at=now)

    for a in [a1, a2, a3]:
        await save_alarm(a)

    results = await get_recent_alarms("FLN02", limit=2)
    assert len(results) == 2
    assert results[0].id == "a3"
    assert results[1].id == "a2"


@pytest.mark.asyncio
async def test_mark_notified(_clean_json):
    """mark_notified sets notified=True and notified_at in JSON."""
    alarm = _make_alarm()
    await save_alarm(alarm)

    result = await mark_notified("test-alarm-001")
    assert result is True

    records = json.loads(_clean_json.read_text())
    assert records[0]["notified"] is True
    assert records[0]["notified_at"] is not None


@pytest.mark.asyncio
async def test_mark_cleared(_clean_json):
    """mark_cleared sets cleared=True and cleared_at in JSON."""
    alarm = _make_alarm()
    await save_alarm(alarm)

    result = await mark_cleared("test-alarm-001")
    assert result is True

    records = json.loads(_clean_json.read_text())
    assert records[0]["cleared"] is True
    assert records[0]["cleared_at"] is not None


@pytest.mark.asyncio
async def test_check_duplicate_within_window(_clean_json):
    """Same subject within 1 hour returns True."""
    alarm = _make_alarm(received_at=datetime.now(UTC) - timedelta(minutes=30))
    await save_alarm(alarm)

    is_dup = await check_duplicate("FLN02: Fire Damper Fail", window_hours=1)
    assert is_dup is True


@pytest.mark.asyncio
async def test_check_duplicate_outside_window(_clean_json):
    """Same subject older than window returns False."""
    alarm = _make_alarm(received_at=datetime.now(UTC) - timedelta(hours=2))
    await save_alarm(alarm)

    is_dup = await check_duplicate("FLN02: Fire Damper Fail", window_hours=1)
    assert is_dup is False
