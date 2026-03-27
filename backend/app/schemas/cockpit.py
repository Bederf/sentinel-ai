from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

IssueSeverity = Literal["critical", "high", "medium", "low"]
IssueSource = Literal["bms", "intake", "tech"]
IssueStatus = Literal["new", "triaged", "in_progress", "resolved"]
CockpitActionType = Literal["acknowledge", "assign", "create_work_order", "escalate"]
AuditActorType = Literal["user", "system"]
AuditOutcome = Literal["success", "rejected", "failed"]
SourceHealthState = Literal["healthy", "stale", "degraded", "unavailable"]
SourceBadgeTone = Literal["normal", "warning", "critical"]


class CockpitIssueEvidenceRef(BaseModel):
    id: str
    kind: Literal["telemetry", "email", "ticket", "recommendation", "observation"]
    label: str
    source: IssueSource


class CockpitIssueLocation(BaseModel):
    zone_ids: list[str] = []
    asset_ids: list[str] = []
    floor_id: str | None = None


class CockpitIssue(BaseModel):
    id: str
    title: str
    summary: str
    severity: IssueSeverity
    source: IssueSource
    status: IssueStatus
    owner: str | None = None
    owner_team: str | None = None
    opened_at: datetime
    updated_at: datetime
    sla_due_at: datetime | None = None
    stale: bool = False
    impact_summary: str | None = None
    cause_hypothesis: str | None = None
    recommended_action: str | None = None
    confidence: float | None = None
    confidence_label: str | None = None
    location: CockpitIssueLocation
    evidence_refs: list[CockpitIssueEvidenceRef] = []
    source_record_id: str | None = None


class CockpitSourceStatus(BaseModel):
    source: IssueSource
    label: str
    state: SourceHealthState
    badge_tone: SourceBadgeTone
    last_updated_at: datetime | None = None
    freshness_seconds: int | None = None
    stale_after_seconds: int
    degraded_after_seconds: int
    degraded_confidence: bool = False
    message: str


class CockpitActionAudit(BaseModel):
    id: str
    issue_id: str
    action: CockpitActionType
    actor_type: AuditActorType
    actor_id: str
    actor_label: str
    occurred_at: datetime
    outcome: AuditOutcome
    status_before: IssueStatus
    status_after: IssueStatus
    notes: str | None = None
    evidence_refs: list[str] = []
    work_order_id: str | None = None
