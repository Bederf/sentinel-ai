# Logging & Observability Troubleshooting

> Troubleshooting the Promtail → Loki → Grafana pipeline for SENTINEL log collection.

## Quick Health Check

```bash
# 1. Are all containers running?
cd /opt/aimthelaw && docker compose -f docker-compose.monitoring.yml ps

# 2. Is Loki accepting writes?
curl -s http://localhost:3100/ready  # expect "ready"

# 3. Does Loki have SENTINEL data?
curl -s http://localhost:3100/loki/api/v1/label/job/values | python3 -m json.tool
# expect: sentinel-audit, sentinel-security, sentinel-decisions

# 4. Are Promtail targets healthy?
curl -s http://localhost:9080/targets | grep -c "READY"
```

## Common Issues

### No data in Grafana dashboards

**Symptoms:** Dashboard panels show "No data" or empty charts.

**Check 1: Log files exist and have content**
```bash
ls -la /var/log/sentinel/
# expect: decisions.log, security.log (non-zero size)

# If files are missing, check the fallback directory
ls -la /opt/bms-intelligence/backend/app/data/logs/
```

**Check 2: Promtail is tailing the files**
```bash
# Check Promtail targets for SENTINEL jobs
curl -s http://localhost:9080/targets | grep sentinel
# expect: 3 targets (sentinel-audit, sentinel-security, sentinel-decisions)
```

**Check 3: Loki is ingesting**
```bash
# Query recent entries
curl -s "http://localhost:3100/loki/api/v1/query?query={job=%22sentinel-decisions%22}&limit=5"
```

**Check 4: Grafana datasource UID**
```bash
# The dashboards expect Loki datasource UID: P8E80F9AEF21F6940
curl -s http://localhost:3000/api/datasources | python3 -m json.tool | grep -A2 '"type": "loki"'
```

### decisions.log is empty or missing

The backend writes to `/var/log/sentinel/decisions.log` via `RotatingFileHandler`. If the file is missing:

1. **Check directory permissions:**
   ```bash
   ls -la /var/log/sentinel/
   # Must be writable by the backend process user
   ```

2. **Check fallback location:** If `/var/log/sentinel/` is not writable, the backend falls back to `backend/app/data/logs/decisions.log` (see `backend/app/logging_config.py`).

3. **Verify the logger is active:**
   ```bash
   # Check if decision events are being generated
   grep -c "stage" /var/log/sentinel/decisions.log
   ```

### security.log is empty

Security events are only written when the security middleware detects suspicious activity (failed logins, scanner patterns, path traversal). In dev/demo mode with no external traffic, this file may legitimately be empty.

To generate test events:
```bash
# Trigger a failed auth event
curl -s http://localhost:9095/api/health -H "User-Agent: sqlmap/1.0"
```

### Promtail not shipping logs

**Check Promtail config:**
```bash
docker exec promtail cat /etc/promtail/config.yml | grep sentinel
# expect: sentinel-audit, sentinel-security, sentinel-decisions jobs
```

**Check Promtail can access log files:**
```bash
# Promtail mounts /var/log:/var/log:ro
docker exec promtail ls -la /var/log/sentinel/
```

**Check Promtail logs for errors:**
```bash
docker logs promtail --tail 20
```

### Loki query returns empty results

```bash
# Verify labels exist
curl -s http://localhost:3100/loki/api/v1/labels

# Check specific job has streams
curl -s "http://localhost:3100/loki/api/v1/series" \
  --data-urlencode 'match[]={job="sentinel-decisions"}' | python3 -m json.tool
```

### Grafana dashboard not appearing

Dashboards are auto-provisioned from `/opt/aimthelaw/config/grafana/provisioning/dashboards/`. The provisioning cycle is ~30 seconds.

```bash
# Check provisioning config exists
ls /opt/aimthelaw/config/grafana/provisioning/dashboards/*.json

# Force reload
docker restart grafana

# Check Grafana logs for provisioning errors
docker logs grafana --tail 20 | grep -i "dashboard\|provision"
```

### Alert rules not firing

```bash
# Check alert rule provisioning
curl -s http://localhost:3000/api/v1/provisioning/alert-rules | python3 -m json.tool | grep title
# expect: 5 SENTINEL rules

# Check rule evaluation
curl -s http://localhost:3000/api/v1/provisioning/alert-rules | python3 -m json.tool | grep state
```

## Log File Locations

| File | Path | Format | Rotation |
|------|------|--------|----------|
| Decision events | `/var/log/sentinel/decisions.log` | JSON-lines | 10MB x 5 |
| Security events | `/var/log/sentinel/security.log` | JSON-lines | 10MB x 5 |
| Audit log | `backend/app/data/audit_log.json` | JSON array | 1,000 entries |
| Fallback decisions | `backend/app/data/logs/decisions.log` | JSON-lines | 10MB x 5 |
| Fallback security | `backend/app/data/logs/security.log` | JSON-lines | 10MB x 5 |

## Related Docs

- [Logging Architecture](../08-security/logging-architecture.md) — Full pipeline design
- [Audit Logging](../06-safety-compliance/audit-logging.md) — Audit event format and compliance
- [Monitoring Stack Operations](../09-operations/monitoring-stack.md) — Deployment and config management
