"""Structured error types for validation failures.

Phase 162: Semantic Control Foundation — Plan 03.
Provides typed error categories and structured reports for the static validation engine.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ValidationErrorCategory(str, Enum):
    BOUNDS_VIOLATION = "bounds_violation"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    MISSING_REQUIRED_POINTS = "missing_required_points"
    TEMPLATE_INCOMPLETE = "template_incomplete"
    CONFLICTING_TAGS = "conflicting_tags"
    INVALID_UNIT = "invalid_unit"
    DATA_QUALITY_TOO_LOW = "data_quality_too_low"
    SAFETY_CLASS_MISMATCH = "safety_class_mismatch"


class ValidationError(BaseModel):
    """A single validation error with context."""

    error_id: str
    category: ValidationErrorCategory
    severity: str  # "error" or "warning"
    message: str
    point_id: Optional[str] = None
    tag: Optional[str] = None
    actual_value: Optional[float] = None
    expected_bounds: Optional[dict] = None
    suggestion: Optional[str] = None


class ValidationReport(BaseModel):
    """Complete validation report for a point or equipment."""

    classification_id: str
    validation_passed: bool
    errors: list[ValidationError]
    warnings: list[ValidationError]
    completeness_score: float  # 0.0 to 1.0
    validation_timestamp: str
