"""Abstract base interface for all point classifiers.

Phase 162: Semantic Control Foundation — Plan 02.
All classifiers must implement this interface to ensure consistent
evidence-trail output and batch processing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models.point_classification import BatchClassificationResult, PointClassification


class BasePointClassifier(ABC):
    """Abstract base for all point classifiers.

    Concrete implementations must produce PointClassification records with
    complete evidence trails so every decision is auditable.
    """

    @property
    @abstractmethod
    def classifier_id(self) -> str:
        """Unique identifier for this classifier implementation."""

    @abstractmethod
    async def classify_point(self, point_data: dict[str, Any]) -> PointClassification:
        """Classify a single point against the semantic dictionary.

        Args:
            point_data: Dictionary with point metadata including:
                - point_id: str — unique point identifier
                - device_id: Optional[str] — parent device identifier
                - site_id: str — site this point belongs to
                - equipment_type: str — e.g. "AHU", "FCU", "VAV"
                - point_name: str — raw BACnet/DALI point name
                - haystack_id: Optional[str] — Haystack semantic ID if available
                - metadata: dict — additional point properties
                - current_value: Any — last read value
                - data_quality_score: float -- 0-1 quality score from upstream

        Returns:
            PointClassification with complete evidence trail.
        """

    @abstractmethod
    async def classify_equipment_batch(
        self,
        equipment_id: str,
        points: list[dict[str, Any]],
    ) -> BatchClassificationResult:
        """Classify all points for a single equipment/device.

        Args:
            equipment_id: Device/equipment identifier.
            points: List of point_data dictionaries (same schema as classify_point).

        Returns:
            BatchClassificationResult with aggregate statistics.
        """

    def get_supported_point_types(self) -> list[str]:
        """List of BACnet/DALI point types this classifier handles.

        Subclasses may override to restrict the set of types.
        """
        return [
            "analog_input",
            "analog_output",
            "analog_value",
            "binary_input",
            "binary_output",
            "binary_value",
            "multistate",
        ]
