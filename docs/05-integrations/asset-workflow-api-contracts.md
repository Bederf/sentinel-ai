---
title: "SENTINEL Workflow Integration - API Contracts"
type: "spec"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# SENTINEL Workflow Integration - API Contracts

**Date:** 2026-02-08
**Phase:** 53 - SENTINEL Asset Management Workflow Integration
**Version:** 1.0

## Overview

This document defines the REST API contracts for cross-system communication in the SENTINEL asset management workflow.

## Phase 53-01 Integration Notes

- Critical/safety inspection deficiencies auto-trigger workflow work orders via `/api/inspection/deficiencies`.
- Technician work order completion auto-triggers repair-completed workflow via `/api/work-orders/technician/{id}/complete`.
- Baseline deviation workflow remains wired in `/api/baselines/{equipment_id}/compare`.

## Conventions

- **Base URL:** `http://localhost:9095/api`
- **Content-Type:** `application/json`
- **Authentication:** Bearer token (for production)
- **Rate Limiting:** None (demo scope)
- **Error Format:** Unified error response structure

## Unified Error Response

All endpoints return errors in this format:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {
      "field": "Additional context"
    }
  }
}
```

## Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `NOT_FOUND` | 404 | Resource not found |
| `INVALID_INPUT` | 400 | Request validation failed |
| `UNAUTHORIZED` | 401 | Authentication required |
| `FORBIDDEN` | 403 | Access denied |
| `CONFLICT` | 409 | Resource state conflict |
| `INTERNAL_ERROR` | 500 | Server error |

---

## 1. Workflow Orchestrator API (NEW)

### 1.1 Onboard Asset

**Endpoint:** `POST /api/workflow/onboard-asset`

**Description:** Onboard a new asset, persist onboarding metadata, and attempt initial baseline capture

**Request Body:**
```json
{
  "site_id": "sandton-mall",
  "site_name": "Sandton City Mall",
  "site_address": "83 5th St, Sandton",
  "equipment": [
    {
      "equipment_id": "chiller-001",
      "equipment_type": "chiller",
      "name": "Main Chiller",
      "manufacturer": "York",
      "model": "YCIV",
      "criticality": "high",
      "baseline_values": {
        "chw_supply_temp": 7.2,
        "chw_return_temp": 12.5,
        "motor_current": 145.2,
        "vibration_rms": 1.8
      }
    }
  ],
  "captured_by": "Mike Chen",
  "notes": "Initial commissioning"
}
```

**Response (200):**
```json
{
  "success": true,
  "site_id": "sandton-mall",
  "equipment_onboarded": 1,
  "baselines_captured": 1,
  "workflow_state": "baseline_capture",
  "equipment": [
    {
      "equipment_id": "chiller-001",
      "baseline_id": "bl-123e4567",
      "state": "monitoring"
    }
  ]
}
```

**Persistence behavior (current):**
- Writes onboarding metadata to `equipment.operating_data.onboarding`:
  - `onboarded`, `onboarded_at`, `captured_by`, `notes`
  - `service_sheet_ref`, `photo_links`, `age_years`, `equipment_ref`
- Writes workflow transitions to `workflow_events` with:
  - `trigger_type: "workflow_state"`
  - `details.from_state`, `details.to_state`, `details.transition_time`
- Baseline capture is attempted; if baseline schema is not compatible in the deployed DB, onboarding still succeeds and logs baseline capture as unavailable.

**Errors:**
- `400` - Invalid equipment data
- `409` - Equipment already exists

---

### 1.2 Get Workflow Status

**Endpoint:** `GET /api/workflow/status/{equipment_id}`

**Description:** Get current workflow state for equipment

**Resolution order:**
1. Latest persisted transition in `workflow_events`
2. In-memory orchestrator state
3. Default fallback (`onboarding`)

**Response (200):**
```json
{
  "success": true,
  "equipment_id": "chiller-001",
  "current_state": "monitoring",
  "state_history": [
    {
      "state": "onboarding",
      "entered_at": "2025-08-01T10:00:00Z",
      "exited_at": "2025-08-01T10:05:00Z",
      "duration_seconds": 300
    },
    {
      "state": "baseline_capture",
      "entered_at": "2025-08-01T10:05:00Z",
      "exited_at": "2025-08-01T10:15:00Z",
      "duration_seconds": 600
    },
    {
      "state": "monitoring",
      "entered_at": "2025-08-01T10:15:00Z",
      "exited_at": null
    }
  ],
  "active_inspection": null,
  "active_repair": null,
  "last_anomaly": null,
  "baseline_status": {
    "has_baseline": true,
    "last_capture": "2025-08-01T10:15:00Z",
    "deviation_status": "normal"
  }
}
```

---

### 1.3 Trigger Inspection from Anomaly

**Endpoint:** `POST /api/workflow/trigger-inspection`

**Description:** Create inspection task triggered by ML anomaly

**Request Body:**
```json
{
  "equipment_id": "chiller-001",
  "trigger_source": "ml_anomaly",
  "anomaly_type": "vibration",
  "probability": 0.85,
  "timeframe": "7 days",
  "ml_explanation": "Bearing vibration up 111% from baseline...",
  "priority": "high"
}
```

**Response (200):**
```json
{
  "success": true,
  "inspection_task_id": "task-123e4567",
  "equipment_id": "chiller-001",
  "scheduled_date": "2026-02-02T08:00:00Z",
  "priority": "high",
  "reason": "ML anomaly detected: vibration (85% probability)",
  "workflow_transition": {
    "from_state": "monitoring",
    "to_state": "inspection_scheduled"
  }
}
```

---

### 1.4 Validate Repair Effectiveness

**Endpoint:** `POST /api/workflow/validate-repair`

**Description:** Compare pre/post repair baselines and validate effectiveness

**Request Body:**
```json
{
  "equipment_id": "chiller-001",
  "work_order_id": "WO-2026-0847",
  "pre_repair_baseline_id": "bl-pre-123",
  "post_repair_baseline_id": "bl-post-456"
}
```

**Response (200):**
```json
{
  "success": true,
  "equipment_id": "chiller-001",
  "work_order_id": "WO-2026-0847",
  "effectiveness": {
    "score": 54.8,
    "repair_successful": true,
    "back_to_baseline": true,
    "improvements": {
      "vibration_rms": {
        "pre_value": 4.2,
        "post_value": 1.9,
        "improvement_percent": 54.8,
        "back_to_baseline": true
      },
      "motor_current": {
        "pre_value": 168.5,
        "post_value": 146.1,
        "improvement_percent": 13.3,
        "back_to_baseline": true
      }
    }
  },
  "workflow_transition": {
    "from_state": "post_repair_baseline",
    "to_state": "effectiveness_validated"
  },
  "ml_feedback_recorded": true
}
```

---

### 1.5 Workflow Events Log

**Endpoint:** `GET /api/workflow/events`

**Description:** Retrieve workflow event log entries for trigger outcomes (created, suppressed, errors).

**Query Parameters:**
- `equipment_id` (optional)
- `trigger_type` (optional)
- `limit` (optional, default 100, max 500)

**Response (200):**
```json
{
  "count": 2,
  "events": [
    {
      "id": "b4a3e29c-1fcb-4a5a-9f2a-7b3f5b71a91a",
      "equipment_id": "2d9b5a83-8f9a-45fa-a6f8-fd2f38b0f88f",
      "trigger_type": "ml_anomaly",
      "action_taken": "created_inspection_task",
      "source": "workflow_triggers",
      "work_order_id": null,
      "inspection_id": null,
      "details": {
        "anomaly_id": "anomaly-20260208093000",
        "task_id": "insp-20260208093000",
        "priority": "high"
      },
      "success": true,
      "created_at": "2026-02-08T09:30:00Z"
    }
  ]
}
```

**Note:** `equipment_id` in events is stored as equipment UUID; `details.equipment_ref` may include the human-readable equipment code used in requests.

---

## 2. Asset Baseline API (Existing)

### 2.1 Capture Baseline

**Endpoint:** `POST /api/equipment/{equipment_id}/baseline`

**Request Body:**
```json
{
  "captured_by": "Mike Chen",
  "baseline_type": "initial",
  "baseline_values": {
    "chw_supply_temp": 7.2,
    "motor_current": 145.2,
    "vibration_rms": 1.8
  },
  "measurement_conditions": {
    "ambient_temp": 22,
    "load_percent": 85
  },
  "notes": "Commissioning baseline"
}
```

**Response:** See 1.1

---

### 2.2 Compare to Baseline

**Endpoint:** `POST /api/equipment/{equipment_id}/baseline/compare`

**Request Body:**
```json
{
  "current_values": {
    "vibration_rms": 4.2,
    "motor_current": 168.5
  },
  "data_source": "bms_sensor"
}
```

**Response (200):**
```json
{
  "success": true,
  "comparison_id": "comp-123",
  "equipment_id": "chiller-001",
  "overall_status": "critical",
  "max_deviation_percent": 133.3,
  "critical_count": 1,
  "warning_count": 1,
  "normal_count": 0,
  "deviations": [
    {
      "metric": "vibration_rms",
      "baseline_value": 1.8,
      "current_value": 4.2,
      "deviation_percent": 133.3,
      "status": "critical"
    },
    {
      "metric": "motor_current",
      "baseline_value": 145.2,
      "current_value": 168.5,
      "deviation_percent": 16.0,
      "status": "warning"
    }
  ]
}
```

---

## 3. Inspection API (Existing)

### 3.1 Create Inspection Schedule

**Endpoint:** `POST /api/inspection/schedules`

**Request Body:**
```json
{
  "equipment_id": "chiller-001",
  "schedule_name": "Monthly Chiller Inspection",
  "schedule_description": "Routine monthly inspection with vibration analysis",
  "frequency_type": "monthly",
  "estimated_duration_minutes": 90,
  "assigned_to": "John Smith",
  "required_skills": ["chiller_maintenance", "vibration_analysis"]
}
```

**Response (200):**
```json
{
  "id": "schedule-123",
  "equipment_id": "chiller-001",
  "schedule_name": "Monthly Chiller Inspection",
  "frequency_type": "monthly",
  "is_active": true,
  "next_due_date": "2026-03-01T08:00:00Z"
}
```

---

### 3.2 Submit Inspection Result

**Endpoint:** `POST /api/inspection/results`

**Request Body:**
```json
{
  "task_id": "task-123",
  "equipment_id": "chiller-001",
  "inspected_by": "John Smith",
  "overall_status": "fail",
  "item_results": [
    {
      "item_id": "ch_007",
      "description": "Measure compressor vibration",
      "status": "fail",
      "measurement_value": "4.2 mm/s",
      "baseline_value": "1.8 mm/s",
      "deviation_percent": 133,
      "notes": "Vibration significantly elevated"
    }
  ],
  "deficiencies_found": 1,
  "general_notes": "Critical vibration issue detected"
}
```

**Response (200):**
```json
{
  "id": "result-456",
  "task_id": "task-123",
  "overall_status": "fail",
  "deficiencies_created": 1,
  "deficiency_ids": ["def-789"]
}
```

---

## 4. ML Predictions API (Existing)

### 4.1 Get Equipment Prediction

**Endpoint:** `GET /api/ml/predictions/lstm/{equipment_id}`

**Query Parameters:**
- `equipment_type` (optional): chiller, generator, ahu, etc.

**Response (200):**
```json
{
  "equipment_id": "chiller-001",
  "equipment_type": "chiller",
  "predictions": {
    "24h": {
      "value": 12.5,
      "confidence": 0.92
    },
    "48h": {
      "value": 12.8,
      "confidence": 0.87
    },
    "72h": {
      "value": 13.1,
      "confidence": 0.81
    }
  },
  "anomaly_detected": false
}
```

---

### 4.2 Get Anomaly Status

**Endpoint:** `GET /api/ml/anomalies/equipment/{equipment_id}`

**Response (200):**
```json
{
  "equipment_id": "chiller-001",
  "is_anomaly": true,
  "anomaly_score": 0.0042,
  "threshold": 0.0007,
  "severity": "critical",
  "details": {
    "reconstruction_error": 0.0042,
    "threshold_exceeded": true,
    "last_check": "2026-02-01T10:30:00Z"
  }
}
```

---

## 5. AI Recommendations API (Existing)

### 5.1 Get Maintenance Recommendation

**Endpoint:** `GET /api/maintenance/recommendations?equipment_id={equipment_id}`

**Response (200):**
```json
{
  "equipment_id": "chiller-001",
  "recommendations": [
    {
      "title": "Replace Compressor Bearing",
      "urgency": "high",
      "description": "Vibration analysis indicates bearing failure imminent...",
      "actions": [
        {
          "description": "Inspect compressor bearing",
          "estimated_time_hours": 2,
          "estimated_cost": 3500,
          "parts_required": ["Leak detector", "Sealant"]
        }
      ],
      "risk_assessment": {
        "probability": "85% within 7 days",
        "impact": "Complete cooling failure",
        "consequence": "Building discomfort, tenant complaints"
      }
    }
  ]
}
```

---

## 6. SIMBIOT MCP API (Existing)

### 6.1 Execute SIMBIOT Tool

**Endpoint:** `POST /api/mcp/simbiot/call`

**Request Body:**
```json
{
  "tool_name": "create_building",
  "parameters": {
  "site_id": "sandton-mall",
    "name": "Sandton City Mall",
    "address": "83 5th St, Sandton",
    "building_type": "commercial"
  }
}
```

**Response (200):**
```json
{
  "success": true,
  "result": {
  "site_id": "sandton-mall",
    "status": "created",
    "equipment_count": 0,
    "zones_count": 0
  }
}
```

---

## Async Operations

For long-running operations (e.g., baseline automation, ML predictions), the API uses async patterns:

### Async Request

```json
{
  "success": true,
  "operation_id": "op-123e4567",
  "status": "pending",
  "estimated_duration_seconds": 300
}
```

### Check Status

**Endpoint:** `GET /api/operations/{operation_id}`

**Response:**
```json
{
  "operation_id": "op-123e4567",
  "status": "completed",
  "result": { /* ... */ }
}
```

---

## Rate Limiting (Future)

Not implemented for demo. Production headers:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1643723400
```

---

## Authentication (Future)

**Request Header:**
```
Authorization: Bearer <token>
```

**Token Types:**
- Service token (backend-to-backend)
- User token (technician/app)

---

## Testing

### Example: Full Onboarding Flow

```bash
# 1. Onboard asset
curl -X POST http://localhost:9095/api/workflow/onboard-asset \
  -H "Content-Type: application/json" \
  -d '{
  "site_id": "sandton-mall",
    "equipment": [{
      "equipment_id": "chiller-001",
      "equipment_type": "chiller",
      "name": "Main Chiller"
    }]
  }'

# 2. Check workflow status
curl http://localhost:9095/api/workflow/status/chiller-001

# 3. Get baseline
curl http://localhost:9095/api/equipment/chiller-001/baseline

# 4. Trigger ML anomaly inspection
curl -X POST http://localhost:9095/api/workflow/trigger-inspection \
  -d '{
    "equipment_id": "chiller-001",
    "trigger_source": "ml_anomaly",
    "priority": "high"
  }'
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-01 | Initial API contracts for Phase 53 |
| 1.1 | 2026-03-31 | Added durable onboarding metadata, persisted workflow state transitions, and baseline compatibility behavior |
