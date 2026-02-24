"""Load Forecast API — 15-minute building demand forecast endpoints.

Endpoints:
  GET  /api/load-forecast/{site_id}          — 96-interval forecast
  GET  /api/load-forecast/{site_id}/accuracy  — Model accuracy metrics
  POST /api/load-forecast/{site_id}/retrain   — Trigger model retraining
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.load_forecast_service import get_load_forecast_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/load-forecast", tags=["load-forecast"])


@router.get("/{site_id}")
async def get_load_forecast(
    site_id: str,
    intervals: Optional[int] = Query(96, ge=1, le=672, description="Number of 15-min intervals (max 672 = 7 days)"),
):
    """Get 15-minute building load forecast.

    Returns per-interval demand predictions with confidence bands.
    Default: 96 intervals = 24 hours.
    """
    service = get_load_forecast_service()
    forecast = service.get_forecast(site_id, intervals_ahead=intervals)

    if not forecast.intervals:
        raise HTTPException(
            status_code=404,
            detail=f"No load forecast model available for site {site_id}",
        )

    return forecast.to_dict()


@router.get("/{site_id}/accuracy")
async def get_load_forecast_accuracy(site_id: str):
    """Get model accuracy metrics (RMSE, MAE, R²)."""
    service = get_load_forecast_service()
    accuracy = service.get_accuracy(site_id)

    if not accuracy:
        raise HTTPException(
            status_code=404,
            detail=f"No accuracy metrics available for site {site_id}",
        )

    return {
        "site_id": site_id,
        "model": "gradient_boosting",
        **accuracy,
    }


@router.post("/{site_id}/retrain")
async def retrain_load_forecast(site_id: str):
    """Trigger model retraining for a site.

    Re-generates synthetic training data and fits a new GBR model.
    """
    service = get_load_forecast_service()
    success = service.retrain(site_id)

    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrain load forecast model for site {site_id}",
        )

    accuracy = service.get_accuracy(site_id)
    return {
        "site_id": site_id,
        "status": "retrained",
        "accuracy": accuracy,
    }
