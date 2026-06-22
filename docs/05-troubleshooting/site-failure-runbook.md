# Site Failure Runbook

**Purpose:** 2am decision tree. One page per failure mode.

---

## 1. Backend Down

### Detect
```bash
curl -fsS http://127.0.0.1:9095/api/health | jq .status
# Expected: "ok"
```

### Triage
```bash
# Step 1 — is the process alive?
systemctl status sentinel-backend

# Step 2 — last logs
journalctl -u sentinel-backend --since "15 minutes ago" --no-pager | tail -40

# Step 3 — is the port listening?
ss -tlnp | grep 9095
```

### Restart
```bash
sudo systemctl restart sentinel-backend
# Startup takes ~90s (AI model loading, scheduler init)
# Health: curl -fsS http://127.0.0.1:9095/api/health  (use 127.0.0.1, not localhost — IPv6 delay)
```

### Escalate
If restart doesn't help within 3 minutes:
- Check `/var/log/syslog` for OOM kills: `dmesg | grep -i oom`
- Check disk: `df -h /` (if full, journald stops writing)
- Check `/etc/sentinel/secrets.env` integrity (bad env file = startup failure)

---

## 2. Supabase Down

### Detect
```bash
# DB directly
docker exec supabase_db_bms-intelligence psql -U postgres -c "SELECT 1;"

# PostgREST (via Kong)
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:55321/rest/v1/

# Container status
docker ps --filter name=supabase_db_bms-intelligence --format "{{.Status}}"
```

### Restart
```bash
docker restart supabase_db_bms-intelligence
# Wait 10s, retry health check
```

### Failover
If DB container won't start:
1. Check disk space: `df -h`
2. Check container logs: `docker logs supabase_db_bms-intelligence --tail 30`
3. Restore from latest backup (see Section 4)

---

## 3. SIMBIOT Bridge Down

### Detect
```bash
# Status endpoint
curl -s -H "X-Sentry-API-Key: $(sudo cat /etc/sentinel/secrets.env | grep SENTRY_BOT_API_KEY | cut -d= -f2)" \
  http://127.0.0.1:9095/api/v1/bridge/status | jq .

# Prometheus alert
# SentinelAlertBridgeDown fires when sentry_bridge_up == 0 for >2m
```

### Effect
- No live sensor data (HVAC, lighting, energy)
- Scheduler jobs will report stale data freshness
- AI recommendations still work on cached data
- Site still operational — blind, not dead

### Restore
Bridge connects to replica VPS at `10.99.0.1` via WireGuard.
```bash
ping -c 3 10.99.0.1          # Is WireGuard up?
wg show                       # Is handshake recent?
curl -s http://10.99.0.1:8080/health
```

Operational access to the bridge is through the WireGuard bridge API. Do not assume SSH key access from the Sentinel host.

---

## 4. Data Loss / Corruption

### Detect
```bash
# Row count check
docker exec supabase_db_bms-intelligence psql -U postgres -t -c "
SELECT 'recommendations', count(*) FROM recommendations
UNION ALL SELECT 'work_orders', count(*) FROM work_orders
UNION ALL SELECT 'audit_log', count(*) FROM public.audit_log;"
```

### Restore
```bash
# 1. List available backups
ls -lt /opt/bms-intelligence/backups/postgres/{daily,manual}/

# 2. Restore to standby (port 55432)
RESTORE_DOCKER_CONTAINER=sentinel-postgres-backup-db \
/opt/bms-intelligence/scripts/restore/restore_postgres_backup.sh latest

# 3. Verify restored counts match expected
docker exec sentinel-postgres-backup-db psql -U postgres -d sentinel_backup -t -c "
SELECT 'recommendations', count(*) FROM recommendations
UNION ALL SELECT 'work_orders', count(*) FROM work_orders;"

# 4. Promote standby to primary (point backend env to port 55432 if needed)
# Not automated — requires config change + restart
```

### Offsite Recovery
Encrypted backups on replica VPS (`10.99.0.1`):
```bash
# Use the documented backup transport for the active deployment.
# Do not assume SSH key access from the Sentinel host.
```

---

## 5. Prometheus / Alerting Down

### Detect
```bash
curl -s http://127.0.0.1:9090/-/healthy
```

### Effect
- No alert delivery to Telegram
- No historical metrics
- Scheduler observability still works (metrics emitted to DB)
- System stays fully operational — only visibility lost

### Restart
```bash
docker restart sentinel-prometheus
docker restart sentinel-alertmanager
```

### Bridge cut
If alerts not reaching Telegram:
```bash
docker logs sentry-bridge --tail 20
curl -fsS http://127.0.0.1:9099/health
```

---

## Quick Reference

| Service | Port | Health Check |
|---------|------|-------------|
| Backend API | 9095 | `/api/health` |
| Supabase DB | 55322 | `docker exec ... psql -c "SELECT 1"` |
| Supabase API (Kong) | 55321 | `curl :55321/rest/v1/` |
| PostgREST | via Kong | `curl :55321/rest/v1/health` |
| Standby DB | 55432 | `docker exec ... psql -c "SELECT 1"` |
| Prometheus | 9090 | `/-/healthy` |
| Alertmanager | 9093 | `/alertmanager/-/healthy` |
| WireGuard | — | `ping 10.99.0.1` |
| Bridge API | 8080 over WireGuard | `curl http://10.99.0.1:8080/health` |

## Contacts

| Role | Contact |
|------|---------|
| Operations | Pieter — Telegram |
| Bridge / remote endpoint | WireGuard bridge API; use deployment-specific operator access if host changes are required |
| Alert Delivery | Telegram @bederf_bot |
