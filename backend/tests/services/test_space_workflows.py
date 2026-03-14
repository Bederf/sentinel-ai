from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.models.booking_record import BlockBookingConfig, BookingRecord
from app.models.space_occupancy import GhostBookingFinding, OccupancyEvent


@pytest.fixture(autouse=True)
def _clean_space_store(tmp_path):
    with (
        patch("app.services.occupancy_store._DATA_DIR", tmp_path),
        patch("app.services.occupancy_store._EVENTS_FILE", tmp_path / "occupancy_events.json"),
        patch("app.services.occupancy_store._GHOST_FILE", tmp_path / "ghost_findings.json"),
        patch("app.services.occupancy_store._RIGHTSIZING_FILE", tmp_path / "rightsizing_findings.json"),
        patch("app.services.occupancy_store._SESSIONS_FILE", tmp_path / "focus_room_sessions.json"),
    ):
        yield


def _booking(now: datetime, room: str = "FA1-1Q2-MR4") -> BookingRecord:
    return BookingRecord(
        id="booking-001",
        site_id="site-002",
        organiser_email="alice@example.com",
        organiser_name="Alice Smith",
        room_id=room,
        room_name=room,
        booking_date=now.date(),
        start_time=now - timedelta(minutes=20),
        end_time=now + timedelta(minutes=40),
        raw_email_hash="hash-001",
    )


@pytest.mark.asyncio
async def test_block_booking_notifier_uses_n8n():
    from app.models.booking_record import BlockBookingAlert
    from app.services.block_booking_detector.notifier import send_block_booking_alert

    alert = BlockBookingAlert(
        id="alert-001",
        site_id="site-002",
        organiser_email="alice@example.com",
        organiser_name="Alice Smith",
        overlap_window_start=datetime(2026, 3, 10, 9, 0),
        overlap_window_end=datetime(2026, 3, 10, 10, 0),
        rooms=["MR1", "MR2", "MR3"],
        room_count=3,
        booking_ids=["b1", "b2", "b3"],
    )
    config = BlockBookingConfig(site_id="site-002", concierge_email="concierge@example.com")
    service = AsyncMock()
    service.trigger_webhook.return_value = {"success": True}

    with (
        patch("app.services.block_booking_detector.notifier.get_n8n_service", return_value=service),
        patch("app.services.block_booking_detector.notifier.get_booking_store") as store_factory,
    ):
        store = store_factory.return_value
        sent = await send_block_booking_alert(alert, config, site_name="Site 002")

    assert sent is True
    service.trigger_webhook.assert_awaited_once()
    assert service.trigger_webhook.await_args.kwargs["webhook_path"] == "space-block-booking-alert"
    store.mark_alert_notified.assert_called_once_with("alert-001")


@pytest.mark.asyncio
async def test_ghost_room_monitor_creates_and_notifies():
    from app.services import occupancy_store
    from app.services.ghost_room_monitor import scan_due_ghost_bookings

    now = datetime(2026, 3, 10, 9, 20)
    booking = _booking(now)
    store = AsyncMock()
    send_alert = AsyncMock(return_value={"success": True})

    # Seed a recent sensor event (not occupied) so room_has_sensor_data/room_sensor_is_alive pass
    # Use real UTC time so room_sensor_is_alive (which calls datetime.utcnow()) sees it as recent
    real_now = datetime.utcnow()
    sensor_event = OccupancyEvent(
        room_code="FA1-1Q2-MR4",
        sensor_id="node_001",
        occupied=False,
        timestamp=real_now,
        received_at=real_now,
    )
    occupancy_store.save_event(sensor_event)

    with (
        patch("app.services.ghost_room_monitor.get_registered_site_ids", return_value=["site-002"]),
        patch("app.services.ghost_room_monitor.get_booking_store") as get_store,
        patch(
            "app.services.ghost_room_monitor.get_block_booking_config",
            return_value=BlockBookingConfig(site_id="site-002"),
        ),
        patch("app.services.ghost_room_monitor.send_ghost_booking_alert", send_alert),
    ):
        get_store.return_value.get_bookings_for_site.side_effect = lambda site_id, target_date: (
            [booking] if target_date == date(2026, 3, 10) else []
        )
        result = await scan_due_ghost_bookings(now=now)

    assert result["ghost_findings_created"] == 1
    assert result["notifications_sent"] == 1
    send_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_concierge_whatsapp_reply_yes_marks_occupied():
    from app.services import occupancy_store
    from app.services.ghost_room_notifier import process_concierge_whatsapp_reply

    finding = GhostBookingFinding(
        id="ghost-001",
        site_id="site-002",
        room_code="FA1-1Q2-MR4",
        room_name="FA1-1Q2-MR4",
        booking_id="booking-001",
        organiser_email="alice@example.com",
        organiser_name="Alice",
        booking_start=datetime(2026, 3, 10, 9, 0),
        booking_end=datetime(2026, 3, 10, 10, 0),
        grace_period_minutes=15,
        status="pending_inspection",
        concierge_whatsapp="+27721234567",
        whatsapp_message_id="SM-001",
        notification_sent=True,
    )
    occupancy_store.save_ghost_finding(finding)

    result = await process_concierge_whatsapp_reply(
        "+27721234567",
        "yes",
        reply_to_message_id="SM-001",
        message_id="SM-REPLY-1",
    )

    updated = occupancy_store.get_ghost_finding_by_id("ghost-001")
    assert result["handled"] is True
    assert updated is not None
    assert updated.status == "verified_occupied"


@pytest.mark.asyncio
async def test_process_concierge_whatsapp_reply_no_marks_empty():
    from app.services import occupancy_store
    from app.services.ghost_room_notifier import process_concierge_whatsapp_reply

    finding = GhostBookingFinding(
        id="ghost-002",
        site_id="site-002",
        room_code="FA1-1Q2-MR5",
        room_name="FA1-1Q2-MR5",
        booking_id="booking-002",
        organiser_email="alice@example.com",
        organiser_name="Alice",
        booking_start=datetime(2026, 3, 10, 9, 0),
        booking_end=datetime(2026, 3, 10, 10, 0),
        grace_period_minutes=15,
        status="pending_inspection",
        concierge_whatsapp="+27721234567",
        whatsapp_message_id="SM-002",
        notification_sent=True,
    )
    occupancy_store.save_ghost_finding(finding)

    result = await process_concierge_whatsapp_reply(
        "+27721234567",
        "no",
        reply_to_message_id="SM-002",
        message_id="SM-REPLY-2",
    )

    updated = occupancy_store.get_ghost_finding_by_id("ghost-002")
    assert result["handled"] is True
    assert updated is not None
    assert updated.status == "confirmed_empty"


def test_parse_mqtt_presence_message_prefers_zone_as_room_code():
    from app.services.space_mqtt_listener import parse_mqtt_presence_message

    # Mock node_room_mapping to empty so zone field takes priority (no server-side override)
    with patch("app.services.space_mqtt_listener.get_node_room_mapping", return_value={}):
        event = parse_mqtt_presence_message(
            "sentinel/nodes/node_001/presence",
            {
                "zone": "FA1-1Q2-MR4",
                "presence": True,
                "site_id": "site-002",
                "ts": 1741234567,
            },
        )

    assert event.room_code == "FA1-1Q2-MR4"
    assert event.sensor_id == "node_001"
    assert event.occupied is True
