"""API tests for Block Booking Detection endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.booking_record import BlockBookingAlert


@pytest.fixture
def client():
    """Create a test client with auth bypass."""
    from app.main import app

    return TestClient(app)


SAMPLE_EMAIL = """\
From: Shaun Grose <shaun@example.com>
To: boardroom1@resource.example.com
Subject: Accepted: Project Review - Boardroom 1
Content-Type: text/plain; charset="utf-8"

Location: Boardroom 1
Start: Monday, 02 March 2026 09:00
End: Monday, 02 March 2026 11:00
"""

ALERT_ID = str(uuid.uuid4())
MOCK_ALERT = BlockBookingAlert(
    id=ALERT_ID,
    site_id="site-002",
    organiser_email="shaun@example.com",
    organiser_name="Shaun Grose",
    overlap_window_start=datetime(2026, 3, 2, 9, 0),
    overlap_window_end=datetime(2026, 3, 2, 11, 0),
    rooms=["Boardroom 1", "Boardroom 2"],
    room_count=2,
    booking_ids=["b1", "b2"],
    detected_at=datetime(2026, 3, 1, 15, 0),
    notification_sent=True,
    dismissed=False,
)


# 9. GET /api/block-bookings/alerts
class TestListAlerts:
    @patch(
        "app.services.block_booking_detector.booking_store.get_booking_store",
    )
    def test_list_open_alerts(self, mock_get_store, client):
        mock_store = MagicMock()
        mock_store.get_open_alerts.return_value = [MOCK_ALERT]
        mock_get_store.return_value = mock_store

        response = client.get(
            "/api/block-bookings/alerts",
            params={"site_id": "site-002"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["alerts"][0]["organiser_email"] == "shaun@example.com"
        assert data["alerts"][0]["room_count"] == 2


# 10. POST /api/block-bookings/alerts/{id}/dismiss
class TestDismissAlert:
    @patch(
        "app.services.block_booking_detector.booking_store.get_booking_store",
    )
    def test_dismiss_alert(self, mock_get_store, client):
        dismissed_alert = BlockBookingAlert(
            id=ALERT_ID,
            site_id="site-002",
            organiser_email="shaun@example.com",
            organiser_name="Shaun Grose",
            overlap_window_start=datetime(2026, 3, 2, 9, 0),
            overlap_window_end=datetime(2026, 3, 2, 11, 0),
            rooms=["Boardroom 1", "Boardroom 2"],
            room_count=2,
            booking_ids=["b1", "b2"],
            dismissed=True,
            dismissed_at=datetime(2026, 3, 2, 12, 0),
            dismissed_by="concierge@example.com",
        )
        mock_store = MagicMock()
        mock_store.dismiss_alert.return_value = dismissed_alert
        mock_get_store.return_value = mock_store

        response = client.post(
            f"/api/block-bookings/alerts/{ALERT_ID}/dismiss",
            json={"dismissed_by": "concierge@example.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["dismissed"] is True
        assert data["dismissed_by"] == "concierge@example.com"

    @patch(
        "app.services.block_booking_detector.booking_store.get_booking_store",
    )
    def test_dismiss_nonexistent_alert_404(self, mock_get_store, client):
        mock_store = MagicMock()
        mock_store.dismiss_alert.return_value = None
        mock_get_store.return_value = mock_store

        response = client.post(
            f"/api/block-bookings/alerts/{uuid.uuid4()}/dismiss",
            json={"dismissed_by": "concierge@example.com"},
        )
        assert response.status_code == 404
