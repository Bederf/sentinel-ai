"""Parity tests for WaterTableProcessor.

Verifies that the processor produces the same results as the original
inline logic that lived in WaterAggregationService before the refactor.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.processing.water_table import WaterTableProcessor

# ---------------------------------------------------------------------------
# Fixtures — deterministic fake records
# ---------------------------------------------------------------------------


@pytest.fixture()
def two_meter_zone_records():
    """Three records across two meters for zone 'Z1'."""
    return [
        {"meter_id": "M1", "zone_id": "Z1", "zone_name": "Zone One", "volume_liters": 100.0, "flow_rate_lpm": 5.0},
        {"meter_id": "M1", "zone_id": "Z1", "zone_name": "Zone One", "volume_liters": 120.0, "flow_rate_lpm": 6.0},
        {"meter_id": "M2", "zone_id": "Z1", "zone_name": "Zone One", "volume_liters": 50.0, "flow_rate_lpm": 2.5},
    ]


@pytest.fixture()
def multi_zone_site_records():
    """Six records: three zones, two L1 and one L2."""
    return [
        {"meter_id": "M1", "zone_id": "101", "zone_name": "Z101", "volume_liters": 200.0, "flow_rate_lpm": 10.0},
        {"meter_id": "M1", "zone_id": "102", "zone_name": "Z102", "volume_liters": 150.0, "flow_rate_lpm": 7.5},
        {"meter_id": "M2", "zone_id": "101", "zone_name": "Z101", "volume_liters": 180.0, "flow_rate_lpm": 9.0},
        {"meter_id": "M3", "zone_id": "201", "zone_name": "Z201", "volume_liters": 300.0, "flow_rate_lpm": 15.0},
        {"meter_id": "M3", "zone_id": "201", "zone_name": "Z201", "volume_liters": 310.0, "flow_rate_lpm": 15.5},
        {"meter_id": "M1", "zone_id": "101", "zone_name": "Z101", "volume_liters": 190.0, "flow_rate_lpm": 9.5},
    ]


# ---------------------------------------------------------------------------
# aggregate_zone_records
# ---------------------------------------------------------------------------


class TestAggregateZoneRecords:
    def test_empty_returns_zero_totals(self):
        result = WaterTableProcessor.aggregate_zone_records("Z1", [], date(2026, 1, 1), date(2026, 1, 31))
        assert result["total_liters"] == 0
        assert result["meter_count"] == 0
        assert result["meters"] == []
        assert result["record_count"] == 0

    def test_zone_name_taken_from_first_record(self, two_meter_zone_records):
        result = WaterTableProcessor.aggregate_zone_records(
            "Z1", two_meter_zone_records, date(2026, 1, 1), date(2026, 1, 31)
        )
        assert result["zone_name"] == "Zone One"

    def test_meter_count(self, two_meter_zone_records):
        result = WaterTableProcessor.aggregate_zone_records(
            "Z1", two_meter_zone_records, date(2026, 1, 1), date(2026, 1, 31)
        )
        assert result["meter_count"] == 2

    def test_record_count(self, two_meter_zone_records):
        result = WaterTableProcessor.aggregate_zone_records(
            "Z1", two_meter_zone_records, date(2026, 1, 1), date(2026, 1, 31)
        )
        assert result["record_count"] == 3

    def test_volume_last_value_per_meter(self, two_meter_zone_records):
        # M1 has two records; last volume_liters=120 is taken (each write overwrites)
        result = WaterTableProcessor.aggregate_zone_records(
            "Z1", two_meter_zone_records, date(2026, 1, 1), date(2026, 1, 31)
        )
        m1 = next(m for m in result["meters"] if m["meter_id"] == "M1")
        assert m1["liters"] == 120.0

    def test_peak_flow_across_all_meters(self, two_meter_zone_records):
        result = WaterTableProcessor.aggregate_zone_records(
            "Z1", two_meter_zone_records, date(2026, 1, 1), date(2026, 1, 31)
        )
        # Flows: 5.0, 6.0, 2.5 → peak = 6.0
        assert result["peak_flow_lpm"] == 6.0

    def test_avg_flow_across_all_meters(self, two_meter_zone_records):
        result = WaterTableProcessor.aggregate_zone_records(
            "Z1", two_meter_zone_records, date(2026, 1, 1), date(2026, 1, 31)
        )
        # avg(5.0, 6.0, 2.5) = 4.5
        assert result["avg_flow_lpm"] == pytest.approx(4.5, abs=0.01)

    def test_date_range_in_output(self, two_meter_zone_records):
        result = WaterTableProcessor.aggregate_zone_records(
            "Z1", two_meter_zone_records, date(2026, 1, 1), date(2026, 1, 31)
        )
        assert result["start_date"] == "2026-01-01"
        assert result["end_date"] == "2026-01-31"


# ---------------------------------------------------------------------------
# aggregate_floor_records
# ---------------------------------------------------------------------------


class TestAggregateFloorRecords:
    def test_filters_to_l1_only(self, multi_zone_site_records):
        result = WaterTableProcessor.aggregate_floor_records(
            "S1", "L1", multi_zone_site_records, date(2026, 1, 1), date(2026, 1, 31)
        )
        zone_ids = {z["zone_id"] for z in result["zones"]}
        assert "101" in zone_ids
        assert "102" in zone_ids
        assert "201" not in zone_ids  # L2 zone excluded

    def test_zones_sorted_by_volume_desc(self, multi_zone_site_records):
        result = WaterTableProcessor.aggregate_floor_records(
            "S1", "L1", multi_zone_site_records, date(2026, 1, 1), date(2026, 1, 31)
        )
        liters = [z["liters"] for z in result["zones"]]
        assert liters == sorted(liters, reverse=True)

    def test_empty_when_no_floor_match(self, multi_zone_site_records):
        result = WaterTableProcessor.aggregate_floor_records(
            "S1", "L9", multi_zone_site_records, date(2026, 1, 1), date(2026, 1, 31)
        )
        assert result["zone_count"] == 0
        assert result["zones"] == []

    def test_record_count_matches_floor_records(self, multi_zone_site_records):
        # L1 records: zone 101 (3) + zone 102 (1) = 4
        result = WaterTableProcessor.aggregate_floor_records(
            "S1", "L1", multi_zone_site_records, date(2026, 1, 1), date(2026, 1, 31)
        )
        assert result["record_count"] == 4


# ---------------------------------------------------------------------------
# rank_top_zones
# ---------------------------------------------------------------------------


class TestRankTopZones:
    def test_ranked_by_volume_desc(self, multi_zone_site_records):
        result = WaterTableProcessor.rank_top_zones(multi_zone_site_records, limit=10, days=30)
        volumes = [z["total_liters"] for z in result]
        assert volumes == sorted(volumes, reverse=True)

    def test_rank_field_starts_at_one(self, multi_zone_site_records):
        result = WaterTableProcessor.rank_top_zones(multi_zone_site_records, limit=10, days=30)
        assert result[0]["rank"] == 1

    def test_limit_respected(self, multi_zone_site_records):
        result = WaterTableProcessor.rank_top_zones(multi_zone_site_records, limit=1, days=30)
        assert len(result) == 1

    def test_days_carried_through(self, multi_zone_site_records):
        result = WaterTableProcessor.rank_top_zones(multi_zone_site_records, limit=10, days=7)
        assert all(z["days"] == 7 for z in result)

    def test_empty_records_returns_empty(self):
        assert WaterTableProcessor.rank_top_zones([], limit=5, days=30) == []

    def test_rows_without_zone_id_ignored(self):
        records = [
            {"meter_id": "M1", "zone_id": None, "volume_liters": 999.0, "flow_rate_lpm": 1.0},
            {"meter_id": "M1", "zone_id": "Z1", "volume_liters": 50.0, "flow_rate_lpm": 1.0},
        ]
        result = WaterTableProcessor.rank_top_zones(records, limit=10, days=30)
        assert len(result) == 1
        assert result[0]["zone_id"] == "Z1"


# ---------------------------------------------------------------------------
# build_zone_trend
# ---------------------------------------------------------------------------


class TestBuildZoneTrend:
    def test_empty_returns_zero_trend(self):
        result = WaterTableProcessor.build_zone_trend("Z1", [], 7)
        assert result["data"] == []
        assert result["total_liters"] == 0
        assert result["average_daily_liters"] == 0

    def test_groups_by_date(self):
        records = [
            {
                "timestamp": "2026-01-01T08:00:00",
                "zone_id": "Z1",
                "zone_name": "Z",
                "volume_liters": 10.0,
                "flow_rate_lpm": 1.0,
            },
            {
                "timestamp": "2026-01-01T14:00:00",
                "zone_id": "Z1",
                "zone_name": "Z",
                "volume_liters": 12.0,
                "flow_rate_lpm": 1.2,
            },
            {
                "timestamp": "2026-01-02T09:00:00",
                "zone_id": "Z1",
                "zone_name": "Z",
                "volume_liters": 8.0,
                "flow_rate_lpm": 0.8,
            },
        ]
        result = WaterTableProcessor.build_zone_trend("Z1", records, 7)
        dates = [d["date"] for d in result["data"]]
        assert len(dates) == 2
        assert "2026-01-01" in dates
        assert "2026-01-02" in dates

    def test_data_sorted_ascending(self):
        records = [
            {
                "timestamp": "2026-01-03T08:00:00",
                "zone_id": "Z1",
                "zone_name": "Z",
                "volume_liters": 5.0,
                "flow_rate_lpm": 1.0,
            },
            {
                "timestamp": "2026-01-01T08:00:00",
                "zone_id": "Z1",
                "zone_name": "Z",
                "volume_liters": 10.0,
                "flow_rate_lpm": 1.0,
            },
            {
                "timestamp": "2026-01-02T08:00:00",
                "zone_id": "Z1",
                "zone_name": "Z",
                "volume_liters": 8.0,
                "flow_rate_lpm": 1.0,
            },
        ]
        result = WaterTableProcessor.build_zone_trend("Z1", records, 7)
        dates = [d["date"] for d in result["data"]]
        assert dates == sorted(dates)

    def test_average_daily_liters(self):
        records = [
            {
                "timestamp": "2026-01-01T08:00:00",
                "zone_id": "Z1",
                "zone_name": "Z",
                "volume_liters": 10.0,
                "flow_rate_lpm": 1.0,
            },
            {
                "timestamp": "2026-01-02T08:00:00",
                "zone_id": "Z1",
                "zone_name": "Z",
                "volume_liters": 20.0,
                "flow_rate_lpm": 1.0,
            },
        ]
        result = WaterTableProcessor.build_zone_trend("Z1", records, 7)
        assert result["average_daily_liters"] == pytest.approx(15.0, abs=0.01)


# ---------------------------------------------------------------------------
# compare_zone_vs_building
# ---------------------------------------------------------------------------


class TestCompareZoneVsBuilding:
    def test_above_threshold(self):
        # Zone avg = 20 L/day, building avg = 10 L/day → 100% above
        result = WaterTableProcessor.compare_zone_vs_building(
            "Z1",
            "Zone One",
            "S1",
            zone_liters=200.0,
            building_volumes=[0.0, 100.0],  # max-min = 100 over 10 days
            days=10,
        )
        assert result["status"] == "above"
        assert result["difference_percent"] > 0

    def test_below_threshold(self):
        result = WaterTableProcessor.compare_zone_vs_building(
            "Z1",
            "Zone One",
            "S1",
            zone_liters=5.0,
            building_volumes=[0.0, 1000.0],
            days=10,
        )
        assert result["status"] == "below"

    def test_at_average(self):
        # Zone = 100 L in 10 days = 10 L/day; building also 100 L → same
        result = WaterTableProcessor.compare_zone_vs_building(
            "Z1",
            "Zone One",
            "S1",
            zone_liters=100.0,
            building_volumes=[0.0, 100.0],
            days=10,
        )
        assert result["status"] == "at_average"

    def test_empty_building_volumes(self):
        result = WaterTableProcessor.compare_zone_vs_building(
            "Z1",
            "Zone One",
            "S1",
            zone_liters=50.0,
            building_volumes=[],
            days=10,
        )
        assert result["status"] == "at_average"
        assert result["building_daily_avg"] == 0


# ---------------------------------------------------------------------------
# zone_is_on_floor
# ---------------------------------------------------------------------------


class TestZoneIsOnFloor:
    @pytest.mark.parametrize(
        "zone_id,floor,expected",
        [
            ("50", "L0", True),
            ("50", "001-099", True),
            ("99", "L0", True),
            ("100", "L0", False),
            ("100", "L1", True),
            ("199", "L1", True),
            ("200", "L1", False),
            ("200", "L2", True),
            ("L1-A", "L1", True),
            ("L2-B", "L1", False),
            (None, "L1", False),
            ("abc", "L1", False),
        ],
    )
    def test_floor_classification(self, zone_id, floor, expected):
        assert WaterTableProcessor.zone_is_on_floor(zone_id, floor) is expected
