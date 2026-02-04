# SENTINEL Logging Architecture

**Version:** 1.0
**Date:** 2026-02-04
**FSR Reference:** Domain 4.13 - Information Security Incident Detection
**Current Maturity:** 3.0 (target: 4.0 HIGH)

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

### Grafana Loki (Log Storage)

| Property | Value |
|----------|-------|
| **Image** | `grafana/loki:2.9.3` |
| **Port** | 3100 (internal only, not exposed to host) |
| **Storage** | Filesystem with BoltDB-Shipper indexing |
| **Retention** | 90 days (2,160 hours) - FSR compliant |
| **Compaction** | Every 10 minutes with retention enforcement |
| **Index** | Daily rotation with `sentinel_loki_index_` prefix |

**Configuration file:** `infrastructure/loki/loki-config.yaml`

### Promtail (Log Collector)

| Property | Value |
|----------|-------|
| **Image** | `grafana/promtail:2.9.3` |
| **Port** | 9080 (metrics) |
| **Push target** | `http://loki:3100/loki/api/v1/push` |

**Configuration file:** `infrastructure/promtail/promtail-config.yaml`

### Grafana (Visualisation and Alerting)

| Property | Value |
|----------|-------|
| **Datasource** | Loki (auto-provisioned) |
| **Alert rules** | 6 security rules (auto-provisioned) |

**Datasource config:** `infrastructure/grafana/provisioning/datasources/loki.yaml`
**Alert rules:** `infrastructure/grafana/provisioning/alerting/security-alerts.yaml`

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

Six SIEM-equivalent alerting rules are provisioned in Grafana:

| # | Rule | Trigger | Severity |
|---|------|---------|----------|
| 1 | Failed Login Attempts | >5 auth failures from same IP in 5 min | High |
| 2 | Suspicious Path Patterns | Any SQL injection or path traversal | High |
| 3 | Unusual API Activity | >100 requests from single IP in 1 min | Medium |
| 4 | After-Hours Access | Sensitive endpoint access outside 06:00-22:00 SAST | Medium |
| 5 | Error Spike | >10 HTTP 5xx responses in 5 min | High |
| 6 | Audit Log Gap | No audit entries for >30 min during business hours | Critical |

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
- Ports 3100 (Loki) and 9080 (Promtail) available internally
- Cloudflare Tunnel configured for Grafana access (optional)

### Deployment Steps

```bash
# Start the full stack including Loki and Promtail
cd /opt/bms-intelligence
docker compose up -d loki promtail

# Verify Loki is ready
curl -s http://localhost:3100/ready

# Verify Promtail is collecting
curl -s http://localhost:9080/targets
```

### Verification

```bash
# Check Loki label values (should show sentinel-docker, sentinel-system, etc.)
curl -s http://localhost:3100/loki/api/v1/labels | jq

# Query recent logs
curl -s 'http://localhost:3100/loki/api/v1/query_range' \
  --data-urlencode 'query={job="sentinel-docker"}' \
  --data-urlencode 'limit=5' | jq '.data.result[0].values[:3]'
```

## Related Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Loki and Promtail service definitions |
| `infrastructure/loki/loki-config.yaml` | Loki storage, retention, and compaction config |
| `infrastructure/promtail/promtail-config.yaml` | Log collection and pipeline config |
| `infrastructure/grafana/provisioning/datasources/loki.yaml` | Grafana Loki datasource |
| `infrastructure/grafana/provisioning/alerting/security-alerts.yaml` | 6 SIEM alerting rules |
| `backend/app/middleware/security_logging.py` | Security event detection and structured logging |
| `backend/app/services/audit_logger.py` | Enhanced audit logger with JSON output |
| `backend/app/middleware/audit_middleware.py` | Existing audit middleware for control actions |

---

*Document: SENTINEL Logging Architecture*
*FSR Domain: 4.13 - Information Security Incident Detection*
*Platform: Contabo VPS (Ubuntu 24), Docker Compose, FastAPI, Cloudflare Tunnel*
*Last updated: 2026-02-04*
