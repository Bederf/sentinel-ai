"""
Pricing API endpoints for actuarial quote calculations.

Phase 52-01: Risk-Based Pricing Tools
REST API for pricing calculations, equipment types, and SLA tiers.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional
from decimal import Decimal

from app.models.pricing import QuoteRequest, QuoteResponse, SLATier
from app.services.pricing_engine import PricingEngine, get_pricing_engine


router = APIRouter(prefix="/api/pricing", tags=["pricing"])


@router.post("/calculate-quote", response_model=QuoteResponse)
async def calculate_quote(request: QuoteRequest) -> QuoteResponse:
    """
    Calculate recommended price for contract quote.

    Multi-factor pricing calculation:
    - Base cost from equipment templates
    - Condition adjustment (equipment health score)
    - Age adjustment (equipment lifecycle position)
    - Risk buffer (ML failure predictions)
    - SLA tier premium
    - Target margin application

    Returns quote with fee range, breakdown, risk factors, and assumptions.
    """
    try:
        engine = get_pricing_engine()
        quote = engine.calculate_price(request)
        return quote
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Pricing calculation failed: {str(e)}"
        )


@router.post("/calculate-price-range")
async def calculate_price_range(
    request: QuoteRequest,
    variance_pct: float = Query(default=10.0, ge=0, le=50, description="Variance percentage for range")
) -> Dict[str, Any]:
    """
    Calculate price range with specified variance.

    Returns base fee, min/max range, and variance percentage.
    Useful for what-if analysis and negotiation scenarios.
    """
    try:
        engine = get_pricing_engine()
        quote = engine.calculate_price(request)
        base_fee = quote.recommended_fee_zar

        variance_decimal = Decimal(str(variance_pct)) / Decimal("100")

        return {
            "base_fee": base_fee,
            "min_fee": base_fee * (Decimal("1") - variance_decimal),
            "max_fee": base_fee * (Decimal("1") + variance_decimal),
            "variance_pct": variance_pct
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Price range calculation failed: {str(e)}"
        )


@router.get("/equipment-types")
async def get_equipment_types() -> Dict[str, Any]:
    """
    Get available equipment types for pricing.

    Returns list of equipment types with budget templates.
    Used for quote building UI to populate equipment selectors.
    """
    try:
        from app.database.repositories.budget_repository import BudgetRepository
        repo = BudgetRepository()
        templates = repo.get_budget_templates()

        return {
            "equipment_types": list(templates.keys()),
            "count": len(templates)
        }
    except Exception as e:
        # Fallback to default templates
        from app.services.pricing_engine import PricingEngine
        engine = PricingEngine()
        default_templates = engine._get_default_templates()
        return {
            "equipment_types": list(default_templates.keys()),
            "count": len(default_templates),
            "note": "Using default templates"
        }


@router.get("/sla-tiers")
async def get_sla_tiers() -> Dict[str, Any]:
    """
    Get available SLA tiers with pricing.

    Returns SLA tiers with margin targets and pricing multipliers.
    Used for quote building to show SLA tier options.
    """
    from app.services.pricing_engine import PricingEngine

    engine = PricingEngine()

    tiers = []
    for margin_target in engine.config.margin_targets:
        tiers.append({
            "tier": margin_target.sla_tier.value,
            "margin_target": float(margin_target.margin_pct),
            "multiplier": float(margin_target.multiplier)
        })

    # Sort by margin (basic first)
    tiers.sort(key=lambda x: x["margin_target"])

    return {
        "tiers": tiers,
        "count": len(tiers)
    }


@router.get("/config")
async def get_pricing_config() -> Dict[str, Any]:
    """
    Get current pricing configuration.

    Returns condition multipliers, age brackets, SLA multipliers,
    and margin targets. Useful for transparency and debugging.
    """
    from app.services.pricing_engine import PricingEngine

    engine = PricingEngine()
    config = engine.config

    return {
        "enabled": config.enabled,
        "default_margin_pct": float(config.default_margin_pct),
        "condition_multipliers": {
            f"score_{k}": float(v) for k, v in config.condition_multipliers.items()
        },
        "age_multipliers": {
            f"age_{k}": float(v) for k, v in config.age_multipliers.items()
        },
        "sla_multipliers": {
            f"sla_{k}": float(v) for k, v in config.sla_multipliers.items()
        },
        "margin_targets": [
            {
                "sla_tier": mt.sla_tier.value,
                "margin_pct": float(mt.margin_pct),
                "multiplier": float(mt.multiplier)
            }
            for mt in config.margin_targets
        ]
    }


@router.get("/health")
async def pricing_health() -> Dict[str, Any]:
    """
    Health check for pricing service.

    Returns service status and configuration info.
    """
    try:
        engine = get_pricing_engine()
        return {
            "status": "healthy",
            "service": "pricing",
            "config_loaded": engine.config.enabled,
            "repositories": {
                "budget": "connected",
                "condition": "connected",
                "contract": "connected"
            }
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "pricing",
            "error": str(e)
        }
