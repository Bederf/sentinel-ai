# Monitoring Stack Operations

> Deployment, configuration, and maintenance of the Loki + Promtail + Grafana observability stack.

## Stack Overview

The monitoring stack runs on the shared `/opt/aimthelaw` infrastructure alongside the BMS backend.

| Service | Port | Purpose |
|---------|------|---------|
| Loki | 3100 | Log aggregation and querying |
| Promtail | 9080 | Log collection agent (tails files, ships to Loki) |
| Grafana | 3000 | Dashboards, alerting, visualization |
| Prometheus | 9090 | Metrics collection (optional) |

## Configuration Files

All configs live at `/opt/aimthelaw/config/`:

| File | Purpose |
|------|---------|
| `loki-config.yml` | Loki server, retention, storage, schema |
| `promtail-config.yml` | Scrape jobs, label extraction, file paths |
| `grafana/provisioning/dashboards/*.json` | Auto-provisioned Grafana dashboards |
| `grafana/provisioning/alerting/*.yml` | Alert rules |
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
# Loki readiness
curl -s http://localhost:3100/ready

# Promtail targets
curl -s http://localhost:9080/targets | grep READY

# Grafana health
curl -s http://localhost:3000/api/health
```

### View service logs

```bash
docker logs loki --tail 50
docker logs promtail --tail 50
docker logs grafana --tail 50
```

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

| Dashboard | UID | Panels |
|-----------|-----|--------|
| PARASITE Decision Pipeline | `sentinel-parasite-decisions` | 9 (stats, pie charts, logs, timeseries) |
| Security Operations | `sentinel-security-operations` | 7 (failed logins, suspicious UAs, device control, API errors) |

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

Five SENTINEL alert rules are provisioned via `/opt/aimthelaw/config/grafana/provisioning/alerting/sentinel-security-alert-rules.yml`:

| Rule | Trigger | Severity |
|------|---------|----------|
| Brute Force Attempt | >5 failed logins in 5min | Critical |
| MFA Brute Force | >3 failed MFA in 5min | Critical |
| Error Spike | >10 ERROR/CRITICAL in 5min | Warning |
| Suspicious Request Pattern | SQLi/scanner in 15min | Warning |
| Audit Log Flow Check | No audit data in 24h | Warning |

## Related Docs

- [Logging Architecture](../08-security/logging-architecture.md) — Design and pipeline details
- [Audit Logging](../06-safety-compliance/audit-logging.md) — Event format and compliance
- [Troubleshooting](../05-troubleshooting/logging-observability.md) — Common issues and fixes
