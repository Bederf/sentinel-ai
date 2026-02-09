---
title: "Module Integration API Reference"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-09"
updated: "2026-02-09"
author: "Sentinel Development Team"
tags: ["api", "modules", "integration", "rest"]
domain: "api"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 15
---

# Module Integration API Reference

Complete REST API reference for querying, managing, and monitoring module integrations.

## Base URL

```
http://localhost:9095/api/modules
```

## Overview

The Module Integration API provides endpoints to:
- Query active modules and integrations at a site
- Activate/deactivate modules (triggers auto-integration)
- Enable/disable specific integration links
- Monitor integration performance and telemetry
- Get integration summaries and status

---

## Endpoints

### Query Active Integrations

**Endpoint:**
```
GET /api/modules/site/{site_id}/integrations
```

**Description:** Get all cross-module integration links at a site, with status and configuration.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `site_id` | string | Yes | Site identifier (e.g., `site-002`) |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled_only` | boolean | false | Filter to only enabled links |
| `source_module` | string | - | Filter by source module type |
| `target_module` | string | - | Filter by target module type |

**Response:** (200 OK)
```json
{
  "site_id": "site-002",
  "total_links": 12,
  "active_links": 12,
  "integrations": [
    {
      "link_id": "sandton-hvac_energy_loadshed",
      "source_module": "energy",
      "target_module": "hvac",
      "integration_type": "hvac_energy_loadshed",
      "name": "HVAC Load Shedding",
      "description": "Reduce HVAC load when on generator power",
      "enabled": true,
      "last_triggered": "2026-02-09T14:23:00Z",
      "trigger_count": 47,
      "config": {}
    },
    {
      "link_id": "sandton-security_hvac_occupancy",
      "source_module": "security",
      "target_module": "hvac",
      "integration_type": "security_hvac_occupancy",
      "name": "Occupancy-Based HVAC",
      "description": "Adjust HVAC based on access control occupancy",
      "enabled": true,
      "last_triggered": "2026-02-09T12:45:00Z",
      "trigger_count": 186,
      "config": {
        "empty_setpoint_offset_c": 2.0,
        "low_occupancy_threshold": 3,
        "low_occupancy_offset_c": 1.0
      }
    }
  ]
}
```

**Error Responses:**
```json
// 404 Not Found
{
  "detail": "Site not found"
}

// 400 Bad Request
{
  "detail": "Invalid filter parameters"
}
```

---

### Activate Module

**Endpoint:**
```
POST /api/modules/activate
```

**Description:** Activate a module at a site. Automatically creates integration links if target modules are active.

**Request Body:**
```json
{
  "site_id": "site-002",
  "module_type": "solar",
  "config": {
    "bess_enabled": true,
    "compliance_monitoring": true
  }
}
```

**Body Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `site_id` | string | Yes | Site identifier |
| `module_type` | string | Yes | Module type (hvac, energy, lighting, security, solar, ml, etc.) |
| `config` | object | No | Module configuration (module-specific) |

**Response:** (201 Created)
```json
{
  "instance_id": "sandton-solar-002",
  "site_id": "site-002",
  "module_type": "solar",
  "status": "active",
  "activated_at": "2026-02-09T15:00:00Z",
  "health_score": 100.0,
  "new_integrations_created": [
    {
      "link_id": "sandton-energy_solar_generation",
      "source_module": "solar",
      "target_module": "energy",
      "integration_type": "energy_solar_generation",
      "enabled": true
    },
    {
      "link_id": "sandton-solar_generator_coordination",
      "source_module": "solar",
      "target_module": "energy",
      "integration_type": "solar_generator_coordination",
      "enabled": true
    }
  ]
}
```

**Error Responses:**
```json
// 409 Conflict - Module already active
{
  "detail": "Module solar already active at site-002"
}

// 400 Bad Request - Invalid module type
{
  "detail": "Invalid module type: unknown_module"
}

// 404 Not Found
{
  "detail": "Site not found"
}
```

---

### Deactivate Module

**Endpoint:**
```
POST /api/modules/site/{site_id}/deactivate/{module_type}
```

**Description:** Deactivate a module and all its associated integration links.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `site_id` | string | Yes | Site identifier |
| `module_type` | string | Yes | Module type to deactivate |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cascade` | boolean | true | Also deactivate modules that depend on this one |

**Response:** (200 OK)
```json
{
  "instance_id": "sandton-solar-002",
  "module_type": "solar",
  "status": "inactive",
  "deactivated_at": "2026-02-09T15:30:00Z",
  "disabled_integrations": [
    {
      "link_id": "sandton-energy_solar_generation",
      "integration_type": "energy_solar_generation",
      "reason": "Source module deactivated"
    },
    {
      "link_id": "sandton-solar_generator_coordination",
      "integration_type": "solar_generator_coordination",
      "reason": "Source module deactivated"
    },
    {
      "link_id": "sandton-sustainability_solar_green",
      "integration_type": "sustainability_solar_green",
      "reason": "Source module deactivated"
    }
  ],
  "dependent_modules_affected": [
    {
      "module_type": "sustainability",
      "dependent_links": 1
    }
  ]
}
```

**Error Responses:**
```json
// 404 Not Found
{
  "detail": "Module not found or not active"
}

// 409 Conflict - Other modules depend on this
{
  "detail": "Cannot deactivate. Modules sustainability depend on solar module. Use cascade=true to deactivate dependent modules."
}
```

---

### Toggle Integration Link

**Endpoint:**
```
POST /api/modules/site/{site_id}/integration/{link_id}/toggle
```

**Description:** Manually enable or disable a specific integration link.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `site_id` | string | Yes | Site identifier |
| `link_id` | string | Yes | Integration link ID |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | boolean | - | Target state (if not provided, toggles) |

**Response:** (200 OK)
```json
{
  "link_id": "sandton-hvac_energy_loadshed",
  "source_module": "energy",
  "target_module": "hvac",
  "integration_type": "hvac_energy_loadshed",
  "enabled": false,
  "previous_state": true,
  "changed_at": "2026-02-09T15:35:00Z"
}
```

**Error Responses:**
```json
// 404 Not Found
{
  "detail": "Integration link not found"
}

// 400 Bad Request
{
  "detail": "Link cannot be disabled: target module requires this integration"
}
```

---

### Get Integration Telemetry

**Endpoint:**
```
GET /api/modules/site/{site_id}/integration/{link_id}/telemetry
```

**Description:** Get performance metrics and telemetry for an integration link.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `site_id` | string | Yes | Site identifier |
| `link_id` | string | Yes | Integration link ID |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hours` | integer | 24 | Look-back period in hours |
| `include_history` | boolean | false | Include hourly breakdown |

**Response:** (200 OK)
```json
{
  "link_id": "sandton-hvac_energy_loadshed",
  "integration_type": "hvac_energy_loadshed",
  "period_hours": 24,
  "metrics": {
    "total_triggers": 47,
    "successful_actions": 46,
    "failed_actions": 1,
    "success_rate": 97.9,
    "avg_latency_ms": 145.2,
    "last_trigger": "2026-02-09T14:23:00Z",
    "first_trigger": "2026-02-08T14:24:00Z"
  },
  "hourly_breakdown": [
    {
      "hour": "2026-02-08T14:00:00Z",
      "triggers": 2,
      "successes": 2,
      "failures": 0,
      "avg_latency_ms": 138.5
    },
    {
      "hour": "2026-02-08T15:00:00Z",
      "triggers": 3,
      "successes": 3,
      "failures": 0,
      "avg_latency_ms": 142.1
    }
  ],
  "alerts": [
    {
      "timestamp": "2026-02-09T10:15:00Z",
      "severity": "warning",
      "message": "Integration latency high (245ms > 200ms threshold)"
    }
  ]
}
```

**Error Responses:**
```json
// 404 Not Found
{
  "detail": "Integration link or telemetry data not found"
}

// 400 Bad Request
{
  "detail": "Invalid hours parameter (must be 1-720)"
}
```

---

### Get Integration Summary

**Endpoint:**
```
GET /api/modules/site/{site_id}/integration-summary
```

**Description:** Get high-level summary of all module integrations at a site.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `site_id` | string | Yes | Site identifier |

**Response:** (200 OK)
```json
{
  "site_id": "site-002",
  "site_name": "Sandton Data Centre",
  "summary": {
    "total_modules": 14,
    "active_modules": 14,
    "total_integrations": 12,
    "enabled_integrations": 12,
    "disabled_integrations": 0,
    "auto_integration_enabled": true,
    "ai_enabled": true
  },
  "modules": [
    {
      "module_type": "hvac",
      "status": "active",
      "health_score": 100.0,
      "integration_count": 5,
      "integrations_as_target": [
        "hvac_energy_loadshed",
        "hvac_energy_demand",
        "security_hvac_occupancy",
        "ml_hvac_predictive"
      ],
      "integrations_as_source": []
    },
    {
      "module_type": "energy",
      "status": "active",
      "health_score": 95.0,
      "integration_count": 6,
      "integrations_as_target": [
        "energy_solar_generation",
        "solar_generator_coordination",
        "ml_energy_anomaly"
      ],
      "integrations_as_source": [
        "hvac_energy_loadshed",
        "hvac_energy_demand",
        "energy_lighting_loadshed"
      ]
    }
  ],
  "integration_matrix": {
    "energy->hvac": {
      "links": 2,
      "status": "active"
    },
    "energy->lighting": {
      "links": 1,
      "status": "active"
    },
    "solar->energy": {
      "links": 2,
      "status": "active"
    },
    "security->hvac": {
      "links": 1,
      "status": "active"
    },
    "security->lighting": {
      "links": 1,
      "status": "active"
    },
    "ml->hvac": {
      "links": 1,
      "status": "active"
    },
    "ml->energy": {
      "links": 1,
      "status": "active"
    },
    "sustainability->energy": {
      "links": 1,
      "status": "active"
    },
    "sustainability->solar": {
      "links": 1,
      "status": "active"
    },
    "water->sustainability": {
      "links": 1,
      "status": "active"
    }
  }
}
```

**Error Responses:**
```json
// 404 Not Found
{
  "detail": "Site not found"
}
```

---

### Get All Module Types

**Endpoint:**
```
GET /api/modules/types
```

**Description:** Get reference information about all available module types.

**Response:** (200 OK)
```json
{
  "module_types": [
    {
      "type": "hvac",
      "category": "building_systems",
      "name": "HVAC Control & Monitoring",
      "description": "Zone temperature control, setpoint management, comfort optimization",
      "cost_model": "paid_addon",
      "capabilities": [
        "zone_temperature_control",
        "setpoint_management",
        "occupancy_based_optimization",
        "demand_response"
      ],
      "can_be_source_of": [],
      "can_be_target_of": [
        "hvac_energy_loadshed",
        "hvac_energy_demand",
        "security_hvac_occupancy",
        "ml_hvac_predictive"
      ]
    },
    {
      "type": "energy",
      "category": "building_systems",
      "name": "Power & Load Management",
      "description": "Generator/UPS/ATS monitoring, load shedding, demand response",
      "cost_model": "paid_addon",
      "capabilities": [
        "generator_monitoring",
        "ats_coordination",
        "load_shedding",
        "demand_response"
      ],
      "can_be_source_of": [
        "hvac_energy_loadshed",
        "hvac_energy_demand",
        "energy_lighting_loadshed",
        "energy_solar_generation",
        "solar_generator_coordination"
      ],
      "can_be_target_of": [
        "energy_solar_generation",
        "solar_generator_coordination",
        "ml_energy_anomaly",
        "sustainability_energy_carbon"
      ]
    }
  ]
}
```

---

## Common Use Cases

### Use Case 1: Check Integration Status Before Activating Module

**Scenario:** Client wants to activate Solar module. First check what integrations will be created.

**Steps:**
1. Get current active modules: `GET /api/modules/site/{site_id}/integrations`
2. Review which modules are active
3. Call `POST /api/modules/activate` with `module_type=solar`
4. Review `new_integrations_created` in response

**Example Request:**
```bash
curl -X POST http://localhost:9095/api/modules/activate \
  -H "Content-Type: application/json" \
  -d '{
    "site_id": "site-002",
    "module_type": "solar",
    "config": {"bess_enabled": true}
  }'
```

**Expected Response Shows:**
- Two new integration links created (energy_solar_generation, solar_generator_coordination)
- Integration links automatically enabled

---

### Use Case 2: Troubleshoot Slow Integration

**Scenario:** Integration link running slow, need to diagnose.

**Steps:**
1. Get telemetry: `GET /api/modules/site/{site_id}/integration/{link_id}/telemetry?hours=24`
2. Review latency and failure rates
3. If failure rate high, check logs for errors
4. If latency high, may need to disable link temporarily: `POST /api/modules/site/{site_id}/integration/{link_id}/toggle?enabled=false`

**Example Request:**
```bash
curl http://localhost:9095/api/modules/site/site-002/integration/sandton-hvac_energy_loadshed/telemetry?hours=24
```

**Expected Response Shows:**
- Hourly breakdown of integration performance
- Any alerts or warnings during the period

---

### Use Case 3: Disable Single Integration (Keep Modules Active)

**Scenario:** Security-HVAC occupancy integration causing false positives. Disable just this link while keeping both modules active.

**Request:**
```bash
curl -X POST http://localhost:9095/api/modules/site/site-002/integration/sandton-security_hvac_occupancy/toggle \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

**Result:**
- Integration link disabled
- Both Security and HVAC modules still active
- All other integrations continue working

---

### Use Case 4: Get Full Site Integration Picture

**Scenario:** New operations manager wants to understand which systems are connected.

**Request:**
```bash
curl http://localhost:9095/api/modules/site/site-002/integration-summary
```

**Shows:**
- All 14 modules and their status
- 12 active integrations in matrix format
- Health scores per module
- Capabilities of each module

---

## Error Handling

### Common Errors

| Status | Code | Message | Solution |
|--------|------|---------|----------|
| 400 | INVALID_PARAMETER | Invalid module type | Use `/api/modules/types` to get valid types |
| 404 | NOT_FOUND | Site not found | Check site_id is correct |
| 409 | CONFLICT | Module already active | Use GET to check before POST |
| 429 | RATE_LIMITED | Too many requests | Implement backoff |
| 500 | INTERNAL_ERROR | Integration trigger failed | Check logs, may retry |

### Retry Strategy

Implement exponential backoff for 5xx errors:
```python
max_retries = 3
base_delay = 1  # seconds

for attempt in range(max_retries):
    try:
        response = requests.post(url, json=data)
        if response.status_code < 500:
            break
    except Exception as e:
        delay = base_delay * (2 ** attempt)
        time.sleep(delay)
```

---

## Rate Limits

| Endpoint | Requests/Minute | Requests/Hour |
|----------|-----------------|---------------|
| GET (queries) | 300 | 5000 |
| POST (writes) | 60 | 1000 |
| Integration activation | 10 | 100 |
| Telemetry queries | 100 | 2000 |

Rate limit headers:
```
X-RateLimit-Limit: 300
X-RateLimit-Remaining: 298
X-RateLimit-Reset: 1707501234
```

---

## See Also

- [Module Connectivity & Cross-System Integration](../02-architecture/module-connectivity.md) - Business view of integrations
- [Module System](../02-architecture/module-system.md) - Architecture and module lifecycle
- [Module Registry](../13-modules/module-registry.md) - Internal implementation details

---

**Document Control**

| Revision | Date | Change | Author |
|----------|------|--------|--------|
| 1.0 | 2026-02-09 | Initial publication | Sentinel Team |
