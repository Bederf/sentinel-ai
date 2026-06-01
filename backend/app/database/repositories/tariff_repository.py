"""Repository for utility tariff operations."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class TariffRepository:
    """Repository for electricity and water tariff data."""

    def __init__(self):
        self.client = get_supabase_client()

    def get_current_tariff(
        self, site_id: str, utility_type: str, as_of_date: date | None = None
    ) -> dict[str, Any] | None:
        """Get the current active tariff for a site.

        Args:
            site_id: Site code
            utility_type: 'electricity' or 'water'
            as_of_date: Date to check (defaults to today)

        Returns:
            Tariff record or None
        """
        check_date = as_of_date or date.today()

        try:
            result = (
                self.client.table("utility_tariffs")
                .select("*")
                .eq("site_id", site_id)
                .eq("utility_type", utility_type)
                .lte("effective_date", check_date.isoformat())
                .or_(f"expiry_date.is.null,expiry_date.gte.{check_date.isoformat()}")
                .order("effective_date", desc=True)
                .limit(1)
                .execute()
            )

            return result.data[0] if result.data else None

        except Exception as e:
            logger.error(f"[TARIFF_REPO] Error fetching tariff: {e}")
            return None

    def get_tariff_history(self, site_id: str, utility_type: str, limit: int = 12) -> list[dict[str, Any]]:
        """Get tariff history for a site.

        Args:
            site_id: Site code
            utility_type: 'electricity' or 'water'
            limit: Maximum records to return

        Returns:
            List of tariff records
        """
        try:
            result = (
                self.client.table("utility_tariffs")
                .select("*")
                .eq("site_id", site_id)
                .eq("utility_type", utility_type)
                .order("effective_date", desc=True)
                .limit(limit)
                .execute()
            )

            return result.data or []

        except Exception as e:
            logger.error(f"[TARIFF_REPO] Error fetching tariff history: {e}")
            return []

    def get_electricity_rates(self, site_id: str, hour: int | None = None) -> dict[str, Any]:
        """Get electricity rates for a site.

        Args:
            site_id: Site code
            hour: Hour of day (0-23) to get specific rate, or None for all rates

        Returns:
            Rate information dict
        """
        tariff = self.get_current_tariff(site_id, "electricity")

        if not tariff:
            # Return default City Power rates
            return {
                "current_rate": 2.28,
                "peak_rate": 4.52,
                "off_peak_rate": 0.63,
                "band": "standard",
                "demand_charge_per_kva": 180.50,
            }

        structure = tariff.get("tariff_structure", {})
        bands = structure.get("tou_bands", [])

        if hour is not None:
            # Find rate for specific hour
            for band in bands:
                if hour in band.get("hours", []):
                    return {
                        "current_rate": band.get("rate", 2.28),
                        "band": band.get("name", "standard"),
                        "unit": band.get("unit", "ZAR/kWh"),
                        "demand_charge_per_kva": structure.get("demand_charge_per_kva", 180.50),
                        "fixed_monthly_charge": structure.get("fixed_monthly_charge", 1200.00),
                    }

        # Return all rates
        return {
            "bands": bands,
            "demand_charge_per_kva": structure.get("demand_charge_per_kva", 180.50),
            "fixed_monthly_charge": structure.get("fixed_monthly_charge", 1200.00),
            "network_charge_per_kwh": structure.get("network_charge_per_kwh", 0.45),
        }

    def get_water_rates(self, site_id: str, monthly_liters: float | None = None) -> dict[str, Any]:
        """Get water rates for a site.

        Args:
            site_id: Site code
            monthly_liters: Monthly consumption to determine tier

        Returns:
            Rate information dict
        """
        tariff = self.get_current_tariff(site_id, "water")

        if not tariff:
            # Return default Johannesburg rates
            return {
                "tiered_rates": [
                    {"tier": 1, "threshold_liters": 100000, "rate_r_per_kiloliter": 7.95},
                    {"tier": 2, "threshold_liters": 500000, "rate_r_per_kiloliter": 12.50},
                    {"tier": 3, "threshold_liters": None, "rate_r_per_kiloliter": 18.95},
                ],
                "sewerage_rate_r_per_kiloliter": 4.45,
                "fixed_monthly_charge": 250.0,
            }

        structure = tariff.get("tariff_structure", {})
        tiers = structure.get("tiered_rates", [])

        if monthly_liters is not None:
            # Determine current tier
            current_tier = 1
            current_rate = tiers[0]["rate_r_per_kiloliter"] if tiers else 7.95

            for tier in tiers:
                threshold = tier.get("threshold_liters")
                if threshold and monthly_liters > threshold:
                    current_tier = tier.get("tier", current_tier)
                    current_rate = tier.get("rate_r_per_kiloliter", current_rate)

            return {
                "current_tier": current_tier,
                "current_rate_r_per_kiloliter": current_rate,
                "current_rate_r_per_liter": current_rate / 1000,
                "sewerage_rate_r_per_kiloliter": structure.get("sewerage_rate_r_per_kiloliter", 4.45),
                "fixed_monthly_charge": structure.get("fixed_monthly_charge", 250.0),
                "all_tiers": tiers,
            }

        return {
            "tiered_rates": tiers,
            "sewerage_rate_r_per_kiloliter": structure.get("sewerage_rate_r_per_kiloliter", 4.45),
            "fixed_monthly_charge": structure.get("fixed_monthly_charge", 250.0),
        }

    def calculate_projected_costs(
        self, site_id: str, energy_kwh: float, water_liters: float, demand_kva: float = 0
    ) -> dict[str, float]:
        """Calculate projected utility costs.

        Args:
            site_id: Site code
            energy_kwh: Energy consumption in kWh
            water_liters: Water consumption in liters
            demand_kva: Peak demand in kVA

        Returns:
            Cost breakdown dict
        """
        # Get electricity cost (use average rate)
        elec_rates = self.get_electricity_rates(site_id)
        bands = elec_rates.get("bands", [])

        if bands:
            # Calculate weighted average rate
            total_hours = sum(len(b.get("hours", [])) for b in bands)
            avg_rate = (
                sum(b.get("rate", 0) * len(b.get("hours", [])) / total_hours for b in bands)
                if total_hours > 0
                else 2.28
            )
        else:
            avg_rate = 2.28

        energy_cost = energy_kwh * avg_rate
        demand_charge = demand_kva * elec_rates.get("demand_charge_per_kva", 180.50)

        # Get water cost
        water_rates = self.get_water_rates(site_id, water_liters)

        if "current_rate_r_per_liter" in water_rates:
            water_rate_per_liter = water_rates["current_rate_r_per_liter"]
            sewerage_rate_per_liter = water_rates.get("sewerage_rate_r_per_kiloliter", 4.45) / 1000
        else:
            water_rate_per_liter = 0.0124
            sewerage_rate_per_liter = 0.00445

        water_cost = water_liters * water_rate_per_liter
        sewerage_cost = water_liters * sewerage_rate_per_liter

        return {
            "energy_cost": round(energy_cost, 2),
            "demand_charge": round(demand_charge, 2),
            "water_cost": round(water_cost, 2),
            "sewerage_cost": round(sewerage_cost, 2),
            "total_cost": round(energy_cost + demand_charge + water_cost + sewerage_cost, 2),
        }

    def get_all_active_tariffs(self, site_id: str) -> dict[str, Any]:
        """Get all active tariffs for a site.

        Args:
            site_id: Site code

        Returns:
            Dict with electricity and water tariff info
        """
        elec_tariff = self.get_current_tariff(site_id, "electricity")
        water_tariff = self.get_current_tariff(site_id, "water")

        return {
            "electricity": {
                "provider": elec_tariff.get("provider", "City Power") if elec_tariff else "City Power",
                "tariff_name": elec_tariff.get("tariff_name", "LPU-TOU") if elec_tariff else "LPU-TOU",
                "municipality": elec_tariff.get("municipality", "Johannesburg") if elec_tariff else "Johannesburg",
                "rates": self.get_electricity_rates(site_id),
                "last_updated": elec_tariff.get("last_fetched_at") if elec_tariff else None,
            },
            "water": {
                "provider": water_tariff.get("provider", "Johannesburg Water")
                if water_tariff
                else "Johannesburg Water",
                "tariff_name": water_tariff.get("tariff_name", "Commercial") if water_tariff else "Commercial",
                "municipality": water_tariff.get("municipality", "Johannesburg") if water_tariff else "Johannesburg",
                "rates": self.get_water_rates(site_id),
                "last_updated": water_tariff.get("last_fetched_at") if water_tariff else None,
            },
        }
