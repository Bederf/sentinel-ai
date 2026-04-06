"""Cost validation and tariff adjustment engine.

Compares simulated energy/water costs with real municipal invoices
to validate tariff assumptions and fine-tune billing calculations.

Model:
  Invoice Matching: Correlate simulated daily costs with monthly invoices
  Tariff Validation: Verify tiered pricing assumptions
  Variance Analysis: Track billing accuracy over time
  Adjustment Factors: Auto-detect and recommend tariff tweaks

Integration: Called daily at hour 23 with invoice data when available.
Output: Cost variance reports, tariff adjustment recommendations.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from app.database.supabase_client import get_supabase_client
from app.services.simulation_store import get_simulation_store

# Demo fixture path
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

logger = logging.getLogger(__name__)

# Cost variance thresholds
COST_VARIANCE_THRESHOLD_PCT = 5.0  # Flag >5% cost deviation
COST_CRITICAL_VARIANCE_PCT = 15.0  # Critical if >15% off
MINIMUM_INVOICE_RECORDS = 3  # Months of data needed

# Tariff adjustment parameters
TARIFF_CONFIDENCE_MIN = 0.75  # Minimum confidence for adjustment
TARIFF_ADJUSTMENT_MAX_PCT = 10.0  # Max tariff change per adjustment


class CostValidationEngine:
    """Engine for validating simulated costs against real invoices."""

    def __init__(self, site_id: str):
        """Initialize cost validation engine.

        Args:
            site_id: Building/site identifier (e.g., 'site-002')
        """
        self.site_id = site_id
        self.client = get_supabase_client()
        self.sim_store = get_simulation_store(site_id)

    async def get_daily_simulated_cost(
        self,
        energy_kwh: float,
        water_liters: float,
        cost_date: datetime,
    ) -> dict[str, Any]:
        """Calculate daily cost from simulated consumption using current tariffs.

        Args:
            energy_kwh: Daily energy consumption
            water_liters: Daily water consumption
            cost_date: Date for tariff selection

        Returns:
            Daily cost breakdown (energy, water, total)
        """
        try:
            # Get current tariffs
            month = cost_date.month
            season = "winter" if month in [6, 7, 8] else "summer"

            # Energy cost (City Power TOU tariff)
            energy_cost = await self._calculate_energy_cost(energy_kwh, season)

            # Water cost (Johannesburg municipal)
            water_cost = await self._calculate_water_cost(water_liters)

            total_cost = energy_cost["total_cost_r"] + water_cost["total_cost_r"]

            return {
                "date": cost_date.date().isoformat(),
                "energy_kwh": round(energy_kwh, 2),
                "water_liters": round(water_liters, 2),
                "energy_cost_r": round(energy_cost["total_cost_r"], 2),
                "water_cost_r": round(water_cost["total_cost_r"], 2),
                "total_cost_r": round(total_cost, 2),
                "season": season,
            }

        except Exception as e:
            logger.error(f"Error calculating daily cost: {e}")
            return {
                "date": cost_date.date().isoformat(),
                "error": str(e),
                "total_cost_r": 0.0,
            }

    async def _calculate_energy_cost(self, kwh: float, season: str) -> dict[str, float]:
        """Calculate energy cost using TOU tariff."""
        # Johannesburg City Power commercial TOU rates (simplified to average)
        if season == "summer":
            rate_r_kwh = 2.159  # Average summer rate
        else:
            rate_r_kwh = 2.285  # Average winter rate (slightly higher)

        energy_cost = kwh * rate_r_kwh
        service_charge = 9.50  # Daily allocation

        return {
            "energy_cost_r": round(energy_cost, 2),
            "service_charge_r": round(service_charge, 2),
            "total_cost_r": round(energy_cost + service_charge, 2),
        }

    async def _calculate_water_cost(self, liters: float) -> dict[str, float]:
        """Calculate water cost using Johannesburg tiered tariff."""
        # Tier thresholds (daily allocation of monthly)
        tier_1_daily = 100000 / 30  # First tier
        tier_2_daily = 500000 / 30  # Second tier

        # Rates per liter
        rate_tier_1 = 0.00795  # R7.95/kL
        rate_tier_2 = 0.01250  # R12.50/kL
        rate_tier_3 = 0.01895  # R18.95/kL
        rate_sewerage = 0.00630  # R6.30/kL

        # Calculate tiered cost
        tier_1_liters = min(liters, tier_1_daily)
        tier_1_cost = tier_1_liters * rate_tier_1

        tier_2_liters = 0.0
        tier_2_cost = 0.0
        if liters > tier_1_daily:
            tier_2_liters = min(liters - tier_1_daily, tier_2_daily - tier_1_daily)
            tier_2_cost = tier_2_liters * rate_tier_2

        tier_3_liters = 0.0
        tier_3_cost = 0.0
        if liters > tier_2_daily:
            tier_3_liters = liters - tier_2_daily
            tier_3_cost = tier_3_liters * rate_tier_3

        sewerage_cost = liters * rate_sewerage
        fixed_daily = 285.00 / 30

        total_cost = tier_1_cost + tier_2_cost + tier_3_cost + sewerage_cost + fixed_daily

        return {
            "tier_1_cost_r": round(tier_1_cost, 2),
            "tier_2_cost_r": round(tier_2_cost, 2),
            "tier_3_cost_r": round(tier_3_cost, 2),
            "sewerage_cost_r": round(sewerage_cost, 2),
            "fixed_charge_r": round(fixed_daily, 2),
            "total_cost_r": round(total_cost, 2),
        }

    async def validate_daily_cost(
        self,
        simulated_date: datetime,
        daily_cost: Any,
    ) -> dict[str, Any]:
        """Validate daily cost against running average.

        Called by thermal engine at hour 23 after daily cost is calculated.
        Compares today's cost to the running average to detect anomalies.

        Args:
            simulated_date: The date being validated
            daily_cost: Daily cost dict from EnergyCostService (or numeric value)

        Returns:
            Validation result dict with status and variance
        """
        try:
            # Extract the cost value
            if isinstance(daily_cost, dict):
                cost_r = float(daily_cost.get("total_cost_r", 0))
            elif isinstance(daily_cost, (int, float)):
                cost_r = float(daily_cost)
            else:
                return {
                    "validation_status": "skipped",
                    "reason": "invalid_cost_data",
                    "date": simulated_date.date().isoformat()
                    if hasattr(simulated_date, "date")
                    else str(simulated_date),
                }

            if cost_r <= 0:
                return {
                    "validation_status": "skipped",
                    "reason": "zero_cost",
                    "date": simulated_date.date().isoformat()
                    if hasattr(simulated_date, "date")
                    else str(simulated_date),
                }

            # Get expected daily cost from invoices / running average
            expected_daily_cost = await self._get_expected_daily_cost()

            # Calculate variance
            if expected_daily_cost > 0:
                variance_pct = abs(cost_r - expected_daily_cost) / expected_daily_cost * 100
            else:
                variance_pct = 0.0

            # Determine status
            if variance_pct > COST_CRITICAL_VARIANCE_PCT:
                status = "critical"
                severity = "critical"
            elif variance_pct > COST_VARIANCE_THRESHOLD_PCT:
                status = "warning"
                severity = "warning"
            else:
                status = "validated"
                severity = "healthy"

            result_date = simulated_date.date().isoformat() if hasattr(simulated_date, "date") else str(simulated_date)

            return {
                "validation_status": status,
                "severity": severity,
                "date": result_date,
                "daily_cost_r": round(cost_r, 2),
                "expected_daily_cost_r": round(expected_daily_cost, 2),
                "variance_pct": round(variance_pct, 2),
                "variance_direction": "over" if cost_r > expected_daily_cost else "under",
            }

        except Exception as e:
            logger.warning(f"Error in validate_daily_cost: {e}")
            return {
                "validation_status": "error",
                "error": str(e),
                "date": simulated_date.date().isoformat() if hasattr(simulated_date, "date") else str(simulated_date),
                "variance_pct": 0.0,
            }

    async def _get_expected_daily_cost(self) -> float:
        """Get expected daily cost from invoices or seeded data.

        Returns average daily cost from the most recent invoice data.
        Falls back to seeded fixtures if no real data available.
        """
        try:
            # Try to get from real invoice data in database
            response = (
                self.client.table("cost_validations")
                .select("real_cost_r, period_start, period_end")
                .eq("site_id", self.site_id)
                .order("period_end", desc=True)
                .limit(3)
                .execute()
            )

            records = response.data or []
            if records:
                # Average the monthly costs and divide by 30 for daily
                monthly_costs = [float(r["real_cost_r"]) for r in records if r.get("real_cost_r")]
                if monthly_costs:
                    return mean(monthly_costs) / 30.0

        except Exception as e:
            logger.debug(f"Could not get real invoice data: {e}")

        # Fallback: try seeded fixtures (3-tier: Supabase -> Cache -> JSON)
        try:
            fixture_path = _DATA_DIR / "demo_monthly_invoices.json"
            if fixture_path.exists():
                with open(fixture_path) as f:
                    invoices = json.load(f)
                if invoices:
                    monthly_costs = [float(inv["total_cost_r"]) for inv in invoices if inv.get("total_cost_r")]
                    if monthly_costs:
                        avg_monthly = mean(monthly_costs)
                        return avg_monthly / 30.0
        except Exception as e:
            logger.debug(f"Could not load seeded invoices: {e}")

        # Hardcoded fallback: estimate from typical commercial rate
        # ~315 kWh/day * R5/kWh = ~R1,575/day
        return 1575.0

    async def validate_monthly_cost(
        self,
        month: int,
        year: int,
        real_invoice_cost_r: float,
        simulated_total_kwh: float | None = None,
        simulated_total_water_liters: float | None = None,
    ) -> dict[str, Any]:
        """Validate simulated monthly cost against real invoice.

        Args:
            month: Month (1-12)
            year: Year
            real_invoice_cost_r: Actual invoice amount
            simulated_total_kwh: Simulated energy consumption
            simulated_total_water_liters: Simulated water consumption

        Returns:
            Monthly validation with variance and recommendations
        """
        try:
            # Get simulated costs from database if not provided
            if simulated_total_kwh is None or simulated_total_water_liters is None:
                simulated_cost_r = await self._get_simulated_monthly_cost(month, year)
            else:
                # Calculate from provided consumption
                start_date = datetime(year, month, 1)
                simulated_breakdown = await self.get_daily_simulated_cost(
                    simulated_total_kwh, simulated_total_water_liters, start_date
                )
                simulated_cost_r = simulated_breakdown.get("total_cost_r", 0.0)

            # Calculate variance
            if real_invoice_cost_r > 0:
                variance_pct = abs(simulated_cost_r - real_invoice_cost_r) / real_invoice_cost_r * 100
            else:
                variance_pct = 0.0

            # Determine status
            if variance_pct > COST_CRITICAL_VARIANCE_PCT:
                status = "critical"
                severity = "critical"
            elif variance_pct > COST_VARIANCE_THRESHOLD_PCT:
                status = "warning"
                severity = "warning"
            else:
                status = "validated"
                severity = "healthy"

            # Generate recommendation
            recommendation = self._get_cost_recommendation(variance_pct, simulated_cost_r, real_invoice_cost_r)

            result = {
                "validation_status": status,
                "severity": severity,
                "month": month,
                "year": year,
                "period": f"{year}-{month:02d}",
                "real_invoice_cost_r": round(real_invoice_cost_r, 2),
                "simulated_cost_r": round(simulated_cost_r, 2),
                "variance_pct": round(variance_pct, 2),
                "variance_r": round(simulated_cost_r - real_invoice_cost_r, 2),
                "variance_direction": "over" if simulated_cost_r > real_invoice_cost_r else "under",
                "recommendation": recommendation,
            }

            # Write validation record if significant variance
            if status != "validated":
                await self._write_cost_validation_record(result)

            return result

        except Exception as e:
            logger.error(f"Error validating monthly cost: {e}")
            return {
                "validation_status": "error",
                "month": month,
                "year": year,
                "error": str(e),
            }

    def _get_cost_recommendation(
        self,
        variance_pct: float,
        simulated_cost: float,
        real_cost: float,
    ) -> str:
        """Generate actionable recommendation for cost variance."""
        if variance_pct < COST_VARIANCE_THRESHOLD_PCT:
            return "Cost simulation validated - tariffs accurate"

        if simulated_cost > real_cost * 1.1:
            return (
                "Simulation overestimating costs (likely overestimating consumption). "
                "Review: COP assumptions, HVAC runtime, occupancy patterns."
            )
        elif simulated_cost < real_cost * 0.9:
            return (
                "Simulation underestimating costs. "
                "Possible causes: Additional loads not modeled, tariff change, "
                "or meter includes common area consumption."
            )
        else:
            return f"Cost variance {variance_pct:.1f}% detected. Requires investigation."

    async def _write_cost_validation_record(
        self,
        validation_result: dict[str, Any],
    ) -> None:
        """Write cost validation record to database."""
        try:
            record = {
                "site_id": self.site_id,
                "period": validation_result["period"],
                "validation_status": validation_result["validation_status"],
                "severity": validation_result["severity"],
                "real_cost_r": validation_result["real_invoice_cost_r"],
                "simulated_cost_r": validation_result["simulated_cost_r"],
                "variance_pct": validation_result["variance_pct"],
                "recommendation": validation_result["recommendation"],
                "created_at": datetime.now().isoformat(),
            }

            # Write to simulation store (JSON), not Supabase
            self.sim_store.write_validation("cost", record)

        except Exception as e:
            logger.debug(f"Could not write cost validation record: {e}")

    async def _get_simulated_monthly_cost(self, month: int, year: int) -> float:
        """Get total simulated cost for a month from database."""
        try:
            # Query energy_cost_summary for the month
            response = (
                self.client.table("energy_cost_summary")
                .select("total_cost_r")
                .eq("site_id", self.site_id)
                .gte("date", f"{year}-{month:02d}-01")
                .lt("date", f"{year}-{month:02d + 1:02d}-01" if month < 12 else f"{year + 1}-01-01")
                .execute()
            )

            costs = response.data or []
            return sum(float(c["total_cost_r"]) for c in costs) if costs else 0.0

        except Exception as e:
            logger.warning(f"Could not get simulated monthly cost: {e}")
            return 0.0

    async def get_tariff_adjustment_recommendation(
        self,
        historical_validations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Recommend tariff adjustments based on historical variance.

        Args:
            historical_validations: List of monthly validation records

        Returns:
            Tariff adjustment recommendation with confidence score
        """
        if len(historical_validations) < MINIMUM_INVOICE_RECORDS:
            return {
                "adjustment_needed": False,
                "reason": "insufficient_data",
                "records_analyzed": len(historical_validations),
                "minimum_required": MINIMUM_INVOICE_RECORDS,
            }

        try:
            variances = [v["variance_pct"] for v in historical_validations if v.get("variance_pct") is not None]

            if not variances:
                return {
                    "adjustment_needed": False,
                    "reason": "no_variance_data",
                }

            avg_variance = mean(variances)
            variance_stdev = stdev(variances) if len(variances) > 1 else 0.0

            # Determine if consistent bias exists
            if avg_variance < 1.0:
                return {
                    "adjustment_needed": False,
                    "avg_variance_pct": round(avg_variance, 2),
                    "reason": "tariffs_accurate",
                    "confidence": 0.95,
                }

            # Check for consistent direction bias
            over_count = sum(1 for v in historical_validations if v.get("variance_direction") == "over")
            under_count = len(historical_validations) - over_count
            bias_direction = "over" if over_count > under_count else "under"
            bias_consistency = max(over_count, under_count) / len(historical_validations)

            if bias_consistency < 0.7:
                return {
                    "adjustment_needed": False,
                    "avg_variance_pct": round(avg_variance, 2),
                    "reason": "inconsistent_variance",
                    "confidence": 0.5,
                }

            # Calculate adjustment factor
            adjustment_factor = 1.0 + (avg_variance / 100.0)
            adjustment_factor = max(0.9, min(1.1, adjustment_factor))  # Limit to ±10%
            adjustment_pct = (adjustment_factor - 1.0) * 100

            return {
                "adjustment_needed": abs(adjustment_pct) >= 1.0,
                "avg_variance_pct": round(avg_variance, 2),
                "variance_stdev_pct": round(variance_stdev, 2),
                "bias_direction": bias_direction,
                "bias_consistency_pct": round(bias_consistency * 100, 1),
                "recommended_adjustment_pct": round(adjustment_pct, 2),
                "current_tariff_multiplier": 1.0,
                "recommended_tariff_multiplier": round(adjustment_factor, 4),
                "confidence": round(bias_consistency, 2),
                "records_analyzed": len(historical_validations),
            }

        except Exception as e:
            logger.error(f"Error calculating tariff adjustment: {e}")
            return {
                "adjustment_needed": False,
                "error": str(e),
            }


async def validate_cost(
    site_id: str,
    month: int,
    year: int,
    real_invoice_cost_r: float,
    simulated_total_kwh: float | None = None,
    simulated_total_water_liters: float | None = None,
) -> dict[str, Any]:
    """Public API for cost validation.

    Args:
        site_id: Building/site ID
        month: Month (1-12)
        year: Year
        real_invoice_cost_r: Real invoice amount
        simulated_total_kwh: Simulated energy
        simulated_total_water_liters: Simulated water

    Returns:
        Monthly validation with variance analysis
    """
    engine = CostValidationEngine(site_id)
    return await engine.validate_monthly_cost(
        month=month,
        year=year,
        real_invoice_cost_r=real_invoice_cost_r,
        simulated_total_kwh=simulated_total_kwh,
        simulated_total_water_liters=simulated_total_water_liters,
    )


def get_cost_validation_engine(site_id: str) -> CostValidationEngine:
    """Get singleton instance of CostValidationEngine.

    Args:
        site_id: Building identifier

    Returns:
        CostValidationEngine instance
    """
    return CostValidationEngine(site_id)
