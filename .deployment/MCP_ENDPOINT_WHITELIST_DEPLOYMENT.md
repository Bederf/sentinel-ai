# MCP Endpoint Authentication Whitelist Deployment

## Problem
Production server (`bms.aimthelaw.co.za`) is blocking MCP endpoints with HTTP 401 Authentication Required:
- `/api/mcp/sse` - Claude Desktop SSE transport
- `/api/mcp/openai/mcp` - ChatGPT/M365 Copilot Streamable HTTP transport

## Solution
Add both endpoints to `_PUBLIC_PREFIXES` in middleware to allow unauthenticated access (MCP authentication happens at protocol level, not HTTP header level).

## Changes Made
**File:** `backend/app/startup/middleware.py`

**Added to `_PUBLIC_PREFIXES` tuple:**
```python
_PUBLIC_PREFIXES = (
    "/api/clawd-webhooks",  # Telegram bot callbacks
    "/api/mcp/sse",         # Claude Desktop (NEW)
    "/api/mcp/openai",      # ChatGPT/M365 Copilot (NEW)
)
```

## Deployment Steps

### 1. Copy Updated Middleware to Production
```bash
# From your local development machine:
scp backend/app/startup/middleware.py your-user@bms.aimthelaw.co.za:/opt/bms-intelligence/backend/app/startup/
```

Or if you have direct shell access to production:

### 2. Restart Backend Service
```bash
# On production server (bms.aimthelaw.co.za):
sudo systemctl restart sentinel-bms-backend
```

Verify service restarted:
```bash
sudo systemctl status sentinel-bms-backend
```

### 3. Verify Endpoints Are Now Accessible

Test SSE endpoint (should return text/event-stream with keep-alive):
```bash
curl -i https://bms.aimthelaw.co.za/api/mcp/sse
# Expected: HTTP 200 (not 401)
# Should see streaming events starting with: event: message
```

Test OpenAI endpoint (should return server info):
```bash
curl -i https://bms.aimthelaw.co.za/api/mcp/openai/mcp
# Expected: HTTP 400 (missing POST body is ok - proves auth passed)
# NOT: HTTP 401
```

Test with actual MCP request:
```bash
curl -X POST https://bms.aimthelaw.co.za/api/mcp/openai/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
# Expected: HTTP 200 with tools list (not 401)
```

### 4. Configure Claude Desktop

Update your Claude Desktop MCP configuration to:
```bash
npx -y mcp-remote https://bms.aimthelaw.co.za/api/mcp/sse
```

Then restart Claude Desktop to connect.

## Monitoring

Check production logs for successful connections:
```bash
# On production server:
sudo journalctl -u sentinel-bms-backend -f | grep "SSE MCP"
```

Expected output (every 15 seconds):
```
SSE heartbeat sent (connection uptime: XXXs)
```

## Rollback (if needed)

If something goes wrong:
```bash
# Revert to previous version (remove `/api/mcp/openai` line)
# Then:
sudo systemctl restart sentinel-bms-backend
```

## Files Changed
- `backend/app/startup/middleware.py` - Added 2 lines to `_PUBLIC_PREFIXES`

## Timeline
- **Before:** Claude Desktop connections receive HTTP 401 "Authentication required"
- **After:** Connections proceed to MCP protocol layer (which has its own security)
- **Expected:** Claude Desktop connects and stays connected (keep-alive maintains long-lived sessions)
