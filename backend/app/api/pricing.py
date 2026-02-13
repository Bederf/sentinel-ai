"""
Pricing API endpoints for actuarial quote calculations.

Phase 52-01: Risk-Based Pricing Tools
REST API for pricing calculations, equipment types, and SLA tiers.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional
from decimal import Decimal

from typing import List
from app.models.pricing import (
    QuoteRequest,
    QuoteResponse,
    SLATier,
    WhatIfRequest,
    WhatIfResponse,
    RenewalPricingRequest,
    RenewalPricingResponse,
    PricingBenchmarkResponse,
    RenewalQuote,
    ContractComparable,
    RenegotiationOptions,
    RenegotiationAnalysis,
)
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


@router.post("/what-if", response_model=WhatIfResponse)
async def pricing_what_if(request: WhatIfRequest) -> WhatIfResponse:
    """
    Run what-if analysis for pricing scenarios.
    """
    try:
        engine = get_pricing_engine()
        response = engine.calculate_what_if(
            request.base,
            request.scenarios
        )
        return response
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"What-if analysis failed: {str(e)}"
        )


@router.post("/renewal", response_model=RenewalPricingResponse)
async def calculate_renewal_pricing(request: RenewalPricingRequest) -> RenewalPricingResponse:
    """
    Calculate renewal pricing recommendation for an existing contract.
    """
    try:
        engine = get_pricing_engine()
        return engine.calculate_renewal_pricing(request)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Renewal pricing failed: {str(e)}"
        )


@router.get("/benchmarks/{contract_id}", response_model=PricingBenchmarkResponse)
async def get_pricing_benchmarks(contract_id: str) -> PricingBenchmarkResponse:
    """
    Get benchmark pricing range for similar contracts.
    """
    try:
        engine = get_pricing_engine()
        return engine.get_benchmarks_for_contract(contract_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Benchmarking failed: {str(e)}"
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


@router.post("/quote-history")
async def store_quote_history(request: QuoteRequest, quote_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Store generated quote for history and retrieval.

    Optional enhancement for quote tracking and audit trail.
    Currently a stub - database storage would be added in future phases.
    """
    # In future: Store quote in database with timestamp
    # For now: Return success response
    quote_id = f"q-{hash(str(quote_data))}"
    return {
        "success": True,
        "quote_id": quote_id,
        "message": "Quote stored for future retrieval",
        "note": "Quote history database feature for future implementation"
    }


@router.get("/quote-history/{quote_id}")
async def retrieve_quote_history(quote_id: str) -> Dict[str, Any]:
    """
    Retrieve previously generated quote.

    Optional enhancement for quote tracking and audit trail.
    Currently a stub - database retrieval would be added in future phases.
    """
    return {
        "success": False,
        "message": "Quote history retrieval not yet implemented",
        "note": "Feature available in Phase 52-03"
    }


@router.get("/renewal/{contract_id}", response_model=RenewalQuote)
async def get_renewal_price(contract_id: str) -> RenewalQuote:
    """
    Get renewal price recommendation for an existing contract.

    Compares original quoted fee to current recommended renewal fee,
    showing drivers for change and confidence level.

    Returns:
        RenewalQuote with original vs recommended fee and change drivers
    """
    try:
        engine = get_pricing_engine()
        return engine.calculate_renewal_price(contract_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Renewal pricing calculation failed: {str(e)}"
        )


@router.get("/benchmarks-equipment/{equipment_type}")
async def get_equipment_benchmarks(
    equipment_type: str,
    sla_tier: str = Query(default="standard", description="SLA tier: basic|standard|premium|enterprise")
) -> Dict[str, Any]:
    """
    Get market comparable pricing for equipment type and SLA tier.

    Returns average, min, and max fees from similar contracts.

    Args:
        equipment_type: Type of equipment
        sla_tier: SLA tier for comparison

    Returns:
        Benchmark data with market average and sample size
    """
    if sla_tier not in [tier.value for tier in SLATier]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid SLA tier. Must be one of: {', '.join([t.value for t in SLATier])}"
        )

    try:
        engine = get_pricing_engine()
        # Get comparable contracts
        comparables = engine.get_comparable_contracts(
            equipment_types=[equipment_type],
            sla_tier=SLATier(sla_tier),
            limit=50
        )

        if not comparables:
            return {
                "equipment_type": equipment_type,
                "sla_tier": sla_tier,
                "avg_fee_zar": None,
                "min_fee_zar": None,
                "max_fee_zar": None,
                "sample_size": 0,
                "note": "No comparable contracts found"
            }

        fees = [Decimal(str(c.monthly_fee)) for c in comparables]
        avg_fee = sum(fees) / len(fees)

        return {
            "equipment_type": equipment_type,
            "sla_tier": sla_tier,
            "avg_fee_zar": float(avg_fee),
            "min_fee_zar": float(min(fees)),
            "max_fee_zar": float(max(fees)),
            "sample_size": len(comparables),
            "confidence_pct": min(100, len(comparables) * 10)  # Higher sample = higher confidence
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Benchmark query failed: {str(e)}"
        )


@router.post("/renegotiation/{contract_id}", response_model=RenegotiationAnalysis)
async def analyze_renegotiation(
    contract_id: str,
    option_type: str = Query(default=None, description="Optional: maintain|invest|expand")
) -> RenegotiationAnalysis:
    """
    Analyze renegotiation options for contract renewal.

    Returns analysis of three options:
    1. Maintain margin - Raise fee to cover increased costs
    2. Invest in maintenance - Reduce risk buffer, maintain fee
    3. Add services - Justify higher fee with expanded scope

    Returns NPV analysis for each option.

    Args:
        contract_id: Contract to analyze
        option_type: Optional filter to single option

    Returns:
        RenegotiationAnalysis with options and NPV comparison
    """
    try:
        engine = get_pricing_engine()
        return engine.calculate_renegotiation_terms(contract_id, option_type)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Renegotiation analysis failed: {str(e)}"
        )


@router.get("/win-loss-analysis")
async def get_win_loss_analysis() -> Dict[str, Any]:
    """
    Get portfolio-level win/loss statistics.

    Returns aggregate win rate, average negotiation time,
    lost reasons, and negotiation discount analysis.

    Returns:
        Win/loss metrics and opportunity analysis
    """
    try:
        # In future, this would query from pricing_history and win_loss_analysis tables
        # For now, return placeholder with structure for frontend
        return {
            "total_quotes": 0,
            "total_won": 0,
            "total_lost": 0,
            "total_pending": 0,
            "win_rate_pct": 0.0,
            "avg_negotiation_days": 0,
            "lost_reasons": {},
            "avg_discount_pct": 0.0,
            "note": "Data will populate from pricing_history and win_loss_analysis tables"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Win/loss analysis failed: {str(e)}"
        )


@router.get("/portfolio-benchmarks")
async def get_portfolio_benchmarks(
    include_details: bool = Query(default=False, description="Include detailed breakdown")
) -> Dict[str, Any]:
    """
    Compare all contracts in portfolio to market benchmarks.

    Returns list of contracts with variance from market average,
    highlighting over/underpriced contracts.

    Args:
        include_details: Include full contract details

    Returns:
        Portfolio benchmarking analysis with variance metrics
    """
    try:
        # In future, this would query portfolio_pricing_summary materialized view
        # For now, return placeholder structure for frontend
        return {
            "portfolio_size": 0,
            "above_market": [],
            "below_market": [],
            "at_market": [],
            "avg_variance_pct": 0.0,
            "top_underpriced": [],
            "top_overpriced": [],
            "market_opportunities": [],
            "note": "Data will populate from portfolio_pricing_summary view"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Portfolio benchmarking failed: {str(e)}"
        )


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
