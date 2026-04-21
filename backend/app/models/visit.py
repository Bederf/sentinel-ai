"""Visit Management data models.

Provides data structures for:
- Visit lifecycle (created -> arrived -> registered -> approved/denied -> active -> expired/cancelled)
- Building Map (outlook_location_string -> building_id resolution)
- Access card tracking
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class VisitStatus(StrEnum):
    """Visit lifecycle states.

    PENDING    — Invite received, visitor has not yet accepted
    CREATED    — Visitor accepted, QR sent
    ARRIVED    — Visitor scanned at reception (QR or PIN)
    REGISTERED — Visitor name/photo captured by reception
    APPROVED   — Host approved via WhatsApp
    DENIED     — Host denied access
    ACTIVE     — Access card issued, visitor on premises
    EXPIRED    — Past meeting_end or timed out
    CANCELLED  — Event cancelled or visitor declined
    """

    PENDING = "pending"
    CREATED = "created"
    ARRIVED = "arrived"
    REGISTERED = "registered"
    APPROVED = "approved"
    DENIED = "denied"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Visit(BaseModel):
    """Full visit record with complete lifecycle fields."""

    model_config = ConfigDict(use_enum_values=True, ser_json_timedelta="iso8601")

    id: UUID
    token: UUID  # Primary lookup key — QR payload
    pin: str  # 6-digit zero-padded fallback
    visitor_email: str
    visitor_name: str | None = None
    host_email: str
    host_name: str | None = None
    host_mobile: str | None = None
    building_id: str
    meeting_subject: str | None = None  # Subject of the meeting (from calendar event)

    meeting_start: datetime
    meeting_end: datetime
    status: VisitStatus
    visitor_photo: str | None = None  # base64 encoded
    visitor_vehicle: str | None = None
    visitor_id_number: str | None = None
    access_card_id: str | None = None
    qr_code: str | None = None  # base64 PNG
    created_at: datetime
    updated_at: datetime
    external_event_id: str | None = None  # Graph event ID for idempotency

    def dict(self, *args, **kwargs):
        """Pydantic v1-style dict export for backward compatibility."""
        return {
            "id": str(self.id),
            "token": str(self.token),
            "pin": self.pin,
            "visitor_email": self.visitor_email,
            "visitor_name": self.visitor_name,
            "host_email": self.host_email,
            "host_name": self.host_name,
            "host_mobile": self.host_mobile,
            "building_id": self.building_id,
            "meeting_subject": self.meeting_subject,
            "meeting_start": self.meeting_start.isoformat(),
            "meeting_end": self.meeting_end.isoformat(),
            "status": self.status,
            "visitor_photo": self.visitor_photo,
            "visitor_vehicle": self.visitor_vehicle,
            "visitor_id_number": self.visitor_id_number,
            "access_card_id": self.access_card_id,
            "qr_code": self.qr_code,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "external_event_id": self.external_event_id,
        }


class BuildingMap(BaseModel):
    """Maps an Outlook location string to a site building_id."""

    id: UUID
    name: str  # e.g. "Fairlands Office"
    outlook_location_string: str  # e.g. "FAIRLANDS", "1 FICA ROAD"
    site_id: str  # maps to existing site.code

    def dict(self, *args, **kwargs):
        """Pydantic v1-style dict export for backward compatibility."""
        return {
            "id": str(self.id),
            "name": self.name,
            "outlook_location_string": self.outlook_location_string,
            "site_id": self.site_id,
        }
