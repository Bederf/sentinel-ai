---
title: "BMS Connection Wizard (Multi-Vendor)"
type: "spec"
status: "approved"
version: "2.0.0"
created: "2026-02-04"
updated: "2026-02-04"
author: "Sentinel Development Team"
tags: ["bms", "onboarding", "wizard", "bacnet", "obix", "frontend", "integration", "multi-vendor"]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 12
---

# BMS Connection Wizard (Multi-Vendor)

A 4-step frontend wizard on the Integration Monitoring page that connects to any BMS vendor exposing BACnet/IP, discovers points, classifies them with AI, and activates equipment monitoring — all without leaving the browser.

## Overview

The BMS Connection Wizard provides a guided UI for FM teams to onboard a building's BMS into SENTINEL. It wraps the backend discovery and mapping APIs into a step-by-step modal flow.

**Key principle:** BACnet/IP is the universal BMS protocol. SENTINEL can connect to any vendor that exposes BACnet/IP. For Tridium Niagara, an additional oBIX REST connection provides richer metadata.

### Supported BMS Vendors

| Vendor | Protocol | Connection Test |
|--------|----------|-----------------|
| Tridium Niagara 4 | oBIX REST + BACnet/IP | oBIX config endpoint |
| Siemens Desigo CC | BACnet/IP | BACnet WhoIs |
| Johnson Controls Metasys | BACnet/IP | BACnet WhoIs |
| Honeywell EBI | BACnet/IP | BACnet WhoIs |
| Schneider EcoStruxure | BACnet/IP | BACnet WhoIs |
| Trend Controls IQ4 | BACnet/IP | BACnet WhoIs |
| Generic BACnet/IP | BACnet/IP | BACnet WhoIs |

### Workflow

```
Step 1: Connect     → Select BMS vendor, test connection (oBIX or BACnet WhoIs)
Step 2: Discover    → AI scans BACnet points and classifies into equipment groups
Step 3: Review      → FM team reviews equipment/point mappings, corrects low-confidence items
Step 4: Approve     → Confirm and activate monitoring
```

Steps 2-4 are identical for all vendors — only the connection test in Step 1 differs.

## Access

Navigate to **Integration Monitoring** page and click the blue **Connect to BMS** button in the toolbar.

## Step 1: Connect to BMS

### Vendor Selection

A dropdown at the top of Step 1 lets the user select their BMS vendor. The form adapts based on the selection:

**Tridium Niagara 4** — Shows oBIX connection fields:

| Field | Description | Default |
|-------|-------------|---------|
| Host / IP Address | Niagara supervisor IP or hostname | — |
| Port | oBIX REST API port | 80 |
| Username | Niagara service account | — |
| Password | Service account password | — |
| Use HTTPS | Enable TLS | Off |
| Target Site | Site to associate discovered equipment with | Pre-selected |

**All other vendors** — Simplified BACnet-only view:

| Field | Description | Default |
|-------|-------------|---------|
| Target Site | Site to associate discovered equipment with | Pre-selected |

No credentials are required for non-Niagara vendors. SENTINEL broadcasts a BACnet WhoIs on the local network (UDP port 47808) to discover controllers.

### Demo Mode

Toggle **Use Demo Data** to skip the real connection and use pre-seeded Sandton City discovery data. Works for all vendors.

### Connection Test

Clicking **Test Connection** calls different APIs based on the selected vendor:

- **Niagara**: `POST /api/niagara/obix/config` (oBIX connection test)
- **All others**: `POST /api/niagara/bacnet/test-connection` (BACnet WhoIs broadcast)

**Next** is enabled only after a successful connection test or demo mode activation.

## Step 2: Discover & Classify Points

Automatically triggered when advancing from Step 1. Calls `POST /api/niagara/discover-and-classify` with:

```json
{
  "device_ip": "<configured host or 'demo'>",
  "site_id": "<selected site>",
  "use_demo": true/false,
  "bms_vendor": "desigo"
}
```

### What Happens

1. BACnet Who-Is broadcast discovers devices on the network
2. Point enumeration reads all BACnet objects from each device
3. AI classifier maps points to equipment using Haystack/Brick ontology
4. Points are grouped into equipment models (AHU, Chiller, FCU, etc.)
5. Confidence scores assigned: **high** (exact match), **medium** (partial), **low** (guessed)

### Summary Display

After discovery completes, the wizard shows:
- **Points Found** — total BACnet points discovered
- **Equipment Groups** — number of equipment models created
- **Classification Summary** — breakdown by equipment type

## Step 3: Review Mappings

Loads the full mapping details from `GET /api/niagara/mappings/{discoveryId}`.

### Equipment Cards

Each classified equipment group displays as an expandable card showing:
- Equipment name and ID
- Equipment type (AHU, Chiller, FCU, etc.)
- Point count
- Overall confidence badge (high/medium/low)

Expanding a card reveals a table of individual points:

| Column | Description |
|--------|-------------|
| Point Name | Original BACnet object name |
| Type | Classified point type (sensor, setpoint, command, status) |
| Confidence | Classification confidence badge |
| Brick Class | Brick Schema class (e.g., `Supply_Air_Temperature_Sensor`) |
| Unit | Engineering unit (deg-C, %, kW, etc.) |

### Low-Confidence Highlighting

Points classified with **low** confidence are highlighted in amber. The validation banner at the top shows the count of points needing review.

### Confidence Breakdown

A summary bar shows the distribution of confidence levels across all points (e.g., "high: 45, medium: 12, low: 3").

## Step 4: Approve & Activate

### Activation Summary

Displays:
- Number of equipment models to create
- Total points to activate
- Count of items still needing review

### Approval

Enter the approver's name (defaults to "system") and click **Approve & Activate**. This calls `POST /api/niagara/mappings/{discoveryId}/approve` to:

1. Create equipment models in SENTINEL
2. Map BACnet points to equipment
3. Activate monitoring for all approved equipment
4. Dual-write to Supabase + JSON backup

### Success State

On approval, the wizard shows a green confirmation with the count of equipment models created. Clicking **Done** closes the wizard and refreshes the Integration Monitoring page data.

## API Endpoints Used

| Step | Method | Endpoint | Purpose |
|------|--------|----------|---------|
| 1 | POST | `/api/niagara/obix/config` | Configure and test oBIX connection (Niagara only) |
| 1 | POST | `/api/niagara/bacnet/test-connection` | BACnet WhoIs connectivity test (non-Niagara) |
| 2 | POST | `/api/niagara/discover-and-classify` | Trigger discovery + AI classification |
| 3 | GET | `/api/niagara/mappings/{id}` | Get classified mapping details |
| 3 | POST | `/api/niagara/mappings/{id}/correct` | Manual point correction |
| 4 | POST | `/api/niagara/mappings/{id}/approve` | Approve and activate mappings |

## Frontend Architecture

### Files

| File | Purpose |
|------|---------|
| `frontend/src/components/BMSConnectionWizard.tsx` | 4-step wizard component (multi-vendor) |
| `frontend/src/components/NiagaraConnectionWizard.tsx` | Backward-compatible re-export |
| `frontend/src/components/IntegrationMonitoringPage.tsx` | Host page (button + modal) |
| `frontend/src/lib/api.ts` | `niagaraApi` / `bmsApi` client + TypeScript interfaces |

### State Management

Uses `useReducer` with a single `WizardState` object tracking:
- Current step (1-4)
- Selected BMS vendor
- Connection form values
- Connection status (`idle` / `testing` / `connected` / `failed`)
- Discovery ID and summary
- Mapping data (equipment, points, confidence breakdown)
- Approval status and result

### UI Design

- SENTINEL dark theme via CSS variables (`--color-sentinel-*`)
- Step progress indicator with numbered icons and connecting lines
- Vendor dropdown with protocol info
- Conditional oBIX fields (Niagara) vs BACnet-only info (other vendors)
- Confidence badges: green (high), amber (medium), red (low)
- Native HTML + Tailwind CSS (no Tremor dependency)
- Modal overlay matching the existing IntegrationWizard pattern

## Relationship to Other Onboarding Methods

| Method | Use Case | Entry Point |
|--------|----------|-------------|
| **BMS Connection Wizard** | Live BMS with BACnet/IP (any vendor) | Integration page -> "Connect to BMS" |
| **Integration Wizard** (CSV/Excel) | BMS point list export from any vendor | Integration page -> "Add Data Source" |
| **SIMBIOT MCP Tools** | AI-assisted onboarding via chat/Claude Desktop | Chat -> `create_building` tool |
| **AI-Assisted Onboarding** | Guided 8-step workflow via MCP | Claude Desktop or SENTINEL chat |

The BMS Connection Wizard is the fastest path for buildings with BACnet/IP-enabled systems — no file exports needed.

## Backend Configuration

### Prerequisites

BAC0 (BACnet/IP library) must be installed in the backend venv:

```bash
cd backend && source venv/bin/activate
pip install BAC0>=24.3.25
```

BAC0 is listed in `backend/requirements.txt` but may not be installed in all environments.

### Configuration Options

**Option A — Wizard UI (recommended):** The wizard's Step 1 configures the connection at runtime. For Niagara, oBIX credentials are entered in the form. For other vendors, no configuration is needed — BACnet WhoIs is auto-discovered.

**Option B — Environment variables:** Add to `backend/.env` for persistent Niagara configuration:

```bash
NIAGARA_OBIX_HOST=192.168.1.100    # Niagara Supervisor IP
NIAGARA_OBIX_PORT=443              # oBIX REST port (443 for HTTPS)
NIAGARA_OBIX_USERNAME=sentinel-service
NIAGARA_OBIX_PASSWORD=<password>
NIAGARA_OBIX_HTTPS=true            # Use HTTPS
NIAGARA_BACNET_PORT=47808          # BACnet/IP port (default)
NIAGARA_BACNET_LOCAL_IP=           # Local bind IP (blank = auto-detect)
```

All settings are defined in `backend/app/config/settings.py` as `niagara_*` fields. Environment variables take precedence over Settings defaults.

### BACnet Auto-Start

The BACnet client auto-starts when:
- `POST /api/niagara/bacnet/test-connection` is called (wizard connection test)
- `discover-and-classify` is called with a real device ID

No manual startup required. If BAC0 fails to initialize (port conflict, network issue), the system falls back to demo data when `use_demo=true`.

### Network Requirements

| Protocol | Port | Direction | Purpose |
|----------|------|-----------|---------|
| oBIX REST | 443 (HTTPS) or 80 (HTTP) | SENTINEL -> Niagara | Connection test, history, alarms (Niagara only) |
| BACnet/IP | 47808 (UDP) | SENTINEL <-> BMS | Real-time discovery, point R/W, COV (all vendors) |

SENTINEL VM must have IP access to the BMS controllers — either on the same BMS VLAN or with routed access through the firewall.

## Related Documentation

- [Tridium Niagara Integration Guide](../07-integrations/tridium-niagara-integration.md) — Full backend integration reference (BACnet, oBIX, protocols)
- [AI-Assisted Onboarding](ai-assisted-onboarding.md) — 8-step MCP tool onboarding workflow
- [BMS/CAFM Integration](14-17-bms-cafm-integration.md) — CSV/Excel data ingestion wizard
- [MCP Tools Reference](../03-api-reference/mcp-tools-reference.md) — SIMBIOT MCP tool schemas

---

*Feature: BMS Connection Wizard (Multi-Vendor)*
*Document version: 2.0.0*
*Created: 2026-02-04*
