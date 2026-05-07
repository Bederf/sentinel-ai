"""Pydantic schemas for Fairlands SLA Dashboard API endpoints."""

from datetime import date, datetime

from pydantic import BaseModel


class MilestoneStatusResponse(BaseModel):
    recommendation_id: str
    title: str
    milestone_status: str
    assigned_at: datetime
    in_progress_at: datetime | None
    resolved_at: datetime | None
    verified_at: datetime | None
    sla_deadline_at: datetime | None
    elapsed_pct: float  # 0.0-1.0+ (can exceed 1.0 when breached)
    is_breached: bool
    rag_status: str  # GREEN, YELLOW, RED


class SLABreachResponse(BaseModel):
    recommendation_id: str
    title: str
    milestone_status: str
    sla_deadline_at: datetime
    breach_pct: float  # e.g., 1.23 = 123% past deadline
    days_overdue: float


class ClusterAlertResponse(BaseModel):
    equipment_id: str
    issue_type: str
    cluster_count: int
    first_occurrence: datetime
    last_occurrence: datetime
    urgency_boost: float


class FirePumpComplianceResponse(BaseModel):
    equipment_id: str
    last_test_date: date | None
    next_test_date: date | None
    compliance_rate: float  # 0.0-1.0
    is_overdue: bool
    days_overdue: int | None
    regulatory_reference: str = "FNBFW:32335"


class SLASummaryResponse(BaseModel):
    site_code: str
    total_open: int
    assigned: int
    in_progress: int
    resolved: int
    verified: int
    breach_count: int
    cluster_alert_count: int
    compliance_rate: float
    generated_at: datetime
