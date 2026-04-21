"""Failure Classification API Endpoints.

This module provides REST API endpoints for failure type classification.
It integrates with the classification service to predict failure types
and provide explainability.

Also includes comprehensive prediction endpoint that combines all ML models.
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.classification_service import get_classification_service
from app.services.ml_inference import get_anomaly_service, get_lstm_service
from app.services.survival_service import SurvivalService
from app.utils.ai_provenance import attach_ai_provenance, get_ml_provenance

logger = logging.getLogger(__name__)

router = APIRouter()


# Response Models
class FailurePredictionResponse(BaseModel):
    """Response for failure type prediction."""

    equipment_id: str
    equipment_type: str
    predicted_failure: str
    confidence: float = Field(ge=0.0, le=1.0)
    all_failure_probabilities: dict[str, float]
    contributing_factors: list[dict]
    timestamp: str


class FleetFailureRisk(BaseModel):
    """Fleet-wide failure risk item."""

    equipment_id: str
    equipment_type: str
    predicted_failure: str
    confidence: float
    app_version: str | None = None
    config_checksum: str | None = None
    ai_provenance: dict | None = None


class FeatureImportanceItem(BaseModel):
    """Feature importance item."""

    feature: str
    importance: float


class ModelInfo(BaseModel):
    """Model information."""

    equipment_type: str
    model_path: str
    metadata: dict


# Endpoints
@router.get("/failure-type/{equipment_id}")
async def get_failure_type_prediction(equipment_id: str):
    """Get predicted failure type for equipment.

    Args:
        equipment_id: Equipment identifier

    Returns:
        Failure prediction with probabilities and contributing factors
    """
    try:
        service = get_classification_service()
        result = service.predict_failure_type(equipment_id)
        if isinstance(result, dict):
            return attach_ai_provenance(result, get_ml_provenance("failure-classifier-v1"))
        response_dict = result.model_dump() if hasattr(result, "model_dump") else result
        return attach_ai_provenance(response_dict, get_ml_provenance("failure-classifier-v1"))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error predicting failure type: {e}")
        raise HTTPException(status_code=500, detail=f"Prediction error: {e!s}")


@router.get("/fleet/risks", response_model=list[FleetFailureRisk])
async def get_fleet_failure_risks(min_confidence: float = Query(default=0.5, ge=0.0, le=1.0)):
    """Get failure type predictions for all equipment.

    Args:
        min_confidence: Minimum confidence threshold (default: 0.5)

    Returns:
        List of high-confidence failure predictions sorted by confidence
    """
    try:
        service = get_classification_service()
        return attach_ai_provenance(
            service.get_fleet_failure_risks(min_confidence), get_ml_provenance("failure-classifier-v1")
        )
    except Exception as e:
        logger.error(f"Error getting fleet risks: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {e!s}")


@router.get("/feature-importance/{equipment_type}", response_model=list[FeatureImportanceItem])
async def get_feature_importance(equipment_type: str, top_n: int = Query(default=20, ge=1, le=100)):
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
        raise HTTPException(status_code=500, detail=f"Error: {e!s}")


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
        raise HTTPException(status_code=500, detail=f"Error: {e!s}")


@router.get("/models", response_model=list[ModelInfo])
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
        raise HTTPException(status_code=500, detail=f"Error: {e!s}")


@router.get("/health")
async def health_check():
    """Health check for classification service.

    Returns:
        Service health status
    """
    try:
        service = get_classification_service()
        models = service.list_available_models()

        return {"status": "healthy", "n_models": len(models), "equipment_types": [m["equipment_type"] for m in models]}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}


# === Comprehensive Prediction Endpoint ===


class ComprehensivePredictionResponse(BaseModel):
    """Comprehensive prediction combining all ML models."""

    equipment_id: str
    equipment_type: str
    predictions: dict
    overall_risk: dict


@router.get("/comprehensive/{equipment_id}")
async def get_comprehensive_prediction(equipment_id: str):
    """Get all ML predictions for equipment (LSTM, Autoencoder, Survival, Classifier).

    Combines predictions from all available models:
    - LSTM: Time-series forecasting (24/48/72h)
    - Autoencoder: Anomaly detection
    - Survival: Failure probability (30/60/90 days)
    - Classifier: Failure type prediction

    Calculates overall risk score from all predictions.

    Args:
        equipment_id: Equipment identifier

    Returns:
        Comprehensive prediction with overall risk assessment
    """
    from app.database.repositories.equipment_repository import EquipmentRepository

    # Get equipment
    equipment_repo = EquipmentRepository()
    equipment = equipment_repo.get_by_id(equipment_id)

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
        raise HTTPException(status_code=404, detail="Equipment not found")

    equipment_type = equipment.get("equipment_type") if isinstance(equipment, dict) else equipment.equipment_type

    results = {"equipment_id": equipment_id, "equipment_type": equipment_type, "predictions": {}}

    # LSTM forecast
    try:
        lstm_service = get_lstm_service()
        results["predictions"]["forecast"] = lstm_service.predict(equipment_id, equipment_type)
    except Exception as e:
        logger.debug(f"LSTM prediction failed for {equipment_id}: {e}")
        results["predictions"]["forecast"] = {"error": str(e)}

    # Anomaly detection
    try:
        anomaly_service = get_anomaly_service()
        results["predictions"]["anomaly"] = anomaly_service.check_equipment(equipment_id)
    except Exception as e:
        logger.debug(f"Anomaly detection failed for {equipment_id}: {e}")
        results["predictions"]["anomaly"] = {"error": str(e)}

    # Survival analysis
    try:
        survival_service = SurvivalService()
        results["predictions"]["survival"] = survival_service.predict_equipment(equipment_id)
    except Exception as e:
        logger.debug(f"Survival analysis failed for {equipment_id}: {e}")
        results["predictions"]["survival"] = {"error": str(e)}

    # Failure classification
    try:
        classification_service = get_classification_service()
        results["predictions"]["failure_type"] = classification_service.predict_failure_type(equipment_id)
    except Exception as e:
        logger.debug(f"Classification failed for {equipment_id}: {e}")
        results["predictions"]["failure_type"] = {"error": str(e)}

    # Calculate overall risk
    results["overall_risk"] = calculate_overall_risk(results["predictions"])
    return attach_ai_provenance(results, get_ml_provenance("comprehensive-ml-ensemble-v1"))


def calculate_overall_risk(predictions: dict) -> dict:
    """Calculate overall risk from all predictions.

    Args:
        predictions: Dictionary of prediction results

    Returns:
        Overall risk assessment with score and level
    """
    risk_score = 0
    risk_factors = []

    # Anomaly detection contributes to risk
    if "anomaly" in predictions and "is_anomaly" in predictions["anomaly"] and predictions["anomaly"]["is_anomaly"]:
        risk_score += 30
        risk_factors.append("Anomalous behavior detected")

    # Survival analysis contributes
    if "survival" in predictions and "failure_probability" in predictions["survival"]:
        prob_30d = predictions["survival"]["failure_probability"]["30d"]
        risk_score += int(prob_30d * 40)
        if prob_30d > 0.3:
            risk_factors.append(f"{int(prob_30d * 100)}% failure probability in 30 days")

    # Failure type confidence contributes
    if "failure_type" in predictions and "confidence" in predictions["failure_type"]:
        conf = predictions["failure_type"]["confidence"]
        if conf > 0.7:
            risk_score += 20
            risk_factors.append(
                f"High confidence ({int(conf * 100)}%) {predictions['failure_type']['predicted_failure']} risk"
            )

    # Determine risk level
    if risk_score > 70:
        risk_level = "critical"
    elif risk_score > 40:
        risk_level = "high"
    elif risk_score > 20:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {"risk_score": min(100, risk_score), "risk_level": risk_level, "risk_factors": risk_factors}
