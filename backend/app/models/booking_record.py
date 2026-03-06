"""Data models for the Block Booking Detection module.

BookingRecord: represents a single room reservation parsed from a confirmation email.
BlockBookingAlert: represents a detected overlap where one organiser holds multiple rooms.
BlockBookingConfig: per-site configuration for detection thresholds and notification targets.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class BookingRecord:
    """A single room booking extracted from a confirmation email."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    site_id: str = ""
    organiser_email: str = ""
    organiser_name: str = ""
    room_id: str = ""
    room_name: str = ""
    booking_date: date = field(default_factory=date.today)
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: datetime = field(default_factory=datetime.utcnow)
    raw_email_hash: str = ""
    ingested_at: datetime = field(default_factory=datetime.utcnow)
    flagged: bool = False


@dataclass
class BlockBookingAlert:
    """An overlap alert where one organiser holds multiple rooms simultaneously."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    site_id: str = ""
    organiser_email: str = ""
    organiser_name: str = ""
    overlap_window_start: datetime = field(default_factory=datetime.utcnow)
    overlap_window_end: datetime = field(default_factory=datetime.utcnow)
    rooms: list[str] = field(default_factory=list)
    room_count: int = 0
    booking_ids: list[str] = field(default_factory=list)
    detected_at: datetime = field(default_factory=datetime.utcnow)
    notification_sent: bool = False
    notification_sent_at: Optional[datetime] = None
    dismissed: bool = False
    dismissed_at: Optional[datetime] = None
    dismissed_by: Optional[str] = None


@dataclass
class BlockBookingConfig:
    """Per-site configuration for block booking detection."""

    site_id: str = ""
    min_rooms_for_alert: int = 2
    full_day_threshold_hours: float = 6.0
    lookahead_days: int = 14
    enabled: bool = True
    concierge_email: Optional[str] = None
    concierge_whatsapp: Optional[str] = None
    concierge_telegram_chat_id: Optional[str] = None
