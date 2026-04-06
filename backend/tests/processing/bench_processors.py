"""Baseline benchmarks for the four processing-layer modules.

Purpose
-------
Establish throughput baselines *before* any Polars migration so that a future
swap can be verified to be neutral or faster.  These are NOT performance
assertions — they simply print timing so you can record them.

Run with::

    python3 -m pytest tests/processing/bench_processors.py -v -s

Or run standalone::

    python3 tests/processing/bench_processors.py

Recorded baselines (update after each significant data-volume change)
----------------------------------------------------------------------
Date        | Env          | water rank 10k | water floor 10k | cockpit 1k | occupancy 5k | solar 8760
------------|--------------|----------------|-----------------|------------|--------------|----------
2026-03-27  | dev (Python) | 11 ms          | 76 ms           | 100 ms     | 34 ms        | 14 ms

"""

from __future__ import annotations

import statistics
import time
from datetime import UTC, date, datetime, timedelta

from app.processing.cockpit_table import CockpitTableProcessor
from app.processing.occupancy_table import aggregate_window
from app.processing.solar_table import SolarTableProcessor
from app.processing.water_table import WaterTableProcessor
from app.services.solar_annual_aggregator import HourlySnapshot

# ---------------------------------------------------------------------------
# Data generators
# ---------------------------------------------------------------------------


def _water_records(n: int) -> list[dict]:
    zones = [f"Z{i % 20}" for i in range(n)]
    return [
        {
            "meter_id": f"M{i % 5}",
            "zone_id": zones[i],
            "zone_name": f"Zone {i % 20}",
            "volume_liters": float(50 + i % 500),
            "flow_rate_lpm": float(1 + i % 20),
            "timestamp": (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=i)).isoformat(),
        }
        for i in range(n)
    ]


def _alert_records(n: int) -> list[dict]:
    sevs = ["critical", "high", "medium", "low"]
    now = datetime.now(UTC)
    return [
        {
            "id": f"a{i}",
            "severity": sevs[i % 4],
            "status": "new",
            "equipment_id": f"eq-{i % 50}",
            "site_id": "S001",
            "type": "hvac",
            "title": f"Alert {i}",
            "updated_at": (now - timedelta(minutes=i)).isoformat(),
        }
        for i in range(n)
    ]


def _occupancy_events(n: int) -> list[dict]:
    base = datetime(2026, 3, 25, 0, 0, 0, tzinfo=UTC)
    return [
        {
            "room_code": f"R{i % 30}",
            "timestamp": (base + timedelta(minutes=i * 2)).isoformat(),
            "occupied": bool(i % 2),
        }
        for i in range(n)
    ]


def _hourly_snapshots() -> list[HourlySnapshot]:
    hours = []
    base = datetime(2026, 1, 1)
    for h in range(8760):
        month = (h // 730) + 1  # rough month approximation
        if month > 12:
            month = 12
        hours.append(
            HourlySnapshot(
                hour=h,
                date=base + timedelta(hours=h),
                month=month,
                day_of_year=(h // 24) + 1,
                solar_gen_kw=10.0 + (h % 24) * 0.5,
                site_load_kw=20.0,
                bess_soc_pct=50.0,
                bess_charge_kw=2.0,
                bess_discharge_kw=1.0,
                grid_import_kw=15.0,
                grid_export_kw=3.0,
            )
        )
    return hours


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def _bench(label: str, fn, *, reps: int = 5) -> None:
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    mean_ms = statistics.mean(times) * 1000
    min_ms = min(times) * 1000
    print(f"  {label:<40}  mean={mean_ms:7.2f} ms  min={min_ms:7.2f} ms  ({reps} reps)")


def run_benchmarks() -> None:
    print("\n" + "=" * 70)
    print("PROCESSING LAYER BENCHMARKS (baseline — not assertions)")
    print("=" * 70)

    # ---- Water (10 000 records) ----
    records_10k = _water_records(10_000)
    start = date(2026, 1, 1)
    end = date(2026, 1, 31)

    print("\n[water_table] 10 000 records")
    _bench("rank_top_zones(limit=10)", lambda: WaterTableProcessor.rank_top_zones(records_10k, limit=10, days=30))
    _bench(
        "aggregate_floor_records('L1')",
        lambda: WaterTableProcessor.aggregate_floor_records("S1", "L1", records_10k, start, end),
    )
    zone_records = [r for r in records_10k if r["zone_id"] == "Z0"]
    _bench("build_zone_trend(zone records)", lambda: WaterTableProcessor.build_zone_trend("Z0", zone_records, 30))

    # ---- Cockpit (1 000 alerts, 200 intakes, 100 WOs) ----
    alerts_1k = _alert_records(1_000)
    intakes_200 = [{**_alert_records(1)[0], "id": f"i{i}", "equipment_id": f"eq-{i % 50}"} for i in range(200)]
    wos_100 = [{**_alert_records(1)[0], "id": f"wo{i}", "equipment_id": f"eq-{i % 50}"} for i in range(100)]
    print("\n[cockpit_table] 1 000 alerts + 200 intakes + 100 WOs")
    _bench("fuse (1 300 rows)", lambda: CockpitTableProcessor.fuse(alerts_1k, intakes_200, wos_100, [], None))

    # ---- Occupancy (5 000 events, 30 rooms) ----
    events_5k = _occupancy_events(5_000)
    window_end = datetime(2026, 3, 25, 23, 59, 59, tzinfo=UTC)
    print("\n[occupancy_table] 5 000 events, 30 rooms")
    _bench("aggregate_window", lambda: aggregate_window(events_5k, window_end))

    # ---- Solar (8 760 hourly snapshots) ----
    hourly = _hourly_snapshots()
    print("\n[solar_table] 8 760 hourly snapshots (full year)")
    _bench("aggregate_months", lambda: SolarTableProcessor.aggregate_months(hourly))
    monthly = SolarTableProcessor.aggregate_months(hourly)
    _bench("calculate_learning_curve", lambda: SolarTableProcessor.calculate_learning_curve(monthly))
    _bench("aggregate_seasons", lambda: SolarTableProcessor.aggregate_seasons(monthly))

    print("\n" + "=" * 70)
    print("Record these numbers before any engine swap (Polars etc.).")
    print("=" * 70 + "\n")


# ---------------------------------------------------------------------------
# pytest entry point (use -s to see output)
# ---------------------------------------------------------------------------


def test_bench_water_rank():
    """Smoke + baseline — should complete in < 2 s for 10k records."""
    records = _water_records(10_000)
    t0 = time.perf_counter()
    result = WaterTableProcessor.rank_top_zones(records, limit=10, days=30)
    elapsed = time.perf_counter() - t0
    assert len(result) == 10
    assert elapsed < 2.0, f"rank_top_zones(10k) took {elapsed:.2f}s — check for regression"


def test_bench_cockpit_fuse():
    """Smoke + baseline — 1k alerts should fuse in < 2 s."""
    alerts = _alert_records(1_000)
    t0 = time.perf_counter()
    issues, _, _, _ = CockpitTableProcessor.fuse(alerts, [], [], [], None)
    elapsed = time.perf_counter() - t0
    assert len(issues) > 0
    assert elapsed < 2.0, f"cockpit fuse(1k) took {elapsed:.2f}s — check for regression"


def test_bench_occupancy_aggregate():
    """Smoke + baseline — 5k events should aggregate in < 2 s."""
    events = _occupancy_events(5_000)
    window_end = datetime(2026, 3, 25, 23, 59, 59, tzinfo=UTC)
    t0 = time.perf_counter()
    result = aggregate_window(events, window_end)
    elapsed = time.perf_counter() - t0
    assert result["rooms_total"] == 30
    assert elapsed < 2.0, f"occupancy aggregate(5k) took {elapsed:.2f}s — check for regression"


def test_bench_solar_months():
    """Smoke + baseline — 8 760 snapshots should aggregate in < 5 s."""
    hourly = _hourly_snapshots()
    t0 = time.perf_counter()
    monthly = SolarTableProcessor.aggregate_months(hourly)
    elapsed = time.perf_counter() - t0
    assert len(monthly) == 12
    assert elapsed < 5.0, f"solar aggregate_months(8760) took {elapsed:.2f}s — check for regression"


if __name__ == "__main__":
    run_benchmarks()
