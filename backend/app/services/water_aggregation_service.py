"""Water Aggregation Service — zone-level consumption analytics.

Provides aggregation and analysis of water consumption by zone, floor, and building.
Enables identification of high-consuming areas and supports floor-level billing reconciliation.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from app.database.repositories.water_consumption_repository import WaterConsumptionRepository

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

    def __init__(self, repository: Optional[WaterConsumptionRepository] = None):
        """Initialize aggregation service.

        Args:
            repository: WaterConsumptionRepository instance (uses default if None)
        """
        self.repository = repository or WaterConsumptionRepository()

    def get_consumption_by_zone(
        self,
        zone_id: str,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> Dict[str, Any]:
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

        # Get all records for this zone from all meters
        # Since zone_id is stored per consumption record, we query all and filter
        all_records = self.repository.get_consumption_by_site(
            site="",  # We'll need to search all sites
            start_date=start,
            end_date=end,
            limit=100000,  # Large limit to get all zone records
        )

        # Filter by zone_id (noting: would be more efficient with direct DB query)
        zone_records = [r for r in all_records if r.get("zone_id") == zone_id]

        if not zone_records:
            return {
                "zone_id": zone_id,
                "zone_name": None,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "total_liters": 0,
                "avg_flow_lpm": 0,
                "peak_flow_lpm": 0,
                "meter_count": 0,
                "meters": [],
                "record_count": 0,
            }

        # Extract zone_name from first record if available
        zone_name = zone_records[0].get("zone_name") if zone_records else None

        # Group by meter_id to get per-meter totals
        meter_data: Dict[str, Dict[str, Any]] = {}
        for record in zone_records:
            meter_id = record["meter_id"]
            if meter_id not in meter_data:
                meter_data[meter_id] = {
                    "meter_id": meter_id,
                    "volume_liters": 0,
                    "flows": [],
                    "count": 0,
                }
            meter_data[meter_id]["volume_liters"] = record.get("volume_liters", 0)
            meter_data[meter_id]["flows"].append(record.get("flow_rate_lpm", 0))
            meter_data[meter_id]["count"] += 1

        # Calculate meter-level statistics
        meters = []
        total_volume = 0
        all_flows = []
        for meter_id, data in meter_data.items():
            avg_flow = sum(data["flows"]) / len(data["flows"]) if data["flows"] else 0
            meters.append(
                {
                    "meter_id": meter_id,
                    "liters": round(data["volume_liters"], 2),
                    "avg_flow": round(avg_flow, 2),
                }
            )
            total_volume += data["volume_liters"]
            all_flows.extend(data["flows"])

        # Calculate aggregates
        avg_flow = sum(all_flows) / len(all_flows) if all_flows else 0
        peak_flow = max(all_flows) if all_flows else 0

        return {
            "zone_id": zone_id,
            "zone_name": zone_name,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "total_liters": round(total_volume, 2),
            "avg_flow_lpm": round(avg_flow, 2),
            "peak_flow_lpm": round(peak_flow, 2),
            "meter_count": len(meter_data),
            "meters": meters,
            "record_count": len(zone_records),
        }

    def get_consumption_by_floor(
        self,
        site_id: str,
        floor: str,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> Dict[str, Any]:
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

        # Get all consumption for building
        site_records = self.repository.get_consumption_by_site(
            site=site_id,
            start_date=start,
            end_date=end,
            limit=100000,
        )

        # Filter records by floor based on zone_id pattern
        # Assumption: floor can be encoded in zone_id (e.g., L1, L2, or 100-199, 200-299)
        floor_records = [r for r in site_records if self._zone_is_on_floor(r.get("zone_id"), floor)]

        if not floor_records:
            return {
                "floor": floor,
                "site_id": site_id,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "total_liters": 0,
                "avg_flow_lpm": 0,
                "zone_count": 0,
                "zones": [],
                "record_count": 0,
            }

        # Group by zone_id
        zone_data: Dict[str, Dict[str, Any]] = {}
        for record in floor_records:
            zone_id = record.get("zone_id")
            if not zone_id:
                continue
            if zone_id not in zone_data:
                zone_data[zone_id] = {
                    "zone_id": zone_id,
                    "zone_name": record.get("zone_name"),
                    "volume_liters": 0,
                    "flows": [],
                }
            zone_data[zone_id]["volume_liters"] = max(
                zone_data[zone_id]["volume_liters"], record.get("volume_liters", 0)
            )
            zone_data[zone_id]["flows"].append(record.get("flow_rate_lpm", 0))

        # Calculate per-zone statistics
        zones = []
        total_volume = 0
        all_flows = []
        for zone_id, data in zone_data.items():
            avg_flow = sum(data["flows"]) / len(data["flows"]) if data["flows"] else 0
            zones.append(
                {
                    "zone_id": zone_id,
                    "zone_name": data.get("zone_name"),
                    "liters": round(data["volume_liters"], 2),
                    "avg_flow": round(avg_flow, 2),
                }
            )
            total_volume += data["volume_liters"]
            all_flows.extend(data["flows"])

        # Sort zones by consumption
        zones.sort(key=lambda z: z["liters"], reverse=True)

        avg_flow = sum(all_flows) / len(all_flows) if all_flows else 0

        return {
            "floor": floor,
            "site_id": site_id,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "total_liters": round(total_volume, 2),
            "avg_flow_lpm": round(avg_flow, 2),
            "zone_count": len(zone_data),
            "zones": zones,
            "record_count": len(floor_records),
        }

    def get_top_consuming_zones(
        self,
        site_id: str,
        limit: int = 10,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
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

        # Get all consumption records for building
        records = self.repository.get_consumption_by_site(
            site=site_id,
            start_date=start,
            end_date=end,
            limit=100000,
        )

        # Group by zone_id
        zone_consumption: Dict[str, Dict[str, Any]] = {}
        for record in records:
            zone_id = record.get("zone_id")
            if not zone_id:
                continue
            if zone_id not in zone_consumption:
                zone_consumption[zone_id] = {
                    "zone_id": zone_id,
                    "zone_name": record.get("zone_name"),
                    "volume_liters": 0,
                    "flows": [],
                    "meter_ids": set(),
                }
            zone_consumption[zone_id]["volume_liters"] = max(
                zone_consumption[zone_id]["volume_liters"], record.get("volume_liters", 0)
            )
            zone_consumption[zone_id]["flows"].append(record.get("flow_rate_lpm", 0))
            zone_consumption[zone_id]["meter_ids"].add(record["meter_id"])

        # Calculate statistics and sort by consumption
        top_zones = []
        for rank, (zone_id, data) in enumerate(
            sorted(zone_consumption.items(), key=lambda x: x[1]["volume_liters"], reverse=True)[:limit], 1
        ):
            avg_flow = sum(data["flows"]) / len(data["flows"]) if data["flows"] else 0
            peak_flow = max(data["flows"]) if data["flows"] else 0
            top_zones.append(
                {
                    "rank": rank,
                    "zone_id": zone_id,
                    "zone_name": data["zone_name"],
                    "total_liters": round(data["volume_liters"], 2),
                    "avg_flow_lpm": round(avg_flow, 2),
                    "peak_flow_lpm": round(peak_flow, 2),
                    "meter_count": len(data["meter_ids"]),
                    "days": days,
                }
            )

        return top_zones

    def zone_consumption_trend(
        self,
        zone_id: str,
        days: int = 7,
    ) -> Dict[str, Any]:
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

        # Get all consumption for zone in period
        # Query all records (fallback since zone filtering needs DB support)
        all_records = self.repository.get_consumption_by_site(
            site="",
            start_date=start,
            end_date=end,
            limit=100000,
        )

        zone_records = [r for r in all_records if r.get("zone_id") == zone_id]

        if not zone_records:
            return {
                "zone_id": zone_id,
                "zone_name": None,
                "days": days,
                "data": [],
                "total_liters": 0,
                "average_daily_liters": 0,
            }

        # Extract zone_name
        zone_name = zone_records[0].get("zone_name") if zone_records else None

        # Group by date
        daily_data: Dict[str, Dict[str, Any]] = {}
        for record in zone_records:
            timestamp = record["timestamp"]
            if isinstance(timestamp, str):
                record_date = datetime.fromisoformat(timestamp).date()
            else:
                record_date = timestamp.date()

            date_str = record_date.isoformat()
            if date_str not in daily_data:
                daily_data[date_str] = {
                    "volume_liters": 0,
                    "flows": [],
                }
            daily_data[date_str]["volume_liters"] = max(
                daily_data[date_str]["volume_liters"], record.get("volume_liters", 0)
            )
            daily_data[date_str]["flows"].append(record.get("flow_rate_lpm", 0))

        # Build trend data
        trend_data = []
        total_liters = 0
        for date_str in sorted(daily_data.keys()):
            data = daily_data[date_str]
            avg_flow = sum(data["flows"]) / len(data["flows"]) if data["flows"] else 0
            liters = data["volume_liters"]
            trend_data.append(
                {
                    "date": date_str,
                    "liters": round(liters, 2),
                    "avg_flow_lpm": round(avg_flow, 2),
                }
            )
            total_liters += liters

        average_daily = total_liters / len(trend_data) if trend_data else 0

        return {
            "zone_id": zone_id,
            "zone_name": zone_name,
            "days": days,
            "data": trend_data,
            "total_liters": round(total_liters, 2),
            "average_daily_liters": round(average_daily, 2),
        }

    def zone_vs_building_average(
        self,
        zone_id: str,
        site_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
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

        # Get zone data
        zone_result = self.get_consumption_by_zone(zone_id, start, end)
        zone_liters = zone_result["total_liters"]
        zone_name = zone_result["zone_name"]

        # Get building data
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

        # Calculate building total
        building_volumes = [r.get("volume_liters", 0) for r in site_records]
        building_liters = max(building_volumes) - min(building_volumes) if building_volumes else 0

        # Calculate daily averages
        zone_daily_avg = zone_liters / days if days > 0 else 0
        building_daily_avg = building_liters / days if days > 0 else 0

        # Calculate difference
        if building_daily_avg > 0:
            difference_percent = ((zone_daily_avg - building_daily_avg) / building_daily_avg) * 100
        else:
            difference_percent = 0

        # Determine status
        if difference_percent > 10:
            status = "above"
        elif difference_percent < -10:
            status = "below"
        else:
            status = "at_average"

        return {
            "zone_id": zone_id,
            "zone_name": zone_name,
            "site_id": site_id,
            "zone_daily_avg": round(zone_daily_avg, 2),
            "building_daily_avg": round(building_daily_avg, 2),
            "difference_percent": round(difference_percent, 1),
            "status": status,
            "days": days,
        }

    @staticmethod
    def _zone_is_on_floor(zone_id: Optional[str], floor: str) -> bool:
        """Check if zone_id belongs to a floor.

        Supports patterns like:
        - Numeric: "001-099" = L0, "100-199" = L1, "200-299" = L2
        - Floor codes: "L0", "L1", "L2"

        Args:
            zone_id: Zone identifier
            floor: Floor identifier

        Returns:
            True if zone is on the floor
        """
        if not zone_id:
            return False

        # Numeric pattern (e.g., "001" on floor "L0" means range 001-099)
        try:
            zone_num = int(zone_id)
            if floor in ["L0", "001-099"]:
                return 1 <= zone_num <= 99
            elif floor in ["L1", "100-199"]:
                return 100 <= zone_num <= 199
            elif floor in ["L2", "200-299"]:
                return 200 <= zone_num <= 299
        except ValueError:
            pass

        # Floor code pattern (e.g., "L1-A")
        if zone_id.startswith(floor):
            return True

        return False


# Singleton instance
_water_aggregation_service: Optional[WaterAggregationService] = None


def get_water_aggregation_service() -> WaterAggregationService:
    """Get singleton instance of WaterAggregationService."""
    global _water_aggregation_service
    if _water_aggregation_service is None:
        _water_aggregation_service = WaterAggregationService()
    return _water_aggregation_service
