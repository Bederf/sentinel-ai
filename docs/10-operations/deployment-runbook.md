---
title: SENTINEL Deployment Runbook
category: operations
date: 2026-03-14
tags: [deployment, setup, onboarding, handoff]
---

# SENTINEL Deployment Runbook

Step-by-step guide for deploying SENTINEL to a new site. A new site team should be able to follow this document from a fresh server to an operational system without developer assistance.

This runbook supports two deployment patterns:
- local site hosting: Sentinel and the site adapter run on the same host/network
- remote site connection: Sentinel runs separately and reaches the building data source through SIMBIOT over WireGuard/VPN, edge connection, BACnet, or another supported adapter path

Across both patterns, the contract is the same:
- SIMBIOT exposes building-operational data to SENTINEL
- SENTINEL consumes the building view, not remote lifecycle internals

**Estimated time:** 45-60 minutes (excluding Supabase provisioning)

---

## Prerequisites

### Hardware

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 4 cores | 8 cores |
| RAM | 8 GB | 16 GB |
| Disk | 40 GB SSD | 100 GB SSD |
| Network | 10 Mbps | 100 Mbps |
| OS | Debian 12 / Ubuntu 22.04 | Debian 12 |

### Software

- Python 3.11+
- Node.js 20+ and npm
- PostgreSQL client (`psycopg2` dependencies)
- Redis 7+
- Git
- systemd (for service management)

### Accounts & Credentials

- Anthropic API key (or OpenAI key as fallback)
- Supabase project (local or cloud)
- SMTP credentials for email notifications
- Sentry bot tokens (manager, technician, staff) if Telegram bot access is enabled

---

## Step 1: Clone & Install (10 min)

```bash
# Clone repository
cd /opt
git clone https://github.com/your-org/bms-intelligence.git
cd bms-intelligence

# Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

## Step 2: Supabase Setup (10 min)

### Option A: Local Supabase (recommended for on-premise)

```bash
# Install Supabase CLI
npx supabase init  # if not already done
npx supabase start

# Note the output — you need:
# API URL (default: http://localhost:54321)
# anon key
# service_role key
```

### Option B: Existing Supabase instance

Use your project's URL and keys from the Supabase dashboard.

### Run Migrations

```bash
cd /opt/bms-intelligence

# Apply all migrations in order
for f in supabase/migrations/*.sql; do
  echo "Applying $f..."
  PGPASSWORD=postgres psql -h localhost -p 55322 -U postgres -d postgres -f "$f"
done

# Apply backend-specific migrations
for f in backend/supabase/migrations/*.sql; do
  echo "Applying $f..."
  PGPASSWORD=postgres psql -h localhost -p 55322 -U postgres -d postgres -f "$f"
done
```

## Step 3: Configure Environment (5 min)

```bash
cd /opt/bms-intelligence/backend

# Copy template
cp .env.example .env

# Edit with your values — minimum required:
nano .env
```

**Minimum viable `.env`:**

```bash
# Required
ENVIRONMENT=production
JWT_SECRET_KEY=<generate: python3 -c "import secrets; print(secrets.token_urlsafe(64))">
SUPABASE_URL=http://localhost:55321
SUPABASE_KEY=<your-anon-key>
SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>
ANTHROPIC_API_KEY=<your-claude-key>

# Recommended
DEMO_MODE=false
ADMIN_EMAILS=admin@yourcompany.co.za
NOTIFICATION_SMTP_HOST=smtp.gmail.com
NOTIFICATION_SMTP_PORT=587
NOTIFICATION_SMTP_USERNAME=alerts@yourcompany.co.za
NOTIFICATION_SMTP_PASSWORD=<app-password>

# Remote-VM / WireGuard topology
ENABLE_SITE002_SOURCE=false
SENTINEL_ISLAND_MODE=true
BRIDGE_BASE_URL=http://10.99.0.1:8080
BRIDGE_API_TOKEN=<legacy-shared-bridge-token>
BRIDGE_API_TOKEN_SITE_002=<site-002-bridge-token>
BRIDGE_API_TOKEN_SITE_005=<site-005-bridge-token>
```

### Remote VM + WireGuard Checklist

If the site adapter or building endpoint lives on another host/network:

1. Bring up the WireGuard tunnel before `sentinel-backend`.
2. Confirm the remote VM tunnel IP is reachable from the Sentinel host.
3. Confirm the bridge health endpoint responds on the WireGuard IP/port.
4. Keep `ENABLE_SITE002_SOURCE=false` so this host does not start the local `site-002` simulator.
5. Keep `SENTINEL_ISLAND_MODE=true` so device bootstrap and simulation queue stay disabled locally.
6. Ensure the remote site endpoint does not write directly to Supabase; Sentinel remains the single writer.

**Frontend:**

```bash
cd /opt/bms-intelligence/frontend
echo "VITE_API_URL=http://localhost:9095" > .env.production
```

## Step 4: Build Frontend (3 min)

```bash
cd /opt/bms-intelligence/frontend
npm run build
```

## Step 5: Start Services (2 min)

### Option A: systemd (production)

```bash
# Copy service files
sudo cp infra/systemd/sentinel-backend.service /etc/systemd/system/
sudo cp infra/systemd/sentinel-frontend.service /etc/systemd/system/

# Reload and start
sudo systemctl daemon-reload
sudo systemctl enable sentinel-backend sentinel-frontend
sudo systemctl start sentinel-backend sentinel-frontend

# Verify
sudo systemctl status sentinel-backend
sudo systemctl status sentinel-frontend
```

### Option B: Manual (development)

```bash
# Terminal 1: Backend
cd /opt/bms-intelligence/backend
source venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 9095

# Terminal 2: Frontend
cd /opt/bms-intelligence/frontend
npm run dev  # or: npx serve dist -l 9096
```

## Step 6: Verify Health (2 min)

```bash
# Backend health
curl http://localhost:9095/api/health
# Expected: {"status":"healthy","version":"..."}

# System health (extended)
curl http://localhost:9095/api/system/health
# Expected: overall_status: "healthy" or "degraded"

# Frontend
curl -I http://localhost:9096
# Expected: HTTP 200
```

Open browser: `http://localhost:9096`

### Additional verification for remote site connections

```bash
# WireGuard peer state
sudo wg show

# Route to the remote site subnet
ip route | grep 10.99.0.0

# Site endpoint health over the chosen path. Use that site's token.
curl -H "Authorization: Bearer <BRIDGE_API_TOKEN_SITE_005>" http://10.99.0.1:8080/api/sites/site-005/health

# Sentinel should log SIMBIOT remote ingestion mode, not local simulation fallback
journalctl -u sentinel-backend -n 100 | grep -E "SIMBIOT|remote site bridge|data source"
```

## Step 7: First Login & Admin Setup (5 min)

1. Navigate to `http://localhost:9096` (or your domain)
2. Login with the email configured in `ADMIN_EMAILS`
3. Go to **Settings** page
4. Verify:
   - System Health Dashboard shows green/amber (not all red)
   - Building Profile shows correct building details

## Step 8: SIMBIOT Wizard — Connect Your BMS (10 min)

If you have a Niagara/BACnet BMS:

1. Navigate to the **SIMBIOT** tab in the building view
2. Follow the 4-step wizard:
   - **Step 1:** Enter Niagara oBIX connection details
   - **Step 2:** Discover BACnet points → wizard receives `discovery_id`
   - **Step 3:** AI auto-classifies discovered points
   - **Step 4:** Review and approve mappings (must complete within 10 minutes of discovery)
3. The commit is **atomic** — all equipment, mappings, and modules are created in one transaction
4. Equipment will appear in the dashboard automatically

**Important:** Discovery sessions expire after 10 minutes. If the user takes longer than 10 minutes to review, they must click **Rescan & Reload Review** to get a fresh `discovery_id` before approving.

If no BMS yet, use `DEMO_MODE=true` to explore with sample data.

## Step 9: Register Technicians (5 min)

1. Go to **Settings** → **Team & Technicians**
2. Click **Add Technician**
3. For each technician, enter:
   - Name, email, phone
   - Disciplines (HVAC, Electrical, Plumbing, etc.)
   - Technician Telegram ID/channel binding if Sentry Tech bot notifications are enabled
4. Technicians will automatically receive alerts matching their disciplines

## Step 10: Sentry Staff Bot Onboarding (5 min)

For site-002, do not manually collect Telegram IDs for every staff member. Import or sync the staff roster first, then send a registration link or QR code. The roster should include `staff_number`, `name`, `email`, `phone`, `desk`, `site_id`, and `active`. Staff open the Staff bot link, enter their staff number, confirm the last 4 digits of their phone number, and Sentry binds the channel ID to that staff identity.

Current Telegram link: `https://t.me/sentinelstaffbot?start=staff`. WhatsApp or custom app channels should use the same staff-number verification pattern with their own channel binding. Keep first-contact registration disabled unless the roster/HR lookup is active.

## Step 11: Configure Alert Routing (5 min)

1. Go to **Settings** → **Alert Routing Rules**
2. Default rules are pre-populated (critical → Telegram+WhatsApp, warning → Telegram)
3. Adjust channels and escalation times as needed
4. Test via **Notification Channels** → **Send Test** button

## Step 12: RAG Knowledge Base (automatic)

RAG auto-loads on first startup if the vector store is empty:
- Equipment fault codes and maintenance procedures (26 entries)
- System documentation from `docs/` (100+ files)

To manually trigger or re-ingest:

```bash
cd /opt/bms-intelligence/backend
source venv/bin/activate

# Equipment knowledge
python scripts/ingest_rag_knowledge.py

# System docs (use --force to re-ingest all)
python scripts/ingest_system_docs.py
```

## Step 12: Backup Verification (2 min)

1. Go to **Settings** → **System Health** → **Database Backup**
2. Click **Backup Now**
3. Verify status shows "success" with file count

For automated daily backup, add to crontab:

```bash
0 2 * * * cd /opt/bms-intelligence/backend && python3 scripts/backup_supabase_to_json.py >> /var/log/sentinel-backup.log 2>&1
```

---

## Post-Deployment Checklist

- [ ] Backend health returns 200
- [ ] Frontend loads without errors
- [ ] Admin user can log in
- [ ] System Health shows Supabase connected
- [ ] Building profile shows correct site details
- [ ] At least 1 technician registered
- [ ] Alert routing rules configured
- [ ] Notification channel test succeeds
- [ ] First backup completed successfully
- [ ] RAG knowledge base populated (check via chat: "what fault codes exist for chillers?")

---

## Troubleshooting

| Issue | Check | Fix |
|-------|-------|-----|
| Backend won't start | `journalctl -u sentinel-backend -n 50` | Check .env for missing required vars |
| "Invalid JWT" errors | JWT_SECRET_KEY set? | Generate a fresh key |
| Supabase connection fails | `curl $SUPABASE_URL/rest/v1/` | Check URL/keys, verify Supabase is running |
| Frontend shows blank page | Browser console (F12) | Check VITE_API_URL matches backend |
| CORS errors | Browser console | Add frontend URL to CORS_ORIGINS in .env |
| No alerts routing | Settings → Channel Status | Verify SMTP/Telegram credentials in .env |
| Chat returns errors | Check ANTHROPIC_API_KEY | Verify API key is valid and has credits |
| "Embedding model" slow first query | Normal (11s first load) | Pre-warmed automatically on startup |

---

## Architecture Quick Reference

```
Frontend (React/Vite)     → localhost:9096
Backend (FastAPI/Uvicorn)  → localhost:9095
Supabase (PostgreSQL)      → localhost:55321 (API), 55322 (DB)
Redis                      → localhost:6379
Ollama (optional)          → localhost:11434
```

**Data flow:**
```
BMS (Niagara/BACnet/Modbus)
    → SIMBIOT device abstraction
    → Equipment telemetry
    → ML models (anomaly/fault/health)
    → Alerts + Work Orders
    → Technician notifications (Telegram/WhatsApp/Email)
```

**Config files:**
- Backend env: `/opt/bms-intelligence/backend/.env`
- Frontend env: `/opt/bms-intelligence/frontend/.env.production`
- Building data: `/opt/bms-intelligence/backend/app/data/buildings/{site-id}/building.json`
- Technicians: Supabase `technicians` table (JSON fallback at `backend/app/data/technicians_whatsapp.json`)

---

## Related Docs

- [System Health & Diagnostics](system-health-diagnostics.md)
- [SIMBIOT Wizard](../04-features/niagara-connection-wizard.md)
- [Module System](../02-architecture/module-system.md)
- [Security Suite](../09-security/README.md)
- [AI Cost Tracking](../04-features/ai-cost-tracking.md)
- [Quick Start](../01-getting-started/quick-start.md)
