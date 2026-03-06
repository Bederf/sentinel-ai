"""
Pricing models for actuarial pricing engine.

Phase 52-01: Risk-Based Pricing Tools
Models for equipment condition, age, ML risk buffers, SLA tiers, and quote calculations.
"""

from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from decimal import Decimal
from datetime import date


class SLATier(str, Enum):
    """Service Level Agreement tiers with different response times and uptime targets."""

    basic = "basic"  # 99% uptime, 24hr response
    standard = "standard"  # 99.5% uptime, 8hr response
    premium = "premium"  # 99.9% uptime, 4hr response
    enterprise = "enterprise"  # 99.95% uptime, 2hr response


class ConditionFactor(BaseModel):
    """Equipment condition assessment factor for pricing adjustments."""

    equipment_id: str
    overall_score: int = Field(..., ge=1, le=5, description="Condition score 1-5 from assessment")
    age_years: float = Field(..., ge=0, description="Equipment age in years")
    condition_multiplier: Decimal = Field(default=Decimal("1.0"), description="1.0-2.0 based on score")
    age_multiplier: Decimal = Field(default=Decimal("1.0"), description="1.0-1.5 based on age")


class RiskBuffer(BaseModel):
    """ML failure prediction risk buffer for pricing."""

    equipment_id: str
    failure_probability: Decimal = Field(
        ..., ge=Decimal("0"), le=Decimal("1"), description="Failure probability from ML (0-1)"
    )
    health_score: int = Field(..., ge=0, le=100, description="Health score 0-100")
    risk_buffer_pct: Decimal = Field(
        default=Decimal("0"), ge=Decimal("0"), le=Decimal("50"), description="Risk buffer percentage 0-50%"
    )


class PricingCalculation(BaseModel):
    """Complete pricing calculation with all adjustments and breakdowns."""

    contract_id: Optional[str] = None
    site_id: str
    equipment_list: List[str]
    sla_tier: SLATier

    # Base costs
    total_base_cost_zar: Decimal = Field(..., description="Base cost from templates")

    # Adjustments
    condition_adjustment_zar: Decimal = Field(default=Decimal("0"), description="Condition-based adjustment")
    age_adjustment_zar: Decimal = Field(default=Decimal("0"), description="Age-based adjustment")
    risk_buffer_zar: Decimal = Field(default=Decimal("0"), description="ML risk buffer adjustment")
    sla_adjustment_zar: Decimal = Field(default=Decimal("0"), description="SLA tier premium adjustment")

    # Margin
    target_margin_pct: Decimal = Field(..., ge=Decimal("0"), le=Decimal("100"), description="Target margin percentage")
    margin_amount_zar: Decimal = Field(default=Decimal("0"), description="Margin amount in ZAR")

    # Final
    recommended_monthly_fee_zar: Decimal = Field(..., description="Recommended monthly fee")
    confidence_level: str = Field(..., description="Confidence: high, medium, low")

    # Breakdown
    cost_breakdown: Dict[str, Any] = Field(default_factory=dict, description="Detailed cost breakdown")


class QuoteRequest(BaseModel):
    """Request for pricing quote calculation."""

    site_id: str
    equipment_codes: List[str] = Field(..., min_length=1, description="List of equipment codes to quote")
    sla_tier: SLATier
    contract_months: int = Field(default=12, ge=1, le=60, description="Contract duration in months")
    include_benchmarks: bool = Field(default=True, description="Include market benchmark comparison")


class QuoteResponse(BaseModel):
    """Response from pricing quote calculation."""

    request_id: str
    recommended_fee_zar: Decimal = Field(..., description="Recommended monthly fee")
    fee_range_zar: Dict[str, Decimal] = Field(..., description="Min, target, max fee range")
    cost_breakdown: Dict[str, Decimal] = Field(..., description="Cost component breakdown")
    risk_factors: List[str] = Field(default_factory=list, description="Identified risk factors")
    assumptions: List[str] = Field(default_factory=list, description="Quote assumptions")
    market_comparison: Optional[Dict[str, Any]] = Field(None, description="Market benchmark data")
    valid_until: date = Field(..., description="Quote validity date")

    # Optional fields for database storage and tracking
    quote_id: Optional[str] = Field(None, description="UUID for quote tracking")
    company_name: Optional[str] = Field(None, description="Client company name")
    created_by: Optional[str] = Field(None, description="Sales person or technician who created quote")
    status: Optional[str] = Field(default="draft", description="Quote status: draft, sent, accepted, rejected")


class WhatIfScenario(BaseModel):
    """Scenario override for pricing what-if analysis."""

    name: str
    sla_tier: Optional[SLATier] = None
    add_equipment_codes: List[str] = Field(default_factory=list)
    condition_score_delta: int = Field(default=0, ge=-4, le=4, description="Adjust condition score by +/-")
    risk_buffer_multiplier: Decimal = Field(default=Decimal("1.0"), ge=Decimal("0.5"), le=Decimal("2.0"))
    target_margin_pct: Optional[Decimal] = Field(default=None, ge=Decimal("0"), le=Decimal("100"))


class WhatIfRequest(BaseModel):
    """Request containing base quote and scenarios."""

    base: QuoteRequest
    scenarios: List[WhatIfScenario] = Field(default_factory=list)


class WhatIfScenarioResult(BaseModel):
    """Result for a what-if scenario."""

    name: str
    recommended_fee_zar: Decimal
    delta_zar: Decimal
    delta_pct: Decimal
    cost_breakdown: Dict[str, Decimal]
    risk_factors: List[str]
    assumptions: List[str]


class WhatIfResponse(BaseModel):
    """Response for what-if analysis."""

    base_quote: QuoteResponse
    scenarios: List[WhatIfScenarioResult]


class RenewalPricingRequest(BaseModel):
    """Request for renewal pricing recommendation."""

    contract_id: str
    year: int = Field(..., ge=2000, le=2100)
    sla_tier: Optional[SLATier] = None


class RenewalPricingResponse(BaseModel):
    """Renewal pricing recommendation response."""

    contract_id: str
    year: int
    current_monthly_fee_zar: Decimal
    actual_cost_monthly_avg_zar: Decimal
    target_margin_pct: Decimal
    recommended_monthly_fee_zar: Decimal
    delta_zar: Decimal
    delta_pct: Decimal
    notes: List[str] = Field(default_factory=list)


class PricingBenchmarkResponse(BaseModel):
    """Benchmarking response for similar contracts."""

    contract_id: str
    similar_contracts: int
    average_monthly_fee_zar: Decimal
    min_monthly_fee_zar: Decimal
    max_monthly_fee_zar: Decimal


class EquipmentTypePricing(BaseModel):
    """Equipment-type specific pricing template data."""

    equipment_type: str
    monthly_base_cost: Decimal
    typical_monthly_breakdown: Dict[str, Decimal]
    condition_impact: bool = True
    age_impact: bool = True
    ml_risk_applicable: bool = True


class MarginTarget(BaseModel):
    """Target margin settings by SLA tier."""

    sla_tier: SLATier
    margin_pct: Decimal
    multiplier: Decimal = Field(..., description="SLA premium multiplier")


class PricingConfig(BaseModel):
    """Global pricing configuration."""

    enabled: bool = True
    default_margin_pct: Decimal = Decimal("25")
    condition_multipliers: Dict[int, Decimal] = Field(
        default_factory=lambda: {
            5: Decimal("1.0"),  # Excellent - no adjustment
            4: Decimal("1.25"),  # Good
            3: Decimal("1.5"),  # Fair
            2: Decimal("1.75"),  # Poor
            1: Decimal("2.0"),  # Critical
        }
    )
    age_multipliers: Dict[str, Decimal] = Field(
        default_factory=lambda: {
            "0-5": Decimal("1.0"),
            "5-10": Decimal("1.1"),
            "10-15": Decimal("1.2"),
            "15-20": Decimal("1.3"),
            "20+": Decimal("1.5"),
        }
    )
    sla_multipliers: Dict[str, Decimal] = Field(
        default_factory=lambda: {
            "basic": Decimal("1.0"),
            "standard": Decimal("1.15"),
            "premium": Decimal("1.3"),
            "enterprise": Decimal("1.5"),
        }
    )
    margin_targets: List[MarginTarget] = Field(
        default_factory=lambda: [
            MarginTarget(sla_tier=SLATier.basic, margin_pct=Decimal("20"), multiplier=Decimal("1.0")),
            MarginTarget(sla_tier=SLATier.standard, margin_pct=Decimal("25"), multiplier=Decimal("1.15")),
            MarginTarget(sla_tier=SLATier.premium, margin_pct=Decimal("30"), multiplier=Decimal("1.3")),
            MarginTarget(sla_tier=SLATier.enterprise, margin_pct=Decimal("35"), multiplier=Decimal("1.5")),
        ]
    )


class RenewalQuote(BaseModel):
    """Renewal quote with fee recommendations and drivers."""

    original_monthly_fee: Decimal
    recommended_monthly_fee: Decimal
    fee_change_pct: Decimal
    drivers: List[str] = Field(default_factory=list, description="Factors driving price change")
    confidence: str = Field(..., description="Confidence level: high, medium, low")
    assumptions: List[str] = Field(default_factory=list, description="Key assumptions for renewal")


class ContractComparable(BaseModel):
    """Comparable contract for benchmarking."""

    contract_id: str
    equipment_types: List[str]
    monthly_fee: Decimal
    sla_tier: SLATier
    profitability: Optional[Decimal] = None


class RenegotiationOption(BaseModel):
    """Single renegotiation option analysis."""

    option_type: str = Field(..., description="maintain|invest|expand")
    description: str
    recommended_fee: Decimal
    estimated_npv_zar: Decimal
    roi_pct: Decimal
    implementation_notes: List[str] = Field(default_factory=list)


class RenegotiationOptions(BaseModel):
    """Request for renegotiation analysis."""

    contract_id: str
    option_type: str = Field(..., description="maintain|invest|expand")


class RenegotiationAnalysis(BaseModel):
    """Comprehensive renegotiation analysis."""

    contract_id: str
    options: List[RenegotiationOption]
    recommended_option: str
    market_context: Dict[str, Any] = Field(default_factory=dict)


class PricingHistory(BaseModel):
    """Track all quotes generated."""

    id: Optional[str] = None
    contract_id: str
    quote_fee_zar: Decimal = Field(..., description="Quote amount in ZAR")
    accepted_fee_zar: Optional[Decimal] = Field(None, description="Accepted amount if different")
    quote_date: date = Field(default_factory=date.today)
    decision_date: Optional[date] = None
    status: str = Field(default="draft", description="draft|sent|accepted|rejected|expired")
    created_by: Optional[str] = None


class QuotePerformance(BaseModel):
    """Track actual vs quoted costs."""

    id: Optional[str] = None
    quote_id: str
    actual_costs_zar: Optional[Decimal] = None
    variance_pct: Optional[Decimal] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None


class WinLossAnalysis(BaseModel):
    """Track quote acceptance/rejection."""

    id: Optional[str] = None
    quote_id: str
    outcome: str = Field(..., description="won|lost|pending")
    reason: Optional[str] = None
    client_feedback: Optional[str] = None
    lost_to_competitor: Optional[str] = None


class BenchmarkData(BaseModel):
    """Market benchmark data for comparables."""

    id: Optional[str] = None
    equipment_type: str
    sla_tier: str
    avg_fee_zar: Decimal
    min_fee_zar: Optional[Decimal] = None
    max_fee_zar: Optional[Decimal] = None
    market_sample_size: int = 0
    confidence_pct: int = 0
