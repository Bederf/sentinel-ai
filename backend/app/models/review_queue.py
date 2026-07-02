"""Pydantic models for review queue entries and decisions.

Phase 162: Semantic Control Foundation — Plan 05.
Human-in-the-loop review interface for semantic classification decisions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReviewQueueEntry(BaseModel):
    """A classification queued for human review."""

    id: str | None = None
    site_id: str
    equipment_id: str
    point_id: str
    classification_id: str

    # Classification details
    semantic_tags: list[str] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0)
    confidence_level: str  # HIGH, MEDIUM, LOW
    safety_class: str  # LOW, MEDIUM, HIGH
    automation_tier: str  # observe_only, supervised, automatic

    # Validation results
    validation_passed: bool = False
    validation_errors: list[Any] = Field(default_factory=list)
    completeness_score: float | None = None

    # Review metadata
    status: str = "pending"  # pending, approved, rejected, overridden
    priority: int = 100  # Lower = higher priority

    # Audit trail
    classified_by: str
    classified_at: datetime = Field(default_factory=datetime.utcnow)

    # Review decision
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    decision_reason: str | None = None

    # Override data
    override_tags: list[str] | None = None
    override_confidence: float | None = None
    override_justification: str | None = None

    # Trust reset metadata (PLAN-162B)
    reset_reason: str | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ReviewDecision(BaseModel):
    """A decision made on a review queue entry."""

    id: str | None = None
    review_queue_id: str
    decision_type: str  # approve, reject, override
    decision_reason: str | None = None
    reviewed_by: str
    reviewed_at: datetime = Field(default_factory=datetime.utcnow)
    review_notes: str | None = None
    metadata: dict | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ReviewQueueStats(BaseModel):
    """Statistics about the review queue."""

    total_pending: int = 0
    by_safety_class: dict[str, int] = Field(default_factory=dict)
    by_confidence_level: dict[str, int] = Field(default_factory=dict)
    avg_age_hours: float = 0.0
    high_priority_count: int = 0  # priority <= 50
