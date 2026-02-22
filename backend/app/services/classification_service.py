"""Failure Classification Service.

This service provides failure type classification using Random Forest models.
It predicts specific failure types (compressor, bearing, motor, etc.) for equipment.
"""

import logging
from datetime import datetime
from typing import Dict, List

import pandas as pd
from ml.classifier.model import FailureClassifier
from ml.registry import ModelRegistry
from app.services.feature_service import FeatureComputeService
from app.database.repositories.equipment_repository import EquipmentRepository

logger = logging.getLogger(__name__)

# Singleton instance
_classification_service = None


def get_classification_service() -> "FailureClassificationService":
    """Get the singleton classification service instance.

    Returns:
        FailureClassificationService instance
    """
    global _classification_service
    if _classification_service is None:
        _classification_service = FailureClassificationService()
    return _classification_service


class FailureClassificationService:
    """Service for failure type classification.

    Features:
    - Predict most likely failure type for equipment
    - Get fleet-wide failure risk summary
    - Feature importance for explainability
    """

    def __init__(self):
        """Initialize the classification service."""
        self.registry = ModelRegistry()
        self._models: Dict[str, FailureClassifier] = {}
        self.feature_service = FeatureComputeService()
        self.equipment_repo = EquipmentRepository()

    def _load_model(self, equipment_type: str) -> FailureClassifier:
        """Load classifier for equipment type.

        Args:
            equipment_type: Type of equipment

        Returns:
            Loaded FailureClassifier

        Raises:
            ValueError: If no classifier available for equipment type
        """
        if equipment_type not in self._models:
            model_info = self.registry.get_active_model("classifier", equipment_type)

            if not model_info:
                raise ValueError(f"No classifier available for {equipment_type}")

            self._models[equipment_type] = FailureClassifier.load(model_info["model_path"])
            logger.info(f"Loaded classifier for {equipment_type}")

        return self._models[equipment_type]

    def predict_failure_type(self, equipment_id: str) -> Dict:
        """Predict most likely failure type for equipment.

        Args:
            equipment_id: Equipment identifier

        Returns:
            Prediction dictionary with failure type, confidence, and probabilities
        """
        # Get equipment
        equipment = self.equipment_repo.get_by_id(equipment_id)

        if not equipment:
            # Try JSON fallback
            import json
            from pathlib import Path

            equipment_file = Path(__file__).parent.parent / "data" / "equipment.json"
            with open(equipment_file) as f:
                all_equipment = json.load(f)
                equipment_list = [eq for eq in all_equipment if eq.get("id") == equipment_id]
                equipment = equipment_list[0] if equipment_list else None

        if not equipment:
            raise ValueError(f"Equipment not found: {equipment_id}")

        equipment_type = equipment.get("equipment_type") if isinstance(equipment, dict) else equipment.equipment_type

        # Load model
        model = self._load_model(equipment_type)

        # Get current features
        try:
            features = self.feature_service.compute_features(equipment_id=equipment_id, equipment_type=equipment_type)
        except Exception as e:
            logger.error(f"Failed to compute features for {equipment_id}: {e}")
            # Use default features
            from ml.classifier.data_prep import ClassifierDataPrep

            data_prep = ClassifierDataPrep()
            features = data_prep._get_default_features(equipment_type)

        # Flatten features
        flattened = {}
        for key, value in features.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    flattened[f"{key}_{sub_key}"] = sub_value
            else:
                flattened[key] = value

        # Predict
        X = pd.DataFrame([flattened])
        predictions = model.predict(X)[0]

        # Get explanation
        explanation = model.explain_prediction(X)

        return {
            "equipment_id": equipment_id,
            "equipment_type": equipment_type,
            "predicted_failure": predictions["predicted_failure"],
            "confidence": predictions["confidence"],
            "all_failure_probabilities": predictions["all_probabilities"],
            "contributing_factors": explanation,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def get_fleet_failure_risks(self, min_confidence: float = 0.5) -> List[Dict]:
        """Get failure type predictions for all equipment.

        Args:
            min_confidence: Minimum confidence threshold

        Returns:
            List of high-confidence failure predictions
        """
        equipment_list = self.equipment_repo.get_all()

        if not equipment_list:
            # Try JSON fallback
            import json
            from pathlib import Path

            equipment_file = Path(__file__).parent.parent / "data" / "equipment.json"
            with open(equipment_file) as f:
                equipment_list = json.load(f)

        results = []

        for eq in equipment_list:
            equipment_id = eq.get("id") if isinstance(eq, dict) else eq.id

            try:
                pred = self.predict_failure_type(equipment_id)

                if pred["confidence"] >= min_confidence:
                    results.append(
                        {
                            "equipment_id": equipment_id,
                            "equipment_type": pred["equipment_type"],
                            "predicted_failure": pred["predicted_failure"],
                            "confidence": pred["confidence"],
                        }
                    )
            except Exception as e:
                logger.debug(f"Could not classify {equipment_id}: {e}")
                continue

        # Sort by confidence
        results.sort(key=lambda x: x["confidence"], reverse=True)

        return results

    def get_feature_importance(self, equipment_type: str, top_n: int = 20) -> List[Dict]:
        """Get feature importance for an equipment type.

        Args:
            equipment_type: Type of equipment
            top_n: Number of top features to return

        Returns:
            List of feature importance rankings
        """
        model = self._load_model(equipment_type)

        importance_df = model.get_feature_importance(top_n)

        return importance_df.to_dict("records")

    def get_model_info(self, equipment_type: str) -> Dict:
        """Get model information for an equipment type.

        Args:
            equipment_type: Type of equipment

        Returns:
            Model metadata
        """
        model_info = self.registry.get_active_model("classifier", equipment_type)

        if not model_info:
            raise ValueError(f"No classifier available for {equipment_type}")

        return {
            "equipment_type": equipment_type,
            "model_path": model_info["model_path"],
            "metadata": model_info.get("metadata", {}),
        }

    def list_available_models(self) -> List[Dict]:
        """List all available classification models.

        Returns:
            List of model information
        """
        models = []

        for equipment_type in ["chiller", "ahu", "generator", "fcu", "ups"]:
            try:
                info = self.get_model_info(equipment_type)
                models.append(info)
            except ValueError:
                continue

        return models
