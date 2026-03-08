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
from enum import Enum
from typing import Optional


class RightSizingPattern(str, Enum):
    """Detectable room underuse patterns (presence-based, not count-based)."""

    EARLY_VACATE = "early_vacate"  # Room occupied then vacated >90 min before booking end
    SPORADIC_USE = "sporadic_use"  # Total occupied time < 25% of booking duration
    BRIEF_OCCUPATION = "brief_occupation"  # Occupied < 30 min, then empty for remainder


@dataclass
class OccupancyEvent:
    """A single presence event from an mmWave sensor.

    The HLK-LD2410C reports presence zones, NOT verified headcount.
    There is no ``count`` field — all logic uses ``occupied: bool`` only.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    site_id: str = ""
    room_code: str = ""
    sensor_id: str = ""
    occupied: bool = False  # True = presence detected, False = no presence
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: str = ""  # e.g. "mmwave_ld2410c"
    received_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class GhostBookingFinding:
    """A booking with zero occupancy detected — the room was never used.

    Workflow:
      1. Sensor reports no movement for grace_period_minutes -> status='open'
      2. Concierge notified -> status='pending_inspection'
      3. Concierge physically inspects and confirms empty -> status='released'
         - charge_amount and cost_centre recorded against organiser
      4. OR sensor detects movement -> status='verified_occupied' (auto-resolved)
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    site_id: str = ""
    room_code: str = ""
    room_name: str = ""
    booking_id: str = ""
    organiser_email: str = ""
    organiser_name: str = ""
    booking_start: datetime = field(default_factory=datetime.utcnow)
    booking_end: datetime = field(default_factory=datetime.utcnow)
    grace_period_minutes: int = 0
    detected_at: datetime = field(default_factory=datetime.utcnow)
    notification_sent: bool = False
    notification_sent_at: Optional[datetime] = None
    status: str = "open"  # 'open' | 'pending_inspection' | 'verified_occupied' | 'released' | 'dismissed'
    resolved_at: Optional[datetime] = None
    # Concierge inspection fields
    inspected_by: Optional[str] = None  # Concierge name/ID who confirmed
    inspected_at: Optional[datetime] = None
    # Charge fields — recorded when concierge confirms room empty
    cost_centre: Optional[str] = None  # Organiser's cost centre / department
    charge_amount: Optional[float] = None  # Penalty amount (currency from site config)
    charge_reason: Optional[str] = None  # e.g. "Ghost booking - room unused for 45 minutes"


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
    notification_sent_at: Optional[datetime] = None
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
    end_time: Optional[datetime] = None  # None = session still active
    duration_seconds: int = 0  # Computed on close
    extended_use: bool = False  # True if duration > threshold
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_active(self) -> bool:
        return self.end_time is None

    def close(self, end: datetime, extended_threshold: int = 7200) -> None:
        """Close this session and compute duration + extended_use flag."""
        self.end_time = end
        self.duration_seconds = int((end - self.start_time).total_seconds())
        self.extended_use = self.duration_seconds > extended_threshold
