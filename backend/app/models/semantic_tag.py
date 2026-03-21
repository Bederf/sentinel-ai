"""Pydantic models for semantic tags and classification rules.

Phase 162: Semantic Control Foundation — Plan 01.
Provides the controlled vocabulary for deterministic, auditable point classification.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SafetyClass(str, Enum):
    """Safety classification for a semantic tag.

    Determines what autonomous actions are permitted on a classified point.
    """

    LOW = "LOW"  # Monitor/presentation only — read freely, no write restrictions
    MEDIUM = "MEDIUM"  # Supervised control — writes allowed with human-in-loop
    HIGH = "HIGH"  # Critical safety — no autonomous writes; monitor only or explicit approval


class EvidenceSource(str, Enum):
    """Sources of evidence used to classify a point."""

    HAYSTACK_ID = "haystack_id"
    POINT_NAME = "point_name"
    EQUIPMENT_TYPE = "equipment_type"
    METADATA = "metadata"
    VALUE_PATTERN = "value_pattern"


class ValidationBounds(BaseModel):
    """Physical value bounds for a classified point."""

    min: float
    max: float
    unit: str
    rationale: str


class RateLimit(BaseModel):
    """Rate-of-change limit for a classified point."""

    max_per_minute: Optional[float] = None
    max_per_second: Optional[float] = None
    alarm_if_exceeded: bool = False


class ControlEnvelope(BaseModel):
    """Safety envelope governing writes to a classified control point."""

    min_cooldown_seconds: Optional[int] = None
    max_daily_writes: Optional[int] = None
    requires_approval_above: Optional[int] = None
    writable: bool = True
    monitor_only: bool = False
    alarm_on_change: bool = False
    requires_immediate_review: bool = False
    ramp_limits: Optional[RateLimit] = None
    bounds: Optional[ValidationBounds] = None


class ClassificationRule(BaseModel):
    """Single rule used to match a point to a semantic tag."""

    source: EvidenceSource
    pattern: Optional[str] = None  # Single glob pattern (haystack_id source)
    patterns: Optional[list[str]] = None  # Multiple exact/glob patterns (point_name source)
    must_be: Optional[list[str]] = None  # Allowed values (equipment_type source)
    weight: float = Field(ge=0.0, le=1.0)
    evidence: str  # Human-readable rationale for this rule
    equipment_context: Optional[dict] = None  # Additional context constraints


class SemanticTag(BaseModel):
    """A single entry in the semantic dictionary."""

    tag: str = ""  # Populated by DictionaryService after load
    description: str
    applies_to: list[str]  # Equipment types (e.g. AHU, FCU)
    expected_units: list[str]
    point_types: list[str]
    classification_rules: list[ClassificationRule]
    required_evidence: int = Field(ge=0)  # Minimum evidence count for acceptance; 0 means no minimum
    minimum_confidence: float = Field(ge=0.0, le=1.0)
    negative_samples: list[str] = Field(default_factory=list)
    safety_class: SafetyClass
    control_envelope: Optional[ControlEnvelope] = None
    validation_rules: Optional[dict] = None


class SemanticDictionary(BaseModel):
    """The complete loaded semantic dictionary."""

    version: str
    generated_at: str
    semantic_tags: dict[str, SemanticTag]
