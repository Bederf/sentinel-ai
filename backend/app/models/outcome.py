"""Outcome model for recommendation verification.

Tracks actual vs predicted outcomes after recommendation execution.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict


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
    """

    recommendation_id: str
    predicted: Dict[str, Any]
    actual: Dict[str, Any]
    accuracy: float
    verified_at: datetime
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "recommendation_id": self.recommendation_id,
            "predicted": self.predicted,
            "actual": self.actual,
            "accuracy": self.accuracy,
            "verified_at": self.verified_at.isoformat()
            if isinstance(self.verified_at, datetime)
            else self.verified_at,
            "notes": self.notes,
        }

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

        return cls(
            recommendation_id=data.get("recommendation_id", ""),
            predicted=data.get("predicted", {}),
            actual=data.get("actual", {}),
            accuracy=float(data.get("accuracy", 0.0)),
            verified_at=verified_at,
            notes=data.get("notes", ""),
        )
