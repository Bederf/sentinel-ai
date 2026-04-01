"""Visit Management data models.

Provides data structures for:
- Visit lifecycle (created -> arrived -> registered -> approved/denied -> active -> expired/cancelled)
- Building Map (outlook_location_string -> building_id resolution)
- Access card tracking
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class VisitStatus(str, Enum):
    """Visit lifecycle states.

    CREATED    — Outlook event created, QR sent to visitor
    ARRIVED    — Visitor scanned at reception (QR or PIN)
    REGISTERED — Visitor name/photo captured by reception
    APPROVED   — Host approved via WhatsApp
    DENIED     — Host denied access
    ACTIVE     — Access card issued, visitor on premises
    EXPIRED    — Past meeting_end or timed out
    CANCELLED  — Explicitly cancelled
    """

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
    visitor_name: Optional[str] = None
    host_email: str
    host_name: Optional[str] = None
    host_mobile: Optional[str] = None
    building_id: str
    meeting_start: datetime
    meeting_end: datetime
    status: VisitStatus
    visitor_photo: Optional[str] = None  # base64 encoded
    visitor_vehicle: Optional[str] = None
    visitor_id_number: Optional[str] = None
    access_card_id: Optional[str] = None
    qr_code: Optional[str] = None  # base64 PNG
    created_at: datetime
    updated_at: datetime

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
