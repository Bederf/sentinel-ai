"""Pydantic models matching the RLM Runner API contract (spec Section 5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, computed_field


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    """POST /run request body."""

    case_id: str
    question: str
    model: Optional[str] = None


# ---------------------------------------------------------------------------
# Response (immediate)
# ---------------------------------------------------------------------------

class RunResponse(BaseModel):
    """POST /run response — returned immediately after queuing."""

    run_id: str
    status: Literal["queued"] = "queued"


# ---------------------------------------------------------------------------
# Trajectory / result
# ---------------------------------------------------------------------------

class TrajectoryData(BaseModel):
    """Runner execution trajectory metrics."""

    steps: int = 0
    files_read: int = 0
    bytes_read: int = 0
    elapsed_s: float = 0.0


class ScoringMetadata(BaseModel):
    """Snapshot of scoring config used for this result — enables audit of old runs."""

    version: int = 1
    threshold_medium: float = 0.4
    threshold_high: float = 0.7


class ResultSchema(BaseModel):
    """Full result schema matching spec Section 5.4."""

    status: Literal["queued", "running", "complete", "error", "timeout"] = "queued"
    summary: str = ""
    findings: list[str] = Field(default_factory=list)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    needs_deeper_run: bool = False
    trajectory: TrajectoryData = Field(default_factory=TrajectoryData)
    scoring: ScoringMetadata = Field(default_factory=lambda: _build_scoring_metadata())
    model_name: str = ""
    model_provider: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def confidence_label(self) -> Literal["low", "medium", "high"]:
        """Human-readable confidence label derived from the float score.

        Thresholds come from the scoring metadata snapshot (which mirrors
        config at result-creation time). Use for UI display and policy rules.
        The float stays stable for ML.
        """
        if self.confidence >= self.scoring.threshold_high:
            return "high"
        if self.confidence >= self.scoring.threshold_medium:
            return "medium"
        return "low"


def _build_scoring_metadata() -> ScoringMetadata:
    """Snapshot scoring config at result-creation time."""
    from app.config import settings

    return ScoringMetadata(
        version=settings.scoring_version,
        threshold_medium=settings.confidence_threshold_medium,
        threshold_high=settings.confidence_threshold_high,
    )


# ---------------------------------------------------------------------------
# Trace
# ---------------------------------------------------------------------------

class TraceEntry(BaseModel):
    """Single entry in trace.jsonl."""

    timestamp: datetime
    event_type: str
    details: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

class ManifestSchema(BaseModel):
    """Case manifest.json schema."""

    case_id: str
    created_at: str
    description: Optional[str] = None
    evidence_files: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """GET /health response."""

    status: str = "ok"
    version: str = "1.0.0"
    ollama_available: bool = False
