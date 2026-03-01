---
title: "ServiceNow integration"
type: "guide"
status: "approved"
version: "1.0.0"
created: "2026-03-01"
updated: "2026-03-01"
author: "Sentinel Development Team"
tags: ["servicenow", "itsm", "integration", "incidents", "work-orders"]
related: ["../03-api-reference/servicenow-api.md"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 6
---

# ServiceNow integration

Phase 138 adds a read-only ServiceNow client that connects SENTINEL to an
existing ITSM instance. The integration is designed to start idle with zero
network calls and produce graceful empty responses until credentials are
provided.

## What it does

- Reads incidents, work orders, change requests, assets, locations, and 10 other
  FM-relevant tables from a ServiceNow instance via the Table API and Stats API
- Auto-discovers which tables are accessible on first connection check (15
  tables probed in parallel batches of 5)
- Caches table schemas per session to avoid repeated lookups
- Exposes 10 REST endpoints under `/api/servicenow`
- Provides 4 chat tools for the conversational AI to query ITSM data
- All operations are strictly read-only; no writes are made to ServiceNow

## Architecture

```
SENTINEL Backend
  ├── api/servicenow.py         # 10 REST endpoints
  ├── services/servicenow_service.py  # Read-only httpx client (singleton)
  └── services/chat_tools.py    # 4 ServiceNow chat tool handlers
         │
         ▼
   ServiceNow Instance (Table API + Stats API)
```

The service uses `httpx.AsyncClient` with HTTP Basic authentication.
A module-level singleton (`get_servicenow_service()`) manages the client
lifecycle. The shutdown handler is wired in `app/startup/events.py`.

## Configuration

All settings are loaded from environment variables. No configuration files are
required.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SERVICENOW_DOMAIN` | Yes | (empty) | Instance domain (e.g. `mycompany.service-now.com`) |
| `SERVICENOW_USER` | Yes | (empty) | Service account username |
| `SERVICENOW_PASSWORD` | Yes | (empty) | Service account password |
| `SERVICENOW_TIMEOUT` | No | `30` | HTTP request timeout in seconds |
| `SERVICENOW_PAGE_SIZE` | No | `100` | Default page size for table queries |

The service considers itself configured when all three required variables
(`DOMAIN`, `USER`, `PASSWORD`) are non-empty.

### Minimal .env example

```bash
SERVICENOW_DOMAIN=mycompany.service-now.com
SERVICENOW_USER=sentinel_readonly
SERVICENOW_PASSWORD=<service-account-password>
```

## Connection status

The service tracks connection state as one of:

| Status | Meaning |
|--------|---------|
| `not_configured` | Required env vars are missing |
| `connected` | Auth succeeded, tables discovered |
| `auth_failed` | 401 from ServiceNow; check credentials |
| `unreachable` | Network/DNS failure; check domain |
| `error` | Unexpected failure |

Use `GET /api/servicenow/status` or `POST /api/servicenow/discover` to inspect
the current state.

## Module gating

Endpoints are split into two tiers:

- **BASE** (any authenticated user): status, discover, incidents,
  incident summary
- **MAINTENANCE** (requires `ModuleType.MAINTENANCE` active): work orders, work
  order summary, generic table query, schema, history, aggregate

This means a site without the MAINTENANCE module can still view incident
intelligence, but work order and advanced query capabilities are gated.

## Chat tools

Four tools are registered in `chat_tools.py` for the conversational AI:

| Tool | Description | Module gate |
|------|-------------|-------------|
| `check_servicenow_status` | Connection and config status | BASE |
| `query_servicenow_incidents` | Filtered incident queries | BASE |
| `query_servicenow_work_orders` | Filtered work order queries | MAINTENANCE |
| `get_servicenow_incident_summary` | Priority/state breakdown | BASE |

All four tools are registered in `tool_policy.py` as `ANALYSIS_TOOLS` (read-only
tier) and `SAFE_TO_ECHO_TOOLS` (no secrets in output).

## Discovered tables

On connection, the service probes these 15 FM-relevant tables:

`incident`, `sc_task`, `change_request`, `cmdb_ci`, `cmn_location`,
`sys_user`, `sys_user_group`, `fm_expense_line`, `wm_order`, `alm_asset`,
`pm_schedule`, `sn_si_incident`, `kb_knowledge`, `sla_condition`, `contract`

Only tables the service account can access appear in the discovered list.

## Testing without ServiceNow

When `SERVICENOW_DOMAIN` is not set, the service remains in
`not_configured` state. All API endpoints and chat tools return graceful empty
responses:

```json
{"result": [], "count": 0, "error": "ServiceNow not configured"}
```

No network calls are made. This allows local development, demo mode, and tests
to run without a live ServiceNow instance.

## Security

- **Read-only:** No POST/PUT/PATCH/DELETE calls to ServiceNow. The httpx client
  only issues GET requests against the Table API and Stats API.
- **Credentials:** Loaded from environment variables, never logged or echoed.
- **Tool policy:** All 4 chat tools pass the default-deny `REGISTERED_TOOLS`
  check and are classified as `ANALYSIS_TOOLS` (no control or write actions).
- **Auth:** Every endpoint requires JWT authentication. MAINTENANCE endpoints
  additionally require module activation.

## Files

| File | Purpose |
|------|---------|
| `backend/app/services/servicenow_service.py` | Core read-only client and singleton |
| `backend/app/api/servicenow.py` | 10 REST endpoints |
| `backend/app/services/chat_tools.py` | 4 chat tool handlers |
| `backend/app/security/tool_policy.py` | Tool registration (ANALYSIS + SAFE_TO_ECHO) |
| `backend/app/api/registrars/operations.py` | Router registration |
| `backend/app/startup/events.py` | Shutdown cleanup |

## Related

- [ServiceNow API reference](../03-api-reference/servicenow-api.md)
