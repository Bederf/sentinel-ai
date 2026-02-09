# SENTINEL Asset Management Workflow - Integration Architecture

**Date:** 2026-02-08
**Phase:** 53 - SENTINEL Asset Management Workflow Integration
**Author:** Claude Code

## Overview

This document describes the integration architecture that connects SIMBIOT, Asset Baseline Assessment, Inspection System, ML Predictions, and AI Recommendations into a cohesive automated workflow.

## Phase 53-01 Integration Wiring

- Baseline comparison API triggers workflow deviations (wired in `/api/baselines/{equipment_id}/compare`).
- Inspection deficiency creation (critical/safety) triggers auto work order workflow.
- Technician work order completion triggers post-repair workflow (baseline + verification).

## System Components

### 1. SIMBIOT MCP Server
**Purpose:** Building and equipment onboarding from BMS exports
**Key Tools:**
- `create_building` - Initialize building configuration
- `add_building_zones` - Add HVAC zones
- `add_building_desks` - Add workspace desks
- `add_building_devices` - Add BMS devices
- `import_point_list` - Parse BACnet point list CSV
- `activate_building` - Add to active registry

**API Endpoints:**
- `GET /api/mcp/simbiot/tools` - List all SIMBIOT tools
- `POST /api/mcp/simbiot/call` - Execute SIMBIOT tool

### 2. Asset Baseline Assessment Service
**Purpose:** Capture and manage equipment operating baselines
**Key Operations:**
- Capture baseline (manual/automated)
- Compare current to baseline
- Deviation detection (>15% warning, >20% critical)
- Pre/post-repair baselines

**API Endpoints:**
- `POST /api/equipment/{id}/baseline` - Capture baseline
- `GET /api/equipment/{id}/baseline` - Get active baseline
- `POST /api/equipment/{id}/baseline/compare` - Compare to baseline
- `GET /api/equipment/{id}/baseline/deviations/critical` - Get critical deviations
- `GET /api/equipment/{id}/elements` - List equipment elements
- `POST /api/equipment/{id}/elements/{element_id}/baseline` - Capture element baseline

### 3. Inspection & Maintenance Service
**Purpose:** Schedule and track routine inspections
**Key Operations:**
- Create inspection schedules (weekly/monthly/quarterly/annual)
- Generate inspection tasks from schedules
- Capture inspection results
- Create deficiencies from failed items
- Track deficiency resolution

**API Endpoints:**
- `POST /api/inspection/schedules` - Create schedule
- `POST /api/inspection/tasks/generate` - Generate tasks
- `GET /api/inspection/tasks/{task_id}` - Get task details
- `POST /api/inspection/tasks/{task_id}/start` - Start inspection
- `POST /api/inspection/results` - Submit results
- `POST /api/inspection/deficiencies` - Create deficiency
- `GET /api/inspection/summary/equipment/{id}` - Equipment summary

### 4. ML Predictions Service
**Purpose:** Failure forecasting and anomaly detection
**Key Operations:**
- LSTM time-series forecasting (24/48/72h predictions)
- Autoencoder anomaly detection
- Survival analysis (Cox Proportional Hazards)
- Equipment health scoring

**API Endpoints:**
- `GET /api/ml/predictions/lstm/{equipment_id}` - LSTM predictions
- `GET /api/ml/anomalies/equipment/{equipment_id}` - Anomaly detection
- `GET /api/ml/survival/equipment/{equipment_id}` - Survival prediction
- `GET /api/ml/anomalies/alerts` - All active anomaly alerts

### 5. AI Recommendations Service (Explainable AI)
**Purpose:** Generate explainable maintenance recommendations
**Key Operations:**
- Natural language explanations for predictions
- Structured output parsing (actions, urgency, cost, parts)
- Maintenance prioritization
- Fleet learning from historical patterns

**API Endpoints:**
- `GET /api/ml/explanations/{equipment_id}` - Get explanation
- `GET /api/maintenance/recommendations` - Get recommendations
- `GET /api/maintenance/priorities` - Get prioritized actions

### 6. Workflow Orchestrator (NEW)
**Purpose:** Coordinate automated workflow across all systems
**Key Operations:**
- Onboard asset (SIMBIOT + baseline capture)
- Schedule baseline inspection
- Process ML anomaly (create inspection)
- Generate maintenance recommendation
- Validate repair effectiveness (pre/post comparison)

**API Endpoints:**
- `POST /api/workflow/onboard-asset` - Onboard new asset
- `POST /api/workflow/trigger-inspection` - Trigger inspection from anomaly
- `GET /api/workflow/status/{equipment_id}` - Get workflow status
- `POST /api/workflow/validate-repair` - Validate repair effectiveness

### 7. Workflow Events Log (NEW)
**Purpose:** Persistent log of workflow trigger outcomes for observability
**Key Operations:**
- Record trigger outcomes (created, suppressed, errors)
- Filter by equipment or trigger type

**API Endpoints:**
- `GET /api/workflow/events` - List workflow events (filters supported)

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SENTINEL Workflow Integration                          │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │   User Input    │
                              │  (Technician/   │
                              │   FM Manager)   │
                              └────────┬────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Workflow Orchestrator                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  State Machine: Onboarding → Baseline → Monitoring → Inspection    │   │
│  │                → Deficiency → Repair → Validation                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└───────────┬───────────────────────────────────────────────────────────────────┘
            │
            ├─────────────────────────────────────────────────────────────┐
            │                             │                               │
            ▼                             ▼                               ▼
┌───────────────────────┐   ┌───────────────────────┐   ┌───────────────────────┐
│   SIMBIOT MCP Server  │   │ Asset Baseline Service│   │  Inspection Service    │
│                       │   │                       │   │                       │
│ • Building onboarding │   │ • Capture baselines   │   │ • Schedule inspections│
│ • Equipment import    │◄──┤ • Compare to baseline│──►│ • Generate tasks      │
│ • Zone/desk mappings  │   │ • Deviation detection │   │ • Track results       │
│ • BACnet import       │   │ • Pre/post capture   │   │ • Create deficiencies │
└───────────────────────┘   └───────────────────────┘   └───────────────────────┘
            │                             │                               │
            │                             ▼                               │
            │                    ┌───────────────────────┐               │
            │                    │  ML Predictions      │               │
            │                    │                       │               │
            │                    │ • LSTM forecasting    │               │
            │                    │ • Anomaly detection   │               │
            │                    │ • Survival analysis   │               │
            │                    │ • Health scoring      │               │
            │                    └───────────┬───────────┘               │
            │                                │                           │
            │                                ▼                           │
            │                    ┌───────────────────────┐               │
            │                    │ AI Recommendations   │               │
            │                    │                       │               │
            │                    │ • Explainable AI      │               │
            │                    │ • Maintenance recs   │               │
            │                    │ • Prioritization     │               │
            │                    │ • Fleet learning     │               │
            │                    └───────────────────────┘               │
            │                                                             │
            └─────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │   Audit Log     │
                              │  (All actions   │
                              │   tracked)      │
                              └─────────────────┘

## Data Flow

### Flow 1: Asset Onboarding
```
User → Workflow Orchestrator
  ├─→ SIMBIOT: create_building()
  ├─→ SIMBIOT: import_point_list()
  ├─→ SIMBIOT: add_building_zones()
  └─→ Baseline Service: capture_baseline(initial)
```

### Flow 2: Routine Inspection Cycle
```
Workflow Orchestrator (scheduled)
  ├─→ Inspection Service: generate_tasks()
  ├─→ User: Starts inspection via mobile
  ├─→ Inspection Service: submit_results()
  ├─→ Baseline Service: compare()
  ├─→ IF deviation > 15%: AI Recommendations
  └─→ IF deviation > 20%: Create deficiency
```

### Flow 3: ML Anomaly Trigger
```
ML Service: anomaly_detected()
  ├─→ Workflow Orchestrator: on_ml_anomaly()
  ├─→ Inspection Service: create_task(priority=high)
  ├─→ User: Performs inspection
  ├─→ IF critical: Create deficiency
  └─→ Work Order: auto-created
```

### Flow 4: Repair Validation
```
Work Order: completed()
  ├─→ Workflow Orchestrator: on_repair_completed()
  ├─→ Baseline Service: schedule_capture(post_repair)
  ├─→ Inspection Service: create_task(verification)
  └─→ Workflow Orchestrator: validate_repair_effectiveness()
       ├─→ Compare pre/post baselines
       ├─→ Calculate improvement %
       ├─→ IF successful: Return to monitoring
       └─→ IF failed: Schedule follow-up
```

## Integration Points

### 1. SIMBIOT → Baseline
**Trigger:** Building/equipment onboarding complete
**Action:** Capture initial baseline for new equipment
**Data:** equipment_id, baseline_values

### 2. Baseline → Inspection
**Trigger:** Baseline deviation detected
**Action:** Create inspection task with baseline reference
**Data:** equipment_id, deviation_percent, baseline_id

### 3. ML → Inspection
**Trigger:** Anomaly alert generated
**Action:** Create inspection task with ML reference
**Data:** equipment_id, anomaly_type, probability

### 4. Inspection → Deficiency
**Trigger:** Inspection item failed
**Action:** Create deficiency record
**Data:** equipment_id, deficiency_details, severity

### 5. Deficiency → Work Order
**Trigger:** Critical deficiency created
**Action:** Auto-generate work order
**Data:** equipment_id, deficiency_id, repair_recommendations

### 6. Work Order → Baseline (Pre-Repair)
**Trigger:** Work order scheduled
**Action:** Schedule pre-repair baseline capture
**Data:** equipment_id, work_order_id

### 7. Work Order → Baseline (Post-Repair)
**Trigger:** Work order completed
**Action:** Schedule post-repair baseline capture
**Data:** equipment_id, work_order_id

### 8. Baseline Comparison → Effectiveness
**Trigger:** Pre/post baselines available
**Action:** Calculate repair effectiveness
**Data:** equipment_id, pre_baseline_id, post_baseline_id

### 9. Effectiveness → ML Feedback
**Trigger:** Repair validation complete
**Action:** Record outcome for ML training
**Data:** equipment_id, work_order_id, effectiveness_score

## State Machine

### Asset Lifecycle States

```
┌──────────────┐
│  ONBOARDING  │  SIMBIOT building/equipment import
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ BASELINE_    │  Initial baseline captured
│  CAPTURE     │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  MONITORING  │  Normal operation, routine checks
└──────┬───────┘
       │
       ├──────────────────┐
       │                  │
       ▼                  ▼
┌──────────────┐   ┌──────────────┐
│  INSPECTION_ │   │   ANOMALY_   │  ML alert
│  SCHEDULED   │   │  DETECTED    │
└──────┬───────┘   └──────┬───────┘
       │                  │
       ▼                  ▼
┌──────────────┐   ┌──────────────┐
│  INSPECTION_ │   │  INSPECTION_ │
│  IN_PROGRESS │   │  SCHEDULED   │  Triggered by ML
└──────┬───────┘   └──────┬───────┘
       │                  │
       ▼                  ▼
┌──────────────┐   ┌──────────────┐
│ DEFICIENCY_  │   │  INSPECTION_ │
│ IDENTIFIED   │   │ IN_PROGRESS  │
└──────┬───────┘   └──────┬───────┘
       │                  │
       ▼                  ▼
┌──────────────┐   ┌──────────────┐
│   REPAIR_    │   │ DEFICIENCY_  │
│  SCHEDULED   │   │ IDENTIFIED   │
└──────┬───────┘   └──────┬───────┘
       │                  │
       ▼                  ▼
┌──────────────┐   ┌──────────────┐
│ PRE_REPAIR_  │   │   REPAIR_    │
│  BASELINE    │   │ SCHEDULED    │
└──────┬───────┘   └──────┬───────┘
       │                  │
       ▼                  ▼
┌──────────────┐   ┌──────────────┐
│  REPAIR_IN_  │   │ PRE_REPAIR_  │
│  PROGRESS    │   │  BASELINE    │
└──────┬───────┘   └──────┬───────┘
       │                  │
       ▼                  ▼
┌──────────────┐   ┌──────────────┐
│ POST_REPAIR_ │   │  REPAIR_IN_  │
│  BASELINE    │   │ PROGRESS     │
└──────┬───────┘   └──────┬───────┘
       │                  │
       ▼                  ▼
┌──────────────┐   ┌──────────────┐
│ EFFECTIVE-   │   │ POST_REPAIR_ │
│   NESS_      │   │  BASELINE    │
│  VALIDATED   │   └──────┬───────┘
└──────┬───────┘          │
       │                  ▼
       ▼         ┌──────────────┐
┌──────────────┐ │ EFFECTIVE-   │
│ BACK_TO_     │ │   NESS_      │
│  NORMAL      │ │  VALIDATED   │
└──────────────┘ └──────┬───────┘
                      │
                      ▼
               ┌──────────────┐
               │ BACK_TO_     │
               │  NORMAL      │
               └──────────────┘
```

## API Contracts

See `asset-workflow-api-contracts.md` for detailed API specifications.

## Technology Stack

- **Backend:** FastAPI + Python 3.11
- **Orchestrator:** Async Python service
- **State Management:** In-memory with audit log
- **Database:** Supabase (PostgreSQL) with JSON fallback
- **ML:** TensorFlow (LSTM/Autoencoder), lifelines (Survival)
- **AI:** Ollama (phi3:mini) for explanations

## Security & Safety

- All control actions validated through SafetyEngine
- Audit logging for all workflow transitions
- Human-in-the-loop for critical repairs
- Read-only operations by default (SIMBIOT)

## Next Steps

1. Implement Workflow Orchestrator service (Task 3)
2. Document API contracts (Task 2)
3. Create integration tests (Task 5)
4. Build automated triggers (Plan 53-02)
