---
title: "ServiceNow API"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-03-01"
updated: "2026-03-01"
author: "Sentinel Development Team"
tags: ["servicenow", "itsm", "incidents", "work-orders", "api"]
related: ["../05-integrations/servicenow-integration.md"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 8
---

# ServiceNow API

Read-only REST endpoints for querying a ServiceNow ITSM instance. All endpoints
live under the `/api/servicenow` prefix and return graceful empty responses when
ServiceNow is not configured.

## Authentication and module gating

| Tier | Auth requirement | Endpoints |
|------|-----------------|-----------|
| BASE | `AuthLevel.AUTHENTICATED` | `/status`, `/discover`, `/incidents`, `/incidents/summary` |
| MAINTENANCE | `ModuleType.MAINTENANCE` | `/work-orders`, `/work-orders/summary`, `/query/{table}`, `/schema/{table}`, `/history/{table}/{sys_id}`, `/aggregate/{table}` |

BASE endpoints are available to any authenticated user. MAINTENANCE endpoints
require the MAINTENANCE bolt-on module to be active for the requesting site.

---

## Endpoints

### GET /api/servicenow/status

Return current ServiceNow connection status.

**Auth:** AUTHENTICATED

**Response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | One of `not_configured`, `connected`, `auth_failed`, `unreachable`, `error` |
| `message` | string | Human-readable status message |
| `instance_name` | string | Configured ServiceNow domain (empty when not configured) |
| `discovered_tables` | string[] | FM tables found during last discovery |
| `last_checked` | string | ISO 8601 timestamp of last connection check |
| `is_configured` | boolean | Whether all required env vars are set |

---

### POST /api/servicenow/discover

Force a connection check and table re-discovery. Probes 15 FM-relevant tables in
parallel batches of 5.

**Auth:** AUTHENTICATED

**Response:** Same shape as `/status` (minus `is_configured`).

---

### GET /api/servicenow/incidents

Fetch open incidents with optional filters.

**Auth:** AUTHENTICATED

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `priority` | int (1-4) | none | Filter by priority (1=Critical, 2=High, 3=Medium, 4=Low) |
| `category` | string | none | Filter by category |
| `limit` | int (1-500) | 50 | Max records to return |

**Response:** `{"result": [...], "count": N}`

---

### GET /api/servicenow/incidents/summary

Aggregate incident counts by priority and state.

**Auth:** AUTHENTICATED

**Response:**

```json
{
  "by_priority": [{"groupby_fields": [...], "stats": {"count": "12"}}],
  "by_state": [{"groupby_fields": [...], "stats": {"count": "8"}}],
  "total_open": 42
}
```

---

### GET /api/servicenow/work-orders

Fetch work orders from the `wm_order` table.

**Auth:** MAINTENANCE module

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `state` | string | none | Filter by state value |
| `priority` | int (1-4) | none | Filter by priority |
| `limit` | int (1-500) | 50 | Max records to return |

**Response:** `{"result": [...], "count": N}`

---

### GET /api/servicenow/work-orders/summary

Aggregate work order counts grouped by state and priority.

**Auth:** MAINTENANCE module

**Response:** ServiceNow Stats API result grouped by `state,priority`.

---

### GET /api/servicenow/query/{table}

Generic read-only table query against any ServiceNow table.

**Auth:** MAINTENANCE module

**Path parameters:**

| Param | Description |
|-------|-------------|
| `table` | ServiceNow table name (e.g. `incident`, `cmdb_ci`, `alm_asset`) |

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | string | none | ServiceNow encoded query string |
| `fields` | string | table default | Comma-separated field names |
| `limit` | int (1-1000) | 100 | Max records |
| `offset` | int | 0 | Pagination offset |
| `order_by` | string | none | Sort field (prefix `-` for descending) |

**Response:** `{"result": [...], "count": N}`

Default fields are applied per table when `fields` is not specified. The service
defines defaults for 15 FM-relevant tables including `incident`, `wm_order`,
`cmdb_ci`, `alm_asset`, `change_request`, `pm_schedule`, and more.

---

### GET /api/servicenow/schema/{table}

Inspect table columns via `sys_dictionary`. Results are session-cached for the
lifetime of the service instance.

**Auth:** MAINTENANCE module

**Response:** `{"result": [{"element": "...", "column_label": "...", "internal_type": "...", ...}]}`

---

### GET /api/servicenow/history/{table}/{sys_id}

Fetch the audit trail for a specific ServiceNow record from `sys_audit`.

**Auth:** MAINTENANCE module

**Path parameters:**

| Param | Description |
|-------|-------------|
| `table` | Source table name |
| `sys_id` | Record sys_id |

**Response:** `{"result": [{"fieldname": "...", "oldvalue": "...", "newvalue": "...", ...}]}`

---

### GET /api/servicenow/aggregate/{table}

Stats API for counts and breakdowns on any table.

**Auth:** MAINTENANCE module

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | string | none | Encoded query string |
| `group_by` | string | none | Comma-separated group-by fields |

**Response:** ServiceNow Stats API result with grouped counts.

---

## Error handling

All endpoints return graceful empty responses when ServiceNow is not configured
or when a query fails:

```json
{"result": [], "count": 0, "error": "ServiceNow not configured"}
```

No endpoint raises an exception to the caller. HTTP status codes from
ServiceNow (401, 404, 5xx) are captured and returned as error messages within
the standard response envelope.

## Related

- [ServiceNow integration guide](../05-integrations/servicenow-integration.md)
