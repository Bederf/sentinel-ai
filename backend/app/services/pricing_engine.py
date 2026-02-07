"""
Actuarial pricing calculation engine for FM contract quotes.

Phase 52-01: Risk-Based Pricing Tools
Calculates recommended contract fees based on equipment condition, age,
ML failure predictions, SLA tier requirements, and target margins.
"""

import uuid
from typing import List, Dict, Any, Optional
from decimal import Decimal
from datetime import date, timedelta

from app.models.pricing import (
    SLATier,
    ConditionFactor,
    RiskBuffer,
    QuoteRequest,
    QuoteResponse,
    PricingConfig,
    MarginTarget
)
from app.database.repositories.budget_repository import BudgetRepository
from app.database.repositories.condition_assessment_repository import ConditionAssessmentRepository
from app.database.repositories.contract_repository import ContractRepository


class PricingEngine:
    """
    Actuarial pricing engine for FM contract quotes.

    Multi-factor pricing calculation:
    1. Base cost from budget templates
    2. Condition adjustment (equipment health)
    3. Age adjustment (equipment lifecycle)
    4. Risk buffer (ML failure predictions)
    5. SLA tier premium
    6. Target margin application
    """

    def __init__(
        self,
        budget_repo: Optional[BudgetRepository] = None,
        condition_repo: Optional[ConditionAssessmentRepository] = None,
        contract_repo: Optional[ContractRepository] = None,
        config: Optional[PricingConfig] = None
    ):
        """Initialize pricing engine with repositories and configuration."""
        self.budget_repo = budget_repo or BudgetRepository()
        self.condition_repo = condition_repo or ConditionAssessmentRepository()
        self.contract_repo = contract_repo or ContractRepository()
        self.config = config or PricingConfig()

    def calculate_price(self, request: QuoteRequest) -> QuoteResponse:
        """
        Calculate recommended price for contract quote.

        Args:
            request: Quote request with building, equipment, SLA tier

        Returns:
            QuoteResponse with recommended fee, breakdown, and risk factors
        """
        # Step 1: Get base cost from templates
        base_cost = self._calculate_base_cost(request.equipment_codes)

        # Step 2: Get condition factors
        condition_factors = self._get_condition_factors(request.equipment_codes)
        condition_adj = self._calculate_condition_adjustment(
            base_cost, condition_factors
        )

        # Step 3: Get age adjustments
        age_adj = self._calculate_age_adjustment(
            base_cost, condition_factors
        )

        # Step 4: Get ML risk buffers
        risk_buffers = self._get_risk_buffers(request.equipment_codes)
        risk_adj = self._calculate_risk_buffer(base_cost, risk_buffers)

        # Step 5: SLA tier adjustment
        sla_adj = self._calculate_sla_adjustment(
            base_cost, request.sla_tier
        )

        # Step 6: Calculate total adjusted cost
        total_cost = (
            base_cost
            + condition_adj
            + age_adj
            + risk_adj
            + sla_adj
        )

        # Step 7: Apply target margin
        target_margin = self._get_target_margin(request.sla_tier)
        margin_amount = total_cost * (target_margin / Decimal("100"))
        recommended_fee = total_cost + margin_amount

        # Step 8: Build response
        return QuoteResponse(
            request_id=str(uuid.uuid4()),
            recommended_fee_zar=recommended_fee,
            fee_range_zar=self._calculate_fee_range(recommended_fee),
            cost_breakdown={
                "base_cost": base_cost,
                "condition_adjustment": condition_adj,
                "age_adjustment": age_adj,
                "risk_buffer": risk_adj,
                "sla_adjustment": sla_adj,
                "margin": margin_amount
            },
            risk_factors=self._identify_risk_factors(condition_factors, risk_buffers),
            assumptions=self._list_assumptions(request),
            market_comparison=self._get_market_comparison(request) if request.include_benchmarks else None,
            valid_until=date.today() + timedelta(days=30)
        )

    def _calculate_base_cost(self, equipment_codes: List[str]) -> Decimal:
        """
        Calculate base cost from equipment budget templates.

        Sums monthly costs from equipment-type templates.
        """
        try:
            templates = self.budget_repo.get_budget_templates()
        except Exception:
            # Fallback to default templates if repository unavailable
            templates = self._get_default_templates()

        total_monthly = Decimal("0")

        for code in equipment_codes:
            equipment_type = self._extract_equipment_type(code)
            if equipment_type in templates:
                template = templates[equipment_type]
                monthly = sum(
                    Decimal(str(v)) for v in
                    template.get("typical_monthly_breakdown", {}).values()
                    if v  # Skip None/0 values
                )
                total_monthly += monthly
            else:
                # Default cost if no template found
                total_monthly += Decimal("5000")  # Default R5000/month

        return total_monthly

    def _calculate_condition_adjustment(
        self,
        base_cost: Decimal,
        factors: List[ConditionFactor]
    ) -> Decimal:
        """
        Calculate cost adjustment based on equipment condition.

        Condition multiplier: 1.0 (excellent) to 2.0 (poor)
        Score 5 = 1.0x, Score 1 = 2.0x
        """
        adjustment = Decimal("0")

        if not factors:
            return adjustment

        for factor in factors:
            # Use config multipliers
            multiplier = self.config.condition_multipliers.get(
                factor.overall_score,
                Decimal("1.0")
            )
            cost_share = base_cost / Decimal(len(factors))
            adjustment += cost_share * (multiplier - Decimal("1.0"))

        return adjustment

    def _calculate_age_adjustment(
        self,
        base_cost: Decimal,
        factors: List[ConditionFactor]
    ) -> Decimal:
        """
        Calculate cost adjustment based on equipment age.

        Age multiplier: 1.0x (<5 years) to 1.5x (>20 years)
        """
        adjustment = Decimal("0")

        if not factors:
            return adjustment

        for factor in factors:
            # Determine age bracket
            if factor.age_years < 5:
                age_bracket = "0-5"
            elif factor.age_years < 10:
                age_bracket = "5-10"
            elif factor.age_years < 15:
                age_bracket = "10-15"
            elif factor.age_years < 20:
                age_bracket = "15-20"
            else:
                age_bracket = "20+"

            multiplier = self.config.age_multipliers.get(age_bracket, Decimal("1.0"))
            cost_share = base_cost / Decimal(len(factors))
            adjustment += cost_share * (multiplier - Decimal("1.0"))

        return adjustment

    def _calculate_risk_buffer(
        self,
        base_cost: Decimal,
        buffers: List[RiskBuffer]
    ) -> Decimal:
        """
        Calculate risk buffer from ML failure predictions.

        Failure probability 0-1 → Buffer 0-50%
        """
        if not buffers:
            return Decimal("0")

        total_buffer_pct = Decimal("0")

        for buffer in buffers:
            # Failure probability 0-1 → Buffer 0-50%
            risk_pct = buffer.failure_probability * Decimal("50")
            total_buffer_pct += risk_pct

        avg_buffer_pct = total_buffer_pct / Decimal(len(buffers))
        return base_cost * (avg_buffer_pct / Decimal("100"))

    def _calculate_sla_adjustment(
        self,
        base_cost: Decimal,
        sla_tier: SLATier
    ) -> Decimal:
        """
        Calculate SLA tier premium adjustment.

        Premium tiers require more resources, faster response.
        """
        multiplier = self.config.sla_multipliers.get(
            sla_tier.value,
            Decimal("1.0")
        )
        return base_cost * (multiplier - Decimal("1.0"))

    def _get_target_margin(self, sla_tier: SLATier) -> Decimal:
        """
        Get target margin based on SLA tier.

        Higher SLA = higher margin target.
        """
        for margin_target in self.config.margin_targets:
            if margin_target.sla_tier == sla_tier:
                return margin_target.margin_pct
        return self.config.default_margin_pct

    def _get_condition_factors(self, equipment_codes: List[str]) -> List[ConditionFactor]:
        """
        Get condition assessment data for equipment.

        Returns ConditionFactor with score, age, and calculated multipliers.
        """
        factors = []

        for code in equipment_codes:
            try:
                assessment = self.condition_repo.get_latest_assessment(code)
                equipment = self.contract_repo.get_equipment(code)

                if assessment and equipment:
                    age_years = self._calculate_equipment_age(
                        equipment.get("installed_date")
                    )

                    factor = ConditionFactor(
                        equipment_id=code,
                        overall_score=assessment.get("overall_score", 3),
                        age_years=age_years,
                        condition_multiplier=Decimal("1.0"),  # Calculated later
                        age_multiplier=Decimal("1.0")  # Calculated later
                    )
                    factors.append(factor)
            except Exception:
                # Skip equipment if data unavailable
                continue

        return factors

    def _get_risk_buffers(self, equipment_codes: List[str]) -> List[RiskBuffer]:
        """
        Get ML prediction risk buffers for equipment.

        Returns RiskBuffer with failure probability and health score.
        """
        buffers = []

        for code in equipment_codes:
            try:
                # Try to get ML prediction
                prediction = self._get_ml_prediction(code)

                if prediction:
                    buffer = RiskBuffer(
                        equipment_id=code,
                        failure_probability=Decimal(str(prediction.get("probability", 0))),
                        health_score=prediction.get("health_score", 80),
                        risk_buffer_pct=Decimal("0")  # Calculated later
                    )
                    buffers.append(buffer)
            except Exception:
                # Skip if ML prediction unavailable
                continue

        return buffers

    def _calculate_fee_range(self, recommended_fee: Decimal) -> Dict[str, Decimal]:
        """Calculate pricing range for quote."""
        return {
            "min": recommended_fee * Decimal("0.9"),  # -10%
            "target": recommended_fee,
            "max": recommended_fee * Decimal("1.1")   # +10%
        }

    def _identify_risk_factors(
        self,
        condition_factors: List[ConditionFactor],
        risk_buffers: List[RiskBuffer]
    ) -> List[str]:
        """Identify key risk factors for quote."""
        factors = []

        for cf in condition_factors:
            if cf.overall_score <= 2:
                factors.append(f"Poor condition: {cf.equipment_id} (score {cf.overall_score}/5)")
            if cf.age_years > 15:
                factors.append(f"Aging equipment: {cf.equipment_id} ({cf.age_years:.0f} years)")

        for rb in risk_buffers:
            if rb.failure_probability > Decimal("0.3"):
                factors.append(
                    f"High failure risk: {rb.equipment_id} "
                    f"({rb.failure_probability * 100:.0f}% probability)"
                )

        return factors if factors else ["No significant risk factors identified"]

    def _list_assumptions(self, request: QuoteRequest) -> List[str]:
        """List key assumptions in quote."""
        return [
            f"Contract duration: {request.contract_months} months",
            f"SLA tier: {request.sla_tier.value}",
            "Assumes normal operating conditions",
            "Excludes act of god events",
            "Based on current equipment condition assessments"
        ]

    def _get_market_comparison(self, request: QuoteRequest) -> Optional[Dict[str, Any]]:
        """Get market benchmark data for comparison."""
        try:
            # Find similar contracts in portfolio
            similar = self.contract_repo.find_similar_contracts(
                equipment_types=request.equipment_codes,
                sla_tier=request.sla_tier
            )

            if similar and len(similar) > 0:
                fees = [c.get("monthly_fee_zar", Decimal("0")) for c in similar]
                return {
                    "similar_contracts": len(similar),
                    "average_monthly_fee": sum(fees) / Decimal(len(fees)),
                    "min_monthly_fee": min(fees),
                    "max_monthly_fee": max(fees)
                }
        except Exception:
            pass

        return None

    def _extract_equipment_type(self, equipment_code: str) -> str:
        """Extract equipment type from equipment code."""
        # Equipment code format: S002-CHILLER-B1-001
        parts = equipment_code.split("-")
        if len(parts) >= 2:
            return parts[1].lower()
        return "unknown"

    def _calculate_equipment_age(self, installed_date: Optional[str]) -> float:
        """Calculate equipment age in years from installation date."""
        if not installed_date:
            return 5.0  # Default 5 years if unknown

        try:
            from datetime import datetime
            install_date = datetime.fromisoformat(installed_date.replace("Z", "+00:00"))
            age_days = (datetime.now(install_date.tzinfo) - install_date).days
            return age_days / 365.25
        except Exception:
            return 5.0  # Default 5 years if parsing fails

    def _get_ml_prediction(self, equipment_code: str) -> Optional[Dict[str, Any]]:
        """
        Get ML failure prediction for equipment.

        Returns prediction dict with probability and health_score.
        """
        try:
            # Import ML service
            from app.services.ml_prediction_service import MLPredictionService
            ml_service = MLPredictionService()
            prediction = ml_service.get_prediction(equipment_code)
            return prediction
        except Exception:
            # Return default if ML unavailable
            return {
                "probability": 0.1,  # 10% default risk
                "health_score": 80
            }

    def _get_default_templates(self) -> Dict[str, Any]:
        """Get default budget templates if repository unavailable."""
        return {
            "chiller": {
                "typical_monthly_breakdown": {
                    "labor": 4500,
                    "parts": 2500,
                    "callout": 800
                }
            },
            "ahu": {
                "typical_monthly_breakdown": {
                    "labor": 2200,
                    "parts": 1200,
                    "callout": 600
                }
            },
            "fcu": {
                "typical_monthly_breakdown": {
                    "labor": 800,
                    "parts": 400,
                    "callout": 300
                }
            },
            "vav": {
                "typical_monthly_breakdown": {
                    "labor": 400,
                    "parts": 200,
                    "callout": 200
                }
            },
            "pump": {
                "typical_monthly_breakdown": {
                    "labor": 600,
                    "parts": 300,
                    "callout": 200
                }
            },
            "generator": {
                "typical_monthly_breakdown": {
                    "labor": 3500,
                    "parts": 2000,
                    "callout": 500
                }
            },
            "ups": {
                "typical_monthly_breakdown": {
                    "labor": 800,
                    "parts": 500,
                    "callout": 200
                }
            }
        }


# Singleton factory function
_pricing_engine_instance = None


def get_pricing_engine() -> PricingEngine:
    """Get or create singleton pricing engine instance."""
    global _pricing_engine_instance
    if _pricing_engine_instance is None:
        _pricing_engine_instance = PricingEngine()
    return _pricing_engine_instance
