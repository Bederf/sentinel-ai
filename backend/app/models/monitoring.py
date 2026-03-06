"""Monitoring models for Phase 108: Monitoring Hardening.

Provides unified KPI, alert, and trend models for ingestion mode observability.
"""

from pydantic import BaseModel


class IngestionKPIs(BaseModel):
    """Key performance indicators for data ingestion health."""

    freshness_hours: float
    error_rate: float
    unmatched_points: int
    total_points: int
    match_coverage: float
    provenance_summary: dict[str, int]  # {"live_protocol": N, "file_manual": M}


class ControlKPIs(BaseModel):
    """Key performance indicators for device control activity (24h window)."""

    shadow_writes_24h: int
    blocked_writes_24h: int
    approved_writes_24h: int
    safety_violations_24h: int


class CommissioningSnapshot(BaseModel):
    """Summary of commissioning scorecard state."""

    gates_passed: int
    gates_total: int
    all_gates_passed: bool
    consecutive_pass_days: int
    can_promote: bool
    blocking_gates: list[str]


class MonitoringAlert(BaseModel):
    """Alert raised by monitoring rule evaluation."""

    id: str
    rule: str  # "stale_data" | "json_in_live" | "high_error_rate" | "low_coverage" | "truth_check_fail"
    severity: str  # "warning" | "critical"
    message: str
    timestamp: str


class TrendBucket(BaseModel):
    """Hourly trend bucket for 24h history."""

    hour: str  # ISO hour e.g. "2026-02-20T14:00:00"
    freshness_hours: float
    error_rate: float
    shadow_writes: int
    derived: bool  # True when freshness/error_rate are repeated (no per-bucket history yet)


class MonitoringSnapshot(BaseModel):
    """Unified monitoring snapshot returned by /api/system/monitoring."""

    ingestion_mode: str
    is_live: bool
    site_id: str | None
    ingestion: IngestionKPIs
    control: ControlKPIs
    commissioning: CommissioningSnapshot | None  # None in SIMULATION mode
    alerts: list[MonitoringAlert]
    trend_24h: list[TrendBucket]
    checked_at: str
    # Phase 109: Quality gate evaluation result
    quality_gate: dict | None = None  # Overall gate status + per-rule results
