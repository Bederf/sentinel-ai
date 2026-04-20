"""Decision Memory models — storing diagnostic and control outcomes.

Records every diagnosis-action-outcome triple and extracts patterns
when enough evidence accumulates.

Phase 145: Decision Memory Layer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class DecisionOutcome(str, Enum):
    """Outcome of a decision/action."""

    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    INEFFECTIVE = "ineffective"
    WORSENED = "worsened"
    PENDING = "pending"
    UNKNOWN = "unknown"


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _generate_record_id() -> str:
    ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"DM-{ts}-{uuid.uuid4().hex[:8]}"


def _detect_season() -> str:
    month = datetime.now(UTC).month
    if month in (12, 1, 2):
        return "summer"  # Southern hemisphere
    elif month in (3, 4, 5):
        return "autumn"
    elif month in (6, 7, 8):
        return "winter"
    return "spring"


def _detect_time_of_day() -> str:
    hour = datetime.now(UTC).hour
    if 6 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    return "night"


@dataclass
class DecisionRecord:
    """A single decision/action and its outcome."""

    record_id: str = field(default_factory=_generate_record_id)

    # Trigger
    event_type: str = ""
    event_description: str = ""
    equipment_id: str = ""
    equipment_type: str = ""
    site_id: str = ""

    # Diagnosis
    diagnosis: str = ""
    diagnosis_confidence: float = 0.0
    diagnosis_source: str = "ai_reasoning"

    # Action
    action_type: str = ""
    action_details: dict[str, Any] = field(default_factory=dict)
    action_executed_at: datetime | None = None
    action_executed_by: str | None = None

    # Outcome
    outcome: DecisionOutcome = DecisionOutcome.PENDING
    outcome_details: str | None = None
    outcome_evaluated_at: datetime | None = None
    resolution_time_minutes: float | None = None

    # Context
    signals_snapshot: list[dict[str, Any]] = field(default_factory=list)
    season: str = field(default_factory=_detect_season)
    time_of_day: str = field(default_factory=_detect_time_of_day)

    # Timestamps
    created_at: datetime = field(default_factory=_now_utc)
    updated_at: datetime = field(default_factory=_now_utc)

    # Correlation
    correlation_id: str | None = None
    recommendation_id: str | None = None
    work_order_id: str | None = None
    event_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        def _dt(v: datetime | None) -> str | None:
            return v.isoformat() if isinstance(v, datetime) else v

        return {
            "record_id": self.record_id,
            "event_type": self.event_type,
            "event_description": self.event_description,
            "equipment_id": self.equipment_id,
            "equipment_type": self.equipment_type,
            "site_id": self.site_id,
            "diagnosis": self.diagnosis,
            "diagnosis_confidence": self.diagnosis_confidence,
            "diagnosis_source": self.diagnosis_source,
            "action_type": self.action_type,
            "action_details": self.action_details,
            "action_executed_at": _dt(self.action_executed_at),
            "action_executed_by": self.action_executed_by,
            "outcome": self.outcome.value,
            "outcome_details": self.outcome_details,
            "outcome_evaluated_at": _dt(self.outcome_evaluated_at),
            "resolution_time_minutes": self.resolution_time_minutes,
            "signals_snapshot": self.signals_snapshot,
            "season": self.season,
            "time_of_day": self.time_of_day,
            "created_at": _dt(self.created_at),
            "updated_at": _dt(self.updated_at),
            "correlation_id": self.correlation_id,
            "recommendation_id": self.recommendation_id,
            "work_order_id": self.work_order_id,
            "event_id": self.event_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionRecord:
        def _parse_dt(val: Any) -> datetime | None:
            if isinstance(val, datetime):
                return val
            if isinstance(val, str) and val:
                try:
                    return datetime.fromisoformat(val)
                except (ValueError, TypeError):
                    return None
            return None

        outcome_str = data.get("outcome", "pending")
        try:
            outcome = DecisionOutcome(outcome_str)
        except ValueError:
            outcome = DecisionOutcome.UNKNOWN

        return cls(
            record_id=data.get("record_id", _generate_record_id()),
            event_type=data.get("event_type", ""),
            event_description=data.get("event_description", ""),
            equipment_id=data.get("equipment_id", ""),
            equipment_type=data.get("equipment_type", ""),
            site_id=data.get("site_id", ""),
            diagnosis=data.get("diagnosis", ""),
            diagnosis_confidence=float(data.get("diagnosis_confidence", 0.0)),
            diagnosis_source=data.get("diagnosis_source", "ai_reasoning"),
            action_type=data.get("action_type", ""),
            action_details=data.get("action_details", {}),
            action_executed_at=_parse_dt(data.get("action_executed_at")),
            action_executed_by=data.get("action_executed_by"),
            outcome=outcome,
            outcome_details=data.get("outcome_details"),
            outcome_evaluated_at=_parse_dt(data.get("outcome_evaluated_at")),
            resolution_time_minutes=data.get("resolution_time_minutes"),
            signals_snapshot=data.get("signals_snapshot", []),
            season=data.get("season", ""),
            time_of_day=data.get("time_of_day", ""),
            created_at=_parse_dt(data.get("created_at")) or _now_utc(),
            updated_at=_parse_dt(data.get("updated_at")) or _now_utc(),
            correlation_id=data.get("correlation_id"),
            recommendation_id=data.get("recommendation_id"),
            work_order_id=data.get("work_order_id"),
            event_id=data.get("event_id"),
        )


@dataclass
class DecisionPattern:
    """A learned pattern from multiple decision records.

    Created when the same event_type + equipment_type has 3+ records
    with the same diagnosis and RESOLVED outcome.
    """

    pattern_id: str = field(default_factory=lambda: f"PAT-{uuid.uuid4().hex[:8]}")

    # Pattern key
    event_type: str = ""
    equipment_type: str = ""

    # Learned knowledge
    likely_diagnosis: str = ""
    diagnosis_confidence: float = 0.0
    recommended_action: str = ""
    action_details: dict[str, Any] = field(default_factory=dict)

    # Statistics
    total_occurrences: int = 0
    resolved_count: int = 0
    success_rate: float = 0.0
    avg_resolution_time_minutes: float = 0.0

    # Applicability
    applicable_sites: list[str] = field(default_factory=list)
    seasonal_pattern: str | None = None

    # Timestamps
    created_at: datetime = field(default_factory=_now_utc)
    updated_at: datetime = field(default_factory=_now_utc)
    last_matched_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        def _dt(v: datetime | None) -> str | None:
            return v.isoformat() if isinstance(v, datetime) else v

        return {
            "pattern_id": self.pattern_id,
            "event_type": self.event_type,
            "equipment_type": self.equipment_type,
            "likely_diagnosis": self.likely_diagnosis,
            "diagnosis_confidence": self.diagnosis_confidence,
            "recommended_action": self.recommended_action,
            "action_details": self.action_details,
            "total_occurrences": self.total_occurrences,
            "resolved_count": self.resolved_count,
            "success_rate": self.success_rate,
            "avg_resolution_time_minutes": self.avg_resolution_time_minutes,
            "applicable_sites": self.applicable_sites,
            "seasonal_pattern": self.seasonal_pattern,
            "created_at": _dt(self.created_at),
            "updated_at": _dt(self.updated_at),
            "last_matched_at": _dt(self.last_matched_at),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionPattern:
        def _parse_dt(val: Any) -> datetime | None:
            if isinstance(val, datetime):
                return val
            if isinstance(val, str) and val:
                try:
                    return datetime.fromisoformat(val)
                except (ValueError, TypeError):
                    return None
            return None

        return cls(
            pattern_id=data.get("pattern_id", f"PAT-{uuid.uuid4().hex[:8]}"),
            event_type=data.get("event_type", ""),
            equipment_type=data.get("equipment_type", ""),
            likely_diagnosis=data.get("likely_diagnosis", ""),
            diagnosis_confidence=float(data.get("diagnosis_confidence", 0.0)),
            recommended_action=data.get("recommended_action", ""),
            action_details=data.get("action_details", {}),
            total_occurrences=int(data.get("total_occurrences", 0)),
            resolved_count=int(data.get("resolved_count", 0)),
            success_rate=float(data.get("success_rate", 0.0)),
            avg_resolution_time_minutes=float(data.get("avg_resolution_time_minutes", 0.0)),
            applicable_sites=data.get("applicable_sites", []),
            seasonal_pattern=data.get("seasonal_pattern"),
            created_at=_parse_dt(data.get("created_at")) or _now_utc(),
            updated_at=_parse_dt(data.get("updated_at")) or _now_utc(),
            last_matched_at=_parse_dt(data.get("last_matched_at")),
        )
