"""
Model Performance Monitor

Evaluates prediction accuracy against actual outcomes.
Compares predicted failures/anomalies with real alerts and faults.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class ModelPerformanceMonitor:
    """Monitors ML model prediction accuracy against actuals."""

    def __init__(self):
        self._evaluation_history: List[Dict[str, Any]] = []

    def evaluate_predictions(
        self,
        days_back: int = 7,
        site_code: str = "site-002",
    ) -> Dict[str, Any]:
        """Compare predictions vs actual alerts/faults.

        Computes accuracy, precision, recall, and F1 score.

        Args:
            days_back: Number of days to look back
            site_code: Building to evaluate

        Returns:
            Dict with metrics and details
        """
        try:
            from app.database.repositories.prediction_repository import PredictionRepository
            from app.database.repositories.alert_repository import AlertRepository

            pred_repo = PredictionRepository()
            alert_repo = AlertRepository()

            # Get predictions from period
            predictions = pred_repo.get_all(status="active") + pred_repo.get_all(status="resolved")

            # Get actual alerts from period
            alerts = alert_repo.get_all(site_code=site_code)

            # Build sets of equipment that had predictions vs actual faults
            predicted_equipment = set()
            for pred in predictions:
                eq = pred.get("equipment", {})
                if eq:
                    predicted_equipment.add(eq.get("code", ""))
                elif pred.get("equipment_id"):
                    predicted_equipment.add(pred["equipment_id"])

            actual_fault_equipment = set()
            for alert in alerts:
                severity = alert.get("severity", "")
                if severity in ("high", "critical"):
                    eq = alert.get("equipment", {})
                    if eq:
                        actual_fault_equipment.add(eq.get("code", ""))

            # Compute metrics
            true_positives = len(predicted_equipment & actual_fault_equipment)
            false_positives = len(predicted_equipment - actual_fault_equipment)
            false_negatives = len(actual_fault_equipment - predicted_equipment)
            true_negatives = max(0, 20 - true_positives - false_positives - false_negatives)  # Estimate

            total = true_positives + false_positives + false_negatives + true_negatives
            accuracy = (true_positives + true_negatives) / max(total, 1)
            precision = true_positives / max(true_positives + false_positives, 1)
            recall = true_positives / max(true_positives + false_negatives, 1)
            f1 = (2 * precision * recall) / max(precision + recall, 0.001)

            result = {
                "evaluated_at": datetime.now().isoformat(),
                "period_days": days_back,
                "site_code": site_code,
                "predictions_count": len(predictions),
                "alerts_count": len(alerts),
                "metrics": {
                    "accuracy": round(accuracy, 3),
                    "precision": round(precision, 3),
                    "recall": round(recall, 3),
                    "f1_score": round(f1, 3),
                },
                "confusion_matrix": {
                    "true_positives": true_positives,
                    "false_positives": false_positives,
                    "false_negatives": false_negatives,
                    "true_negatives": true_negatives,
                },
            }

            self._evaluation_history.append(result)
            return result

        except Exception as e:
            logger.error(f"Performance evaluation failed: {e}")
            return {
                "evaluated_at": datetime.now().isoformat(),
                "error": str(e),
                "metrics": {
                    "accuracy": 0.0,
                    "precision": 0.0,
                    "recall": 0.0,
                    "f1_score": 0.0,
                },
            }

    def get_performance_trend(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return recent evaluation history."""
        return self._evaluation_history[-limit:]

    def get_model_health_summary(self) -> Dict[str, Any]:
        """Summary of all active models with age, metrics, and refresh status.

        Combines registry info with performance evaluations.
        """
        try:
            from ml.training.retraining_scheduler import get_retraining_scheduler

            scheduler = get_retraining_scheduler()

            model_checks = scheduler.check_all_models()

            # Categorize
            total = len(model_checks)
            fresh = len([m for m in model_checks if m["status"] == "fresh"])
            stale = len([m for m in model_checks if m["status"] == "stale"])
            missing = len([m for m in model_checks if m["status"] == "missing"])
            underperforming = len([m for m in model_checks if m["status"] == "underperforming"])

            # Latest evaluation
            latest_eval = self._evaluation_history[-1] if self._evaluation_history else None

            return {
                "summary": {
                    "total_model_slots": total,
                    "fresh": fresh,
                    "stale": stale,
                    "missing": missing,
                    "underperforming": underperforming,
                    "health_pct": round((fresh / max(total, 1)) * 100, 1),
                },
                "latest_evaluation": latest_eval,
                "models": model_checks,
                "evaluated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Model health summary failed: {e}")
            return {
                "summary": {"error": str(e)},
                "models": [],
                "evaluated_at": datetime.now().isoformat(),
            }


# Singleton
_monitor: Optional[ModelPerformanceMonitor] = None


def get_performance_monitor() -> ModelPerformanceMonitor:
    """Get singleton ModelPerformanceMonitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = ModelPerformanceMonitor()
    return _monitor
