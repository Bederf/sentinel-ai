---
title: "Dashboard Generator API"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-03-01"
updated: "2026-03-01"
author: "Sentinel Development Team"
tags: ["api", "dashboard", "equipment-classification", "onboarding"]
related: ["../04-features/141-auto-dashboard-generator.md"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 8
---

# Dashboard Generator API

REST endpoints for auto-generating tailored dashboard configurations from discovered equipment. All endpoints require authentication via `get_current_user`. Registered in the analytics registrar.

**Base path:** `/api/dashboard-generator`

## Endpoints

### POST /generate/{site_id}

Generate a complete dashboard configuration for a site.

**Path parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| site_id | string | yes | Site code (e.g., `site-002`) |

**Request body** (optional):

```json
{
  "equipment_list": [
    {
      "code": "S002-CHILLER-B1-001",
      "type": "chiller",
      "name": "Chiller 1",
      "status": "running",
      "health_score": 92
    }
  ]
}
```

If `equipment_list` is omitted, the service loads equipment from the repository using 3-tier fallback (Supabase, JSON files, empty list).

**Response (200):**

```json
{
  "site_id": "site-002",
  "status": "generated",
  "equipment_summary": {
    "chiller": 2,
    "ahu": 1,
    "fcu": 8,
    "solar_inverter": 4,
    "bess": 1,
    "meter_energy": 2
  },
  "dashboard_cards": [
    {
      "card_id": "site-002-health-score",
      "title": "Building Health Score",
      "card_type": "gauge",
      "domain": "overview",
      "priority": 1,
      "equipment_classes": [],
      "config": {
        "metric": "health_score",
        "max_value": 100,
        "unit": "%"
      }
    }
  ],
  "monitoring_rules": [
    {
      "rule_id": "site-002-chiller-high-load",
      "name": "Chiller High Load",
      "description": "Chiller load exceeds 85% for sustained period",
      "equipment_class": "chiller",
      "metric": "load_pct",
      "condition": "gt",
      "threshold": 85.0,
      "severity": "warning",
      "evaluation_window": "15m",
      "cooldown_minutes": 60
    }
  ],
  "health_weights": {
    "chiller": 28.5,
    "ahu": 13.4,
    "fcu": 18.9,
    "solar_inverter": 26.8,
    "bess": 13.4
  },
  "module_suggestions": [
    {
      "module": "hvac_control",
      "reason": "Chiller staging and setpoint optimization for energy savings",
      "savings_hint": "5-15% reduction in chiller energy consumption",
      "triggered_by": "chiller",
      "equipment_count": 2
    }
  ],
  "ai_context": "Site site-002 has 18 equipment items discovered.\n\nHVAC: 2 chiller, 1 ahu, 8 fcu\nSolar/BESS: 4 solar_inverter, 1 bess\nEnergy: 2 meter_energy"
}
```

**Error (500):**

```json
{
  "detail": "Dashboard generation failed"
}
```

---

### POST /preview/{site_id}

Preview dashboard for a given equipment list. Same output as `/generate` with an added `"preview": true` field. Used by the BMS Connection Wizard to show what dashboards will look like before committing.

**Path parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| site_id | string | yes | Site code |

**Request body** (required):

```json
{
  "equipment_list": [
    {"code": "S002-FCU-101", "type": "fcu"},
    {"code": "S002-AHU-B1-001"}
  ]
}
```

**Response (200):**

Same structure as `/generate` with `"preview": true` added at top level.

---

### POST /classify

Classify an equipment list without generating a full dashboard. Returns classified items with summary counts.

**Request body** (required):

```json
{
  "equipment_list": [
    {"code": "S002-CHILLER-B1-001"},
    {"code": "S002-INV-R-001"},
    {"code": "S002-MTR-W-001"},
    {"code": "UNKNOWN-DEVICE-X"}
  ]
}
```

**Response (200):**

```json
{
  "items": [
    {"code": "S002-CHILLER-B1-001", "type": null, "equipment_class": "chiller"},
    {"code": "S002-INV-R-001", "type": null, "equipment_class": "solar_inverter"},
    {"code": "S002-MTR-W-001", "type": null, "equipment_class": "meter_water"},
    {"code": "UNKNOWN-DEVICE-X", "type": null, "equipment_class": "unknown"}
  ],
  "summary": {
    "chiller": 1,
    "solar_inverter": 1,
    "meter_water": 1,
    "unknown": 1
  },
  "total": 4
}
```

---

### GET /suggestions/{site_id}

Get module upgrade suggestions for a site. Runs full generation internally but returns only the suggestions array.

**Path parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| site_id | string | yes | Site code |

**Response (200):**

```json
{
  "site_id": "site-002",
  "suggestions": [
    {
      "module": "hvac_control",
      "reason": "Chiller staging and setpoint optimization for energy savings",
      "savings_hint": "5-15% reduction in chiller energy consumption",
      "triggered_by": "chiller",
      "equipment_count": 2
    },
    {
      "module": "solar",
      "reason": "Solar performance monitoring, curtailment optimization, and grid export management",
      "savings_hint": "Maximize self-consumption, reduce grid export losses",
      "triggered_by": "solar_inverter",
      "equipment_count": 4
    }
  ]
}
```

## Request Models

### EquipmentItem

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| code | string | yes | Equipment code (e.g., `S002-CHILLER-B1-001`) |
| type | string | no | Explicit type string (e.g., `chiller`) |
| name | string | no | Equipment display name |
| status | string | no | Current status |
| health_score | integer | no | Current health score (0-100) |

## Response Models

### DashboardCard

| Field | Type | Description |
|-------|------|-------------|
| card_id | string | Unique card identifier (e.g., `site-002-chiller-status`) |
| title | string | Card display title |
| card_type | string | One of: `kpi`, `chart`, `status_grid`, `gauge`, `list` |
| domain | string | Functional domain (e.g., `hvac`, `solar`, `overview`) |
| priority | integer | Display order (lower = higher priority) |
| equipment_classes | string[] | Equipment classes this card covers |
| config | object | Card-specific configuration |

### MonitoringRule

| Field | Type | Description |
|-------|------|-------------|
| rule_id | string | Unique rule identifier |
| name | string | Rule display name |
| description | string | Human-readable description |
| equipment_class | string | Equipment class this rule applies to |
| metric | string | Metric to evaluate |
| condition | string | One of: `gt`, `lt`, `eq`, `ne`, `change` |
| threshold | number | Threshold value |
| severity | string | One of: `critical`, `warning`, `info` |
| evaluation_window | string | Time window (e.g., `5m`, `15m`, `1h`) |
| cooldown_minutes | integer | Minimum minutes between alerts |

## Event-Driven Triggers

The dashboard generator also runs automatically via event bus subscribers:

| Event | Result |
|-------|--------|
| `system.site_onboarded` | Full dashboard generation, emits `system.dashboard_generated` and `system.module_suggested` |
| `system.equipment_discovered` | Dashboard regeneration for the affected site |

See [Auto-Dashboard Generator](../04-features/141-auto-dashboard-generator.md) for event subscriber details.

## Related Documentation

- [Auto-Dashboard Generator Feature Spec](../04-features/141-auto-dashboard-generator.md) -- classification rules, card templates, monitoring rule defaults
- [Event Bus Architecture](../02-architecture/event-bus-architecture.md) -- pub/sub event system
