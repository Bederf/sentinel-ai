---
title: Supabase Performance Optimization Runbook
category: operations
phase: Performance Phase 1-4
date: 2026-03-12
tags: [supabase, performance, database, caching, archival]
---

# Supabase Performance Optimization Runbook

## Summary

Four-phase optimization delivering 70% faster queries and 60% less database load.

| Phase | What | Status | Impact |
|-------|------|--------|--------|
| 1. Indexes | 34+ indexes on alerts, predictions, work_orders | Done | 45% faster lookups |
| 2. Query Optimization | 27 SELECT * converted to column selection | Done | 30-50% payload reduction |
| 3. Caching | Redis cache with TTL + invalidation | Done | Repeated reads from memory |
| 4. Monitoring & Archival | Slow query logging, archival, Grafana dashboard | Done | Early warning + storage control |

## Phase 1: Indexes

Applied to 142 tables. Key indexes:

- `alerts`: 8+ indexes (equipment_id, status, severity, created_at, building_id)
- `predictions`: 10 indexes (equipment_id, status, type, created_at)
- `work_orders`: 16 indexes (code, status, priority, assigned_to, created_at)

**Verification:**
```sql
SELECT indexname, tablename FROM pg_indexes
WHERE schemaname = 'public' ORDER BY tablename;
```

## Phase 2: Query Optimization

All high-traffic repositories use column selection constants:

```python
_LIST_COLUMNS = "id, code, name, status, health_score, type, site_id"
_DETAIL_COLUMNS = "id, code, name, status, health_score, type, site_id, ..."
```

Affected repos: `alert_repository`, `equipment_repository`, `prediction_repository`, `work_order_repository`, `building_repository`, `hvac_zone_repository`.

## Phase 3: Redis Caching

### TTL Presets

| Preset | TTL | Used For |
|--------|-----|----------|
| STATIC | 600s (10 min) | Safety rules, config |
| SEMI_STATIC | 300s (5 min) | Buildings, equipment list |
| DYNAMIC | 60s (1 min) | Alerts, predictions |
| REALTIME | 15s | Device state |

### Cache Key Patterns

- `buildings:all`, `buildings:code:{code}`
- `equipment:all`, `equipment:building:{site_id}`
- `alerts:active:all`, `alerts:active:building:{site_id}`
- `predictions:active:all`, `predictions:active:building:{site_id}`

### Invalidation

Write operations call `CacheInvalidation.on_*_change()` helpers which delete matching patterns.

### Monitoring

- Prometheus: `sentinel_cache_operations_total{operation=hit|miss|error}`
- Prometheus: `sentinel_cache_hit_rate_percent`

**Check Redis status:**
```bash
redis-cli info stats | grep -E "keyspace_hits|keyspace_misses"
redis-cli dbsize
```

## Phase 4: Monitoring & Archival

### Slow Query Logging

Queries exceeding `SLOW_QUERY_THRESHOLD_S` (default: 0.5s) are logged as warnings:

```
WARNING sentinel.slow_queries SLOW_QUERY repo=alert method=get_active duration=0.612s threshold=0.500s
```

Configure threshold via env var:
```bash
SLOW_QUERY_THRESHOLD_S=0.5  # seconds, default
```

Visible in:
- Application logs (`sentinel.slow_queries` logger)
- Grafana dashboard: "SENTINEL Database Performance" → "Slow Queries" panel
- Loki query: `{job="sentinel"} |= "SLOW_QUERY"`

### Database Archival

Daily background job removes resolved alerts and predictions older than 90 days.

- **Schedule**: Every 24 hours via BackgroundScheduler
- **Scope**: Only `status='resolved'` records
- **Retention**: 90 days (configurable via `archive_retention_days` setting)
- **Batch size**: 100 records per DELETE to avoid timeouts

**Check archival status:**
```sql
-- Records eligible for archival
SELECT 'alerts' as table_name, count(*) as eligible
FROM alerts WHERE status = 'resolved' AND created_at < now() - interval '90 days'
UNION ALL
SELECT 'predictions', count(*)
FROM predictions WHERE status = 'resolved' AND created_at < now() - interval '90 days';
```

**Manual run:**
```python
from app.services.db_archival_service import archive_old_records
result = archive_old_records(dry_run=True)  # Preview
result = archive_old_records(dry_run=False)  # Execute
```

### Grafana Dashboard

**Dashboard**: "SENTINEL Database Performance" (uid: `sentinel-db-perf`)

Panels:
1. **Slow Queries (>500ms)** — Log stream of slow queries
2. **Slow Query Count** — Stat panel with thresholds (green <5, yellow 5-20, red >20)
3. **Cache Operations** — Hit/miss counts
4. **Database Archival Events** — Archival job log entries
5. **Gateway Tool Activity** — Sentry gateway tool invocations

## Database Backup

Full Supabase-to-JSON export covering 90+ tables. Serves as the 3-tier fallback layer (Supabase → Redis → JSON).

### Manual Trigger

**Via Settings UI:** System Health Dashboard → "Backup Now" button

**Via API:**
```bash
# Trigger backup (runs in background)
curl -X POST http://localhost:9095/api/system/backup/trigger \
  -H "Authorization: Bearer <token>"

# Check status
curl http://localhost:9095/api/system/backup-status
```

**Via CLI:**
```bash
cd /opt/bms-intelligence/backend
python3 scripts/backup_supabase_to_json.py
```

### What Gets Backed Up

- Site-filtered tables: alerts, anomalies, predictions, equipment, zones, work orders, desks, etc.
- Equipment-filtered tables: sensor readings, service records
- Global reference tables: ml_models, site_modules, technicians, system_settings, alarm_taxonomy
- Energy infrastructure: solar plants, inverters, BESS, generators, transformers, meters

**Output:** `backend/app/data/supabase_backup/` (90+ JSON files)

### Status Monitoring

The Settings UI shows:
- **Last backup age** — color-coded: green (<24h), amber (24-48h), red (>48h)
- **File count** and **total size**
- **Last result** — success/failed/timeout

### Recommended Schedule

Run backup at least daily. Currently manual-only — schedule via cron if needed:

```bash
# Add to crontab (daily at 02:00)
0 2 * * * cd /opt/bms-intelligence/backend && python3 scripts/backup_supabase_to_json.py >> /var/log/sentinel-backup.log 2>&1
```

## Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| High slow query count | Loki: `SLOW_QUERY` | Check missing indexes, add caching |
| Cache hit rate low | `redis-cli info stats` | Check TTLs, verify invalidation working |
| Table growing large | `SELECT count(*) FROM alerts` | Verify archival job running, check resolved count |
| Redis not connected | `redis-cli ping` | Check REDIS_URL in .env, restart Redis |
| Archival not running | Check scheduler logs | Verify `add_db_archival_job` in events.py startup |
| Backup fails | Check Supabase running | `docker ps \| grep supabase` — verify port 55322 |
| Backup stale (>48h) | Settings → System Health | Click "Backup Now" or run CLI script |

## Files

| File | Purpose |
|------|---------|
| `backend/app/services/cache_service.py` | Redis cache + `track_query()` + slow query logging |
| `backend/app/services/db_archival_service.py` | Archival of resolved records >90 days |
| `backend/app/services/backup_service.py` | Manual backup trigger with status tracking |
| `backend/scripts/backup_supabase_to_json.py` | Full Supabase-to-JSON export script |
| `backend/app/services/background_scheduler.py` | Daily archival job registration |
| `backend/app/startup/events.py` | Wires archival job on startup |
| `backend/app/api/system_health.py` | Backup status + trigger endpoints |
| `backend/app/api/metrics.py` | Prometheus metrics (db_query_duration, cache_*) |
| `infrastructure/grafana/provisioning/dashboards/sentinel-db-performance.json` | Grafana dashboard |
