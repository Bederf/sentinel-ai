# `app/processing/` — Tabular Processing Boundary

## Purpose

This package isolates all tabular shaping from the service and repository
layers. Its single job: accept pre-fetched data, transform it, return a
result. No database access. No side effects.

```
API layer (FastAPI routers)
        │
        ▼
Service layer  ←── fetches via repositories
        │
        ▼
Processing layer  ←── owns groupby / rank / sort / aggregate / dedupe
        │
        ▼
Repository layer  ←── fetch / persist only
```

---

## What belongs here

- `groupby` + `sum / avg / max / count` across a list of records
- Ranking and ordering of records (top-N, sort by composite key)
- Deduplication and merge logic across multiple sources
- Sliding-window / time-bucket aggregations
- Feature vector assembly from multiple scalar inputs
- Multi-source joins that produce a new tabular result

---

## What does NOT belong here

- Database queries or writes — use repositories
- API request/response validation — use FastAPI schemas
- Business rules that decide *what* to do — use services
- ML model inference — stays in `ml/`

---

## Modules

| Module | Processor | Domain |
|--------|-----------|--------|
| `water_table.py` | `WaterTableProcessor` | Zone / floor / building water consumption aggregation |
| `cockpit_table.py` | `CockpitTableProcessor` | Multi-source issue normalise → dedupe → rank → source status |
| `occupancy_table.py` | `aggregate_window`, `compute_room_occupied_minutes` | Room-level occupancy event aggregation |
| `solar_table.py` | `SolarTableProcessor` | Hourly solar snapshot → monthly / seasonal rollup + learning curve |

---

## Stable contract (do not break)

Every public method accepts plain Python types and returns plain Python types:

```python
records: list[dict[str, Any]] → result: dict[str, Any] | list[dict[str, Any]]
```

No Pydantic models, no dataclasses, no custom types as *inputs* (outputs may
use schema types where the caller already expects them, e.g. `CockpitIssue`).

This contract is what makes Polars adoption a contained internal swap.

---

## Polars adoption path

To migrate a processor to Polars, open the module and replace the method
body. The signature and output shape must stay identical.

### Example — `WaterTableProcessor.rank_top_zones`

```python
# Current (plain Python dicts):
@staticmethod
def rank_top_zones(records, limit, days):
    zone_consumption: dict[str, Any] = {}
    for record in records:
        zone_id = record.get("zone_id")
        ...  # manual groupby

# Polars drop-in:
@staticmethod
def rank_top_zones(records, limit, days):
    import polars as pl
    df = pl.DataFrame(records)
    top = (
        df.group_by("zone_id")
          .agg(
              pl.max("volume_liters"),
              pl.mean("flow_rate_lpm").alias("avg_flow_lpm"),
              pl.max("flow_rate_lpm").alias("peak_flow_lpm"),
              pl.col("meter_id").n_unique().alias("meter_count"),
              pl.first("zone_name"),
          )
          .sort("volume_liters", descending=True)
          .head(limit)
          .with_row_index(name="rank", offset=1)
          .with_columns(pl.lit(days).alias("days"))
    )
    return top.to_dicts()   # same output shape
```

### Recommended migration order (by data volume / frequency)

1. **`water_table.py`** — highest record volumes; groupby patterns map
   directly to Polars `group_by().agg()`
2. **`occupancy_table.py`** — state-machine scan over sorted events; Polars
   `shift()` + `cum_sum()` replaces the Python loop
3. **`cockpit_table.py`** — multi-source sort + dedup; lower volume but
   complex sort key benefits from Polars `sort()`
4. **`solar_table.py`** — 8 760-row annual data; Polars fastest here but
   current Python is already fast enough

---

## Time handling (occupancy)

`_to_naive_utc` in `occupancy_table.py` strips timezone before arithmetic.
This is intentional: Johannesburg (UTC+2, no DST) means the offset is fixed.

**If the deployment timezone changes**, update `_ensure_timezone` in
`occupancy_daily_ml_processing_service.py` — that is the single source of
truth for the local/UTC boundary. The processing functions receive
pre-constructed `window_end_utc` and do not need to know the site timezone.

---

## Output contract per module

### `water_table.py`

All volume fields are `float`, rounded to 2 decimal places.
Flow fields are `float` in LPM, rounded to 2 decimal places.
Date strings are ISO 8601 (`YYYY-MM-DD`).

### `cockpit_table.py`

`fuse()` returns a 4-tuple:
- `list[CockpitIssue]` — ordered: highest severity first, resolved last
- `list[CockpitSourceStatus]` — always 3 entries, order matches `SOURCE_ORDER`
- `list[CockpitActionAudit]` — newest first, capped at 10
- `str | None` — selected issue id (caller's preference or top issue)

Sort tie-breaks for issues (in order): severity → resolved → SLA seconds →
recency → source priority → issue id. This is deterministic across equal
timestamps.

### `occupancy_table.py`

`aggregate_window()` returns a dict with `rooms` (list), `rooms_total` (int),
and `window.end_utc` (ISO 8601 with tz). `occupied_percent` is rounded to 2
decimal places. Events with unparseable timestamps are silently skipped.

### `solar_table.py`

`aggregate_months()` returns only months that have data (sparse input → sparse
output). `calculate_learning_curve()` length always equals `len(monthly_data)`.
`aggregate_seasons()` returns only seasons with matching months present.

---

## Baselines (plain Python, dev machine, 2026-03-27)

Run `python3 -m pytest tests/processing/bench_processors.py -v -s` to refresh.

| Benchmark | Input | Mean |
|-----------|-------|------|
| `water: rank_top_zones` | 10 000 records | 11 ms |
| `water: aggregate_floor` | 10 000 records | 76 ms |
| `cockpit: fuse` | 1 000 alerts | 100 ms |
| `occupancy: aggregate_window` | 5 000 events / 30 rooms | 34 ms |
| `solar: aggregate_months` | 8 760 hourly snapshots | 14 ms |
| `solar: aggregate_seasons` | 12 monthly summaries | < 1 ms |

---

## Known repository violations (follow-on cleanup)

The following repository methods contain ranking / aggregation logic that
should eventually migrate to this layer:

| File | Method | Violation |
|------|--------|-----------|
| `water_consumption_repository.py:745` | (unnamed, in `get_top_consuming_zones`) | Sorts by `total_liters` and assigns `rank` |
| `water_cost_repository.py:287` | (billing rollup) | `sorted(by_zone.items())` for presentation |
| `budget_repository.py:60` | `get_budget_vs_actual` | Manual aggregation with optional fallback |
| `parasite_decision_repository.py:489` | `get_decision_stats` | Aggregate metrics assembled in repository |
| `sla_repository.py:187` | `get_sla_metrics` | Aggregate metrics assembled in repository |

These are pre-existing patterns. They do not block Polars adoption for the
four domains above, but they are the natural next targets for this boundary.
