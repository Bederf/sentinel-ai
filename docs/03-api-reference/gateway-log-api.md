---
title: Gateway Log API
category: api-reference
phase: ADR-001
date: 2026-03-12
tags: [sentry, observability, gateway]
---

# Gateway Log API

## Overview

Observability endpoints for the Sentry gateway tool layer. Every tool script (`bms_query.py`, `bms_wo.py`, `bms_inspect.py`, `bms_reset.py`, `bms_note.py`) posts a structured log entry after each invocation. This closes the gateway-level blind spot identified in ADR-001 (Hermes Migration Assessment).

Two endpoints on the `/api/sentry` router:

1. **`POST /api/sentry/gateway-log`** — Record a tool invocation
2. **`GET /api/sentry/gateway-log`** — Query recent gateway activity

## POST /api/sentry/gateway-log

Record a gateway tool invocation for observability.

**Authentication:** `X-Sentry-API-Key` header (optional — fire-and-forget from tool scripts).

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tool` | string | Yes | Tool name (`bms_query`, `bms_wo`, `bms_inspect`, `bms_reset`, `bms_note`) |
| `command` | string | Yes | Action (`info`, `summary`, `create_wo`, `reset`, `inspect`, `save`, `prompt`) |
| `equipment_code` | string | No | Equipment code if applicable |
| `telegram_user_id` | string | No | Telegram user who triggered the action (default: `"unknown"`) |
| `success` | boolean | No | Whether the invocation succeeded (default: `true`) |
| `error` | string | No | Error message if failed |
| `duration_ms` | integer | No | Execution time in milliseconds |
| `result_summary` | string | No | Short result (e.g. WO code, `reset_ok`, `blocked`) |
| `metadata` | object | No | Additional context |

### Response

```json
{"logged": true}
```

### Example

```bash
curl -X POST http://localhost:9095/api/sentry/gateway-log \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "bms_wo",
    "command": "create_wo",
    "equipment_code": "S002-FCU-341",
    "telegram_user_id": "8359288792",
    "success": true,
    "result_summary": "WO-SIM-0042",
    "duration_ms": 1250
  }'
```

## GET /api/sentry/gateway-log

Query recent gateway activity. Returns entries newest-first from an in-memory ring buffer (1000 entries max).

**Authentication:** `X-Sentry-API-Key` header.

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 50 | Max entries to return (1-500) |
| `tool` | string | — | Filter by tool name |
| `equipment_code` | string | — | Filter by equipment code |
| `telegram_user_id` | string | — | Filter by Telegram user |
| `success_only` | boolean | — | Filter by success status |

### Response

```json
{
  "entries": [
    {
      "id": 1,
      "timestamp": "2026-03-12T20:37:10.692955+00:00",
      "tool": "bms_query",
      "command": "info",
      "equipment_code": "S002-AHU-101",
      "telegram_user_id": "8359288792",
      "success": true,
      "error": null,
      "duration_ms": 56,
      "result_summary": "Health 85%",
      "metadata": {}
    }
  ],
  "total_in_buffer": 42,
  "showing": 1
}
```

### Example

```bash
# All recent activity
curl -H "X-Sentry-API-Key: $KEY" \
  "http://localhost:9095/api/sentry/gateway-log?limit=20"

# Only failed calls
curl -H "X-Sentry-API-Key: $KEY" \
  "http://localhost:9095/api/sentry/gateway-log?success_only=false"

# Activity for specific equipment
curl -H "X-Sentry-API-Key: $KEY" \
  "http://localhost:9095/api/sentry/gateway-log?equipment_code=S002-FCU-341"
```

## Architecture

```
Telegram → Sentry Gateway (OpenClaw)
               ↓
         Tool Scripts (~/.sentry/tools/)
               ↓
    gateway_log.py (fire-and-forget POST)
               ↓
    POST /api/sentry/gateway-log
               ↓
    In-memory ring buffer (1000 entries)
    + Python structured logger (Loki/Promtail)
```

## Storage

- **In-memory ring buffer**: Last 1000 entries, lost on restart
- **Structured logger**: `GATEWAY` prefix entries in Python logging, collected by Promtail for Loki

## Related

- [Call Log API](call-log-api.md) — Sentry complaint/WO endpoints
- [Inspection API](inspection.md) — Inspection checklist and result endpoints
- ADR-001: Hermes Migration Assessment (project memory)
