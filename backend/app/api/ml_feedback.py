"""
ML Feedback API Endpoints (Phase 57-02)

REST API for ML feedback loop management.
Records repair outcomes, generates training data, and tracks
prediction accuracy for continuous ML model improvement.

5 endpoints under /api/ml-feedback:
1. POST /record - Record repair feedback
2. GET /training-data - Generate training dataset
3. GET /accuracy/{model_type} - Get prediction accuracy
4. GET /equipment/{equipment_id} - Get feedback for equipment
5. GET /summary - Get overall ML feedback summary
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.models.ml_feedback import (
    MLFeedbackRecord,
    MLFeedbackSummary,
    PredictionAccuracy,
    RecordFeedbackRequest,
    TrainingDataPoint,
)
from app.services.ml_feedback_service import get_ml_feedback_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ml-feedback", tags=["ml-feedback"])


# ============================================================================
# API Endpoints
# ============================================================================


@router.post("/record", response_model=MLFeedbackRecord, status_code=201)
async def record_feedback(request: RecordFeedbackRequest) -> MLFeedbackRecord:
    """
    Record repair feedback for ML training.

    Creates a feedback record linking repair outcomes to ML predictions.
    Automatically generates training data and updates prediction accuracy.

    Request body:
    - equipment_id: Equipment identifier
    - work_order_id: Related work order ID
    - effectiveness_score: Repair effectiveness percentage (0-100)
    - repair_successful: Whether repair was successful
    - failure_type: Optional type of failure repaired
    - prediction_id: Optional ML prediction ID that triggered this repair
    """
    try:
        service = get_ml_feedback_service()
        record = service.record_repair_feedback(
            equipment_id=request.equipment_id,
            work_order_id=request.work_order_id,
            effectiveness_score=request.effectiveness_score,
            repair_successful=request.repair_successful,
            failure_type=request.failure_type,
            prediction_id=request.prediction_id,
        )
        return record

    except Exception as e:
        logger.error(f"Error recording ML feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/training-data", response_model=list[TrainingDataPoint])
async def get_training_data(
    equipment_type: str | None = Query(None, description="Filter by equipment type (e.g., chiller, ahu, fcu)"),
) -> list[TrainingDataPoint]:
    """
    Generate training dataset for ML model retraining.

    Returns training data points derived from repair outcomes,
    optionally filtered by equipment type.

    Query params:
    - equipment_type: Filter by equipment type (optional)
    """
    try:
        service = get_ml_feedback_service()
        data = service.generate_training_data(equipment_type=equipment_type)
        return data

    except Exception as e:
        logger.error(f"Error generating training data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accuracy/{model_type}", response_model=PredictionAccuracy)
async def get_prediction_accuracy(model_type: str) -> PredictionAccuracy:
    """
    Get prediction accuracy metrics for a specific ML model type.

    Evaluates all feedback records with prediction IDs and calculates
    accuracy, precision, and recall for the specified model type.

    Path params:
    - model_type: Model type (lstm, autoencoder, survival, random_forest)
    """
    valid_types = ["lstm", "autoencoder", "survival", "random_forest"]
    if model_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid model type '{model_type}'. Valid types: {valid_types}")

    try:
        service = get_ml_feedback_service()
        accuracy = service.evaluate_prediction_accuracy(model_type=model_type)
        return accuracy

    except Exception as e:
        logger.error(f"Error evaluating prediction accuracy for {model_type}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equipment/{equipment_id}", response_model=list[MLFeedbackRecord])
async def get_equipment_feedback(equipment_id: str) -> list[MLFeedbackRecord]:
    """
    Get all ML feedback records for a specific equipment.

    Returns feedback history including repair outcomes and
    prediction evaluations for the given equipment.

    Path params:
    - equipment_id: Equipment identifier (e.g., S002-CHILLER-B1-001)
    """
    try:
        service = get_ml_feedback_service()
        records = service.get_feedback_for_equipment(equipment_id=equipment_id)
        return records

    except Exception as e:
        logger.error(f"Error getting feedback for {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary", response_model=MLFeedbackSummary)
async def get_feedback_summary() -> MLFeedbackSummary:
    """
    Get overall ML feedback system summary.

    Returns aggregated statistics including total feedback records,
    prediction accuracy across all models, and training data status.
    """
    try:
        service = get_ml_feedback_service()
        summary = service.get_feedback_summary()
        return summary

    except Exception as e:
        logger.error(f"Error getting feedback summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/module-summary")
async def get_module_feedback_summary(
    site_id: str | None = Query(None, description="Optional site filter (e.g., site-002)"),
) -> dict[str, Any]:
    """Get module outcome summary for integrated cross-module feedback."""
    try:
        service = get_ml_feedback_service()
        return service.get_module_feedback_summary(site_id=site_id)
    except Exception as e:
        logger.error(f"Error getting module feedback summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))
