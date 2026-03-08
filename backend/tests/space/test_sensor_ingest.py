"""Tests for sensor_ingest.py — FastAPI router for event ingestion and queries."""

from __future__ import annotations

import os
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch


os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.space.sensor_ingest import router

# ---------------------------------------------------------------------------
# Lightweight test app (avoids loading full main.py)
# ---------------------------------------------------------------------------
_app = FastAPI()
_app.include_router(router, tags=["space-occupancy"])

VALID_TOKEN = "tkn_FA2-1Q1-MR-01_a3f9c2"
VALID_ROOM = "FA2-1Q1-MR-01"
VALID_SENSOR = "LD2410C-FA2-1Q1-MR-01"

DEVICE_RECORD = {
    "device_token": VALID_TOKEN,
    "room_code": VALID_ROOM,
    "sensor_id": VALID_SENSOR,
    "site_id": "FLN02",
    "enabled": True,
}

DISABLED_DEVICE = {**DEVICE_RECORD, "enabled": False}


def _make_payload(
    occupied: bool = True,
    event_type: str = "state_change",
    room_code: str = VALID_ROOM,
) -> dict:
    return {
        "device_token": VALID_TOKEN,
        "room_code": room_code,
        "sensor_id": VALID_SENSOR,
        "occupied": occupied,
        "event_type": event_type,
        "rssi": -55,
        "uptime_seconds": 3600,
        "firmware_version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sync_request(method: str, url: str, **kwargs):
    async def _do():
        transport = ASGITransport(app=_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, url, **kwargs)

    return asyncio.run(_do())


# ---------------------------------------------------------------------------
# Tests — POST /api/space/events
# ---------------------------------------------------------------------------


@patch("app.space.sensor_ingest.repo")
def test_valid_state_change_accepted(mock_repo):
    mock_repo.get_device_by_token = AsyncMock(return_value=DEVICE_RECORD)
    mock_repo.insert_room_event = AsyncMock()
    mock_repo.update_device_last_seen = AsyncMock()
    mock_repo.get_room_current_state = AsyncMock(return_value=None)
    mock_repo.upsert_room_current_state = AsyncMock()
    mock_repo.insert_finding = AsyncMock()
    mock_repo.resolve_finding = AsyncMock()

    resp = _sync_request(
        "POST",
        "/api/space/events",
        json=_make_payload(occupied=True, event_type="state_change"),
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["received"] is True
    assert "server_time" in data
    mock_repo.insert_room_event.assert_called_once()
    mock_repo.upsert_room_current_state.assert_called_once()


@patch("app.space.sensor_ingest.repo")
def test_valid_heartbeat_accepted(mock_repo):
    mock_repo.get_device_by_token = AsyncMock(return_value=DEVICE_RECORD)
    mock_repo.insert_room_event = AsyncMock()
    mock_repo.update_device_last_seen = AsyncMock()
    mock_repo.get_room_current_state = AsyncMock(return_value=None)
    mock_repo.upsert_room_current_state = AsyncMock()
    mock_repo.insert_finding = AsyncMock()
    mock_repo.resolve_finding = AsyncMock()

    resp = _sync_request(
        "POST",
        "/api/space/events",
        json=_make_payload(occupied=False, event_type="heartbeat"),
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert resp.status_code == 200
    assert resp.json()["received"] is True


@patch("app.space.sensor_ingest.repo")
def test_invalid_token_returns_401(mock_repo):
    mock_repo.get_device_by_token = AsyncMock(return_value=None)

    resp = _sync_request(
        "POST",
        "/api/space/events",
        json=_make_payload(),
        headers={"Authorization": "Bearer bad_token_xyz"},
    )
    assert resp.status_code == 401


def test_missing_auth_header_returns_401():
    resp = _sync_request(
        "POST",
        "/api/space/events",
        json=_make_payload(),
    )
    assert resp.status_code == 401


@patch("app.space.sensor_ingest.repo")
def test_wrong_room_code_for_token_returns_403(mock_repo):
    mock_repo.get_device_by_token = AsyncMock(return_value=DEVICE_RECORD)

    resp = _sync_request(
        "POST",
        "/api/space/events",
        json=_make_payload(room_code="FA2-1Q1-MR-99"),
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert resp.status_code == 403


@patch("app.space.sensor_ingest.repo")
def test_disabled_device_returns_403(mock_repo):
    mock_repo.get_device_by_token = AsyncMock(return_value=DISABLED_DEVICE)

    resp = _sync_request(
        "POST",
        "/api/space/events",
        json=_make_payload(),
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert resp.status_code == 403


@patch("app.space.sensor_ingest.repo")
def test_state_change_updates_current_state(mock_repo):
    mock_repo.get_device_by_token = AsyncMock(return_value=DEVICE_RECORD)
    mock_repo.insert_room_event = AsyncMock()
    mock_repo.update_device_last_seen = AsyncMock()
    mock_repo.get_room_current_state = AsyncMock(return_value=None)
    mock_repo.upsert_room_current_state = AsyncMock()
    mock_repo.insert_finding = AsyncMock()
    mock_repo.resolve_finding = AsyncMock()

    resp = _sync_request(
        "POST",
        "/api/space/events",
        json=_make_payload(occupied=True, event_type="state_change"),
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert resp.status_code == 200

    call_args = mock_repo.upsert_room_current_state.call_args[0][0]
    assert call_args["occupied"] is True
    assert call_args["last_event_type"] == "state_change"
    assert call_args["occupied_since"] is not None
    assert call_args["sensor_online"] is True


@patch("app.space.sensor_ingest.repo")
def test_heartbeat_updates_last_seen(mock_repo):
    mock_repo.get_device_by_token = AsyncMock(return_value=DEVICE_RECORD)
    mock_repo.insert_room_event = AsyncMock()
    mock_repo.update_device_last_seen = AsyncMock()
    mock_repo.get_room_current_state = AsyncMock(return_value=None)
    mock_repo.upsert_room_current_state = AsyncMock()
    mock_repo.insert_finding = AsyncMock()
    mock_repo.resolve_finding = AsyncMock()

    resp = _sync_request(
        "POST",
        "/api/space/events",
        json=_make_payload(event_type="heartbeat"),
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert resp.status_code == 200
    mock_repo.update_device_last_seen.assert_called_once()


# ---------------------------------------------------------------------------
# Tests — GET endpoints
# ---------------------------------------------------------------------------


@patch("app.space.sensor_ingest.repo")
def test_get_rooms_returns_all_rooms(mock_repo):
    mock_repo.get_all_room_states = AsyncMock(
        return_value=[
            {"room_code": "FA2-1Q1-MR-01", "site_id": "FLN02", "occupied": True, "sensor_online": True},
            {"room_code": "FA2-1Q1-MR-02", "site_id": "FLN02", "occupied": False, "sensor_online": True},
        ]
    )
    resp = _sync_request("GET", "/api/space/rooms")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["room_code"] == "FA2-1Q1-MR-01"
    assert data[0]["occupied"] is True


@patch("app.space.sensor_ingest.repo")
def test_get_room_detail(mock_repo):
    mock_repo.get_room_current_state = AsyncMock(
        return_value={
            "room_code": "FA2-1Q1-MR-01",
            "site_id": "FLN02",
            "occupied": False,
            "sensor_online": True,
            "last_heartbeat_at": "2026-03-08T10:00:00+00:00",
        }
    )
    resp = _sync_request("GET", "/api/space/rooms/FA2-1Q1-MR-01")
    assert resp.status_code == 200
    data = resp.json()
    assert data["room_code"] == "FA2-1Q1-MR-01"
    assert data["occupied"] is False


@patch("app.space.sensor_ingest.repo")
def test_get_devices(mock_repo):
    mock_repo.get_all_devices = AsyncMock(
        return_value=[
            {
                "device_token": VALID_TOKEN,
                "room_code": VALID_ROOM,
                "sensor_id": VALID_SENSOR,
                "site_id": "FLN02",
                "enabled": True,
            },
        ]
    )
    resp = _sync_request("GET", "/api/space/devices")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    # Token should be masked
    assert "***" in data[0]["device_token"]
    assert data[0]["device_token"] != VALID_TOKEN
