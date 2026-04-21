"""Prediction Overlay Service for Digital Twin visualization.

Aggregates ML predictions into a visualization-ready format for the
Digital Twin 3D view. Maps raw prediction data to PredictiveFault models
with severity classification based on timeframe.
"""

import logging
from typing import Optional

from app.models.equipment_status import PredictiveFault

logger = logging.getLogger(__name__)

# Singleton instance
_prediction_overlay_service: Optional["PredictionOverlayService"] = None


class PredictionOverlayService:
    """Aggregates ML predictions for Digital Twin visualization overlay."""

    # Severity thresholds (days until predicted failure)
    CRITICAL_THRESHOLD_DAYS = 7
    WARNING_THRESHOLD_DAYS = 30

    def __init__(self):
        """Initialize the prediction overlay service."""
        self._repo = None

    def _get_repo(self):
        """Lazy-load prediction repository to avoid circular imports."""
        if self._repo is None:
            from app.database.repositories.prediction_repository import PredictionRepository

            self._repo = PredictionRepository()
        return self._repo

    async def get_predictions_for_site(self, site_id: str) -> list[PredictiveFault]:
        """Get active predictions for a site, mapped for visualization.

        Queries the prediction repository for active predictions,
        filters to equipment with predictions in the next 30 days,
        and maps to PredictiveFault models with severity classification.

        Args:
            site_id: Site UUID to fetch predictions for

        Returns:
            List of PredictiveFault sorted by severity then confidence
        """
        try:
            repo = self._get_repo()
            raw_predictions = repo.get_active_by_site(site_id)

            faults: list[PredictiveFault] = []
            for pred in raw_predictions:
                timeframe_days = pred.get("timeframe_days") or 0
                confidence = pred.get("confidence") or pred.get("probability_percent", 0)

                # Normalize confidence to 0-1 range
                if confidence > 1:
                    confidence = confidence / 100.0

                # Filter to predictions within 30 days
                if timeframe_days > self.WARNING_THRESHOLD_DAYS:
                    continue

                # Classify severity based on timeframe
                severity = "critical" if timeframe_days <= self.CRITICAL_THRESHOLD_DAYS else "warning"

                fault = PredictiveFault(
                    equipment_id=pred.get("equipment_id", ""),
                    prediction_type=pred.get("prediction_type", "unknown"),
                    severity=severity,
                    timeframe_days=timeframe_days,
                    confidence=round(confidence, 3),
                    model_name=pred.get("model_name"),
                )
                faults.append(fault)

            # Sort by severity (critical first) then confidence (highest first)
            severity_order = {"critical": 0, "warning": 1}
            faults.sort(key=lambda f: (severity_order.get(f.severity, 2), -f.confidence))

            return faults

        except Exception as e:
            logger.error(f"Failed to get predictions for site {site_id}: {e}")
            return []


def get_prediction_overlay_service() -> PredictionOverlayService:
    """Get or create the singleton PredictionOverlayService instance."""
    global _prediction_overlay_service
    if _prediction_overlay_service is None:
        _prediction_overlay_service = PredictionOverlayService()
    return _prediction_overlay_service
