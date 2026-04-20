"""Repository for energy consumption history operations."""

from datetime import date, datetime, timedelta
from typing import Any

from app.database.supabase_client import get_supabase_client


class EnergyConsumptionRepository:
    """Repository for energy consumption history database operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_by_site(
        self,
        site_id: str,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Get energy consumption history for a building.

        Args:
            site_id: Building code (e.g., "site-002", "local-office")
            days: Number of days to retrieve (default 30, max 365)

        Returns:
            List of energy consumption records sorted by date ascending
        """
        # Cap days at 365
        days = min(days, 365)

        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        response = (
            self.client.table("energy_consumption_history")
            .select("*")
            .eq("site_id", site_id)
            .gte("date", start_date.isoformat())
            .lte("date", end_date.isoformat())
            .order("date", desc=False)  # Ascending for charts
            .execute()
        )

        return response.data

    def get_all_sites(
        self,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Get energy consumption history for all buildings.

        Args:
            days: Number of days to retrieve (default 30, max 365)

        Returns:
            List of energy consumption records sorted by date, then building
        """
        # Cap days at 365
        days = min(days, 365)

        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        response = (
            self.client.table("energy_consumption_history")
            .select("*")
            .gte("date", start_date.isoformat())
            .lte("date", end_date.isoformat())
            .order("date", desc=False)  # Ascending for charts
            .execute()
        )

        return response.data

    def get_by_date_range(
        self,
        site_id: str,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Get energy consumption for a building within a date range.

        Args:
            site_id: Building code
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of energy consumption records
        """
        response = (
            self.client.table("energy_consumption_history")
            .select("*")
            .eq("site_id", site_id)
            .gte("date", start_date.isoformat())
            .lte("date", end_date.isoformat())
            .order("date", desc=False)
            .execute()
        )

        return response.data

    def get_latest_date(self, site_id: str) -> date | None:
        """Get the latest consumption date for a building.

        Args:
            site_id: Building code

        Returns:
            Latest date or None if no data exists
        """
        response = (
            self.client.table("energy_consumption_history")
            .select("date")
            .eq("site_id", site_id)
            .order("date", desc=True)
            .limit(1)
            .execute()
        )

        if response.data:
            return datetime.fromisoformat(response.data[0]["date"]).date()
        return None

    def get_daily_summary(
        self,
        site_id: str,
        days: int = 30,
    ) -> dict[str, Any]:
        """Get daily summary statistics for a building.

        Args:
            site_id: Building code
            days: Number of days to summarize

        Returns:
            Dictionary with summary statistics
        """
        records = self.get_by_site(site_id, days)

        if not records:
            return {
                "total_kwh": 0,
                "average_daily_kwh": 0,
                "hvac_percentage": 0,
                "lighting_percentage": 0,
                "other_percentage": 0,
                "days": 0,
            }

        total_kwh = sum(r["total_kwh"] or 0 for r in records)
        total_hvac = sum(r["hvac_kwh"] or 0 for r in records)
        total_lighting = sum(r["lighting_kwh"] or 0 for r in records)
        total_other = sum(r["other_kwh"] or 0 for r in records)
        days_count = len(records)

        return {
            "total_kwh": round(total_kwh, 1),
            "average_daily_kwh": round(total_kwh / days_count, 1) if days_count > 0 else 0,
            "hvac_percentage": round(total_hvac / total_kwh * 100, 1) if total_kwh > 0 else 0,
            "lighting_percentage": round(total_lighting / total_kwh * 100, 1) if total_kwh > 0 else 0,
            "other_percentage": round(total_other / total_kwh * 100, 1) if total_kwh > 0 else 0,
            "days": days_count,
        }

    def upsert(
        self,
        site_id: str,
        consumption_date: date,
        hvac_kwh: float,
        lighting_kwh: float,
        other_kwh: float,
    ) -> dict[str, Any]:
        """Insert or update energy consumption record.

        Args:
            site_id: Building code
            consumption_date: Date of consumption
            hvac_kwh: HVAC consumption in kWh
            lighting_kwh: Lighting consumption in kWh
            other_kwh: Other consumption in kWh

        Returns:
            Created or updated record
        """
        data = {
            "site_id": site_id,
            "date": consumption_date.isoformat(),
            "hvac_kwh": hvac_kwh,
            "lighting_kwh": lighting_kwh,
            "other_kwh": other_kwh,
        }

        # Use upsert to handle duplicate dates
        response = self.client.table("energy_consumption_history").upsert(data, on_conflict="site_id,date").execute()

        return response.data[0]

    def batch_upsert(
        self,
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Insert or update multiple energy consumption records.

        Args:
            records: List of records with site_id, date, hvac_kwh, lighting_kwh, other_kwh

        Returns:
            Created or updated records
        """
        if not records:
            return []

        response = self.client.table("energy_consumption_history").upsert(records, on_conflict="site_id,date").execute()

        return response.data

    def delete_by_site(
        self,
        site_id: str,
    ) -> int:
        """Delete all energy consumption records for a building.

        Args:
            site_id: Building code

        Returns:
            Number of records deleted
        """
        response = self.client.table("energy_consumption_history").delete().eq("site_id", site_id).execute()

        return len(response.data)

    def delete_by_date_range(
        self,
        site_id: str,
        start_date: date,
        end_date: date,
    ) -> int:
        """Delete energy consumption records within a date range.

        Args:
            site_id: Building code
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            Number of records deleted
        """
        response = (
            self.client.table("energy_consumption_history")
            .delete()
            .eq("site_id", site_id)
            .gte("date", start_date.isoformat())
            .lte("date", end_date.isoformat())
            .execute()
        )

        return len(response.data)


def get_energy_consumption_repository() -> EnergyConsumptionRepository:
    """Get singleton instance of EnergyConsumptionRepository."""
    return EnergyConsumptionRepository()
