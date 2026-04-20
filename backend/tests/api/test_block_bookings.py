"""API tests for Block Booking Detection endpoints."""

from __future__ import annotations

import os

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.booking_record import BlockBookingAlert, BookingRecord


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

SITE_002_EMAIL = """\
From: Rooms Scheduler <rooms@sentinel-ai.co.za>
To: rooms@sentinel-ai.co.za
Subject: Accepted: Site 002 planning session
Content-Type: text/plain; charset="utf-8"

Organizer: Shaun Grose <shaun@example.com>
Location: S002-L1-MR1
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


class TestIngestBookingEmail:
    @patch("app.services.block_booking_detector.booking_store.get_booking_store")
    @patch("app.services.block_booking_detector.notifier.send_block_booking_alert")
    def test_ingest_routes_to_site_from_room_identity(self, mock_send_alert, mock_get_store, client):
        mock_store = MagicMock()
        mock_store.booking_exists.return_value = False
        mock_store.get_bookings_for_site.return_value = []
        mock_get_store.return_value = mock_store

        response = client.post(
            "/api/block-bookings/ingest",
            json={"raw_email": SITE_002_EMAIL},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["action"] == "booking_ingested"
        assert data["alerts_generated"] == 0
        saved_record = mock_store.save_booking.call_args.args[0]
        assert saved_record.site_id == "site-002"
        mock_store.get_bookings_for_site.assert_called_once_with("site-002", saved_record.booking_date)
        mock_store.flag_bookings.assert_not_called()

    @patch("app.services.block_booking_detector.booking_store.get_booking_store")
    @patch("app.services.block_booking_detector.notifier.send_block_booking_alert")
    def test_ingest_rejects_explicit_site_mismatch(self, mock_send_alert, mock_get_store, client):
        mock_store = MagicMock()
        mock_get_store.return_value = mock_store

        response = client.post(
            "/api/block-bookings/ingest",
            json={"raw_email": SITE_002_EMAIL, "site_id": "site-001"},
        )

        assert response.status_code == 400
        assert "site-002" in response.json()["detail"]

    @patch("app.services.block_booking_detector.booking_store.get_booking_store")
    @patch("app.services.block_booking_detector.notifier.send_block_booking_alert")
    @patch("app.services.block_booking_detector.overlap_detector.detect_overlaps")
    def test_ingest_flags_bookings_when_alert_is_created(
        self, mock_detect_overlaps, mock_send_alert, mock_get_store, client
    ):
        booking = BookingRecord(
            id="booking-001",
            site_id="site-002",
            organiser_email="shaun@example.com",
            organiser_name="Shaun Grose",
            room_id="S002-L1-MR1",
            room_name="S002-L1-MR1",
            booking_date=datetime(2026, 3, 2).date(),
            start_time=datetime(2026, 3, 2, 9, 0),
            end_time=datetime(2026, 3, 2, 17, 0),
            raw_email_hash="hash-001",
        )
        alert = BlockBookingAlert(
            id="alert-001",
            site_id="site-002",
            organiser_email="shaun@example.com",
            organiser_name="Shaun Grose",
            overlap_window_start=datetime(2026, 3, 2, 9, 0),
            overlap_window_end=datetime(2026, 3, 2, 17, 0),
            rooms=["S002-L1-MR1", "S002-L2-MR1", "S002-L3-MR1"],
            room_count=3,
            booking_ids=["booking-001", "booking-002", "booking-003"],
        )
        mock_store = MagicMock()
        mock_store.booking_exists.return_value = False
        mock_store.save_booking.return_value = booking
        mock_store.get_bookings_for_site.return_value = [booking]
        mock_store.save_alert.return_value = alert
        mock_get_store.return_value = mock_store
        mock_detect_overlaps.return_value = [alert]
        mock_send_alert.return_value = True

        response = client.post(
            "/api/block-bookings/ingest",
            json={"raw_email": SITE_002_EMAIL},
        )

        assert response.status_code == 200
        assert response.json()["alerts_generated"] == 1
        mock_store.flag_bookings.assert_called_once_with(["booking-001", "booking-002", "booking-003"])
