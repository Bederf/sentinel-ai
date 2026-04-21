"""Simulate room-booking traffic for space optimization modules."""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
from pathlib import Path

from app.api.block_bookings import get_block_booking_config
from app.api.space_settings import get_space_setting
from app.services import occupancy_store
from app.services.block_booking_detector.booking_store import get_booking_store
from app.services.block_booking_detector.email_parser import parse_booking_confirmation
from app.services.block_booking_detector.notifier import send_block_booking_alert
from app.services.block_booking_detector.overlap_detector import detect_overlaps
from app.services.site_holiday_service import get_site_holiday_service
from app.services.space_event_service import process_occupancy_event

logger = logging.getLogger(__name__)

DATA_PATH = Path(__file__).parent.parent / "data" / "buildings"
NORMAL_SLOTS: tuple[tuple[int, int], ...] = ((8, 9), (9, 10), (12, 15), (15, 16))
ADVANCE_BOOKING_WINDOW_DAYS = 28
MAX_BLOCK_BOOKING_DAYS_PER_WEEK = 1
MAX_GHOST_BOOKINGS_PER_WEEK = 3
MAX_GHOST_BOOKINGS_PER_CLUSTER = 1
MAX_MEETING_ROOM_INTAKE_EMAILS_PER_WEEK = 2
MAX_FOCUS_ROOM_OVERSTAYS_PER_WEEK = 1
INTAKE_MAILBOX_EMAIL = "intake@sentinel-ai.co.za"
HELPDESK_MAILBOX_EMAIL = "helpdesk@site002.example.com"
FOCUS_SESSION_TEMPLATES: tuple[tuple[int, int, int], ...] = (
    (8, 15, 50),
    (9, 45, 80),
    (11, 15, 55),
    (13, 0, 95),
    (15, 15, 60),
)
NORMAL_ORGANISERS: tuple[tuple[str, str, int], ...] = (
    ("Executive Assistant Aisha Patel", "aisha.assistant@site002.example.com", 8),
    ("Operations Assistant Sarah Naidoo", "sarah.assistant@site002.example.com", 7),
    ("Floor Coordinator Musa Khumalo", "musa.coordinator@site002.example.com", 6),
    ("Team Assistant Lebo Dlamini", "lebo.assistant@site002.example.com", 5),
    ("Project Lead Thabo Mokoena", "thabo.mokoena@site002.example.com", 2),
    ("Finance Manager Naledi Nkosi", "naledi.nkosi@site002.example.com", 1),
)
BLOCK_BOOKER = ("Section Coordinator", "section.coordinator@site002.example.com")
INTELLIGENCE_EMAIL_ISSUES: tuple[str, ...] = ("av", "catering")


@dataclass(frozen=True)
class SimulatedBookingSpec:
    organiser_name: str
    organiser_email: str
    room_name: str
    start_hour: int
    end_hour: int
    anomaly_type: str | None = None
    release_lead_days: int | None = None


@dataclass(frozen=True)
class SimulatedRoomEvent:
    room_code: str
    sensor_id: str
    event_time: datetime
    occupied: bool
    moving: bool | None = None
    stationary: bool | None = None
    behavior: str = "normal"


@dataclass(frozen=True)
class SimulatedFocusSessionSpec:
    room_code: str
    sensor_id: str
    start_time: datetime
    end_time: datetime
    anomaly_type: str | None = None


class SpaceBookingSimulator:
    """Generates synthetic meeting-room bookings and anomalies per simulated day."""

    def __init__(self, data_path: Path | None = None):
        self._data_path = data_path or DATA_PATH
        self._holiday_service = get_site_holiday_service()

    def _stable_seed(self, *parts: str) -> int:
        payload = "|".join(parts).encode("utf-8")
        return int(sha256(payload).hexdigest()[:16], 16)

    def _load_meeting_rooms(self, site_id: str) -> list[str]:
        path = self._data_path / site_id / "zones.json"
        if not path.exists():
            return []

        with open(path) as handle:
            data = json.load(handle)

        zones = data.get("zones", []) if isinstance(data, dict) else []
        meeting_rooms: list[str] = []
        for zone in zones:
            if zone.get("zone_type") != "meeting_room":
                continue
            meeting_rooms.append(zone.get("room_name") or zone.get("friendly_name") or zone["zone_id"])
        return meeting_rooms

    def _load_focus_rooms(self, site_id: str) -> list[str]:
        path = self._data_path / site_id / "zones.json"
        if not path.exists():
            return []

        with open(path) as handle:
            data = json.load(handle)

        zones = data.get("zones", []) if isinstance(data, dict) else []
        focus_rooms: list[str] = []
        for zone in zones:
            if zone.get("zone_type") != "focus_room":
                continue
            focus_rooms.append(zone.get("room_name") or zone.get("friendly_name") or zone["zone_id"])
        return focus_rooms

    def _rng_for_day(self, site_id: str, simulated_date: date) -> random.Random:
        seed = self._stable_seed(site_id, simulated_date.isoformat(), "space-bookings") & 0xFFFFFFFF
        return random.Random(seed)

    def _rng_for_booking(self, site_id: str, booking) -> random.Random:
        seed = (
            self._stable_seed(
                site_id,
                booking.organiser_email,
                booking.room_name or booking.room_id,
                booking.start_time.isoformat(),
                booking.end_time.isoformat(),
            )
            & 0xFFFFFFFF
        )
        return random.Random(seed)

    def _select_meeting_room_organiser(self, rng: random.Random) -> tuple[str, str]:
        """Bias recurring meeting-room bookings toward assistants/coordinators."""
        names = [organiser[0] for organiser in NORMAL_ORGANISERS]
        emails = [organiser[1] for organiser in NORMAL_ORGANISERS]
        weights = [organiser[2] for organiser in NORMAL_ORGANISERS]
        selected_index = rng.choices(range(len(NORMAL_ORGANISERS)), weights=weights, k=1)[0]
        return names[selected_index], emails[selected_index]

    def _ghost_grace_minutes(self) -> int:
        value = get_space_setting("ghost_booking_grace_minutes")
        return int(value) if value is not None else 5

    def _start_of_week(self, target_date: date) -> date:
        return target_date - timedelta(days=target_date.weekday())

    def _week_dates(self, target_date: date) -> list[date]:
        start = self._start_of_week(target_date)
        return [start + timedelta(days=offset) for offset in range(7)]

    def _booking_window_dates(self, site_id: str, simulated_date: date) -> list[date]:
        """Return the rolling booking horizon that should exist in advance."""
        window_dates: list[date] = []
        for offset in range(ADVANCE_BOOKING_WINDOW_DAYS):
            target_date = simulated_date + timedelta(days=offset)
            if self._should_generate_bookings(site_id, target_date):
                window_dates.append(target_date)
        return window_dates

    def _booking_score(self, site_id: str, booking) -> int:
        return self._stable_seed(
            site_id,
            booking.organiser_email,
            booking.room_name or booking.room_id,
            booking.start_time.isoformat(),
            booking.end_time.isoformat(),
            "ghost-budget",
        )

    def _ghost_cluster_key(self, booking) -> tuple[str, str, str, str]:
        return (
            booking.organiser_email,
            booking.booking_date.isoformat(),
            booking.start_time.strftime("%H:%M"),
            booking.end_time.strftime("%H:%M"),
        )

    def _selected_block_booking_weekday(self, site_id: str, simulated_date: date) -> int:
        week_start = self._start_of_week(simulated_date)
        return self._stable_seed(site_id, week_start.isoformat(), "block-booking-day") % 5

    def _selected_intelligence_issue_weekdays(self, site_id: str, simulated_date: date) -> set[int]:
        week_start = self._start_of_week(simulated_date)
        rng = random.Random(self._stable_seed(site_id, week_start.isoformat(), "meeting-room-intake"))
        count = min(MAX_MEETING_ROOM_INTAKE_EMAILS_PER_WEEK, 5)
        return set(rng.sample(range(5), k=count))

    def _selected_focus_overstay_keys(
        self,
        site_id: str,
        simulated_date: date,
        specs: list[SimulatedFocusSessionSpec],
    ) -> set[tuple[str, str]]:
        week_start = self._start_of_week(simulated_date)
        ranked = sorted(
            specs,
            key=lambda spec: (
                self._stable_seed(
                    site_id,
                    week_start.isoformat(),
                    spec.room_code,
                    spec.start_time.isoformat(),
                    "focus-overstay",
                ),
                spec.start_time.isoformat(),
                spec.room_code,
            ),
        )
        selected = ranked[:MAX_FOCUS_ROOM_OVERSTAYS_PER_WEEK]
        return {(spec.room_code, spec.start_time.isoformat()) for spec in selected}

    def _load_week_bookings(self, site_id: str, target_date: date) -> list:
        store = get_booking_store()
        bookings = []
        for week_date in self._week_dates(target_date):
            bookings.extend(store.get_bookings_for_site(site_id, week_date))
        return bookings

    def _select_weekly_ghost_booking_keys(self, site_id: str, bookings: list) -> set[tuple[str, str, str, str]]:
        if not bookings:
            return set()

        week_start = self._start_of_week(min(booking.booking_date for booking in bookings))
        ranked = sorted(
            bookings,
            key=lambda booking: (
                self._stable_seed(
                    site_id,
                    week_start.isoformat(),
                    booking.organiser_email,
                    booking.room_name or booking.room_id,
                    booking.start_time.isoformat(),
                    booking.end_time.isoformat(),
                    "weekly-ghost-selection",
                ),
                booking.start_time.isoformat(),
                booking.room_name or booking.room_id,
            ),
        )
        selected: list = []
        cluster_counts: dict[tuple[str, str, str, str], int] = {}

        for booking in ranked:
            cluster_key = self._ghost_cluster_key(booking)
            if cluster_counts.get(cluster_key, 0) >= MAX_GHOST_BOOKINGS_PER_CLUSTER:
                continue
            selected.append(booking)
            cluster_counts[cluster_key] = cluster_counts.get(cluster_key, 0) + 1
            if len(selected) >= MAX_GHOST_BOOKINGS_PER_WEEK:
                break

        return {
            (
                booking.organiser_email,
                booking.room_name or booking.room_id,
                booking.start_time.isoformat(),
                booking.end_time.isoformat(),
            )
            for booking in selected
        }

    def _sensor_id_for_room(self, room_code: str) -> str:
        return f"SIM-RADAR-{room_code}"

    def _should_ghost_booking(self, site_id: str, booking, week_bookings: list) -> bool:
        selected_keys = self._select_weekly_ghost_booking_keys(site_id, week_bookings)
        booking_key = (
            booking.organiser_email,
            booking.room_name or booking.room_id,
            booking.start_time.isoformat(),
            booking.end_time.isoformat(),
        )
        return booking_key in selected_keys

    def _build_room_events_for_booking(self, site_id: str, booking, week_bookings: list) -> list[SimulatedRoomEvent]:
        room_code = booking.room_name or booking.room_id
        if not room_code:
            return []

        sensor_id = self._sensor_id_for_room(room_code)
        start_time = booking.start_time
        end_time = booking.end_time
        duration_minutes = int((end_time - start_time).total_seconds() / 60)
        if duration_minutes <= 1:
            return []

        ghost_check_time = start_time + timedelta(
            minutes=min(self._ghost_grace_minutes() + 1, max(duration_minutes - 1, 1))
        )
        if self._should_ghost_booking(site_id, booking, week_bookings):
            return [
                SimulatedRoomEvent(
                    room_code=room_code,
                    sensor_id=sensor_id,
                    event_time=ghost_check_time,
                    occupied=False,
                    moving=False,
                    stationary=False,
                    behavior="ghost_no_show",
                )
            ]

        arrival_delay = 2 if duration_minutes <= 60 else 4
        occupy_time = start_time + timedelta(minutes=min(arrival_delay, max(duration_minutes - 1, 1)))
        release_buffer = 2 if duration_minutes <= 60 else 5
        release_time = end_time - timedelta(minutes=min(release_buffer, max(duration_minutes - arrival_delay - 1, 1)))

        events = [
            SimulatedRoomEvent(
                room_code=room_code,
                sensor_id=sensor_id,
                event_time=occupy_time,
                occupied=True,
                moving=True,
                stationary=True,
                behavior="normal_arrival",
            )
        ]
        if release_time > occupy_time:
            events.append(
                SimulatedRoomEvent(
                    room_code=room_code,
                    sensor_id=sensor_id,
                    event_time=release_time,
                    occupied=False,
                    moving=False,
                    stationary=False,
                    behavior="normal_departure",
                )
            )
        return events

    def _room_event_exists(self, event: SimulatedRoomEvent) -> bool:
        for existing in occupancy_store.get_events_for_room(
            event.room_code,
            from_dt=event.event_time,
            to_dt=event.event_time,
        ):
            if (
                existing.source in {"simulation_room_radar", "simulation_focus_radar"}
                and existing.sensor_id == event.sensor_id
                and existing.occupied == event.occupied
                and existing.timestamp == event.event_time
            ):
                return True
        return False

    def _build_focus_session_specs(self, site_id: str, simulated_date: date) -> list[SimulatedFocusSessionSpec]:
        if not self._should_generate_bookings(site_id, simulated_date):
            return []

        focus_rooms = self._load_focus_rooms(site_id)
        if not focus_rooms:
            return []

        rng = random.Random(self._stable_seed(site_id, simulated_date.isoformat(), "focus-rooms"))
        specs: list[SimulatedFocusSessionSpec] = []

        for room_code in focus_rooms:
            chosen_slots = [slot for slot in FOCUS_SESSION_TEMPLATES if rng.random() < 0.38]
            if not chosen_slots:
                chosen_slots = [rng.choice(FOCUS_SESSION_TEMPLATES)]

            for start_hour, start_minute, duration_minutes in sorted(chosen_slots)[:2]:
                start_time = datetime(
                    simulated_date.year,
                    simulated_date.month,
                    simulated_date.day,
                    start_hour,
                    start_minute,
                )
                end_time = start_time + timedelta(minutes=duration_minutes)
                specs.append(
                    SimulatedFocusSessionSpec(
                        room_code=room_code,
                        sensor_id=self._sensor_id_for_room(room_code),
                        start_time=start_time,
                        end_time=end_time,
                    )
                )

        overstay_keys = self._selected_focus_overstay_keys(site_id, simulated_date, specs)
        adjusted_specs: list[SimulatedFocusSessionSpec] = []
        for spec in specs:
            if (spec.room_code, spec.start_time.isoformat()) in overstay_keys:
                adjusted_specs.append(
                    SimulatedFocusSessionSpec(
                        room_code=spec.room_code,
                        sensor_id=spec.sensor_id,
                        start_time=spec.start_time,
                        end_time=spec.start_time + timedelta(minutes=150),
                        anomaly_type="extended_use",
                    )
                )
            else:
                adjusted_specs.append(spec)
        return adjusted_specs

    def _build_focus_room_events_for_day(self, site_id: str, simulated_date: date) -> list[SimulatedRoomEvent]:
        events: list[SimulatedRoomEvent] = []
        for spec in self._build_focus_session_specs(site_id, simulated_date):
            events.append(
                SimulatedRoomEvent(
                    room_code=spec.room_code,
                    sensor_id=spec.sensor_id,
                    event_time=spec.start_time,
                    occupied=True,
                    moving=True,
                    stationary=True,
                    behavior=spec.anomaly_type or "focus_session_start",
                )
            )
            events.append(
                SimulatedRoomEvent(
                    room_code=spec.room_code,
                    sensor_id=spec.sensor_id,
                    event_time=spec.end_time,
                    occupied=False,
                    moving=False,
                    stationary=False,
                    behavior=spec.anomaly_type or "focus_session_end",
                )
            )
        return events

    def _should_generate_bookings(self, site_id: str, simulated_date: date) -> bool:
        if simulated_date.weekday() >= 5:
            return False
        return not self._holiday_service.is_holiday(site_id, simulated_date)

    def _should_inject_block_booking(self, site_id: str, simulated_date: date, rng: random.Random) -> bool:
        if not self._should_generate_bookings(site_id, simulated_date):
            return False

        # Deterministic weekly anomaly budget: at most one block-booking day per week.
        del rng
        return simulated_date.weekday() == self._selected_block_booking_weekday(site_id, simulated_date)

    def _should_emit_intelligence_email(self, site_id: str, simulated_date: date) -> bool:
        if not self._should_generate_bookings(site_id, simulated_date):
            return False
        return simulated_date.weekday() in self._selected_intelligence_issue_weekdays(site_id, simulated_date)

    def _select_intelligence_issue_booking(self, site_id: str, simulated_date: date, day_bookings: list):
        if not self._should_emit_intelligence_email(site_id, simulated_date):
            return None

        eligible = [booking for booking in day_bookings if (booking.room_name or booking.room_id)]
        if not eligible:
            return None

        preferred = [booking for booking in eligible if booking.start_time.hour <= 12 < booking.end_time.hour]
        candidates = preferred or eligible
        return sorted(
            candidates,
            key=lambda booking: (
                self._stable_seed(
                    site_id,
                    simulated_date.isoformat(),
                    booking.organiser_email,
                    booking.room_name or booking.room_id,
                    "meeting-room-intake-booking",
                ),
                booking.start_time.isoformat(),
                booking.room_name or booking.room_id,
            ),
        )[0]

    def _select_issue_type(self, site_id: str, simulated_date: date, booking) -> str:
        preferred = "catering" if booking.start_time.hour <= 12 < booking.end_time.hour else "av"

        selector = self._stable_seed(
            site_id,
            simulated_date.isoformat(),
            booking.room_name or booking.room_id,
            "meeting-room-intake-type",
        )
        if selector % 3 == 0:
            return preferred
        return INTELLIGENCE_EMAIL_ISSUES[selector % len(INTELLIGENCE_EMAIL_ISSUES)]

    def _build_intelligence_email(self, site_id: str, booking, issue_type: str) -> tuple[str, str, datetime]:
        room_code = booking.room_name or booking.room_id
        reported_at = booking.start_time + timedelta(minutes=10)
        reporter_name = booking.organiser_name or "Meeting Organiser"
        reporter_email = booking.organiser_email or "user@site002.example.com"
        helpdesk_sent = reported_at + timedelta(minutes=4)

        if issue_type == "catering":
            subject = f"Fw: Meeting room catering issue - {room_code}"
            original_body = (
                f"Good day. Catering for the meeting in {room_code} at {site_id} has not arrived. "
                "The room is booked and the delegates are waiting. Please assist."
            )
        else:
            subject = f"Fw: Meeting room AV issue - {room_code}"
            original_body = (
                f"Good day. The display and HDMI setup in meeting room {room_code} at {site_id} is not working. "
                "Please attend because the team cannot start the session."
            )

        body = (
            "________________________________\n"
            f"From: Site 002 Helpdesk <{HELPDESK_MAILBOX_EMAIL}>\n"
            f"Sent: {helpdesk_sent.strftime('%A, %d %B %Y %H:%M')}\n"
            f"To: {INTAKE_MAILBOX_EMAIL}\n"
            "Cc: facilities.manager@site002.example.com\n"
            f"Subject: {subject}\n\n"
            "Please see below and advise.\n\n"
            f"From: {reporter_name} <{reporter_email}>\n"
            f"Sent: {reported_at.strftime('%A, %d %B %Y %H:%M')}\n"
            f"To: Site 002 Helpdesk <{HELPDESK_MAILBOX_EMAIL}>\n"
            f"Subject: {subject.replace('Fw: ', '')}\n\n"
            f"{original_body}\n"
        )
        return subject, body, helpdesk_sent

    async def _emit_intelligence_signal(self, subject: str, body_plain: str, received_at: datetime) -> dict:
        from app.services.signal_emitter import emit_email_signal

        return await emit_email_signal(
            from_email=HELPDESK_MAILBOX_EMAIL,
            from_name="Site 002 Helpdesk",
            subject=subject,
            body_plain=body_plain,
            to=[INTAKE_MAILBOX_EMAIL],
            cc=["facilities.manager@site002.example.com"],
            received_at=received_at.isoformat(),
        )

    def _build_normal_day_specs(
        self, site_id: str, simulated_date: date, meeting_rooms: list[str]
    ) -> list[SimulatedBookingSpec]:
        rng = self._rng_for_day(site_id, simulated_date)
        specs: list[SimulatedBookingSpec] = []

        for room_name in meeting_rooms:
            for start_hour, end_hour in NORMAL_SLOTS:
                if rng.random() > 0.72:
                    continue
                organiser_name, organiser_email = self._select_meeting_room_organiser(rng)
                specs.append(
                    SimulatedBookingSpec(
                        organiser_name=organiser_name,
                        organiser_email=organiser_email,
                        room_name=room_name,
                        start_hour=start_hour,
                        end_hour=end_hour,
                        release_lead_days=rng.choice((0, 1, 2, 3, 5, 7, 10, 14, 21)),
                    )
                )

        return specs

    def _build_block_booking_specs(self, meeting_rooms: list[str]) -> list[SimulatedBookingSpec]:
        organiser_name, organiser_email = BLOCK_BOOKER
        stagger_plan = [15, 8, 2, 1, 0, 0]
        return [
            SimulatedBookingSpec(
                organiser_name=organiser_name,
                organiser_email=organiser_email,
                room_name=room_name,
                start_hour=8,
                end_hour=17,
                anomaly_type="block_booking",
                release_lead_days=stagger_plan[index] if index < len(stagger_plan) else 0,
            )
            for index, room_name in enumerate(sorted(meeting_rooms))
        ]

    def _build_day_specs(self, site_id: str, simulated_date: date) -> list[SimulatedBookingSpec]:
        if not self._should_generate_bookings(site_id, simulated_date):
            return []

        meeting_rooms = self._load_meeting_rooms(site_id)
        if not meeting_rooms:
            return []

        rng = self._rng_for_day(site_id, simulated_date)
        if self._should_inject_block_booking(site_id, simulated_date, rng):
            return self._build_block_booking_specs(meeting_rooms)

        return self._build_normal_day_specs(site_id, simulated_date, meeting_rooms)

    def _build_raw_email(self, site_id: str, simulated_date: date, spec: SimulatedBookingSpec) -> str:
        start_dt = datetime(simulated_date.year, simulated_date.month, simulated_date.day, spec.start_hour, 0)
        end_dt = datetime(simulated_date.year, simulated_date.month, simulated_date.day, spec.end_hour, 0)
        subject = f"Accepted: {spec.room_name} booking"

        return (
            f"From: {spec.organiser_name} <{spec.organiser_email}>\n"
            "To: rooms@sentinel-ai.co.za\n"
            f"Subject: {subject}\n"
            f"Date: {start_dt.strftime('%a, %d %b %Y %H:%M:%S +0200')}\n"
            'Content-Type: text/plain; charset="utf-8"\n\n'
            "Your meeting has been confirmed.\n\n"
            f"Organizer: {spec.organiser_name} <{spec.organiser_email}>\n"
            f"Location: {spec.room_name}\n"
            f"Start: {start_dt.strftime('%A, %d %B %Y %H:%M')}\n"
            f"End: {end_dt.strftime('%A, %d %B %Y %H:%M')}\n"
            f"Site: {site_id}\n"
        )

    def _release_date_for_spec(self, booking_date: date, spec: SimulatedBookingSpec) -> date:
        lead_days = max(0, min(spec.release_lead_days or 0, ADVANCE_BOOKING_WINDOW_DAYS))
        return booking_date - timedelta(days=lead_days)

    async def _ingest_bookings_for_date(
        self, site_id: str, simulated_date: date, booking_date: date, store, config
    ) -> dict[str, int]:
        """Generate booking confirmations for one meeting date and raise any overlap alerts."""
        specs = [
            spec
            for spec in self._build_day_specs(site_id, booking_date)
            if self._release_date_for_spec(booking_date, spec) <= simulated_date
        ]
        if not specs:
            return {
                "generated_bookings": 0,
                "saved_bookings": 0,
                "alerts_generated": 0,
                "alerts_notified": 0,
            }

        saved_bookings = 0
        for spec in specs:
            raw_email = self._build_raw_email(site_id, booking_date, spec)
            record = parse_booking_confirmation(raw_email)
            if not record:
                logger.warning("Failed to parse simulated booking email for %s on %s", spec.room_name, booking_date)
                continue
            if record.site_id != site_id:
                logger.warning(
                    "Simulated booking resolved to unexpected site: expected=%s actual=%s room=%s",
                    site_id,
                    record.site_id,
                    spec.room_name,
                )
                continue
            if store.booking_exists(record.raw_email_hash):
                continue
            store.save_booking(record)
            saved_bookings += 1

        day_bookings = store.get_bookings_for_site(site_id, booking_date)
        new_alerts = detect_overlaps(site_id, day_bookings, config, store)

        alerts_notified = 0
        for alert in new_alerts:
            stored_alert = store.save_alert(alert)
            store.flag_bookings(alert.booking_ids)
            if await send_block_booking_alert(stored_alert, config, site_name=site_id):
                alerts_notified += 1

        if new_alerts:
            logger.info(
                "Space booking simulator raised %d alert(s) for %s on %s",
                len(new_alerts),
                site_id,
                booking_date.isoformat(),
            )

        return {
            "generated_bookings": len(specs),
            "saved_bookings": saved_bookings,
            "alerts_generated": len(new_alerts),
            "alerts_notified": alerts_notified,
        }

    async def ingest_day(self, site_id: str, simulated_date: date) -> dict[str, int | bool]:
        """Top up a rolling 4-week booking horizon and emit day-of issue emails."""
        config = get_block_booking_config(site_id)
        if not config.enabled:
            return {
                "generated_bookings": 0,
                "saved_bookings": 0,
                "alerts_generated": 0,
                "alerts_notified": 0,
                "intelligence_emails_generated": 0,
                "intelligence_signals_created": 0,
            }

        store = get_booking_store()
        summary = {
            "generated_bookings": 0,
            "saved_bookings": 0,
            "alerts_generated": 0,
            "alerts_notified": 0,
            "intelligence_emails_generated": 0,
            "intelligence_signals_created": 0,
        }

        for booking_date in self._booking_window_dates(site_id, simulated_date):
            date_summary = await self._ingest_bookings_for_date(site_id, simulated_date, booking_date, store, config)
            summary["generated_bookings"] += date_summary["generated_bookings"]
            summary["saved_bookings"] += date_summary["saved_bookings"]
            summary["alerts_generated"] += date_summary["alerts_generated"]
            summary["alerts_notified"] += date_summary["alerts_notified"]

        intelligence_emails_generated = 0
        intelligence_signals_created = 0
        if self._should_generate_bookings(site_id, simulated_date):
            day_bookings = store.get_bookings_for_site(site_id, simulated_date)
            selected_booking = self._select_intelligence_issue_booking(site_id, simulated_date, day_bookings)
            if selected_booking:
                issue_type = self._select_issue_type(site_id, simulated_date, selected_booking)
                subject, body_plain, received_at = self._build_intelligence_email(site_id, selected_booking, issue_type)
                result = await self._emit_intelligence_signal(subject, body_plain, received_at)
                intelligence_emails_generated = 1
                intelligence_signals_created = int(result.get("status") == "created")

        summary["intelligence_emails_generated"] = intelligence_emails_generated
        summary["intelligence_signals_created"] = intelligence_signals_created
        return summary

    async def replay_hour(self, site_id: str, simulated_time: datetime) -> dict[str, int]:
        """Replay simulated room-radar events for the current simulated hour."""
        if not self._should_generate_bookings(site_id, simulated_time.date()):
            return {
                "events_replayed": 0,
                "meeting_room_events_replayed": 0,
                "focus_room_events_replayed": 0,
                "ghost_findings_created": 0,
                "ghost_notifications_sent": 0,
            }

        store = get_booking_store()
        day_bookings = store.get_bookings_for_site(site_id, simulated_time.date())
        week_bookings = self._load_week_bookings(site_id, simulated_time.date())
        events_replayed = 0
        meeting_room_events_replayed = 0
        focus_room_events_replayed = 0
        ghost_findings_created = 0
        ghost_notifications_sent = 0

        for booking in day_bookings:
            for event in self._build_room_events_for_booking(site_id, booking, week_bookings):
                if event.event_time.hour != simulated_time.hour:
                    continue
                if self._room_event_exists(event):
                    continue

                result = await process_occupancy_event(
                    site_id=site_id,
                    room_code=event.room_code,
                    sensor_id=event.sensor_id,
                    occupied=event.occupied,
                    source="simulation_room_radar",
                    room_type="meeting",
                    timestamp=event.event_time,
                    moving=event.moving,
                    stationary=event.stationary,
                    distance_m=1.4 if event.occupied else None,
                )
                events_replayed += 1
                meeting_room_events_replayed += 1
                ghost_findings_created += int(result.get("ghost_findings_created", 0))
                ghost_notifications_sent += int(result.get("ghost_notifications_sent", 0))

        for event in self._build_focus_room_events_for_day(site_id, simulated_time.date()):
            if event.event_time.hour != simulated_time.hour:
                continue
            if self._room_event_exists(event):
                continue

            await process_occupancy_event(
                site_id=site_id,
                room_code=event.room_code,
                sensor_id=event.sensor_id,
                occupied=event.occupied,
                source="simulation_focus_radar",
                room_type="focus",
                timestamp=event.event_time,
                moving=event.moving,
                stationary=event.stationary,
                distance_m=1.0 if event.occupied else None,
            )
            events_replayed += 1
            focus_room_events_replayed += 1

        return {
            "events_replayed": events_replayed,
            "meeting_room_events_replayed": meeting_room_events_replayed,
            "focus_room_events_replayed": focus_room_events_replayed,
            "ghost_findings_created": ghost_findings_created,
            "ghost_notifications_sent": ghost_notifications_sent,
        }


_space_booking_simulator: SpaceBookingSimulator | None = None


def get_space_booking_simulator() -> SpaceBookingSimulator:
    global _space_booking_simulator
    if _space_booking_simulator is None:
        _space_booking_simulator = SpaceBookingSimulator()
    return _space_booking_simulator
