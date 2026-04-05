"""Canonical MaintenanceEvent schema — normalised from MRI Evolution job cards."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MaintenanceEvent(BaseModel):
    """Normalised maintenance/work order event from MRI Evolution."""

    external_ref: str = Field(..., description="e.g. 'FNBFW:30453' — immutable external key")
    source_system: str = Field(default="mri_evolution")
    site_id: UUID | None = None
    building: str | None = None
    location: str | None = None
    discipline: str | None = None
    problem: str | None = None
    priority_raw: str | None = None
    priority_normalised: str | None = Field(None, pattern=r"^(P1|P2|P3|P4)$")
    sla_respond_hours: int | None = None
    sla_attend_hours: int | None = None
    sla_temp_fix_hours: int | None = None
    sla_resolve_work_days: int | None = None
    is_ppm: bool = False
    status: str | None = None
    created_at_source: datetime | None = None
    assigned_at: datetime | None = None
    attended_at: datetime | None = None
    temp_fixed_at: datetime | None = None
    resolved_at: datetime | None = None
    level_of_completion: str | None = None
    sla_pct: float | None = None
    days_open: int | None = None
    metadata: dict = Field(default_factory=dict)
