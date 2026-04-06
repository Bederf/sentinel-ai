"""Water Aggregation Service — zone-level consumption analytics.

Provides aggregation and analysis of water consumption by zone, floor, and building.
Enables identification of high-consuming areas and supports floor-level billing reconciliation.
"""

import logging
from datetime import date, timedelta
from typing import Any

from app.database.repositories.water_consumption_repository import WaterConsumptionRepository
from app.processing.water_table import WaterTableProcessor

logger = logging.getLogger(__name__)


class WaterAggregationService:
    """Provides zone and floor-level water consumption aggregation and analysis.

    Methods aggregate consumption data across meters in a zone to provide:
    - Zone-level consumption totals and averages
    - Floor-level consumption by zone
    - Top consuming zones for a building
    - Consumption trends for zones
    - Comparison of zone consumption to building average
    """

    def __init__(self, repository: WaterConsumptionRepository | None = None):
        """Initialize aggregation service.

        Args:
            repository: WaterConsumptionRepository instance (uses default if None)
        """
        self.repository = repository or WaterConsumptionRepository()

    def get_consumption_by_zone(
        self,
        zone_id: str,
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, Any]:
        """Get aggregated consumption for a zone.

        Args:
            zone_id: Zone identifier (e.g., "L2-A", "101")
            start: Start date (default: 30 days ago)
            end: End date (default: today)

        Returns:
            {
                "zone_id": str,
                "zone_name": str (if available),
                "start_date": str,
                "end_date": str,
                "total_liters": float,
                "avg_flow_lpm": float,
                "peak_flow_lpm": float,
                "meter_count": int,
                "meters": [{"meter_id": str, "liters": float, "avg_flow": float}],
                "record_count": int,
            }
        """
        if end is None:
            end = date.today()
        if start is None:
            start = end - timedelta(days=30)

        all_records = self.repository.get_consumption_by_site(
            site="",
            start_date=start,
            end_date=end,
            limit=100000,
        )
        zone_records = [r for r in all_records if r.get("zone_id") == zone_id]
        return WaterTableProcessor.aggregate_zone_records(zone_id, zone_records, start, end)

    def get_consumption_by_floor(
        self,
        site_id: str,
        floor: str,
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, Any]:
        """Get aggregated consumption for all zones on a floor.

        Args:
            site_id: Building/site identifier (e.g., "site-002")
            floor: Floor identifier (e.g., "L2", "101-199")
            start: Start date
            end: End date

        Returns:
            {
                "floor": str,
                "site_id": str,
                "start_date": str,
                "end_date": str,
                "total_liters": float,
                "avg_flow_lpm": float,
                "zone_count": int,
                "zones": [{"zone_id": str, "zone_name": str, "liters": float, ...}],
                "record_count": int,
            }
        """
        if end is None:
            end = date.today()
        if start is None:
            start = end - timedelta(days=30)

        site_records = self.repository.get_consumption_by_site(
            site=site_id,
            start_date=start,
            end_date=end,
            limit=100000,
        )
        return WaterTableProcessor.aggregate_floor_records(site_id, floor, site_records, start, end)

    def get_top_consuming_zones(
        self,
        site_id: str,
        limit: int = 10,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Get top N zones by consumption.

        Args:
            site_id: Building/site identifier
            limit: Number of top zones to return
            days: Look-back period (default: 30 days)

        Returns:
            List of zones sorted by consumption (descending):
            [{"zone_id": str, "zone_name": str, "total_liters": float, "rank": int, ...}]
        """
        end = date.today()
        start = end - timedelta(days=days)

        records = self.repository.get_consumption_by_site(
            site=site_id,
            start_date=start,
            end_date=end,
            limit=100000,
        )
        return WaterTableProcessor.rank_top_zones(records, limit, days)

    def zone_consumption_trend(
        self,
        zone_id: str,
        days: int = 7,
    ) -> dict[str, Any]:
        """Get daily consumption trend for a zone.

        Args:
            zone_id: Zone identifier
            days: Number of days to analyze

        Returns:
            {
                "zone_id": str,
                "zone_name": str (if available),
                "days": int,
                "data": [{"date": str, "liters": float, "avg_flow_lpm": float}, ...],
                "total_liters": float,
                "average_daily_liters": float,
            }
        """
        end = date.today()
        start = end - timedelta(days=days)

        all_records = self.repository.get_consumption_by_site(
            site="",
            start_date=start,
            end_date=end,
            limit=100000,
        )
        zone_records = [r for r in all_records if r.get("zone_id") == zone_id]
        return WaterTableProcessor.build_zone_trend(zone_id, zone_records, days)

    def zone_vs_building_average(
        self,
        zone_id: str,
        site_id: str,
        days: int = 30,
    ) -> dict[str, Any]:
        """Compare zone consumption to building average.

        Args:
            zone_id: Zone identifier
            site_id: Building/site identifier
            days: Analysis period

        Returns:
            {
                "zone_id": str,
                "zone_name": str,
                "site_id": str,
                "zone_daily_avg": float,
                "building_daily_avg": float,
                "difference_percent": float,
                "status": "above" | "below" | "at_average",
                "days": int,
            }
        """
        end = date.today()
        start = end - timedelta(days=days)

        zone_result = self.get_consumption_by_zone(zone_id, start, end)
        zone_liters = zone_result["total_liters"]
        zone_name = zone_result["zone_name"]

        site_records = self.repository.get_consumption_by_site(
            site=site_id,
            start_date=start,
            end_date=end,
            limit=100000,
        )

        if not site_records:
            return {
                "zone_id": zone_id,
                "zone_name": zone_name,
                "site_id": site_id,
                "zone_daily_avg": 0,
                "building_daily_avg": 0,
                "difference_percent": 0,
                "status": "unknown",
                "days": days,
            }

        building_volumes = [r.get("volume_liters", 0) for r in site_records]
        return WaterTableProcessor.compare_zone_vs_building(
            zone_id, zone_name, site_id, zone_liters, building_volumes, days
        )


# Singleton instance
_water_aggregation_service: WaterAggregationService | None = None


def get_water_aggregation_service() -> WaterAggregationService:
    """Get singleton instance of WaterAggregationService."""
    global _water_aggregation_service
    if _water_aggregation_service is None:
        _water_aggregation_service = WaterAggregationService()
    return _water_aggregation_service
