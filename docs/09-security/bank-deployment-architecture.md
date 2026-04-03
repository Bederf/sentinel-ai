---
title: "SENTINEL Bank Deployment Architecture"
type: "reference"
status: "draft"
version: "1.0.0"
created: "2026-04-03"
updated: "2026-04-03"
tags: ["sentinel", "bank", "deployment", "edge", "security"]
domain: "security"
audience: "bank-it", "bank-security", "platform-team"
complexity: "intermediate"
estimated_read_time: 15
---

# SENTINEL Bank Deployment Architecture

**Document ID:** SENTINEL-BDA-001
**Version:** 1.0
**Effective Date:** 2026-04-03
**Owner:** SENTINEL Platform Team
**Classification:** Confidential

---

## 1. Overview

This document describes the deployment architecture for SENTINEL in a bank or enterprise environment. It covers hardware requirements, network topology, data residency, notification channels, and the configuration required to satisfy enterprise security requirements.

SENTINEL is designed as a **local-first, air-gap-compatible** BMS intelligence platform. The architecture requires no inbound network connections, no external API calls for inference, and no data residency beyond the bank's own network.

---

## 2. Hardware Specification

### 2.1 Recommended: NVIDIA Jetson Orin Nano 16GB

| Component | Specification | Notes |
|-----------|--------------|-------|
| **GPU** | 1024 CUDA cores, 16 GB VRAM | Runs full local model set simultaneously |
| **CPU** | 6-core ARM Cortex-A78AE | достаточно for BMS workloads |
| **RAM** | Integrated (shares VRAM) | Models use VRAM, not system RAM |
| **Storage** | MicroSD or NVMe SSD (256 GB recommended) | For OS, models, telemetry DB |
| **Power** | 7-15W | Low enough for PoE |
| **Form Factor** | 100x87mm SODIMM module | Fits in standard electrical enclosures |

**Models that fit on Orin Nano 16GB simultaneously:**

| Model | VRAM | Speed (tok/s) | Use Case |
|-------|------|---------------|----------|
| `qwen2.5:7b-instruct` | ~5 GB | 15-25 | Chat, light tasks, fast responses |
| `deepseek-r1:14b` | ~12 GB | 10-15 | Heavy reasoning, health analysis, fault diagnosis |

### 2.2 Alternative: VM on Bank Infrastructure

If SBC deployment is not approved, SENTINEL runs on a standard VM:

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | 8 dedicated vCPU | 16 dedicated vCPU |
| **RAM** | 32 GB | 64 GB |
| **Storage** | 100 GB SSD | 200 GB SSD |
| **GPU** | None (CPU inference works) | NVIDIA GPU (any CUDA-capable) |
| **Network** | 1 Gbps, isolated VLAN | 1 Gbps, isolated VLAN |

For CPU-only VMs, `qwen2.5:7b` generates ~3-8 tok/s on 8 dedicated cores — acceptable for BMS workloads where responses are not real-time-critical.

### 2.3 Why Not Run on the VPS?

Development and production VPS deployments (api_prod profile) use Anthropic Claude API for inference due to hardware limitations of shared cloud instances. Bank deployments use the `local_full` profile which routes all inference to locally hosted Ollama — **no external LLM API calls**.

---

## 3. Deployment Topology

### 3.1 Bank Network (Primary Deployment)

```
Bank Internal Network (Isolated VLAN)
┌──────────────────────────────────────────────────────────────┐
│  Desigo / BACnet / Niagara (OT network — isolated)           │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Jetson Orin Nano 16GB (edge gateway)                   │  │
│  │                                                          │  │
│  │  ├── SIMBIOT BACnet Adapter                             │  │
│  │  │      ↕ BACnet/IP                                     │  │
│  │  ├── Desigo/Niagara Controllers                         │  │
│  │                                                          │  │
│  │  ├── Ollama (GPU inference — deepseek-r1:14b, qwen2.5)  │  │
│  │  ├── SENTINEL API + MCP Server (:9095)                  │  │
│  │  ├── InfluxDB (telemetry)                               │  │
│  │  ├── Grafana (dashboards — local only)                  │  │
│  │                                                          │  │
│  │  └── Reverse tunnel agent ──────────────────────────►    │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Reverse tunnel: outbound HTTPS only to SENTINEL VPS         │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 Network Security Properties

| Property | Value | Implication |
|----------|-------|-------------|
| **Inbound holes** | **Zero** | No ports opened on bank firewall |
| **Outbound connections** | HTTPS only | Bank firewall allows 443 outbound |
| **OT network isolation** | VLAN-separated | BMS network not accessible from corporate |
| **Remote access** | Reverse tunnel only | Initiated from Jetson, not by external party |
| **Internet access** | None required | Fully air-gap capable |

### 3.3 Remote Access (Reverse Tunnel)

SENTINEL establishes an outbound reverse SSH tunnel to a nominated VPS:

```bash
# On Jetson — reverse tunnel (one line, outbound only)
ssh -R 9096:localhost:9095 vps-user@vps-ip

# Or with frp (more robust, auto-reconnect)
frpc -c /etc/frp/frpc.ini  # connects OUTBOUND to VPS frps
```

The VPS is used only as a **relay** for remote operator access. All inference, all BMS data, all control loops remain inside the bank network.

### 3.4 VPS (Optional — Operator Access Only)

| Component | Purpose |
|-----------|---------|
| **SENTINEL API relay** | Remote operators connect via MCP/SSH through VPS |
| **SENTINEL MCP Server** | Operator tools (optional) |
| **Git repository** | Config management, deployment scripts |
| **No BMS data stored** | Telemetry stays on Jetson; VPS is a relay only |

The VPS does **not** store telemetry, work orders, or any building data. It is a network relay only.

---

## 4. SENTINEL Routing Profiles

SENTINEL uses routing profiles to determine where LLM inference occurs.

### 4.1 Available Profiles

| Profile | Mode | External API Calls | Use Case |
|---------|------|-------------------|----------|
| `api_prod` | `api` | Anthropic Claude API | Development / VPS (current) |
| `cloud_dev` | `cloud` | Z.ai Ollama cloud | Development alternative |
| `local_full` | `local` | **Zero** — Ollama only | **Bank deployment** |

### 4.2 local_full Profile

```python
# In settings.py or .env
SENTINEL_ROUTING_PROFILE=local_full
EDGE_MODE=true  # Auto-forces local_full, cannot be overridden
```

When `EDGE_MODE=true`:
- `SENTINEL_ROUTING_PROFILE` is forcibly set to `local_full`
- All LLM calls route to local Ollama on the Jetson GPU
- If Ollama is unreachable, inference raises `LocalInferenceUnavailableError` — **no fallback to cloud APIs**
- This is a **hard guarantee**, not a preference

### 4.3 Model Routing in local_full

| Task Class | Model | Provider |
|------------|-------|----------|
| `heavy` | `deepseek-r1:14b` | Ollama (GPU) |
| `chat_tech` | `deepseek-r1:14b` | Ollama (GPU) |
| `medium` | `qwen2.5:7b-instruct` | Ollama (GPU) |
| `light` | `qwen2.5:7b-instruct` | Ollama (GPU) |
| `chat_ai` | `qwen2.5:7b-instruct` | Ollama (GPU) |

---

## 5. Data Classification and Residency

### 5.1 Data Categories

| Data Type | Examples | Classification | Residency |
|-----------|----------|---------------|-----------|
| Badge swipes, access logs | Zone entry/exit, photo captures | **High** — personnel movement | Never leaves bank network |
| CCTV / camera events | Motion alerts, footage references | **High** — physical security | Never leaves bank network |
| AI chat prompts | Technician queries, building context | **Medium** — operational data | Processed locally only |
| Work order content | Descriptions, technician names | **Medium** — HR-adjacent | Email/Teams only |
| HVAC telemetry | Temperatures, pressures, setpoints | **Low** — sensor readings | Optional relay to VPS |
| Energy consumption | kWh, demand, solar generation | **Low** — operational | Optional relay to VPS |
| Audit logs | Login events, command history | **Medium** — accountability | Local only |

### 5.2 What Leaves the Bank Network

| Data | Destination | Justification |
|------|-------------|---------------|
| **Nothing (default)** | — | `LOCAL_AI_ONLY=true` — fully air-gapped |
| Anonymized telemetry (optional) | VPS relay only | Operational monitoring, no PII |
| Work order notifications | Teams / Email | Push to technicians via bank infrastructure |

**Badge data, CCTV events, access logs, and AI chat prompts never leave the bank network under any configuration.**

### 5.3 Third-Party Risk Elimination

In `local_full` mode, the following third-party services are **not used**:

| Third Party | Risk (api_prod) | local_full |
|------------|----------------|-----------|
| Anthropic Claude API | Medium (cross-border, POPIA s72) | **Not used** |
| Supabase | Medium (data processor) | **Not used** (use internal PostgreSQL) |
| Twilio / Meta | Medium (cross-border, POPIA s72) | **Not used** (use Teams/email) |
| Telegram API | Low (outbound polling) | Optional — outbound only |

---

## 6. Notification Channels

### 6.1 Microsoft Teams (Recommended)

SENTINEL posts discipline-specific notifications to Teams channels via Incoming Webhooks.

#### Channels per Discipline

| Discipline | Teams Channel | Webhook Config Key |
|------------|--------------|-------------------|
| Electrical | `BMS-Electrical` | `TEAMS_WEBHOOK_ELECTRICAL` |
| HVAC | `BMS-HVAC` | `TEAMS_WEBHOOK_HVAC` |
| Plumbing | `BMS-Plumbing` | `TEAMS_WEBHOOK_PLUMBING` |
| Fire / Safety | `BMS-Fire-Safety` | `TEAMS_WEBHOOK_FIRE` |
| General | `BMS-Alerts` | `TEAMS_WEBHOOK_DEFAULT` |

Each discipline routes to the correct channel automatically based on the work order or alert classification.

#### Setup (No Code Changes)

1. Teams Admin creates a channel per discipline
2. Each channel: **Add Connector → Incoming Webhook → Configure → Copy URL**
3. Add URLs to SENTINEL environment:

```bash
TEAMS_WEBHOOK_ELECTRICAL=https://outlook.office.com/webhook/...
TEAMS_WEBHOOK_HVAC=https://outlook.office.com/webhook/...
TEAMS_WEBHOOK_PLUMBING=https://outlook.office.com/webhook/...
TEAMS_WEBHOOK_FIRE=https://outlook.office.com/webhook/...
```

4. SENTINEL posts discipline-tagged messages to the appropriate channel

**Security properties:**
- Outbound HTTPS POST only from Jetson to M365
- No inbound connections
- No Azure AD app registration required
- Uses bank's existing M365 tenant

#### Two-Way Messaging (Future Enhancement)

Technicians can reply to work orders via **email** (existing SENTINEL email intake pipeline) or via a **Power Automate workflow** bridging Teams messages to SENTINEL's webhook API.

Full Teams Bot Framework (conversational interface in Teams) requires Azure AD app registration and is not implemented in the current release.

### 6.2 Email (Fallback / Reply Channel)

SENTINEL sends and receives email via the bank's SMTP/IMAP infrastructure.

#### Outbound Email (SENTINEL → Technicians)

```bash
NOTIFICATION_SMTP_HOST=mail.bankinternal.co.za
NOTIFICATION_SMTP_PORT=587
NOTIFICATION_SMTP_USERNAME=sentinel@bankinternal.co.za
NOTIFICATION_SMTP_PASSWORD=*******
NOTIFICATION_SMTP_USE_TLS=true
NOTIFICATION_SMTP_FROM_NAME="SENTINEL BMS Alerts"
```

#### Inbound Email (Replies)

Technicians reply to work order notification emails. SENTINEL processes replies via the email intake pipeline — no separate inbound channel needed.

#### Email-to-SMS (For Technicians Without Smartphones)

If the bank has an email-to-SMS gateway:

```bash
# Forward SMS to: +27821234567@sms.bankgateway.com
SENTINEL sends email → SMS gateway → technician phone (SMS)
```

Requires the bank's IT team to provide the SMS gateway address.

### 6.3 SMS (Optional — Via Twilio or Bank Gateway)

If SMS is required and no bank gateway is available:

```bash
TWILIO_WHATSAPP_FROM=+14155238886
TWILIO_AUTH_TOKEN=*******
```

SENTINEL sends SMS via Twilio API (outbound HTTPS only, ~$1/month). Requires bank firewall to allow outbound HTTPS to `api.twilio.com`.

### 6.4 Telegram (Optional — If Already in Use)

If the maintenance team uses Telegram:

- Configure `TELEGRAM_BOT_TOKEN` in SENTINEL
- SENTINEL uses **long-polling** (`getUpdates`) — outbound HTTPS only to `api.telegram.org`
- **No webhook** — avoids inbound connection requirement
- Requires bank firewall to allow outbound HTTPS to `api.telegram.org`

---

## 7. Firewall Requirements

### 7.1 Jetson (Edge Gateway)

| Direction | Destination | Port | Purpose |
|-----------|------------|------|---------|
| **Outbound** | M365 / Teams webhooks | 443 | Teams notifications |
| **Outbound** | Bank SMTP server | 587 | Email delivery |
| **Outbound** | `api.telegram.org` | 443 | Telegram (optional) |
| **Outbound** | `api.twilio.com` | 443 | SMS (optional) |
| **Outbound** | SENTINEL VPS (reverse tunnel) | 443 | Remote operator access |
| **Inbound** | **None** | — | No inbound connections |

### 7.2 VPS (Operator Access Relay — Optional)

The VPS only forwards operator traffic to the Jetson tunnel. It does not initiate connections to the Jetson.

| Direction | Source | Port | Purpose |
|-----------|--------|------|---------|
| **Inbound** | Operators (MCP/SSH) | 2222 | Remote access |
| **Outbound** | Bank Jetson (via tunnel) | 9096 | Telemetry relay |

---

## 8. Configuration Reference

### 8.1 Bank Deployment Environment Variables

```bash
# ============================================
# SENTINEL — Bank Deployment Configuration
# ============================================

# --- Operation Mode ---
SENTINEL_ROUTING_PROFILE=local_full
EDGE_MODE=true

# --- Network ---
# Reverse tunnel to operator VPS (outbound from Jetson)
# FRP or SSH reverse tunnel configured separately

# --- Notification Channels ---
# Teams discipline webhooks (outbound HTTPS)
TEAMS_WEBHOOK_ELECTRICAL=https://outlook.office.com/webhook/...
TEAMS_WEBHOOK_HVAC=https://outlook.office.com/webhook/...
TEAMS_WEBHOOK_PLUMBING=https://outlook.office.com/webhook/...
TEAMS_WEBHOOK_FIRE=https://outlook.office.com/webhook/...

# Email (SMTP — bank internal)
NOTIFICATION_SMTP_HOST=mail.bankinternal.co.za
NOTIFICATION_SMTP_PORT=587
NOTIFICATION_SMTP_USERNAME=sentinel@bankinternal.co.za
NOTIFICATION_SMTP_PASSWORD=********
NOTIFICATION_SMTP_USE_TLS=true
NOTIFICATION_SMTP_FROM_NAME="SENTINEL BMS Alerts"

# --- Local Database (InfluxDB) ---
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=******
INFLUX_ORG=sentinel
INFLUX_BUCKET=bms_telemetry

# --- Authentication ---
JWT_SECRET_KEY=******(bank-managed, 256-bit hex)
DEMO_MODE=false

# --- External APIs (DISABLED) ---
# These are NOT used in local_full mode
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
```

### 8.2 What NOT to Configure for Bank Deployment

| Variable | Reason |
|---------|--------|
| `ANTHROPIC_API_KEY` | Not used — local Ollama only |
| `OPENAI_API_KEY` | Not used |
| `SUPABASE_URL` | Not used — local InfluxDB + PostgreSQL |
| `SUPABASE_SERVICE_KEY` | Not used |
| `TWILIO_WHATSAPP_FROM` | Not used unless SMS required |
| `TELEGRAM_BOT_TOKEN` | Only if Telegram is the chosen notification channel |
| `WHATSAPP_WEBHOOK_URL` | Not used — Teams is the push channel |

---

## 9. Bank IT Requirements Summary

| Item | Ask | Classification |
|------|-----|---------------|
| **Hardware** | Jetson Orin Nano 16GB (or VM with 32 GB RAM) | IT procurement |
| **Network** | Isolated VLAN for BMS + Jetson | Network team |
| **Firewall outbound** | Allow HTTPS to M365 (Teams webhooks) | Security team |
| **Firewall outbound** | Allow HTTPS to bank SMTP (port 587) | Security team |
| **Firewall outbound** | Allow HTTPS to VPS relay (tunnel, port 443) | Security team |
| **Teams channels** | Create 4-5 BMS channels + Incoming Webhooks | Teams Admin |
| **SMTP relay** | Configure bank mail server for SENTINEL relay | Email admin |
| **VPN/Remote access** | Optional — reverse tunnel via VPS | Network team |

**No inbound firewall changes. No Azure AD app registration. No new infrastructure.**

---

## 10. Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-03 | SENTINEL Platform Team | Initial bank deployment architecture |

---

*Document: SENTINEL-BDA-001*
*Classification: Confidential*
