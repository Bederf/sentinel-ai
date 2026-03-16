"""
Acceptance tests for Concierge Intelligence Dashboard — S001 Fairlands.
Phase 161-05 — pass conditions from spec.

Covers the full pipeline: room registry, signal emission, room-signal mapping,
urgency scoring, API endpoints, and dashboard cards.
"""

from __future__ import annotations

import os
import re

import pytest

# Ensure demo mode before importing app
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """FastAPI TestClient with demo mode."""
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Role Assignment
# ---------------------------------------------------------------------------


class TestRoleAssignment:
    def test_thandi_role_assignment_exists(self, client):
        """Thandi must have a concierge role_assignment for Fairlands."""
        response = client.get("/api/concierge/dashboard/TDineka@fnb.co.za")
        assert response.status_code == 200
        data = response.json()
        assert data["person_email"] == "TDineka@fnb.co.za"
        assert data["role_type"] == "concierge"

    def test_thandi_dashboard_has_cards(self, client):
        """Thandi's dashboard must contain at least one card."""
        response = client.get("/api/concierge/dashboard/TDineka@fnb.co.za")
        assert response.status_code == 200
        data = response.json()
        assert len(data["cards"]) >= 1


# ---------------------------------------------------------------------------
# 2. Room Registry
# ---------------------------------------------------------------------------

ROOM_ID_PATTERN = re.compile(r"^FA\d-\d+Q\d+-(?:MR|PR)-\d+$")


class TestRoomRegistry:
    def test_room_registry_has_s001_rooms(self, client):
        """S001 must have at least 5 rooms registered."""
        response = client.get("/api/concierge/rooms/S001")
        assert response.status_code == 200
        rooms = response.json()["rooms"]
        assert len(rooms) >= 5

    def test_room_ids_follow_convention(self, client):
        """All room IDs must match FA convention (e.g. FA2-1Q1-MR-01)."""
        response = client.get("/api/concierge/rooms/S001")
        for room in response.json()["rooms"]:
            assert ROOM_ID_PATTERN.match(room["room_id"]), f"Bad room_id: {room['room_id']}"


# ---------------------------------------------------------------------------
# 3. Signal Emission
# ---------------------------------------------------------------------------


class TestSignalEmission:
    def test_block_booking_signal_emitted(self, client):
        """Block booking detector must produce booking_conflict signals."""
        response = client.get("/api/concierge/rooms/S001")
        rooms = response.json()["rooms"]
        all_signals = []
        for room in rooms:
            all_signals.extend(room.get("signals", []))
        conflict_types = [s for s in all_signals if s["signal_type"] == "booking_conflict"]
        assert len(conflict_types) >= 1, "Expected at least 1 booking_conflict signal"

    def test_ghost_booking_signal_emitted(self, client):
        """Ghost booking confirmation must produce no_show_pattern signal."""
        response = client.get("/api/concierge/rooms/S001")
        rooms = response.json()["rooms"]
        all_signals = []
        for room in rooms:
            all_signals.extend(room.get("signals", []))
        ghost_types = [s for s in all_signals if s["signal_type"] == "no_show_pattern"]
        assert len(ghost_types) >= 1, "Expected at least 1 no_show_pattern signal"

    def test_complaint_email_signal_present(self, client):
        """At least one complaint_email signal must be present in fixtures."""
        response = client.get("/api/concierge/rooms/S001")
        rooms = response.json()["rooms"]
        all_signals = []
        for room in rooms:
            all_signals.extend(room.get("signals", []))
        complaint_types = [s for s in all_signals if s["signal_type"] == "complaint_email"]
        assert len(complaint_types) >= 1, "Expected at least 1 complaint_email signal"


# ---------------------------------------------------------------------------
# 4. Concierge API Response Shape
# ---------------------------------------------------------------------------


class TestConciergeAPI:
    def test_rooms_endpoint_returns_signal_summary(self, client):
        """Each room must include signal_count, domains, severity, urgency."""
        response = client.get("/api/concierge/rooms/S001")
        assert response.status_code == 200
        rooms = response.json()["rooms"]
        # Only check rooms that have signals
        rooms_with_signals = [r for r in rooms if r["signal_count"] > 0]
        assert len(rooms_with_signals) >= 1
        room = rooms_with_signals[0]
        assert "signal_count" in room
        assert "domains" in room
        assert "highest_severity" in room
        assert "urgency_score" in room

    def test_room_signals_endpoint(self, client):
        """Room signal list endpoint returns correct data."""
        rooms = client.get("/api/concierge/rooms/S001").json()["rooms"]
        room_with_signals = next((r for r in rooms if r["signal_count"] > 0), None)
        assert room_with_signals is not None, "Need at least one room with signals"
        response = client.get(f"/api/concierge/rooms/S001/{room_with_signals['room_id']}/signals")
        assert response.status_code == 200
        signals = response.json()
        assert len(signals) >= 1

    def test_signal_detail_has_advisory_label(self, client):
        """Signal detail must include advisory label for concierge."""
        rooms = client.get("/api/concierge/rooms/S001").json()["rooms"]
        room_with_signals = next((r for r in rooms if r["signal_count"] > 0), None)
        assert room_with_signals is not None
        signals = client.get(f"/api/concierge/rooms/S001/{room_with_signals['room_id']}/signals").json()
        assert len(signals) >= 1
        detail = client.get(
            f"/api/concierge/rooms/S001/{room_with_signals['room_id']}/signals/{signals[0]['id']}"
        ).json()
        assert "advisory_label" in detail
        label = detail["advisory_label"].lower()
        assert "awareness" in label or "discretion" in label, (
            f"Advisory label must contain 'awareness' or 'discretion', got: {detail['advisory_label']}"
        )

    def test_signal_detail_has_suggested_actions(self, client):
        """Signal detail must include non-empty suggested actions."""
        signal_id = "a1000000-0000-0000-0000-000000000001"
        detail = client.get(f"/api/concierge/rooms/S001/FA2-1Q1-MR-01/signals/{signal_id}").json()
        assert "suggested_actions" in detail
        assert len(detail["suggested_actions"]) > 0

    def test_signal_detail_not_found_returns_404(self, client):
        """Requesting a non-existent signal returns 404."""
        resp = client.get("/api/concierge/rooms/S001/FA2-1Q1-MR-01/signals/nonexistent-id")
        assert resp.status_code == 404

    def test_rooms_sorted_by_urgency_descending(self, client):
        """Rooms must be sorted by urgency score descending."""
        rooms = client.get("/api/concierge/rooms/S001").json()["rooms"]
        scores = [r["urgency_score"] for r in rooms]
        assert scores == sorted(scores, reverse=True), "Rooms not sorted by urgency"


# ---------------------------------------------------------------------------
# 5. Urgency Scoring
# ---------------------------------------------------------------------------


class TestUrgencyScoring:
    def test_urgency_scores_normalised(self, client):
        """All urgency scores must be between 0.0 and 1.0."""
        response = client.get("/api/concierge/rooms/S001")
        for room in response.json()["rooms"]:
            assert 0.0 <= room["urgency_score"] <= 1.0, (
                f"Room {room['room_id']} urgency {room['urgency_score']} out of range"
            )

    def test_highest_urgency_room_is_1_0(self, client):
        """The room with highest urgency must have score 1.0 (normalised max)."""
        response = client.get("/api/concierge/rooms/S001")
        rooms = response.json()["rooms"]
        rooms_with_signals = [r for r in rooms if r["signal_count"] > 0]
        if rooms_with_signals:
            max_urgency = max(r["urgency_score"] for r in rooms_with_signals)
            assert max_urgency == 1.0, f"Max urgency should be 1.0, got {max_urgency}"


# ---------------------------------------------------------------------------
# 6. Signal-Room Mapping
# ---------------------------------------------------------------------------


class TestSignalRoomMapping:
    def test_email_signal_with_room_id_maps_to_room(self):
        """Email signal mentioning room ID in text must map to correct room."""
        from app.services.room_signal_mapper import extract_room_id

        room_id = extract_room_id("AV equipment in FA2-1Q1-MR-06 is not working")
        assert room_id == "FA2-1Q1-MR-06"

    def test_signal_without_room_id_returns_none(self):
        """Signal with no room reference must return None."""
        from app.services.room_signal_mapper import extract_room_id

        assert extract_room_id("General facility complaint") is None

    def test_case_insensitive_extraction(self):
        """Room ID extraction must be case-insensitive."""
        from app.services.room_signal_mapper import extract_room_id

        room_id = extract_room_id("Room fa2-1q1-mr-01 has issues")
        assert room_id == "FA2-1Q1-MR-01"

    def test_location_ref_extraction(self):
        """Location ref like 'Fairlands/FA2/1Q1/FA2-1Q1-MR-05' extracts room."""
        from app.services.room_signal_mapper import extract_room_id

        room_id = extract_room_id("Fairlands/FA2/1Q1/FA2-1Q1-MR-05")
        assert room_id == "FA2-1Q1-MR-05"


# ---------------------------------------------------------------------------
# 7. Dashboard Cards
# ---------------------------------------------------------------------------


class TestDashboardCards:
    def test_thandi_receives_dashboard_cards(self, client):
        """After signals are processed, Thandi must have dashboard cards."""
        response = client.get("/api/concierge/dashboard/TDineka@fnb.co.za")
        assert response.status_code == 200
        data = response.json()
        assert len(data["cards"]) >= 1

    def test_dashboard_cards_have_required_fields(self, client):
        """Each dashboard card must have card_id, signal_type, title, severity."""
        response = client.get("/api/concierge/dashboard/TDineka@fnb.co.za")
        cards = response.json()["cards"]
        for card in cards:
            assert "card_id" in card, f"Missing card_id in card: {card}"
            assert "signal_type" in card, f"Missing signal_type in card: {card}"
            assert "title" in card, f"Missing title in card: {card}"
            assert "severity" in card, f"Missing severity in card: {card}"

    def test_dashboard_cards_have_advisory_label(self, client):
        """Each card must have an advisory label."""
        response = client.get("/api/concierge/dashboard/TDineka@fnb.co.za")
        cards = response.json()["cards"]
        for card in cards:
            assert "advisory_label" in card

    def test_unknown_email_still_returns_200(self, client):
        """An unknown email should still return 200 with empty cards in demo mode."""
        response = client.get("/api/concierge/dashboard/unknown@example.com")
        assert response.status_code == 200
        data = response.json()
        assert "cards" in data
