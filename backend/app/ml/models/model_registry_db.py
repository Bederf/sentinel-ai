"""
ML Model Registry - Database Driven

Loads equipment-to-model mappings and confidence thresholds from Supabase
instead of hardcoded values. This allows configuration changes without
redeploying code.

Provides:
- Equipment type → Model mapping (from ml_models table)
- Confidence thresholds per tier (from model_thresholds table)
- Model status tracking (active, disabled, unavailable)
- Caching for performance
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class ModelStatus(str, Enum):
    """Status of ML model availability and quality."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DEGRADED = "degraded"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"


@dataclass
class ModelConfig:
    """Configuration for a single ML model from database."""

    model_id: str
    model_type: str  # "lstm", "autoencoder", etc.
    equipment_type: str
    model_path: str
    scaler_path: Optional[str]
    r_squared_avg: Optional[float]
    status: str  # ModelStatus value
    notes: Optional[str]

    def is_available(self) -> bool:
        """Check if model is available for use."""
        return self.status in (ModelStatus.ACTIVE.value, ModelStatus.DEGRADED.value) and self.model_path


@dataclass
class ThresholdConfig:
    """Confidence thresholds for equipment type."""

    equipment_type: str
    tier2_confidence_min: float  # Advisory recommendations
    tier3_confidence_min: float  # Auto-execute recommendations
    status: str
    reason: Optional[str]

    def is_enabled(self) -> bool:
        """Check if thresholds allow recommendations."""
        return self.status == "active" and self.tier2_confidence_min < 1.0

    def meets_tier2_requirement(self, confidence: float) -> bool:
        """Check if confidence meets Tier 2 threshold."""
        return confidence >= self.tier2_confidence_min

    def meets_tier3_requirement(self, confidence: float) -> bool:
        """Check if confidence meets Tier 3 threshold."""
        return confidence >= self.tier3_confidence_min


class ModelRegistryDB:
    """
    Database-driven ML model registry.

    Loads model configurations and thresholds from Supabase on demand
    with optional caching for performance.
    """

    # Cache settings
    CACHE_TTL_SECONDS = 3600  # 1 hour
    CACHE_MODELS = True
    CACHE_THRESHOLDS = True

    def __init__(self):
        """Initialize registry with Supabase client."""
        self.supabase = get_supabase_client()
        self._models_cache: Dict[str, ModelConfig] = {}
        self._models_cache_time: Optional[datetime] = None
        self._thresholds_cache: Dict[str, ThresholdConfig] = {}
        self._thresholds_cache_time: Optional[datetime] = None

    def _is_cache_valid(self, cache_time: Optional[datetime]) -> bool:
        """Check if cache is still valid."""
        if not cache_time:
            return False
        age = (datetime.now() - cache_time).total_seconds()
        return age < self.CACHE_TTL_SECONDS

    async def get_model(self, equipment_type: str) -> Optional[ModelConfig]:
        """
        Get active model for equipment type.

        Args:
            equipment_type: Equipment type (e.g., 'chiller', 'ahu')

        Returns:
            ModelConfig if available, None otherwise
        """
        try:
            # Check cache
            if self.CACHE_MODELS and self._is_cache_valid(self._models_cache_time):
                return self._models_cache.get(equipment_type)

            # Query Supabase for active model
            response = (
                self.supabase.table("ml_models")
                .select("model_id, model_type, equipment_type, model_path, scaler_path, r_squared_avg, status, notes")
                .eq("equipment_type", equipment_type.lower())
                .eq("status", "active")
                .limit(1)
                .execute()
            )

            if not response.data:
                logger.debug(f"No active model found for {equipment_type}")
                return None

            model_data = response.data[0]
            model = ModelConfig(
                model_id=model_data["model_id"],
                model_type=model_data["model_type"],
                equipment_type=model_data["equipment_type"],
                model_path=model_data["model_path"],
                scaler_path=model_data.get("scaler_path"),
                r_squared_avg=model_data.get("r_squared_avg"),
                status=model_data["status"],
                notes=model_data.get("notes"),
            )

            # Cache result
            if self.CACHE_MODELS:
                self._models_cache[equipment_type] = model
                self._models_cache_time = datetime.now()

            logger.debug(f"Loaded model for {equipment_type}: {model.model_id}")
            return model

        except Exception as e:
            logger.error(f"Error loading model for {equipment_type}: {str(e)}")
            return None

    async def get_thresholds(self, equipment_type: str) -> Optional[ThresholdConfig]:
        """
        Get confidence thresholds for equipment type.

        Args:
            equipment_type: Equipment type (e.g., 'chiller', 'ahu')

        Returns:
            ThresholdConfig if found, None otherwise
        """
        try:
            # Check cache
            if self.CACHE_THRESHOLDS and self._is_cache_valid(self._thresholds_cache_time):
                return self._thresholds_cache.get(equipment_type)

            # Query Supabase
            response = (
                self.supabase.table("model_thresholds")
                .select("equipment_type, tier2_confidence_min, tier3_confidence_min, status, reason")
                .eq("equipment_type", equipment_type.lower())
                .limit(1)
                .execute()
            )

            if not response.data:
                logger.warning(f"No thresholds found for {equipment_type}")
                # Return safe default: no recommendations
                return ThresholdConfig(
                    equipment_type=equipment_type,
                    tier2_confidence_min=1.0,
                    tier3_confidence_min=1.0,
                    status="disabled",
                    reason="No configuration found",
                )

            threshold_data = response.data[0]
            thresholds = ThresholdConfig(
                equipment_type=threshold_data["equipment_type"],
                tier2_confidence_min=threshold_data["tier2_confidence_min"],
                tier3_confidence_min=threshold_data["tier3_confidence_min"],
                status=threshold_data["status"],
                reason=threshold_data.get("reason"),
            )

            # Cache result
            if self.CACHE_THRESHOLDS:
                self._thresholds_cache[equipment_type] = thresholds
                self._thresholds_cache_time = datetime.now()

            logger.debug(
                f"Loaded thresholds for {equipment_type}: tier2={thresholds.tier2_confidence_min}, tier3={thresholds.tier3_confidence_min}"
            )
            return thresholds

        except Exception as e:
            logger.error(f"Error loading thresholds for {equipment_type}: {str(e)}")
            # Return safe default
            return ThresholdConfig(
                equipment_type=equipment_type,
                tier2_confidence_min=1.0,
                tier3_confidence_min=1.0,
                status="disabled",
                reason=f"Error loading: {str(e)}",
            )

    async def get_threshold_value(self, equipment_type: str, tier: int = 2) -> Optional[float]:
        """
        Get confidence threshold for specific tier.

        Args:
            equipment_type: Equipment type
            tier: Tier (2 or 3)

        Returns:
            Confidence threshold (0.0-1.0) or None if error
        """
        thresholds = await self.get_thresholds(equipment_type)
        if not thresholds:
            return None

        if tier == 2:
            return thresholds.tier2_confidence_min
        elif tier == 3:
            return thresholds.tier3_confidence_min
        else:
            logger.warning(f"Unknown tier {tier}, using tier 2")
            return thresholds.tier2_confidence_min

    async def is_model_available(self, equipment_type: str) -> bool:
        """Check if model is available for equipment type."""
        model = await self.get_model(equipment_type)
        return model.is_available() if model else False

    async def is_enabled_for_recommendations(self, equipment_type: str) -> bool:
        """Check if equipment type is enabled for recommendations."""
        thresholds = await self.get_thresholds(equipment_type)
        return thresholds.is_enabled() if thresholds else False

    async def get_all_active_models(self) -> Dict[str, ModelConfig]:
        """
        Get all active models.

        Returns:
            Dict mapping equipment_type → ModelConfig
        """
        try:
            response = (
                self.supabase.table("ml_models")
                .select("model_id, model_type, equipment_type, model_path, scaler_path, r_squared_avg, status, notes")
                .eq("status", "active")
                .execute()
            )

            models = {}
            for model_data in response.data or []:
                model = ModelConfig(
                    model_id=model_data["model_id"],
                    model_type=model_data["model_type"],
                    equipment_type=model_data["equipment_type"],
                    model_path=model_data["model_path"],
                    scaler_path=model_data.get("scaler_path"),
                    r_squared_avg=model_data.get("r_squared_avg"),
                    status=model_data["status"],
                    notes=model_data.get("notes"),
                )
                models[model_data["equipment_type"]] = model

            logger.info(f"Loaded {len(models)} active models")
            return models

        except Exception as e:
            logger.error(f"Error loading all models: {str(e)}")
            return {}

    async def get_all_thresholds(self) -> Dict[str, ThresholdConfig]:
        """
        Get all threshold configurations.

        Returns:
            Dict mapping equipment_type → ThresholdConfig
        """
        try:
            response = (
                self.supabase.table("model_thresholds")
                .select("equipment_type, tier2_confidence_min, tier3_confidence_min, status, reason")
                .execute()
            )

            thresholds = {}
            for threshold_data in response.data or []:
                threshold = ThresholdConfig(
                    equipment_type=threshold_data["equipment_type"],
                    tier2_confidence_min=threshold_data["tier2_confidence_min"],
                    tier3_confidence_min=threshold_data["tier3_confidence_min"],
                    status=threshold_data["status"],
                    reason=threshold_data.get("reason"),
                )
                thresholds[threshold_data["equipment_type"]] = threshold

            logger.info(f"Loaded {len(thresholds)} threshold configurations")
            return thresholds

        except Exception as e:
            logger.error(f"Error loading all thresholds: {str(e)}")
            return {}

    def clear_cache(self):
        """Clear all caches (useful for testing or manual refresh)."""
        self._models_cache.clear()
        self._thresholds_cache.clear()
        self._models_cache_time = None
        self._thresholds_cache_time = None
        logger.info("Cleared model registry cache")

    async def get_registry_summary(self) -> Dict[str, Any]:
        """Get summary of all registered models and thresholds."""
        try:
            models = await self.get_all_active_models()
            thresholds = await self.get_all_thresholds()

            active_count = sum(1 for m in models.values() if m.status == "active")
            enabled_count = sum(1 for t in thresholds.values() if t.is_enabled())

            return {
                "total_models": len(models),
                "total_thresholds": len(thresholds),
                "active_models": active_count,
                "enabled_thresholds": enabled_count,
                "models": {
                    k: {"model_id": v.model_id, "r_squared": v.r_squared_avg, "status": v.status}
                    for k, v in models.items()
                },
                "thresholds": {
                    k: {"tier2": v.tier2_confidence_min, "tier3": v.tier3_confidence_min, "status": v.status}
                    for k, v in thresholds.items()
                },
            }

        except Exception as e:
            logger.error(f"Error getting registry summary: {str(e)}")
            return {"error": str(e)}


# Singleton instance
_registry_instance: Optional[ModelRegistryDB] = None


async def get_model_registry() -> ModelRegistryDB:
    """Get or create model registry singleton."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ModelRegistryDB()
    return _registry_instance


# Convenience functions for backward compatibility
async def get_model(equipment_type: str) -> Optional[ModelConfig]:
    """Get model configuration for equipment type."""
    registry = await get_model_registry()
    return await registry.get_model(equipment_type)


async def get_threshold(equipment_type: str, tier: int = 2) -> Optional[float]:
    """Get confidence threshold for equipment type and tier."""
    registry = await get_model_registry()
    return await registry.get_threshold_value(equipment_type, tier)


async def is_model_available(equipment_type: str) -> bool:
    """Check if model is available for equipment type."""
    registry = await get_model_registry()
    return await registry.is_model_available(equipment_type)
