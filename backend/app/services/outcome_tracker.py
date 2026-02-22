"""Outcome tracking service for recommendation verification and learning feedback.

Tracks actual vs predicted outcomes after recommendation execution.
Measures accuracy and feeds results back to improve future recommendations.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.outcome import Outcome
from app.services.device_abstraction import device_manager
from app.services.recommendation_service import get_recommendation_service
from app.database.repositories.outcome_repository import OutcomeRepository

logger = logging.getLogger(__name__)


class OutcomeTracker:
    """Tracks recommendation outcomes and provides learning feedback.

    Verifies actual impact of recommendations after execution.
    Calculates accuracy and feeds back to improve confidence scores.
    """

    def __init__(self):
        """Initialize OutcomeTracker."""
        self.device_manager = device_manager
        self.recommendation_service = get_recommendation_service()
        self.repo = OutcomeRepository()

    async def verify_outcome(self, rec_id: str, verify_delay_minutes: int = 30) -> Optional[Outcome]:
        """Verify actual outcome 30 minutes after recommendation execution.

        Compares predicted vs actual impact:
        - Temperature changes (±0.5°C tolerance)
        - Energy cost (±15% tolerance)
        - Equipment status

        Args:
            rec_id: Recommendation ID to verify
            verify_delay_minutes: Delay before verification (default 30 min)

        Returns:
            Outcome object with accuracy score, or None if not executable
        """
        try:
            # Note: Full implementation would fetch from repository
            # For now, this is a placeholder that demonstrates the logic
            logger.info(f"Verifying outcome for recommendation {rec_id} with {verify_delay_minutes}min delay")

            # In production, would query repository here
            rec = None

            if not rec:
                logger.warning(f"Recommendation {rec_id} not found")
                return None

            if rec.status != RecommendationStatus.EXECUTED:
                logger.info(f"Skipping outcome verification - recommendation not in EXECUTED status: {rec.status}")
                return None

            # Wait for system to stabilize after execution
            if verify_delay_minutes > 0:
                await asyncio.sleep(verify_delay_minutes * 60)

            # Read actual state from device manager
            actual_state = await self._read_actual_state(rec.target_equipment)

            # Estimate energy cost
            energy_cost = await self._estimate_cost(actual_state, rec.executed_at)

            # Build actual impact dict
            actual = {
                "temperature_c": actual_state.get("zone_temp"),
                "energy_cost_zar": energy_cost,
                "equipment_runtime_hours": actual_state.get("runtime_hours"),
            }

            # Get predicted impact
            predicted = rec.expected_impact

            # Calculate accuracy
            accuracy = self._calculate_accuracy(predicted, actual)

            # Create outcome record
            outcome = Outcome(
                recommendation_id=rec_id,
                predicted=predicted,
                actual=actual,
                accuracy=accuracy,
                verified_at=datetime.utcnow(),
                notes="",
            )

            # Store in repository
            await self.repo.create(outcome)

            # Update recommendation with outcome
            # Note: This would normally update the recommendation in the service/repo
            logger.info(f"Verified outcome for {rec_id}: accuracy={accuracy:.1%}")

            # Feed back to learning system
            await self._process_outcome_learning(rec, accuracy)

            return outcome

        except Exception as e:
            logger.error(f"Error verifying outcome for {rec_id}: {e}")
            return None

    def _calculate_accuracy(self, predicted: Dict, actual: Dict) -> float:
        """Calculate accuracy as percentage match (0.0 to 1.0).

        Temperature: ±0.5°C = good
        Cost: ±100% error = 0 match (linear penalty)

        Weighted: 60% temperature, 40% cost

        Args:
            predicted: Predicted impact dict
            actual: Actual measured impact dict

        Returns:
            Accuracy score 0.0-1.0 (1.0 = perfect match)
        """
        # Temperature accuracy
        temp_pred = predicted.get("temperature_c", 0)
        temp_actual = actual.get("temperature_c", 0)
        temp_error = abs(temp_actual - temp_pred)

        # Temperature within ±0.5°C = good
        # Error > 0.5°C reduces accuracy linearly
        temp_match = max(0.0, 1.0 - (temp_error / 0.5))

        # Cost accuracy
        cost_pred = predicted.get("cost_zar", 0)
        cost_actual = actual.get("energy_cost_zar", 0)

        if cost_pred > 0:
            cost_error_pct = abs(cost_actual - cost_pred) / cost_pred
            # ±100% error = 0 match (linear penalty)
            cost_match = max(0.0, 1.0 - cost_error_pct)
        else:
            # Can't evaluate cost if no predicted cost
            cost_match = 1.0

        # Weighted average: 60% temperature, 40% cost
        accuracy = (temp_match * 0.6) + (cost_match * 0.4)

        return accuracy

    async def _read_actual_state(self, equipment_id: str) -> Dict[str, Any]:
        """Read current state from device manager.

        Args:
            equipment_id: Equipment to read

        Returns:
            State dict with temperature, runtime, power draw, etc.
        """
        try:
            device = await self.device_manager.read_device(equipment_id)
            return device.state if hasattr(device, "state") else {}
        except Exception as e:
            logger.warning(f"Failed to read actual state for {equipment_id}: {e}")
            return {}

    async def _estimate_cost(self, state: Dict[str, Any], since: datetime) -> float:
        """Estimate energy cost since recommendation execution.

        Args:
            state: Device state dict
            since: Start time for cost calculation

        Returns:
            Estimated cost in ZAR
        """
        try:
            elapsed_minutes = (datetime.utcnow() - since).total_seconds() / 60
            power_kw = state.get("power_draw", 5.0)
            cost_per_kwh = 2.50  # ZAR

            estimated_kwh = (power_kw * elapsed_minutes) / 60
            estimated_cost = estimated_kwh * cost_per_kwh

            return estimated_cost
        except Exception as e:
            logger.warning(f"Failed to estimate cost: {e}")
            return 0.0

    async def _process_outcome_learning(self, rec: Recommendation, accuracy: float) -> None:
        """Update confidence scores based on outcome accuracy.

        High accuracy (> 0.8): increase confidence for similar actions
        Low accuracy (< 0.4): decrease confidence, flag for review

        Args:
            rec: Executed recommendation
            accuracy: Accuracy score from verification
        """
        try:
            if accuracy > 0.8:
                # Successful prediction - increase confidence
                await self._increase_confidence(rec.action_type, rec.site_id, amount=0.05)
                logger.info(f"High accuracy outcome ({accuracy:.1%}) for {rec.action_type} - increasing confidence")
            elif accuracy < 0.4:
                # Poor prediction - decrease confidence
                await self._decrease_confidence(rec.action_type, rec.site_id, amount=0.1)
                logger.warning(f"Low accuracy outcome ({accuracy:.1%}) for {rec.action_type} - decreasing confidence")
        except Exception as e:
            logger.error(f"Error processing outcome learning: {e}")

    async def _increase_confidence(self, action_type: str, site_id: str, amount: float = 0.05) -> None:
        """Increase confidence score for action type.

        Args:
            action_type: Type of action (e.g., hvac_setpoint_change)
            site_id: Site ID
            amount: Amount to increase by (0.0-1.0)
        """
        # Note: Placeholder - full implementation would update confidence tracking
        logger.debug(f"Increasing confidence for {action_type} on {site_id} by {amount}")

    async def _decrease_confidence(self, action_type: str, site_id: str, amount: float = 0.1) -> None:
        """Decrease confidence score for action type.

        Args:
            action_type: Type of action (e.g., hvac_setpoint_change)
            site_id: Site ID
            amount: Amount to decrease by (0.0-1.0)
        """
        # Note: Placeholder - full implementation would update confidence tracking
        logger.debug(f"Decreasing confidence for {action_type} on {site_id} by {amount}")


# Singleton instance
_outcome_tracker: Optional[OutcomeTracker] = None


def get_outcome_tracker() -> OutcomeTracker:
    """Get or create OutcomeTracker singleton.

    Returns:
        OutcomeTracker instance
    """
    global _outcome_tracker
    if _outcome_tracker is None:
        _outcome_tracker = OutcomeTracker()
    return _outcome_tracker
