---
title: "Monitoring Stack Operations"
type: "guide"
status: "draft"
version: "1.1.0"
created: "2026-03-31"
updated: "2026-06-14"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Monitoring Stack Operations

> Deployment, configuration, and maintenance of the Loki + Promtail + Grafana observability stack.

## Stack Overview

The monitoring stack runs on the shared `/opt/aimthelaw` infrastructure alongside the BMS backend.

| Service | Port | Purpose |
|---------|------|---------|
| Prometheus | 9090 | Metrics scraping (6 targets: SENTINEL backend ×2, node-exporter, cadvisor, sentry-bridge, self) |
| Grafana | 3000 | Dashboards, alerting, visualization |
| Alertmanager | 9093 | Alert routing, silencing, aggregation |
| Loki | 3100 | Log aggregation and querying |
| Promtail | 9080 | Log collection agent (tails files, ships to Loki) |
| Node Exporter | 9100 | System-level metrics (CPU, memory, disk, network) |
| cAdvisor | 8080 | Container-level metrics (CPU, memory, network per container) |
| PgBouncer | 6432 | Connection pooler for background workers |
| PgBouncer Exporter* | 9127 | PgBouncer metrics for Prometheus (not yet deployed) |

## Configuration Files

All configs live at `/opt/aimthelaw/config/`:

| File | Purpose |
|------|---------|
| `loki-config.yml` | Loki server, retention, storage, schema |
| `promtail-config.yml` | Scrape jobs, label extraction, file paths |
| `grafana/provisioning/dashboards/*.json` | Auto-provisioned Grafana dashboards |
| `grafana/provisioning/alerting/*.yml` | Alert rules |
| `prometheus.yml` | Prometheus scrape targets (6 targets: sentinel-governance, sentinel-discipline, node-exporter, cadvisor, sentry-bridge, self) |
| `alertmanager.yml` | Alertmanager routing, receivers, inhibition rules |
| `docker-compose.monitoring.yml` | Container orchestration |

**Repo copies** (version-controlled, may differ from deployed):

| Repo Path | Deployed Path |
|-----------|---------------|
| `infrastructure/promtail/promtail-config.yaml` | `/opt/aimthelaw/config/promtail-config.yml` |
| `infrastructure/grafana/provisioning/dashboards/` | `/opt/aimthelaw/config/grafana/provisioning/dashboards/` |
| `infrastructure/loki/loki-config.yaml` | `/opt/aimthelaw/config/loki-config.yml` |
| `infrastructure/prometheus/` | `/opt/aimthelaw/config/prometheus.yml` |

### Recommendation Energy Feedback Panels

Executed recommendation outcomes must show measured impact, not projected savings. The recommendation feedback loop exports actual before/after telemetry values from the backend `/metrics` endpoint:

| Metric | Source | Meaning |
|--------|--------|---------|
| `sentinel_recommendation_baseline_energy_kwh` | `recommendations.baseline_energy_kwh` | Actual kWh measured before implementation |
| `sentinel_recommendation_actual_energy_kwh` | `recommendations.actual_energy_kwh` | Actual kWh measured after implementation |
| `sentinel_recommendation_actual_saving_kwh` | `recommendations.actual_saving_kwh` | Before kWh minus after kWh |
| `sentinel_recommendation_actual_saving_zar` | `recommendations.actual_saving_zar` | Measured kWh delta multiplied by tariff |

Provisioned panels:

| Dashboard file | Panels |
|----------------|--------|
| `sentinel-energy.json` | Measured Rec kWh Saved; Measured Rec R Saved; Recommendation Before vs After kWh |
| `sentinel-ai-governance-live.json` | Verified Rec kWh Impact; Verified Rec R Impact; Verified Recommendation Energy Outcome |

Operator UI visibility:

| Product area | View | Purpose |
|--------------|------|---------|
| System Health | AI Actions tab | Summary of AI recommendations suggested, actioned, and measured outcome |
| Optimization pages | Execution history | Same recommendation lifecycle audit in the optimization workflow |

Negative kWh or Rand values are expected when an action increases measured consumption. Do not clamp these to zero; they are evidence that the recommendation did not deliver savings during the verification window.

### Onboarding Baseline and Phase Comparison Panels

Grafana must also expose the baseline established during onboarding/shadow operation and compare later phases against it. This is broader than energy: it covers formal equipment baseline coverage, equipment health, and energy where daily kWh history is available.

| Metric | Source | Meaning |
|--------|--------|---------|
| `sentinel_equipment_baseline_coverage_percent` | `equipment_baselines` vs `equipment` | Percent of equipment with an active formal baseline record |
| `sentinel_equipment_phase_health_score_avg` | `asset_health_snapshots` + `phase_transition_log` | Average equipment health score per phase |
| `sentinel_equipment_phase_health_delta_from_shadow` | Derived from phase health averages | Health delta versus `shadow` / `shadow_live` baseline |
| `sentinel_energy_phase_avg_daily_kwh` | `energy_consumption_history` + `phase_transition_log` | Average daily kWh per phase |
| `sentinel_energy_phase_delta_from_shadow_kwh` | Derived from phase energy averages | Daily kWh delta versus `shadow` / `shadow_live` baseline |

Provisioned panels:

| Dashboard file | Panels |
|----------------|--------|
| `sentinel-energy.json` | Energy Phase Baseline vs Current Phases; Energy Delta from Shadow Baseline |
| `sentinel-ai-governance-live.json` | Equipment Baseline Coverage; Equipment Health by Phase; Equipment Health Delta from Shadow |

For site-002, the formal `equipment_baselines` table is currently empty, so baseline coverage correctly reports `0%`. Historical phase energy and health are still visible where telemetry exists, but formal equipment baseline capture must be completed during onboarding/shadow for future sites before promotion to advisory/supervised/auto.

## Common Operations

### Restart the monitoring stack

```bash
cd /opt/aimthelaw
docker compose -f docker-compose.monitoring.yml restart
```

### Restart a single service

```bash
docker restart loki      # Log storage
docker restart promtail  # Log collector
docker restart grafana   # Dashboards
```

## PgBouncer Monitoring

PgBouncer exposes pool statistics via its admin console. For Prometheus scraping, a `pgbouncer_exporter` sidecar can be deployed:

### Key metrics to monitor

| Metric | Source | Warning | Critical |
|--------|--------|---------|----------|
| Pool utilization | `SHOW POOLS` → `sv_active + sv_idle` vs pool_size | >80% | >95% |
| Connection wait time | `SHOW STATS` → `total_wait_time` | >100ms avg | >500ms avg |
| Client connections | `SHOW POOLS` → `cl_active + cl_waiting` | >80% of max_client_conn | >95% |
| Server connections | `SHOW POOLS` → `sv_active + sv_idle` | — | = default_pool_size (fully saturated) |

### Manual pool inspection

```bash
# Pool state
psql -h 127.0.0.1 -p 6432 -U postgres -d pgbouncer -c "SHOW POOLS;"

# Transaction stats
psql -h 127.0.0.1 -p 6432 -U postgres -d pgbouncer -c "SHOW STATS;"

# Active server connections
psql -h 127.0.0.1 -p 6432 -U postgres -d pgbouncer -c "SHOW SERVERS;"

# Client connections
psql -h 127.0.0.1 -p 6432 -U postgres -d pgbouncer -c "SHOW CLIENTS;"
```

### Pgbouncer Exporter (deployed)

```bash
docker run -d --name pgbouncer-exporter \
  --network host \
  -e PGBOUNCER_EXPORTER_CONNECTION_STRING="postgres://postgres:postgres@127.0.0.1:6432/pgbouncer?sslmode=disable" \
  prometheuscommunity/pgbouncer-exporter:latest
```

**Env var**: `PGBOUNCER_EXPORTER_CONNECTION_STRING` (not `PGBOUNCER_DSN` or `PGBOUNCER_URI`).

Prometheus scrapes at `192.168.48.1:9127` (Docker gateway IP). Requires UFW rule:
```bash
sudo ufw allow from 192.168.48.0/24 to any port 9127 proto tcp
```

Prometheus config (`infrastructure/prometheus/prometheus.yml`):
```yaml
- job_name: 'pgbouncer'
  static_configs:
    - targets: ['192.168.48.1:9127']
  metrics_path: '/metrics'
  scrape_interval: 15s
```

Available metrics:
- `pgbouncer_up` — exporter connected to PgBouncer
- `pgbouncer_pools_client_active_connections` — active clients
- `pgbouncer_pools_client_waiting_connections` — queued clients
- `pgbouncer_pools_server_idle_connections` — available pool capacity
- `pgbouncer_pools_server_active_connections` — connections in use
- `pgbouncer_pools_client_maxwait_seconds` — longest client wait time

### PgBouncer alert rules

Add to Grafana alerting:
| Rule | Trigger | Severity |
|------|---------|----------|
| Pool Saturation | `default_pool_size - sv_idle < 2` for 5min | Warning |
| Connection Wait Spike | `rate(pgbouncer_avg_wait_time[5m]) > 0.1` | Warning |
| Pool Exhausted | `sv_active >= default_pool_size` | Critical |

## Infrastructure Health Check

`infra/scripts/health-check.sh` runs a comprehensive check of all Sentinel infrastructure. It covers: systemd services, HTTP endpoints, Docker containers (Supabase), MQTT broker, data stores (Redis, Postgres), PgBouncer, and streaming WAL replica.

### Run the health check

```bash
# Full output
./infra/scripts/health-check.sh

# Exit code only (for cron/monitoring)
./infra/scripts/health-check.sh --quiet
```

### Streaming WAL replica checks

When `REPLICA_HOST`/`REPLICA_PORT` are set, the script verifies:
- Port connectivity to the replica
- `pg_is_in_recovery()` = `t` (confirms it's a standby, not a promoted primary)
- WAL lag in MB (`pg_wal_lag_diff`) — warns at >10 MB, fails at >100 MB
- WAL replay age — warns if replay is delayed >60s

```bash
# Override replica host/port if needed
REPLICA_HOST=164.90.235.216 REPLICA_PORT=55432 ./infra/scripts/health-check.sh
```

### Check service health

```bash
# Prometheus healthy
curl -s http://localhost:9090/-/healthy

# Prometheus scrape targets (6 targets)
curl -s http://localhost:9090/api/v1/targets | python3 -c "
import sys, json; d = json.load(sys.stdin)
for t in d['data']['activeTargets']:
    print(f\"{t['labels']['job']:30s} health={t['health']:10s} {t['labels']['instance']}\")"

# Active alerts
curl -s http://localhost:9090/api/v1/alerts | python3 -c "
import sys, json
for a in json.load(sys.stdin)['data']['alerts']:
    if a['state'] == 'firing':
        print(f\"FIRING: {a['labels']['alertname']}\")"

# Loki readiness
curl -s http://localhost:3100/ready

# Promtail targets
curl -s http://localhost:9080/targets | grep READY

# Grafana health
curl -s http://localhost:3000/api/health

# Alertmanager status
curl -s http://localhost:9093/-/healthy
```

### View service logs

```bash
docker logs loki --tail 50
docker logs promtail --tail 50
docker logs grafana --tail 50
```

## Application Policy Dry-Run Monitoring (Site-002)

Phase 109C adds an application-level scheduler job that evaluates deterministic onboarding stage thresholds every 5 minutes.

| Item | Value |
|------|-------|
| Scheduler job ID | `site_mode_policy_dry_run_site-002` |
| Interval | 300 seconds |
| Scope | Site-002 onboarding stages |
| Mode | Dry-run only (no control enforcement) |
| State file | `backend/app/data/policies/site-002-mode-policy-state.json` |
| Policy file | `backend/app/data/policies/site-002-mode-policy.json` |

### Expected startup log

`✅ Site mode policy dry-run initialized for site-002`

### Decision log patterns

- `Site mode policy dry-run hold: ...`
- `Site mode policy dry-run decision: site=site-002 decision=would_promote ...`
- `Site mode policy dry-run decision: site=site-002 decision=would_demote ...`
- `Site mode policy dry-run decision: site=site-002 decision=would_fail_closed_demote ... write_action=stop_writes`

### Manual evaluator check

```bash
cd /opt/bms-intelligence/backend
python3 - <<'PY'
import asyncio
from app.services.site_mode_policy_service import SiteModePolicyService

async def main():
    svc = SiteModePolicyService()
    result = await svc.evaluate_site("site-002")
    print(result["decision"], result["state_before"], "->", result["state_after"])

asyncio.run(main())
PY
```

## Prometheus Metrics

The SENTINEL backend exposes Prometheus metric families at `GET /metrics`. The endpoint is **Bearer-token authenticated** — Prometheus uses an auth token configured in `prometheus.yml`. Direct curl access requires the token:

```bash
# Requires auth token
curl -s -H "Authorization: Bearer <token>" http://localhost:9095/metrics | grep "^sentinel_"

# Via Prometheus (already has the token)
curl -s http://localhost:9090/api/v1/targets | python3 -c "
import sys, json
for t in json.load(sys.stdin)['data']['activeTargets']:
    print(f\"{t['labels']['job']:30s} {t['health']:10s} {t['labels']['instance']}\")"
```

### Scrape Targets

| Target | Job Name | Endpoint | Interval | Auth |
|--------|----------|----------|----------|------|
| SENTINEL Backend (governance) | `sentinel-governance` | `192.168.48.1:9095/metrics` | 10s | Bearer token |
| SENTINEL Backend (discipline) | `sentinel-discipline` | `192.168.48.1:9095/metrics` | 60s | Bearer token |
| Node Exporter | `node-exporter` | `node-exporter:9100/metrics` | 15s | None |
| cAdvisor | `cadvisor` | `cadvisor:8080/metrics` | 15s | None |
| sentry-bridge | `sentry-bridge` | `sentry-bridge:9099/metrics` | 60s | None |
| Prometheus Self | `prometheus` | `localhost:9090/metrics` | 15s | None |
| PgBouncer | `pgbouncer` | `localhost:9127/metrics` | 15s | None |

### SENTINEL Metric Families

| # | Metric | Type | Source | Wired |
|---|--------|------|--------|-------|
| 1 | `sentinel_quality_gate_evaluations_total` | Counter | quality_gate_evaluator.py | Yes |
| 2 | `sentinel_quality_gate_enforcement` | Gauge | quality_gate_evaluator.py | Yes |
| 3 | `sentinel_recommendations_total` | Counter | tier_routing_engine.py | Yes |
| 4 | `sentinel_approval_decisions_total` | Counter | approval_service.py | Yes |
| 5 | `sentinel_safety_violations_total` | Counter | safety_interlocks.py | Yes |
| 6 | `sentinel_model_drift_alerts` | Gauge | background_scheduler.py | Yes |
| 7 | `sentinel_rollback_total` | Counter | approval_service.py | Yes |
| 8 | `sentinel_info` | Info | metrics.py (static) | Yes |
| 9 | `sentinel_http_requests_total` | Counter | request_metrics.py | Yes |
| 10 | `sentinel_http_request_duration_seconds` | Histogram | request_metrics.py | Yes |
| 11 | `sentinel_http_requests_in_progress` | Gauge | request_metrics.py | Yes |
| 12 | `sentinel_tool_calls_total` | Counter | chat_tools.py | Yes |
| 13 | `sentinel_tool_call_duration_seconds` | Histogram | chat_tools.py | Yes |
| 14 | `sentinel_db_query_duration_seconds` | Histogram | cache_service.py / repositories | Yes |
| 15 | `sentinel_cache_operations_total` | Counter | cache_service.py | Yes |
| 16 | `sentinel_cache_hit_rate_percent` | Gauge | cache_service.py | Yes |

### RequestMetricsMiddleware

`backend/app/middleware/request_metrics.py` — captures HTTP request count, duration, and in-progress gauge for every request. Registered as outermost middleware to capture full lifecycle.

**Path normalization** prevents label cardinality explosion:
- UUIDs → `{id}`
- Equipment codes (`S002-AHU-B1-001`) → `{id}`
- Site IDs (`site-002`) → `{id}`
- Numeric IDs → `{id}`

Paths `/metrics`, `/health`, `/docs`, `/openapi.json` are skipped.

## Promtail Scrape Jobs

The deployed Promtail config has these SENTINEL-specific scrape jobs:

| Job Name | File Path | Labels Extracted |
|----------|-----------|-----------------|
| `sentinel-audit` | `backend/app/data/audit_log.json` | `event_type` |
| `sentinel-security` | `/var/log/sentinel/security.log` | `event_type`, `severity` |
| `sentinel-decisions` | `/var/log/sentinel/decisions.log` | `stage`, `tier`, `status`, `correlation_id`, `decision_id`, `equipment_code` |

### Adding a new scrape job

1. Edit `/opt/aimthelaw/config/promtail-config.yml`
2. Add a new `scrape_configs` entry following the existing pattern
3. Restart Promtail: `docker restart promtail`
4. Verify the new target appears: `curl -s http://localhost:9080/targets | grep <job-name>`
5. Copy the change to the repo: `infrastructure/promtail/promtail-config.yaml`

## Grafana Dashboards

### Provisioned dashboards

| Dashboard | UID | Panels | Data Source |
|-----------|-----|--------|-------------|
| SENTINEL AI Governance | `sentinel-ai-governance` | 8 (quality gate, safety, recommendations, drift, rollbacks, build info) | Prometheus |
| PARASITE Decision Pipeline | `sentinel-parasite-decisions` | 9 (stats, pie charts, logs, timeseries) | Loki |
| Security Operations | `sentinel-security-operations` | 7 (failed logins, suspicious UAs, device control, API errors) | Loki |

### Adding a new dashboard

1. Create the dashboard JSON (use an existing one as template)
2. Set the Loki datasource UID to `P8E80F9AEF21F6940`
3. Copy to `/opt/aimthelaw/config/grafana/provisioning/dashboards/`
4. Wait ~30s for auto-provisioning, or `docker restart grafana`
5. Verify at `http://localhost:3000/dashboards`
6. Copy to repo: `infrastructure/grafana/provisioning/dashboards/`

**Datasource UID:** The running Grafana instance uses `P8E80F9AEF21F6940` for the Loki datasource. All dashboard JSON files must reference this UID.

## Loki Retention

| Setting | Value | Location |
|---------|-------|----------|
| `retention_period` | `2160h` (90 days) | `limits_config` in `loki-config.yml` |
| `retention_enabled` | `true` | `compactor` in `loki-config.yml` |
| `delete_request_cancel_period` | `24h` | `compactor` in `loki-config.yml` |
| `compaction_interval` | `10m` | `compactor` in `loki-config.yml` |

The 90-day retention satisfies FSR domain 4.13 requirements.

### Verify retention is active

```bash
curl -s http://localhost:3100/config | grep -A2 retention
# expect: retention_period: 90d (or 2160h)
```

## Log Directory Setup

The backend writes logs to `/var/log/sentinel/`. This directory must exist and be writable by the backend process.

```bash
# Create if missing
sudo mkdir -p /var/log/sentinel
sudo chown bederf:bederf /var/log/sentinel

# Verify Promtail can read it (mounted as /var/log:/var/log:ro)
docker exec promtail ls -la /var/log/sentinel/
```

If `/var/log/sentinel/` is not available, the backend falls back to `backend/app/data/logs/`.

## Alert Rules

Alert rules are defined in `/opt/aimthelaw/config/prometheus/alerting-rules.yml` (Prometheus rule files) and provisioned via Grafana. **16 rules across 7 groups** are currently deployed:

### safety-critical
| Rule | Severity | Description |
|------|----------|-------------|
| `SentinelSafetyViolation` | Critical | Any safety violation in 5min |
| `SentinelQualityGateBlockWrites` | Critical | Block writes enforcement active |

### ai-governance-warning
| Rule | Severity | Description |
|------|----------|-------------|
| `SentinelModelDriftPersistent` | Warning | Drift alerts active for 1hr |
| `SentinelHighRollbackRate` | Warning | High rollback volume in 1hr |
| `SentinelQualityGateWarning` | Warning | Quality gate approaching threshold |
| `SentinelCreditExhaustion` | Warning | AI credit budget near exhaustion |
| `SchedulerJobSlow` | Warning | Scheduled job taking longer than expected |

### security-warning
| Rule | Severity | Description |
|------|----------|-------------|
| `SentinelBruteForceAttempt` | Warning | >5 failed logins in 5min |
| `SentinelSuspiciousUserAgent` | Warning | Suspicious UA pattern detected |

### bridge-health
| Rule | Severity | Description |
|------|----------|-------------|
| `SentinelAlertBridgeDown` | Critical | Sentry alert bridge unreachable |

### scheduler-health
| Rule | Severity | Description |
|------|----------|-------------|
| `SchedulerJobSlow` | Warning | Job execution time exceeded threshold |
| `SchedulerJobStuck` | Critical | Job not completing within max duration |

### prometheus-health
| Rule | Severity | Description |
|------|----------|-------------|
| `PrometheusHighCardinality` | Warning | Metric series count approaching limit |

### system-info
| Rule | Severity | Description |
|------|----------|-------------|
| `SentinelMetricsStale` | Warning | No metrics received from backend |
| `PrometheusTargetDown` | Critical | Scrape target unreachable |
| `SentinelMLGateCleared` | Info | ML advisory gate cleared |
| `HighErrorRate` | Warning | API error rate above threshold |

### Currently Firing Alerts

Check active alerts at any time:
```bash
curl -s http://localhost:9090/api/v1/alerts | python3 -c "
import sys, json
for a in json.load(sys.stdin)['data']['alerts']:
    if a['state'] == 'firing':
        print(f\"{a['labels']['alertname']:40s} severity={a['labels'].get('severity','?'):10s} since={a['activeAt']}\")"
```

## Related Docs

- [Logging Architecture](../08-security/logging-architecture.md) — Design and pipeline details
- [Audit Logging](../06-safety-compliance/audit-logging.md) — Event format and compliance
- [Troubleshooting](../05-troubleshooting/logging-observability.md) — Common issues and fixes
