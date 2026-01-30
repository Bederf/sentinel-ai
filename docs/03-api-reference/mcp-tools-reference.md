---
title: "MCP Tools Reference (SIMBIOT)"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-01-30"
updated: "2026-01-30"
author: "Sentinel Development Team"
tags: ["mcp", "simbiot", "model-context-protocol", "tools"]
related: ["../02-architecture/system-overview.md", "../08-ai-ml/claude-integration.md"]
domain: "bms"
audience: "developers"
complexity: "advanced"
estimated_read_time: 20
---

# SIMBIOT MCP Server Integration Guide

This guide explains how to integrate SIMBIOT MCP tools with Claude Desktop and cloud Claude.

## Overview

SIMBIOT MCP Server provides 12 tools for building management:
- get_buildings, get_assets, get_asset_detail
- get_devices, read_device_point, write_device_point
- get_alarms, search_alarms
- get_trends, get_health_score
- get_work_orders, create_work_order

## Integration Methods

### Method 1: Local stdio (Claude Desktop)

**Best for:** Local development, Claude Desktop app

**Setup:**

1. Edit Claude Desktop config:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%/Claude/claude_desktop_config.json`
   - Linux: `~/.config/Claude/claude_desktop_config.json`

2. Add SIMBIOT server:
   ```json
   {
     "mcpServers": {
       "simbiot": {
         "command": "python",
         "args": [
           "-m",
           "app.mcp.simbiot_stdio"
         ],
         "cwd": "/path/to/bms-intelligence/backend",
         "env": {
           "PYTHONPATH": "/path/to/bms-intelligence/backend"
         }
       }
     }
   }
   ```

3. Restart Claude Desktop

4. Verify tools are available in Claude

**Usage:**
In Claude Desktop, ask:
- "Show me all buildings in Gauteng"
- "What's the current status of chiller 001-gwc-chiller-001?"
- "List all active alarms"

### Method 2: Remote SSE (Cloud Claude)

**Best for:** Web applications, cloud-based AI

**Setup:**

1. Start backend server:
   ```bash
   cd backend
   uvicorn app.main:app --host 0.0.0.0 --port 9095
   ```

2. Connect via SSE:
   ```
   GET http://localhost:9095/api/mcp/sse
   ```

3. Or use POST endpoint:
   ```bash
   curl -X POST http://localhost:9095/api/mcp/sse/request \
     -H "Content-Type: application/json" \
     -d '{
       "jsonrpc": "2.0",
       "id": 1,
       "method": "tools/call",
       "params": {
         "name": "get_buildings",
         "arguments": {}
       }
     }'
   ```

**Usage in Python:**
```python
import asyncio
from anthropic import Anthropic

client = Anthropic()

async def ask_claude_with_simbiot():
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        tools=[],  # Claude auto-discovers SIMBIOT tools via MCP
        messages=[
            {
                "role": "user",
                "content": "Show me all buildings with critical alarms"
            }
        ]
    )
    return response
```

### Method 3: REST API (Existing)

**Best for:** Traditional web applications, mobile apps

**Documentation:** See http://localhost:9095/docs

**Endpoints:**
- `GET /api/mcp/simbiot/info` - Server info
- `GET /api/mcp/simbiot/tools` - List tools
- `POST /api/mcp/simbiot/call` - Execute tool

## MCP Protocol Reference

### Initialize
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "clientInfo": {
      "name": "claude-desktop",
      "version": "1.0.0"
    }
  }
}
```

### List Tools
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list"
}
```

### Call Tool
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "get_buildings",
    "arguments": {
      "region": "Gauteng",
      "status_filter": "critical"
    }
  }
}
```

## Testing

### Test stdio server:
```bash
cd backend
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m app.mcp.simbiot_stdio
```

### Test SSE server:
```bash
curl -N http://localhost:9095/api/mcp/sse
```

### Test REST API:
```bash
python test_mcp_api.py
```

## Troubleshooting

**Claude Desktop can't connect:**
- Verify PYTHONPATH includes backend directory
- Check Python executable path
- Enable debug logging in Claude Desktop

**SSE connection drops:**
- Check firewall settings
- Verify backend is running
- Check browser console for errors

**Tools not available:**
- Restart Claude/backend
- Check SIMBIOTMCPServer has 12 tools
- Verify MCP server logs for errors

## Security Notes

**Local (stdio):** Runs on your machine, no network exposure

**Remote (SSE):** Exposes building data over network:
- Use HTTPS in production
- Add authentication middleware
- Implement rate limiting
- Audit all tool calls

## Next Steps

- Add authentication for SSE endpoint
- Implement request signing
- Add usage metrics and monitoring
- Create admin dashboard for MCP connections
