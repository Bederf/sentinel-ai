"""API integration tests for app.plant.plant_alerts router."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.plant.models import AlarmSeverity, DesigoBuildingAlarm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_SENDER = "noreply@fnb.co.za"

_VALID_SUBJECT = "AHU B2-AHU-01 Fail Status (Fault)"
_VALID_BODY = "Building: Fairland 2\nEquipment: AHU B2-AHU-01\nAlarm: Fail Status High\n"


def _make_alarm(**overrides) -> DesigoBuildingAlarm:
    defaults = {
        "id": "test-api-alarm-001",
        "site_id": "FLN02",
        "building": "Fairland 2",
        "raw_subject": _VALID_SUBJECT,
        "raw_body": _VALID_BODY,
        "equipment_description": "AHU B2-AHU-01",
        "alarm_type": "Fail Status",
        "status": "Fault",
        "severity": AlarmSeverity.CRITICAL,
        "equipment_category": "hvac",
        "received_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return DesigoBuildingAlarm(**defaults)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """Create a TestClient with PLANT_ALERTS_ENABLED=true."""
    import os

    os.environ["PLANT_ALERTS_ENABLED"] = "true"

    # Re-import to pick up env override.  We import the router directly
    # rather than the full app to keep tests lightweight and isolated.
    from app.plant.plant_alerts import router

    from fastapi import FastAPI

    test_app = FastAPI()
    test_app.include_router(router)
    yield TestClient(test_app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@patch("app.plant.plant_alerts.send_plant_alert", new_callable=AsyncMock, return_value=False)
@patch("app.plant.plant_alerts.alarm_store")
def test_ingest_valid_email(mock_store, mock_whatsapp, client):
    """POST valid Desigo email returns 200 with alarm_id."""
    mock_store.check_duplicate = AsyncMock(return_value=False)
    mock_store.save_alarm = AsyncMock(return_value=True)
    mock_store.mark_notified = AsyncMock(return_value=True)

    resp = client.post(
        "/api/plant/alerts/ingest",
        json={
            "from_address": _VALID_SENDER,
            "subject": _VALID_SUBJECT,
            "body": _VALID_BODY,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "alarm_id" in data
    assert data["severity"] in ["critical", "very_critical", "non_critical", "cleared"]
    assert "equipment" in data
    mock_store.save_alarm.assert_awaited_once()


@patch("app.plant.plant_alerts.send_plant_alert", new_callable=AsyncMock, return_value=False)
@patch("app.plant.plant_alerts.alarm_store")
def test_ingest_wrong_sender(mock_store, mock_whatsapp, client):
    """POST from wrong sender address returns 403."""
    resp = client.post(
        "/api/plant/alerts/ingest",
        json={
            "from_address": "attacker@evil.com",
            "subject": _VALID_SUBJECT,
            "body": _VALID_BODY,
        },
    )
    assert resp.status_code == 403
    assert "not authorised" in resp.json()["detail"].lower()


@patch("app.plant.plant_alerts.send_plant_alert", new_callable=AsyncMock, return_value=False)
@patch("app.plant.plant_alerts.alarm_store")
def test_ingest_empty_subject(mock_store, mock_whatsapp, client):
    """POST with empty subject returns 400."""
    resp = client.post(
        "/api/plant/alerts/ingest",
        json={
            "from_address": _VALID_SENDER,
            "subject": "",
            "body": _VALID_BODY,
        },
    )
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


@patch("app.plant.plant_alerts.send_plant_alert", new_callable=AsyncMock, return_value=False)
@patch("app.plant.plant_alerts.alarm_store")
def test_ingest_duplicate(mock_store, mock_whatsapp, client):
    """POST same subject twice within dedup window returns 409."""
    mock_store.check_duplicate = AsyncMock(return_value=True)

    resp = client.post(
        "/api/plant/alerts/ingest",
        json={
            "from_address": _VALID_SENDER,
            "subject": _VALID_SUBJECT,
            "body": _VALID_BODY,
        },
    )
    assert resp.status_code == 409
    assert "duplicate" in resp.json()["detail"].lower()


@patch("app.plant.plant_alerts.alarm_store")
def test_get_recent_alarms(mock_store, client):
    """GET /api/plant/alerts returns list of alarms."""
    alarm = _make_alarm()
    mock_store.get_recent_alarms = AsyncMock(return_value=[alarm])

    resp = client.get("/api/plant/alerts/")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == "test-api-alarm-001"


@patch("app.plant.plant_alerts.alarm_store")
def test_get_single_alarm(mock_store, client):
    """GET /api/plant/alerts/{id} returns alarm detail."""
    alarm = _make_alarm(id="single-lookup-001")
    mock_store.get_recent_alarms = AsyncMock(return_value=[alarm])

    resp = client.get("/api/plant/alerts/single-lookup-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "single-lookup-001"


@patch("app.plant.plant_alerts.alarm_store")
def test_get_single_alarm_not_found(mock_store, client):
    """GET /api/plant/alerts/{id} returns 404 for unknown alarm."""
    mock_store.get_recent_alarms = AsyncMock(return_value=[])

    resp = client.get("/api/plant/alerts/nonexistent-id")
    assert resp.status_code == 404


@patch("app.plant.plant_alerts.alarm_store")
def test_acknowledge_alarm(mock_store, client):
    """POST /api/plant/alerts/{id}/acknowledge marks alarm as acknowledged."""
    mock_store.mark_notified = AsyncMock(return_value=True)

    resp = client.post("/api/plant/alerts/ack-001/acknowledge")
    assert resp.status_code == 200
    data = resp.json()
    assert data["alarm_id"] == "ack-001"
    assert data["acknowledged"] is True
    mock_store.mark_notified.assert_awaited_once_with("ack-001")
