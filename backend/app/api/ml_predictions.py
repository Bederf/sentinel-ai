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

import logging
from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from app.utils.ai_provenance import attach_ai_provenance, attach_runtime_metadata, get_ml_provenance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ml", tags=["ml"])


# === Pydantic Models ===


class PredictionResponse(BaseModel):
    """LSTM prediction response."""

    equipment_id: str
    equipment_type: str
    predictions: dict  # {"24h": float, "48h": float, "72h": float}
    confidence: float
    timestamp: str
    model_info: dict | None = None
    explanation: dict | None = None  # Natural language explanation
    maintenance_recommendations: list[dict] | None = None  # Actionable recommendations
    error: str | None = None


class AnomalyResponse(BaseModel):
    """Anomaly detection response."""

    equipment_id: str
    equipment_type: str | None = None
    is_anomaly: bool | None = None
    anomaly_score: float | None = None
    threshold: float | None = None
    score_pct: float | None = None
    severity: str | None = None
    timestamp: str | None = None
    model_info: dict | None = None
    explanation: dict | None = None  # Natural language explanation
    recommended_actions: list[dict] | None = None  # Immediate actions
    related_faults: list[str] | None = None  # Matching fault patterns
    error: str | None = None


class TrainRequest(BaseModel):
    """Training request."""

    epochs: int = 50
    use_demo_data: bool = False
    site_id: str | None = None


class TrainResponse(BaseModel):
    """Training response."""

    status: str
    message: str
    model_id: str | None = None
    metrics: dict | None = None


class ModelInfo(BaseModel):
    """Model information."""

    model_id: str
    model_type: str
    equipment_type: str
    site_id: str | None = None
    status: str
    registered_at: str
    metrics: dict


# === LSTM Prediction Endpoints ===


@router.get("/predictions/lstm/{equipment_id}")
async def get_lstm_prediction(
    equipment_id: str,
    equipment_type: str = Query(..., description="Equipment type (chiller, ahu, generator, etc.)"),
    site_id: str | None = Query(None, description="Site ID for site-scoped model lookup"),
    include_explanation: bool = Query(False, description="Include natural language explanation"),
):
    """
    Get 24/48/72 hour predictions for an equipment.

    Uses LSTM model trained for the specific equipment type.
    """
    from app.services.explanation_service import ExplanationService
    from app.services.maintenance_recommender import MaintenanceRecommender
    from app.services.ml_inference import get_lstm_service

    service = get_lstm_service()
    result = service.predict(equipment_id, equipment_type, site_id=site_id)

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    # Generate explanation if requested
    if include_explanation:
        try:
            explanation_service = ExplanationService()
            explanation = await explanation_service.explain_prediction(
                equipment_id=equipment_id,
                equipment_type=equipment_type,
                predictions=result["predictions"],
                confidence=result["confidence"],
                include_rag_context=True,
            )
            result["explanation"] = asdict(explanation) if hasattr(explanation, "__dict__") else explanation

            # Generate maintenance recommendations
            recommender = MaintenanceRecommender()
            recommendations = await recommender.generate_recommendations(
                equipment_id=equipment_id,
                equipment_type=equipment_type,
                predictions=result["predictions"],
                confidence=result["confidence"],
            )
            result["maintenance_recommendations"] = recommendations

        except Exception as e:
            # Don't fail the prediction if explanation fails
            result["explanation"] = {"error": f"Failed to generate explanation: {e!s}"}
            result["maintenance_recommendations"] = []

    return attach_ai_provenance(result, get_ml_provenance(f"lstm-{equipment_type}-v1"))


@router.get("/predictions/trend/{equipment_id}")
async def get_prediction_trend(
    equipment_id: str,
    equipment_type: str = Query(..., description="Equipment type"),
    hours_history: int = Query(168, description="Hours of history to include"),
    site_id: str | None = Query(None, description="Site ID for site-scoped model lookup"),
    include_explanation: bool = Query(False, description="Include trend explanation"),
):
    """
    Get historical + predicted trend data for visualization.

    Returns data formatted for chart display.
    """
    from app.services.explanation_service import ExplanationService
    from app.services.ml_inference import get_lstm_service

    service = get_lstm_service()
    result = service.get_trend(equipment_id, equipment_type, hours_history, site_id=site_id)

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    # Generate explanation if requested
    if include_explanation:
        try:
            explanation_service = ExplanationService()
            explanation = await explanation_service.explain_trend(
                equipment_id=equipment_id,
                equipment_type=equipment_type,
                historical_data=result.get("historical", []),
                predictions=result.get("predictions", {}),
            )
            result["explanation"] = asdict(explanation) if hasattr(explanation, "__dict__") else explanation
        except Exception as e:
            result["explanation"] = {"error": f"Failed to generate trend explanation: {e!s}"}

    return attach_ai_provenance(result, get_ml_provenance(f"lstm-{equipment_type}-trend-v1"))


@router.post("/predictions/batch")
async def get_batch_predictions(equipment_list: list[dict]):
    """
    Get predictions for multiple equipment.

    Body: List of {"equipment_id": str, "equipment_type": str}
    """
    from app.services.ml_inference import get_lstm_service

    service = get_lstm_service()
    results = []

    for eq in equipment_list:
        result = service.predict(eq.get("equipment_id"), eq.get("equipment_type"), site_id=eq.get("site_id"))
        results.append(result)

    return attach_ai_provenance(results, get_ml_provenance("lstm-batch-predictions-v1"))


# === Anomaly Detection Endpoints ===


@router.get("/anomalies/equipment/{equipment_id}")
async def check_equipment_anomaly(
    equipment_id: str,
    equipment_type: str = Query(..., description="Equipment type"),
    site_id: str | None = Query(None, description="Site ID for site-scoped model lookup"),
    include_explanation: bool = Query(False, description="Include anomaly explanation"),
):
    """
    Check if equipment is exhibiting anomalous behavior.

    Uses autoencoder trained on normal operation data.
    High reconstruction error indicates anomaly.
    """
    from app.services.explanation_service import ExplanationService
    from app.services.ml_inference import get_anomaly_service
    from app.services.rag_service import RAGService

    service = get_anomaly_service()
    result = service.check_equipment(equipment_id, equipment_type, site_id=site_id)

    if result.get("error") and not result.get("is_anomaly"):
        raise HTTPException(status_code=400, detail=result["error"])

    # Generate explanation if requested
    if include_explanation:
        try:
            explanation_service = ExplanationService()
            rag_service = RAGService()

            # Generate anomaly explanation
            explanation = await explanation_service.explain_anomaly(
                equipment_id=equipment_id,
                equipment_type=equipment_type,
                anomaly_score=result.get("anomaly_score"),
                severity=result.get("severity"),
                include_rag_context=True,
            )
            result["explanation"] = asdict(explanation) if hasattr(explanation, "__dict__") else explanation

            # Search for related fault patterns if anomaly detected
            if result.get("is_anomaly"):
                fault_results = await rag_service.search_faults(
                    query=f"{equipment_type} anomaly {result.get('severity')}", equipment_type=equipment_type, limit=5
                )
                result["related_faults"] = [doc.get("title", "Unknown") for doc in fault_results.get("results", [])]

                # Get recommended actions from matching faults
                recommended_actions = []
                for doc in fault_results.get("results", [])[:3]:  # Top 3 faults
                    metadata = doc.get("metadata", {})
                    actions = metadata.get("recommended_actions", [])
                    recommended_actions.extend(actions)

                result["recommended_actions"] = recommended_actions

        except Exception as e:
            result["explanation"] = {"error": f"Failed to generate anomaly explanation: {e!s}"}
            result["related_faults"] = []
            result["recommended_actions"] = []

    # Auto-classify fault type when anomaly detected
    if result.get("is_anomaly"):
        try:
            from app.services.classification_service import get_classification_service

            classifier = get_classification_service()
            classification = classifier.predict_failure_type(equipment_id)
            result["fault_classification"] = {
                "predicted_failure": classification["predicted_failure"],
                "confidence": classification["confidence"],
                "all_probabilities": classification["all_failure_probabilities"],
                "contributing_factors": classification["contributing_factors"][:3],
            }
        except Exception as e:
            result["fault_classification"] = None
            logger.debug(f"Fault classification unavailable: {e}")

    return attach_ai_provenance(result, get_ml_provenance(f"autoencoder-{equipment_type}-v1"))


@router.get("/anomalies/all")
async def check_all_anomalies(limit: int = Query(20, description="Maximum results to return")):
    """
    Get anomaly status for all monitored equipment.

    Returns list sorted by anomaly score (highest first).
    """
    from app.services.ml_inference import get_anomaly_service

    service = get_anomaly_service()
    results = service.check_all_equipment()

    return attach_ai_provenance(results[:limit], get_ml_provenance("autoencoder-fleet-anomaly-v1"))


@router.get("/anomalies/alerts")
async def get_anomaly_alerts():
    """
    Get equipment currently flagged as anomalous.

    Only returns equipment where is_anomaly=True.
    """
    from app.services.ml_inference import get_anomaly_service

    service = get_anomaly_service()
    return attach_ai_provenance(service.get_anomaly_alerts(), get_ml_provenance("autoencoder-anomaly-alerts-v1"))


@router.get("/anomalies/history/{equipment_id}")
async def get_anomaly_history(
    equipment_id: str,
    equipment_type: str = Query(..., description="Equipment type"),
    days: int = Query(7, description="Days of history"),
):
    """
    Get anomaly score history for trending analysis.

    Shows how anomaly score has changed over time.
    """
    from app.services.ml_inference import get_anomaly_service

    service = get_anomaly_service()
    history = service.get_anomaly_history(equipment_id, equipment_type, days)
    if isinstance(history, dict):
        return attach_ai_provenance(history, get_ml_provenance(f"autoencoder-{equipment_type}-history-v1"))
    return attach_ai_provenance(history, get_ml_provenance(f"autoencoder-{equipment_type}-history-v1"))


# === Model Management Endpoints ===


@router.get("/models", response_model=list[ModelInfo])
async def list_models(
    model_type: str | None = Query(None, description="Filter by model type (lstm, autoencoder)"),
    equipment_type: str | None = Query(None, description="Filter by equipment type"),
    site_id: str | None = Query(None, description="Filter by site ID"),
    status: str | None = Query(None, description="Filter by status (active, inactive)"),
):
    """
    List all registered ML models.

    Can filter by model type, equipment type, and status.
    """
    from ml.registry import get_model_registry

    registry = get_model_registry()
    models = registry.list_models(model_type, equipment_type, status, site_id=site_id)

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
async def activate_model(model_id: str, site_id: str | None = Query(None, description="Site ID for scoped activation")):
    """Set a model as the active version for inference."""
    from ml.registry import get_model_registry

    registry = get_model_registry()

    try:
        registry.set_active(model_id, site_id=site_id)
        return {"status": "success", "message": f"Model {model_id} activated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/models/compare/{model_type}/{equipment_type}")
async def compare_models(
    model_type: str,
    equipment_type: str,
    site_id: str | None = Query(None, description="Filter by site ID"),
):
    """
    Compare all model versions for a specific type/equipment.

    Useful for evaluating model performance over time.
    """
    from ml.registry import get_model_registry

    registry = get_model_registry()
    return registry.get_model_comparison(model_type, equipment_type, site_id=site_id)


# === Training Endpoints ===


@router.post("/train/lstm/{equipment_type}", response_model=TrainResponse)
async def train_lstm_model(equipment_type: str, request: TrainRequest, background_tasks: BackgroundTasks):
    """
    Train a new LSTM forecasting model.

    Training runs in background. Check /models endpoint for status.
    """

    def train_task():
        from ml.lstm.train import LSTMTrainer

        trainer = LSTMTrainer(site_id=request.site_id)
        return trainer.train_equipment_type(
            equipment_type,
            epochs=request.epochs,
            use_demo_data=request.use_demo_data,
            site_id=request.site_id,
        )

    # Run synchronously in local mode (production should use a background task)
    try:
        result = train_task()
        return TrainResponse(
            status="completed",
            message=f"LSTM model trained for {equipment_type}",
            model_id=result.get("model_id"),
            metrics=result.get("metrics"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ModelReadinessResponse(BaseModel):
    """ML model training readiness for a site."""

    site_id: str
    training_enabled: bool
    ready: bool
    active_model_count: int
    equipment_types_covered: list[str]
    last_training_at: str | None
    message: str


@router.get("/model-readiness/{site_id}", response_model=ModelReadinessResponse)
async def get_model_readiness(site_id: str):
    """
    Check whether ML models are trained and ready for a site.

    A site is READY when:
    - Background training is enabled
    - At least one active ML model exists in the registry

    Returns readiness status with model counts and equipment coverage.
    """
    from app.services.site_ai_policy_service import is_site_ml_training_enabled
    from ml.registry import get_model_registry

    site_id = site_id.strip().lower()
    training_enabled = is_site_ml_training_enabled(site_id)

    if not training_enabled:
        return ModelReadinessResponse(
            site_id=site_id,
            training_enabled=False,
            ready=False,
            active_model_count=0,
            equipment_types_covered=[],
            last_training_at=None,
            message="ML training is disabled for this site.",
        )

    registry = get_model_registry()
    active_models = registry.list_models(status="active", site_id=site_id)

    covered_types = sorted({m["equipment_type"] for m in active_models if m.get("equipment_type")})

    last_training = None
    # Only count models that actually have trained_at — registry entries without
    # training timestamps are placeholders, not real models
    actually_trained = [m for m in active_models if m.get("metadata", {}).get("trained_at")]
    covered_types = sorted({m["equipment_type"] for m in actually_trained if m.get("equipment_type")})

    last_training = None
    if actually_trained:
        last_training = max(
            (m["metadata"]["trained_at"] for m in actually_trained if m["metadata"].get("trained_at")),
            default=None,
        )

    # Site is ready only when at least one model has a real trained_at timestamp
    ready = len(actually_trained) > 0

    if ready:
        message = (
            f"{len(actually_trained)} trained model(s) covering {len(covered_types)} "
            f"equipment type(s). Site is ready for advisory mode."
        )
    else:
        message = (
            f"Shadow training in progress — {len(active_models)} model entry/ies exist "
            f"but none have completed training yet. Models will be ready once "
            f"sufficient telemetry is collected."
        )

    return ModelReadinessResponse(
        site_id=site_id,
        training_enabled=True,
        ready=ready,
        active_model_count=len(active_models),
        equipment_types_covered=covered_types,
        last_training_at=last_training,
        message=message,
    )


@router.post("/train/autoencoder/{equipment_type}", response_model=TrainResponse)
async def train_autoencoder_model(equipment_type: str, request: TrainRequest, background_tasks: BackgroundTasks):
    """
    Train a new autoencoder anomaly detection model.

    Training runs in background. Check /models endpoint for status.
    """

    def train_task():
        from ml.autoencoder.train import AutoencoderTrainer

        trainer = AutoencoderTrainer(site_id=request.site_id)
        return trainer.train_equipment_type(
            equipment_type,
            epochs=request.epochs,
            use_demo_data=request.use_demo_data,
            site_id=request.site_id,
        )

    try:
        result = train_task()
        return TrainResponse(
            status="completed",
            message=f"Autoencoder trained for {equipment_type}",
            model_id=result.get("model_id"),
            metrics=result.get("metrics"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/train/classifier/{equipment_type}", response_model=TrainResponse)
async def train_classifier_model(equipment_type: str, background_tasks: BackgroundTasks):
    """Train a new Random Forest failure classifier for an equipment type."""

    def train_task():
        from ml.classifier.train import ClassifierTrainer

        trainer = ClassifierTrainer()
        return trainer.train_equipment_type(equipment_type)

    try:
        result = train_task()
        if result.get("status") == "failed":
            raise HTTPException(status_code=500, detail=result.get("error"))
        return TrainResponse(
            status="completed",
            message=f"Classifier trained for {equipment_type}",
            model_id=result.get("model_path"),
            metrics={"accuracy": result.get("accuracy"), "n_classes": result.get("n_classes")},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/train/all")
async def train_all_models(request: TrainRequest):
    """
    Train all model types for all equipment types.

    This is a long-running operation. In production, would run in background.
    """
    results = {"lstm": [], "autoencoder": [], "classifier": []}

    # Train LSTM models
    try:
        from ml.lstm.train import LSTMTrainer

        trainer = LSTMTrainer(site_id=request.site_id)
        lstm_results = trainer.train_all(epochs=request.epochs, use_demo_data=request.use_demo_data)
        results["lstm"] = lstm_results
    except Exception as e:
        results["lstm"] = [{"error": str(e)}]

    # Train autoencoder models
    try:
        from ml.autoencoder.train import AutoencoderTrainer

        trainer = AutoencoderTrainer(site_id=request.site_id)
        ae_results = trainer.train_all(epochs=request.epochs, use_demo_data=request.use_demo_data)
        results["autoencoder"] = ae_results
    except Exception as e:
        results["autoencoder"] = [{"error": str(e)}]

    # Train classifier models
    try:
        from ml.classifier.train import ClassifierTrainer

        trainer = ClassifierTrainer()
        classifier_results = trainer.train_all()
        results["classifier"] = classifier_results
    except Exception as e:
        results["classifier"] = [{"error": str(e)}]

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
    classifier_active = [m for m in active_models if m["model_type"] == "classifier"]

    return {
        "status": "healthy",
        "total_models": len(all_models),
        "active_models": len(active_models),
        "lstm_models_active": len(lstm_active),
        "autoencoder_models_active": len(ae_active),
        "classifier_models_active": len(classifier_active),
        "equipment_types_covered": list({m["equipment_type"] for m in active_models}),
    }


# === Maintenance Recommendations Endpoints ===


class MaintenanceRecommendationRequest(BaseModel):
    """Request for generating maintenance recommendations."""

    equipment_id: str
    equipment_type: str
    include_historical: bool = True
    urgency_filter: str | None = None  # 'critical', 'high', 'medium', 'low'


class MaintenanceRecommendationResponse(BaseModel):
    """Response with maintenance recommendations."""

    equipment_id: str
    equipment_type: str
    recommendations: list[dict]
    total_estimated_time: float
    total_estimated_cost: float
    priority_breakdown: dict
    timestamp: str


@router.post("/maintenance/recommendations")
async def generate_maintenance_recommendations(request: MaintenanceRecommendationRequest):
    """
    Generate maintenance recommendations for equipment.

    Combines ML predictions with RAG knowledge base and fleet experience
    to provide specific, actionable maintenance recommendations.
    """
    from app.services.maintenance_recommender import MaintenanceRecommender

    recommender = MaintenanceRecommender()

    try:
        result = await recommender.generate_recommendations(
            equipment_id=request.equipment_id,
            equipment_type=request.equipment_type,
            include_historical=request.include_historical,
            urgency_filter=request.urgency_filter,
        )

        response = MaintenanceRecommendationResponse(
            equipment_id=request.equipment_id,
            equipment_type=request.equipment_type,
            recommendations=result.get("recommendations", []),
            total_estimated_time=result.get("total_estimated_time", 0.0),
            total_estimated_cost=result.get("total_estimated_cost", 0.0),
            priority_breakdown=result.get("priority_breakdown", {}),
            timestamp=datetime.utcnow().isoformat(),
        )
        return attach_ai_provenance(
            response.model_dump(),
            get_ml_provenance(f"maintenance-recommender-{request.equipment_type}-v1"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate recommendations: {e!s}")


@router.get("/maintenance/priorities/{equipment_type}")
async def get_maintenance_priorities(equipment_type: str):
    """
    Get maintenance priority framework for equipment type.

    Returns the decision logic used to prioritize maintenance actions.
    """
    from app.services.maintenance_recommender import MaintenanceRecommender

    recommender = MaintenanceRecommender()

    try:
        framework = recommender.get_priority_framework(equipment_type)
        return attach_runtime_metadata(
            {
                "equipment_type": equipment_type,
                "priority_framework": framework,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/maintenance/history/{equipment_id}")
async def get_maintenance_history(
    equipment_id: str,
    days: int = Query(30, description="Days of history"),
    include_outcomes: bool = Query(True, description="Include action outcomes"),
):
    """
    Get historical maintenance actions and their outcomes.

    Used for continuous improvement of recommendation accuracy.
    """
    from app.services.maintenance_recommender import MaintenanceRecommender

    recommender = MaintenanceRecommender()

    try:
        history = await recommender.get_maintenance_history(
            equipment_id=equipment_id, days=days, include_outcomes=include_outcomes
        )
        return attach_runtime_metadata(
            {
                "equipment_id": equipment_id,
                "history": history,
                "total_actions": len(history),
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/maintenance/feedback")
async def submit_maintenance_feedback(
    equipment_id: str,
    recommendation_id: str,
    action_taken: str,
    outcome: str,
    actual_time_hours: float | None = None,
    actual_cost: float | None = None,
    notes: str | None = None,
):
    """
    Submit feedback on maintenance recommendations.

    Used to continuously improve recommendation accuracy based on
    actual outcomes vs predictions.
    """
    from app.services.maintenance_recommender import MaintenanceRecommender

    recommender = MaintenanceRecommender()

    try:
        await recommender.record_feedback(
            equipment_id=equipment_id,
            recommendation_id=recommendation_id,
            action_taken=action_taken,
            outcome=outcome,
            actual_time_hours=actual_time_hours,
            actual_cost=actual_cost,
            notes=notes,
        )

        return {
            "status": "success",
            "message": "Feedback recorded successfully",
            "equipment_id": equipment_id,
            "recommendation_id": recommendation_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
