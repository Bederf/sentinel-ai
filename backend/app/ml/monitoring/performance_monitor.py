"""ML Performance Monitoring - Calculates accuracy metrics from simulation events.

Reads JSONL simulation logs and computes:
- Confusion matrix (TP, FP, FN, TN)
- Accuracy, Precision, Recall, F1 Score
- Per-equipment performance

This enables dashboard visualization of model accuracy based on real simulation outcomes.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LOG_DIR = Path(__file__).parent.parent.parent / "data" / "simulation_logs"


@dataclass
class ConfusionMatrix:
    """Confusion matrix for binary classification (fault vs no fault)."""

    true_positives: int = 0  # Fault predicted AND repaired
    false_positives: int = 0  # Fault predicted but NOT repaired
    false_negatives: int = 0  # NO fault predicted but WAS repaired
    true_negatives: int = 0  # NO fault predicted and NOT repaired


class PerformanceMonitor:
    """Calculates ML model performance metrics from simulation events."""

    def __init__(self, log_dir: Path = LOG_DIR):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def evaluate_predictions(self, days_back: int = 7, site_code: str | None = None) -> dict[str, Any]:
        """
        Evaluate prediction accuracy against actual simulation outcomes.

        Args:
            days_back: Number of days to look back (uses recent simulation runs)
            site_code: Building code to filter (usually site-002)

        Returns:
            Dict with metrics, confusion matrix, and metadata
        """
        # Find simulation run files from the last N days
        cutoff_time = datetime.now() - timedelta(days=days_back)
        run_files = self._find_recent_runs(cutoff_time, site_code)

        if not run_files:
            logger.warning(f"No simulation runs found in last {days_back} days")
            return self._empty_performance_result()

        # Parse events from all runs
        all_events = []
        for run_file in run_files:
            events = self._read_events_jsonl(run_file)
            all_events.extend(events)

        if not all_events:
            logger.warning("No events found in simulation logs")
            return self._empty_performance_result()

        # Build confusion matrix
        equipment_predictions = {}  # Map equipment_code -> {predicted, actual}
        confusion = ConfusionMatrix()

        for event in all_events:
            event_type = event.get("event_type", "")
            equipment_id = event.get("equipment_id", "unknown")

            # Initialize equipment entry if not present
            if equipment_id not in equipment_predictions:
                equipment_predictions[equipment_id] = {
                    "fault_predicted": False,
                    "repair_completed": False,
                    "fault_details": {},
                }

            # Track fault events (predictions)
            if event_type == "equipment_fault":
                equipment_predictions[equipment_id]["fault_predicted"] = True
                equipment_predictions[equipment_id]["fault_details"] = event.get("details", {})

            # Track repair events (actual outcomes)
            elif event_type == "repair_completed":
                equipment_predictions[equipment_id]["repair_completed"] = True

        # Build confusion matrix from predictions
        for _eq_id, pred in equipment_predictions.items():
            predicted = pred["fault_predicted"]  # Model predicted fault
            actual = pred["repair_completed"]  # Actual: repair happened

            if predicted and actual:
                confusion.true_positives += 1
            elif predicted and not actual:
                confusion.false_positives += 1
            elif not predicted and actual:
                confusion.false_negatives += 1
            else:
                confusion.true_negatives += 1

        # Calculate metrics from confusion matrix
        metrics = self._calculate_metrics(confusion)

        return {
            "evaluated_at": datetime.now().isoformat(),
            "period_days": days_back,
            "site_code": site_code,
            "predictions_count": len(equipment_predictions),
            "alerts_count": len([e for e in all_events if e.get("event_type") == "alert_generated"]),
            "metrics": {
                "accuracy": metrics["accuracy"],
                "precision": metrics["precision"],
                "recall": metrics["recall"],
                "f1_score": metrics["f1_score"],
            },
            "confusion_matrix": {
                "true_positives": confusion.true_positives,
                "false_positives": confusion.false_positives,
                "false_negatives": confusion.false_negatives,
                "true_negatives": confusion.true_negatives,
            },
        }

    def get_model_health_summary(self) -> dict[str, Any]:
        """Get health summary of all active models.

        Evaluates recent model performance and returns overall health status.
        Returns:
            Dict with model health metrics and summary.
        """
        try:
            recent_result = self.evaluate_predictions(days_back=7)
            metrics = recent_result.get("metrics", {})

            # Determine health status based on metrics
            accuracy = metrics.get("accuracy", 0.0)
            precision = metrics.get("precision", 0.0)

            if accuracy >= 0.85 and precision >= 0.80:
                status = "healthy"
            elif accuracy >= 0.75 and precision >= 0.65:
                status = "warning"
            else:
                status = "critical"

            return {
                "status": status,
                "summary": {
                    "model_count": 2,  # lstm, autoencoder
                    "healthy": 1 if status == "healthy" else 0,
                    "warning": 1 if status == "warning" else 0,
                    "critical": 1 if status == "critical" else 0,
                },
                "metrics": metrics,
                "evaluated_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting model health summary: {e}")
            return {
                "status": "unknown",
                "summary": {"model_count": 0},
                "metrics": {},
                "error": str(e),
            }

    def _find_recent_runs(self, cutoff_time: datetime, site_code: str) -> list[Path]:
        """Find simulation run metadata files newer than cutoff_time."""
        recent_runs = []

        if not self.log_dir.exists():
            return recent_runs

        for meta_file in self.log_dir.glob("*_meta.json"):
            try:
                # Check file modification time
                file_time = datetime.fromtimestamp(meta_file.stat().st_mtime)
                if file_time < cutoff_time:
                    continue

                # Check building code in metadata
                with open(meta_file) as f:
                    meta = json.load(f)
                    if meta.get("site_code") == site_code:
                        # Find corresponding events file
                        events_file = self.log_dir / meta["events_file"]
                        if events_file.exists():
                            recent_runs.append(events_file)
            except Exception as e:
                logger.warning(f"Error reading {meta_file}: {e}")

        return recent_runs

    def _read_events_jsonl(self, jsonl_file: Path) -> list[dict[str, Any]]:
        """Read JSONL events file line by line."""
        events = []

        try:
            with open(jsonl_file) as f:
                for line in f:
                    if line.strip():
                        try:
                            event = json.loads(line)
                            events.append(event)
                        except json.JSONDecodeError as e:
                            logger.warning(f"Error parsing JSON line in {jsonl_file}: {e}")
        except Exception as e:
            logger.error(f"Error reading {jsonl_file}: {e}")

        return events

    def _calculate_metrics(self, confusion: ConfusionMatrix) -> dict[str, float]:
        """Calculate Accuracy, Precision, Recall, F1 from confusion matrix."""
        tp = confusion.true_positives
        fp = confusion.false_positives
        fn = confusion.false_negatives
        tn = confusion.true_negatives

        # Accuracy: (TP + TN) / (TP + TN + FP + FN)
        total = tp + tn + fp + fn
        accuracy = (tp + tn) / total if total > 0 else 0.0

        # Precision: TP / (TP + FP)  - "Of predicted faults, how many were real?"
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0

        # Recall: TP / (TP + FN)  - "Of actual faults, how many did we predict?"
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

        # F1 Score: 2 * (Precision * Recall) / (Precision + Recall)
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        return {
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1_score, 4),
        }

    def _empty_performance_result(self) -> dict[str, Any]:
        """Return empty result when no data available."""
        return {
            "evaluated_at": datetime.now().isoformat(),
            "period_days": 7,
            "site_code": "unknown",
            "predictions_count": 0,
            "alerts_count": 0,
            "metrics": {
                "accuracy": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "f1_score": 0.0,
            },
            "confusion_matrix": {
                "true_positives": 0,
                "false_positives": 0,
                "false_negatives": 0,
                "true_negatives": 0,
            },
            "note": "No simulation data available for the specified period",
        }


# Singleton instance
_monitor: PerformanceMonitor | None = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get singleton performance monitor."""
    global _monitor
    if _monitor is None:
        _monitor = PerformanceMonitor()
    return _monitor
