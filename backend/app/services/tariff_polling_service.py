"""Service for polling utility tariffs from external sources.

Fetches electricity and water tariffs from municipal providers:
- Electricity: Eskom, City Power, municipal providers
- Water: Rand Water, Johannesburg Water, municipal water departments

Runs monthly via background scheduler to keep tariffs current.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class TariffPollingService:
    """Polls utility tariffs from external sources and updates database."""

    # Known tariff sources
    RAND_WATER_URL = "https://www.randwater.co.za/tariffs/"
    ESKOM_TARIFF_URL = "https://www.eskom.co.za/distribution/customer-service/municipalities/municipal-tariffs/"

    # Default tariffs (fallback when polling fails)
    DEFAULT_TARIFFS = {
        "electricity": {
            "johannesburg": {
                "provider": "City Power",
                "tariff_name": "LPU-TOU",
                "tou_bands": [
                    {"name": "peak", "hours": [7, 8, 17, 18, 19, 20], "rate": 4.52, "unit": "ZAR/kWh"},
                    {
                        "name": "standard",
                        "hours": [6, 9, 10, 11, 12, 13, 14, 15, 16, 21, 22],
                        "rate": 2.28,
                        "unit": "ZAR/kWh",
                    },
                    {"name": "off_peak", "hours": [0, 1, 2, 3, 4, 5, 23], "rate": 0.63, "unit": "ZAR/kWh"},
                ],
                "demand_charge_per_kva": 180.50,
                "fixed_monthly_charge": 1200.00,
                "network_charge_per_kwh": 0.45,
            }
        },
        "water": {
            "johannesburg": {
                "provider": "Johannesburg Water",
                "tariff_name": "Commercial",
                "tiered_rates": [
                    {"tier": 1, "threshold_liters": 100000, "rate_r_per_kiloliter": 7.95},
                    {"tier": 2, "threshold_liters": 500000, "rate_r_per_kiloliter": 12.50},
                    {"tier": 3, "threshold_liters": None, "rate_r_per_kiloliter": 18.95},
                ],
                "sewerage_rate_r_per_kiloliter": 4.45,
                "fixed_monthly_charge": 250.00,
                "tier_thresholds": [100000, 500000],  # liters
            }
        },
    }

    def __init__(self):
        self.client = get_supabase_client()
        self.http_client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()

    async def poll_all_tariffs(self) -> dict[str, Any]:
        """Poll tariffs for all active sites.

        Returns:
            Summary of polling results
        """
        results = {"sites_processed": 0, "tariffs_updated": 0, "errors": []}

        try:
            # Get all sites with location info
            sites_resp = (
                self.client.table("sites")
                .select("code, name, region, electricity_provider, latitude, longitude")
                .execute()
            )

            sites = sites_resp.data or []
            results["sites_processed"] = len(sites)

            for site in sites:
                site_code = site["code"]
                region = site.get("region", "").lower()
                provider = site.get("electricity_provider", "")

                try:
                    # Poll electricity tariff
                    elec_result = await self._poll_electricity_tariff(site_code, region, provider)
                    if elec_result:
                        results["tariffs_updated"] += 1

                    # Poll water tariff
                    water_result = await self._poll_water_tariff(site_code, region)
                    if water_result:
                        results["tariffs_updated"] += 1

                except Exception as e:
                    error_msg = f"Site {site_code}: {e!s}"
                    logger.error(f"[TARIFF_POLL] {error_msg}")
                    results["errors"].append(error_msg)

            logger.info(
                f"[TARIFF_POLL] Completed: {results['sites_processed']} sites, "
                f"{results['tariffs_updated']} tariffs updated, "
                f"{len(results['errors'])} errors"
            )

        except Exception as e:
            logger.error(f"[TARIFF_POLL] Failed to poll tariffs: {e}")
            results["errors"].append(f"Global error: {e!s}")

        return results

    async def _poll_electricity_tariff(self, site_code: str, region: str, provider: str) -> bool:
        """Poll electricity tariff for a site.

        Args:
            site_code: Site identifier
            region: Site region/municipality
            provider: Electricity provider name

        Returns:
            True if tariff was updated
        """
        municipality = self._region_to_municipality(region)

        # Try to fetch from provider (currently uses defaults with warnings)
        try:
            # TODO: Implement actual API calls to Eskom/City Power
            # For now, use default tariffs with last_fetched tracking
            default = self.DEFAULT_TARIFFS["electricity"].get(municipality)

            if not default:
                logger.warning(
                    f"[TARIFF_POLL] No default electricity tariff for {municipality}, using Johannesburg fallback"
                )
                default = self.DEFAULT_TARIFFS["electricity"]["johannesburg"]

            # Store/update tariff
            await self._store_tariff(
                site_code=site_code,
                utility_type="electricity",
                provider=default["provider"],
                municipality=municipality.capitalize(),
                tariff_name=default["tariff_name"],
                tariff_structure={
                    "tou_bands": default["tou_bands"],
                    "demand_charge_per_kva": default["demand_charge_per_kva"],
                    "fixed_monthly_charge": default["fixed_monthly_charge"],
                    "network_charge_per_kwh": default["network_charge_per_kwh"],
                },
                source_url=self.ESKOM_TARIFF_URL,
                source_type="manual",  # Until we implement real API
            )

            return True

        except Exception as e:
            logger.error(f"[TARIFF_POLL] Failed to poll electricity for {site_code}: {e}")
            return False

    async def _poll_water_tariff(self, site_code: str, region: str) -> bool:
        """Poll water tariff for a site from Rand Water.

        Args:
            site_code: Site identifier
            region: Site region/municipality

        Returns:
            True if tariff was updated
        """
        municipality = self._region_to_municipality(region)

        try:
            # Try to fetch from Rand Water website
            tariff_data = await self._fetch_randwater_tariff(municipality)

            if tariff_data:
                await self._store_tariff(
                    site_code=site_code,
                    utility_type="water",
                    provider="Rand Water",
                    municipality=municipality.capitalize(),
                    tariff_name=tariff_data.get("tariff_name", "Commercial"),
                    tariff_structure=tariff_data["structure"],
                    source_url=self.RAND_WATER_URL,
                    source_type="scrape" if tariff_data.get("fetched") else "manual",
                )
                logger.info(f"[TARIFF_POLL] Updated water tariff for {site_code} from Rand Water")
                return True
            else:
                # Use default if fetch failed
                default = self.DEFAULT_TARIFFS["water"].get(municipality)
                if not default:
                    default = self.DEFAULT_TARIFFS["water"]["johannesburg"]

                await self._store_tariff(
                    site_code=site_code,
                    utility_type="water",
                    provider=default["provider"],
                    municipality=municipality.capitalize(),
                    tariff_name=default["tariff_name"],
                    tariff_structure={
                        "tiered_rates": default["tiered_rates"],
                        "sewerage_rate_r_per_kiloliter": default["sewerage_rate_r_per_kiloliter"],
                        "fixed_monthly_charge": default["fixed_monthly_charge"],
                    },
                    source_url=self.RAND_WATER_URL,
                    source_type="manual",
                    fetch_status="error",
                    fetch_error="Could not fetch from Rand Water, using defaults",
                )
                logger.warning(f"[TARIFF_POLL] Used default water tariff for {site_code}")
                return True

        except Exception as e:
            logger.error(f"[TARIFF_POLL] Failed to poll water for {site_code}: {e}")
            return False

    async def _fetch_randwater_tariff(self, municipality: str) -> dict | None:
        """Fetch water tariff from Rand Water website.

        Note: Rand Water doesn't have a public API. This attempts to scrape
        or uses cached values. In production, this should use a proper API
        or PDF parsing of tariff schedules.

        Args:
            municipality: Municipality name

        Returns:
            Tariff data dict or None if unavailable
        """
        try:
            # Attempt to fetch Rand Water tariffs page
            response = await self.http_client.get(self.RAND_WATER_URL)

            if response.status_code != 200:
                logger.warning(f"[TARIFF_POLL] Rand Water returned {response.status_code}")
                return None

            # Parse HTML for tariff information
            # Note: This is a simplified scraper - real implementation would need
            # proper HTML parsing based on actual page structure
            html = response.text

            # Look for tariff patterns (example patterns)
            tariff_patterns = [
                r"R\s*(\d+\.?\d*)\s*/?\s*kL",  # R 7.95 / kL
                r"(\d+\.?\d*)\s*cents?\s*/?\s*litre",  # 0.795 cents/litre
            ]

            rates_found = []
            for pattern in tariff_patterns:
                matches = re.findall(pattern, html, re.IGNORECASE)
                rates_found.extend([float(m) for m in matches])

            if rates_found:
                # Use found rates to update tariff structure
                # For now, return None to use defaults
                logger.info(f"[TARIFF_POLL] Found {len(rates_found)} rate patterns on Rand Water site")

            # Return None to trigger fallback for now
            # TODO: Implement proper parsing when we have access to actual tariff page structure
            return None

        except Exception as e:
            logger.error(f"[TARIFF_POLL] Error fetching Rand Water tariffs: {e}")
            return None

    async def _store_tariff(
        self,
        site_code: str,
        utility_type: str,
        provider: str,
        municipality: str,
        tariff_name: str,
        tariff_structure: dict,
        source_url: str,
        source_type: str,
        fetch_status: str = "active",
        fetch_error: str | None = None,
    ) -> None:
        """Store or update tariff in database.

        Uses upsert to handle existing tariffs for the same period.
        """
        effective_date = date.today().replace(day=1)  # First of current month

        tariff_data = {
            "site_id": site_code,
            "utility_type": utility_type,
            "provider": provider,
            "municipality": municipality,
            "region": municipality,  # Could be more specific
            "tariff_name": tariff_name,
            "tariff_code": f"{provider[:3].upper()}-{tariff_name[:3].upper()}-{effective_date.strftime('%Y%m')}",
            "effective_date": effective_date.isoformat(),
            "expiry_date": (effective_date + timedelta(days=90)).isoformat(),  # 3 month default
            "tariff_structure": tariff_structure,
            "source_url": source_url,
            "source_type": source_type,
            "last_fetched_at": datetime.utcnow().isoformat(),
            "fetch_status": fetch_status,
            "fetch_error": fetch_error,
        }

        try:
            # Upsert - update if exists for this site/type/effective_date
            result = (
                self.client.table("utility_tariffs")
                .upsert(tariff_data, on_conflict="site_id,utility_type,provider,tariff_name,effective_date")
                .execute()
            )

            if result.data:
                logger.debug(f"[TARIFF_POLL] Stored {utility_type} tariff for {site_code} ({provider} - {tariff_name})")

        except Exception as e:
            logger.error(f"[TARIFF_POLL] Failed to store tariff: {e}")
            raise

    def _region_to_municipality(self, region: str) -> str:
        """Map region to municipality name.

        Args:
            region: Site region string

        Returns:
            Municipality name
        """
        region_lower = region.lower()

        mappings = {
            "johannesburg": "johannesburg",
            "joburg": "johannesburg",
            "sandton": "johannesburg",
            "rosebank": "johannesburg",
            "jhb": "johannesburg",
            "tshwane": "tshwane",
            "pretoria": "tshwane",
            "ekurhuleni": "ekurhuleni",
            " Germiston": "ekurhuleni",
            "benoni": "ekurhuleni",
            "kempton": "ekurhuleni",
            "midrand": "johannesburg",
            "centurion": "tshwane",
        }

        for key, value in mappings.items():
            if key in region_lower:
                return value

        return "johannesburg"  # Default fallback

    def get_tariff_for_site(
        self, site_code: str, utility_type: str, as_of_date: date | None = None
    ) -> dict[str, Any] | None:
        """Get current tariff for a site.

        Args:
            site_code: Site identifier
            utility_type: 'electricity' or 'water'
            as_of_date: Date to check (defaults to today)

        Returns:
            Tariff data dict or None
        """
        check_date = as_of_date or date.today()

        try:
            result = (
                self.client.table("utility_tariffs")
                .select("*")
                .eq("site_id", site_code)
                .eq("utility_type", utility_type)
                .lte("effective_date", check_date.isoformat())
                .or_(f"expiry_date.is.null,expiry_date.gte.{check_date.isoformat()}")
                .order("effective_date", desc=True)
                .limit(1)
                .execute()
            )

            if result.data:
                return result.data[0]

            # Fallback to defaults
            municipality = "johannesburg"  # Could look up from sites table
            default = self.DEFAULT_TARIFFS.get(utility_type, {}).get(municipality)

            if default:
                return {
                    "utility_type": utility_type,
                    "provider": default.get("provider", "Default"),
                    "municipality": municipality.capitalize(),
                    "tariff_structure": default,
                    "source_type": "default",
                }

            return None

        except Exception as e:
            logger.error(f"[TARIFF_POLL] Error fetching tariff for {site_code}: {e}")
            return None

    def calculate_water_cost(self, liters: float, site_code: str) -> dict[str, float]:
        """Calculate water cost using tiered tariff.

        Args:
            liters: Water volume in liters
            site_code: Site identifier

        Returns:
            Cost breakdown dict
        """
        tariff = self.get_tariff_for_site(site_code, "water")

        if not tariff:
            # Use default calculation
            rate = 0.0124  # Average R/L
            return {
                "water_cost": liters * rate,
                "sewerage_cost": liters * 0.00445,
                "total_cost": liters * (rate + 0.00445),
                "fixed_charge": 250.0,
            }

        structure = tariff.get("tariff_structure", {})
        tiers = structure.get("tiered_rates", [])
        sewerage_rate = structure.get("sewerage_rate_r_per_kiloliter", 4.45) / 1000  # Convert to R/L
        fixed_charge = structure.get("fixed_monthly_charge", 250.0)

        # Calculate tiered cost
        remaining = liters
        water_cost = 0.0

        for tier in tiers:
            threshold = tier.get("threshold_liters")
            rate = tier.get("rate_r_per_kiloliter", 0) / 1000  # Convert to R/L

            if threshold is None:
                # Unlimited tier
                tier_volume = remaining
            else:
                tier_volume = min(remaining, threshold)

            water_cost += tier_volume * rate
            remaining -= tier_volume

            if remaining <= 0:
                break

        sewerage_cost = liters * sewerage_cost

        return {
            "water_cost": round(water_cost, 2),
            "sewerage_cost": round(sewerage_cost, 2),
            "total_cost": round(water_cost + sewerage_cost, 2),
            "fixed_charge": fixed_charge,
        }


# Singleton instance
_tariff_polling_service: TariffPollingService | None = None


def get_tariff_polling_service() -> TariffPollingService:
    """Get or create tariff polling service singleton."""
    global _tariff_polling_service
    if _tariff_polling_service is None:
        _tariff_polling_service = TariffPollingService()
    return _tariff_polling_service
