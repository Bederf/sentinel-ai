"""
Tests for booking signal emitter (Phase 159-02).
=================================================
Covers ghost booking, block booking, and saturation signal emission,
deduplication, entity extraction, and room code to location ref conversion.
All Supabase calls are mocked via httpx.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_dedup():
    """Clear the in-memory dedup cache between tests."""
    from app.services.signal_emitter_base import _reset_dedup

    _reset_dedup()
    yield
    _reset_dedup()


def _make_mock_response(json_data):
    """Create a MagicMock response with sync .json() method."""
    resp = MagicMock()
    resp.status_code = 201
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    return resp


class PostRecorder:
    """Records all POST calls made through the mock httpx client."""

    def __init__(self):
        self.calls: list[dict] = []

    async def __call__(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        if isinstance(json, list):
            return _make_mock_response(json)
        return _make_mock_response([json])


@pytest.fixture
def mock_httpx():
    """Patch httpx.AsyncClient to avoid real HTTP calls."""
    recorder = PostRecorder()

    mock_client = AsyncMock()
    mock_client.post = recorder
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.signal_emitter_base.httpx.AsyncClient", return_value=mock_client):
        yield recorder


# ---------------------------------------------------------------------------
# Room code to location ref
# ---------------------------------------------------------------------------


class TestRoomCodeToLocationRef:
    def test_fairlands_room_code(self):
        from app.services.booking_signal_emitter import _room_code_to_location_ref

        result = _room_code_to_location_ref("FA1-1Q4-MR10")
        assert result == "Fairlands/FA1/1Q4/MR10"

    def test_s002_prefix(self):
        from app.services.booking_signal_emitter import _room_code_to_location_ref

        result = _room_code_to_location_ref("S002-CONF-L2-A")
        assert result == "Fairlands/S002/CONF/L2/A"

    def test_unknown_code_returned_as_is(self):
        from app.services.booking_signal_emitter import _room_code_to_location_ref

        result = _room_code_to_location_ref("RANDOM")
        assert result == "RANDOM"

    def test_empty_code(self):
        from app.services.booking_signal_emitter import _room_code_to_location_ref

        result = _room_code_to_location_ref("")
        assert result == "unknown"


# ---------------------------------------------------------------------------
# Ghost booking signals
# ---------------------------------------------------------------------------


class TestGhostBookingSignal:
    @pytest.mark.asyncio
    async def test_emit_ghost_booking_creates_signal(self, mock_httpx):
        from app.services.booking_signal_emitter import emit_ghost_booking_signal

        finding = {
            "room_code": "FA1-1Q4-MR10",
            "booking_title": "Team Standup",
            "booked_by": "John Smith",
            "start_time": "2026-03-15T09:00:00Z",
            "end_time": "2026-03-15T10:00:00Z",
            "occupancy_detected": False,
            "site_id": "site-002",
        }

        result = await emit_ghost_booking_signal(finding)
        assert result is not None
        assert result["signal_type"] == "ghost_booking"
        assert result["source_module"] == "booking_system"
        assert result["severity"] == "low"

    @pytest.mark.asyncio
    async def test_emit_ghost_booking_extracts_entities(self, mock_httpx):
        from app.services.booking_signal_emitter import emit_ghost_booking_signal

        finding = {
            "room_code": "FA1-1Q4-MR10",
            "booking_title": "Team Standup",
            "booked_by": "John Smith",
            "start_time": "2026-03-15T09:00:00Z",
            "end_time": "2026-03-15T10:00:00Z",
            "occupancy_detected": False,
            "site_id": "site-002",
        }

        await emit_ghost_booking_signal(finding)

        # write_entities called (second POST call, after write_signal)
        # At least 2 calls: 1 for signal, 1 for entities
        assert len(mock_httpx.calls) >= 2
        entities_json = mock_httpx.calls[1]["json"]

        entity_types = [e["entity_type"] for e in entities_json]
        entity_names = [e["name"] for e in entities_json]
        assert "person" in entity_types
        assert "room" in entity_types
        assert "booking_ref" in entity_types
        assert "John Smith" in entity_names
        assert "FA1-1Q4-MR10" in entity_names
        assert "Team Standup" in entity_names

    @pytest.mark.asyncio
    async def test_emit_ghost_booking_dedup_within_window(self, mock_httpx):
        from app.services.booking_signal_emitter import emit_ghost_booking_signal

        finding = {
            "room_code": "FA1-1Q4-MR10",
            "booking_title": "Meeting A",
            "booked_by": "User A",
            "start_time": "2026-03-15T09:00:00Z",
            "end_time": "2026-03-15T10:00:00Z",
            "occupancy_detected": False,
        }

        result1 = await emit_ghost_booking_signal(finding)
        assert result1 is not None

        # Second call within window → deduped
        result2 = await emit_ghost_booking_signal(finding)
        assert result2 is None

    @pytest.mark.asyncio
    async def test_emit_ghost_booking_dedup_outside_window(self, mock_httpx):
        import time

        from app.services.booking_signal_emitter import emit_ghost_booking_signal
        from app.services.signal_emitter_base import _recent_signals

        finding = {
            "room_code": "FA1-1Q4-MR10",
            "booking_title": "Meeting A",
            "booked_by": "User A",
            "start_time": "2026-03-15T09:00:00Z",
            "end_time": "2026-03-15T10:00:00Z",
            "occupancy_detected": False,
        }

        result1 = await emit_ghost_booking_signal(finding)
        assert result1 is not None

        # Simulate time passing beyond 60 min window by backdating the cache entry
        for key in list(_recent_signals.keys()):
            _recent_signals[key] = time.monotonic() - 3700  # > 3600s

        result2 = await emit_ghost_booking_signal(finding)
        assert result2 is not None

    @pytest.mark.asyncio
    async def test_ghost_booking_recurrence_medium_severity(self, mock_httpx):
        from app.services.booking_signal_emitter import emit_ghost_booking_signal

        finding = {
            "room_code": "FA1-1Q4-MR10",
            "booking_title": "Team Standup",
            "booked_by": "John Smith",
            "start_time": "2026-03-15T09:00:00Z",
            "end_time": "2026-03-15T10:00:00Z",
            "occupancy_detected": False,
            "metadata": {"recurrence_count": 3},
        }

        result = await emit_ghost_booking_signal(finding)
        assert result is not None
        assert result["severity"] == "medium"


# ---------------------------------------------------------------------------
# Block booking signals
# ---------------------------------------------------------------------------


class TestBlockBookingSignal:
    @pytest.mark.asyncio
    async def test_emit_block_booking_creates_signal(self, mock_httpx):
        from app.services.booking_signal_emitter import emit_block_booking_signal

        alert = {
            "room_code": "FA1-1Q4-MR10",
            "booked_by": "Jane Doe",
            "pattern": "daily",
            "booking_count": 15,
            "date_range": "2026-03-01 to 2026-03-15",
            "site_id": "site-002",
        }

        result = await emit_block_booking_signal(alert)
        assert result is not None
        assert result["signal_type"] == "block_booking"
        assert result["source_module"] == "booking_system"
        assert result["severity"] == "medium"

    @pytest.mark.asyncio
    async def test_emit_block_booking_extracts_person_entity(self, mock_httpx):
        from app.services.booking_signal_emitter import emit_block_booking_signal

        alert = {
            "room_code": "FA1-1Q4-MR10",
            "booked_by": "Jane Doe",
            "pattern": "weekly",
            "booking_count": 8,
            "date_range": "2026-02-01 to 2026-03-15",
        }

        await emit_block_booking_signal(alert)

        assert len(mock_httpx.calls) >= 2
        entities_json = mock_httpx.calls[1]["json"]

        person_entities = [e for e in entities_json if e["entity_type"] == "person"]
        assert len(person_entities) == 1
        assert person_entities[0]["name"] == "Jane Doe"

    @pytest.mark.asyncio
    async def test_emit_block_booking_dedup_same_person_24h(self, mock_httpx):
        from app.services.booking_signal_emitter import emit_block_booking_signal

        alert = {
            "room_code": "FA1-1Q4-MR10",
            "booked_by": "Jane Doe",
            "pattern": "daily",
            "booking_count": 15,
            "date_range": "2026-03-01 to 2026-03-15",
        }

        result1 = await emit_block_booking_signal(alert)
        assert result1 is not None

        # Same person + room within 24h → deduped
        result2 = await emit_block_booking_signal(alert)
        assert result2 is None


# ---------------------------------------------------------------------------
# Booking saturation signals
# ---------------------------------------------------------------------------


class TestBookingSaturationSignal:
    @pytest.mark.asyncio
    async def test_emit_saturation_medium_severity(self, mock_httpx):
        from app.services.booking_signal_emitter import emit_booking_saturation_signal

        data = {
            "building_code": "FA1",
            "floor": "L2",
            "utilisation_pct": 87,
            "peak_hour": "10:00-11:00",
            "site_id": "site-002",
        }

        result = await emit_booking_saturation_signal(data)
        assert result is not None
        assert result["signal_type"] == "booking_saturation"
        assert result["severity"] == "medium"

    @pytest.mark.asyncio
    async def test_emit_saturation_high_severity(self, mock_httpx):
        from app.services.booking_signal_emitter import emit_booking_saturation_signal

        data = {
            "building_code": "FA1",
            "floor": "L2",
            "utilisation_pct": 96,
            "peak_hour": "09:00-10:00",
        }

        result = await emit_booking_saturation_signal(data)
        assert result is not None
        assert result["severity"] == "high"

    @pytest.mark.asyncio
    async def test_emit_saturation_dedup_4h(self, mock_httpx):
        from app.services.booking_signal_emitter import emit_booking_saturation_signal

        data = {
            "building_code": "FA1",
            "floor": "L2",
            "utilisation_pct": 90,
            "peak_hour": "10:00-11:00",
        }

        result1 = await emit_booking_saturation_signal(data)
        assert result1 is not None

        # Same building + floor within 4h → deduped
        result2 = await emit_booking_saturation_signal(data)
        assert result2 is None

    @pytest.mark.asyncio
    async def test_emit_saturation_building_entity(self, mock_httpx):
        from app.services.booking_signal_emitter import emit_booking_saturation_signal

        data = {
            "building_code": "FA1",
            "floor": "L2",
            "utilisation_pct": 88,
            "peak_hour": "14:00-15:00",
        }

        await emit_booking_saturation_signal(data)

        assert len(mock_httpx.calls) >= 2
        entities_json = mock_httpx.calls[1]["json"]

        assert len(entities_json) == 1
        assert entities_json[0]["entity_type"] == "building"
        assert entities_json[0]["name"] == "FA1"
