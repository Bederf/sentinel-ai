"""Pydantic schemas for Visit Management API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

# ==============================================================================
# Request Schemas
# ==============================================================================


class VisitCreate(BaseModel):
    """Payload to create a new visit (internal use by token service)."""

    visitor_email: EmailStr
    host_email: EmailStr
    host_name: str | None = None
    host_mobile: str | None = None
    building_id: str
    meeting_start: datetime
    meeting_end: datetime
    visitor_name: str | None = None
    visitor_vehicle: str | None = None


class ScanRequest(BaseModel):
    """Scan at reception — token OR pin."""

    model_config = {"extra": "forbid"}

    token: UUID | None = None
    pin: str | None = Field(default=None, pattern=r"^\d{6}$")  # exactly 6 digits


class RegisterRequest(BaseModel):
    """Capture visitor details at reception."""

    model_config = {"extra": "forbid"}

    token: UUID
    visitor_name: str = Field(min_length=1, max_length=200)
    photo: str = Field(min_length=1, description="base64 encoded photo")
    vehicle: str | None = Field(default=None, max_length=100)
    id_number: str | None = Field(default=None, max_length=50)


class IssueCardRequest(BaseModel):
    """Issue an access card to a registered visitor."""

    model_config = {"extra": "forbid"}

    token: UUID
    access_card_id: str = Field(min_length=1, max_length=100)


# ==============================================================================
# Response Schemas
# ==============================================================================


class VisitResponse(BaseModel):
    """Full visit record returned by API endpoints."""

    id: UUID
    token: UUID
    pin: str
    visitor_email: str
    visitor_name: str | None = None
    host_email: str
    host_name: str | None = None
    host_mobile: str | None = None
    building_id: str
    meeting_start: datetime
    meeting_end: datetime
    status: str
    visitor_photo: str | None = None
    visitor_vehicle: str | None = None
    visitor_id_number: str | None = None
    access_card_id: str | None = None
    qr_code: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScanResponse(BaseModel):
    """Response from /reception/scan — includes host + meeting info."""

    visit: VisitResponse
    building_name: str | None = None
    time_window_valid: bool


class RegisterResponse(BaseModel):
    """Response from /reception/register."""

    visit: VisitResponse
    message: str = "Visitor registered successfully"


class IssueCardResponse(BaseModel):
    """Response from /reception/issue-card."""

    visit_id: UUID
    status: str = "active"
    access_card_id: str


class BuildingMapResponse(BaseModel):
    """A single building map entry."""

    id: UUID
    name: str
    outlook_location_string: str
    site_id: str

    model_config = {"from_attributes": True}
