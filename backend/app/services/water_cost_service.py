"""Water cost calculation and forecasting service.

Manages cost tracking, tiered billing calculations, and cost forecasting
for water consumption with zone-based attribution.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from app.database.repositories.water_consumption_repository import WaterConsumptionRepository
from app.database.repositories.water_cost_repository import WaterCostRepository
from app.models.water_meter import WaterConsumption, WaterCost

logger = logging.getLogger(__name__)


class WaterCostService:
    """Service for water cost calculation, billing, and forecasting."""

    def __init__(
        self,
        cost_repository: WaterCostRepository | None = None,
        consumption_repository: WaterConsumptionRepository | None = None,
    ):
        """Initialize service with repositories.

        Args:
            cost_repository: WaterCostRepository instance (created if None)
            consumption_repository: WaterConsumptionRepository instance (created if None)
        """
        self.cost_repo = cost_repository or WaterCostRepository()
        self.consumption_repo = consumption_repository or WaterConsumptionRepository()

    async def calculate_consumption_cost(
        self,
        consumption: WaterConsumption,
        site: str,
    ) -> WaterCost:
        """Calculate and persist cost for a consumption record.

        Args:
            consumption: WaterConsumption record
            site: Building site code

        Returns:
            WaterCost record with all tier costs calculated
        """
        try:
            # Get active tariff for consumption date
            tariff = await self.cost_repo.get_active_tariff(site, consumption.timestamp)
            if not tariff:
                logger.warning(f"No active tariff found for {site} on {consumption.timestamp}")
                return None

            # Calculate tiered cost
            cost_breakdown = self.cost_repo.calculate_cost(consumption.volume_liters, tariff)

            # Create cost record
            cost = WaterCost(
                site=site,
                consumption_id=consumption.meter_id,  # Link to consumption record
                zone_id=consumption.zone_id,
                period_date=consumption.timestamp,
                consumption_liters=consumption.volume_liters,
                tariff_id=tariff.id,
                tier_1_cost=cost_breakdown["tier_1_cost"],
                tier_2_cost=cost_breakdown["tier_2_cost"],
                tier_3_cost=cost_breakdown["tier_3_cost"],
                fixed_charge=cost_breakdown["fixed_charge"],
                total_cost=cost_breakdown["total_cost"],
                calculated_at=datetime.now(),
            )

            # Persist cost record
            try:
                if hasattr(self.cost_repo, "client") and self.cost_repo.client:
                    response = self.cost_repo.client.table("water_costs").insert(cost.to_dict()).execute()
                    if response.data:
                        return WaterCost.from_dict(response.data[0])
            except Exception as e:
                logger.warning(f"Could not persist cost to Supabase: {e}, using JSON fallback")

            # Save to JSON fallback
            backup = self.cost_repo._load_json_backup(site, "costs")
            if "costs" not in backup:
                backup["costs"] = []
            backup["costs"].append(cost.to_dict())
            self.cost_repo._save_json_backup(site, backup, "costs")

            return cost

        except Exception as e:
            logger.error(f"Error calculating consumption cost: {e}")
            return None

    async def forecast_monthly_cost(
        self,
        site: str,
        zone_id: str | None = None,
    ) -> dict[str, Any]:
        """Forecast monthly cost based on recent consumption.

        Args:
            site: Building site code
            zone_id: Optional zone filter

        Returns:
            Dict with consumption, cost, and forecast details
        """
        try:
            # Get last 7 days of consumption for baseline
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)

            # Get consumption records
            try:
                if hasattr(self.consumption_repo, "client") and self.consumption_repo.client:
                    response = (
                        self.consumption_repo.client.table("water_consumption")
                        .select("*")
                        .eq("site", site)
                        .gte("timestamp", start_date.isoformat())
                        .lte("timestamp", end_date.isoformat())
                        .execute()
                    )
                    records = response.data or []
                else:
                    records = []
            except Exception as e:
                logger.warning(f"Could not query Supabase: {e}, using JSON fallback")
                records = []

            if zone_id:
                records = [r for r in records if r.get("zone_id") == zone_id]

            if not records:
                return {
                    "site": site,
                    "zone_id": zone_id,
                    "period": "monthly",
                    "consumption_liters": 0,
                    "cost": 0,
                    "confidence": "low",
                    "assumptions": ["No recent consumption data available"],
                }

            # Calculate daily average consumption
            total_consumption = sum(r.get("volume_liters", 0) for r in records)
            daily_avg = total_consumption / 7

            # Get active tariff
            tariff = await self.cost_repo.get_active_tariff(site, end_date)
            if not tariff:
                return {
                    "site": site,
                    "zone_id": zone_id,
                    "period": "monthly",
                    "consumption_liters": 0,
                    "cost": 0,
                    "confidence": "low",
                    "assumptions": ["No active tariff configured"],
                }

            # Project to 30-day month
            monthly_consumption = daily_avg * 30
            cost_breakdown = self.cost_repo.calculate_cost(monthly_consumption, tariff)

            assumptions = [
                f"Based on {len(records)} consumption records from last 7 days",
                f"Daily average: {round(daily_avg, 2)} L/day",
                f"Tariff: {tariff.name} (effective {tariff.effective_date.date()})",
            ]

            return {
                "site": site,
                "zone_id": zone_id,
                "period": "monthly",
                "consumption_liters": round(monthly_consumption, 2),
                "tier_1_cost": cost_breakdown["tier_1_cost"],
                "tier_2_cost": cost_breakdown["tier_2_cost"],
                "tier_3_cost": cost_breakdown["tier_3_cost"],
                "fixed_charge": cost_breakdown["fixed_charge"],
                "total_cost": cost_breakdown["total_cost"],
                "confidence": "high",
                "assumptions": assumptions,
            }

        except Exception as e:
            logger.error(f"Error forecasting monthly cost for {site}: {e}")
            return {
                "site": site,
                "zone_id": zone_id,
                "period": "monthly",
                "consumption_liters": 0,
                "total_cost": 0,
                "confidence": "low",
                "assumptions": ["Error during forecast calculation"],
            }

    async def forecast_annual_cost(
        self,
        site: str,
        zone_id: str | None = None,
    ) -> dict[str, Any]:
        """Forecast annual cost based on recent patterns.

        Args:
            site: Building site code
            zone_id: Optional zone filter

        Returns:
            Dict with annual projection
        """
        try:
            # Get last 30 days of consumption
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)

            # Get consumption records
            try:
                if hasattr(self.consumption_repo, "client") and self.consumption_repo.client:
                    response = (
                        self.consumption_repo.client.table("water_consumption")
                        .select("*")
                        .eq("site", site)
                        .gte("timestamp", start_date.isoformat())
                        .lte("timestamp", end_date.isoformat())
                        .execute()
                    )
                    records = response.data or []
                else:
                    records = []
            except Exception as e:
                logger.warning(f"Could not query Supabase: {e}, using JSON fallback")
                records = []

            if zone_id:
                records = [r for r in records if r.get("zone_id") == zone_id]

            if not records:
                return {
                    "site": site,
                    "zone_id": zone_id,
                    "period": "annual",
                    "projected_consumption": 0,
                    "projected_cost": 0,
                    "confidence": "low",
                }

            # Calculate monthly average
            total_consumption = sum(r.get("volume_liters", 0) for r in records)
            monthly_avg = total_consumption / (30 / 7)  # Normalize 30 days to months

            # Get active tariff
            tariff = await self.cost_repo.get_active_tariff(site, end_date)
            if not tariff:
                return {
                    "site": site,
                    "zone_id": zone_id,
                    "period": "annual",
                    "projected_consumption": 0,
                    "projected_cost": 0,
                    "confidence": "low",
                }

            # Project to 12-month year
            annual_consumption = monthly_avg * 12
            cost_breakdown = self.cost_repo.calculate_cost(annual_consumption, tariff)

            return {
                "site": site,
                "zone_id": zone_id,
                "period": "annual",
                "year": end_date.year,
                "projected_consumption": round(annual_consumption, 2),
                "tier_1_cost": cost_breakdown["tier_1_cost"],
                "tier_2_cost": cost_breakdown["tier_2_cost"],
                "tier_3_cost": cost_breakdown["tier_3_cost"],
                "fixed_charge": cost_breakdown["fixed_charge"],
                "projected_cost": cost_breakdown["total_cost"],
                "confidence": "medium",
            }

        except Exception as e:
            logger.error(f"Error forecasting annual cost for {site}: {e}")
            return {
                "site": site,
                "zone_id": zone_id,
                "period": "annual",
                "projected_consumption": 0,
                "projected_cost": 0,
                "confidence": "low",
            }

    async def get_zone_cost_comparison(
        self,
        site: str,
        period_days: int = 30,
    ) -> list[dict[str, Any]]:
        """Compare costs across zones at a site.

        Args:
            site: Building site code
            period_days: Look-back period in days

        Returns:
            List of zones sorted by cost (highest first)
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days)

            # Get all costs for site in period
            try:
                if hasattr(self.cost_repo, "client") and self.cost_repo.client:
                    response = (
                        self.cost_repo.client.table("water_costs")
                        .select("*")
                        .eq("site", site)
                        .gte("period_date", start_date.isoformat())
                        .lte("period_date", end_date.isoformat())
                        .execute()
                    )
                    costs = response.data or []
                else:
                    costs = []
            except Exception as e:
                logger.warning(f"Could not query Supabase: {e}")
                costs = []

            # Group by zone
            zone_totals = {}
            for cost in costs:
                zone = cost.get("zone_id", "unassigned")
                if zone not in zone_totals:
                    zone_totals[zone] = {
                        "consumption": 0,
                        "cost": 0,
                        "count": 0,
                    }
                zone_totals[zone]["consumption"] += cost.get("consumption_liters", 0)
                zone_totals[zone]["cost"] += cost.get("total_cost", 0)
                zone_totals[zone]["count"] += 1

            # Format and rank
            result = []
            for zone, data in sorted(zone_totals.items(), key=lambda x: x[1]["cost"], reverse=True):
                cost_per_liter = data["cost"] / data["consumption"] if data["consumption"] > 0 else 0
                result.append(
                    {
                        "zone_id": zone,
                        "consumption_liters": round(data["consumption"], 2),
                        "total_cost": round(data["cost"], 2),
                        "cost_per_liter": round(cost_per_liter, 4),
                        "records": data["count"],
                        "rank": len(result) + 1,
                    }
                )

            return result

        except Exception as e:
            logger.error(f"Error comparing zone costs for {site}: {e}")
            return []

    async def calculate_cost_impact(
        self,
        consumption_reduction_liters: float,
        site: str,
        period_days: int = 30,
    ) -> dict[str, Any]:
        """Simulate cost savings from consumption reduction.

        Args:
            consumption_reduction_liters: Target reduction volume
            site: Building site code
            period_days: Base period for analysis

        Returns:
            Dict with current cost, reduced cost, and savings
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days)

            # Get current costs
            current_costs = await self.cost_repo.get_site_costs(site, start_date, end_date)
            current_total = current_costs.get("total_cost", 0)

            # Get active tariff
            tariff = await self.cost_repo.get_active_tariff(site, end_date)
            if not tariff:
                return {
                    "site": site,
                    "current_cost": current_total,
                    "reduced_cost": current_total,
                    "savings": 0,
                    "savings_percent": 0,
                }

            # Calculate reduced cost
            # Approximate: assume reduction applies to most expensive tier
            estimated_reduction_cost = min(
                consumption_reduction_liters * tariff.tier_3_rate_per_liter,
                current_total,
            )

            reduced_cost = max(0, current_total - estimated_reduction_cost)
            savings_percent = (estimated_reduction_cost / current_total * 100) if current_total > 0 else 0

            return {
                "site": site,
                "period_days": period_days,
                "current_cost": round(current_total, 2),
                "reduction_liters": round(consumption_reduction_liters, 2),
                "estimated_savings": round(estimated_reduction_cost, 2),
                "reduced_cost": round(reduced_cost, 2),
                "savings_percent": round(savings_percent, 1),
            }

        except Exception as e:
            logger.error(f"Error calculating cost impact for {site}: {e}")
            return {
                "site": site,
                "current_cost": 0,
                "reduced_cost": 0,
                "savings": 0,
                "savings_percent": 0,
            }


# Module-level getter for dependency injection
_water_cost_service: WaterCostService | None = None


def get_water_cost_service() -> WaterCostService:
    """Get or create water cost service singleton.

    Returns:
        WaterCostService instance
    """
    global _water_cost_service
    if _water_cost_service is None:
        _water_cost_service = WaterCostService()
    return _water_cost_service
