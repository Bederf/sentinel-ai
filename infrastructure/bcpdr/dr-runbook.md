# SENTINEL Disaster Recovery Runbook

**Document Owner:** SENTINEL Platform Team
**Version:** 1.0
**Created:** 2026-02-04
**Classification:** CONFIDENTIAL — Contains system access details
**Review Cycle:** Annual (and after each DR event)
**Status:** Active

---

## 1. Emergency Contacts and Escalation

### Escalation Path

| Level | Role | Contact | Escalate After |
|-------|------|---------|----------------|
| **L1** | On-call operator | [Primary contact details] | Immediate |
| **L2** | Platform lead / DevOps | [Secondary contact details] | 30 minutes |
| **L3** | Management / CTO | [Management contact details] | 2 hours |
| **L4** | External support (Contabo, Supabase) | See vendor contacts below | As needed |

### Vendor Contacts

| Vendor | Service | Support Channel | SLA |
|--------|---------|-----------------|-----|
| **Contabo** | VPS hosting | support@contabo.com / Dashboard ticket | 24h response |
| **Supabase** | Database (PostgreSQL) | support@supabase.com / Dashboard | 24h response (Pro) |
| **Cloudflare** | Tunnel / DNS | support@cloudflare.com / Dashboard | Varies by plan |
| **Anthropic** | Claude API | console.anthropic.com/support | Best effort |
| **Tridonic** | DALI-2 Gateway | [Local distributor] | Business hours |

---

## 2. System Inventory

### Infrastructure Components

| Component | Details | Location |
|-----------|---------|----------|
| **Contabo VPS** | [VM ID], [Region], [Specs] | Contabo dashboard |
| **Docker Swarm** | Single-node swarm, [number] services | VPS |
| **Supabase** | Project: [project-id], Region: [region] | supabase.com dashboard |
| **Cloudflare Tunnel** | Tunnel ID: [tunnel-id] | Cloudflare Zero Trust dashboard |
| **InfluxDB** | Container: sentinel_influxdb | Docker volume |
| **Ollama** | Container: sentinel_ollama, models: phi3:mini, llama3.2:1b | Docker volume |

### Docker Services

| Service | Image | Ports | Volumes | Health Check |
|---------|-------|-------|---------|-------------|
| **backend** | sentinel-backend:latest | 9095 | app/data/ | /api/health |
| **frontend** | sentinel-frontend:latest | 9096 | — | / (HTTP 200) |
| **influxdb** | influxdb:2.7 | 8086 | influxdb-data | /health |
| **ollama** | ollama/ollama | 11434 | ollama-models | /api/version |
| **cloudflared** | cloudflare/cloudflared | — | — | Tunnel status |
| **promtail** | grafana/promtail | — | /var/log | — |
| **loki** | grafana/loki | 3100 | loki-data | /ready |
| **grafana** | grafana/grafana | 3000 | grafana-data | /api/health |
| **wazuh-agent** | wazuh/wazuh-agent | — | — | Agent status |

### External Integrations

| Integration | Protocol | Endpoint | Fallback |
|-------------|----------|----------|----------|
| **Claude API** | HTTPS | api.anthropic.com | Ollama (local) |
| **Supabase** | HTTPS | [project].supabase.co | JSON file fallback |
| **FSI Concept** | HTTPS | [fsi-api-url] | Offline queue |
| **WhatsApp** | HTTPS | WhatsApp Business API | — |
| **Telegram** | HTTPS | api.telegram.org | — |

---

## 3. Recovery Procedures

### 3.1 Contabo VM Recovery

**When to use:** Complete VM failure, unresponsive VM, corrupted OS

**Pre-requisites:**
- Contabo dashboard access credentials
- SSH key backup
- Docker Compose/Swarm configuration backup
- `.env` file backup (stored in [secure location])

**Procedure:**

```
STEP 1: Assess situation
  - Try SSH access to current VM
  - Check Contabo dashboard for VM status
  - If VM is recoverable (reboot possible), try restart first

STEP 2: If VM unrecoverable — restore from snapshot
  a) Log into Contabo control panel
  b) Navigate to Snapshots section
  c) Select latest snapshot (verify date is < 24 hours)
  d) Click "Restore" or "Create new VM from snapshot"
  e) Wait for provisioning (typically 10-30 minutes)
  f) Note new IP address if different

STEP 3: Verify base system
  a) SSH into restored/new VM
  b) Verify: hostname, disk space, memory, Docker daemon
     $ df -h
     $ free -m
     $ docker info
     $ docker service ls

STEP 4: Restore Docker services
  a) If snapshot was recent, services should auto-start with Swarm
  b) If services not running:
     $ cd /opt/bms-intelligence
     $ docker stack deploy -c docker-compose.yml sentinel
  c) Wait for all services to reach "Running" state:
     $ watch docker service ls

STEP 5: Restore environment
  a) Verify .env files are in place:
     $ ls -la /opt/bms-intelligence/backend/.env
     $ ls -la /opt/bms-intelligence/frontend/.env.development
  b) If missing, restore from secure backup:
     [Retrieve from secure backup location]

STEP 6: Restore Cloudflare Tunnel
  a) If IP changed, update Cloudflare tunnel configuration
  b) Restart cloudflared:
     $ systemctl restart cloudflared
  c) Verify tunnel status:
     $ systemctl status cloudflared
     $ curl -s https://[external-url]/api/health

STEP 7: Verify services
  a) Backend health:
     $ curl -s http://localhost:9095/api/health | jq .
  b) Frontend:
     $ curl -s -o /dev/null -w "%{http_code}" http://localhost:9096
  c) Database connectivity:
     $ curl -s http://localhost:9095/api/sites | jq length
  d) AI services:
     $ curl -s http://localhost:9095/api/chat/status | jq .

STEP 8: Post-recovery
  a) Verify data integrity (compare with pre-failure baseline if available)
  b) Check audit logs for any gaps
  c) Notify users of restoration
  d) Document recovery in incident log
  e) Schedule follow-up review
```

**RTO:** 4 hours | **RPO:** 24 hours

---

### 3.2 Database Recovery (Supabase)

**When to use:** Database corruption, accidental data deletion, schema issues

**Procedure:**

```
STEP 1: Stop application writes
  a) Enable maintenance mode or stop backend service:
     $ docker service scale sentinel_backend=0
  b) Verify no active connections

STEP 2: Assess damage
  a) Log into Supabase dashboard
  b) Check table integrity:
     - Run: SELECT count(*) FROM each critical table
     - Compare with expected counts
  c) Identify scope of corruption/loss

STEP 3: Restore from backup
  a) Supabase Pro: Use point-in-time recovery (PITR)
     - Navigate to Database > Backups
     - Select recovery point (within RPO window)
     - Initiate restoration
  b) Free tier: Restore from daily backup
     - Download latest backup
     - Apply to fresh database instance

STEP 4: Apply migrations
  a) Run any pending migrations:
     $ psql $DATABASE_URL -f supabase/migrations/*.sql
  b) Verify schema matches expected state

STEP 5: Verify data integrity
  a) Check row counts match pre-corruption baseline
  b) Verify foreign key relationships intact
  c) Run application health checks

STEP 6: Resume operations
  a) Start backend service:
     $ docker service scale sentinel_backend=1
  b) Verify API endpoints return valid data
  c) Check JSON fallback files for any data to reconcile

STEP 7: Post-recovery
  a) Document what was lost and restored
  b) Verify audit log continuity
  c) Notify affected users if data loss occurred
```

**RTO:** 2 hours | **RPO:** 1 hour (continuous backup)

---

### 3.3 Docker Service Recovery

**When to use:** Individual container crash, service unavailability

**Procedure:**

```
STEP 1: Identify failed service
  $ docker service ls
  (Look for services with 0/1 replicas or "Rejected" status)

STEP 2: Check service logs
  $ docker service logs sentinel_[service] --tail 100

STEP 3: Attempt restart
  a) Docker Swarm should auto-restart (check):
     $ docker service ps sentinel_[service] --no-trunc
  b) If not auto-restarting, force update:
     $ docker service update --force sentinel_[service]

STEP 4: If restart fails — rebuild
  a) Remove and redeploy service:
     $ docker service rm sentinel_[service]
     $ docker stack deploy -c docker-compose.yml sentinel
  b) Or rebuild image and update:
     $ docker build -t sentinel-[service]:latest .
     $ docker service update --image sentinel-[service]:latest sentinel_[service]

STEP 5: Verify recovery
  a) Check health endpoint
  b) Check dependent services reconnect
  c) Check logs for errors
```

**RTO:** 30 minutes | **RPO:** 0 (stateless)

---

### 3.4 Cloudflare Tunnel Recovery

**When to use:** External access disruption, tunnel disconnect

**Procedure:**

```
STEP 1: Verify tunnel status
  $ systemctl status cloudflared
  $ journalctl -u cloudflared --since "1 hour ago"

STEP 2: Restart cloudflared
  $ systemctl restart cloudflared
  $ sleep 10
  $ systemctl status cloudflared

STEP 3: If restart fails
  a) Check Cloudflare status page (cloudflarestatus.com)
  b) If Cloudflare outage, activate SSH fallback:
     - Set up SSH tunnel from local machine:
       $ ssh -L 9095:localhost:9095 -L 9096:localhost:9096 user@[vm-ip]
     - Notify users of temporary access method

STEP 4: If tunnel configuration lost
  a) Log into Cloudflare Zero Trust dashboard
  b) Verify tunnel configuration
  c) Re-download tunnel credentials if needed:
     $ cloudflared tunnel login
     $ cloudflared tunnel route dns [tunnel-name] [hostname]
  d) Restart cloudflared service

STEP 5: Verify external access
  $ curl -s https://[external-url]/api/health
```

**RTO:** 1 hour

---

### 3.5 SSL Certificate Recovery

**When to use:** Certificate expiry, renewal failure

**Procedure:**

```
STEP 1: Check certificate status
  $ echo | openssl s_client -connect [external-url]:443 2>/dev/null | openssl x509 -noout -dates

STEP 2: If Cloudflare-managed (most common)
  a) Cloudflare handles SSL automatically
  b) Check Cloudflare dashboard for certificate status
  c) If issue, toggle SSL mode off and back on

STEP 3: If internal certificates needed
  a) Generate new certificates via Let's Encrypt or Caddy
  b) Update Docker service configurations
  c) Restart affected services
```

---

### 3.6 Environment Variable Recovery

**When to use:** `.env` files lost or corrupted

**Procedure:**

```
STEP 1: Check if .env files exist
  $ ls -la /opt/bms-intelligence/backend/.env
  $ ls -la /opt/bms-intelligence/frontend/.env.development

STEP 2: Restore from secure backup
  [Location of .env backups: document the secure storage location]

  Required variables for backend:
  - ANTHROPIC_API_KEY
  - CLAUDE_MODEL
  - SUPABASE_URL
  - SUPABASE_KEY
  - SUPABASE_SERVICE_ROLE_KEY
  - DATABASE_URL
  - DEMO_MODE
  - CORS_ORIGINS

  Required variables for frontend:
  - VITE_API_URL

STEP 3: Verify configuration
  $ docker service update --force sentinel_backend
  $ curl -s http://localhost:9095/api/health
```

**Note:** Store `.env` backups in a secure, encrypted location (e.g., Bitwarden, 1Password, or encrypted USB). Never store in version control.

---

## 4. Backup Verification

### Monthly Backup Check

| Check | Command / Action | Expected Result | Date | Status |
|-------|-----------------|-----------------|------|--------|
| VM snapshot exists | Contabo dashboard > Snapshots | Recent snapshot (< 7 days) | | |
| VM snapshot restorable | Test restore to staging (if available) | VM boots from snapshot | | |
| Supabase backup status | Supabase dashboard > Backups | Backup active, recent point | | |
| JSON data files intact | `find /opt/bms-intelligence/backend/app/data -name "*.json" -size 0` | No empty JSON files | | |
| Docker images available | `docker images \| grep sentinel` | All images present | | |
| .env backup current | Verify secure backup matches production | Hashes match | | |
| Cloudflare tunnel config | Cloudflare dashboard > Tunnels | Tunnel configured correctly | | |

---

## 5. Communication Plan

### During DR Event

| Timeframe | Action | Audience | Channel |
|-----------|--------|----------|---------|
| **0-15 min** | Acknowledge incident, begin assessment | L1 operator | Internal chat |
| **15-30 min** | Escalate if needed, notify L2 | Platform lead | Phone + chat |
| **30-60 min** | Status update: scope, ETA | Internal team | Email + chat |
| **1-2 hours** | Update: progress, issues | Internal team + management | Email |
| **2-4 hours** | If data affected: notify FSR compliance | Compliance officer | Email + phone |
| **On recovery** | Service restored notification | All users | Email + status page |
| **24 hours** | Post-incident report | Management | Written report |
| **1 week** | Lessons learned review | Technical team | Meeting |

### Notification Templates

**Initial Notification:**
> SENTINEL Service Disruption — [Date/Time]
> Scope: [Brief description]
> Impact: [Services affected]
> ETA: [Estimated recovery time]
> Contact: [On-call operator]

**Recovery Notification:**
> SENTINEL Service Restored — [Date/Time]
> Duration: [Total outage time]
> Data Impact: [None / Brief description]
> Follow-up: Post-incident review scheduled for [date]

---

## 6. Post-Incident Process

1. **Within 24 hours:** Write initial incident report
2. **Within 1 week:** Conduct lessons learned review
3. **Within 2 weeks:** Create remediation tasks from findings
4. **Within 1 month:** Update runbook and procedures based on findings
5. **Archive:** Store incident report and test results for FSR audit

### Incident Report Template

| Field | Value |
|-------|-------|
| **Incident Date** | YYYY-MM-DD |
| **Detection Time** | HH:MM |
| **Recovery Time** | HH:MM |
| **Duration** | [hours:minutes] |
| **Root Cause** | [description] |
| **Impact** | [services affected, users affected, data loss] |
| **Recovery Actions** | [steps taken] |
| **Data Loss** | [Yes/No, describe] |
| **Notification Required** | [FSR/POPIA notifications] |
| **Lessons Learned** | [findings] |
| **Remediation Tasks** | [action items] |

---

## 7. References

- BCP Test Plan: `infrastructure/bcpdr/bcp-test-plan.md`
- BCP/DR Documentation: `docs/08-security/bcp-dr-procedures.md`
- FSR Domain 4.15: Business Continuity Management
- SENTINEL Logging Architecture: `docs/08-security/logging-architecture.md`
- Incident Response: Reference `infrastructure/bcpdr/` procedures

---

*Runbook maintained by SENTINEL Platform Team. Updated after each DR event or test.*
*Classification: CONFIDENTIAL — Contains system architecture and access details.*
