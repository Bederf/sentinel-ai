"""Pydantic models for point classification results with full evidence trail.

Phase 162: Semantic Control Foundation — Plan 02.
Every classification decision is traceable to specific evidence records.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.semantic_tag import EvidenceSource, SafetyClass


class EvidenceRecord(BaseModel):
    """Single piece of evidence supporting a classification decision."""

    source: EvidenceSource
    value_found: str  # The actual value extracted from the point (e.g. "SAT")
    rule_matched: str  # The rule/pattern that matched (e.g. "SAT" in patterns list)
    weight: float  # Evidence weight from the classification rule (0.0-1.0)
    contributed_confidence: float  # weight x normalisation factor
    evidence_description: str  # Human-readable rationale string from the rule


class PointClassification(BaseModel):
    """Complete classification result for one BACnet/DALI point."""

    point_id: str
    device_id: str | None = None
    site_id: str
    equipment_type: str
    semantic_tags: list[str] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0)
    data_quality_score: float = Field(ge=0.0, le=1.0)
    classification_date: datetime
    status: str = "pending_review"  # pending_review | approved | rejected
    reviewed_by: str | None = None
    review_date: datetime | None = None
    review_notes: str | None = None

    # Evidence trail — every match is recorded
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)

    # Risk assessment from best-matching tag
    highest_safety_class: SafetyClass | None = None

    # Control envelope extracted from highest-confidence tag (if writable)
    control_envelope: dict | None = None

    # Validation outcome
    validation_passed: bool = False
    validation_errors: list[str] = Field(default_factory=list)

    # Current and historical values (populated from BMS adapter when available)
    current_value: float | None = None
    historic_values: dict | None = None  # {"values": [...], "timestamps": [...]}

    # Trust accumulation — updated by later stability tracking plans
    stability_days: int = 0
    validation_runs: int = 0
    successful_actions: int = 0


class BatchClassificationResult(BaseModel):
    """Aggregate result from classifying all points for a single equipment."""

    equipment_id: str
    site_id: str
    classified_points: list[PointClassification]
    total_points: int
    high_confidence_count: int  # confidence >= 0.7
    medium_confidence_count: int  # 0.4 <= confidence < 0.7
    low_confidence_count: int  # confidence < 0.4
    requires_review_count: int  # status == "pending_review"
    processing_time_ms: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
