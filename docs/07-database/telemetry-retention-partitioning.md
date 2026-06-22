# Telemetry Retention & Partitioning Strategy

> **Status**: Draft 2026-06-14
> **Database**: 5.2 GB / 233 tables / 596 indexes
> **Growth driver**: Telemetry ingestion, ML predictions, audit logs

## Current State

| Category | Approx Size | Growth Rate | Retention |
|----------|-------------|-------------|-----------|
| Telemetry timeseries | Unknown | Per-site polling cadence | Unlimited (no purge) |
| ML predictions | Unknown | Per-retraining cycle | Unlimited |
| Audit logs | ~30k rows | Event-driven | Unlimited |
| Work orders | ~7 rows | Per-incident | Indefinite |
| Recommendations | ~90k rows | Per-evaluation cycle | Unlimited |

## Risks

1. **No retention policy** — telemetry data accumulates indefinitely. At 100 sites, the 5.2 GB baseline could grow to 50+ GB without any purge.
2. **No partitioning** — all data in monolithic tables. `DELETE` for old data causes vacuum bloat; no time-based partition pruning.
3. **No archival strategy** — cold data lives in the same tables as hot data, slowing queries over time.

## Recommended Approach

### Phase 1: Measure (1-2 sprints)

Before partitioning, establish actual growth rates:

```sql
-- Table size by schema
SELECT schemaname, tablename,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 20;

-- Estimate daily write volume
SELECT schemaname, tablename,
       n_tup_ins as inserts_since_stats_reset,
       n_live_tup as estimated_row_count
FROM pg_stat_user_tables
ORDER BY n_tup_ins DESC
LIMIT 10;
```

### Phase 2: Retain & Purge (2-3 sprints)

Define retention per data class:

| Data Class | Retention | Action | Rationale |
|------------|-----------|--------|-----------|
| Raw telemetry (sensor readings) | 90 days | Delete | Aggregated summaries preserved |
| Aggregated telemetry (hourly/daily) | 2 years | Archive to cold storage | Trend analysis, reporting |
| ML predictions | 1 year | Delete | Model performance tracked via registry |
| Audit logs | 3 years | Archive | Compliance requirement |
| Work orders | Indefinite | Keep | Operational record |
| Recommendations | 1 year | Delete | Superseded by newer runs |

Implementation:

```sql
-- Delete raw telemetry older than 90 days
DELETE FROM sensor_readings WHERE timestamp < NOW() - INTERVAL '90 days';
-- Run as a monthly cron job, outside peak hours
```

### Phase 3: Partition (3-4 sprints)

Partition large tables by time range:

```sql
-- Convert sensor_readings to partitioned table
CREATE TABLE sensor_readings (
    id UUID DEFAULT gen_random_uuid(),
    site_id TEXT,
    device_id TEXT,
    metric TEXT,
    value DOUBLE PRECISION,
    timestamp TIMESTAMPTZ,
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Create monthly partitions
CREATE TABLE sensor_readings_2026_01 PARTITION OF sensor_readings
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE sensor_readings_2026_02 PARTITION OF sensor_readings
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
-- ... automated via pg_partman or cron
```

### Phase 4: Automate (1 sprint)

- Schedule monthly purge via pg_cron or systemd timer
- Add Prometheus metrics for table size and growth rate
- Alert when any table exceeds `autovacuum_vacuum_threshold` bloat

## Related Docs

- `docs/05-operations/monitoring-stack.md` — existing retention for Loki logs (90 days)
- `docs/10-operations/disaster-recovery.md` — backup/restore of all data
