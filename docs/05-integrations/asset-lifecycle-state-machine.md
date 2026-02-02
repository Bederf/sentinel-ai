# SENTINEL Asset Lifecycle State Machine

**Date:** 2026-02-01
**Phase:** 53 - SENTINEL Asset Management Workflow Integration

## Overview

This document defines the asset lifecycle state machine that tracks equipment from initial onboarding through repair validation and back to normal operation.

## State Definitions

### 1. ONBOARDING
**Description:** Building/equipment being onboarded via SIMBIOT
**Entry Trigger:** User initiates building onboarding
**Exit Trigger:** SIMBIOT onboarding complete
**Duration:** Typically 5-10 minutes
**Next States:** BASELINE_CAPTURE

**Activities:**
- SIMBIOT: `create_building()`
- SIMBIOT: `import_point_list()`
- SIMBIOT: `add_building_zones()`
- SIMBIOT: `add_building_desks()`
- SIMBIOT: `add_building_devices()`
- SIMBIOT: `activate_building()`

**Data Required:**
- Building ID, name, address
- Equipment list with types
- BACnet point list (optional)

**Data Produced:**
- Building record created
- Equipment records created
- Zone/desk mappings established

---

### 2. BASELINE_CAPTURE
**Description:** Initial baseline being captured for equipment
**Entry Trigger:** Onboarding complete
**Exit Trigger:** Baseline successfully captured
**Duration:** Typically 10-30 minutes (manual) or 24 hours (automated)
**Next States:** MONITORING

**Activities:**
- Manual: Engineer records baseline readings
- Automated: System averages BMS sensor readings over 24h
- Store baseline values in database
- Generate baseline comparison report

**Data Required:**
- Equipment ID
- Baseline values (key metrics)
- Measurement conditions (load, ambient temp, etc.)
- Captured by (technician name)

**Data Produced:**
- Baseline record with ID
- Baseline values JSON
- Measurement conditions

---

### 3. MONITORING
**Description:** Equipment under normal monitoring
**Entry Trigger:** Baseline captured OR repair validated
**Exit Trigger:** ML anomaly detected OR inspection scheduled
**Duration:** Ongoing (until event triggers exit)
**Next States:** INSPECTION_SCHEDULED, ANOMALY_DETECTED

**Activities:**
- Background ML monitoring (LSTM predictions)
- Anomaly detection (autoencoder)
- Scheduled baseline comparisons
- Routine inspection generation

**Monitoring Checks:**
- LSTM: 24/48/72h predictions
- Autoencoder: Anomaly score every 15 min
- Baseline: Daily deviation check
- Inspection: Monthly schedule

**Exit Conditions:**
- Anomaly score > threshold → ANOMALY_DETECTED
- Inspection due → INSPECTION_SCHEDULED
- Baseline deviation > 15% → Generate recommendation

---

### 4. INSPECTION_SCHEDULED
**Description:** Routine inspection task created and scheduled
**Entry Trigger:** Schedule due date reached OR anomaly detected
**Exit Trigger:** Technician starts inspection
**Duration:** Until scheduled date (typically 1-30 days)
**Next States:** INSPECTION_IN_PROGRESS

**Activities:**
- Create inspection task
- Assign to technician
- Generate checklist from baseline
- Send notification

**Data Required:**
- Equipment ID
- Schedule ID (if recurring)
- Priority (normal/high/critical)
- Assigned technician

**Data Produced:**
- Inspection task record
- Checklist items with baseline references
- Notification sent

---

### 5. INSPECTION_IN_PROGRESS
**Description:** Inspection being performed by technician
**Entry Trigger:** Technician starts task
**Exit Trigger:** Technician submits results
**Duration:** Typically 30-120 minutes
**Next States:** DEFICIENCY_IDENTIFIED, BACK_TO_NORMAL

**Activities:**
- Technician follows checklist
- Record measurements
- Compare to baseline values
- Upload photos
- Pass/fail each item

**Data Required:**
- Task ID
- Technician ID
- Measurement values
- Notes/photos

**Data Produced:**
- Inspection result record
- Item results (pass/fail)
- Deficiencies (if any)

---

### 6. ANOMALY_DETECTED
**Description:** ML model detected anomaly
**Entry Trigger:** Anomaly score exceeds threshold
**Exit Trigger:** Inspection task created
**Duration:** Minutes to hours (response time)
**Next States:** INSPECTION_SCHEDULED

**Activities:**
- ML service generates alert
- Orchestrator creates inspection task
- High priority flag set
- Notification sent

**Data Required:**
- Equipment ID
- Anomaly type
- Anomaly score
- Probability/confidence

**Data Produced:**
- Anomaly alert record
- Inspection task (high priority)

---

### 7. DEFICIENCY_IDENTIFIED
**Description:** Inspection found equipment issue
**Entry Trigger:** Inspection item failed
**Exit Trigger:** Work order created
**Duration:** Until work order scheduled (hours to days)
**Next States:** REPAIR_SCHEDULED

**Activities:**
- Log deficiency details
- Determine severity (minor/major/critical/safety)
- Estimate repair cost/time
- Recommend action

**Data Required:**
- Inspection result ID
- Failed item details
- Technician observations

**Data Produced:**
- Deficiency record
- Repair recommendations
- Cost estimates

---

### 8. REPAIR_SCHEDULED
**Description:** Work order created for repair
**Entry Trigger:** Deficiency identified (auto-created if critical)
**Exit Trigger:** Repair work starts
**Duration:** Until scheduled (hours to weeks)
**Next States:** PRE_REPAIR_BASELINE

**Activities:**
- Create work order
- Schedule technician(s)
- Order parts (if needed)
- Schedule pre-repair baseline

**Data Required:**
- Deficiency ID
- Repair description
- Estimated cost/time
- Parts required

**Data Produced:**
- Work order record
- Pre-repair baseline task

---

### 9. PRE_REPAIR_BASELINE
**Description:** Capturing equipment state before repair
**Entry Trigger:** Work order scheduled, 2 hours before repair
**Exit Trigger:** Pre-repair baseline captured
**Duration:** Typically 30 minutes
**Next States:** REPAIR_IN_PROGRESS

**Activities:**
- Technician captures baseline readings
- Document current equipment state
- Note any additional findings

**Data Required:**
- Equipment ID
- Work order ID
- Current readings

**Data Produced:**
- Pre-repair baseline record
- Linked to work order

---

### 10. REPAIR_IN_PROGRESS
**Description:** Repair work being performed
**Entry Trigger:** Pre-repair baseline captured
**Exit Trigger:** Repair marked complete
**Duration:** Variable (hours to days)
**Next States:** POST_REPAIR_BASELINE

**Activities:**
- Technician performs repair
- Replace parts/adjust settings
- Test equipment operation
- Document work performed

**Data Required:**
- Work order ID
- Repair details
- Parts used
- Labor hours

**Data Produced:**
- Work order completion record
- Labor/parts tracking

---

### 11. POST_REPAIR_BASELINE
**Description:** Capturing equipment state after repair
**Entry Trigger:** Repair marked complete
**Exit Trigger:** Post-repair baseline captured
**Duration:** Typically 30 minutes
**Next States:** EFFECTIVENESS_VALIDATED

**Activities:**
- Technician captures baseline readings
- Same metrics as pre-repair
- Compare to pre-repair values

**Data Required:**
- Equipment ID
- Work order ID
- Post-repair readings

**Data Produced:**
- Post-repair baseline record
- Linked to work order

---

### 12. EFFECTIVENESS_VALIDATED
**Description:** Comparing pre/post repair baselines
**Entry Trigger:** Both baselines captured
**Exit Trigger:** Validation complete
**Duration:** Automated (seconds)
**Next States:** BACK_TO_NORMAL, REPAIR_SCHEDULED (if failed)

**Activities:**
- Calculate improvement percentage
- Determine if back to baseline
- Validate repair success
- Record ML feedback

**Validation Criteria:**
- **Success:** Improvement > 50% AND within 15% of original baseline
- **Failure:** Improvement < 50% OR not within baseline range

**Data Required:**
- Pre-repair baseline ID
- Post-repair baseline ID
- Work order ID

**Data Produced:**
- Effectiveness score
- Validation result
- ML feedback record

---

### 13. BACK_TO_NORMAL
**Description:** Equipment returned to normal monitoring
**Entry Trigger:** Repair validated OR inspection passed
**Exit Trigger:** Next event (anomaly, inspection due, etc.)
**Duration:** Ongoing
**Next States:** MONITORING (effectively same state)

**Activities:**
- Resume normal monitoring
- Close work order
- Update equipment status
- Feed ML training data

**Data Required:**
- Equipment ID
- Work order ID (if repair)

**Data Produced:**
- Equipment status updated
- ML training data recorded

---

## State Transitions

### Primary Flow (Happy Path)
```
ONBOARDING
  → BASELINE_CAPTURE
  → MONITORING
  → INSPECTION_SCHEDULED (routine)
  → INSPECTION_IN_PROGRESS
  → BACK_TO_NORMAL (pass)
  → MONITORING
```

### Anomaly Detection Flow
```
MONITORING
  → ANOMALY_DETECTED
  → INSPECTION_SCHEDULED (priority: high)
  → INSPECTION_IN_PROGRESS
  → DEFICIENCY_IDENTIFIED (issue found)
  → REPAIR_SCHEDULED
  → PRE_REPAIR_BASELINE
  → REPAIR_IN_PROGRESS
  → POST_REPAIR_BASELINE
  → EFFECTIVENESS_VALIDATED
  → BACK_TO_NORMAL (success)
  → MONITORING
```

### Failed Repair Flow
```
EFFECTIVENESS_VALIDATED
  → REPAIR_SCHEDULED (if validation failed)
  → (repeat repair process)
```

## Transition Triggers

| From State | To State | Trigger | Auto/Manual |
|------------|----------|---------|------------|
| ONBOARDING | BASELINE_CAPTURE | SIMBIOT complete | Auto |
| BASELINE_CAPTURE | MONITORING | Baseline captured | Auto |
| MONITORING | INSPECTION_SCHEDULED | Schedule due | Auto |
| MONITORING | ANOMALY_DETECTED | ML anomaly detected | Auto |
| ANOMALY_DETECTED | INSPECTION_SCHEDULED | Task created | Auto |
| INSPECTION_SCHEDULED | INSPECTION_IN_PROGRESS | Technician starts | Manual |
| INSPECTION_IN_PROGRESS | DEFICIENCY_IDENTIFIED | Items failed | Auto |
| INSPECTION_IN_PROGRESS | BACK_TO_NORMAL | All passed | Auto |
| DEFICIENCY_IDENTIFIED | REPAIR_SCHEDULED | Work order created | Auto (if critical) |
| REPAIR_SCHEDULED | PRE_REPAIR_BASELINE | 2h before repair | Auto |
| PRE_REPAIR_BASELINE | REPAIR_IN_PROGRESS | Baseline captured | Auto |
| REPAIR_IN_PROGRESS | POST_REPAIR_BASELINE | Repair complete | Manual |
| POST_REPAIR_BASELINE | EFFECTIVENESS_VALIDATED | Baseline captured | Auto |
| EFFECTIVENESS_VALIDATED | BACK_TO_NORMAL | Validation successful | Auto |
| EFFECTIVENESS_VALIDATED | REPAIR_SCHEDULED | Validation failed | Auto |
| BACK_TO_NORMAL | MONITORING | Resume monitoring | Auto |

## State Duration Analysis

| State | Typical Duration | Max Duration |
|-------|------------------|--------------|
| ONBOARDING | 5-10 min | 1 hour |
| BASELINE_CAPTURE | 10-30 min (manual) / 24h (auto) | 48 hours |
| MONITORING | Ongoing | Indefinite |
| INSPECTION_SCHEDULED | 1-30 days | 90 days |
| INSPECTION_IN_PROGRESS | 30-120 min | 4 hours |
| ANOMALY_DETECTED | Minutes | 1 hour |
| DEFICIENCY_IDENTIFIED | Hours-days | 30 days |
| REPAIR_SCHEDULED | Hours-weeks | 90 days |
| PRE_REPAIR_BASELINE | 30 min | 2 hours |
| REPAIR_IN_PROGRESS | Hours-days | 14 days |
| POST_REPAIR_BASELINE | 30 min | 2 hours |
| EFFECTIVENESS_VALIDATED | Seconds | 1 minute |
| BACK_TO_NORMAL | Ongoing | Indefinite |

## State Visualization

```
                    ┌─────────────┐
                    │ ONBOARDING  │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │ BASELINE_   │
                    │  CAPTURE    │
                    └──────┬──────┘
                           │
                           ▼
         ┌───────────────────────────────────┐
         │          MONITORING               │◄────────────────┐
         └───────┬─────────────────┬─────────┘                 │
                 │                 │                           │
        ┌────────▼────────┐   ┌───▼────────┐                  │
        │ INSPECTION_     │   │ ANOMALY_   │                  │
        │  SCHEDULED      │   │ DETECTED   │                  │
        └────────┬────────┘   └─────┬──────┘                  │
                 │                  │                          │
        ┌────────▼────────┐         │                          │
        │ INSPECTION_     │         │                          │
        │ IN_PROGRESS     │         │                          │
        └─────┬──────┬────┘         │                          │
              │      │              │                          │
        ┌───────┘      └───┬────────┘                          │
        │                  │                                   │
   ┌────▼─────┐     ┌─────▼──────────┐                        │
   │ BACK_TO_ │     │ DEFICIENCY_    │                        │
   │  NORMAL  │     │ IDENTIFIED     │                        │
   └────┬─────┘     └─────┬──────────┘                        │
        │                  │                                   │
        └──────────────────┴───────────┐                       │
                                      │                       │
                              ┌───────▼──────────┐             │
                              │  REPAIR_         │             │
                              │  SCHEDULED       │             │
                              └───────┬──────────┘             │
                                      │                       │
                              ┌───────▼──────────┐             │
                              │ PRE_REPAIR_      │             │
                              │  BASELINE        │             │
                              └───────┬──────────┘             │
                                      │                       │
                              ┌───────▼──────────┐             │
                              │  REPAIR_IN_      │             │
                              │  PROGRESS        │             │
                              └───────┬──────────┘             │
                                      │                       │
                              ┌───────▼──────────┐             │
                              │ POST_REPAIR_     │             │
                              │  BASELINE        │             │
                              └───────┬──────────┘             │
                                      │                       │
                              ┌───────▼──────────┐             │
                              │ EFFECTIVE-       │             │
                              │   NESS_          │             │
                              │  VALIDATED       │             │
                              └───────┬──────────┘             │
                                      │                       │
                    ┌─────────────────┴────────────────────────┘
                    │
         ┌──────────▼──────────┐
         │    BACK_TO_NORMAL   │
         └──────────┬──────────┘
                    │
                    ▼
         ┌───────────────────┐
         │   MONITORING      │
         └───────────────────┘
```

## Implementation

The state machine is implemented in `backend/app/services/workflow_orchestrator.py`:

```python
class AssetWorkflowOrchestrator:
    def __init__(self):
        # In-memory state storage (demo scope)
        self._equipment_states: Dict[str, WorkflowState] = {}
        self._state_history: Dict[str, List[StateTransition]] = {}

    def _set_state(self, equipment_id: str, state: WorkflowState):
        """Set equipment state and record transition"""
        # Record transition in history
        # Update current state
        # Log transition
```

## State Persistence

**Current Implementation:** In-memory (demo scope)
**Future Enhancement:** Database table

```sql
-- Future: Asset workflow state persistence
CREATE TABLE asset_workflow_states (
    equipment_id TEXT PRIMARY KEY,
    current_state TEXT NOT NULL,
    state_history JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## Next Steps

1. Implement automated state transitions in workflow orchestrator
2. Add state transition logging to audit trail
3. Create state monitoring dashboard
4. Add state timeout alerts (e.g., stuck in REPAIR_IN_PROGRESS > 7 days)
