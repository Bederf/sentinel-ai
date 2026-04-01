"""Water consumption tabular processing.

Owns all groupby / aggregate / rank / sort logic for water consumption records.
Receives pre-fetched ``list[dict]`` rows from the repository layer and returns
shaped plain-dict results suitable for API responses.

Polars adoption path
--------------------
Replace each method body with a Polars expression that consumes the same
``records: list[dict]`` input and produces the same output dict.
The public signatures are the stable contract — callers need no changes.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any


class WaterTableProcessor:
    """Pure tabular shaping for water consumption records.

    All methods are static and side-effect free.  No database access.
    """

    # ------------------------------------------------------------------
    # Zone-level aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def aggregate_zone_records(
        zone_id: str,
        zone_records: list[dict[str, Any]],
        start: date,
        end: date,
    ) -> dict[str, Any]:
        """Group zone records by meter and return zone-level aggregates.

        Args:
            zone_id:      Zone identifier (already filtered — all rows belong to this zone).
            zone_records: Pre-filtered rows from the repository.
            start / end:  Date window (included in the output for context only).

        Returns:
            Dict with total_liters, avg_flow_lpm, peak_flow_lpm, per-meter breakdown, etc.
        """
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

        zone_name = zone_records[0].get("zone_name")

        # Group by meter_id
        meter_data: dict[str, dict[str, Any]] = {}
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

        meters = []
        total_volume = 0.0
        all_flows: list[float] = []
        for meter_id, data in meter_data.items():
            avg_flow = sum(data["flows"]) / len(data["flows"]) if data["flows"] else 0.0
            meters.append(
                {
                    "meter_id": meter_id,
                    "liters": round(data["volume_liters"], 2),
                    "avg_flow": round(avg_flow, 2),
                }
            )
            total_volume += data["volume_liters"]
            all_flows.extend(data["flows"])

        return {
            "zone_id": zone_id,
            "zone_name": zone_name,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "total_liters": round(total_volume, 2),
            "avg_flow_lpm": round(sum(all_flows) / len(all_flows) if all_flows else 0.0, 2),
            "peak_flow_lpm": round(max(all_flows) if all_flows else 0.0, 2),
            "meter_count": len(meter_data),
            "meters": meters,
            "record_count": len(zone_records),
        }

    # ------------------------------------------------------------------
    # Floor-level aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def aggregate_floor_records(
        site_id: str,
        floor: str,
        site_records: list[dict[str, Any]],
        start: date,
        end: date,
    ) -> dict[str, Any]:
        """Filter records to a floor, group by zone_id, return floor-level aggregates.

        Args:
            site_id:      Building / site identifier (context only in output).
            floor:        Floor label used by ``zone_is_on_floor``.
            site_records: All records for the site (filtering happens here).
            start / end:  Date window for context.
        """
        floor_records = [r for r in site_records if WaterTableProcessor.zone_is_on_floor(r.get("zone_id"), floor)]

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

        # Group by zone_id — last volume_liters wins (cumulative meter read)
        zone_data: dict[str, dict[str, Any]] = {}
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

        zones = []
        total_volume = 0.0
        all_flows: list[float] = []
        for zone_id, data in zone_data.items():
            avg_flow = sum(data["flows"]) / len(data["flows"]) if data["flows"] else 0.0
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

        zones.sort(key=lambda z: z["liters"], reverse=True)

        return {
            "floor": floor,
            "site_id": site_id,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "total_liters": round(total_volume, 2),
            "avg_flow_lpm": round(sum(all_flows) / len(all_flows) if all_flows else 0.0, 2),
            "zone_count": len(zone_data),
            "zones": zones,
            "record_count": len(floor_records),
        }

    # ------------------------------------------------------------------
    # Top-N ranking
    # ------------------------------------------------------------------

    @staticmethod
    def rank_top_zones(
        records: list[dict[str, Any]],
        limit: int,
        days: int,
    ) -> list[dict[str, Any]]:
        """Group by zone_id, sort by volume descending, return top N.

        Args:
            records: All records for the site/period.
            limit:   Maximum zones to return.
            days:    Look-back period (carried through to output only).
        """
        zone_consumption: dict[str, dict[str, Any]] = {}
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

        top_zones = []
        sorted_zones = sorted(zone_consumption.items(), key=lambda x: x[1]["volume_liters"], reverse=True)[:limit]
        for rank, (zone_id, data) in enumerate(sorted_zones, 1):
            avg_flow = sum(data["flows"]) / len(data["flows"]) if data["flows"] else 0.0
            peak_flow = max(data["flows"]) if data["flows"] else 0.0
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

    # ------------------------------------------------------------------
    # Daily trend
    # ------------------------------------------------------------------

    @staticmethod
    def build_zone_trend(
        zone_id: str,
        zone_records: list[dict[str, Any]],
        days: int,
    ) -> dict[str, Any]:
        """Group records by date, compute daily totals.

        Args:
            zone_id:      Zone identifier (carried through to output).
            zone_records: Pre-filtered rows for this zone.
            days:         Look-back period (carried through to output).
        """
        if not zone_records:
            return {
                "zone_id": zone_id,
                "zone_name": None,
                "days": days,
                "data": [],
                "total_liters": 0,
                "average_daily_liters": 0,
            }

        zone_name = zone_records[0].get("zone_name")

        daily_data: dict[str, dict[str, Any]] = {}
        for record in zone_records:
            timestamp = record["timestamp"]
            record_date = (
                datetime.fromisoformat(timestamp).date() if isinstance(timestamp, str) else timestamp.date()
            )
            date_str = record_date.isoformat()
            if date_str not in daily_data:
                daily_data[date_str] = {"volume_liters": 0, "flows": []}
            daily_data[date_str]["volume_liters"] = max(
                daily_data[date_str]["volume_liters"], record.get("volume_liters", 0)
            )
            daily_data[date_str]["flows"].append(record.get("flow_rate_lpm", 0))

        trend_data = []
        total_liters = 0.0
        for date_str in sorted(daily_data.keys()):
            data = daily_data[date_str]
            avg_flow = sum(data["flows"]) / len(data["flows"]) if data["flows"] else 0.0
            liters = data["volume_liters"]
            trend_data.append(
                {
                    "date": date_str,
                    "liters": round(liters, 2),
                    "avg_flow_lpm": round(avg_flow, 2),
                }
            )
            total_liters += liters

        average_daily = total_liters / len(trend_data) if trend_data else 0.0

        return {
            "zone_id": zone_id,
            "zone_name": zone_name,
            "days": days,
            "data": trend_data,
            "total_liters": round(total_liters, 2),
            "average_daily_liters": round(average_daily, 2),
        }

    # ------------------------------------------------------------------
    # Zone-vs-building comparison
    # ------------------------------------------------------------------

    @staticmethod
    def compare_zone_vs_building(
        zone_id: str,
        zone_name: str | None,
        site_id: str,
        zone_liters: float,
        building_volumes: list[float],
        days: int,
    ) -> dict[str, Any]:
        """Compute zone/building daily-average difference.

        Args:
            zone_id / zone_name / site_id: Identifiers carried into output.
            zone_liters:      Total zone consumption in the period.
            building_volumes: All ``volume_liters`` values for the building.
            days:             Period length used to derive daily averages.
        """
        building_liters = max(building_volumes) - min(building_volumes) if building_volumes else 0.0
        zone_daily_avg = zone_liters / days if days > 0 else 0.0
        building_daily_avg = building_liters / days if days > 0 else 0.0

        if building_daily_avg > 0:
            difference_percent = ((zone_daily_avg - building_daily_avg) / building_daily_avg) * 100
        else:
            difference_percent = 0.0

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

    # ------------------------------------------------------------------
    # Floor helper
    # ------------------------------------------------------------------

    @staticmethod
    def zone_is_on_floor(zone_id: str | None, floor: str) -> bool:
        """Return True if zone_id belongs to the given floor label.

        Supports:
        - Numeric zones: "001-099" or "L0" → int range 1-99
        - Floor-prefix zones: "L1-A" starts with "L1"
        """
        if not zone_id:
            return False
        try:
            zone_num = int(zone_id)
            if floor in {"L0", "001-099"}:
                return 1 <= zone_num <= 99
            if floor in {"L1", "100-199"}:
                return 100 <= zone_num <= 199
            if floor in {"L2", "200-299"}:
                return 200 <= zone_num <= 299
        except ValueError:
            pass
        return zone_id.startswith(floor)
