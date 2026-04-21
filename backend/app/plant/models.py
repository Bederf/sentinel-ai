"""Data models for Desigo building alarm pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class AlarmSeverity(StrEnum):
    """Severity classification for Desigo building alarms."""

    VERY_CRITICAL = "very_critical"
    CRITICAL = "critical"
    NON_CRITICAL = "non_critical"
    CLEARED = "cleared"


class DesigoBuildingAlarm(BaseModel):
    """Structured representation of a Desigo BMS fault notification."""

    id: str = Field(..., description="UUID identifier for this alarm")
    site_id: str = Field(..., description="Site identifier (e.g. FLN02)")
    building: str = Field(default="", description="Building name if known")
    raw_subject: str = Field(..., description="Original email subject line")
    raw_body: str = Field(..., description="Original email body")
    equipment_description: str = Field(..., description="Extracted equipment description")
    alarm_type: str = Field(..., description="Extracted alarm type (e.g. Fail Status)")
    status: str = Field(..., description="Extracted status word (Normal, Fault, Trip, etc.)")
    severity: AlarmSeverity = Field(..., description="Classified alarm severity")
    equipment_category: str = Field(
        default="unknown", description="Equipment category (hvac, power, fire_safety, etc.)"
    )
    received_at: datetime = Field(..., description="When the email was received")
    notified: bool = Field(default=False, description="Whether notification was sent")
    notified_at: datetime | None = Field(default=None, description="When notification was sent")
    cleared: bool = Field(default=False, description="Whether alarm has been cleared")
    cleared_at: datetime | None = Field(default=None, description="When alarm was cleared")
