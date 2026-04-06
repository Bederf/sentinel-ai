---
title: "Recommendations API Reference"
type: "api-reference"
status: "complete"
version: "1.2.0"
created: "2026-02-09"
updated: "2026-04-03"
author: "SENTINEL Development Team"
tags: ["api", "recommendations", "optimization", "approval-workflow", "background-jobs"]
domain: "optimization"
audience: "developers|integrators|operators"
complexity: "intermediate"
estimated_read_time: 10
related: ["../08-ai-ml/ai-recommendation-system.md", "../08-ai-ml/background-recommendation-generation.md", "../04-features/72-profile-based-optimization.md"]
---

# Recommendations API Reference

**Base URL:** `http://localhost:9095/api`
**Authentication:** JWT bearer token in `Authorization` header
**Auto-Generation:** Recommendations are generated automatically every 10 minutes. See [Background Recommendation Generation](../08-ai-ml/background-recommendation-generation.md) for details.

---

## Endpoints Overview

### Profile Management (4 endpoints)
- `GET /optimization/settings/{site_id}` - Get site profile configuration
- `PUT /optimization/settings/{site_id}` - Update site profile
- `POST /optimization/profiles` - List available profiles
- `GET /optimization/profiles/{name}` - Get profile details

### Recommendations (4 endpoints)
- `GET /modules/site/{site_id}/recommendations` - Get pending recommendations (returns list directly)
- `POST /recommendations/{rec_id}/approve` - Approve recommendation
- `POST /recommendations/{rec_id}/reject` - Reject recommendation
- `GET /recommendations/{rec_id}` - Get recommendation details

### Analysis (1 endpoint)
- `POST /optimization/analyze` - Run AI optimizer

---

## Detailed Endpoints

### Profile Management

#### GET /optimization/settings/{site_id}
Retrieve the active profile and configuration for a site.

**Parameters:**
- `site_id` (path, required): Site identifier (e.g., "site-002")

**Response:**
```json
{
  "site_id": "site-002",
  "site_name": "Sandton Data Centre",
  "active_profile": "cost_saving",
  "control_tier": "human_in_loop",
  "zone_overrides": [
    {
      "zone_id": "server-room",
      "profile": "comfort_first",
      "reason": "Thermal criticality"
    }
  ],
  "schedule_overrides": [
    {
      "start_time": "06:00",
      "end_time": "18:00",
      "profile": "comfort_first",
      "days": ["MON", "TUE", "WED", "THU", "FRI"]
    }
  ]
}
```

**Status Codes:**
- `200 OK` - Configuration retrieved
- `404 Not Found` - Site not found
- `401 Unauthorized` - Invalid authentication

---

#### PUT /optimization/settings/{site_id}
Update profile configuration for a site.

**Parameters:**
- `site_id` (path, required): Site identifier

**Request Body:**
```json
{
  "active_profile": "cost_saving",
  "control_tier": "auto_execute",
  "zone_overrides": [
    {
      "zone_id": "zone_01",
      "profile": "comfort_first",
      "reason": "Executive area"
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "message": "Profile updated successfully",
  "updated_at": "2026-02-09T14:30:00Z",
  "active_profile": "cost_saving"
}
```

**Validation:**
- `active_profile`: Must be "sweat_assets", "comfort_first", or "cost_saving"
- `control_tier`: Must be "monitor", "human_in_loop", or "auto_execute"
- `zone_overrides[].zone_id`: Must match existing zone in building
- `zone_overrides[].profile`: Must be valid profile name

---

#### POST /optimization/profiles
List available optimization profiles.

**Parameters:** None

**Response:**
```json
{
  "profiles": [
    {
      "name": "sweat_assets",
      "display_name": "Asset Sweating",
      "description": "Maximize equipment utilization, defer replacements",
      "weights": {
        "runtime": 0.40,
        "comfort": 0.15,
        "cost": 0.05,
        "maintenance": 0.20,
        "energy": 0.20
      }
    },
    {
      "name": "comfort_first",
      "display_name": "Comfort First",
      "description": "Maintain tight environment control regardless of cost",
      "weights": {
        "runtime": 0.15,
        "comfort": 0.50,
        "cost": 0.05,
        "maintenance": 0.15,
        "energy": 0.15
      }
    },
    {
      "name": "cost_saving",
      "display_name": "Cost Saving",
      "description": "Minimize operational spend and energy usage",
      "weights": {
        "runtime": 0.15,
        "comfort": 0.07,
        "cost": 0.45,
        "maintenance": 0.03,
        "energy": 0.30
      }
    }
  ]
}
```

---

#### GET /optimization/profiles/{name}
Get detailed information about a specific profile.

**Parameters:**
- `name` (path, required): Profile name ("sweat_assets", "comfort_first", "cost_saving")

**Response:**
```json
{
  "name": "cost_saving",
  "display_name": "Cost Saving",
  "description": "Minimize operational spend and energy usage",
  "weights": {
    "runtime": 0.15,
    "comfort": 0.07,
    "cost": 0.45,
    "maintenance": 0.03,
    "energy": 0.30
  },
  "thresholds": {
    "hvac_temp_min": 16,
    "hvac_temp_max": 28,
    "empty_zone_setback_c": 3.0,
    "low_occ_setback_c": 1.5,
    "lighting_min_lux": 300,
    "lighting_max_lux": 500,
    "empty_zone_lighting_percent": 20,
    "low_occ_lighting_percent": 50,
    "generator_usage": "standby"
  },
  "use_cases": [
    "Light commercial (shops, warehouses)",
    "Cost-conscious facilities",
    "Load shedding scenarios"
  ]
}
```

---

### Recommendations

#### GET /recommendations/{site_id}
Get pending recommendations requiring operator action (Tier 2 mode).

**Parameters:**
- `site_id` (path, required): Site identifier
- `limit` (query, optional): Max recommendations to return (default: 10, max: 50)
- `risk_level` (query, optional): Filter by risk level ("low", "medium", "high", "critical")

**Response:**
```json
{
  "site_id": "site-002",
  "total_pending": 3,
  "recommendations": [
    {
      "id": "rec_20260209_001",
      "site_id": "site-002",
      "timestamp": "2026-02-09T14:15:00Z",
      "action_type": "hvac_setpoint_change",
      "risk_level": "low",
      "target_equipment": "zone_01",
      "action": {
        "point": "zone_setpoint_c",
        "value": 24.0
      },
      "reason": "Cost profile: Raise setpoint +2°C during peak hours to reduce cooling load",
      "expected_impact": {
        "cost_zar": 120,
        "energy_kwh": -15,
        "comfort_delta": -2,
        "equipment_health": 0
      },
      "confidence": "high",
      "profile": "cost_saving",
      "multi_objective_score": 0.92,
      "status": "pending",
      "requires_approval": false,
      "created_at": "2026-02-09T14:15:00Z",
      "expires_at": "2026-02-09T18:15:00Z"
    }
  ]
}
```

**Status Codes:**
- `200 OK` - Recommendations retrieved
- `404 Not Found` - Site not found

---

#### POST /recommendations/{rec_id}/approve
Approve a pending recommendation for execution.

**Parameters:**
- `rec_id` (path, required): Recommendation identifier
- Authorization header required

**Request Body:**
```json
{
  "reason": "Approved by operations team - within acceptable parameters"
}
```

**Response:**
```json
{
  "success": true,
  "recommendation": {
    "id": "rec_20260209_001",
    "status": "executed",
    "approved_by": "operator_123",
    "approval_reason": "Approved by operations team - within acceptable parameters",
    "executed_at": "2026-02-09T14:16:00Z",
    "execution_result": {
      "success": true,
      "device": "zone_01",
      "action": "setpoint_changed",
      "previous_value": 22.0,
      "new_value": 24.0,
      "timestamp": "2026-02-09T14:16:00Z"
    }
  }
}
```

**Errors:**
```json
{
  "error": "INVALID_STATUS",
  "message": "Recommendation already approved or rejected",
  "recommendation_id": "rec_20260209_001"
}
```

**Workflow After Approval:**
1. Recommendation status → "EXECUTED"
2. Action applied to BMS/device
3. Outcome verification scheduled (T+30min)
4. Audit trail recorded

---

#### POST /recommendations/{rec_id}/reject
Reject a pending recommendation (triggers learning).

**Parameters:**
- `rec_id` (path, required): Recommendation identifier
- Authorization header required

**Request Body:**
```json
{
  "reason": "Zone too cold already, reject temperature reduction"
}
```

**Response:**
```json
{
  "success": true,
  "recommendation": {
    "id": "rec_20260209_001",
    "status": "rejected",
    "rejection_reason": "Zone too cold already, reject temperature reduction",
    "rejected_at": "2026-02-09T14:16:00Z"
  },
  "learning": {
    "pattern_detected": false,
    "rejection_count": 1,
    "threshold": 3,
    "message": "Rejection recorded. Will trigger learning after 3 similar rejections."
  }
}
```

**Learning Trigger:**
When 3+ rejections of same action type detected in 30 days:
```json
{
  "pattern_detected": true,
  "constraint_created": {
    "zone_id": "zone_01",
    "constraint_type": "min_setpoint",
    "value": 22.0,
    "reason": "Operator rejected 3 similar actions"
  },
  "message": "Constraint added: min_setpoint=22°C for zone_01"
}
```

---

#### GET /recommendations/{rec_id}
Get detailed information about a specific recommendation, including execution outcome.

**Parameters:**
- `rec_id` (path, required): Recommendation identifier

**Response (Pending):**
```json
{
  "id": "rec_20260209_001",
  "site_id": "site-002",
  "status": "pending",
  "action_type": "hvac_setpoint_change",
  "risk_level": "low",
  "target_equipment": "zone_01",
  "action": {
    "point": "zone_setpoint_c",
    "value": 24.0
  },
  "reason": "Cost profile: Raise setpoint +2°C",
  "expected_impact": {
    "cost_zar": 120,
    "energy_kwh": -15,
    "comfort_delta": -2
  },
  "confidence": "high",
  "profile": "cost_saving",
  "multi_objective_score": 0.92,
  "created_at": "2026-02-09T14:15:00Z",
  "expires_at": "2026-02-09T18:15:00Z"
}
```

**Response (Executed with Outcome):**
```json
{
  "id": "rec_20260209_001",
  "site_id": "site-002",
  "status": "executed",
  "action_type": "hvac_setpoint_change",
  "target_equipment": "zone_01",
  "action": {
    "point": "zone_setpoint_c",
    "value": 24.0
  },
  "reason": "Cost profile: Raise setpoint +2°C",
  "expected_impact": {
    "cost_zar": 120,
    "energy_kwh": -15,
    "comfort_delta": -2
  },
  "profile": "cost_saving",
  "multi_objective_score": 0.92,
  "executed_at": "2026-02-09T14:16:00Z",
  "execution_result": {
    "success": true,
    "previous_value": 22.0,
    "new_value": 24.0
  },
  "outcome": {
    "verified_at": "2026-02-09T14:46:00Z",
    "predicted": {
      "temperature_c": 24.0,
      "cost_zar": 120,
      "energy_kwh": -15
    },
    "actual": {
      "temperature_c": 23.8,
      "cost_zar": 118,
      "energy_kwh": -14.5
    },
    "accuracy": 0.88,
    "accuracy_breakdown": {
      "temperature_accuracy": 0.90,
      "cost_accuracy": 0.85
    }
  }
}
```

---

### Analysis

#### POST /optimization/analyze
Run AI optimizer to generate recommendations for a site with current profile.

**ML Context Injection (Phase 132):** Before building Claude's prompt, this endpoint gathers outputs from all active ML models via `_gather_ml_context()`:
- LSTM 24/48/72h forecasts per equipment type
- Anomaly detection scores above 0.5 threshold
- Fault classification probabilities above 0.4 confidence
- Health trend slopes for degrading equipment
- Building-level features (EUI, Base Load Index, CDD, Efficiency Score)

This enables predictive recommendations based on future equipment behaviour. See [ML Context Injection](../08-ai-ml/ai-recommendation-system.md#ml-context-injection-phase-132) for details.

**Parameters:** None (all in request body)

**Request Body:**
```json
{
  "site_id": "site-002"
}
```

**Response:**
```json
{
  "site_id": "site-002",
  "profile": "cost_saving",
  "profile_applied": true,
  "timestamp": "2026-02-09T14:30:00Z",
  "recommendations": [
    {
      "id": "rec_20260209_001",
      "action_type": "hvac_setpoint_change",
      "target_equipment": "zone_01",
      "action": {
        "point": "zone_setpoint_c",
        "value": 24.0
      },
      "reason": "Cost profile (45% weight): Raise setpoint +2°C during peak hours to reduce cooling load",
      "expected_impact": {
        "cost_zar": 120,
        "energy_kwh": -15,
        "comfort_delta": -2,
        "equipment_health": 0
      },
      "confidence": "high",
      "risk_level": "low",
      "profile": "cost_saving",
      "multi_objective_score": 0.92,
      "status": "auto_executed"
    },
    {
      "id": "rec_20260209_002",
      "action_type": "lighting_dim",
      "target_equipment": "zone_01_lights",
      "action": {
        "point": "dali_level",
        "value": 50
      },
      "reason": "Low occupancy detected - Cost profile reduces lighting to 50%",
      "expected_impact": {
        "cost_zar": 45,
        "energy_kwh": -8,
        "comfort_delta": 0,
        "equipment_health": 0
      },
      "confidence": "high",
      "risk_level": "low",
      "profile": "cost_saving",
      "multi_objective_score": 0.85,
      "status": "auto_executed"
    }
  ],
  "scoring_summary": {
    "total_recommendations": 2,
    "top_score": 0.92,
    "average_score": 0.885,
    "weighted_by": "cost_saving"
  }
}
```

**Profile Injection in Prompt:**
The AI receives context including:
- Site equipment inventory (categorized by type)
- Current building conditions
- Active profile weights and thresholds
- Zone overrides and constraints from learning

---

## Error Responses

### Common Error Codes

**400 Bad Request**
```json
{
  "error": "INVALID_PROFILE",
  "message": "Profile 'invalid_name' does not exist",
  "valid_profiles": ["sweat_assets", "comfort_first", "cost_saving"]
}
```

**401 Unauthorized**
```json
{
  "error": "UNAUTHORIZED",
  "message": "Invalid or missing authorization token"
}
```

**404 Not Found**
```json
{
  "error": "NOT_FOUND",
  "message": "Recommendation 'rec_xyz' not found"
}
```

**409 Conflict**
```json
{
  "error": "INVALID_STATUS",
  "message": "Cannot approve recommendation with status 'rejected'",
  "current_status": "rejected"
}
```

**422 Unprocessable Entity**
```json
{
  "error": "VALIDATION_ERROR",
  "message": "Zone override validation failed",
  "details": [
    {
      "field": "zone_overrides[0].zone_id",
      "message": "Zone 'invalid_zone' not found in building"
    }
  ]
}
```

**500 Internal Server Error**
```json
{
  "error": "INTERNAL_ERROR",
  "message": "Error executing recommendation",
  "request_id": "req_abc123"
}
```

---

## Rate Limiting

API endpoints are rate-limited per user:
- **Recommendations:** 60 requests/minute
- **Profiles:** 120 requests/minute
- **Analysis:** 10 requests/minute (AI intensive)

Rate limit headers:
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1707480600
```

---

## Webhooks

Recommendations can trigger webhooks for real-time notifications:

### Webhook Events

**recommendation.created**
```json
{
  "event": "recommendation.created",
  "recommendation_id": "rec_20260209_001",
  "site_id": "site-002",
  "action_type": "hvac_setpoint_change",
  "status": "pending",
  "timestamp": "2026-02-09T14:15:00Z"
}
```

**recommendation.executed**
```json
{
  "event": "recommendation.executed",
  "recommendation_id": "rec_20260209_001",
  "site_id": "site-002",
  "executed_at": "2026-02-09T14:16:00Z",
  "success": true
}
```

**recommendation.rejected**
```json
{
  "event": "recommendation.rejected",
  "recommendation_id": "rec_20260209_001",
  "site_id": "site-002",
  "rejected_at": "2026-02-09T14:16:00Z",
  "reason": "Zone too cold already"
}
```

To subscribe to webhooks: `POST /api/notifications/webhooks`

---

## Examples

### Example 1: Switch Profile to Cost Saving
```bash
curl -X PUT http://localhost:9095/api/optimization/settings/site-002 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "active_profile": "cost_saving",
    "control_tier": "auto_execute"
  }'
```

### Example 2: Get Pending Recommendations
```bash
curl -X GET "http://localhost:9095/api/recommendations/site-002?limit=5" \
  -H "Authorization: Bearer $TOKEN"
```

### Example 3: Approve Recommendation
```bash
curl -X POST http://localhost:9095/api/recommendations/rec_20260209_001/approve \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Approved by ops"}'
```

### Example 4: Run Optimizer
```bash
curl -X POST http://localhost:9095/api/optimization/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"site_id": "site-002"}'
```

---

### Agent Trigger

#### POST /recommendations/{site_id}/process-pending
Trigger the LangGraph recommendation agent to process pending recommendations for a site.

The agent validates, assesses impact, checks schedule conflicts, routes through the tier engine, and either auto-executes (Tier 3), requests approval (Tier 2), or logs as advisory (Tier 1).

**Parameters:**
- `site_id` (path, required): Site identifier (e.g., "S002")

**Request Body:**
```json
{
  "channel": "system",
  "trigger": "manual"
}
```

| Field | Type | Default | Values |
|-------|------|---------|--------|
| `channel` | string | `"system"` | `"system"`, `"whatsapp"`, `"telegram"`, `"chat"` |
| `trigger` | string | `"manual"` | `"manual"`, `"scheduled"`, `"health_alert"` |

**Response (Tier 1 Advisory):**
```json
{
  "success": true,
  "site_id": "S002",
  "response": "[ADVISORY] S002-FCU-201 (Level 2, Zone A)\nAction: hvac_setpoint_change\n...",
  "tier": "tier1",
  "recommendation_id": "rec-abc123",
  "needs_input": false,
  "processing_complete": true
}
```

**Response (Tier 2 Approval Required):**
```json
{
  "success": true,
  "site_id": "S002",
  "response": "🔧 *Approval Required*\n\nEquipment: S002-FCU-201...\n\nReply: APPROVE rec-abc1 or REJECT rec-abc1 <reason>",
  "tier": "tier2",
  "recommendation_id": "rec-abc123",
  "needs_input": true,
  "processing_complete": false
}
```

**Response (Tier 3 Auto-Executed):**
```json
{
  "success": true,
  "site_id": "S002",
  "response": "✅ Auto-executed: S002-FCU-201 hvac_setpoint_change\nCOV verified: true",
  "tier": "tier3",
  "recommendation_id": "rec-abc123",
  "needs_input": false,
  "processing_complete": true
}
```

**Response (No Pending):**
```json
{
  "success": true,
  "site_id": "S002",
  "response": "Processing complete.",
  "tier": null,
  "recommendation_id": null,
  "needs_input": false,
  "processing_complete": true
}
```

**Rate Limit:** 10 requests/minute

**Status Codes:**
- `200 OK` — Processing complete or approval requested
- `501 Not Implemented` — LangGraph not installed
- `500 Internal Server Error` — Agent processing error

**Example:**
```bash
curl -X POST "http://localhost:9095/api/recommendations/S002/process-pending" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel": "whatsapp", "trigger": "manual"}'
```

---

## See Also

- [Profile-Based Optimization Architecture](../02-architecture/profile-based-optimization.md)
- [Module Connectivity](../02-architecture/module-connectivity.md)
- [AI Recommendation System](../08-ai-ml/ai-recommendation-system.md) - Full agent architecture
- [Recommendation Agent Feature Doc](../04-features/recommendation-agent.md)
- [Authentication](auth.md)

---

**Document Control**

| Revision | Date | Change | Author |
|----------|------|--------|--------|
| 1.1 | 2026-02-19 | Added process-pending agent trigger endpoint | SENTINEL Team |
| 1.0 | 2026-02-09 | Initial publication | SENTINEL Team |
