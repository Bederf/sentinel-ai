"""Repository for water tariff and cost management.

Implements dual-write pattern: Supabase (primary) + JSON file (backup).
Manages tariff configurations and cost calculations with tiered billing support.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.database.supabase_client import get_supabase_client
from app.models.water_meter import WaterTariff

logger = logging.getLogger(__name__)


class WaterCostRepository:
    """Repository for water tariff and cost data with dual-write support."""

    def __init__(self, supabase_client=None, use_json=False):
        """Initialize repository with optional Supabase override."""
        self.client = supabase_client or get_supabase_client()
        self.use_json = use_json
        self.json_backup_dir = Path("backend/app/data/buildings")

    def _get_json_backup_path(self, site: str, data_type: str = "tariffs") -> Path:
        """Get path to JSON backup file for a site."""
        site_dir = self.json_backup_dir / site
        site_dir.mkdir(parents=True, exist_ok=True)
        return site_dir / f"water_{data_type}.json"

    def _load_json_backup(self, site: str, data_type: str = "tariffs") -> dict[str, Any]:
        """Load tariff or cost data from JSON backup."""
        json_path = self._get_json_backup_path(site, data_type)
        if not json_path.exists():
            return {data_type: []}
        try:
            with open(json_path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading JSON backup from {json_path}: {e}")
            return {data_type: []}

    def _save_json_backup(self, site: str, data: dict[str, Any], data_type: str = "tariffs") -> None:
        """Save tariff or cost data to JSON backup."""
        json_path = self._get_json_backup_path(site, data_type)
        try:
            with open(json_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving JSON backup to {json_path}: {e}")

    async def get_active_tariff(self, site: str, date_ref: datetime | None = None) -> WaterTariff | None:
        """Get tariff effective on given date.

        Args:
            site: Building site code
            date_ref: Date to check (default: today)

        Returns:
            WaterTariff or None if not found
        """
        if date_ref is None:
            date_ref = datetime.now()

        try:
            if not self.use_json and self.client:
                # Query Supabase
                response = self.client.table("water_tariffs").select("*").eq("site", site).execute()
                tariffs = response.data or []
                for t in tariffs:
                    eff = (
                        datetime.fromisoformat(t["effective_date"])
                        if isinstance(t["effective_date"], str)
                        else t["effective_date"]
                    )
                    end = None
                    if t.get("end_date"):
                        end = datetime.fromisoformat(t["end_date"]) if isinstance(t["end_date"], str) else t["end_date"]

                    if eff <= date_ref and (end is None or end > date_ref):
                        return WaterTariff.from_dict(t)
            else:
                # Use JSON fallback
                backup = self._load_json_backup(site, "tariffs")
                tariffs = backup.get("tariffs", [])
                for t in tariffs:
                    eff = (
                        datetime.fromisoformat(t["effective_date"])
                        if isinstance(t["effective_date"], str)
                        else t["effective_date"]
                    )
                    end = None
                    if t.get("end_date"):
                        end = datetime.fromisoformat(t["end_date"]) if isinstance(t["end_date"], str) else t["end_date"]

                    if eff <= date_ref and (end is None or end > date_ref):
                        return WaterTariff.from_dict(t)
        except Exception as e:
            logger.error(f"Error getting active tariff for {site}: {e}")
            # Fallback to JSON
            backup = self._load_json_backup(site, "tariffs")
            tariffs = backup.get("tariffs", [])
            for t in tariffs:
                eff = (
                    datetime.fromisoformat(t["effective_date"])
                    if isinstance(t["effective_date"], str)
                    else t["effective_date"]
                )
                end = None
                if t.get("end_date"):
                    end = datetime.fromisoformat(t["end_date"]) if isinstance(t["end_date"], str) else t["end_date"]

                if eff <= date_ref and (end is None or end > date_ref):
                    return WaterTariff.from_dict(t)

        return None

    async def list_tariffs(self, site: str) -> list[WaterTariff]:
        """Get all tariffs for a site.

        Args:
            site: Building site code

        Returns:
            List of WaterTariff objects
        """
        try:
            if not self.use_json and self.client:
                response = self.client.table("water_tariffs").select("*").eq("site", site).execute()
                tariffs = response.data or []
                return [WaterTariff.from_dict(t) for t in tariffs]
            else:
                backup = self._load_json_backup(site, "tariffs")
                tariffs = backup.get("tariffs", [])
                return [WaterTariff.from_dict(t) for t in tariffs]
        except Exception as e:
            logger.error(f"Error listing tariffs for {site}: {e}")
            backup = self._load_json_backup(site, "tariffs")
            tariffs = backup.get("tariffs", [])
            return [WaterTariff.from_dict(t) for t in tariffs]

    async def create_tariff(self, tariff: WaterTariff) -> WaterTariff:
        """Create new tariff record.

        Args:
            tariff: WaterTariff object

        Returns:
            Created tariff with ID populated
        """
        try:
            tariff_dict = tariff.to_dict()

            if not self.use_json and self.client:
                response = self.client.table("water_tariffs").insert(tariff_dict).execute()
                if response.data:
                    return WaterTariff.from_dict(response.data[0])

            # JSON fallback
            backup = self._load_json_backup(tariff.site, "tariffs")
            if "tariffs" not in backup:
                backup["tariffs"] = []
            backup["tariffs"].append(tariff_dict)
            self._save_json_backup(tariff.site, backup, "tariffs")

            return tariff
        except Exception as e:
            logger.error(f"Error creating tariff: {e}")
            # Fallback to JSON
            backup = self._load_json_backup(tariff.site, "tariffs")
            if "tariffs" not in backup:
                backup["tariffs"] = []
            backup["tariffs"].append(tariff.to_dict())
            self._save_json_backup(tariff.site, backup, "tariffs")
            return tariff

    async def get_zone_costs(self, zone_id: str, start: datetime, end: datetime) -> dict[str, Any]:
        """Get cost summary for a zone in period.

        Args:
            zone_id: Zone identifier
            start: Period start date
            end: Period end date

        Returns:
            Cost breakdown by tier
        """
        try:
            if not self.use_json and self.client:
                response = (
                    self.client.table("water_costs")
                    .select("*")
                    .eq("zone_id", zone_id)
                    .gte("period_date", start.isoformat())
                    .lte("period_date", end.isoformat())
                    .execute()
                )
                costs = response.data or []
            else:
                # JSON search - find costs for this zone
                costs = []
                # This would need site info to load from JSON properly
                costs = []

            tier_1 = sum(c.get("tier_1_cost", 0) for c in costs)
            tier_2 = sum(c.get("tier_2_cost", 0) for c in costs)
            tier_3 = sum(c.get("tier_3_cost", 0) for c in costs)
            fixed = sum(c.get("fixed_charge", 0) for c in costs)
            total = tier_1 + tier_2 + tier_3 + fixed

            return {
                "zone_id": zone_id,
                "period": {"start": start.isoformat(), "end": end.isoformat()},
                "tier_1_cost": round(tier_1, 2),
                "tier_2_cost": round(tier_2, 2),
                "tier_3_cost": round(tier_3, 2),
                "fixed_charge": round(fixed, 2),
                "total_cost": round(total, 2),
            }
        except Exception as e:
            logger.error(f"Error getting zone costs for {zone_id}: {e}")
            return {
                "zone_id": zone_id,
                "period": {"start": start.isoformat(), "end": end.isoformat()},
                "tier_1_cost": 0.0,
                "tier_2_cost": 0.0,
                "tier_3_cost": 0.0,
                "fixed_charge": 0.0,
                "total_cost": 0.0,
            }

    async def get_site_costs(self, site: str, start: datetime, end: datetime) -> dict[str, Any]:
        """Get cost summary for entire site in period.

        Args:
            site: Building site code
            start: Period start date
            end: Period end date

        Returns:
            Cost breakdown with zone attribution
        """
        try:
            if not self.use_json and self.client:
                response = (
                    self.client.table("water_costs")
                    .select("*")
                    .eq("site", site)
                    .gte("period_date", start.isoformat())
                    .lte("period_date", end.isoformat())
                    .execute()
                )
                costs = response.data or []
            else:
                backup = self._load_json_backup(site, "costs")
                costs = backup.get("costs", [])

            tier_1 = sum(c.get("tier_1_cost", 0) for c in costs)
            tier_2 = sum(c.get("tier_2_cost", 0) for c in costs)
            tier_3 = sum(c.get("tier_3_cost", 0) for c in costs)
            fixed = sum(c.get("fixed_charge", 0) for c in costs)
            total = tier_1 + tier_2 + tier_3 + fixed

            # Group by zone
            by_zone = {}
            for c in costs:
                z = c.get("zone_id", "unassigned")
                if z not in by_zone:
                    by_zone[z] = {"tier_1": 0, "tier_2": 0, "tier_3": 0, "fixed": 0}
                by_zone[z]["tier_1"] += c.get("tier_1_cost", 0)
                by_zone[z]["tier_2"] += c.get("tier_2_cost", 0)
                by_zone[z]["tier_3"] += c.get("tier_3_cost", 0)
                by_zone[z]["fixed"] += c.get("fixed_charge", 0)

            zone_list = [
                {
                    "zone_id": z,
                    "tier_1_cost": round(data["tier_1"], 2),
                    "tier_2_cost": round(data["tier_2"], 2),
                    "tier_3_cost": round(data["tier_3"], 2),
                    "fixed_charge": round(data["fixed"], 2),
                    "total_cost": round(data["tier_1"] + data["tier_2"] + data["tier_3"] + data["fixed"], 2),
                }
                for z, data in sorted(by_zone.items())
            ]

            return {
                "site": site,
                "period": {"start": start.isoformat(), "end": end.isoformat()},
                "tier_1_cost": round(tier_1, 2),
                "tier_2_cost": round(tier_2, 2),
                "tier_3_cost": round(tier_3, 2),
                "fixed_charge": round(fixed, 2),
                "total_cost": round(total, 2),
                "by_zone": zone_list,
            }
        except Exception as e:
            logger.error(f"Error getting site costs for {site}: {e}")
            return {
                "site": site,
                "period": {"start": start.isoformat(), "end": end.isoformat()},
                "tier_1_cost": 0.0,
                "tier_2_cost": 0.0,
                "tier_3_cost": 0.0,
                "fixed_charge": 0.0,
                "total_cost": 0.0,
                "by_zone": [],
            }

    async def get_cost_forecast(self, site: str, days: int = 30) -> dict[str, Any]:
        """Project future costs based on recent consumption.

        Args:
            site: Building site code
            days: Projection period in days

        Returns:
            Forecasted costs by tier
        """
        try:
            # Get last 7 days of consumption to calculate average
            cutoff = datetime.now() - timedelta(days=7)

            if not self.use_json and self.client:
                response = (
                    self.client.table("water_costs")
                    .select("*")
                    .eq("site", site)
                    .gte("period_date", cutoff.isoformat())
                    .execute()
                )
                recent_costs = response.data or []
            else:
                backup = self._load_json_backup(site, "costs")
                recent_costs = backup.get("costs", [])
                recent_costs = [
                    c for c in recent_costs if datetime.fromisoformat(c.get("period_date", "2000-01-01")) >= cutoff
                ]

            if not recent_costs:
                return {
                    "site": site,
                    "forecast_period": days,
                    "daily_avg_cost": 0.0,
                    "projected_monthly": 0.0,
                    "projected_annual": 0.0,
                }

            avg_daily_cost = sum(c.get("total_cost", 0) for c in recent_costs) / 7
            projected_monthly = avg_daily_cost * 30
            projected_annual = avg_daily_cost * 365

            return {
                "site": site,
                "forecast_period": days,
                "daily_avg_cost": round(avg_daily_cost, 2),
                "projected_monthly": round(projected_monthly, 2),
                "projected_annual": round(projected_annual, 2),
                "confidence": "medium",  # Based on 7-day average
            }
        except Exception as e:
            logger.error(f"Error forecasting costs for {site}: {e}")
            return {
                "site": site,
                "forecast_period": days,
                "daily_avg_cost": 0.0,
                "projected_monthly": 0.0,
                "projected_annual": 0.0,
            }

    def calculate_cost(self, consumption_liters: float, tariff: WaterTariff) -> dict[str, float]:
        """Calculate cost breakdown using tiered tariff.

        Args:
            consumption_liters: Total consumption volume
            tariff: WaterTariff object with tier configuration

        Returns:
            Dict with tier_1_cost, tier_2_cost, tier_3_cost, fixed_charge, total_cost
        """
        tier_1_cost = 0.0
        tier_2_cost = 0.0
        tier_3_cost = 0.0

        # Tier 1: From 0 to tier_1_liters at tier_1_rate
        if consumption_liters > 0:
            tier_1_usage = min(consumption_liters, tariff.tier_1_liters)
            tier_1_cost = tier_1_usage * tariff.tier_1_rate_per_liter

        # Tier 2: From tier_1_liters to tier_2_liters at tier_2_rate
        if consumption_liters > tariff.tier_1_liters:
            tier_2_usage = min(consumption_liters - tariff.tier_1_liters, tariff.tier_2_liters - tariff.tier_1_liters)
            tier_2_cost = tier_2_usage * tariff.tier_2_rate_per_liter

        # Tier 3: Beyond tier_2_liters at tier_3_rate
        if consumption_liters > tariff.tier_2_liters:
            tier_3_usage = consumption_liters - tariff.tier_2_liters
            tier_3_cost = tier_3_usage * tariff.tier_3_rate_per_liter

        total_cost = tier_1_cost + tier_2_cost + tier_3_cost + tariff.fixed_monthly_charge

        return {
            "tier_1_cost": round(tier_1_cost, 4),
            "tier_2_cost": round(tier_2_cost, 4),
            "tier_3_cost": round(tier_3_cost, 4),
            "fixed_charge": round(tariff.fixed_monthly_charge, 2),
            "total_cost": round(total_cost, 2),
        }
