"""
ML Predictions API - REST endpoints for LSTM forecasting and anomaly detection.

Endpoints:
- GET /api/ml/predictions/lstm/{equipment_id} - Get 24/48/72h predictions
- GET /api/ml/predictions/trend/{equipment_id} - Get historical + predicted trend
- GET /api/ml/anomalies/equipment/{equipment_id} - Check single equipment
- GET /api/ml/anomalies/all - Check all equipment
- GET /api/ml/anomalies/alerts - Get active anomaly alerts
- GET /api/ml/anomalies/history/{equipment_id} - Get anomaly score history
- GET /api/ml/models - List available models
- POST /api/ml/train/{model_type}/{equipment_type} - Train new model
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(prefix="/api/ml", tags=["ml"])


# === Pydantic Models ===

class PredictionResponse(BaseModel):
    """LSTM prediction response."""
    equipment_id: str
    equipment_type: str
    predictions: dict  # {"24h": float, "48h": float, "72h": float}
    confidence: float
    timestamp: str
    model_info: Optional[dict] = None
    error: Optional[str] = None


class AnomalyResponse(BaseModel):
    """Anomaly detection response."""
    equipment_id: str
    equipment_type: Optional[str] = None
    is_anomaly: Optional[bool] = None
    anomaly_score: Optional[float] = None
    threshold: Optional[float] = None
    score_pct: Optional[float] = None
    severity: Optional[str] = None
    timestamp: Optional[str] = None
    model_info: Optional[dict] = None
    error: Optional[str] = None


class TrainRequest(BaseModel):
    """Training request."""
    epochs: int = 50
    use_demo_data: bool = True


class TrainResponse(BaseModel):
    """Training response."""
    status: str
    message: str
    model_id: Optional[str] = None
    metrics: Optional[dict] = None


class ModelInfo(BaseModel):
    """Model information."""
    model_id: str
    model_type: str
    equipment_type: str
    status: str
    registered_at: str
    metrics: dict


# === LSTM Prediction Endpoints ===

@router.get("/predictions/lstm/{equipment_id}", response_model=PredictionResponse)
async def get_lstm_prediction(
    equipment_id: str,
    equipment_type: str = Query(..., description="Equipment type (chiller, ahu, generator, etc.)")
):
    """
    Get 24/48/72 hour predictions for an equipment.

    Uses LSTM model trained for the specific equipment type.
    """
    from app.services.ml_inference import get_lstm_service

    service = get_lstm_service()
    result = service.predict(equipment_id, equipment_type)

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@router.get("/predictions/trend/{equipment_id}")
async def get_prediction_trend(
    equipment_id: str,
    equipment_type: str = Query(..., description="Equipment type"),
    hours_history: int = Query(168, description="Hours of history to include")
):
    """
    Get historical + predicted trend data for visualization.

    Returns data formatted for chart display.
    """
    from app.services.ml_inference import get_lstm_service

    service = get_lstm_service()
    result = service.get_trend(equipment_id, equipment_type, hours_history)

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@router.post("/predictions/batch")
async def get_batch_predictions(
    equipment_list: List[dict]
):
    """
    Get predictions for multiple equipment.

    Body: List of {"equipment_id": str, "equipment_type": str}
    """
    from app.services.ml_inference import get_lstm_service

    service = get_lstm_service()
    results = []

    for eq in equipment_list:
        result = service.predict(
            eq.get("equipment_id"),
            eq.get("equipment_type")
        )
        results.append(result)

    return results


# === Anomaly Detection Endpoints ===

@router.get("/anomalies/equipment/{equipment_id}", response_model=AnomalyResponse)
async def check_equipment_anomaly(
    equipment_id: str,
    equipment_type: str = Query(..., description="Equipment type")
):
    """
    Check if equipment is exhibiting anomalous behavior.

    Uses autoencoder trained on normal operation data.
    High reconstruction error indicates anomaly.
    """
    from app.services.ml_inference import get_anomaly_service

    service = get_anomaly_service()
    result = service.check_equipment(equipment_id, equipment_type)

    if result.get("error") and not result.get("is_anomaly"):
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@router.get("/anomalies/all")
async def check_all_anomalies(
    limit: int = Query(20, description="Maximum results to return")
):
    """
    Get anomaly status for all monitored equipment.

    Returns list sorted by anomaly score (highest first).
    """
    from app.services.ml_inference import get_anomaly_service

    service = get_anomaly_service()
    results = service.check_all_equipment()

    return results[:limit]


@router.get("/anomalies/alerts")
async def get_anomaly_alerts():
    """
    Get equipment currently flagged as anomalous.

    Only returns equipment where is_anomaly=True.
    """
    from app.services.ml_inference import get_anomaly_service

    service = get_anomaly_service()
    return service.get_anomaly_alerts()


@router.get("/anomalies/history/{equipment_id}")
async def get_anomaly_history(
    equipment_id: str,
    equipment_type: str = Query(..., description="Equipment type"),
    days: int = Query(7, description="Days of history")
):
    """
    Get anomaly score history for trending analysis.

    Shows how anomaly score has changed over time.
    """
    from app.services.ml_inference import get_anomaly_service

    service = get_anomaly_service()
    return service.get_anomaly_history(equipment_id, equipment_type, days)


# === Model Management Endpoints ===

@router.get("/models", response_model=List[ModelInfo])
async def list_models(
    model_type: Optional[str] = Query(None, description="Filter by model type (lstm, autoencoder)"),
    equipment_type: Optional[str] = Query(None, description="Filter by equipment type"),
    status: Optional[str] = Query(None, description="Filter by status (active, inactive)")
):
    """
    List all registered ML models.

    Can filter by model type, equipment type, and status.
    """
    from ml.registry import get_model_registry

    registry = get_model_registry()
    models = registry.list_models(model_type, equipment_type, status)

    return models


@router.get("/models/{model_id}")
async def get_model(model_id: str):
    """Get details for a specific model."""
    from ml.registry import get_model_registry

    registry = get_model_registry()
    model = registry.get_model(model_id)

    if not model:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    return model


@router.post("/models/{model_id}/activate")
async def activate_model(model_id: str):
    """Set a model as the active version for inference."""
    from ml.registry import get_model_registry

    registry = get_model_registry()

    try:
        registry.set_active(model_id)
        return {"status": "success", "message": f"Model {model_id} activated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/models/compare/{model_type}/{equipment_type}")
async def compare_models(model_type: str, equipment_type: str):
    """
    Compare all model versions for a specific type/equipment.

    Useful for evaluating model performance over time.
    """
    from ml.registry import get_model_registry

    registry = get_model_registry()
    return registry.get_model_comparison(model_type, equipment_type)


# === Training Endpoints ===

@router.post("/train/lstm/{equipment_type}", response_model=TrainResponse)
async def train_lstm_model(
    equipment_type: str,
    request: TrainRequest,
    background_tasks: BackgroundTasks
):
    """
    Train a new LSTM forecasting model.

    Training runs in background. Check /models endpoint for status.
    """
    def train_task():
        from ml.lstm.train import LSTMTrainer
        trainer = LSTMTrainer()
        return trainer.train_equipment_type(
            equipment_type,
            epochs=request.epochs,
            use_demo_data=request.use_demo_data
        )

    # For demo, run synchronously (in production, use background task)
    try:
        result = train_task()
        return TrainResponse(
            status="completed",
            message=f"LSTM model trained for {equipment_type}",
            model_id=result.get("model_id"),
            metrics=result.get("metrics")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/train/autoencoder/{equipment_type}", response_model=TrainResponse)
async def train_autoencoder_model(
    equipment_type: str,
    request: TrainRequest,
    background_tasks: BackgroundTasks
):
    """
    Train a new autoencoder anomaly detection model.

    Training runs in background. Check /models endpoint for status.
    """
    def train_task():
        from ml.autoencoder.train import AutoencoderTrainer
        trainer = AutoencoderTrainer()
        return trainer.train_equipment_type(
            equipment_type,
            epochs=request.epochs,
            use_demo_data=request.use_demo_data
        )

    try:
        result = train_task()
        return TrainResponse(
            status="completed",
            message=f"Autoencoder trained for {equipment_type}",
            model_id=result.get("model_id"),
            metrics=result.get("metrics")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/train/all")
async def train_all_models(
    request: TrainRequest
):
    """
    Train all model types for all equipment types.

    This is a long-running operation. In production, would run in background.
    """
    results = {
        "lstm": [],
        "autoencoder": []
    }

    # Train LSTM models
    try:
        from ml.lstm.train import LSTMTrainer
        trainer = LSTMTrainer()
        lstm_results = trainer.train_all(
            epochs=request.epochs,
            use_demo_data=request.use_demo_data
        )
        results["lstm"] = lstm_results
    except Exception as e:
        results["lstm"] = [{"error": str(e)}]

    # Train autoencoder models
    try:
        from ml.autoencoder.train import AutoencoderTrainer
        trainer = AutoencoderTrainer()
        ae_results = trainer.train_all(
            epochs=request.epochs,
            use_demo_data=request.use_demo_data
        )
        results["autoencoder"] = ae_results
    except Exception as e:
        results["autoencoder"] = [{"error": str(e)}]

    return results


# === Health Check ===

@router.get("/health")
async def ml_health_check():
    """Check ML service health and model availability."""
    from ml.registry import get_model_registry

    registry = get_model_registry()

    # Count models by type
    all_models = registry.list_models()
    active_models = registry.list_models(status="active")

    lstm_active = [m for m in active_models if m["model_type"] == "lstm"]
    ae_active = [m for m in active_models if m["model_type"] == "autoencoder"]

    return {
        "status": "healthy",
        "total_models": len(all_models),
        "active_models": len(active_models),
        "lstm_models_active": len(lstm_active),
        "autoencoder_models_active": len(ae_active),
        "equipment_types_covered": list(set(m["equipment_type"] for m in active_models))
    }
