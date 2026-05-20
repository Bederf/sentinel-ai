---
title: "Asoba Terminal API MCP Server"
type: "spec"
status: "implemented"
version: "1.0.0"
created: "2026-05-18"
updated: "2026-05-18"
tags: ["sentinel", "asoba", "esums", "mcp", "integration", "ltm", "fault-detection"]
domain: "integration"
audience: "backend-engineers, ai-integrators"
complexity: "intermediate"
---

# Asoba Terminal API MCP Server

**Purpose:** Expose Asoba's eSUMS/Ona Terminal API as MCP tools inside Sentinel's AI chat and SIMBIOT interface. Enables bidirectional intelligence — Sentinel BMS health data enriches Asoba fault detection; Asoba OODA summaries surface in Sentinel dashboards.

**Upstream API:** `https://api.asoba.co` (Asoba Corporation)  
**Auth:** `x-api-key` header — contact `support@asoba.co`  
**Base docs:** `https://docs.asoba.co/api-reference/terminal/overview`  
**Implementation:** Phase 209  
**Status:** Implemented (awaiting API key for live testing)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│               Sentinel AI Chat / SIMBIOT Interface              │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│  stdio Transport         │    │  SSE Transport           │
│  (Claude Desktop)        │    │  /api/mcp/asoba/sse      │
│  asoba_stdio.py          │    │                          │
└──────────────────────────┘    └──────────────────────────┘
              │                               │
              └───────────────┬───────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Asoba MCP Server (asoba_server.py)                            │
│  - 11 tools across 3 categories                                │
│  - HTTP client to api.asoba.co                                 │
│  - Site ID mapping: Sentinel → Asoba                           │
│  - Graceful degradation when API key not configured            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Asoba Terminal API  (api.asoba.co)                            │
│  Rate limit: 60 req/min · Auth: x-api-key header               │
└─────────────────────────────────────────────────────────────────┘
```

---

## MCP Tools

### Fault Detection & Diagnostics (4)

| Tool | Description | Asoba Endpoint |
|------|-------------|----------------|
| `asoba_get_ooda_summary` | Get ML-enhanced OODA summary with fault severity and energy-at-risk | `POST /terminal/ooda` |
| `asoba_run_fault_detection` | Trigger OODA fault detection on an asset | `POST /terminal/detect` |
| `asoba_list_detections` | List recent detection results for an asset | `POST /terminal/detect` (action=list) |
| `asoba_run_diagnostics` | Run AI diagnostics on a detected fault | `POST /terminal/diagnose` |

### Asset & Maintenance Management (5)

| Tool | Description | Asoba Endpoint |
|------|-------------|----------------|
| `asoba_list_assets` | List assets registered in Asoba for a customer | `POST /terminal/assets` |
| `asoba_create_work_order` | Create a maintenance work order in Asoba | `POST /terminal/order` |
| `asoba_list_work_orders` | List work orders for a customer | `POST /terminal/order` (action=list) |
| `asoba_create_maintenance_schedule` | Schedule maintenance for an asset | `POST /terminal/schedule` |
| `asoba_get_bom` | Get bill of materials for maintenance task | `POST /terminal/bom` |

### ML Intelligence (2)

| Tool | Description | Asoba Endpoint |
|------|-------------|----------------|
| `asoba_get_forecast` | Retrieve stored ML energy forecast for a site | `POST /terminal/forecast` |
| `asoba_list_ml_models` | List available ML models in Asoba registry | `POST /terminal/ml-models` |

---

## Tool Specifications

### `asoba_get_ooda_summary`

The primary integration tool — fetch ML-enhanced OODA summary including fault severity and energy-at-risk.

**Input Schema:**
```json
{
  "customer_id": {
    "type": "string",
    "description": "Asoba customer ID. Maps from Sentinel site_id via site_mapping config."
  },
  "sentinel_site_id": {
    "type": "string",
    "description": "Optional: auto-resolve customer_id from Sentinel site_id (e.g., site-002)"
  }
}
```

**Example Call:**
```python
await server.call_tool("asoba_get_ooda_summary", {
    "customer_id": "ltm-sandton-001"
})
# or
await server.call_tool("asoba_get_ooda_summary", {
    "sentinel_site_id": "site-002"
})
```

**Response:**
```json
{
  "success": true,
  "customer_id": "ltm-sandton-001",
  "ml_enhanced_activities": [
    {
      "summary_id": "ooda_20260518_090000",
      "asset_id": "INV-S002-SOLAR-001",
      "created_at": "2026-05-18T09:00:00Z",
      "fault_family": "inverter_fault",
      "severity_label": "warning",
      "confidence": 0.87,
      "energy_at_risk_kw": 12.3,
      "root_cause": "Inverter efficiency degradation. Output 8% below expected for current irradiance.",
      "recommended_actions": [
        {
          "priority": "high",
          "action": "Inspect DC string connections on inverter INV-S002-SOLAR-001"
        }
      ],
      "detections": [
        "Power output anomaly detected at 08:45:00Z",
        "Performance ratio below threshold for 3 consecutive intervals"
      ]
    }
  ],
  "count": 1,
  "_sentinel_enriched": {
    "site_id": "site-002",
    "sentinel_health_score": 74,
    "sentinel_alert_count": 2
  }
}
```

---

### `asoba_create_work_order`

Bidirectional integration — Sentinel fault triggers a work order in both Sentinel's own WO system and Asoba's.

**Input Schema:**
```json
{
  "customer_id": { "type": "string", "required": true },
  "asset_id": { "type": "string", "description": "Asoba asset ID", "required": true },
  "description": { "type": "string", "description": "Work order description", "required": true },
  "priority": { "type": "string", "enum": ["low", "medium", "high", "critical"], "default": "medium" },
  "sentinel_work_order_id": { "type": "string", "description": "Cross-reference to Sentinel WO", "required": false }
}
```

---

## Implementation

### File Locations

```
backend/app/mcp/asoba_server.py         # Main MCP server
backend/app/mcp/asoba_stdio.py          # stdio transport wrapper
backend/app/api/mcp_asoba.py            # REST API wrapper
```

### Environment Variables

```bash
# Add to .env
ASOBA_API_KEY=<your_key_from_support@asoba.co>
ASOBA_API_BASE_URL=https://api.asoba.co
ASOBA_ENABLED=true

# Site ID mapping (Sentinel site_id → Asoba customer_id)
ASOBA_SITE_MAPPING=site-002:ltm-sandton-001,site-003:ltm-rosebank-001
```

### Router Registration

Registered in `backend/app/api/registrars/analytics.py`:
```python
from app.api import mcp_asoba
app.include_router(mcp_asoba.router, prefix="/api/mcp/asoba", tags=["asoba"])
```

---

## API Endpoints

### `GET /api/mcp/asoba/tools`
List available MCP tools.

### `POST /api/mcp/asoba/call`
Execute an MCP tool.

**Request:**
```json
{
  "tool": "asoba_get_ooda_summary",
  "arguments": {
    "customer_id": "ltm-sandton-001"
  }
}
```

### `GET /api/mcp/asoba/health`
Health check for Asoba integration.

**Response:**
```json
{
  "enabled": true,
  "api_key_configured": true,
  "base_url": "https://api.asoba.co",
  "site_mapping": {
    "site-002": "ltm-sandton-001"
  },
  "status": "healthy"
}
```

### `GET /api/mcp/asoba/site-mapping`
Get current site ID mappings.

---

## Claude Desktop Configuration

Add to your Claude Desktop config (`~/.config/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "simbiot": {
      "command": "python",
      "args": ["-m", "app.mcp.simbiot_stdio"],
      "cwd": "/opt/bms-intelligence/backend",
      "env": { "PYTHONPATH": "/opt/bms-intelligence/backend" }
    },
    "asoba": {
      "command": "python",
      "args": ["-m", "app.mcp.asoba_stdio"],
      "cwd": "/opt/bms-intelligence/backend",
      "env": {
        "PYTHONPATH": "/opt/bms-intelligence/backend",
        "ASOBA_API_KEY": "<your_key>",
        "ASOBA_ENABLED": "true",
        "ASOBA_SITE_MAPPING": "site-002:ltm-sandton-001"
      }
    }
  }
}
```

---

## Demo Chat Prompts

Once connected, these natural language queries work in Sentinel's AI chat:

```
"What faults does Asoba currently show for Sandton City?"
→ calls asoba_get_ooda_summary with customer_id=ltm-sandton-001

"Run fault detection on the solar inverter"
→ calls asoba_run_fault_detection with asset_id

"Create a work order in eSUMS for the inverter issue"
→ calls asoba_create_work_order, links to Sentinel WO

"What's the energy forecast for site-002?"
→ calls asoba_get_forecast

"List all assets in Asoba for this site"
→ calls asoba_list_assets
```

---

## Graceful Degradation

When `ASOBA_ENABLED=false` or `ASOBA_API_KEY` is empty:

- All tools return a structured error response (not an exception)
- Sentinel AI chat surfaces: *"Asoba integration not enabled — contact support@asoba.co for an API key"*
- Sentinel dashboard health check shows Asoba connector as `disconnected` (not `error`)
- No impact on SIMBIOT or any other Sentinel functionality

---

## Getting an API Key

Contact: `support@asoba.co`  
Subject: `eSUMS Starter — Sentinel BMS integration`  

**Note:** API keys are scoped to specific `site_id` values. Request access for your pilot site IDs upfront.

For the Dhevan meeting: ask him to arrange a complimentary API key for the integration demo. Given LTM is an Asoba partner this should be immediate.

---

## Integration with ODS-E Export

The Asoba MCP server works in conjunction with the ODS-E export endpoints:

1. **ODS-E Export** provides energy timeseries data to Asoba
2. **Asoba MCP** provides fault detection and work order management
3. **Bidirectional flow**: Sentinel detects → Asoba diagnoses → Work order created → Status updates flow back

See also: [ODS-E Export Endpoint Specification](./odse-export-endpoint-spec.md)

---

## Status

✅ **IMPLEMENTED** — Phase 209 complete

- [x] `asoba_server.py` with 11 tools
- [x] `asoba_stdio.py` transport wrapper
- [x] REST wrapper registered
- [x] `.env.example` updated
- [ ] Live test against `api.asoba.co` (requires API key)
- [ ] Demo prompts validated (requires API key)

---

**Document Version:** 1.0.0  
**Last Updated:** 2026-05-18  
**Status:** Implemented (awaiting API key)
