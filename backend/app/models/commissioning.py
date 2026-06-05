"""Pydantic models for commissioning scorecard and promotion gates."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class CommissioningGateId(StrEnum):
    """Identifiers for the 8 hard commissioning gates."""

    MATCH_COVERAGE = "match_coverage"
    UNMATCHED_POINTS = "unmatched_points"
    DATA_FRESHNESS = "data_freshness"
    ERROR_RATE = "error_rate"
    DUPLICATE_RATE = "duplicate_rate"
    SOURCE_PROVENANCE = "source_provenance"
    VALUE_VALIDITY = "value_validity"
    TIMESTAMP_INTEGRITY = "timestamp_integrity"


class CommissioningGate(BaseModel):
    """A single pass/fail commissioning gate."""

    id: CommissioningGateId
    name: str
    category: str  # "point_mapping" | "data_quality" | "ingestion_mode"
    target: str  # Human-readable: ">= 95%"
    actual: float
    passed: bool
    details: str


class TruthCheckEntry(BaseModel):
    """One point comparison between SENTINEL and native BMS."""

    point_id: str
    point_name: str
    sentinel_value: float
    native_bms_value: float
    tolerance: float
    within_tolerance: bool  # abs(sentinel - native) <= tolerance
    timestamp: datetime


class TruthCheckSubmission(BaseModel):
    """Operator-submitted truth check data (minimum 20 entries)."""

    entries: list[TruthCheckEntry] = Field(..., min_length=20)


class TruthCheckResult(BaseModel):
    """Result of a truth check evaluation."""

    site_id: str
    checked_at: datetime
    total_points: int
    agreeing_points: int
    agreement_pct: float  # 0-100
    passed: bool  # >= 98%
    entries: list[TruthCheckEntry]


class CommissioningScorecard(BaseModel):
    """Full commissioning scorecard for a building."""

    site_id: str
    site_name: str | None = None
    ingestion_mode: str
    checked_at: datetime
    gates: list[CommissioningGate]
    truth_check: TruthCheckResult | None = None
    gates_passed: int = 0
    gates_total: int = 0
    stage_calendar_days: int = 0
    summary: dict[str, int]  # {passed, failed, total}
    all_gates_passed: bool
    consecutive_pass_days: int
    can_promote: bool  # all_gates_passed AND consecutive >= 2 AND truth_check.passed
    blocking_gates: list[str]


class PromotionResult(BaseModel):
    """Result of a promote-to-live attempt."""

    success: bool
    site_id: str
    previous_mode: str
    new_mode: str | None = None
    message: str
    scorecard: CommissioningScorecard | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
