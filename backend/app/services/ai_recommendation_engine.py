"""AI Recommendation ROI Engine.

Analyzes all simulated consumption data (HVAC, Lighting, Water) alongside
validation data (power anomalies, cost accuracy) to generate ranked financial
recommendations with payback periods and ROI metrics.

Model:
  Savings Calculation: Baseline - Optimized = Annual Savings
  ROI Analysis: Savings / Investment = Payback Period
  Ranking: Sort by ROI descending, confidence, implementation ease
  Messaging: Generate "Save R X/month" prompts with confidence

Integration: Called on-demand or daily to update recommendation dashboard.
Output: Ranked list of actionable recommendations with financial impact.
"""

import logging
from datetime import datetime
from enum import StrEnum
from statistics import mean
from typing import Any

logger = logging.getLogger(__name__)


# Recommendation categories
class RecommendationType(StrEnum):
    """Types of recommendations"""

    LIGHTING_OPTIMIZATION = "lighting_optimization"
    WATER_EFFICIENCY = "water_efficiency"
    HVAC_MAINTENANCE = "hvac_maintenance"
    OCCUPANCY_OPTIMIZATION = "occupancy_optimization"
    THERMAL_SETBACK = "thermal_setback"


# Baseline assumptions (pre-optimization)
BASELINE_LIGHTING_KWH_PER_DAY = 200.0  # Static baseline before DALI
BASELINE_WATER_LITERS_PER_DAY = 8000.0  # Static baseline
BASELINE_HVAC_COP = 3.5  # Design COP (healthy)

# Cost rates
ENERGY_RATE_R_PER_KWH = 2.159  # City Power average
WATER_RATE_R_PER_LITER = 0.00795  # Johannesburg Tier 1
WATER_SEWERAGE_RATE_R_PER_LITER = 0.00630  # Sewerage charge
MAINTENANCE_COST_R = 15000.0  # Typical HVAC maintenance
DALI_RETROFIT_COST_R = 85000.0  # Zone lighting upgrade
WATER_EFFICIENCY_RETROFIT_COST_R = 35000.0  # Fixture upgrades

# Recommendation confidence thresholds
CONFIDENCE_HIGH = 0.85
CONFIDENCE_MEDIUM = 0.70
CONFIDENCE_LOW = 0.50

# Implementation difficulty (1-5 scale, 1=easy, 5=hard)
DIFFICULTY_DALI_RETROFIT = 4  # Complex, requires rewiring
DIFFICULTY_WATER_RETROFIT = 3  # Moderate, fixture replacement
DIFFICULTY_HVAC_MAINTENANCE = 1  # Easy, call service
DIFFICULTY_OCCUPANCY_OPTIMIZATION = 2  # Software/scheduling


class AIRecommendationEngine:
    """Engine for generating AI-powered financial recommendations."""

    def __init__(self, site_id: str):
        """Initialize recommendation engine.

        Args:
            site_id: Building/site identifier (e.g., 'site-002')
        """
        self.site_id = site_id
        self.simulated_date = datetime.now()

    async def generate_recommendations(
        self,
        lighting_kwh_current: float = 185.0,
        water_liters_current: float = 6847.0,
        hvac_cop_current: float = 3.5,
        power_anomalies_count: int = 0,
        cost_variance_pct: float = 0.18,
    ) -> dict[str, Any]:
        """Generate ranked list of financial recommendations.

        Args:
            lighting_kwh_current: Current daily lighting energy
            water_liters_current: Current daily water consumption
            hvac_cop_current: Current chiller COP (design or degraded)
            power_anomalies_count: Number of power anomalies detected
            cost_variance_pct: Cost model variance from invoices

        Returns:
            Ranked recommendations with ROI, payback period, messaging
        """
        recommendations = []

        # Lighting Optimization Recommendation
        lighting_rec = await self._calculate_lighting_recommendation(lighting_kwh_current)
        if lighting_rec:
            recommendations.append(lighting_rec)

        # Water Efficiency Recommendation
        water_rec = await self._calculate_water_recommendation(water_liters_current)
        if water_rec:
            recommendations.append(water_rec)

        # HVAC Maintenance Recommendation
        if hvac_cop_current < BASELINE_HVAC_COP:
            hvac_rec = await self._calculate_hvac_recommendation(hvac_cop_current)
            if hvac_rec:
                recommendations.append(hvac_rec)

        # Occupancy Optimization Recommendation
        occ_rec = await self._calculate_occupancy_recommendation(power_anomalies_count, cost_variance_pct)
        if occ_rec:
            recommendations.append(occ_rec)

        # Rank by ROI (highest first)
        recommendations.sort(key=lambda x: x["roi_pct"], reverse=True)

        # Add ranking
        for idx, rec in enumerate(recommendations, 1):
            rec["rank"] = idx
            rec["priority"] = self._get_priority(idx, len(recommendations))

        return {
            "site_id": self.site_id,
            "generated_date": datetime.now().isoformat(),
            "recommendation_count": len(recommendations),
            "total_annual_savings_r": round(sum(r["annual_savings_r"] for r in recommendations), 2),
            "total_investment_r": round(
                sum(r["investment_cost_r"] for r in recommendations if r["investment_cost_r"] > 0), 2
            ),
            "average_payback_months": round(
                mean([r["payback_months"] for r in recommendations if r["payback_months"] > 0])
                if any(r["payback_months"] > 0 for r in recommendations)
                else 0,
                1,
            ),
            "recommendations": recommendations,
        }

    async def _calculate_lighting_recommendation(
        self,
        current_kwh: float,
    ) -> dict[str, Any] | None:
        """Calculate DALI lighting optimization recommendation."""
        baseline_kwh = BASELINE_LIGHTING_KWH_PER_DAY
        savings_kwh_per_day = baseline_kwh - current_kwh

        if savings_kwh_per_day < 1.0:
            return None  # Insufficient savings to recommend

        annual_savings_kwh = savings_kwh_per_day * 365
        annual_savings_r = annual_savings_kwh * ENERGY_RATE_R_PER_KWH
        investment_r = DALI_RETROFIT_COST_R
        payback_months = (investment_r / annual_savings_r * 12) if annual_savings_r > 0 else 0

        # Confidence based on consistency
        confidence = min(0.92, CONFIDENCE_HIGH)  # DALI is proven technology

        return {
            "type": RecommendationType.LIGHTING_OPTIMIZATION,
            "rank": None,  # Set by caller
            "priority": None,
            "title": "Install DALI Lighting Control System",
            "description": (
                f"Upgrade to occupancy-aware LED lighting with daylight harvesting. "
                f"Current consumption {current_kwh:.0f} kWh/day can be reduced to optimal levels."
            ),
            "current_state": {
                "daily_kwh": round(current_kwh, 2),
                "annual_kwh": round(current_kwh * 365, 0),
                "annual_cost_r": round(current_kwh * 365 * ENERGY_RATE_R_PER_KWH, 2),
            },
            "optimized_state": {
                "daily_kwh": round(current_kwh * 0.75, 2),  # 25% reduction typical
                "annual_kwh": round(current_kwh * 365 * 0.75, 0),
                "annual_cost_r": round(current_kwh * 365 * 0.75 * ENERGY_RATE_R_PER_KWH, 2),
            },
            "annual_savings_r": round(annual_savings_r, 2),
            "annual_savings_co2_kg": round(annual_savings_kwh * 0.35, 0),  # SA grid intensity
            "investment_cost_r": investment_r,
            "payback_months": round(payback_months, 1),
            "roi_pct": round((annual_savings_r / investment_r * 100) if investment_r > 0 else 0, 1),
            "difficulty": DIFFICULTY_DALI_RETROFIT,
            "confidence": round(confidence, 2),
            "implementation_timeline_weeks": 4,
            "benefits": [
                f"Save R{annual_savings_r:,.0f}/year on electricity",
                "Reduce CO2 emissions by 24.8 tonnes/year",
                "Improve occupant comfort with daylight harvesting",
                "Meet sustainability goals (LEED/GBCSA)",
            ],
            "risks": [
                "Electrical system disruption during installation",
                "Learning curve for control system",
            ],
            "next_steps": [
                "1. Get lighting audit (2 weeks)",
                "2. Design DALI retrofit (1 week)",
                "3. Procurement (2 weeks)",
                "4. Installation & testing (4 weeks)",
            ],
            "messaging": {
                "short": f"Save R{annual_savings_r / 12:,.0f}/month with smart lighting",
                "long": (
                    f"Install DALI controls to reduce lighting energy by "
                    f"{(1 - current_kwh / baseline_kwh) * 100:.0f}%. "
                    f"Pays back in {payback_months:.1f} months."
                ),
                "urgency": "medium",
            },
        }

    async def _calculate_water_recommendation(
        self,
        current_liters: float,
    ) -> dict[str, Any] | None:
        """Calculate water efficiency recommendation."""
        baseline_liters = BASELINE_WATER_LITERS_PER_DAY
        savings_liters_per_day = baseline_liters - current_liters

        if savings_liters_per_day < 100.0:
            return None  # Insufficient savings

        annual_savings_liters = savings_liters_per_day * 365
        water_cost_r_per_liter = WATER_RATE_R_PER_LITER + WATER_SEWERAGE_RATE_R_PER_LITER
        annual_savings_r = annual_savings_liters * water_cost_r_per_liter
        investment_r = WATER_EFFICIENCY_RETROFIT_COST_R
        payback_months = (investment_r / annual_savings_r * 12) if annual_savings_r > 0 else 0

        confidence = min(0.88, CONFIDENCE_HIGH)  # Water efficiency well-proven

        return {
            "type": RecommendationType.WATER_EFFICIENCY,
            "rank": None,
            "priority": None,
            "title": "Water Efficiency Retrofit (Low-Flow Fixtures)",
            "description": (
                f"Install low-flow toilets, faucets, and fixtures. "
                f"Current consumption {current_liters / 1000:.1f} kL/day can be reduced "
                f"by {(1 - current_liters / baseline_liters) * 100:.0f}%."
            ),
            "current_state": {
                "daily_liters": round(current_liters, 0),
                "annual_liters": round(current_liters * 365, 0),
                "annual_cost_r": round(current_liters * 365 * water_cost_r_per_liter, 2),
            },
            "optimized_state": {
                "daily_liters": round(baseline_liters * 0.75, 0),  # 25% reduction typical
                "annual_liters": round(baseline_liters * 365 * 0.75, 0),
                "annual_cost_r": round(baseline_liters * 365 * 0.75 * water_cost_r_per_liter, 2),
            },
            "annual_savings_r": round(annual_savings_r, 2),
            "annual_savings_kliters": round(annual_savings_liters / 1000, 2),
            "investment_cost_r": investment_r,
            "payback_months": round(payback_months, 1),
            "roi_pct": round((annual_savings_r / investment_r * 100) if investment_r > 0 else 0, 1),
            "difficulty": DIFFICULTY_WATER_RETROFIT,
            "confidence": round(confidence, 2),
            "implementation_timeline_weeks": 3,
            "benefits": [
                f"Save R{annual_savings_r:,.0f}/year on water + sewerage",
                f"Reduce water consumption by {annual_savings_liters / 1000:.0f} kL/year",
                "Reduce municipal water strain",
                "Lower carbon footprint (water treatment)",
            ],
            "risks": [
                "Occupant adjustment to lower pressure",
                "Periodic maintenance (aerator cleaning)",
            ],
            "next_steps": [
                "1. Water audit by technician (1 week)",
                "2. Fixture specification & procurement (1 week)",
                "3. Installation & testing (2 weeks)",
            ],
            "messaging": {
                "short": f"Save R{annual_savings_r / 12:,.0f}/month with water efficiency",
                "long": (
                    f"Install low-flow fixtures to reduce water consumption "
                    f"by {(1 - current_liters / baseline_liters) * 100:.0f}%. "
                    f"Pays back in {payback_months:.1f} months."
                ),
                "urgency": "medium",
            },
        }

    async def _calculate_hvac_recommendation(
        self,
        current_cop: float,
    ) -> dict[str, Any] | None:
        """Calculate HVAC maintenance recommendation (COP degradation)."""
        cop_loss_pct = (1.0 - current_cop / BASELINE_HVAC_COP) * 100

        if cop_loss_pct < 5.0:
            return None  # Minimal degradation

        # Estimate cost impact
        # Cooling load ~45 kW, so power = load / COP
        baseline_power_kw = 45.0 / BASELINE_HVAC_COP  # ~12.9 kW
        current_power_kw = 45.0 / current_cop  # ~15.5 kW at COP 2.9
        additional_power_kw = current_power_kw - baseline_power_kw

        annual_additional_kwh = additional_power_kw * 24 * 365
        annual_cost_increase_r = annual_additional_kwh * ENERGY_RATE_R_PER_KWH

        investment_r = MAINTENANCE_COST_R
        annual_savings_r = annual_cost_increase_r  # Savings = avoided cost increase
        payback_months = (investment_r / annual_savings_r * 12) if annual_savings_r > 0 else 0

        # High confidence if COP loss is significant
        confidence = min(0.90 + (cop_loss_pct / 100), 0.95)

        return {
            "type": RecommendationType.HVAC_MAINTENANCE,
            "rank": None,
            "priority": None,
            "title": "Emergency: Chiller Maintenance Required",
            "description": (
                f"Chiller COP degraded from {BASELINE_HVAC_COP} to {current_cop:.1f} ({cop_loss_pct:.0f}% loss). "
                f"Likely causes: fouled condenser, low refrigerant, compressor wear. "
                f"Annual cost impact: R{annual_cost_increase_r:,.0f}."
            ),
            "current_state": {
                "cop": round(current_cop, 2),
                "power_kw": round(current_power_kw, 2),
                "daily_cost_increase_r": round(additional_power_kw * 24 * ENERGY_RATE_R_PER_KWH, 2),
            },
            "optimized_state": {
                "cop": BASELINE_HVAC_COP,
                "power_kw": round(baseline_power_kw, 2),
                "daily_cost_increase_r": 0.0,
            },
            "annual_savings_r": round(annual_savings_r, 2),
            "annual_cost_avoided_kwh": round(annual_additional_kwh, 0),
            "investment_cost_r": investment_r,
            "payback_months": round(payback_months, 1),
            "roi_pct": round((annual_savings_r / investment_r * 100) if investment_r > 0 else 0, 1),
            "difficulty": DIFFICULTY_HVAC_MAINTENANCE,
            "confidence": round(confidence, 2),
            "implementation_timeline_weeks": 1,
            "benefits": [
                f"Avoid R{annual_cost_increase_r:,.0f}/year energy cost increase",
                "Restore equipment to design efficiency",
                "Prevent catastrophic failure",
                "Improve cooling consistency",
            ],
            "risks": [
                "HVAC downtime during service (typically 4-8 hours)",
                "Possible part replacement needed",
            ],
            "next_steps": [
                "1. Call HVAC service provider (TODAY)",
                "2. Schedule emergency inspection (within 48 hours)",
                "3. Perform maintenance: condenser cleaning, refrigerant check",
                "4. Verify COP recovery post-service",
            ],
            "messaging": {
                "short": f"⚠️ URGENT: Maintenance needed - COP degraded {cop_loss_pct:.0f}%",
                "long": (
                    f"Chiller maintenance will prevent R{annual_cost_increase_r:,.0f}/year "
                    f"energy cost increase and system failure."
                ),
                "urgency": "critical",
            },
        }

    async def _calculate_occupancy_recommendation(
        self,
        anomalies_count: int,
        cost_variance_pct: float,
    ) -> dict[str, Any] | None:
        """Calculate occupancy optimization recommendation."""
        if anomalies_count == 0 and abs(cost_variance_pct) < 2.0:
            return None  # System running well

        potential_savings_pct = 8.0  # Conservative estimate from occupancy-aware scheduling
        daily_energy_cost = (315 + 185) * ENERGY_RATE_R_PER_KWH  # HVAC + Lighting
        daily_water_cost = 6847 * (WATER_RATE_R_PER_LITER + WATER_SEWERAGE_RATE_R_PER_LITER)
        daily_cost = daily_energy_cost + daily_water_cost

        annual_savings_r = daily_cost * 365 * (potential_savings_pct / 100)
        investment_r = 8000.0  # Smart building system/sensors
        payback_months = (investment_r / annual_savings_r * 12) if annual_savings_r > 0 else 0

        confidence = CONFIDENCE_MEDIUM  # Depends on occupancy patterns

        return {
            "type": RecommendationType.OCCUPANCY_OPTIMIZATION,
            "rank": None,
            "priority": None,
            "title": "Smart Occupancy Scheduling",
            "description": (
                "Implement real-time occupancy-based HVAC and lighting scheduling. "
                f"Potential savings: {potential_savings_pct}% through demand-responsive operation."
            ),
            "current_state": {
                "daily_total_cost_r": round(daily_cost, 2),
                "annual_cost_r": round(daily_cost * 365, 0),
                "occupancy_profile": "static (not optimized)",
            },
            "optimized_state": {
                "daily_total_cost_r": round(daily_cost * (1 - potential_savings_pct / 100), 2),
                "annual_cost_r": round(daily_cost * 365 * (1 - potential_savings_pct / 100), 0),
                "occupancy_profile": "dynamic (sensor-driven)",
            },
            "annual_savings_r": round(annual_savings_r, 2),
            "investment_cost_r": investment_r,
            "payback_months": round(payback_months, 1),
            "roi_pct": round((annual_savings_r / investment_r * 100) if investment_r > 0 else 0, 1),
            "difficulty": DIFFICULTY_OCCUPANCY_OPTIMIZATION,
            "confidence": round(confidence, 2),
            "implementation_timeline_weeks": 6,
            "benefits": [
                f"Save R{annual_savings_r:,.0f}/year through intelligent scheduling",
                "Improve occupant comfort (responsive to actual usage)",
                "Enable predictive maintenance (occupancy patterns)",
            ],
            "risks": [
                "Initial calibration period (2 weeks)",
                "Sensor maintenance and replacement",
            ],
            "next_steps": [
                "1. Occupancy pattern analysis (2 weeks)",
                "2. BMS integration design (2 weeks)",
                "3. Sensor installation (1 week)",
                "4. Commissioning & optimization (1 week)",
            ],
            "messaging": {
                "short": f"Save R{annual_savings_r / 12:,.0f}/month with smart scheduling",
                "long": (
                    f"Real-time occupancy-based control can reduce facility costs by {potential_savings_pct}%. "
                    f"Pays back in {payback_months:.1f} months."
                ),
                "urgency": "low",
            },
        }

    def _get_priority(self, rank: int, total: int) -> str:
        """Determine priority level from rank."""
        if rank == 1:
            return "urgent"
        elif rank <= total * 0.33:
            return "high"
        elif rank <= total * 0.67:
            return "medium"
        else:
            return "low"


async def generate_ai_recommendations(
    site_id: str,
    lighting_kwh_current: float = 185.0,
    water_liters_current: float = 6847.0,
    hvac_cop_current: float = 3.5,
    power_anomalies_count: int = 0,
    cost_variance_pct: float = 0.18,
) -> dict[str, Any]:
    """Public API for AI recommendation generation.

    Args:
        site_id: Building/site ID
        lighting_kwh_current: Current daily lighting energy
        water_liters_current: Current daily water consumption
        hvac_cop_current: Current chiller COP
        power_anomalies_count: Number of power anomalies detected
        cost_variance_pct: Cost model variance

    Returns:
        Ranked recommendations with ROI and messaging
    """
    engine = AIRecommendationEngine(site_id)
    return await engine.generate_recommendations(
        lighting_kwh_current=lighting_kwh_current,
        water_liters_current=water_liters_current,
        hvac_cop_current=hvac_cop_current,
        power_anomalies_count=power_anomalies_count,
        cost_variance_pct=cost_variance_pct,
    )


def get_ai_recommendation_engine(site_id: str) -> AIRecommendationEngine:
    """Get singleton instance of AIRecommendationEngine.

    Args:
        site_id: Building identifier

    Returns:
        AIRecommendationEngine instance
    """
    return AIRecommendationEngine(site_id)
