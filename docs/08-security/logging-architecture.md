# SENTINEL Logging Architecture

**Version:** 1.1
**Date:** 2026-02-19
**FSR Reference:** Domain 4.13 - Information Security Incident Detection
**Current Maturity:** 3.5 (target: 4.0 LOW)

## Overview

SENTINEL BMS Intelligence Platform implements centralised log aggregation with SIEM-equivalent security event alerting. All system components, application events, and security activities are collected, stored, and analysed through a unified logging pipeline.

**Compliance requirement:** FSR domain 4.13 mandates centralised log aggregation, tamper-evident storage, and automated security alerting for all FSCA-regulated financial services technology platforms.

## Architecture Diagram

```
+----------------------------------------------------------+
|                    SENTINEL Platform                      |
|                                                           |
|  +-------------+  +------------+  +------------+         |
|  |   Backend    |  |  Frontend  |  |  InfluxDB  |         |
|  |   FastAPI    |  |   Nginx    |  |  TimeSeries|         |
|  |  (Python)    |  |   (React)  |  |            |         |
|  +------+-------+  +-----+------+  +-----+------+         |
|         |                |                |                |
|         v                v                v                |
|    Docker JSON     Docker JSON      Docker JSON            |
|    Logging         Logging          Logging                |
|         |                |                |                |
+---------|----------------|----------------|----------------+
          |                |                |
          +--------+-------+-------+--------+
                   |               |
                   v               v
          +----------------+  +---------+
          |   Promtail     |  | System  |
          |   (Collector)  |  | Logs    |
          |                |  | auth.log|
          | - Docker logs  |  | syslog  |
          | - System auth  |  +---------+
          | - Syslog       |       |
          | - Audit logs   |<------+
          | - Security log |
          +--------+-------+
                   |
                   | push (HTTP)
                   v
          +----------------+
          |   Grafana Loki |
          |   (Storage)    |
          |                |
          | - 90-day       |
          |   retention    |
          | - Immutable    |
          |   chunks       |
          | - BoltDB index |
          +--------+-------+
                   |
                   v
          +----------------+
          |    Grafana     |
          |   (Dashboard)  |
          |                |
          | - LogQL queries|
          | - Alert rules  |
          | - Dashboards   |
          +----------------+
                   |
                   v
          +----------------+
          |   Alerting     |
          |                |
          | - Log alerts   |
          | - Email/webhook|
          | - Telegram     |
          +----------------+
```

## Infrastructure Components

> **Note:** SENTINEL shares the monitoring stack hosted at `/opt/aimthelaw`. Loki, Promtail, Grafana, and Prometheus run as Docker containers managed by `/opt/aimthelaw/docker-compose.monitoring.yml`. SENTINEL-specific scrape jobs and alert rules are added to this shared stack.

### Grafana Loki (Log Storage)

| Property | Value |
|----------|-------|
| **Image** | `grafana/loki:2.9.3` |
| **Port** | 3100 (localhost only) |
| **Storage** | Filesystem with BoltDB-Shipper indexing |
| **Retention** | 90 days (2,160 hours) - FSR compliant |
| **Compaction** | Every 10 minutes with retention enforcement |
| **Container** | `aimthelaw_loki_1` |

**Configuration file:** `/opt/aimthelaw/config/loki-config.yml`

### Promtail (Log Collector)

| Property | Value |
|----------|-------|
| **Image** | `grafana/promtail:latest` |
| **Port** | 9080 (metrics) |
| **Push target** | `http://loki:3100/loki/api/v1/push` |
| **Container** | `aimthelaw_promtail_1` |

**Configuration file:** `/opt/aimthelaw/config/promtail-config.yml`

SENTINEL-specific scrape jobs in Promtail:
- `sentinel-audit` — Tails `/opt/bms-intelligence/backend/app/data/audit_log.json` with multiline JSON parsing, extracting `action` and `result` as labels
- `journal` (shared) — Captures systemd journal including `sentinel-backend.service` logs via `unit` label

### Grafana (Visualisation and Alerting)

| Property | Value |
|----------|-------|
| **Datasource** | Loki (UID: `P8E80F9AEF21F6940`) |
| **SENTINEL alert rules** | 5 security rules (auto-provisioned) |
| **Port** | 3001 (localhost only) |
| **Container** | `aimthelaw_grafana_1` |

**Alert rules:** `/opt/aimthelaw/config/grafana/provisioning/alerting/sentinel-security-alert-rules.yml`

## Log Sources

### 1. Docker Container Logs

All SENTINEL Docker containers output structured logs via the `json-file` logging driver. Promtail collects from `/var/lib/docker/containers/`.

| Container | Label | Content |
|-----------|-------|---------|
| bms-backend | `sentinel-backend` | FastAPI application logs, API requests, errors |
| bms-frontend | `sentinel-frontend` | Nginx access/error logs |
| bms-influxdb | `sentinel-influxdb` | InfluxDB operational logs |

**Pipeline stages:**
- Docker JSON parsing
- Log level extraction (INFO, WARNING, ERROR, CRITICAL)
- Container name labelling

### 2. System Authentication Logs

**Source:** `/var/log/auth.log`
**Label:** `job=sentinel-system, component=auth`

Captures:
- SSH login attempts (successful and failed)
- `sudo` command execution
- Session open/close events
- Invalid user attempts

**Pipeline stages:**
- Syslog format parsing
- Service name extraction
- SSH event tagging (Failed password, Accepted password, Invalid user)

### 3. System Syslog

**Source:** `/var/log/syslog`
**Label:** `job=sentinel-system, component=syslog`

Captures:
- Kernel messages
- Service start/stop events
- Cron job execution
- System errors

### 4. SENTINEL Security Events

**Source:** Python `sentinel.security` logger (Docker stdout)
**Label:** `job=sentinel-security, component=backend`

Structured JSON events from the SecurityLoggingMiddleware:

| Event Type | Severity | Description |
|-----------|----------|-------------|
| `AUTH_FAILURE` | medium | Failed authentication attempt (401) |
| `ACCESS_DENIED` | high | Authorization failure (403) |
| `SERVER_ERROR` | high | Internal server error (5xx) |
| `BMS_CONTROL_ACTION` | info | Device control command executed |
| `SENSITIVE_ENDPOINT_ACCESS` | low | Access to BMS control/safety endpoints |
| `SUSPICIOUS_USER_AGENT` | medium | Automated tool or scanner detected |
| `SUSPICIOUS_PATH` | high | SQL injection, path traversal pattern |
| `REQUEST_EXCEPTION` | critical | Unhandled exception during request |

**Event format:**
```json
{
  "timestamp": "2026-02-04T10:30:00.000Z",
  "event_type": "AUTH_FAILURE",
  "severity": "medium",
  "source_ip": "41.185.xxx.xxx",
  "user_agent": "Mozilla/5.0 ...",
  "path": "/api/devices/S002-CHILLER-B1-001/control",
  "method": "POST",
  "status_code": 401,
  "duration_ms": 12.5,
  "correlation_id": "a1b2c3d4e5f6",
  "component": "sentinel-backend",
  "details": {"reason": "unauthorized"}
}
```

### 5. SENTINEL Audit Trail

**Source:** Python `sentinel.audit` logger (Docker stdout)
**Label:** `job=sentinel-audit, component=audit`

Structured JSON audit events from the enhanced AuditLogger:

| Event Type | Description |
|-----------|-------------|
| `DEVICE_CONTROL` | Device setpoint or state change |
| `SAFETY_OVERRIDE` | Safety rule override attempt |
| `BMS_COMMAND` | BMS command execution via chat |
| `SETPOINT_CHANGE` | Critical setpoint modification |
| `CONFIG_CHANGE` | System configuration change |

**Also persisted to:** `backend/app/data/audit_log.json` (file-based backup)

## Retention Policy

| Log Type | Retention | Justification |
|---------|-----------|---------------|
| All Loki logs | 90 days | FSR minimum requirement for incident investigation |
| Docker container logs | 50MB per container (5 x 10MB) | Local rotation, full history in Loki |
| System auth logs | OS default + Loki 90 days | SSH/sudo events critical for forensics |
| Audit log JSON file | 1,000 entries (rolling) | Backup/offline access, full history in Loki |

**FSR compliance note:** The 90-day retention in Loki satisfies FSR domain 4.13 requirements for log preservation. Loki's immutable chunk storage ensures tamper-evidence, as log data cannot be modified after ingestion without leaving evidence in chunk metadata.

## Tamper-Evidence Approach

1. **Immutable chunks:** Loki stores logs in immutable chunk files. Once written, chunks cannot be modified, only deleted after retention expiry.
2. **Separate storage:** Log data is stored in Loki's Docker volume (`loki-data`), separate from application data volumes.
3. **Compaction with retention:** The compactor enforces retention deletion, but with a 24-hour cancel period allowing recovery from accidental deletion.
4. **Access control:** Loki is only accessible within the Docker network (not exposed to host), reducing attack surface.
5. **Audit gap detection:** Alert Rule 6 detects gaps in the audit log stream, indicating potential log tampering or system failure.

## Alert Rules

Five SENTINEL-specific alerting rules are provisioned in Grafana via `/opt/aimthelaw/config/grafana/provisioning/alerting/sentinel-security-alert-rules.yml`:

| # | Rule | Trigger | Severity |
|---|------|---------|----------|
| 1 | Brute Force Attempt | >5 failed logins in 5 min | Critical |
| 2 | MFA Brute Force | >3 failed MFA attempts in 5 min | Critical |
| 3 | Error Spike | >10 ERROR/CRITICAL logs in 5 min | Warning |
| 4 | Suspicious Request Pattern | SQL injection or scanner tool patterns in 15 min | Warning |
| 5 | Audit Log Flow Check | Monitors audit log data pipeline to Loki (24h) | Warning |

**Notification channels:**
- Grafana built-in alerting log (default)
- Extensible to: Email, Webhook, Telegram (Clawd bot integration)

## Daily Security Log Review Procedure

The following checklist should be completed daily by the designated security officer:

### Morning Review (08:00 SAST)

- [ ] Check Grafana alert dashboard for overnight alerts
- [ ] Review failed login attempts from the last 24 hours
  - LogQL: `{job="sentinel-docker"} |= "AUTH_FAILURE" | json | line_format "{{.source_ip}} - {{.path}}"`
- [ ] Check for suspicious path patterns
  - LogQL: `{job="sentinel-docker"} |= "SUSPICIOUS_PATH" | json`
- [ ] Review SSH login events
  - LogQL: `{component="auth"} |= "Accepted password" or "Failed password"`
- [ ] Verify audit log continuity (no gaps > 30 min)
  - Check alert rule #6 status

### Weekly Review (Monday 08:00 SAST)

- [ ] Review API request volume trends by IP
- [ ] Check for new or unusual user agents
- [ ] Review device control actions for the week
  - LogQL: `{job="sentinel-docker"} |= "BMS_CONTROL_ACTION" | json`
- [ ] Verify Loki storage utilisation and retention compliance
- [ ] Export weekly security summary for FSR records

## Forensic Investigation Process

When investigating a security incident, follow this process:

### Step 1: Identify the Timeframe

```logql
# Find events around the incident time
{job="sentinel-docker"} | json
  | line_format "{{.timestamp}} {{.event_type}} {{.source_ip}} {{.path}}"
  | ts >= "2026-02-04T10:00:00Z" and ts <= "2026-02-04T12:00:00Z"
```

### Step 2: Correlate by IP Address

```logql
# All events from a specific source IP
{job=~"sentinel.*"} |= "41.185.xxx.xxx"
```

### Step 3: Correlate by Correlation ID

```logql
# All events in the same request chain
{job=~"sentinel.*"} |= "correlation_id=a1b2c3d4e5f6"
```

### Step 4: Check System-Level Events

```logql
# SSH/sudo events around the incident time
{component="auth"} | line_format "{{.message}}"
```

### Step 5: Review Device Control Actions

```logql
# All device control actions around the incident
{job="sentinel-docker"} |= "BMS_CONTROL_ACTION" | json
  | line_format "{{.timestamp}} {{.path}} {{.source_ip}} status={{.status_code}}"
```

### Step 6: Document Findings

Create an incident report including:
- Timeline of events
- Source IPs and user agents involved
- BMS actions taken (if any)
- Evidence extracted from Loki (export as CSV)
- Remediation actions taken

## Deployment

### Prerequisites

- Docker and Docker Compose installed on Contabo VPS
- Shared monitoring stack running at `/opt/aimthelaw` (Loki, Promtail, Grafana, Prometheus)
- SENTINEL data directory mounted in Promtail container

### Deployment Steps

```bash
# Start/restart the shared monitoring stack
cd /opt/aimthelaw
docker compose -f docker-compose.monitoring.yml up -d

# Verify Loki is ready
curl -s http://localhost:3100/ready

# Verify Promtail is collecting SENTINEL logs
docker logs aimthelaw_promtail_1 2>&1 | grep sentinel
```

### Verification

```bash
# Check Loki has SENTINEL audit data
curl -s 'http://localhost:3100/loki/api/v1/query_range' \
  --data-urlencode 'query={job="sentinel-audit"}' \
  --data-urlencode 'limit=5' | jq '.data.result | length'

# Check SENTINEL backend logs via systemd journal
curl -s 'http://localhost:3100/loki/api/v1/query_range' \
  --data-urlencode 'query={job="systemd-journal", unit="sentinel-backend.service"}' \
  --data-urlencode 'limit=5' | jq '.data.result | length'

# Verify Grafana alert rules are active
curl -s http://admin:admin@127.0.0.1:3001/api/v1/provisioning/alert-rules | jq '.[].title'
```

## Related Files

| File | Purpose |
|------|---------|
| `/opt/aimthelaw/docker-compose.monitoring.yml` | Shared monitoring stack (Loki, Promtail, Grafana, Prometheus) |
| `/opt/aimthelaw/config/loki-config.yml` | Loki storage, retention, and compaction config |
| `/opt/aimthelaw/config/promtail-config.yml` | Log collection and pipeline config (includes SENTINEL scrape jobs) |
| `/opt/aimthelaw/config/grafana/provisioning/alerting/sentinel-security-alert-rules.yml` | 5 SENTINEL security alert rules |
| `backend/app/middleware/security_logging.py` | Security event detection and structured logging |
| `backend/app/services/audit_logger.py` | Enhanced audit logger with JSON output |
| `backend/app/services/encryption_service.py` | Fernet encryption for audit log entries at rest |
| `backend/app/middleware/audit_middleware.py` | Existing audit middleware for control actions |

---

*Document: SENTINEL Logging Architecture*
*FSR Domain: 4.13 - Information Security Incident Detection*
*Platform: Contabo VPS (Ubuntu 24), Docker Compose, FastAPI, Cloudflare Tunnel*
*Last updated: 2026-02-19*
