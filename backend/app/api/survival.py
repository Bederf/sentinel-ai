"""
Survival Analysis API Endpoints - REST API for survival predictions.

Endpoints:
- GET /api/survival/equipment/{equipment_id} - Get survival prediction
- GET /api/survival/fleet/summary - Get fleet risk summary
- GET /api/survival/hazard-ratios - Get model hazard ratios
- GET /api/survival/summary - Get training summary
"""

import logging

from fastapi import APIRouter, HTTPException

from app.services.survival_service import get_survival_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/survival", tags=["survival"])


@router.get("/equipment/{equipment_id}")
async def get_survival_prediction(equipment_id: str) -> dict:
    """
    Get survival prediction for equipment.

    Returns:
        - failure_probability: 30/60/90 day failure probabilities
        - survival_probability: 30/60/90 day survival probabilities
        - hazard_ratio: Risk vs baseline equipment
        - remaining_useful_life_days: Estimated remaining life
        - risk_level: critical/high/medium/low
        - contributing_factors: Top risk factors

    Example:
        GET /api/survival/equipment/eqp-001
    """
    try:
        service = get_survival_service()
        result = service.predict_equipment(equipment_id)

        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting survival prediction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fleet/summary")
async def get_fleet_risk_summary() -> dict:
    """
    Get risk summary across all equipment.

    Returns:
        - total_equipment: Total number of equipment
        - risk_distribution: Count by risk level
        - high_risk_count: Number of critical+high risk equipment
        - high_risk_equipment: List of top 20 high-risk equipment

    Example:
        GET /api/survival/fleet/summary
    """
    try:
        service = get_survival_service()
        return service.get_fleet_risk_summary()
    except Exception as e:
        logger.error(f"Error getting fleet summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hazard-ratios")
async def get_hazard_ratios() -> list[dict]:
    """
    Get hazard ratios for all features from the trained model.

    Returns:
        List of features with:
        - feature: Feature name
        - hazard_ratio: Hazard ratio (HR > 1 = increases risk, HR < 1 = decreases risk)
        - coef: Coefficient value
        - p_value: Statistical significance
        - ci_lower: Lower confidence bound
        - ci_upper: Upper confidence bound

    Example:
        GET /api/survival/hazard-ratios
    """
    try:
        service = get_survival_service()
        return service.get_hazard_ratios()
    except Exception as e:
        logger.error(f"Error getting hazard ratios: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_training_summary() -> dict:
    """
    Get training data and model summary.

    Returns:
        - n_samples: Total equipment in training
        - n_events: Number of failures
        - n_censored: Number of censored (still running)
        - event_rate: Percentage of failures
        - median_duration: Median time to event
        - equipment_types: Count by type
        - model: Model info (c-index, trained_at)

    Example:
        GET /api/survival/summary
    """
    try:
        service = get_survival_service()
        summary = service.get_training_summary()

        if "error" in summary:
            raise HTTPException(status_code=404, detail=summary["error"])

        return summary
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting training summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/train")
async def train_model(penalizer: float = 0.1):
    """
    Train a new survival model.

    Args:
        penalizer: L2 regularization strength (default: 0.1)

    Returns:
        Training results including c-index and model info

    Example:
        POST /api/survival/train?penalizer=0.1
    """
    try:
        from ml.survival.train import SurvivalTrainer

        trainer = SurvivalTrainer()
        results = trainer.train(penalizer=penalizer)

        return results
    except Exception as e:
        logger.error(f"Error training model: {e}")
        raise HTTPException(status_code=500, detail=str(e))
