"""
AI Usage & Cost Tracking API
==============================
Endpoints for monitoring AI API spend across all providers.
"""

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.middleware.auth_middleware import require_role
from app.models.auth import AuthContext, SentinelRole
from app.services.ai_usage_tracker import usage_tracker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai-usage", tags=["ai-usage"])


class ExchangeRateUpdate(BaseModel):
    usd_zar: float


@router.get("/summary")
async def get_usage_summary(
    days: int = Query(30, ge=1, le=365),
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN, SentinelRole.OPERATOR)),
) -> dict:
    """Get AI usage summary for the last N days.

    Returns total cost (USD + ZAR), breakdown by provider and model,
    and daily cost time series.
    """
    return usage_tracker.get_summary(days=days)


@router.get("/today")
async def get_today_usage(
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN, SentinelRole.OPERATOR)),
) -> dict:
    """Get today's AI usage in real-time."""
    return usage_tracker.get_today()


@router.put("/exchange-rate")
async def update_exchange_rate(
    body: ExchangeRateUpdate,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict:
    """Update the USD/ZAR exchange rate for cost calculations."""
    if body.usd_zar <= 0:
        return {"error": "Rate must be positive"}
    usage_tracker.set_exchange_rate(body.usd_zar)
    logger.info(f"USD/ZAR rate updated to {body.usd_zar}")
    return {"status": "updated", "usd_zar": body.usd_zar}


@router.post("/flush")
async def flush_usage(
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict:
    """Force flush usage data to disk."""
    usage_tracker.flush()
    return {"status": "flushed"}
