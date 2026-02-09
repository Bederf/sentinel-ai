---
title: "Workflow Triggers & Automation"
type: "feature"
status: "implemented"
version: "1.0.0"
created: "2026-02-03"
updated: "2026-02-08"
author: "SENTINEL Development Team"
tags: ["workflow", "automation", "triggers", "ml", "baseline", "inspection"]
domain: "asset-management"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
phase: "53-02"
---

# Workflow Triggers & Automation

Automated triggers that connect ML anomalies, baseline deviations, inspection deficiencies, repair completions, and effectiveness validation into a cohesive workflow system.

## Overview

The Workflow Trigger Engine provides 5 automated triggers that orchestrate the complete asset maintenance lifecycle without manual intervention.

**Automation Expansion (Phase 53-02):**
- Trigger deduplication uses cooldown windows to suppress duplicate actions per equipment.
- All trigger outcomes (including suppressed, errors, and within-threshold) are logged to `workflow_events`.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    WORKFLOW TRIGGER FLOW                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ML Anomaly ──────► Inspection Task                                    │
│        │                   │                                            │
│        ▼                   ▼                                            │
│   Baseline         Inspection Execution                                 │
│   Deviation              │                                              │
│        │                 ▼                                              │
│        ▼           Critical Deficiency ──────► Work Order               │
│   AI Recommendation      │                        │                     │
│        │                 │                        ▼                     │
│        └────────────────►│              Pre-Repair Baseline             │
│                          │                        │                     │
│                          ▼                        ▼                     │
│                    Repair Execution ◄────── Work Order Assigned         │
│                          │                                              │
│                          ▼                                              │
│                   Repair Completed                                      │
│                          │                                              │
│                          ▼                                              │
│               Post-Repair Baseline + Verification Inspection            │
│                          │                                              │
│                          ▼                                              │
│               Effectiveness Validation                                  │
│                     │         │                                         │
│              ┌──────┘         └──────┐                                  │
│              ▼                       ▼                                  │
│         SUCCESS               FAILED                                    │
│     ML Feedback Loop      Follow-up Inspection                          │
│     Back to Monitoring    Re-diagnosis Required                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## The 5 Triggers

**Integration Notes (Phase 53-01):**
- Inspection deficiencies (critical/safety) automatically invoke the Critical Deficiency trigger.
- Technician work orders marked complete invoke the Repair Completed trigger.

### 1. ML Anomaly → Inspection Task

When ML detects an anomaly, automatically creates an inspection task.

**Trigger Conditions:**
- ML anomaly detected with probability > 0.5
- No pending inspection exists for equipment
- Duplicate suppression enforced for 6 hours per equipment/anomaly

**Actions:**
- Creates inspection task with priority based on probability
- Sends notification alert
- Logs to audit trail

**Priority Calculation:**
| Probability | Priority |
|-------------|----------|
| ≥ 90% | Critical |
| ≥ 70% | High |
| ≥ 50% | Medium |
| < 50% | Low |

**API Endpoint:**
```bash
POST /api/workflow/triggers/ml-anomaly
Content-Type: application/json

{
  "equipment_id": "chiller-001",
  "anomaly_type": "vibration",
  "description": "High vibration detected during monitoring",
  "probability": 0.85,
  "timeframe": "24h"
}
```

---

### 2. Baseline Deviation → Maintenance Recommendation

When baseline deviation exceeds threshold, generates AI maintenance recommendation.

**Trigger Conditions:**
- Deviation > 15%: Generates recommendation
- Deviation > 20%: Also creates inspection task (critical)
- Duplicate suppression enforced for 6 hours per equipment/baseline

**Actions:**
- Generates AI maintenance recommendation
- If critical (>20%), creates inspection task
- Logs to audit trail

**Thresholds:**
| Deviation | Action |
|-----------|--------|
| < 15% | No action (within tolerance) |
| 15-20% | Generate recommendation |
| > 20% | Recommendation + Critical inspection |

**API Endpoint:**
```bash
POST /api/workflow/triggers/baseline-deviation
Content-Type: application/json

{
  "equipment_id": "pump-001",
  "baseline_id": "bl-001",
  "max_deviation_percent": 18.5,
  "deviating_metrics": {
    "vibration": 18.5,
    "current": 15.0
  }
}
```

---

### 3. Critical Deficiency → Work Order

When inspection finds critical/safety deficiency, automatically creates work order.

**Trigger Conditions:**
- Deficiency severity is "critical" or "safety"
- Minor/major deficiencies require manual work order creation
- Duplicate suppression enforced for 12 hours per equipment/deficiency

**Actions:**
- Creates work order with deficiency details
- Schedules pre-repair baseline capture (2 hours)
- Sends notification alert
- Logs to audit trail

**API Endpoint:**
```bash
POST /api/workflow/triggers/critical-deficiency
Content-Type: application/json

{
  "inspection_id": "insp-001",
  "equipment_id": "ahu-001",
  "severity": "critical",
  "deficiency_title": "Bearing failure imminent",
  "deficiency_description": "Vibration analysis shows bearing wear beyond tolerance",
  "recommended_action": "Replace bearings within 48 hours",
  "estimated_repair_cost_min": 5000.0,
  "estimated_repair_cost_max": 8000.0,
  "estimated_repair_hours": 4.0
}
```

---

### 4. Repair Completed → Post-Repair Inspection

When work order is completed, triggers post-repair verification workflow.

**Trigger Conditions:**
- Work order marked as completed

**Actions:**
- Schedules post-repair baseline capture (1 hour)
- Creates verification inspection task (2 hours)
- Schedules effectiveness validation (3 hours)
- Logs to audit trail

**API Endpoint:**
```bash
POST /api/workflow/triggers/repair-completed
Content-Type: application/json

{
  "work_order_id": "WO-001",
  "equipment_id": "fcu-001",
  "completion_notes": "Bearings replaced successfully",
  "parts_used": ["Bearing SKF 6205", "Seal kit"],
  "actual_hours": 3.5
}
```

---

### 5. Effectiveness Validation → ML Feedback

Compares pre/post repair baselines to validate repair effectiveness.

**Trigger Conditions:**
- Both pre-repair and post-repair baselines captured

**Actions:**
- Calculates improvement percentage for each metric
- Determines repair success (>50% average improvement)
- If failed: Creates follow-up inspection task
- Records ML feedback for continuous learning
- Logs to audit trail

**Success Criteria:**
| Condition | Result |
|-----------|--------|
| Average improvement > 50% | Repair successful |
| All metrics within 15% of original | Back to baseline |
| Average improvement ≤ 50% | Repair failed, follow-up created |

**API Endpoint:**
```bash
POST /api/workflow/triggers/validate-effectiveness
Content-Type: application/json

{
  "equipment_id": "vav-001",
  "work_order_id": "WO-002",
  "pre_baseline": {
    "baseline_values": {
      "vibration_rms": 3.5,
      "motor_current": 152.0
    }
  },
  "post_baseline": {
    "baseline_values": {
      "vibration_rms": 1.2,
      "motor_current": 145.0
    }
  }
}
```

---

## Query Endpoints

### Get Workflow Events Log
```bash
GET /api/workflow/events
GET /api/workflow/events?equipment_id=chiller-001
GET /api/workflow/events?trigger_type=ml_anomaly&limit=50
```

### Get Trigger History
```bash
GET /api/workflow/triggers/history
GET /api/workflow/triggers/history?equipment_id=chiller-001
```

### Get Pending Inspections
```bash
GET /api/workflow/triggers/inspections/{equipment_id}
```

### Get Pending Work Orders
```bash
GET /api/workflow/triggers/work-orders/{equipment_id}
```

### Get Pending Baseline Tasks
```bash
GET /api/workflow/triggers/baseline-tasks/{equipment_id}
```

### Get Effectiveness Result
```bash
GET /api/workflow/triggers/effectiveness/{work_order_id}
```

---

## Test Endpoints

### Test ML Anomaly Trigger
```bash
POST /api/workflow/test/trigger-ml-anomaly?equipment_id=chiller-001&anomaly_type=vibration
```

### Test Full Workflow Cycle
```bash
POST /api/workflow/test/full-workflow?equipment_id=test-chiller
```

This runs the complete workflow: Anomaly → Deficiency → Repair → Validation

---

## Data Models

### TriggerResult
```python
{
  "success": true,
  "trigger_type": "ml_anomaly",
  "equipment_id": "chiller-001",
  "action_taken": "created_inspection_task",
  "details": {
    "task_id": "insp-20260203120000",
    "scheduled_date": "2026-02-04T12:00:00",
    "priority": "high"
  },
  "follow_up_scheduled": true,
  "timestamp": "2026-02-03T12:00:00"
}
```

### EffectivenessResult
```python
{
  "work_order_id": "WO-001",
  "equipment_id": "chiller-001",
  "effectiveness_score": 58.3,
  "improvements": {
    "vibration_rms": {
      "pre_value": 3.5,
      "post_value": 1.2,
      "improvement_percent": 65.7,
      "back_to_baseline": false
    },
    "motor_current": {
      "pre_value": 180.0,
      "post_value": 90.0,
      "improvement_percent": 50.0,
      "back_to_baseline": false
    }
  },
  "repair_successful": true,
  "back_to_baseline": false,
  "validation_date": "2026-02-03T15:00:00"
}
```

---

## Configuration

The trigger engine uses configurable thresholds:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `baseline_deviation_threshold` | 15% | Min deviation to trigger recommendation |
| `critical_deviation_threshold` | 20% | Deviation to also create inspection |
| `effectiveness_success_threshold` | 50% | Min improvement for successful repair |
| `baseline_tolerance` | 15% | Tolerance for "back to baseline" status |

**Deduplication Cooldowns:**
| Trigger | Cooldown |
|---------|----------|
| ML Anomaly | 6 hours |
| Baseline Deviation | 6 hours |
| Critical Deficiency | 12 hours |

---

## Implementation

**Service:** `backend/app/services/workflow_triggers.py`
**API:** `backend/app/api/workflow.py`
**Tests:** `backend/tests/services/test_workflow_triggers.py`

## Related Documentation

- [Asset Workflow Architecture](asset-workflow-architecture.md)
- [Asset Workflow API Contracts](asset-workflow-api-contracts.md)
- [Asset Lifecycle State Machine](asset-lifecycle-state-machine.md)
- [Phases 44-46 Integration Workflow](../04-features/44-46-integration-workflow.md)
