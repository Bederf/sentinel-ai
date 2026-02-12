"""
ML Model Registry

Maps equipment types to their trained ML models with performance metrics and confidence thresholds.
Provides unified interface for model lookup, threshold validation, and status checking.

This registry is the single source of truth for all ML model information in the system.
"""

from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class ModelStatus(str, Enum):
    """Status of ML model availability and quality."""
    ACTIVE = "active"  # Model performing well, use normally
    DEGRADED = "degraded"  # Model underperforming, require higher threshold
    UNAVAILABLE = "unavailable"  # Model not available, recommendations disabled
    DISABLED = "disabled"  # Model explicitly disabled (insufficient data)


@dataclass
class ModelConfig:
    """Configuration for a single ML model."""
    equipment_type: str
    model_path: Optional[str]  # e.g., "LSTM_CHILLER_v3.pkl" or None
    r_squared: Optional[float]  # Model R² score (0.0-1.0) or None
    tier2_threshold: float  # Minimum confidence for Tier 2 (advisory) recommendations
    tier3_threshold: float  # Minimum confidence for Tier 3 (auto-execute) recommendations
    status: ModelStatus
    version: str = "1.0"
    notes: str = ""

    def is_available(self) -> bool:
        """Check if model is available for use."""
        return self.status in (ModelStatus.ACTIVE, ModelStatus.DEGRADED) and self.model_path is not None

    def meets_tier2_requirement(self, confidence: float) -> bool:
        """Check if confidence meets Tier 2 threshold."""
        return confidence >= self.tier2_threshold

    def meets_tier3_requirement(self, confidence: float) -> bool:
        """Check if confidence meets Tier 3 threshold."""
        return confidence >= self.tier3_threshold


class ModelRegistry:
    """
    Central registry of all ML models used in the system.

    Provides:
    - Equipment type → model mapping
    - Confidence threshold enforcement
    - Model status and metadata
    """

    # Equipment type → Model configuration
    _REGISTRY: Dict[str, ModelConfig] = {
        "CHILLER": ModelConfig(
            equipment_type="CHILLER",
            model_path="LSTM_CHILLER_v3.pkl",
            r_squared=0.89,
            tier2_threshold=0.70,
            tier3_threshold=0.85,
            status=ModelStatus.ACTIVE,
            version="3.0",
            notes="Primary HVAC prediction model. High confidence."
        ),
        "AHU": ModelConfig(
            equipment_type="AHU",
            model_path="LSTM_AHU_v2.pkl",
            r_squared=0.82,
            tier2_threshold=0.70,
            tier3_threshold=0.85,
            status=ModelStatus.ACTIVE,
            version="2.0",
            notes="Air handling unit prediction model."
        ),
        "FCU": ModelConfig(
            equipment_type="FCU",
            model_path="LSTM_FCU_v2.pkl",
            r_squared=0.78,
            tier2_threshold=0.70,
            tier3_threshold=0.85,
            status=ModelStatus.ACTIVE,
            version="2.0",
            notes="Fan coil unit prediction model."
        ),
        "VAV": ModelConfig(
            equipment_type="VAV",
            model_path="LSTM_VAV_v2.pkl",
            r_squared=0.317,  # CRITICAL: Below acceptable threshold
            tier2_threshold=1.0,  # Impossible to meet (effectively disabled)
            tier3_threshold=1.0,
            status=ModelStatus.DISABLED,
            version="2.0",
            notes="VAV model disabled (Phase 68-03): R²=0.317 (poor). "
                  "No VAV equipment in current database for retraining. "
                  "Defer retraining to Phase 69 when equipment available."
        ),
        "GENERATOR": ModelConfig(
            equipment_type="GENERATOR",
            model_path="LSTM_GENERATOR_v1.pkl",
            r_squared=0.371,  # Below acceptable, but less critical than VAV
            tier2_threshold=1.0,  # Impossible to meet (effectively disabled)
            tier3_threshold=1.0,
            status=ModelStatus.DISABLED,
            version="1.0",
            notes="Generator model disabled (Phase 68-03): R²=0.371 (poor). "
                  "No Generator equipment in current database for retraining. "
                  "Defer retraining to Phase 69 when equipment available."
        ),
        "UPS": ModelConfig(
            equipment_type="UPS",
            model_path=None,  # Not yet trained
            r_squared=None,
            tier2_threshold=1.0,  # Impossible to meet (effectively disabled)
            tier3_threshold=1.0,
            status=ModelStatus.UNAVAILABLE,
            version="0.0",
            notes="UPS model not yet developed. Recommendations disabled."
        ),
    }

    @classmethod
    def get_model(cls, equipment_type: str) -> Optional[ModelConfig]:
        """
        Get model configuration for equipment type.

        Args:
            equipment_type: Type of equipment (e.g., 'CHILLER', 'VAV')

        Returns:
            ModelConfig if available, None otherwise
        """
        return cls._REGISTRY.get(equipment_type.upper())

    @classmethod
    def get_threshold(cls, equipment_type: str, tier: int) -> Optional[float]:
        """
        Get confidence threshold for equipment type and tier.

        Args:
            equipment_type: Type of equipment
            tier: Capability tier (2=advisory, 3=auto-execute)

        Returns:
            Minimum confidence threshold (0.0-1.0) or None if model unavailable
        """
        config = cls.get_model(equipment_type)
        if not config:
            return None

        if tier == 2:
            return config.tier2_threshold
        elif tier == 3:
            return config.tier3_threshold
        else:
            logger.warning(f"Unknown tier {tier}, using Tier 2 threshold")
            return config.tier2_threshold

    @classmethod
    def get_status(cls, equipment_type: str) -> ModelStatus:
        """
        Get status of model for equipment type.

        Args:
            equipment_type: Type of equipment

        Returns:
            ModelStatus (ACTIVE, DEGRADED, UNAVAILABLE, DISABLED)
        """
        config = cls.get_model(equipment_type)
        return config.status if config else ModelStatus.UNAVAILABLE

    @classmethod
    def is_model_available(cls, equipment_type: str) -> bool:
        """
        Check if model is available for use.

        Args:
            equipment_type: Type of equipment

        Returns:
            True if model exists and is not disabled/unavailable
        """
        config = cls.get_model(equipment_type)
        return config.is_available() if config else False

    @classmethod
    def get_degraded_models(cls) -> Dict[str, ModelConfig]:
        """
        Get all degraded models needing retraining.

        Returns:
            Dict of equipment_type → ModelConfig for degraded models
        """
        return {
            eq_type: config
            for eq_type, config in cls._REGISTRY.items()
            if config.status == ModelStatus.DEGRADED
        }

    @classmethod
    def get_all_models(cls) -> Dict[str, ModelConfig]:
        """Get all registered models."""
        return cls._REGISTRY.copy()

    @classmethod
    def update_model_status(
        cls,
        equipment_type: str,
        r_squared: float,
        status: ModelStatus,
        notes: str = ""
    ) -> bool:
        """
        Update model performance metrics and status.

        Used when retraining models with new data.

        Args:
            equipment_type: Type of equipment
            r_squared: New R² score
            status: New status
            notes: Optional update notes

        Returns:
            True if updated, False if equipment type not found
        """
        if equipment_type not in cls._REGISTRY:
            logger.error(f"Equipment type {equipment_type} not in registry")
            return False

        config = cls._REGISTRY[equipment_type]
        config.r_squared = r_squared
        config.status = status
        if notes:
            config.notes = notes

        logger.info(
            f"Updated {equipment_type} model: R²={r_squared:.3f}, "
            f"status={status.value}, notes={notes}"
        )
        return True

    @classmethod
    def get_registry_summary(cls) -> Dict[str, Any]:
        """
        Get summary of all registered models.

        Returns:
            Dict with model counts and status breakdown
        """
        models = cls._REGISTRY.values()
        return {
            "total_models": len(models),
            "active": sum(1 for m in models if m.status == ModelStatus.ACTIVE),
            "degraded": sum(1 for m in models if m.status == ModelStatus.DEGRADED),
            "unavailable": sum(1 for m in models if m.status == ModelStatus.UNAVAILABLE),
            "disabled": sum(1 for m in models if m.status == ModelStatus.DISABLED),
        }


# Export convenience functions
def get_model(equipment_type: str) -> Optional[ModelConfig]:
    """Get model configuration for equipment type."""
    return ModelRegistry.get_model(equipment_type)


def get_threshold(equipment_type: str, tier: int = 2) -> Optional[float]:
    """Get confidence threshold for equipment type and tier."""
    return ModelRegistry.get_threshold(equipment_type, tier)


def is_model_available(equipment_type: str) -> bool:
    """Check if model is available for use."""
    return ModelRegistry.is_model_available(equipment_type)
