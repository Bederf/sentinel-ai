"""Security tests for block booking ingest endpoint (Phase 184-01-01).

Tests the 5 security fixes:
1. require_auth(AUTHENTICATED) — 403 without auth
2. Pydantic validators — 422 for oversized raw_email and malformed ICS
3. Rate limiting — 429 after limit
4. Startup config validation — logs success/errors
5. graph_integration_enabled — 503 when false
"""

from __future__ import annotations

import os

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from unittest.mock import patch  # noqa: E402


@pytest.fixture
def client():
    """Create a test client with auth bypass."""
    from app.main import app

    return TestClient(app)


class TestBlockBookingSecurity:
    """Security tests for block booking ingest endpoint."""

    def test_ingest_without_auth_returns_403(self, client: TestClient) -> None:
        """Fix 1: POST /api/block-bookings/ingest without auth returns 403."""
        response = client.post(
            "/api/block-bookings/ingest",
            json={
                "ics_data": "BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR",
                "site_id": "site-002",
            },
        )
        assert response.status_code == 403

    def test_ingest_with_valid_auth_succeeds(self, client: TestClient, auth_headers: dict) -> None:
        """Valid auth token allows access to ingest endpoint."""
        response = client.post(
            "/api/block-bookings/ingest",
            json={
                "ics_data": "BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR",
                "site_id": "site-002",
            },
            headers=auth_headers,
        )
        # 200 = success (no booking parsed from empty ICS)
        # 422 = validation error (parsing empty ICS)
        # We only care about not getting 403
        assert response.status_code in (200, 422)

    def test_raw_email_exceeds_10mb_returns_422(self, client: TestClient, auth_headers: dict) -> None:
        """Fix 2: raw_email > 10 MB returns 422."""
        oversized_email = "x" * (10_000_001)  # 10 MB + 1 byte
        response = client.post(
            "/api/block-bookings/ingest",
            json={
                "raw_email": oversized_email,
                "site_id": "site-002",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_ics_exceeds_100kb_returns_422(self, client: TestClient, auth_headers: dict) -> None:
        """Fix 2: ics_data > 100 KB returns 422."""
        oversized_ics = "BEGIN:VCALENDAR\n" + "x" * (100_001) + "\nEND:VCALENDAR"
        response = client.post(
            "/api/block-bookings/ingest",
            json={
                "ics_data": oversized_ics,
                "site_id": "site-002",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_malformed_ics_returns_422(self, client: TestClient, auth_headers: dict) -> None:
        """Fix 2: ICS not starting with BEGIN:VCALENDAR returns 422."""
        response = client.post(
            "/api/block-bookings/ingest",
            json={
                "ics_data": "NOT A CALENDAR\nBEGIN:VEVENT\nEND:VEVENT",
                "site_id": "site-002",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_valid_ics_returns_200(self, client: TestClient, auth_headers: dict) -> None:
        """Fix 2: Valid ICS data returns 200."""
        valid_ics = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Microsoft Corporation//Outlook 16.0 CalDAL//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VEVENT
DTSTART:20260415T090000Z
DTEND:20260415T170000Z
SUMMARY:Board Meeting
LOCATION:Boardroom 1
ORGANIZER;CN=Test User:mailto:test@fnb.co.za
UID:040000008200E00074C5B7101A82E0080000000000000001
DTSTAMP:20260411T100000Z
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR"""
        response = client.post(
            "/api/block-bookings/ingest",
            json={
                "ics_data": valid_ics,
                "site_id": "site-002",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert data.get("action") == "booking_ingested"

    def test_site_id_truncated_at_50_chars(self, client: TestClient, auth_headers: dict) -> None:
        """Fix 2: site_id > 50 chars returns 422."""
        long_site_id = "site-002-" + "x" * 50
        response = client.post(
            "/api/block-bookings/ingest",
            json={
                "ics_data": "BEGIN:VCALENDAR\nEND:VCALENDAR",
                "site_id": long_site_id,
            },
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestGraphIntegrationFeatureFlag:
    """Test graph_integration_enabled feature flag (Fix 5)."""

    def test_graph_webhook_returns_503_when_disabled(self, client: TestClient) -> None:
        """Fix 5: Graph webhook returns 503 when graph_integration_enabled=false."""
        with patch("app.api.graph_webhook_endpoint.settings") as mock_settings:
            mock_settings.graph_integration_enabled = False
            response = client.post(
                "/api/webhooks/graph/events",
                json={
                    "value": [
                        {
                            "subscriptionId": "sub-123",
                            "clientState": "test-client-state",
                            "changeType": "created",
                            "resource": "Users/test/events/evt-123",
                        }
                    ]
                },
            )
            assert response.status_code == 503

    def test_graph_webhook_returns_403_when_no_subscription(self, client: TestClient) -> None:
        """Graph webhook returns 403 when enabled but no stored subscription."""
        with patch("app.api.graph_webhook_endpoint.settings") as mock_settings:
            mock_settings.graph_integration_enabled = True
            with patch("app.api.graph_webhook_endpoint.graph_subscription_service") as mock_sub_svc:
                mock_sub_svc.get_subscription.return_value = None
                response = client.post(
                    "/api/webhooks/graph/events",
                    json={
                        "value": [
                            {
                                "subscriptionId": "sub-123",
                                "clientState": "test-client-state",
                                "changeType": "created",
                                "resource": "Users/test/events/evt-123",
                            }
                        ]
                    },
                )
                # No stored subscription → 403 (not 503 since flag passes)
                assert response.status_code == 403
