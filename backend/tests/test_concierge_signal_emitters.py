"""Tests for Phase 161-02: room signal mapper and signal emitters."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.space_occupancy import GhostBookingFinding
from app.services.room_signal_mapper import extract_room_id, map_signal_to_room
from app.services.signal_emitter_base import _reset_dedup


@pytest.fixture(autouse=True)
def _clear_dedup():
    """Reset dedup cache before each test."""
    _reset_dedup()
    yield
    _reset_dedup()


# ---------------------------------------------------------------------------
# extract_room_id
# ---------------------------------------------------------------------------


def test_extract_room_id_from_text():
    """Room ID extracted from free text."""
    result = extract_room_id("Meeting in FA2-1Q1-MR-06 was cancelled")
    assert result == "FA2-1Q1-MR-06"


def test_extract_room_id_case_insensitive():
    """Lowercase room ID uppercased on extraction."""
    result = extract_room_id("fa2-1q1-mr-01")
    assert result == "FA2-1Q1-MR-01"


def test_extract_room_id_no_match():
    """No room ID in text returns None."""
    result = extract_room_id("No room mentioned here")
    assert result is None


# ---------------------------------------------------------------------------
# map_signal_to_room
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_map_signal_to_room_from_location_ref():
    """Room ID found in location_ref field."""
    repo = MagicMock()
    repo.validate_room_exists = AsyncMock(return_value=True)

    signal = {
        "location_ref": "Fairlands/FA2/1Q1/FA2-1Q1-MR-06",
        "summary": "",
        "metadata": {},
    }
    result = await map_signal_to_room(repo, signal)
    assert result == "FA2-1Q1-MR-06"
    repo.validate_room_exists.assert_called_with("FA2-1Q1-MR-06")


@pytest.mark.asyncio
async def test_map_signal_to_room_from_metadata():
    """Room ID found in metadata.room_id field."""
    repo = MagicMock()
    repo.validate_room_exists = AsyncMock(return_value=True)

    signal = {
        "location_ref": "some/path/no-room",
        "summary": "generic text",
        "metadata": {"room_id": "FA2-1Q1-PR-01"},
    }
    result = await map_signal_to_room(repo, signal)
    assert result == "FA2-1Q1-PR-01"


@pytest.mark.asyncio
async def test_map_signal_to_room_from_summary_text():
    """Room ID extracted from free-text summary."""
    repo = MagicMock()
    repo.validate_room_exists = AsyncMock(return_value=True)

    signal = {
        "location_ref": "",
        "summary": "Ghost booking detected in FA1-2Q3-MR-10",
        "metadata": {},
    }
    result = await map_signal_to_room(repo, signal)
    assert result == "FA1-2Q3-MR-10"


# ---------------------------------------------------------------------------
# Ghost booking signal format
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ghost_booking_signal_format():
    """Emitted ghost signal has correct signal_type, source_module, severity."""
    finding = GhostBookingFinding(
        site_id="S001",
        room_code="FA2-1Q1-MR-06",
        room_name="MR-06",
        booking_id="booking-123",
        organiser_email="test@example.com",
        organiser_name="Test User",
        booking_start=datetime(2026, 3, 16, 9, 0),
        booking_end=datetime(2026, 3, 16, 10, 0),
        grace_period_minutes=15,
    )

    with (
        patch("app.services.ghost_booking_signal_emitter.write_signal", new_callable=AsyncMock) as mock_write,
        patch("app.services.ghost_booking_signal_emitter.link_signal_to_room", new_callable=AsyncMock),
    ):
        mock_write.return_value = {"id": "sig-001", "signal_type": "no_show_pattern"}

        from app.services.ghost_booking_signal_emitter import emit_ghost_booking_signal

        result = await emit_ghost_booking_signal("FA2-1Q1-MR-06", finding)

        assert result is not None
        # Verify the signal row passed to write_signal
        call_args = mock_write.call_args[0][0]
        assert call_args["source_module"] == "space_optimisation"
        assert call_args["signal_type"] == "no_show_pattern"
        assert call_args["severity"] == "medium"
        assert call_args["confidence"] == 0.85
        assert "FA2-1Q1-MR-06" in call_args["location_ref"]


# ---------------------------------------------------------------------------
# Block booking signal format
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_block_booking_signal_format():
    """booking_conflict signal has correct fields."""
    from datetime import date

    from app.models.booking_record import BookingRecord

    bookings = [
        BookingRecord(
            id="b1",
            site_id="S001",
            organiser_email="hoarder@example.com",
            organiser_name="Resource Hoarder",
            room_id="FA2-1Q1-MR-01",
            room_name="MR-01",
            booking_date=date.today(),
            start_time=datetime(2026, 3, 16, 9, 0),
            end_time=datetime(2026, 3, 16, 10, 0),
        ),
        BookingRecord(
            id="b2",
            site_id="S001",
            organiser_email="hoarder@example.com",
            organiser_name="Resource Hoarder",
            room_id="FA2-1Q1-MR-02",
            room_name="MR-02",
            booking_date=date.today(),
            start_time=datetime(2026, 3, 16, 9, 0),
            end_time=datetime(2026, 3, 16, 10, 0),
        ),
    ]

    mock_store = MagicMock()
    mock_store.get_bookings_for_site = MagicMock(return_value=bookings)

    with (
        patch(
            "app.services.block_booking_detector.booking_store.get_booking_store",
            return_value=mock_store,
        ),
        patch("app.services.block_booking_signal_emitter.write_signal", new_callable=AsyncMock) as mock_write,
        patch("app.services.block_booking_signal_emitter.link_signal_to_room", new_callable=AsyncMock),
    ):
        mock_write.return_value = {"id": "sig-002", "signal_type": "booking_conflict"}

        from app.services.block_booking_signal_emitter import emit_block_booking_signals

        results = await emit_block_booking_signals("S001")

        assert len(results) >= 1
        call_args = mock_write.call_args[0][0]
        assert call_args["source_module"] == "space_optimisation"
        assert call_args["signal_type"] == "booking_conflict"
        assert call_args["severity"] == "high"


# ---------------------------------------------------------------------------
# Dedup prevents duplicate signals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dedup_prevents_duplicate_signals():
    """Same ghost signal emitted twice, dedup catches second."""
    finding = GhostBookingFinding(
        site_id="S001",
        room_code="FA2-1Q1-MR-06",
        room_name="MR-06",
        booking_id="booking-456",
        organiser_email="test@example.com",
        grace_period_minutes=15,
        booking_start=datetime(2026, 3, 16, 9, 0),
        booking_end=datetime(2026, 3, 16, 10, 0),
    )

    with (
        patch("app.services.ghost_booking_signal_emitter.write_signal", new_callable=AsyncMock) as mock_write,
        patch("app.services.ghost_booking_signal_emitter.link_signal_to_room", new_callable=AsyncMock),
    ):
        mock_write.return_value = {"id": "sig-003", "signal_type": "no_show_pattern"}

        from app.services.ghost_booking_signal_emitter import emit_ghost_booking_signal

        # First emission — should succeed
        result1 = await emit_ghost_booking_signal("FA2-1Q1-MR-06", finding)
        assert result1 is not None

        # Second emission — should be deduplicated
        result2 = await emit_ghost_booking_signal("FA2-1Q1-MR-06", finding)
        assert result2 is None

        # write_signal called only once
        assert mock_write.call_count == 1


# ---------------------------------------------------------------------------
# link_signal_to_room creates entity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_signal_to_room_creates_entity_and_relationship():
    """Entity type='room', relationship edge_type='affects' created."""
    with patch("app.services.room_signal_mapper.write_entities", new_callable=AsyncMock) as mock_write:
        mock_write.return_value = [{"id": "ent-001"}]

        from app.services.room_signal_mapper import link_signal_to_room

        await link_signal_to_room("signal-abc", "FA2-1Q1-MR-06")

        assert mock_write.call_count == 1
        entities = mock_write.call_args[0][0]
        assert len(entities) == 1
        entity = entities[0]
        assert entity["entity_type"] == "room"
        assert entity["name"] == "FA2-1Q1-MR-06"
        assert entity["signal_id"] == "signal-abc"
        assert entity["metadata"]["edge_type"] == "affects"
