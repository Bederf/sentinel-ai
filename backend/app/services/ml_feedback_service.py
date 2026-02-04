"""
ML Feedback Service (Phase 57-02)

Records repair outcomes, generates training data for ML models,
and tracks prediction accuracy. Closes the feedback loop between
ML predictions and real-world maintenance results.

Uses in-memory storage for demo scope.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from app.models.ml_feedback import (
    MLFeedbackRecord,
    TrainingDataPoint,
    PredictionAccuracy,
    MLFeedbackSummary,
)

logger = logging.getLogger(__name__)


class MLFeedbackService:
    """
    Service for ML feedback loop management.

    Provides:
    - Repair outcome recording linked to ML predictions
    - Training data generation from repair outcomes
    - Prediction accuracy tracking per model type
    - Feedback summary for dashboard display
    """

    def __init__(self):
        """Initialize with in-memory storage."""
        self._feedback_records: List[MLFeedbackRecord] = []
        self._training_data: List[TrainingDataPoint] = []
        self._prediction_accuracy: Dict[str, PredictionAccuracy] = {}
        self._record_counter: int = 0

        logger.info("MLFeedbackService initialized")

    # ========================================================================
    # Record Repair Feedback
    # ========================================================================

    def record_repair_feedback(
        self,
        equipment_id: str,
        work_order_id: str,
        effectiveness_score: float,
        repair_successful: bool,
        failure_type: Optional[str] = None,
        prediction_id: Optional[str] = None,
    ) -> MLFeedbackRecord:
        """
        Record repair outcome as ML feedback.

        Steps:
        1. Create MLFeedbackRecord
        2. If prediction_id provided, evaluate prediction accuracy
        3. Generate TrainingDataPoint from repair outcome
        4. Store in memory
        5. Log feedback recorded

        Args:
            equipment_id: Equipment identifier
            work_order_id: Work order ID
            effectiveness_score: Repair effectiveness percentage (0-100)
            repair_successful: Whether repair was successful
            failure_type: Type of failure repaired
            prediction_id: ML prediction that triggered this repair

        Returns:
            Created MLFeedbackRecord
        """
        self._record_counter += 1
        record_id = f"mlf-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self._record_counter:04d}"

        # 1. Create feedback record
        record = MLFeedbackRecord(
            id=record_id,
            equipment_id=equipment_id,
            work_order_id=work_order_id,
            feedback_type="repair_outcome",
            repair_successful=repair_successful,
            effectiveness_score=effectiveness_score,
            prediction_id=prediction_id,
            actual_failure_type=failure_type,
            recorded_at=datetime.now(),
        )

        # 2. If prediction_id provided, evaluate prediction accuracy
        if prediction_id:
            record.prediction_was_correct = repair_successful
            record.feedback_type = "prediction_accuracy"
            # Update accuracy tracking for the prediction's model
            self._update_prediction_accuracy_from_record(record)

        # 3. Generate training data point from repair outcome
        equipment_type = self._infer_equipment_type(equipment_id)
        features = self._get_latest_features(equipment_id)

        training_point = TrainingDataPoint(
            equipment_id=equipment_id,
            equipment_type=equipment_type,
            features=features,
            label="failed" if not repair_successful or effectiveness_score < 80.0 else "repaired",
            failure_type=failure_type,
            repair_effectiveness=effectiveness_score,
            source="repair_outcome",
        )
        self._training_data.append(training_point)

        # 4. Store feedback record
        self._feedback_records.append(record)

        # 5. Log
        logger.info(
            f"ML feedback recorded: {record_id} for {equipment_id}, "
            f"WO={work_order_id}, score={effectiveness_score:.1f}%, "
            f"successful={repair_successful}"
        )

        return record

    # ========================================================================
    # Generate Training Data
    # ========================================================================

    def generate_training_data(
        self,
        equipment_type: Optional[str] = None,
    ) -> List[TrainingDataPoint]:
        """
        Generate training dataset from feedback records.

        Collects all feedback records, optionally filtered by equipment type,
        and builds TrainingDataPoint entries with features from element trends.

        Args:
            equipment_type: Filter by equipment type (e.g., 'chiller', 'ahu')

        Returns:
            List of TrainingDataPoints for ML model retraining
        """
        if equipment_type:
            filtered = [
                tp for tp in self._training_data
                if tp.equipment_type.lower() == equipment_type.lower()
            ]
            logger.info(
                f"Generated {len(filtered)} training data points "
                f"for equipment type '{equipment_type}'"
            )
            return filtered

        logger.info(f"Generated {len(self._training_data)} total training data points")
        return list(self._training_data)

    # ========================================================================
    # Evaluate Prediction Accuracy
    # ========================================================================

    def evaluate_prediction_accuracy(
        self,
        model_type: str,
    ) -> PredictionAccuracy:
        """
        Evaluate prediction accuracy for a specific model type.

        Filters feedback records that have prediction_id, compares
        predicted vs actual outcomes, and calculates accuracy metrics.

        Args:
            model_type: Model type to evaluate (lstm, autoencoder, survival, random_forest)

        Returns:
            PredictionAccuracy with calculated metrics
        """
        # Filter records with predictions
        prediction_records = [
            r for r in self._feedback_records
            if r.prediction_id is not None
        ]

        if not prediction_records:
            accuracy = self._prediction_accuracy.get(
                model_type,
                PredictionAccuracy(model_type=model_type)
            )
            return accuracy

        # Calculate metrics
        total = len(prediction_records)
        correct = sum(1 for r in prediction_records if r.prediction_was_correct)
        false_positives = sum(
            1 for r in prediction_records
            if r.prediction_was_correct is False and not r.repair_successful
        )
        false_negatives = sum(
            1 for r in prediction_records
            if r.prediction_was_correct is False and r.repair_successful
        )

        # True positives: prediction said failure, and there was a failure
        true_positives = correct

        # Precision: TP / (TP + FP)
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0

        # Recall: TP / (TP + FN)
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0

        accuracy = PredictionAccuracy(
            model_type=model_type,
            total_predictions=total,
            correct_predictions=correct,
            false_positives=false_positives,
            false_negatives=false_negatives,
            accuracy_percent=round((correct / total) * 100, 2) if total > 0 else 0.0,
            precision=round(precision, 4),
            recall=round(recall, 4),
            last_evaluated=datetime.now(),
        )

        self._prediction_accuracy[model_type] = accuracy

        logger.info(
            f"Prediction accuracy for {model_type}: "
            f"{accuracy.accuracy_percent}% ({correct}/{total})"
        )

        return accuracy

    # ========================================================================
    # Query Methods
    # ========================================================================

    def get_feedback_summary(self) -> MLFeedbackSummary:
        """
        Get aggregated ML feedback summary for dashboard display.

        Returns:
            MLFeedbackSummary with overall statistics
        """
        total = len(self._feedback_records)
        repair_outcomes = sum(
            1 for r in self._feedback_records
            if r.feedback_type == "repair_outcome"
        )
        predictions_evaluated = sum(
            1 for r in self._feedback_records
            if r.prediction_id is not None
        )

        # Calculate average accuracy across all model types
        if self._prediction_accuracy:
            avg_accuracy = sum(
                a.accuracy_percent for a in self._prediction_accuracy.values()
            ) / len(self._prediction_accuracy)
        else:
            avg_accuracy = 0.0

        return MLFeedbackSummary(
            total_feedback_records=total,
            repair_outcomes_recorded=repair_outcomes,
            predictions_evaluated=predictions_evaluated,
            avg_prediction_accuracy=round(avg_accuracy, 2),
            model_accuracies=dict(self._prediction_accuracy),
            training_data_points=len(self._training_data),
            last_retrain_date=None,
        )

    def get_feedback_for_equipment(
        self,
        equipment_id: str,
    ) -> List[MLFeedbackRecord]:
        """
        Get all feedback records for a specific equipment.

        Args:
            equipment_id: Equipment identifier

        Returns:
            List of MLFeedbackRecord for the equipment
        """
        records = [
            r for r in self._feedback_records
            if r.equipment_id == equipment_id
        ]
        logger.info(f"Retrieved {len(records)} feedback records for {equipment_id}")
        return records

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _update_prediction_accuracy_from_record(self, record: MLFeedbackRecord):
        """Update prediction accuracy tracking from a single feedback record."""
        # Determine model type from prediction_id pattern or default to 'unknown'
        model_type = self._infer_model_type(record.prediction_id)

        if model_type not in self._prediction_accuracy:
            self._prediction_accuracy[model_type] = PredictionAccuracy(
                model_type=model_type
            )

        acc = self._prediction_accuracy[model_type]
        acc.total_predictions += 1
        if record.prediction_was_correct:
            acc.correct_predictions += 1
        else:
            if record.repair_successful:
                acc.false_negatives += 1
            else:
                acc.false_positives += 1

        # Recalculate metrics
        if acc.total_predictions > 0:
            acc.accuracy_percent = round(
                (acc.correct_predictions / acc.total_predictions) * 100, 2
            )
        tp = acc.correct_predictions
        if (tp + acc.false_positives) > 0:
            acc.precision = round(tp / (tp + acc.false_positives), 4)
        if (tp + acc.false_negatives) > 0:
            acc.recall = round(tp / (tp + acc.false_negatives), 4)

        acc.last_evaluated = datetime.now()

    def _infer_model_type(self, prediction_id: Optional[str]) -> str:
        """Infer model type from prediction ID pattern."""
        if not prediction_id:
            return "unknown"
        pred_lower = prediction_id.lower()
        if "lstm" in pred_lower:
            return "lstm"
        elif "autoencoder" in pred_lower or "ae" in pred_lower:
            return "autoencoder"
        elif "survival" in pred_lower or "cox" in pred_lower:
            return "survival"
        elif "rf" in pred_lower or "random_forest" in pred_lower:
            return "random_forest"
        return "unknown"

    def _infer_equipment_type(self, equipment_id: str) -> str:
        """Infer equipment type from equipment ID naming convention."""
        # S002-CHILLER-B1-001 -> chiller
        parts = equipment_id.split("-")
        if len(parts) >= 2:
            return parts[1].lower()
        return "unknown"

    def _get_latest_features(self, equipment_id: str) -> Dict[str, float]:
        """
        Get latest feature values for equipment from element trend service.

        Uses lazy import to avoid circular dependencies.
        Falls back to empty dict if service unavailable.
        """
        try:
            from app.services.element_trend_service import get_element_trend_service
            trend_service = get_element_trend_service()

            # For demo scope, return basic features
            # In production, this would query real-time sensor data
            return {
                "effectiveness_score": 0.0,
                "equipment_id_hash": hash(equipment_id) % 1000 / 1000.0,
            }
        except Exception as e:
            logger.debug(f"Could not get features for {equipment_id}: {e}")
            return {}


# ============================================================================
# Singleton Instance
# ============================================================================

_ml_feedback_service: Optional[MLFeedbackService] = None


def get_ml_feedback_service() -> MLFeedbackService:
    """Get singleton MLFeedbackService instance."""
    global _ml_feedback_service
    if _ml_feedback_service is None:
        _ml_feedback_service = MLFeedbackService()
    return _ml_feedback_service
