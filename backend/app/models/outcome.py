"""Outcome model for recommendation verification.

Tracks actual vs predicted outcomes after recommendation execution.
Includes quality gate context captured at action time for ML feedback loop closure.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class Outcome:
    """Result of outcome verification for a recommendation.

    Compares predicted impact (from recommendation) with actual measured impact
    after execution. Accuracy score helps improve future recommendations.

    Fields:
        recommendation_id: ID of the verified recommendation
        predicted: Dict with expected impact (temperature_c, cost_zar, etc.)
        actual: Dict with actual measured impact
        accuracy: Accuracy score 0.0-1.0 (1.0 = perfect match)
        verified_at: Timestamp when verification was completed
        notes: Additional notes about the outcome
        quality_gate_status_at_action: Quality gate status (PASS/WARN/FAIL) when action was taken
        quality_snapshot_id: UUID of the quality gate evaluation snapshot
        ingestion_mode_at_action: Ingestion mode (simulation/shadow_live/live_control) at action time
        action_time: When the recommendation action was taken
        outcome_time: When the outcome was measured/verified
    """

    recommendation_id: str
    predicted: Dict[str, Any]
    actual: Dict[str, Any]
    accuracy: float
    verified_at: datetime
    notes: str = ""
    quality_gate_status_at_action: Optional[str] = None
    quality_snapshot_id: Optional[str] = None
    ingestion_mode_at_action: Optional[str] = None
    action_time: Optional[datetime] = None
    outcome_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        result: Dict[str, Any] = {
            "recommendation_id": self.recommendation_id,
            "predicted": self.predicted,
            "actual": self.actual,
            "accuracy": self.accuracy,
            "verified_at": self.verified_at.isoformat() if isinstance(self.verified_at, datetime) else self.verified_at,
            "notes": self.notes,
            "quality_gate_status_at_action": self.quality_gate_status_at_action,
            "quality_snapshot_id": self.quality_snapshot_id,
            "ingestion_mode_at_action": self.ingestion_mode_at_action,
            "action_time": (
                self.action_time.isoformat() if isinstance(self.action_time, datetime) else self.action_time
            ),
            "outcome_time": (
                self.outcome_time.isoformat() if isinstance(self.outcome_time, datetime) else self.outcome_time
            ),
        }
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Outcome":
        """Deserialize from dictionary."""
        verified_at = data.get("verified_at")
        if isinstance(verified_at, str):
            try:
                verified_at = datetime.fromisoformat(verified_at)
            except (ValueError, TypeError):
                verified_at = datetime.utcnow()
        else:
            verified_at = datetime.utcnow()

        def _parse_optional_dt(val: Any) -> Optional[datetime]:
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            if isinstance(val, str):
                try:
                    return datetime.fromisoformat(val)
                except (ValueError, TypeError):
                    return None
            return None

        return cls(
            recommendation_id=data.get("recommendation_id", ""),
            predicted=data.get("predicted", {}),
            actual=data.get("actual", {}),
            accuracy=float(data.get("accuracy", 0.0)),
            verified_at=verified_at,
            notes=data.get("notes", ""),
            quality_gate_status_at_action=data.get("quality_gate_status_at_action"),
            quality_snapshot_id=data.get("quality_snapshot_id"),
            ingestion_mode_at_action=data.get("ingestion_mode_at_action"),
            action_time=_parse_optional_dt(data.get("action_time")),
            outcome_time=_parse_optional_dt(data.get("outcome_time")),
        )
