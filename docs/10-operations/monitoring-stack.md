# Monitoring Stack Operations

> Deployment, configuration, and maintenance of the Loki + Promtail + Grafana observability stack.

## Stack Overview

The monitoring stack runs on the shared `/opt/aimthelaw` infrastructure alongside the BMS backend.

| Service | Port | Purpose |
|---------|------|---------|
| Prometheus | 9090 | Metrics scraping (SENTINEL, node-exporter, self) |
| Grafana | 3001 (→3000) | Dashboards, alerting, visualization |
| Loki | 3100 | Log aggregation and querying |
| Promtail | 9080 | Log collection agent (tails files, ships to Loki) |
| Node Exporter | 9100 | System-level metrics (CPU, memory, disk, network) |

## Configuration Files

All configs live at `/opt/aimthelaw/config/`:

| File | Purpose |
|------|---------|
| `loki-config.yml` | Loki server, retention, storage, schema |
| `promtail-config.yml` | Scrape jobs, label extraction, file paths |
| `grafana/provisioning/dashboards/*.json` | Auto-provisioned Grafana dashboards |
| `grafana/provisioning/alerting/*.yml` | Alert rules |
| `prometheus.yml` | Prometheus scrape targets (sentinel-backend, node, self) |
| `docker-compose.monitoring.yml` | Container orchestration |

**Repo copies** (version-controlled, may differ from deployed):

| Repo Path | Deployed Path |
|-----------|---------------|
| `infrastructure/promtail/promtail-config.yaml` | `/opt/aimthelaw/config/promtail-config.yml` |
| `infrastructure/grafana/provisioning/dashboards/` | `/opt/aimthelaw/config/grafana/provisioning/dashboards/` |
| `infrastructure/loki/loki-config.yaml` | `/opt/aimthelaw/config/loki-config.yml` |

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

### Check service health

```bash
# Prometheus healthy
curl -s http://localhost:9090/-/healthy

# Prometheus scrape targets
curl -s http://localhost:9090/api/v1/targets | python3 -c "
import sys, json; d = json.load(sys.stdin)
for t in d['data']['activeTargets']:
    print(f\"{t['labels']['job']:25s} health={t['health']}\")"

# Loki readiness
curl -s http://localhost:3100/ready

# Promtail targets
curl -s http://localhost:9080/targets | grep READY

# Grafana health
curl -s http://localhost:3001/api/health

# SENTINEL /metrics endpoint
curl -s http://localhost:9095/metrics | grep "^sentinel_" | head -20
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

## Prometheus Metrics (Phase 127)

The SENTINEL backend exposes 13 Prometheus metric families at `GET /metrics` (Prometheus text exposition format).

### Scrape Targets

| Target | Job Name | Endpoint | Interval |
|--------|----------|----------|----------|
| SENTINEL Backend | `sentinel-backend` | `localhost:9095/metrics` | 30s |
| Node Exporter | `node` | `localhost:9100/metrics` | 15s |
| Prometheus Self | `prometheus` | `localhost:9090/metrics` | 15s |

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

Alert rules are provisioned in two files under `/opt/aimthelaw/config/grafana/provisioning/alerting/`:

**Security alert rules** (`sentinel-security-alert-rules.yml`):

| Rule | Trigger | Severity |
|------|---------|----------|
| Brute Force Attempt | >5 failed logins in 5min | Critical |
| MFA Brute Force | >3 failed MFA in 5min | Critical |
| Error Spike | >10 ERROR/CRITICAL in 5min | Warning |
| Suspicious Request Pattern | SQLi/scanner in 15min | Warning |
| Audit Log Flow Check | No audit data in 24h | Warning |

**AI governance alert rules** (`sentinel-ai-governance-alert-rules.yml`):

| Rule | Trigger | Severity |
|------|---------|----------|
| AI Safety Violation | Any safety violation in 5min | Critical |
| Quality Gate BLOCK_WRITES | Block writes enforcement active | Critical |
| Model Drift Persistent | Drift alerts active for 1hr | Warning |
| Rollback Spike | High rollback volume in 1hr | Warning |

## Related Docs

- [Logging Architecture](../08-security/logging-architecture.md) — Design and pipeline details
- [Audit Logging](../06-safety-compliance/audit-logging.md) — Event format and compliance
- [Troubleshooting](../05-troubleshooting/logging-observability.md) — Common issues and fixes
