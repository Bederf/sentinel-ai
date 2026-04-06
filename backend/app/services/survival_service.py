"""
Survival Analysis Service - Run survival predictions for equipment.

Provides:
- Equipment-level survival predictions (30/60/90 day failure probability)
- Hazard ratio calculation (risk vs baseline)
- Remaining useful life estimation
- Fleet-wide risk summary
"""

import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Lazy imports
_registry = None
_model = None


def _get_registry():
    """Lazy load model registry."""
    global _registry
    if _registry is None:
        from ml.registry import get_model_registry

        _registry = get_model_registry()
    return _registry


class SurvivalService:
    """Service for survival analysis predictions."""

    def __init__(self):
        """Initialize survival service."""
        self.registry = _get_registry()
        self._model = None
        self._data_prep = None

    def _load_model(self):
        """Load survival model (cached)."""
        if self._model is None:
            model_info = self.registry.get_active_model("survival", "universal")
            if not model_info:
                raise ValueError("No active survival model found. Train a model first.")

            from ml.survival.model import SurvivalModel

            model_path = model_info["model_path"]
            if not Path(model_path).exists():
                raise ValueError(f"Model file not found: {model_path}")

            self._model = SurvivalModel.load(model_path)
            logger.info(f"Loaded survival model from {model_path}")

        return self._model

    def _get_data_prep(self):
        """Get data prep instance."""
        if self._data_prep is None:
            from ml.survival.data_prep import SurvivalDataPrep

            self._data_prep = SurvivalDataPrep()
        return self._data_prep

    def predict_equipment(self, equipment_id: str) -> dict:
        """
        Get survival prediction for single equipment.

        Args:
            equipment_id: Equipment identifier

        Returns:
            Prediction with failure probabilities, hazard ratio, RUL, risk level
        """
        try:
            model = self._load_model()
        except ValueError as e:
            return {"equipment_id": equipment_id, "error": str(e), "timestamp": datetime.utcnow().isoformat()}

        # Load equipment data
        data_prep = self._get_data_prep()
        equipment_list = data_prep._load_equipment()

        # Find equipment
        equipment = None
        for eq in equipment_list:
            if eq["id"] == equipment_id:
                equipment = eq
                break

        if not equipment:
            return {
                "equipment_id": equipment_id,
                "error": f"Equipment not found: {equipment_id}",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # Get features
        features = data_prep._get_features_at_observation(equipment)

        # Create DataFrame
        try:
            import pandas as pd
        except ImportError:
            return {
                "equipment_id": equipment_id,
                "error": "pandas is required for predictions",
                "timestamp": datetime.utcnow().isoformat(),
            }

        features_df = pd.DataFrame([features])

        # Reorder columns to match model
        feature_cols = model.feature_cols
        for col in feature_cols:
            if col not in features_df.columns:
                features_df[col] = 0
        features_df = features_df[feature_cols]

        # Get survival probabilities
        survival_probs = model.predict_survival_probability(features_df)

        # Get RUL
        rul_days = model.predict_remaining_life(features_df)[0]

        # Get hazard ratio (vs baseline)
        partial_hazard = model.get_partial_hazard(features_df)[0]

        # Get risk level
        failure_prob_30d = float(survival_probs["failure_prob_30d"].values[0])
        risk_level = self._classify_risk(failure_prob_30d)

        # Get contributing factors
        contributing_factors = self._get_top_factors(equipment, features, model)

        return {
            "equipment_id": equipment_id,
            "equipment_type": equipment["type"],
            "equipment_name": equipment.get("name", ""),
            "failure_probability": {
                "30d": round(failure_prob_30d, 3),
                "60d": round(float(survival_probs["failure_prob_60d"].values[0]), 3),
                "90d": round(float(survival_probs["failure_prob_90d"].values[0]), 3),
            },
            "survival_probability": {
                "30d": round(float(survival_probs["survival_30d"].values[0]), 3),
                "60d": round(float(survival_probs["survival_60d"].values[0]), 3),
                "90d": round(float(survival_probs["survival_90d"].values[0]), 3),
            },
            "hazard_ratio": round(float(partial_hazard), 2),
            "remaining_useful_life_days": int(rul_days),
            "risk_level": risk_level,
            "contributing_factors": contributing_factors,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _classify_risk(self, failure_prob_30d: float) -> str:
        """Classify risk level based on 30-day failure probability."""
        if failure_prob_30d > 0.5:
            return "critical"
        elif failure_prob_30d > 0.3:
            return "high"
        elif failure_prob_30d > 0.1:
            return "medium"
        else:
            return "low"

    def _get_top_factors(self, equipment: dict, features: dict, model) -> list[dict]:
        """Get top contributing factors for this equipment."""
        try:
            hazard_ratios = model.get_hazard_ratios()
        except Exception as e:
            logger.warning(f"Could not get hazard ratios: {e}")
            return []

        contributions = []

        for _, row in hazard_ratios.iterrows():
            feature = row["feature"]
            hr = row["hazard_ratio"]
            p_value = row["p_value"]
            value = features.get(feature, 0)

            # Skip if binary feature is 0
            if feature.startswith("is_") and value == 0:
                continue

            # Only include significant factors
            if p_value > 0.1:
                continue

            if hr > 1.2 and value > 0:  # Significant risk factor
                contributions.append(
                    {
                        "factor": feature,
                        "hazard_ratio": round(float(hr), 2),
                        "value": round(float(value), 2),
                        "p_value": round(float(p_value), 3),
                        "impact": "increases_risk",
                    }
                )
            elif hr < 0.8 and value > 0:  # Protective factor
                contributions.append(
                    {
                        "factor": feature,
                        "hazard_ratio": round(float(hr), 2),
                        "value": round(float(value), 2),
                        "p_value": round(float(p_value), 3),
                        "impact": "decreases_risk",
                    }
                )

        # Sort by absolute deviation from 1.0 and return top 5
        contributions.sort(key=lambda x: abs(x["hazard_ratio"] - 1.0), reverse=True)

        return contributions[:5]

    def get_fleet_risk_summary(self) -> dict:
        """Get risk summary across all equipment."""
        data_prep = self._get_data_prep()
        equipment_list = data_prep._load_equipment()

        risk_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        high_risk_equipment = []

        for eq in equipment_list:
            try:
                pred = self.predict_equipment(eq["id"])
                if "error" in pred:
                    continue

                risk_level = pred["risk_level"]
                risk_counts[risk_level] += 1

                if risk_level in ["critical", "high"]:
                    high_risk_equipment.append(
                        {
                            "equipment_id": eq["id"],
                            "equipment_type": eq["type"],
                            "equipment_name": eq.get("name", ""),
                            "risk_level": risk_level,
                            "failure_prob_30d": pred["failure_probability"]["30d"],
                            "rul_days": pred["remaining_useful_life_days"],
                            "hazard_ratio": pred["hazard_ratio"],
                        }
                    )
            except Exception as e:
                logger.warning(f"Error predicting equipment {eq.get('id')}: {e}")
                continue

        # Sort by failure probability
        high_risk_equipment.sort(key=lambda x: x["failure_prob_30d"], reverse=True)

        return {
            "total_equipment": len(equipment_list),
            "risk_distribution": risk_counts,
            "high_risk_count": risk_counts["critical"] + risk_counts["high"],
            "high_risk_equipment": high_risk_equipment[:20],  # Top 20
            "timestamp": datetime.utcnow().isoformat(),
        }

    def get_hazard_ratios(self) -> list[dict]:
        """Get hazard ratios for all features."""
        try:
            model = self._load_model()
            hazard_ratios = model.get_hazard_ratios()
            return hazard_ratios.to_dict("records")
        except Exception as e:
            logger.error(f"Error getting hazard ratios: {e}")
            return []

    def get_training_summary(self) -> dict:
        """Get summary of training data and model."""
        try:
            model_info = self.registry.get_active_model("survival", "universal")
            if not model_info:
                return {"error": "No active survival model"}

            data_prep = self._get_data_prep()
            summary = data_prep.get_training_summary()

            # Add model info
            summary["model"] = {
                "model_id": model_info["model_id"],
                "c_index": model_info["metrics"].get("c_index"),
                "n_samples": model_info["metrics"].get("n_samples"),
                "n_events": model_info["metrics"].get("n_events"),
                "trained_at": model_info.get("metadata", {}).get("trained_at"),
            }

            return summary
        except Exception as e:
            logger.error(f"Error getting training summary: {e}")
            return {"error": str(e)}


# Singleton instance
_service: SurvivalService | None = None


def get_survival_service() -> SurvivalService:
    """Get singleton survival service."""
    global _service
    if _service is None:
        _service = SurvivalService()
    return _service
