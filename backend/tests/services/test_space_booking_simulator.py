from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.booking_record import BookingRecord
from app.services.space_booking_simulator import SimulatedRoomEvent, SpaceBookingSimulator


@pytest.fixture(autouse=True)
def mock_room_site_resolution():
    with patch("app.services.block_booking_detector.email_parser.resolve_site_id_for_room", return_value="site-002"):
        yield


@pytest.fixture
def simulator(tmp_path: Path):
    site_dir = tmp_path / "site-002"
    site_dir.mkdir()
    (site_dir / "zones.json").write_text(
        """
        {
          "zones": [
            {"zone_id": "Zone-L1-MR1", "zone_type": "meeting_room", "room_name": "S002-L1-MR1"},
            {"zone_id": "Zone-L2-MR1", "zone_type": "meeting_room", "room_name": "S002-L2-MR1"},
            {"zone_id": "Zone-L0-MR1", "zone_type": "meeting_room", "room_name": "S002-L0-MR1"},
            {"zone_id": "Zone-L1-FR1", "zone_type": "focus_room", "room_name": "S002-L1-FR1"},
            {"zone_id": "Zone-L2-FR1", "zone_type": "focus_room", "room_name": "S002-L2-FR1"},
            {"zone_id": "Zone-L0-FR1", "zone_type": "focus_room", "room_name": "S002-L0-FR1"}
          ]
        }
        """.strip()
    )
    return SpaceBookingSimulator(data_path=tmp_path)


@pytest.mark.asyncio
async def test_space_booking_simulator_generates_normal_day_bookings(simulator: SpaceBookingSimulator):
    fake_store = MagicMock()
    fake_store.booking_exists.return_value = False
    fake_store.get_bookings_for_site.return_value = []

    with (
        patch("app.services.space_booking_simulator.get_block_booking_config") as get_config,
        patch("app.services.space_booking_simulator.get_booking_store", return_value=fake_store),
        patch("app.services.space_booking_simulator.detect_overlaps", return_value=[]),
        patch("app.services.space_booking_simulator.send_block_booking_alert", new_callable=AsyncMock),
        patch.object(simulator, "_should_inject_block_booking", return_value=False),
        patch.object(simulator, "_booking_window_dates", return_value=[date(2026, 3, 16)]),
    ):
        get_config.return_value.enabled = True
        get_config.return_value.min_rooms_for_alert = 3
        get_config.return_value.full_day_threshold_hours = 6.0

        summary = await simulator.ingest_day("site-002", date(2026, 3, 16))

    assert summary["generated_bookings"] >= 1
    assert summary["saved_bookings"] == summary["generated_bookings"]
    assert fake_store.save_booking.call_count == summary["generated_bookings"]


@pytest.mark.asyncio
async def test_space_booking_simulator_generates_block_booking_alert(simulator: SpaceBookingSimulator):
    fake_store = MagicMock()
    fake_store.booking_exists.return_value = False
    fake_store.get_bookings_for_site.return_value = []
    fake_store.save_alert.side_effect = lambda alert: alert
    fake_alert = MagicMock()

    with (
        patch("app.services.space_booking_simulator.get_block_booking_config") as get_config,
        patch("app.services.space_booking_simulator.get_booking_store", return_value=fake_store),
        patch("app.services.space_booking_simulator.detect_overlaps", return_value=[fake_alert]),
        patch("app.services.space_booking_simulator.send_block_booking_alert", new_callable=AsyncMock) as send_alert,
        patch.object(simulator, "_should_inject_block_booking", return_value=True),
        patch.object(simulator, "_booking_window_dates", return_value=[date(2026, 3, 18)]),
    ):
        get_config.return_value.enabled = True
        get_config.return_value.min_rooms_for_alert = 3
        get_config.return_value.full_day_threshold_hours = 6.0
        send_alert.return_value = True

        summary = await simulator.ingest_day("site-002", date(2026, 3, 18))

    assert summary["generated_bookings"] == 3
    assert summary["alerts_generated"] == 1
    assert summary["alerts_notified"] == 1
    assert fake_store.save_booking.call_count == 3
    fake_store.flag_bookings.assert_called_once_with(fake_alert.booking_ids)
    send_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_space_booking_simulator_flags_block_booking_when_third_room_arrives_later(
    simulator: SpaceBookingSimulator,
):
    saved_bookings: list[BookingRecord] = []
    fake_alert = MagicMock()

    def booking_exists(raw_email_hash: str) -> bool:
        return any(record.raw_email_hash == raw_email_hash for record in saved_bookings)

    def save_booking(record: BookingRecord) -> BookingRecord:
        saved_bookings.append(record)
        return record

    def get_bookings_for_site(site_id: str, booking_date: date) -> list[BookingRecord]:
        return [
            record for record in saved_bookings if record.site_id == site_id and record.booking_date == booking_date
        ]

    fake_store = MagicMock()
    fake_store.booking_exists.side_effect = booking_exists
    fake_store.save_booking.side_effect = save_booking
    fake_store.get_bookings_for_site.side_effect = get_bookings_for_site
    fake_store.save_alert.side_effect = lambda alert: alert

    def detect_when_threshold_reached(_site_id, bookings, _config, _store):
        return [fake_alert] if len(bookings) >= 3 else []

    target_booking_date = date(2026, 3, 20)  # Friday

    with (
        patch("app.services.space_booking_simulator.get_block_booking_config") as get_config,
        patch("app.services.space_booking_simulator.get_booking_store", return_value=fake_store),
        patch("app.services.space_booking_simulator.detect_overlaps", side_effect=detect_when_threshold_reached),
        patch("app.services.space_booking_simulator.send_block_booking_alert", new_callable=AsyncMock) as send_alert,
        patch.object(simulator, "_should_inject_block_booking", return_value=True),
        patch.object(simulator, "_booking_window_dates", return_value=[target_booking_date]),
        patch.object(simulator, "_select_intelligence_issue_booking", return_value=None),
    ):
        get_config.return_value.enabled = True
        get_config.return_value.min_rooms_for_alert = 3
        get_config.return_value.full_day_threshold_hours = 6.0
        send_alert.return_value = True

        monday_summary = await simulator.ingest_day("site-002", date(2026, 3, 5))
        wednesday_summary = await simulator.ingest_day("site-002", date(2026, 3, 12))
        thursday_summary = await simulator.ingest_day("site-002", date(2026, 3, 18))

    assert monday_summary["saved_bookings"] == 1
    assert monday_summary["alerts_generated"] == 0
    assert wednesday_summary["saved_bookings"] == 1
    assert wednesday_summary["alerts_generated"] == 0
    assert thursday_summary["saved_bookings"] == 1
    assert thursday_summary["alerts_generated"] == 1
    assert thursday_summary["alerts_notified"] == 1
    send_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_space_booking_simulator_generates_meeting_room_intake_email(simulator: SpaceBookingSimulator):
    fake_store = MagicMock()
    fake_store.booking_exists.return_value = False
    selected_booking = BookingRecord(
        id="booking-intake",
        site_id="site-002",
        organiser_email="aisha.patel@site002.example.com",
        organiser_name="Aisha Patel",
        room_id="S002-L2-MR1",
        room_name="S002-L2-MR1",
        booking_date=date(2026, 3, 16),
        start_time=datetime(2026, 3, 16, 12, 0),
        end_time=datetime(2026, 3, 16, 15, 0),
    )
    fake_store.get_bookings_for_site.return_value = [selected_booking]

    with (
        patch("app.services.space_booking_simulator.get_block_booking_config") as get_config,
        patch("app.services.space_booking_simulator.get_booking_store", return_value=fake_store),
        patch("app.services.space_booking_simulator.detect_overlaps", return_value=[]),
        patch("app.services.space_booking_simulator.send_block_booking_alert", new_callable=AsyncMock),
        patch.object(simulator, "_emit_intelligence_signal", new_callable=AsyncMock) as emit_email_signal,
        patch.object(simulator, "_should_inject_block_booking", return_value=False),
        patch.object(simulator, "_select_intelligence_issue_booking", return_value=selected_booking),
        patch.object(simulator, "_booking_window_dates", return_value=[date(2026, 3, 16)]),
    ):
        get_config.return_value.enabled = True
        get_config.return_value.min_rooms_for_alert = 3
        get_config.return_value.full_day_threshold_hours = 6.0
        emit_email_signal.return_value = {"status": "created"}

        summary = await simulator.ingest_day("site-002", date(2026, 3, 16))

    assert summary["intelligence_emails_generated"] == 1
    assert summary["intelligence_signals_created"] == 1
    emit_args = emit_email_signal.await_args.args
    assert "S002-L2-MR1" in emit_args[0]
    assert "meeting room" in emit_args[1].lower()


@pytest.mark.asyncio
async def test_space_booking_simulator_books_up_to_four_weeks_in_advance(simulator: SpaceBookingSimulator):
    fake_store = MagicMock()
    fake_store.booking_exists.return_value = False
    fake_store.get_bookings_for_site.return_value = []

    with (
        patch("app.services.space_booking_simulator.get_block_booking_config") as get_config,
        patch("app.services.space_booking_simulator.get_booking_store", return_value=fake_store),
        patch("app.services.space_booking_simulator.detect_overlaps", return_value=[]),
        patch("app.services.space_booking_simulator.send_block_booking_alert", new_callable=AsyncMock),
        patch.object(simulator, "_should_inject_block_booking", return_value=False),
    ):
        get_config.return_value.enabled = True
        get_config.return_value.min_rooms_for_alert = 3
        get_config.return_value.full_day_threshold_hours = 6.0

        summary = await simulator.ingest_day("site-002", date(2026, 1, 1))

    saved_dates = sorted({call.args[0].booking_date for call in fake_store.save_booking.call_args_list})
    assert saved_dates
    assert min(saved_dates) > date(2026, 1, 1)
    assert max(saved_dates) <= date(2026, 1, 28)
    assert all(day.weekday() < 5 for day in saved_dates)
    assert summary["saved_bookings"] == fake_store.save_booking.call_count


@pytest.mark.asyncio
async def test_space_booking_simulator_biases_bookings_toward_assistants(simulator: SpaceBookingSimulator):
    fake_store = MagicMock()
    fake_store.booking_exists.return_value = False
    fake_store.get_bookings_for_site.return_value = []

    with (
        patch("app.services.space_booking_simulator.get_block_booking_config") as get_config,
        patch("app.services.space_booking_simulator.get_booking_store", return_value=fake_store),
        patch("app.services.space_booking_simulator.detect_overlaps", return_value=[]),
        patch("app.services.space_booking_simulator.send_block_booking_alert", new_callable=AsyncMock),
        patch.object(simulator, "_should_inject_block_booking", return_value=False),
    ):
        get_config.return_value.enabled = True
        get_config.return_value.min_rooms_for_alert = 3
        get_config.return_value.full_day_threshold_hours = 6.0

        await simulator.ingest_day("site-002", date(2026, 1, 1))

    organiser_emails = [call.args[0].organiser_email for call in fake_store.save_booking.call_args_list]
    assistant_like = [email for email in organiser_emails if ("assistant" in email or "coordinator" in email)]
    assert organiser_emails
    assert len(assistant_like) > len(organiser_emails) / 2


@pytest.mark.asyncio
async def test_space_booking_simulator_replays_normal_room_movement(simulator: SpaceBookingSimulator):
    booking = BookingRecord(
        id="booking-normal",
        site_id="site-002",
        organiser_email="alice@example.com",
        organiser_name="Alice Smith",
        room_id="S002-L1-MR1",
        room_name="S002-L1-MR1",
        booking_date=date(2026, 3, 16),
        start_time=datetime(2026, 3, 16, 9, 0),
        end_time=datetime(2026, 3, 16, 10, 0),
    )
    fake_store = MagicMock()
    fake_store.get_bookings_for_site.return_value = [booking]

    with (
        patch("app.services.space_booking_simulator.get_booking_store", return_value=fake_store),
        patch("app.services.space_booking_simulator.process_occupancy_event", new_callable=AsyncMock) as process_event,
        patch("app.services.space_booking_simulator.occupancy_store.get_events_for_room", return_value=[]),
        patch("app.services.space_booking_simulator.get_space_setting", return_value=5),
        patch.object(simulator, "_should_generate_bookings", return_value=True),
        patch.object(simulator, "_should_ghost_booking", return_value=False),
        patch.object(simulator, "_build_focus_room_events_for_day", return_value=[]),
    ):
        process_event.return_value = {"ghost_findings_created": 0, "ghost_notifications_sent": 0}
        summary = await simulator.replay_hour("site-002", datetime(2026, 3, 16, 9, 0))

    assert summary["events_replayed"] == 2
    assert process_event.await_count == 2
    first_call = process_event.await_args_list[0].kwargs
    second_call = process_event.await_args_list[1].kwargs
    assert first_call["occupied"] is True
    assert second_call["occupied"] is False


@pytest.mark.asyncio
async def test_space_booking_simulator_replays_ghost_room_no_show(simulator: SpaceBookingSimulator):
    booking = BookingRecord(
        id="booking-ghost",
        site_id="site-002",
        organiser_email="section.coordinator@site002.example.com",
        organiser_name="Section Coordinator",
        room_id="S002-L2-MR1",
        room_name="S002-L2-MR1",
        booking_date=date(2026, 3, 18),
        start_time=datetime(2026, 3, 18, 8, 0),
        end_time=datetime(2026, 3, 18, 17, 0),
        flagged=True,
    )
    fake_store = MagicMock()
    fake_store.get_bookings_for_site.return_value = [booking]

    with (
        patch("app.services.space_booking_simulator.get_booking_store", return_value=fake_store),
        patch("app.services.space_booking_simulator.process_occupancy_event", new_callable=AsyncMock) as process_event,
        patch("app.services.space_booking_simulator.occupancy_store.get_events_for_room", return_value=[]),
        patch("app.services.space_booking_simulator.get_space_setting", return_value=5),
        patch.object(simulator, "_should_generate_bookings", return_value=True),
        patch.object(simulator, "_build_focus_room_events_for_day", return_value=[]),
    ):
        process_event.return_value = {"ghost_findings_created": 1, "ghost_notifications_sent": 1}
        summary = await simulator.replay_hour("site-002", datetime(2026, 3, 18, 8, 0))

    assert summary["events_replayed"] == 1
    assert summary["ghost_findings_created"] == 1
    assert summary["ghost_notifications_sent"] == 1
    process_kwargs = process_event.await_args.kwargs
    assert process_kwargs["occupied"] is False
    assert process_kwargs["timestamp"] == datetime(2026, 3, 18, 8, 6)


@pytest.mark.asyncio
async def test_space_booking_simulator_replays_focus_room_sessions(simulator: SpaceBookingSimulator):
    fake_store = MagicMock()
    fake_store.get_bookings_for_site.return_value = []
    focus_events = [
        SimulatedRoomEvent(
            room_code="S002-L1-FR1",
            sensor_id="SIM-RADAR-S002-L1-FR1",
            event_time=datetime(2026, 3, 16, 8, 15),
            occupied=True,
            moving=True,
            stationary=True,
            behavior="focus_session_start",
        ),
        SimulatedRoomEvent(
            room_code="S002-L1-FR1",
            sensor_id="SIM-RADAR-S002-L1-FR1",
            event_time=datetime(2026, 3, 16, 8, 55),
            occupied=False,
            moving=False,
            stationary=False,
            behavior="focus_session_end",
        ),
    ]

    with (
        patch("app.services.space_booking_simulator.get_booking_store", return_value=fake_store),
        patch("app.services.space_booking_simulator.process_occupancy_event", new_callable=AsyncMock) as process_event,
        patch("app.services.space_booking_simulator.occupancy_store.get_events_for_room", return_value=[]),
        patch.object(simulator, "_should_generate_bookings", return_value=True),
        patch.object(simulator, "_build_focus_room_events_for_day", return_value=focus_events),
    ):
        process_event.return_value = {}
        summary = await simulator.replay_hour("site-002", datetime(2026, 3, 16, 8, 0))

    assert summary["focus_room_events_replayed"] >= 1
    focus_calls = [call.kwargs for call in process_event.await_args_list if call.kwargs["room_type"] == "focus"]
    assert focus_calls
    assert all(call["room_code"].startswith("S002-L") and call["room_code"].endswith("-FR1") for call in focus_calls)


def test_space_booking_simulator_caps_focus_room_overstays_to_one_per_week(simulator: SpaceBookingSimulator):
    specs = simulator._build_focus_session_specs("site-002", date(2026, 3, 16))
    extended = [spec for spec in specs if spec.anomaly_type == "extended_use"]
    assert len(extended) <= 1
    if extended:
        duration_minutes = int((extended[0].end_time - extended[0].start_time).total_seconds() / 60)
        assert duration_minutes == 150


def test_space_booking_simulator_caps_ghost_bookings_to_three_per_week(simulator: SpaceBookingSimulator):
    week_start = datetime(2026, 3, 16, 8, 0)
    bookings = [
        BookingRecord(
            id=f"booking-{idx}",
            site_id="site-002",
            organiser_email=f"user{idx}@example.com",
            organiser_name=f"User {idx}",
            room_id=f"S002-L{idx}-MR1",
            room_name=f"S002-L{idx}-MR1",
            booking_date=(week_start + timedelta(days=idx - 1)).date(),
            start_time=week_start + timedelta(days=idx - 1),
            end_time=week_start + timedelta(days=idx - 1, hours=1),
            flagged=(idx == 1),
        )
        for idx in range(1, 5)
    ]

    selected = simulator._select_weekly_ghost_booking_keys("site-002", bookings)

    assert len(selected) <= 3


def test_space_booking_simulator_limits_ghosts_from_one_block_cluster(simulator: SpaceBookingSimulator):
    booking_date = date(2026, 3, 20)
    start = datetime(2026, 3, 20, 8, 0)
    end = datetime(2026, 3, 20, 17, 0)
    bookings = [
        BookingRecord(
            id=f"booking-{idx}",
            site_id="site-002",
            organiser_email="section.coordinator@site002.example.com",
            organiser_name="Section Coordinator",
            room_id=room_id,
            room_name=room_id,
            booking_date=booking_date,
            start_time=start,
            end_time=end,
            flagged=True,
        )
        for idx, room_id in enumerate(
            [
                "S002-L1-MR1",
                "S002-L1-MR2",
                "S002-L2-MR1",
                "S002-L2-MR2",
                "S002-L0-MR1",
                "S002-L0-MR2",
            ],
            start=1,
        )
    ]

    selected = simulator._select_weekly_ghost_booking_keys("site-002", bookings)

    assert len(selected) == 1


def test_space_booking_simulator_caps_block_booking_to_one_day_per_week(simulator: SpaceBookingSimulator):
    monday = date(2026, 3, 16)
    injected_days = [
        day
        for day in range(5)
        if simulator._should_inject_block_booking(
            "site-002", monday + timedelta(days=day), simulator._rng_for_day("site-002", monday)
        )
    ]

    assert len(injected_days) == 1
