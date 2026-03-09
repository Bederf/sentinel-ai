"""
ML Feedback Service (Phase 57-02)

Records repair outcomes, generates training data for ML models,
and tracks prediction accuracy. Closes the feedback loop between
ML predictions and real-world maintenance results.

Uses in-memory storage for demo scope.
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config.settings import settings
from app.models.ml_feedback import (
    MLFeedbackRecord,
    TrainingDataPoint,
    PredictionAccuracy,
    MLFeedbackSummary,
)

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
ML_FEEDBACK_FILE = DATA_DIR / "ml_feedback_records.json"
ML_FEEDBACK_STATE_TABLE = "ml_feedback_state"
ML_FEEDBACK_STATE_KEY = "global"


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
        self._client = None
        self._feedback_records: List[MLFeedbackRecord] = []
        self._training_data: List[TrainingDataPoint] = []
        self._prediction_accuracy: Dict[str, PredictionAccuracy] = {}
        self._record_counter: int = 0
        self._scoring_inputs: Dict[str, Dict[str, Any]] = {}

        self._load_state()
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
        self._save_state()

        # 5. Log
        logger.info(
            f"ML feedback recorded: {record_id} for {equipment_id}, "
            f"WO={work_order_id}, score={effectiveness_score:.1f}%, "
            f"successful={repair_successful}"
        )

        return record

    def record_module_outcome(
        self,
        *,
        site_id: str,
        module_type: str,
        recommendation_id: str,
        action_type: str,
        successful: bool,
        outcome_status: str,
        predicted_impact: Optional[Dict[str, Any]] = None,
        actual_impact: Optional[Dict[str, Any]] = None,
        confidence_score: Optional[float] = None,
        equipment_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[MLFeedbackRecord]:
        """Record module-level recommendation outcome into the shared ML loop.

        This keeps base-package ML feedback active while adding module-specific
        outcome learning as add-ons are activated.
        """
        module_type_normalized = self._normalize_module_type(module_type)
        if not module_type_normalized:
            return None

        if not self._is_module_eligible_for_feedback(site_id, module_type_normalized):
            logger.info(
                "Skipping module feedback for inactive module: site=%s module=%s",
                site_id,
                module_type_normalized,
            )
            return None

        predicted = predicted_impact or {}
        actual = actual_impact or {}
        extra = metadata or {}
        effective_equipment_id = equipment_id or f"{site_id}-{module_type_normalized}-module"
        effective_score = self._compute_effectiveness_score(
            successful=successful,
            predicted_impact=predicted,
            actual_impact=actual,
        )

        self._record_counter += 1
        record_id = f"mlf-mod-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self._record_counter:04d}"

        record = MLFeedbackRecord(
            id=record_id,
            equipment_id=effective_equipment_id,
            work_order_id=recommendation_id or f"module-{record_id}",
            feedback_type="module_outcome",
            repair_successful=successful,
            effectiveness_score=effective_score,
            prediction_id=recommendation_id or None,
            prediction_was_correct=successful,
            recorded_at=datetime.now(),
            metadata={
                "site_id": site_id,
                "module_type": module_type_normalized,
                "action_type": action_type,
                "outcome_status": outcome_status,
                "predicted_impact": predicted,
                "actual_impact": actual,
                "confidence_score": confidence_score,
                **extra,
            },
        )

        self._feedback_records.append(record)

        training_features: Dict[str, float] = {
            "effectiveness_score": float(effective_score),
            "success_flag": 1.0 if successful else 0.0,
        }
        if isinstance(confidence_score, (int, float)):
            training_features["confidence_score"] = float(confidence_score)

        predicted_energy = predicted.get("energy_kwh")
        actual_energy = actual.get("energy_kwh")
        if isinstance(predicted_energy, (int, float)):
            training_features["predicted_energy_kwh"] = float(predicted_energy)
        if isinstance(actual_energy, (int, float)):
            training_features["actual_energy_kwh"] = float(actual_energy)
            if isinstance(predicted_energy, (int, float)):
                training_features["energy_delta_kwh"] = float(actual_energy) - float(predicted_energy)

        self._training_data.append(
            TrainingDataPoint(
                equipment_id=effective_equipment_id,
                equipment_type=module_type_normalized,
                features=training_features,
                label="successful" if successful else "failed",
                repair_effectiveness=effective_score,
                source="module_outcome",
            )
        )
        self._save_state()

        logger.info(
            "Module feedback recorded: id=%s site=%s module=%s action=%s status=%s success=%s",
            record_id,
            site_id,
            module_type_normalized,
            action_type,
            outcome_status,
            successful,
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
            filtered = [tp for tp in self._training_data if tp.equipment_type.lower() == equipment_type.lower()]
            logger.info(f"Generated {len(filtered)} training data points for equipment type '{equipment_type}'")
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
        prediction_records = [r for r in self._feedback_records if r.prediction_id is not None]

        if not prediction_records:
            accuracy = self._prediction_accuracy.get(model_type, PredictionAccuracy(model_type=model_type))
            return accuracy

        # Calculate metrics
        total = len(prediction_records)
        correct = sum(1 for r in prediction_records if r.prediction_was_correct)
        false_positives = sum(
            1 for r in prediction_records if r.prediction_was_correct is False and not r.repair_successful
        )
        false_negatives = sum(
            1 for r in prediction_records if r.prediction_was_correct is False and r.repair_successful
        )

        # True positives: prediction said failure, and there was a failure
        true_positives = correct

        # Precision: TP / (TP + FP)
        precision = (
            true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
        )

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
        self._save_state()

        logger.info(f"Prediction accuracy for {model_type}: {accuracy.accuracy_percent}% ({correct}/{total})")

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
        repair_outcomes = sum(1 for r in self._feedback_records if r.feedback_type == "repair_outcome")
        predictions_evaluated = sum(1 for r in self._feedback_records if r.prediction_id is not None)
        module_feedback_records = [r for r in self._feedback_records if r.feedback_type == "module_outcome"]

        module_feedback_counts: Dict[str, int] = {}
        module_success_counts: Dict[str, int] = {}
        for record in module_feedback_records:
            module_name = self._normalize_module_type(record.metadata.get("module_type", ""))
            if not module_name:
                continue
            module_feedback_counts[module_name] = module_feedback_counts.get(module_name, 0) + 1
            if record.repair_successful:
                module_success_counts[module_name] = module_success_counts.get(module_name, 0) + 1

        module_success_rates: Dict[str, float] = {}
        for module_name, total_count in module_feedback_counts.items():
            success_count = module_success_counts.get(module_name, 0)
            module_success_rates[module_name] = (
                round((success_count / total_count) * 100, 2) if total_count > 0 else 0.0
            )

        # Calculate average accuracy across all model types
        if self._prediction_accuracy:
            avg_accuracy = sum(a.accuracy_percent for a in self._prediction_accuracy.values()) / len(
                self._prediction_accuracy
            )
        else:
            avg_accuracy = 0.0

        return MLFeedbackSummary(
            total_feedback_records=total,
            repair_outcomes_recorded=repair_outcomes,
            predictions_evaluated=predictions_evaluated,
            avg_prediction_accuracy=round(avg_accuracy, 2),
            model_accuracies=dict(self._prediction_accuracy),
            training_data_points=len(self._training_data),
            module_feedback_records=len(module_feedback_records),
            module_feedback_counts=module_feedback_counts,
            module_success_rates=module_success_rates,
            last_retrain_date=None,
        )

    def get_module_feedback_summary(
        self,
        site_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get module-outcome feedback summary, optionally scoped to a site."""
        module_records = [r for r in self._feedback_records if r.feedback_type == "module_outcome"]
        if site_id:
            module_records = [r for r in module_records if r.metadata.get("site_id") == site_id]

        counts: Dict[str, int] = {}
        success_counts: Dict[str, int] = {}
        for record in module_records:
            module_name = self._normalize_module_type(record.metadata.get("module_type", ""))
            if not module_name:
                continue
            counts[module_name] = counts.get(module_name, 0) + 1
            if record.repair_successful:
                success_counts[module_name] = success_counts.get(module_name, 0) + 1

        success_rates = {
            module_name: round((success_counts.get(module_name, 0) / total) * 100, 2) if total else 0.0
            for module_name, total in counts.items()
        }

        return {
            "site_id": site_id,
            "records": len(module_records),
            "counts": counts,
            "success_rates": success_rates,
        }

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
        records = [r for r in self._feedback_records if r.equipment_id == equipment_id]
        logger.info(f"Retrieved {len(records)} feedback records for {equipment_id}")
        return records

    def refresh_scoring_inputs(self, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Refresh feedback-derived scoring inputs (module multipliers).

        Converts module success rates into ranking multipliers used by
        recommendation scoring to prioritize modules performing well and
        de-emphasize modules with weak realized outcomes.
        """
        site_ids: set[str] = set()
        if site_id:
            site_ids.add(site_id)
        else:
            for record in self._feedback_records:
                if record.feedback_type != "module_outcome":
                    continue
                sid = record.metadata.get("site_id")
                if isinstance(sid, str) and sid.strip():
                    site_ids.add(sid.strip())

        refreshed: Dict[str, Dict[str, Any]] = {}
        for sid in site_ids:
            module_summary = self.get_module_feedback_summary(site_id=sid)
            success_rates = module_summary.get("success_rates", {})
            multipliers = {
                module_name: self._success_rate_to_multiplier(rate) for module_name, rate in success_rates.items()
            }
            refreshed[sid] = {
                "site_id": sid,
                "module_multipliers": multipliers,
                "module_success_rates": success_rates,
                "records": module_summary.get("records", 0),
                "refreshed_at": datetime.now().isoformat(),
            }

        if refreshed:
            self._scoring_inputs.update(refreshed)
            self._save_state()

        return {
            "refreshed_sites": len(refreshed),
            "site_ids": sorted(list(refreshed.keys())),
        }

    def get_scoring_inputs(self, site_id: str) -> Dict[str, Any]:
        """Get feedback-derived scoring inputs for a site."""
        if not site_id:
            return {}
        site_inputs = self._scoring_inputs.get(site_id)
        if isinstance(site_inputs, dict):
            return site_inputs
        return {}

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    @property
    def client(self):
        """Lazy-load Supabase client (disabled when JSON-only mode is set)."""
        if settings.use_json_storage:
            return None
        if self._client is None:
            try:
                from app.database.supabase_client import get_supabase_client

                self._client = get_supabase_client()
            except Exception as e:
                logger.warning("ML feedback Supabase client unavailable, using JSON fallback: %s", e)
                self._client = None
        return self._client

    def _load_state(self) -> None:
        """Load ML feedback state from Supabase first, then JSON fallback."""
        loaded_from_supabase = self._load_state_supabase()
        if loaded_from_supabase:
            # Keep JSON backup synced to latest source of truth.
            self._save_state_json()
            return
        self._load_state_json()

    def _load_state_supabase(self) -> bool:
        """Load ML feedback state payload from Supabase."""
        client = self.client
        if client is None:
            return False

        try:
            result = (
                client.table(ML_FEEDBACK_STATE_TABLE)
                .select("payload")
                .eq("state_key", ML_FEEDBACK_STATE_KEY)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            if not rows:
                return False

            payload = rows[0].get("payload")
            if not isinstance(payload, dict):
                logger.warning("Invalid ML feedback payload format in Supabase")
                return False

            self._hydrate_from_payload(payload)
            logger.info(
                "Loaded ML feedback state from Supabase: records=%s training=%s models=%s",
                len(self._feedback_records),
                len(self._training_data),
                len(self._prediction_accuracy),
            )
            return True
        except Exception as e:
            logger.warning("Failed to load ML feedback state from Supabase: %s", e)
            return False

    def _load_state_json(self) -> None:
        """Load ML feedback state from local JSON backup."""
        try:
            if not ML_FEEDBACK_FILE.exists():
                return

            with open(ML_FEEDBACK_FILE, "r") as f:
                payload = json.load(f)
            self._hydrate_from_payload(payload)
            logger.info(
                "Loaded ML feedback state from JSON backup: records=%s training=%s models=%s",
                len(self._feedback_records),
                len(self._training_data),
                len(self._prediction_accuracy),
            )
        except Exception as e:
            logger.warning("Failed to load ML feedback state, starting fresh: %s", e)
            self._feedback_records = []
            self._training_data = []
            self._prediction_accuracy = {}
            self._record_counter = 0

    def _save_state(self) -> None:
        """Persist ML feedback to Supabase (source of truth) and JSON backup."""
        payload = self._build_state_payload()

        saved_to_supabase = self._save_state_supabase(payload)
        if not saved_to_supabase and not settings.use_json_storage:
            logger.warning("ML feedback state not saved to Supabase; JSON backup only for this update")

        self._save_state_json(payload)

    def _save_state_supabase(self, payload: Dict[str, Any]) -> bool:
        """Persist ML feedback state payload to Supabase."""
        client = self.client
        if client is None:
            return False

        try:
            client.table(ML_FEEDBACK_STATE_TABLE).upsert(
                {
                    "state_key": ML_FEEDBACK_STATE_KEY,
                    "payload": payload,
                },
                on_conflict="state_key",
            ).execute()
            return True
        except Exception as e:
            logger.warning("Failed to persist ML feedback state to Supabase: %s", e)
            return False

    def _save_state_json(self, payload: Optional[Dict[str, Any]] = None) -> None:
        """Persist ML feedback state payload to JSON backup."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            state_payload = payload if payload is not None else self._build_state_payload()
            with open(ML_FEEDBACK_FILE, "w") as f:
                json.dump(state_payload, f, indent=2)
        except Exception as e:
            logger.warning("Failed to persist ML feedback JSON backup: %s", e)

    def _build_state_payload(self) -> Dict[str, Any]:
        """Build serialized state payload for Supabase/JSON persistence."""
        return {
            "feedback_records": [r.model_dump(mode="json") for r in self._feedback_records[-2000:]],
            "training_data": [t.model_dump(mode="json") for t in self._training_data[-5000:]],
            "prediction_accuracy": {
                model_name: metrics.model_dump(mode="json") for model_name, metrics in self._prediction_accuracy.items()
            },
            "scoring_inputs": self._scoring_inputs,
            "record_counter": self._record_counter,
            "updated_at": datetime.now().isoformat(),
        }

    def _hydrate_from_payload(self, payload: Dict[str, Any]) -> None:
        """Hydrate in-memory state from serialized payload."""
        records = payload.get("feedback_records", [])
        training = payload.get("training_data", [])
        accuracy = payload.get("prediction_accuracy", {})

        self._feedback_records = [MLFeedbackRecord.model_validate(item) for item in records]
        self._training_data = [TrainingDataPoint.model_validate(item) for item in training]
        self._prediction_accuracy = {
            model_name: PredictionAccuracy.model_validate(model_data) for model_name, model_data in accuracy.items()
        }
        scoring_inputs = payload.get("scoring_inputs", {})
        self._scoring_inputs = scoring_inputs if isinstance(scoring_inputs, dict) else {}
        self._record_counter = int(payload.get("record_counter", len(self._feedback_records)))

    def _update_prediction_accuracy_from_record(self, record: MLFeedbackRecord):
        """Update prediction accuracy tracking from a single feedback record."""
        # Determine model type from prediction_id pattern or default to 'unknown'
        model_type = self._infer_model_type(record.prediction_id)

        if model_type not in self._prediction_accuracy:
            self._prediction_accuracy[model_type] = PredictionAccuracy(model_type=model_type)

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
            acc.accuracy_percent = round((acc.correct_predictions / acc.total_predictions) * 100, 2)
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

            get_element_trend_service()  # ensure service initialized

            # For demo scope, return basic features
            # In production, this would query real-time sensor data
            return {
                "effectiveness_score": 0.0,
                "equipment_id_hash": hash(equipment_id) % 1000 / 1000.0,
            }
        except Exception as e:
            logger.debug(f"Could not get features for {equipment_id}: {e}")
            return {}

    def _normalize_module_type(self, module_type: str) -> str:
        """Normalize module type to lowercase canonical value."""
        if not isinstance(module_type, str):
            return ""
        normalized = module_type.strip().lower()
        aliases = {
            "power": "energy",
            "bess": "solar",
            "battery": "solar",
            "pv": "solar",
        }
        return aliases.get(normalized, normalized)

    def _candidate_site_ids(self, site_id: str) -> List[str]:
        """Return site-id variants used across legacy/new storage formats."""
        if not isinstance(site_id, str):
            return []
        sid = site_id.strip()
        if not sid:
            return []

        candidates = [sid]
        lower = sid.lower()
        if lower.startswith("site-"):
            suffix = sid.split("-", 1)[1] if "-" in sid else ""
            if suffix.isdigit():
                candidates.append(f"S{suffix}")
        elif sid.startswith("S") and sid[1:].isdigit():
            candidates.append(f"site-{sid[1:]}")

        deduped: List[str] = []
        for item in candidates:
            if item and item not in deduped:
                deduped.append(item)
        return deduped

    def _is_module_eligible_for_feedback(self, site_id: str, module_type: str) -> bool:
        """Return True if module feedback should be recorded for this site/module."""
        if not site_id or not module_type:
            return False

        try:
            from app.models.module_registry import ModuleType
        except Exception as e:
            logger.debug("Cannot import ModuleType for eligibility check: %s", e)
            return False

        try:
            module_enum = ModuleType(module_type)
        except ValueError:
            return False

        try:
            import app.services.module_registry_service as _registry_mod

            non_deactivatable = _registry_mod.NON_DEACTIVATABLE_MODULES
            registry = _registry_mod.module_registry
        except Exception as e:
            logger.debug("Cannot import module_registry for eligibility check: %s", e)
            return False

        # Base pack modules are always eligible for the shared ML loop.
        if module_enum in non_deactivatable:
            return True

        # For add-on modules, resolve across site-id variants and fail closed.
        for candidate in self._candidate_site_ids(site_id):
            try:
                site_config = registry.get_site_config(candidate)
                if site_config is None:
                    continue
                if registry.is_module_active(candidate, module_enum):
                    return True
            except Exception as e:
                logger.debug("Module check failed for candidate %s: %s", candidate, e)
                continue

        return False

    def _compute_effectiveness_score(
        self,
        *,
        successful: bool,
        predicted_impact: Dict[str, Any],
        actual_impact: Dict[str, Any],
    ) -> float:
        """Compute a normalized 0-100 effectiveness score for module outcomes."""
        predicted_energy = predicted_impact.get("energy_kwh")
        actual_energy = actual_impact.get("energy_kwh")
        if isinstance(predicted_energy, (int, float)) and float(predicted_energy) > 0:
            if isinstance(actual_energy, (int, float)):
                variance_pct = abs(float(predicted_energy) - float(actual_energy)) / float(predicted_energy) * 100.0
                return round(max(0.0, 100.0 - variance_pct), 2)
        return 100.0 if successful else 0.0

    def _success_rate_to_multiplier(self, success_rate: float) -> float:
        """Map module success rate (%) to a recommendation score multiplier."""
        rate = float(success_rate)
        if rate >= 90.0:
            return 1.1
        if rate >= 80.0:
            return 1.05
        if rate >= 65.0:
            return 1.0
        if rate >= 50.0:
            return 0.9
        return 0.8


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
