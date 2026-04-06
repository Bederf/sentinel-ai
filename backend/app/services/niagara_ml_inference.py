"""
Niagara ML Inference Service

Handles equipment-specific ML predictions with confidence thresholds.
Integrates with model registry to route predictions to appropriate trained models.

Provides unified interface for confidence-based prediction filtering.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any

import joblib

from app.database.supabase_client import get_supabase_client
from app.ml.models.model_registry_db import ModelRegistryDB, get_model_registry

logger = logging.getLogger(__name__)

# Path to trained model files
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "ml", "models")


class NiagaraMLInference:
    """
    Equipment-specific ML inference service.

    Routes predictions through appropriate models based on equipment type,
    calculates confidence scores, and enforces tier-based thresholds.
    """

    def __init__(self):
        """Initialize inference service."""
        self.supabase = get_supabase_client()
        self._registry: ModelRegistryDB | None = None
        self._model_cache = {}  # Cache loaded models

    async def _get_registry(self) -> ModelRegistryDB:
        """Get model registry (lazy load)."""
        if self._registry is None:
            self._registry = await get_model_registry()
        return self._registry

    async def get_prediction_with_confidence(
        self, equipment_code: str, min_confidence: float = 0.70, tier: int = 2
    ) -> dict[str, Any] | None:
        """
        Generate prediction with confidence score for equipment.

        Args:
            equipment_code: Equipment identifier (e.g., 'S002-CHILLER-B1-001')
            min_confidence: Minimum confidence threshold to return prediction
            tier: Capability tier (2=advisory, 3=auto-execute)

        Returns:
            Prediction with confidence and model metadata, or None if:
            - Equipment not found
            - Model not available
            - Confidence below threshold
        """
        try:
            # Extract equipment type from code
            # Format: {site}-{type}-{floor}-{zone}
            equipment_type = self._extract_equipment_type(equipment_code)
            if not equipment_type:
                logger.warning(f"Could not extract equipment type from {equipment_code}")
                return None

            # Get registry and check if model available
            registry = await self._get_registry()
            if not await registry.is_model_available(equipment_type):
                logger.debug(f"No model available for {equipment_type}")
                return None

            # Get equipment data
            equipment = await self._get_equipment_data(equipment_code)
            if not equipment:
                logger.warning(f"Equipment not found: {equipment_code}")
                return None

            # Get model configuration
            model_config = await registry.get_model(equipment_type)
            if not model_config:
                return None

            # Prepare features for inference
            features = await self._prepare_features(equipment)
            if features is None:
                logger.warning(f"Could not prepare features for {equipment_code}")
                return None

            # Run inference
            confidence = await self._run_inference(equipment_type, features, model_config)

            if confidence is None:
                logger.warning(f"Inference failed for {equipment_code}")
                return None

            # Check threshold
            threshold = await registry.get_threshold_value(equipment_type, tier)
            if threshold is None or confidence < threshold:
                logger.debug(
                    f"Confidence {confidence:.2%} below threshold {threshold:.2%} for {equipment_code} (tier {tier})"
                    if threshold
                    else f"Confidence {confidence:.2%} but no threshold configured"
                )
                return None

            # Get tier 3 threshold for comparison
            tier3_threshold = await registry.get_threshold_value(equipment_type, 3) or 0.85

            # Return prediction with confidence and metadata
            return {
                "equipment_code": equipment_code,
                "equipment_type": equipment_type,
                "equipment_name": equipment.get("name"),
                "confidence": confidence,
                "model_r_squared": model_config.r_squared_avg,
                "model_id": model_config.model_id,
                "model_status": model_config.status,
                "threshold_tier2": threshold,
                "threshold_tier3": tier3_threshold,
                "meets_tier2_requirement": confidence >= threshold,
                "meets_tier3_requirement": confidence >= tier3_threshold,
                "timestamp": datetime.now().isoformat(),
                "health_score": equipment.get("health_score"),
                "last_alert": equipment.get("last_alert_timestamp"),
            }

        except Exception as e:
            logger.error(f"Error generating prediction for {equipment_code}: {e!s}")
            return None

    async def get_predictions_for_site(
        self, site_code: str, min_confidence: float = 0.70, tier: int = 2, equipment_types: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Generate predictions for all equipment at a site.

        Args:
            site_code: Site identifier (e.g., 'S002')
            min_confidence: Minimum confidence threshold
            tier: Capability tier
            equipment_types: Optional filter for specific equipment types

        Returns:
            Dict with predictions and summary statistics
        """
        results = {
            "site_code": site_code,
            "predictions": [],
            "summary": {
                "total_equipment": 0,
                "with_models": 0,
                "predictions_generated": 0,
                "predictions_filtered": 0,
                "timestamp": datetime.now().isoformat(),
            },
        }

        try:
            # Get all equipment for site
            equipment_list = await self._get_site_equipment(site_code)
            if not equipment_list:
                logger.warning(f"No equipment found for site {site_code}")
                return results

            results["summary"]["total_equipment"] = len(equipment_list)

            # Generate predictions for each equipment
            for equipment in equipment_list:
                equipment_code = equipment.get("code")
                eq_type = self._extract_equipment_type(equipment_code)

                # Filter by equipment types if specified
                if equipment_types and eq_type not in equipment_types:
                    continue

                # Skip if no model
                registry = await self._get_registry()
                if not await registry.is_model_available(eq_type):
                    continue

                results["summary"]["with_models"] += 1

                # Generate prediction
                prediction = await self.get_prediction_with_confidence(equipment_code, min_confidence, tier)

                if prediction:
                    results["predictions"].append(prediction)
                    results["summary"]["predictions_generated"] += 1
                else:
                    results["summary"]["predictions_filtered"] += 1

            logger.info(
                f"Generated {results['summary']['predictions_generated']} predictions "
                f"for {site_code} (filtered: {results['summary']['predictions_filtered']})"
            )

        except Exception as e:
            logger.error(f"Error generating site predictions for {site_code}: {e!s}")

        return results

    def _extract_equipment_type(self, equipment_code: str) -> str | None:
        """
        Extract equipment type from equipment code.

        Equipment code format: {site}-{type}-{floor}-{zone}
        Example: S002-CHILLER-B1-001 → CHILLER

        Args:
            equipment_code: Equipment code string

        Returns:
            Equipment type or None if format invalid
        """
        try:
            parts = equipment_code.split("-")
            if len(parts) < 2:
                return None
            # Second part is the equipment type
            return parts[1].upper()
        except Exception:
            return None

    async def _get_equipment_data(self, equipment_code: str) -> dict[str, Any] | None:
        """Get equipment record from database."""
        try:
            response = self.supabase.table("equipment").select("*").eq("code", equipment_code).single().execute()
            return response.data if response.data else None
        except Exception as e:
            logger.warning(f"Could not fetch equipment {equipment_code}: {e!s}")
            return None

    async def _get_site_equipment(self, site_code: str) -> list[dict[str, Any]]:
        """Get all equipment for a site."""
        try:
            response = (
                self.supabase.table("equipment")
                .select("*, building:buildings(code)")
                .eq("building.code", site_code)
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.warning(f"Could not fetch equipment for site {site_code}: {e!s}")
            return []

    async def _prepare_features(self, equipment: dict[str, Any]) -> dict[str, Any] | None:
        """
        Prepare features for ML inference.

        Collects last 7 days of sensor data, health score, recent alerts.

        Args:
            equipment: Equipment record

        Returns:
            Feature dict for model input, or None if insufficient data
        """
        try:
            equipment_id = equipment.get("id")

            # Get last 7 days of sensor readings
            seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
            readings_response = (
                self.supabase.table("equipment_sensor_readings")
                .select("value, recorded_at")
                .eq("equipment_id", equipment_id)
                .gte("recorded_at", seven_days_ago)
                .order("timestamp", desc=True)
                .limit(1000)
                .execute()
            )

            readings = readings_response.data or []

            # Get recent alerts
            alerts_response = (
                self.supabase.table("alerts")
                .select("severity, timestamp")
                .eq("equipment_id", equipment_id)
                .gte("timestamp", seven_days_ago)
                .execute()
            )

            alerts = alerts_response.data or []

            # Aggregate features
            features = {
                "equipment_id": equipment_id,
                "equipment_type": equipment.get("type"),
                "health_score": equipment.get("health_score", 50),
                "days_in_service": self._calculate_days_in_service(equipment),
                "reading_count": len(readings),
                "recent_alert_count": len(alerts),
                "last_reading": readings[0].get("value") if readings else None,
                "reading_trend": self._calculate_trend(readings),
                "critical_alerts": sum(1 for a in alerts if a.get("severity") == "critical"),
                "warning_alerts": sum(1 for a in alerts if a.get("severity") == "warning"),
                "maintenance_needed": equipment.get("maintenance_needed", False),
                "has_recent_service": self._has_recent_service(equipment),
            }

            return features

        except Exception as e:
            logger.warning(f"Error preparing features for {equipment.get('id')}: {e!s}")
            return None

    def _calculate_days_in_service(self, equipment: dict[str, Any]) -> int:
        """Calculate days equipment has been in service."""
        try:
            install_date_str = equipment.get("install_date")
            if not install_date_str:
                return 0
            install_date = datetime.fromisoformat(install_date_str.replace("Z", "+00:00"))
            return (datetime.now(install_date.tzinfo) - install_date).days
        except Exception:
            return 0

    def _calculate_trend(self, readings: list[dict[str, Any]]) -> str | None:
        """Calculate trend from readings (improving, stable, degrading)."""
        try:
            if len(readings) < 5:
                return None

            # Compare first half vs second half
            mid = len(readings) // 2
            first_half = [r.get("value", 0) for r in readings[mid:]]
            second_half = [r.get("value", 0) for r in readings[:mid]]

            first_avg = sum(first_half) / len(first_half) if first_half else 0
            second_avg = sum(second_half) / len(second_half) if second_half else 0

            diff = second_avg - first_avg
            if abs(diff) < 5:  # Small change
                return "stable"
            elif diff > 0:
                return "improving"
            else:
                return "degrading"

        except Exception:
            return None

    def _has_recent_service(self, equipment: dict[str, Any]) -> bool:
        """Check if equipment had service in last 30 days."""
        try:
            last_service = equipment.get("last_service_date")
            if not last_service:
                return False
            last_service_dt = datetime.fromisoformat(last_service.replace("Z", "+00:00"))
            days_since = (datetime.now(last_service_dt.tzinfo) - last_service_dt).days
            return days_since <= 30
        except Exception:
            return False

    async def _run_inference(self, equipment_type: str, features: dict[str, Any], model_config) -> float | None:
        """
        Run ML model inference.

        Args:
            equipment_type: Equipment type (e.g., 'CHILLER')
            features: Input features for model
            model_config: ModelConfig from registry

        Returns:
            Confidence score (0.0-1.0) or None if inference failed
        """
        try:
            # For now, return simulated confidence based on health score
            # TODO: Load actual model files when available
            # When models are available, uncomment:
            # model = self._load_model(model_config.model_path)
            # if model is None:
            #     return None
            # prediction = model.predict([features])
            # confidence = model.predict_proba([features])

            # Simulate confidence based on health and alerts
            health_score = features.get("health_score", 50)
            alert_count = features.get("recent_alert_count", 0)
            critical_alerts = features.get("critical_alerts", 0)

            # Higher health = lower prediction confidence
            # More alerts = higher confidence
            base_confidence = 0.50
            health_factor = (100 - health_score) / 100 * 0.40  # Up to 40% boost
            alert_factor = min(alert_count / 10, 0.25)  # Up to 25% boost
            critical_factor = critical_alerts * 0.10  # 10% per critical alert

            confidence = min(0.99, max(0.20, base_confidence + health_factor + alert_factor + critical_factor))

            logger.debug(
                f"Inference {equipment_type}: health={health_score}, alerts={alert_count}, confidence={confidence:.2%}"
            )

            return confidence

        except Exception as e:
            logger.error(f"Inference failed for {equipment_type}: {e!s}")
            return None

    def _load_model(self, model_path: str | None):
        """Load model from disk with caching."""
        if not model_path:
            return None

        # Check cache
        if model_path in self._model_cache:
            return self._model_cache[model_path]

        try:
            full_path = os.path.join(MODELS_DIR, model_path)
            if not os.path.exists(full_path):
                logger.warning(f"Model file not found: {full_path}")
                return None

            model = joblib.load(full_path)
            self._model_cache[model_path] = model
            logger.info(f"Loaded model: {model_path}")
            return model

        except Exception as e:
            logger.error(f"Failed to load model {model_path}: {e!s}")
            return None


# Singleton instance
_inference_service: NiagaraMLInference | None = None


def get_ml_inference() -> NiagaraMLInference:
    """Get or create ML inference service singleton."""
    global _inference_service
    if _inference_service is None:
        _inference_service = NiagaraMLInference()
    return _inference_service
