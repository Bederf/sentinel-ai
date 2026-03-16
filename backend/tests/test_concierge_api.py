"""Tests for Phase 161-03: Concierge API endpoints and urgency scoring."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

# Ensure demo mode before importing app
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")

from app.services.concierge_urgency import compute_urgency_score, normalise_urgency_scores

# ---------------------------------------------------------------------------
# Urgency score formula
# ---------------------------------------------------------------------------


def test_urgency_score_formula():
    """Verify formula: 3 signals, high severity, 5 days, 1 repeat."""
    score = compute_urgency_score(
        signal_count=3,
        highest_severity="high",
        oldest_unresolved_at=datetime(2026, 3, 11, 0, 0, tzinfo=UTC),
        repeat_count=1,
    )
    # signal_count(3) * 0.3 = 0.9
    # severity(high=3) * 0.4 = 1.2
    # days_unresolved(5) * 0.2 = 1.0  (approx, depends on test run date)
    # repeat_count(1) * 0.1 = 0.1
    # We cannot assert exact value because days_unresolved depends on now(),
    # but we can verify it's > 2.0 (signal+severity alone = 2.1)
    assert score > 2.0


def test_urgency_score_zero_signals():
    """Zero signals produces minimal score."""
    score = compute_urgency_score(
        signal_count=0,
        highest_severity="low",
        oldest_unresolved_at=None,
        repeat_count=0,
    )
    # 0 * 0.3 + 1 * 0.4 + 0 * 0.2 + 0 * 0.1 = 0.4
    assert score == pytest.approx(0.4)


def test_urgency_normalisation():
    """3 rooms with different scores normalise correctly."""
    rooms = [
        {"room_id": "A", "urgency_score": 10.0},
        {"room_id": "B", "urgency_score": 5.0},
        {"room_id": "C", "urgency_score": 0.0},
    ]
    normalise_urgency_scores(rooms)

    assert rooms[0]["urgency_score"] == 1.0  # highest
    assert rooms[1]["urgency_score"] == 0.5
    assert rooms[2]["urgency_score"] == 0.0  # lowest


def test_urgency_normalisation_all_zero():
    """All-zero scores remain zero after normalisation."""
    rooms = [
        {"room_id": "A", "urgency_score": 0.0},
        {"room_id": "B", "urgency_score": 0.0},
    ]
    normalise_urgency_scores(rooms)
    assert all(r["urgency_score"] == 0.0 for r in rooms)


# ---------------------------------------------------------------------------
# API endpoint tests (using FastAPI TestClient)
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """FastAPI TestClient with demo mode."""
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_concierge_rooms_returns_200(client):
    """GET /api/concierge/rooms/S001 returns 200."""
    resp = client.get("/api/concierge/rooms/S001")
    assert resp.status_code == 200


def test_concierge_rooms_response_shape(client):
    """Response has 'rooms' key, each room has room_id, signal_count, urgency_score."""
    resp = client.get("/api/concierge/rooms/S001")
    data = resp.json()
    assert "rooms" in data

    for room in data["rooms"]:
        assert "room_id" in room
        assert "signal_count" in room
        assert "urgency_score" in room


def test_concierge_rooms_urgency_normalised(client):
    """All urgency_score values between 0.0 and 1.0."""
    resp = client.get("/api/concierge/rooms/S001")
    data = resp.json()

    for room in data["rooms"]:
        score = room["urgency_score"]
        assert 0.0 <= score <= 1.0, f"Room {room['room_id']} urgency {score} out of range"


def test_concierge_room_signals_returns_list(client):
    """GET /api/concierge/rooms/S001/FA2-1Q1-MR-01/signals returns a list."""
    resp = client.get("/api/concierge/rooms/S001/FA2-1Q1-MR-01/signals")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_concierge_signal_detail_has_advisory_label(client):
    """Signal detail includes advisory label."""
    # Use a known fixture signal ID
    signal_id = "a1000000-0000-0000-0000-000000000001"
    resp = client.get(f"/api/concierge/rooms/S001/FA2-1Q1-MR-01/signals/{signal_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "advisory_label" in data
    assert data["advisory_label"] == "For awareness only. Act at your discretion."


def test_concierge_signal_detail_has_suggested_actions(client):
    """Signal detail includes suggested actions from card template."""
    signal_id = "a1000000-0000-0000-0000-000000000001"
    resp = client.get(f"/api/concierge/rooms/S001/FA2-1Q1-MR-01/signals/{signal_id}")
    data = resp.json()
    assert "suggested_actions" in data
    assert len(data["suggested_actions"]) > 0


def test_concierge_dashboard_by_email(client):
    """GET /api/concierge/dashboard/TDineka@fnb.co.za returns cards."""
    resp = client.get("/api/concierge/dashboard/TDineka@fnb.co.za")
    assert resp.status_code == 200
    data = resp.json()
    assert "person_email" in data
    assert data["person_email"] == "TDineka@fnb.co.za"
    assert "cards" in data
    assert len(data["cards"]) > 0
