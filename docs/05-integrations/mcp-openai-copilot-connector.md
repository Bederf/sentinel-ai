---
status: implemented
version: 1.0
date: 2026-04-04
---

# MCP OpenAI / Microsoft 365 Copilot Connector

## Overview

SENTINEL exposes a **Streamable HTTP MCP endpoint** at `https://bms.aimthelaw.co.za/api/mcp/openai/mcp` for integration with:

- Microsoft 365 Copilot (declarative agents)
- ChatGPT (My GPTs / GPT Builder)
- Any MCP-compatible AI assistant

The endpoint implements the MCP 2024-11-05 spec over Streamable HTTP transport.

## Endpoint Details

| Property | Value |
|----------|-------|
| **URL** | `https://bms.aimthelaw.co.za/api/mcp/openai/mcp` |
| **Transport** | Streamable HTTP |
| **Auth** | None (open) |
| **Protocol** | MCP 2024-11-05 |
| **Auto-discovery** | `https://bms.aimthelaw.co.za/.well-known/mcp.json` |

## CORS Headers

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, Accept, Authorization, Cache-Control
Access-Control-Allow-Credentials: true
```

## Available Tools

| Tool | Description |
|------|-------------|
| `search` | Full-text search across all BMS data |
| `fetch` | Retrieve full document by ID |

### search

```json
{
  "name": "search",
  "arguments": {
    "query": "chiller maintenance"
  }
}
```

Returns matching documents across: buildings, equipment, alerts, predictions, work orders, technical documents.

### fetch

```json
{
  "name": "fetch",
  "arguments": {
    "id": "equipment-S002-CHILLER-B1-001"
  }
}
```

Returns full document content including text, metadata, and URL.

## Indexed Data

| Category | Source | Description |
|----------|--------|-------------|
| Buildings | Supabase `sites` | Name, address, region, floors, sqm, equipment count |
| Equipment | Supabase `equipment` | Type, manufacturer, model, health_score, status, location |
| Alerts | Supabase `alerts` | Severity, status, message, equipment, building |
| Predictions | Supabase `predictions` | ML predictions — probability, severity, urgency, failure date, recommended action |
| Work Orders | Supabase `work_orders` | Priority, status, description, assigned_to, cost |
| Documents | Supabase `documents` | Type, equipment_type, manufacturer, model, summary, failure_modes |

Refresh interval: 5 minutes (lazy load).

## Setup: Microsoft 365 Copilot

1. Open **Microsoft 365 Copilot Studio**
2. Create or open your **declarative agent**
3. Go to **Connect** → **Add capability** → **MCP servers**
4. Click **Add server**
5. Enter:
   - **Server name**: `SENTINEL BMS`
   - **Server URL**: `https://bms.aimthelaw.co.za/api/mcp/openai/mcp`
6. Click **Save**
7. The agent auto-discovers `search` and `fetch` tools

## Setup: ChatGPT (My GPTs)

1. Open **ChatGPT** → **My GPTs** → **Create a GPT**
2. Go to **Configure** → **Plugins** → **Plugin Store**
3. Click **Develop your own plugin**
4. Enter domain: `bms.aimthelaw.co.za`
5. Plugin reads from `/.well-known/mcp.json` for tool definitions
6. Save and activate

## Setup: Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sentinel-bms": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://bms.aimthelaw.co.za/api/mcp/openai/mcp"]
    }
  }
}
```

## Testing the Endpoint

### List tools
```bash
curl -X POST https://bms.aimthelaw.co.za/api/mcp/openai/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

### Search
```bash
curl -X POST https://bms.aimthelaw.co.za/api/mcp/openai/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search","arguments":{"query":"chiller"}}}'
```

### Fetch
```bash
curl -X POST https://bms.aimthelaw.co.za/api/mcp/openai/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"fetch","arguments":{"id":"equipment-S002-CHILLER-B1-001"}}}'
```

## Architecture

```
AI Assistant (Copilot/ChatGPT)
         │
         ▼
https://bms.aimthelaw.co.za/api/mcp/openai/mcp
         │
         ▼ (Cloudflare Worker routing)
144.91.122.235:9095
         │
         ▼
  OpenAIConnectorMCPServer
    (search + fetch only)
         │
         ├─► Supabase (primary)
         └─► JSON files (fallback)
```

## Comparison: OpenAI Connector vs SIMBIOT MCP

| Feature | OpenAI Connector | SIMBIOT MCP |
|---------|-----------------|-------------|
| Endpoint | `/api/mcp/openai/mcp` | `/api/mcp/sse` |
| Tools | 2 (search, fetch) | 33 |
| Transport | Streamable HTTP | SSE + REST |
| Device control | No | Yes |
| Write operations | No | Yes |
| Use case | RAG / read-only AI | Full BMS control |
| Auth | None | Configurable |

## Backend Code

- `backend/app/api/mcp_openai.py` — Streamable HTTP endpoint
- `backend/app/mcp/openai_connector_server.py` — Server implementation
