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
    WhatIfScenario,
    WhatIfResponse,
    WhatIfScenarioResult,
    RenewalPricingRequest,
    RenewalPricingResponse,
    PricingBenchmarkResponse,
    RenewalQuote,
    ContractComparable,
    RenegotiationAnalysis,
    RenegotiationOption,
)
from app.database.repositories.sla_repository import get_sla_repository
from app.services.profitability_service import get_profitability_service
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
        config: Optional[PricingConfig] = None,
    ):
        """Initialize pricing engine with repositories and configuration."""
        self.budget_repo = budget_repo or BudgetRepository()
        self.condition_repo = condition_repo or ConditionAssessmentRepository()
        self.contract_repo = contract_repo or ContractRepository()
        self.config = config or PricingConfig()

    def calculate_price(
        self,
        request: QuoteRequest,
        condition_score_delta: int = 0,
        risk_buffer_multiplier: Decimal = Decimal("1.0"),
        target_margin_pct_override: Optional[Decimal] = None,
    ) -> QuoteResponse:
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
        condition_factors = self._get_condition_factors(request.equipment_codes, score_delta=condition_score_delta)
        condition_adj = self._calculate_condition_adjustment(base_cost, condition_factors)

        # Step 3: Get age adjustments
        age_adj = self._calculate_age_adjustment(base_cost, condition_factors)

        # Step 4: Get ML risk buffers
        risk_buffers = self._get_risk_buffers(request.equipment_codes, multiplier=risk_buffer_multiplier)
        risk_adj = self._calculate_risk_buffer(base_cost, risk_buffers)

        # Step 5: SLA tier adjustment
        sla_adj = self._calculate_sla_adjustment(base_cost, request.sla_tier)

        # Step 6: Calculate total adjusted cost
        total_cost = base_cost + condition_adj + age_adj + risk_adj + sla_adj

        # Step 7: Apply target margin
        target_margin = (
            target_margin_pct_override
            if target_margin_pct_override is not None
            else self._get_target_margin(request.sla_tier)
        )
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
                "margin": margin_amount,
            },
            risk_factors=self._identify_risk_factors(condition_factors, risk_buffers),
            assumptions=self._list_assumptions(request),
            market_comparison=self._get_market_comparison(request) if request.include_benchmarks else None,
            valid_until=date.today() + timedelta(days=30),
        )

    def calculate_what_if(self, request: QuoteRequest, scenarios: List[WhatIfScenario]) -> WhatIfResponse:
        """
        Run what-if analysis for pricing scenarios.
        """
        base_quote = self.calculate_price(request)
        results: List[WhatIfScenarioResult] = []

        for scenario in scenarios:
            equipment_codes = list(request.equipment_codes)
            if scenario.add_equipment_codes:
                equipment_codes.extend(scenario.add_equipment_codes)

            scenario_request = QuoteRequest(
                site_id=request.site_id,
                equipment_codes=equipment_codes,
                sla_tier=scenario.sla_tier or request.sla_tier,
                contract_months=request.contract_months,
                include_benchmarks=request.include_benchmarks,
            )

            scenario_quote = self.calculate_price(
                scenario_request,
                condition_score_delta=scenario.condition_score_delta,
                risk_buffer_multiplier=scenario.risk_buffer_multiplier,
                target_margin_pct_override=scenario.target_margin_pct,
            )

            delta = scenario_quote.recommended_fee_zar - base_quote.recommended_fee_zar
            delta_pct = (
                (delta / base_quote.recommended_fee_zar * Decimal("100"))
                if base_quote.recommended_fee_zar > 0
                else Decimal("0")
            )

            results.append(
                WhatIfScenarioResult(
                    name=scenario.name,
                    recommended_fee_zar=scenario_quote.recommended_fee_zar,
                    delta_zar=delta,
                    delta_pct=delta_pct,
                    cost_breakdown=scenario_quote.cost_breakdown,
                    risk_factors=scenario_quote.risk_factors,
                    assumptions=scenario_quote.assumptions,
                )
            )

        return WhatIfResponse(base_quote=base_quote, scenarios=results)

    def calculate_renewal_pricing(self, request: RenewalPricingRequest) -> RenewalPricingResponse:
        """
        Calculate renewal pricing recommendation based on actual costs.
        """
        contract = self.contract_repo.get_by_id(request.contract_id)
        if not contract:
            raise ValueError(f"Contract {request.contract_id} not found")

        current_fee = Decimal(str(contract.get("monthly_fee_zar") or 0))
        sla_tier = request.sla_tier or SLATier.standard
        target_margin = self._get_target_margin(sla_tier)

        # Use budget actuals for year as cost base
        summary = self.budget_repo.get_spending_summary(request.contract_id, request.year)
        total_actual = Decimal(str(summary.get("total_actual_zar", 0))) if summary else Decimal("0")
        months = 12
        avg_monthly_cost = (total_actual / Decimal(months)) if total_actual > 0 else Decimal("0")

        notes = []
        if avg_monthly_cost == 0:
            avg_monthly_cost = current_fee * Decimal("0.6")
            notes.append("No actual cost data for year; using 60% of current fee as proxy.")

        # SLA penalties exposure (best-effort)
        sla_repo = get_sla_repository()
        performance = sla_repo.get_performance_history(request.contract_id, months=12)
        penalty_total = Decimal("0")
        for perf in performance:
            start = getattr(perf, "period_start", None)
            if start and getattr(start, "year", None) == request.year:
                penalty_total += Decimal(str(getattr(perf, "clawback_amount_zar", 0) or 0))

        avg_monthly_penalty = (penalty_total / Decimal(months)) if penalty_total > 0 else Decimal("0")
        if avg_monthly_penalty > 0:
            notes.append(f"SLA penalties average {avg_monthly_penalty:.2f} ZAR/month in {request.year}.")

        # Margin trend adjustment (best-effort)
        trend_buffer = Decimal("0")
        try:
            trends = get_profitability_service().calculate_profitability_trends(request.contract_id, months=6)
            if len(trends) >= 6:
                last_three = sum(Decimal(str(t.margin_pct)) for t in trends[-3:]) / Decimal("3")
                prev_three = sum(Decimal(str(t.margin_pct)) for t in trends[:3]) / Decimal("3")
                if last_three < prev_three - Decimal("2"):
                    trend_buffer = Decimal("2.0")
                    notes.append("Margin trend declining; increasing target margin by 2%.")
        except Exception:
            pass

        # Penalty buffer based on exposure vs fee
        penalty_buffer = Decimal("0")
        if avg_monthly_penalty > 0:
            base = current_fee if current_fee > 0 else avg_monthly_cost
            penalty_pct = (avg_monthly_penalty / base * Decimal("100")) if base > 0 else Decimal("0")
            penalty_buffer = min(Decimal("5"), penalty_pct)
            notes.append(f"Adding {penalty_buffer:.2f}% buffer for penalty exposure.")

        adjusted_margin = target_margin + trend_buffer + penalty_buffer
        total_cost_base = avg_monthly_cost + avg_monthly_penalty
        recommended_fee = total_cost_base * (Decimal("1") + (adjusted_margin / Decimal("100")))
        delta = recommended_fee - current_fee
        delta_pct = (delta / current_fee * Decimal("100")) if current_fee > 0 else Decimal("0")

        # Condition trend note (best-effort)
        assessments = self.condition_repo.get_by_contract(request.contract_id)
        if assessments:
            avg_score = sum(a.get("overall_score", 3) for a in assessments) / len(assessments)
            if avg_score <= 2.5:
                notes.append("Condition assessments indicate below-average asset health.")
            elif avg_score >= 4.5:
                notes.append("Condition assessments indicate strong asset health.")

        return RenewalPricingResponse(
            contract_id=request.contract_id,
            year=request.year,
            current_monthly_fee_zar=current_fee,
            actual_cost_monthly_avg_zar=avg_monthly_cost,
            target_margin_pct=adjusted_margin,
            recommended_monthly_fee_zar=recommended_fee,
            delta_zar=delta,
            delta_pct=delta_pct,
            notes=notes,
        )

    def calculate_renewal_price(self, contract_id: str) -> RenewalQuote:
        """
        Calculate renewal pricing for an existing contract.

        Retrieves contract, recalculates pricing based on current condition,
        and compares to original quoted fee.

        Args:
            contract_id: ID of contract to renew

        Returns:
            RenewalQuote with recommended fee, drivers, and confidence level
        """
        contract = self.contract_repo.get_by_id(contract_id)
        if not contract:
            raise ValueError(f"Contract {contract_id} not found")

        original_fee = Decimal(str(contract.get("monthly_fee_zar") or 0))
        equipment_codes = self._get_contract_equipment_codes(contract_id)
        sla_tier = SLATier(contract.get("sla_tier", "standard"))

        # Build quote request for current conditions
        quote_request = QuoteRequest(
            site_id=contract.get("site_id", ""),
            equipment_codes=equipment_codes,
            sla_tier=sla_tier,
            contract_months=contract.get("contract_months", 12),
            include_benchmarks=True,
        )

        # Calculate current pricing
        current_quote = self.calculate_price(quote_request)
        recommended_fee = current_quote.recommended_fee_zar

        # Calculate drivers
        drivers = []
        fee_change = recommended_fee - original_fee
        fee_change_pct = (fee_change / original_fee * Decimal("100")) if original_fee > 0 else Decimal("0")

        # Analyze what changed
        if (
            "condition" in current_quote.cost_breakdown
            and current_quote.cost_breakdown.get("condition_adjustment", 0) != 0
        ):
            drivers.append("Equipment condition deteriorated")

        if "age" in current_quote.cost_breakdown and current_quote.cost_breakdown.get("age_adjustment", 0) != 0:
            drivers.append("Equipment aging impact")

        if len(current_quote.risk_factors) > 0:
            drivers.append("Increased failure risk from ML predictions")

        if not drivers:
            if fee_change_pct > Decimal("5"):
                drivers.append("Market rate adjustment")
            elif fee_change_pct < Decimal("-5"):
                drivers.append("Competitive market pricing")
            else:
                drivers.append("Standard cost of living adjustment")

        # Determine confidence
        if len(equipment_codes) >= 3 and current_quote.cost_breakdown:
            confidence = "high"
        elif len(equipment_codes) >= 1:
            confidence = "medium"
        else:
            confidence = "low"

        return RenewalQuote(
            original_monthly_fee=original_fee,
            recommended_monthly_fee=recommended_fee,
            fee_change_pct=fee_change_pct,
            drivers=drivers,
            confidence=confidence,
            assumptions=current_quote.assumptions,
        )

    def get_comparable_contracts(
        self, equipment_types: List[str], sla_tier: SLATier, limit: int = 10
    ) -> List[ContractComparable]:
        """
        Find similar contracts in portfolio for benchmarking.

        Args:
            equipment_types: List of equipment types to match
            sla_tier: SLA tier to match
            limit: Maximum number of comparables to return

        Returns:
            List of comparable contracts with fees and profitability
        """
        try:
            similar = self.contract_repo.find_similar_contracts(
                equipment_types=equipment_types, sla_tier=sla_tier, limit=limit
            )

            comparables = []
            for contract in similar:
                try:
                    profitability_service = get_profitability_service()
                    profit_data = profitability_service.get_contract_profitability(contract.get("id"))
                    profitability_pct = Decimal(str(profit_data.get("margin_pct", 0)))
                except Exception:
                    profitability_pct = None

                comparable = ContractComparable(
                    contract_id=contract.get("id", ""),
                    equipment_types=equipment_types,
                    monthly_fee=Decimal(str(contract.get("monthly_fee_zar", 0))),
                    sla_tier=SLATier(contract.get("sla_tier", "standard")),
                    profitability=profitability_pct,
                )
                comparables.append(comparable)

            return comparables
        except Exception:
            return []

    def calculate_renegotiation_terms(
        self, contract_id: str, options_requested: Optional[str] = None
    ) -> RenegotiationAnalysis:
        """
        Analyze renegotiation options for contract renewal.

        Options:
        1. Maintain margin: Raise fee to cover increased costs
        2. Invest in maintenance: Reduce risk buffer, maintain fee
        3. Add services: Justify higher fee with expanded scope

        Args:
            contract_id: ID of contract to analyze
            options_requested: Optional filter (maintain|invest|expand)

        Returns:
            RenegotiationAnalysis with NPV analysis for each option
        """
        contract = self.contract_repo.get_by_id(contract_id)
        if not contract:
            raise ValueError(f"Contract {contract_id} not found")

        current_fee = Decimal(str(contract.get("monthly_fee_zar", 0)))
        equipment_codes = self._get_contract_equipment_codes(contract_id)
        sla_tier = SLATier(contract.get("sla_tier", "standard"))

        # Calculate base scenario
        quote_request = QuoteRequest(
            site_id=contract.get("site_id", ""),
            equipment_codes=equipment_codes,
            sla_tier=sla_tier,
            contract_months=12,
            include_benchmarks=False,
        )
        base_quote = self.calculate_price(quote_request)

        options = []

        # Option 1: Maintain margin (raise fee)
        if options_requested is None or options_requested == "maintain":
            margin_pct = self._get_target_margin(sla_tier)
            base_cost = base_quote.recommended_fee_zar - (
                base_quote.recommended_fee_zar * (margin_pct / Decimal("100"))
            )
            new_fee = base_cost * (Decimal("1") + (margin_pct / Decimal("100")))
            fee_increase = new_fee - current_fee
            npv = fee_increase * Decimal("12") * Decimal("3")  # 3-year horizon

            options.append(
                RenegotiationOption(
                    option_type="maintain",
                    description="Increase contract fee to maintain current margin %",
                    recommended_fee=new_fee,
                    estimated_npv_zar=npv,
                    roi_pct=(fee_increase / current_fee * Decimal("100")) if current_fee > 0 else Decimal("0"),
                    implementation_notes=[
                        "Present to client as cost passthrough for inflation",
                        "Minimal service changes needed",
                        "Higher acceptance risk if market rates are stable",
                    ],
                )
            )

        # Option 2: Invest in maintenance (reduce risk, maintain fee)
        if options_requested is None or options_requested == "invest":
            # Assume 20% reduction in risk buffer through preventive maintenance
            risk_reduction = Decimal("0.2")
            cost_reduction = base_quote.cost_breakdown.get("risk_buffer", Decimal("0")) * risk_reduction
            maintenance_investment = cost_reduction * Decimal("0.5")  # 50% of savings goes to maintenance
            net_improvement = cost_reduction - maintenance_investment
            npv = net_improvement * Decimal("12") * Decimal("3")  # 3-year horizon

            options.append(
                RenegotiationOption(
                    option_type="invest",
                    description="Invest 50% of risk reduction in preventive maintenance",
                    recommended_fee=current_fee,  # Keep fee same
                    estimated_npv_zar=npv,
                    roi_pct=(net_improvement / maintenance_investment * Decimal("100"))
                    if maintenance_investment > 0
                    else Decimal("0"),
                    implementation_notes=[
                        "Fee remains unchanged from client perspective",
                        "Requires new preventive maintenance program",
                        "Builds customer loyalty and longer-term relationship",
                        "Risk reduction improves service quality metrics",
                    ],
                )
            )

        # Option 3: Add services (justify higher fee)
        if options_requested is None or options_requested == "expand":
            # Assume adding monitoring services at 15% of current fee
            service_addition = current_fee * Decimal("0.15")
            new_fee = current_fee + service_addition
            new_value_delivered = service_addition * Decimal("12") * Decimal("3")
            npv = new_value_delivered

            options.append(
                RenegotiationOption(
                    option_type="expand",
                    description="Add predictive maintenance and real-time monitoring services",
                    recommended_fee=new_fee,
                    estimated_npv_zar=npv,
                    roi_pct=Decimal("150"),  # 15% fee increase with 100% uptake of new services
                    implementation_notes=[
                        "Requires deployment of monitoring infrastructure",
                        "Enables data-driven preventive maintenance",
                        "Justifies 15% fee increase with clear ROI to client",
                        "Highest revenue but requires service capability investment",
                    ],
                )
            )

        # Recommend best option (usually maintain for steady state)
        recommended_option = "maintain"
        if options:
            # If risk buffer is high, recommend invest; if services needed, recommend expand
            if base_quote.cost_breakdown.get("risk_buffer", Decimal("0")) > base_quote.recommended_fee_zar * Decimal(
                "0.2"
            ):
                recommended_option = "invest"
            elif "High failure risk" in base_quote.risk_factors:
                recommended_option = "expand"

        return RenegotiationAnalysis(
            contract_id=contract_id,
            options=options,
            recommended_option=recommended_option,
            market_context={
                "current_fee": float(current_fee),
                "base_cost": float(base_quote.recommended_fee_zar),
                "margin_pct": float(self._get_target_margin(sla_tier)),
            },
        )

    def _get_contract_equipment_codes(self, contract_id: str) -> List[str]:
        """Get equipment codes for a contract."""
        try:
            assets = self.contract_repo.get_contract_assets(contract_id)
            equipment_codes = []
            for asset in assets:
                eq_code = asset.get("equipment_code") or asset.get("code")
                if eq_code:
                    equipment_codes.append(eq_code)
            return equipment_codes if equipment_codes else ["unknown"]
        except Exception:
            return ["unknown"]

    def get_benchmarks_for_contract(self, contract_id: str, limit: int = 5) -> PricingBenchmarkResponse:
        """
        Get benchmarking metrics for similar contracts.
        """
        assets = self.contract_repo.get_contract_assets(contract_id)
        equipment_types = []
        for asset in assets:
            eq = asset.get("equipment") or {}
            if eq.get("type"):
                equipment_types.append(eq.get("type"))

        similar = self.contract_repo.find_similar_contracts(equipment_types=equipment_types, limit=limit)

        fees = [Decimal(str(c.get("monthly_fee_zar") or 0)) for c in similar] if similar else []
        if not fees:
            return PricingBenchmarkResponse(
                contract_id=contract_id,
                similar_contracts=0,
                average_monthly_fee_zar=Decimal("0"),
                min_monthly_fee_zar=Decimal("0"),
                max_monthly_fee_zar=Decimal("0"),
            )

        return PricingBenchmarkResponse(
            contract_id=contract_id,
            similar_contracts=len(fees),
            average_monthly_fee_zar=sum(fees) / Decimal(len(fees)),
            min_monthly_fee_zar=min(fees),
            max_monthly_fee_zar=max(fees),
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
                    Decimal(str(v))
                    for v in template.get("typical_monthly_breakdown", {}).values()
                    if v  # Skip None/0 values
                )
                total_monthly += monthly
            else:
                # Default cost if no template found
                total_monthly += Decimal("5000")  # Default R5000/month

        return total_monthly

    def _calculate_condition_adjustment(self, base_cost: Decimal, factors: List[ConditionFactor]) -> Decimal:
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
            multiplier = self.config.condition_multipliers.get(factor.overall_score, Decimal("1.0"))
            cost_share = base_cost / Decimal(len(factors))
            adjustment += cost_share * (multiplier - Decimal("1.0"))

        return adjustment

    def _calculate_age_adjustment(self, base_cost: Decimal, factors: List[ConditionFactor]) -> Decimal:
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

    def _calculate_risk_buffer(self, base_cost: Decimal, buffers: List[RiskBuffer]) -> Decimal:
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

    def _calculate_sla_adjustment(self, base_cost: Decimal, sla_tier: SLATier) -> Decimal:
        """
        Calculate SLA tier premium adjustment.

        Premium tiers require more resources, faster response.
        """
        multiplier = self.config.sla_multipliers.get(sla_tier.value, Decimal("1.0"))
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

    def _get_condition_factors(self, equipment_codes: List[str], score_delta: int = 0) -> List[ConditionFactor]:
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
                        equipment.get("install_date") or equipment.get("installed_date")
                    )

                    adjusted_score = max(1, min(5, int(assessment.get("overall_score", 3)) + score_delta))
                    factor = ConditionFactor(
                        equipment_id=code,
                        overall_score=adjusted_score,
                        age_years=age_years,
                        condition_multiplier=Decimal("1.0"),  # Calculated later
                        age_multiplier=Decimal("1.0"),  # Calculated later
                    )
                    factors.append(factor)
            except Exception:
                # Skip equipment if data unavailable
                continue

        return factors

    def _get_risk_buffers(self, equipment_codes: List[str], multiplier: Decimal = Decimal("1.0")) -> List[RiskBuffer]:
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
                    failure_prob = Decimal(str(prediction.get("probability", 0)))
                    failure_prob = max(Decimal("0"), min(Decimal("1"), failure_prob * multiplier))
                    buffer = RiskBuffer(
                        equipment_id=code,
                        failure_probability=failure_prob,
                        health_score=prediction.get("health_score", 80),
                        risk_buffer_pct=Decimal("0"),  # Calculated later
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
            "max": recommended_fee * Decimal("1.1"),  # +10%
        }

    def _identify_risk_factors(
        self, condition_factors: List[ConditionFactor], risk_buffers: List[RiskBuffer]
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
                    f"High failure risk: {rb.equipment_id} ({rb.failure_probability * 100:.0f}% probability)"
                )

        return factors if factors else ["No significant risk factors identified"]

    def _list_assumptions(self, request: QuoteRequest) -> List[str]:
        """List key assumptions in quote."""
        return [
            f"Contract duration: {request.contract_months} months",
            f"SLA tier: {request.sla_tier.value}",
            "Assumes normal operating conditions",
            "Excludes act of god events",
            "Based on current equipment condition assessments",
        ]

    def _get_market_comparison(self, request: QuoteRequest) -> Optional[Dict[str, Any]]:
        """Get market benchmark data for comparison."""
        try:
            # Find similar contracts in portfolio
            similar = self.contract_repo.find_similar_contracts(
                equipment_types=request.equipment_codes, sla_tier=request.sla_tier
            )

            if similar and len(similar) > 0:
                fees = [c.get("monthly_fee_zar", Decimal("0")) for c in similar]
                return {
                    "similar_contracts": len(similar),
                    "average_monthly_fee": sum(fees) / Decimal(len(fees)),
                    "min_monthly_fee": min(fees),
                    "max_monthly_fee": max(fees),
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
                "health_score": 80,
            }

    def _get_default_templates(self) -> Dict[str, Any]:
        """Get default budget templates if repository unavailable."""
        return {
            "chiller": {"typical_monthly_breakdown": {"labor": 4500, "parts": 2500, "callout": 800}},
            "ahu": {"typical_monthly_breakdown": {"labor": 2200, "parts": 1200, "callout": 600}},
            "fcu": {"typical_monthly_breakdown": {"labor": 800, "parts": 400, "callout": 300}},
            "vav": {"typical_monthly_breakdown": {"labor": 400, "parts": 200, "callout": 200}},
            "pump": {"typical_monthly_breakdown": {"labor": 600, "parts": 300, "callout": 200}},
            "generator": {"typical_monthly_breakdown": {"labor": 3500, "parts": 2000, "callout": 500}},
            "ups": {"typical_monthly_breakdown": {"labor": 800, "parts": 500, "callout": 200}},
        }


# Singleton factory function
_pricing_engine_instance = None


def get_pricing_engine() -> PricingEngine:
    """Get or create singleton pricing engine instance."""
    global _pricing_engine_instance
    if _pricing_engine_instance is None:
        _pricing_engine_instance = PricingEngine()
    return _pricing_engine_instance
