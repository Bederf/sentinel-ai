"""Failure Classification API Endpoints.

This module provides REST API endpoints for failure type classification.
It integrates with the classification service to predict failure types
and provide explainability.
"""

import logging
from typing import Dict, List

from fastapi import APIRouter, HTTPException, Query

from app.services.classification_service import get_classification_service
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# Response Models
class FailurePredictionResponse(BaseModel):
    """Response for failure type prediction."""
    equipment_id: str
    equipment_type: str
    predicted_failure: str
    confidence: float = Field(ge=0.0, le=1.0)
    all_failure_probabilities: Dict[str, float]
    contributing_factors: List[Dict]
    timestamp: str


class FleetFailureRisk(BaseModel):
    """Fleet-wide failure risk item."""
    equipment_id: str
    equipment_type: str
    predicted_failure: str
    confidence: float


class FeatureImportanceItem(BaseModel):
    """Feature importance item."""
    feature: str
    importance: float


class ModelInfo(BaseModel):
    """Model information."""
    equipment_type: str
    model_path: str
    metadata: Dict


# Endpoints
@router.get("/failure-type/{equipment_id}", response_model=FailurePredictionResponse)
async def get_failure_type_prediction(equipment_id: str):
    """Get predicted failure type for equipment.

    Args:
        equipment_id: Equipment identifier

    Returns:
        Failure prediction with probabilities and contributing factors
    """
    try:
        service = get_classification_service()
        return service.predict_failure_type(equipment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error predicting failure type: {e}")
        raise HTTPException(status_code=500, detail=f"Prediction error: {str(e)}")


@router.get("/fleet/risks", response_model=List[FleetFailureRisk])
async def get_fleet_failure_risks(
    min_confidence: float = Query(default=0.5, ge=0.0, le=1.0)
):
    """Get failure type predictions for all equipment.

    Args:
        min_confidence: Minimum confidence threshold (default: 0.5)

    Returns:
        List of high-confidence failure predictions sorted by confidence
    """
    try:
        service = get_classification_service()
        return service.get_fleet_failure_risks(min_confidence)
    except Exception as e:
        logger.error(f"Error getting fleet risks: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/feature-importance/{equipment_type}", response_model=List[FeatureImportanceItem])
async def get_feature_importance(
    equipment_type: str,
    top_n: int = Query(default=20, ge=1, le=100)
):
    """Get feature importance for an equipment type.

    Args:
        equipment_type: Type of equipment (chiller, ahu, generator, fcu, ups)
        top_n: Number of top features to return (default: 20)

    Returns:
        Feature importance ranking
    """
    try:
        service = get_classification_service()
        return service.get_feature_importance(equipment_type, top_n)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting feature importance: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/models/{equipment_type}", response_model=ModelInfo)
async def get_model_info(equipment_type: str):
    """Get model information for an equipment type.

    Args:
        equipment_type: Type of equipment

    Returns:
        Model metadata
    """
    try:
        service = get_classification_service()
        return service.get_model_info(equipment_type)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting model info: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/models", response_model=List[ModelInfo])
async def list_available_models():
    """List all available classification models.

    Returns:
        List of model information
    """
    try:
        service = get_classification_service()
        return service.list_available_models()
    except Exception as e:
        logger.error(f"Error listing models: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/health")
async def health_check():
    """Health check for classification service.

    Returns:
        Service health status
    """
    try:
        service = get_classification_service()
        models = service.list_available_models()

        return {
            "status": "healthy",
            "n_models": len(models),
            "equipment_types": [m["equipment_type"] for m in models]
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }
