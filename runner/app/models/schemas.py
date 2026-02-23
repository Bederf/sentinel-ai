"""Pydantic models matching the RLM Runner API contract (spec Section 5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


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
