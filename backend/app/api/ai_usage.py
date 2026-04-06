"""
Service Usage & Cost Tracking API
===================================
Endpoints for monitoring spend across all external services:
AI providers, messaging (WhatsApp, BulkSMS, Telegram), and
unit-based services (ElevenLabs TTS, EskomSePush).
"""

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.middleware.auth_middleware import require_role
from app.models.auth import AuthContext, SentinelRole
from app.services.ai_usage_tracker import usage_tracker
from app.services.site_ai_policy_service import get_site_ai_policy

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai-usage", tags=["ai-usage"])


class ExchangeRateUpdate(BaseModel):
    usd_zar: float


@router.get("/summary")
async def get_usage_summary(
    days: int = Query(30, ge=1, le=365),
    site_id: str | None = Query(None, description="Optional site scope"),
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN, SentinelRole.OPERATOR)),
) -> dict:
    """Get AI usage summary for the last N days.

    Returns total cost (USD + ZAR), breakdown by provider and model,
    and daily cost time series.
    """
    summary = usage_tracker.get_summary(days=days, site_id=site_id)
    if site_id:
        policy = get_site_ai_policy(site_id)
        budget_zar = float(policy.get("monthly_budget_zar", 0.0) or 0.0)
        spent_zar = float(summary.get("total_cost_zar", 0.0))
        summary["budget"] = {
            "monthly_budget_zar": budget_zar,
            "spent_zar": round(spent_zar, 2),
            "remaining_zar": round(max(0.0, budget_zar - spent_zar), 2),
            "hard_cap_enforced": bool(policy.get("hard_cap_enforced", False)),
            "over_budget": budget_zar > 0 and spent_zar >= budget_zar,
        }
    return summary


@router.get("/today")
async def get_today_usage(
    site_id: str | None = Query(None, description="Optional site scope"),
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN, SentinelRole.OPERATOR)),
) -> dict:
    """Get today's AI usage in real-time."""
    today = usage_tracker.get_today(site_id=site_id)
    if site_id:
        policy = get_site_ai_policy(site_id)
        today["budget"] = {
            "monthly_budget_zar": float(policy.get("monthly_budget_zar", 0.0) or 0.0),
            "hard_cap_enforced": bool(policy.get("hard_cap_enforced", False)),
        }
    return today


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
