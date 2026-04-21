"""Data models for Space Intelligence (Rev 1.4).

OccupancyEvent: presence-only sensor event (no headcount — LD2410C limitation).
GhostBookingFinding: zero-occupancy booking detection with concierge workflow.
RightSizingFinding: pattern-based underuse detection for active bookings.
RightSizingPattern: enum of detectable usage patterns.
FocusRoomSession: continuous occupancy session for unbookable focus rooms (Phase 2).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class RightSizingPattern(StrEnum):
    """Detectable room underuse patterns (presence-based, not count-based)."""

    EARLY_VACATE = "early_vacate"  # Room occupied then vacated >90 min before booking end
    SPORADIC_USE = "sporadic_use"  # Total occupied time < 25% of booking duration
    BRIEF_OCCUPATION = "brief_occupation"  # Occupied < 30 min, then empty for remainder


@dataclass
class OccupancyEvent:
    """A single presence event from an mmWave sensor.

    The HLK-LD2410C reports presence zones, NOT verified headcount.
    There is no ``count`` field — all logic uses ``occupied: bool`` only.

    Radar telemetry fields (optional) capture the raw LD2410C state:
    - moving/stationary: which detection type triggered
    - distance_m: measured distance to target (0.75 m gate resolution)
    - moving_gate/static_gate: which distance gate triggered (0–8)
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    site_id: str = ""
    room_code: str = ""
    sensor_id: str = ""
    occupied: bool = False  # True = presence detected, False = no presence
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: str = ""  # e.g. "mmwave_ld2410c"
    received_at: datetime = field(default_factory=datetime.utcnow)
    # Radar telemetry (optional — populated when MQTT payload includes them)
    moving: bool | None = None
    stationary: bool | None = None
    distance_m: float | None = None
    moving_gate: int | None = None
    static_gate: int | None = None


@dataclass
class GhostBookingFinding:
    """A booking with zero occupancy detected — the room was never used.

    Workflow:
      1. Sensor reports no movement for grace_period_minutes -> status='open'
      2. Concierge notified -> status='pending_inspection'
      3. Concierge physically inspects and confirms outcome:
         - occupied -> status='verified_occupied'
         - empty -> status='confirmed_empty'
      4. OR sensor detects movement -> status='verified_occupied' (auto-resolved)
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    site_id: str = ""
    room_code: str = ""
    room_name: str = ""
    booking_id: str = ""
    organiser_email: str = ""
    organiser_name: str = ""
    source_booking_flagged: bool = False
    booking_start: datetime = field(default_factory=datetime.utcnow)
    booking_end: datetime = field(default_factory=datetime.utcnow)
    grace_period_minutes: int = 0
    detected_at: datetime = field(default_factory=datetime.utcnow)
    notification_sent: bool = False
    notification_sent_at: datetime | None = None
    status: str = "open"  # 'open' | 'pending_inspection' | 'verified_occupied' | 'confirmed_empty' | 'dismissed'
    resolved_at: datetime | None = None
    # Concierge inspection fields
    inspected_by: str | None = None  # Concierge name/ID who confirmed
    inspected_at: datetime | None = None
    concierge_email: str | None = None
    concierge_whatsapp: str | None = None
    email_notified_at: datetime | None = None
    whatsapp_notified_at: datetime | None = None
    whatsapp_message_id: str | None = None
    telegram_notified_at: datetime | None = None
    telegram_message_id: str | None = None
    response_message_id: str | None = None
    response_text: str | None = None
    # Reminder tracking — one reminder sent if concierge doesn't reply within 15 min
    reminder_sent: bool = False
    reminder_sent_at: datetime | None = None
    # Legacy fields retained for backward compatibility with older stored records.
    cost_centre: str | None = None
    charge_amount: float | None = None
    charge_reason: str | None = None


@dataclass
class RightSizingFinding:
    """A pattern-based underuse detection for an active booking.

    Replaces count-based logic — LD2410C cannot provide reliable headcount.
    Detection uses presence duration patterns instead.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    site_id: str = ""
    room_code: str = ""
    room_name: str = ""
    room_capacity: int = 0
    booking_id: str = ""
    organiser_email: str = ""
    organiser_name: str = ""
    booking_start: datetime = field(default_factory=datetime.utcnow)
    booking_end: datetime = field(default_factory=datetime.utcnow)
    booking_duration_minutes: int = 0  # Total booked duration
    occupied_minutes: int = 0  # Total time sensor showed occupied=True
    vacancy_started_at: datetime = field(default_factory=datetime.utcnow)  # When room went empty
    consecutive_vacancy_minutes: int = 0  # How long continuously empty
    pattern_type: str = ""  # RightSizingPattern value
    detected_at: datetime = field(default_factory=datetime.utcnow)
    notification_sent: bool = False
    notification_sent_at: datetime | None = None
    status: str = "open"  # 'open' | 'acknowledged' | 'dismissed'


@dataclass
class FocusRoomSession:
    """A continuous occupancy session in a focus room (Phase 2).

    Focus rooms have no booking system. Sessions are derived from raw
    occupancy events: occupied=True starts a session, occupied=False ends it.

    Sessions shorter than ``min_session_seconds`` (default 180s / 3 min) are
    discarded as noise (door checks, cleaning, availability scans).

    Sessions longer than ``extended_use_threshold_seconds`` (default 7200s / 2h)
    are flagged as extended use.
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    site_id: str = ""
    room_code: str = ""
    room_type: str = "focus"  # 'focus' | 'meeting'
    sensor_id: str = ""
    source: str = "mmwave_ld2410c"
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: datetime | None = None  # None = session still active
    duration_seconds: int = 0  # Computed on close
    extended_use: bool = False  # True if duration > threshold
    created_at: datetime = field(default_factory=datetime.utcnow)
    vacant_since: datetime | None = None  # When room went vacant (gap tolerance)

    @property
    def is_active(self) -> bool:
        return self.end_time is None

    def close(self, end: datetime, extended_threshold: int = 7200) -> None:
        """Close this session and compute duration + extended_use flag."""
        self.end_time = end
        self.duration_seconds = int((end - self.start_time).total_seconds())
        self.extended_use = self.duration_seconds > extended_threshold
