---
title: "PARASITE Three-Tier Autonomous Control Architecture for Niagara BMS"
type: "architecture"
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

# PARASITE Three-Tier Autonomous Control Architecture for Niagara BMS

**Phase:** 67-04 (PARASITE Architecture Design)
**Objective:** Design three-tier autonomous control architecture specifically for Niagara BACnet devices
**Date:** 2026-02-11
**Status:** ✅ Complete

---

## Executive Summary

PARASITE (Predictive Automation for Resource Scheduling in Intelligent Thermal Environments) is SENTINEL BMS's autonomous control system for Niagara BACnet equipment. This document specifies a **three-tier autonomy model** that safely transitions from human-advisory recommendations (Tier 1) → human-approved control (Tier 2) → autonomous control (Tier 3) based on proven decision accuracy and safety constraints.

**Key Architecture Decisions:**
- **Tier 1 (ADVISOR):** Read-only, no Niagara writes, pure recommendation engine
- **Tier 2 (SUPERVISED):** User approval required, Niagara writes with rollback capability
- **Tier 3 (PARASITE):** Full autonomy for safe actions (setpoint adjustments), approval required for risky actions (equipment on/off)
- **Safety-First Approach:** All control points validated through SafetyEngine before write execution
- **Continuous Learning:** Every decision feeds back to ML models for automatic improvement
- **Graceful Degradation:** If decision quality drops, system automatically falls back to lower tier

---

## Table of Contents

1. [Three-Tier Autonomy Model](#three-tier-autonomy-model)
2. [Tier Comparison Matrix](#tier-comparison-matrix)
3. [Niagara Control Examples Per Tier](#niagara-control-examples-per-tier)
4. [Confidence Thresholds for Control Actions](#confidence-thresholds-for-control-actions)
5. [Safety Constraints (Never Override)](#safety-constraints-never-override)
6. [Niagara BACnet Priority Mapping](#niagara-bacnet-priority-mapping)
7. [Rollback Mechanisms](#rollback-mechanisms)
8. [Learning System for Tier 3](#learning-system-for-tier-3)
9. [Tier Transition Criteria](#tier-transition-criteria)
10. [Architecture Decision Rationale](#architecture-decision-rationale)

---

## Three-Tier Autonomy Model

### Tier 1: ADVISOR (Read-Only Advisory System)

**Purpose:** Provide AI-driven recommendations without any remote control authority

**How It Works:**
1. PARASITE reads Niagara data via BACnet COV subscriptions
2. Analyzes equipment status, historical trends, weather, occupancy
3. Generates natural-language recommendations for technicians
4. Technician reads recommendation and manually implements change
5. Manual login to Niagara/building system to adjust setpoints

**Example Workflow:**
```
PARASITE observation: Chiller cooling_setpoint=8°C, supply_temp=7°C (very cold)
PARASITE analysis: Chiller overshooting target, consuming excess energy
PARASITE recommendation: "Chiller supply temp too cold (7°C). Lower setpoint
                         to 9°C to stabilize efficiency. (~$50/day savings)."
Technician action: "Got it. Logging into Niagara now." → Manual setpoint adjustment
Outcome: Documented improvement, technician marked feedback
```

**Characteristics:**
- ❌ **No Niagara writes:** PARASITE never modifies equipment
- ✅ **Read-only:** Full visibility of equipment state
- ✅ **Explainable:** Every recommendation includes reasoning
- ⚠️ **Limited feedback:** Depends on technician compliance
- ⚠️ **Slow response:** Hours/days delay between recommendation and action

**Use Cases:**
- Initial system deployment (proving system reliability)
- Unfamiliar buildings (before safety profiles established)
- Training mode (technicians learning PARASITE behavior)
- Manual override preference (ops prefers full control)

**Safety Level:** 🟢 **SAFE** - No risk (read-only system)

---

### Tier 2: SUPERVISED (Human-in-Loop Approval)

**Purpose:** Enable automated Niagara writes with operator approval and rollback capability

**How It Works:**
1. PARASITE analyzes equipment state and generates control recommendation
2. Recommendation includes: action, confidence score, reason, expected outcome
3. Dashboard displays: `"Lower chiller to 7°C? [Approve] [Reject]"` with details
4. User clicks `[Approve]` → PARASITE executes Niagara write immediately
5. COV subscription monitors if setpoint actually changed
6. If approved action doesn't complete, auto-rollback to original value
7. Audit trail captures: who approved, what was written, result

**Example Workflow:**
```
┌─────────────────────────────────────────────────────────────────┐
│ PARASITE Decision Engine                                        │
├─────────────────────────────────────────────────────────────────┤
│ Current state: Chiller load 95%, cooling_setpoint=8°C           │
│ ML prediction: 88% confidence → temperature drop imminent       │
│ Recommendation: Lower setpoint to 7°C (increase cooling margin) │
│ Action type: SAFE (within 4-12°C constraint)                    │
│ Confidence: 88% > 70% threshold ✓                               │
│ Tier 2 decision: REQUIRE USER APPROVAL                          │
└─────────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ Dashboard Notification                                          │
├─────────────────────────────────────────────────────────────────┤
│ CHILLER optimization                                             │
│ Current: 8°C, Proposed: 7°C                                     │
│ Reason: Load increasing (95%), prevent overshooting             │
│ Confidence: 88%                                                 │
│ Safety: ✓ Within range [4°C-12°C]                               │
│                                                                 │
│ [APPROVE CONTROL] [REJECT] [MORE INFO]                          │
└─────────────────────────────────────────────────────────────────┘
                         ↓
                    User Approves
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ Niagara Write Execution                                         │
├─────────────────────────────────────────────────────────────────┤
│ POST /api/niagara/bacnet/devices/5/points/AO/100/write          │
│ Payload: {value: 7, priority: 8, timeout: 30min}                │
│ Wait 5s for write confirmation...                               │
│ Response: {success: true, device_id: 5, value: 7}               │
│ Status: ✓ Write successful                                      │
└─────────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ COV Monitoring (Real-Time Feedback)                             │
├─────────────────────────────────────────────────────────────────┤
│ Subscribe to: cooling_setpoint changes                          │
│ Expected: setpoint → 7°C within 30 seconds                      │
│ Verify: Read current value, confirm = 7°C                       │
│ Timeline: 1-2 minutes for full verification                     │
│ Status: ✓ Setpoint confirmed at 7°C                             │
└─────────────────────────────────────────────────────────────────┘
                         ↓
              Result logged to audit trail
            ✓ Action approved by: technician@site-002
            ✓ Niagara write: cooling_setpoint 8°C → 7°C
            ✓ Verification: COV confirmed change
            ✓ Health impact: +2 (efficiency improved)
```

**Timeout & Rollback:**
- If approved action doesn't complete within 30 minutes:
  - User can manually click `[REVERT]` button to rollback original value
  - OR system auto-reverts after 30-min timeout
  - Reason: Assumes user forgot or changed mind

**Characteristics:**
- ✅ **Operator controlled:** User approves each action
- ✅ **Fast execution:** Seconds between approval and Niagara write
- ✅ **Verified:** COV feedback confirms write success
- ✅ **Auditable:** Complete approval → action → outcome trail
- ✅ **Reversible:** Explicit rollback or timeout revert
- ⚠️ **Requires availability:** Ops must respond to notifications
- ⚠️ **Manual feedback:** Depends on technician compliance for learning

**Use Cases:**
- Production deployment with human oversight
- Building occupied (occupants present, need conservative control)
- New equipment types (until models proven reliable)
- Peak energy periods (demand response with operator approval)
- Training phase (building team confidence in autonomous system)

**Safety Level:** 🟡 **GUARDED** - Safe with operator verification

---

### Tier 3: PARASITE (Full Autonomous Control)

**Purpose:** Execute safe equipment control automatically without approval for routine actions

**How It Works:**
1. PARASITE analyzes equipment state and generates control recommendation
2. Checks confidence score: 85%+ for safe actions = auto-execute
3. Checks SafetyEngine: Setpoint within 4-12°C for chiller? ✓
4. Executes Niagara write immediately (no approval required)
5. COV subscription verifies outcome within 5 seconds
6. If write failed: Auto-rollback to original value, alert ops
7. Continuous feedback: Every outcome trains ML models
8. Graceful degradation: If success rate drops, fallback to Tier 2

**Example Workflow - Safe Action (Setpoint Adjustment):**
```
Chiller loading 95%, confidence 92% → Lower setpoint 8°C → 7°C
Decision: Routine adjustment, within safety range
Approval: ✓ AUTO-EXECUTE (no user needed)

                    ↓
POST /api/niagara/bacnet/devices/5/points/AO/100/write
value: 7, priority: 8
                    ↓
Response: success=true, value=7
                    ↓
COV Monitoring: setpoint confirmed 7°C
                    ↓
Outcome: Success → Log decision → Train ML model
```

**Example Workflow - Risky Action (Equipment On/Off):**
```
Generator load shedding detected, confidence 88% → Start generator
Decision: Equipment start is risky (fuel consumption, noise)
Approval: ✗ USER APPROVAL REQUIRED (dangerous action)

Dashboard notification: "Load shedding detected. Start generator? [APPROVE]"
User clicks APPROVE
                    ↓
PARASITE executes write → Verify generator started
                    ↓
Outcome: Success → Log decision → Train ML model
```

**Decision Quality Monitoring:**
- PARASITE tracks: decisions made, outcomes verified, success rate
- Every 100 decisions: Calculate success rate
- Success rate > 95%? Continue Tier 3
- Success rate < 90%? Log warning, prepare fallback to Tier 2
- Success rate < 85%? Auto-fallback to Tier 2, alert ops
- Reason: System is making bad decisions, needs human oversight again

**Auto-Rollback on Failure:**
```
Write decision: Lower setpoint to 7°C
Expected outcome: COV shows setpoint = 7°C within 5 seconds
Actual outcome: COV timeout (no change detected)
            ↓
FAILURE DETECTED
            ↓
Auto-rollback: Restore original setpoint (8°C)
Log: "PARASITE write failed for cooling_setpoint"
Alert: Ops sees notification
Impact: Equipment health flagged, manual intervention recommended
```

**Characteristics:**
- ✅ **Autonomous execution:** Seconds between decision and action
- ✅ **Explainable:** Decision logged with confidence, reasoning
- ✅ **Verified:** COV ensures write success
- ✅ **Self-correcting:** Auto-rollback on failures
- ✅ **Learning:** Every outcome feeds to ML retraining
- ✅ **Graceful degradation:** Falls back to Tier 2 if quality drops
- ⚠️ **Requires proven accuracy:** Only safe after 30 days > 95% success
- ⚠️ **Requires extensive testing:** Cannot deploy without validation

**Safe Action Types (Auto-Execute in Tier 3):**
- ✅ Setpoint adjustments ±1°C (high confidence, small change)
- ✅ Setpoint adjustments ±2°C (very high confidence, thermal mass protects)
- ✅ Damper position adjustments (low inertia, quick to react)
- ✅ Fan speed adjustments (reversible, low risk)
- ✅ Lighting dimming (zero safety risk)

**Risky Action Types (Require Approval even in Tier 3):**
- ❌ Equipment on/off (high energy impact, occupant impact)
- ❌ Load shedding commands (grid coordination required)
- ❌ UPS mode switching (power quality impact)
- ❌ Generator start (fuel consumption, emissions)
- ❌ Chiller compressor enable/disable (major efficiency impact)

**Use Cases:**
- Mature deployment (system proven, 30+ days > 95% success)
- Optimized buildings (energy savings, demand response)
- Unoccupied facilities (no occupant impact concern)
- Critical infrastructure (reliability optimization)
- Peak demand response (grid support, economic incentives)

**Safety Level:** 🟡 **CONDITIONAL** - Safe with proven accuracy + auto-rollback

---

## Tier Comparison Matrix

| Aspect | Tier 1: ADVISOR | Tier 2: SUPERVISED | Tier 3: PARASITE |
|--------|-----------------|-------------------|------------------|
| **Autonomy Level** | Advisory only | Controlled action | Full autonomy (safe) + approval (risky) |
| **Approval** | Manual by technician | User dashboard approval | Auto for routine, user for risky |
| **Niagara Write** | ❌ No | ✅ Yes (on approval) | ✅ Yes (immediate for safe) |
| **Response Time** | Hours/days | Seconds | < 1 second |
| **Rollback** | N/A (read-only) | Manual + 30min timeout | Auto-rollback on failure |
| **Learning** | ⚠️ Limited (manual feedback) | ⚠️ Partial (feedback on approval) | ✅ Continuous (every outcome) |
| **Decision Confidence Threshold** | N/A | 70%+ for approval suggestion | 85%+ auto-execute (safe), 95%+ risky |
| **Safety Validation** | ✓ Read-only safe | ✓ SafetyEngine checks | ✓ SafetyEngine + auto-rollback |
| **COV Feedback** | N/A | ✓ Verifies writes | ✓ Verifies + triggers rollback |
| **Audit Trail** | Recommendations | Approval + write + outcome | All decisions + outcomes |
| **Failure Handling** | N/A | Manual revert | Auto-revert + fallback to Tier 2 |
| **Use Case** | Initial deployment, training | Production with oversight | Optimized, proven systems |
| **Deployment Duration** | Week 1 (baseline) | Week 2-4 (testing) | Month 2+ (after 30 days proven) |

---

## Niagara Control Examples Per Tier

### Example 1: Chiller Setpoint Adjustment

**Context:** Chiller supply temperature too cold (7°C), wasting energy. PARASITE detects opportunity to raise setpoint from 8°C to 9°C.

**Tier 1 (ADVISOR):**
```
PARASITE Dashboard Recommendation:
┌─────────────────────────────────────────────────────┐
│ Chiller Optimization Opportunity                    │
├─────────────────────────────────────────────────────┤
│ Equipment: S002-CHILLER-B1-001                      │
│ Current State: supply_temp=7°C, setpoint=8°C        │
│ Issue: Supply temp below setpoint (8°C)             │
│ Reason: Chiller overshooting, wasting energy        │
│ Recommendation: Raise setpoint to 9°C               │
│ Expected Benefit: $50/day energy savings             │
│ Action Required: Manual login to Niagara            │
│ Technician: Manual setpoint adjustment              │
└─────────────────────────────────────────────────────┘

Technician action: Opens Niagara UI, finds chiller, manually
                   adjusts cooling_setpoint from 8°C to 9°C
Result: Change logged, feedback recorded
Timeline: 1-2 hours (technician availability dependent)
```

**Tier 2 (SUPERVISED):**
```
PARASITE Dashboard Notification:
┌─────────────────────────────────────────────────────┐
│ Chiller Control Action - Approval Required          │
├─────────────────────────────────────────────────────┤
│ Equipment: S002-CHILLER-B1-001                      │
│ Proposed Action: Lower cooling_setpoint             │
│ From: 8°C → To: 9°C                                 │
│ Reason: Supply temp overshooting (7°C)              │
│ Confidence: 88% (within safety margin)              │
│ Safety: ✓ Setpoint in range [4°C-12°C]              │
│ Expected Benefit: $50/day energy savings             │
│ Duration: Applies for 30 minutes (or until reverted)│
│                                                      │
│ [APPROVE] [REJECT] [MORE INFO]                      │
└─────────────────────────────────────────────────────┘

User clicks [APPROVE]
           ↓
PARASITE executes: POST /api/niagara/bacnet/devices/5/points/AO/100/write
                   {value: 9, priority: 8}
           ↓
Response: {success: true, device_id: 5}
           ↓
COV Monitoring: Setpoint confirmed changed to 9°C
           ↓
Audit log: User "technician@site-002" approved chiller control
          PARASITE wrote cooling_setpoint 8°C → 9°C
          COV verified: Change successful
          Health impact: +2 (efficiency improved)

Timeline: 5-10 seconds (notification to write execution)
Result: Immediate savings, automatic feedback for learning
```

**Tier 3 (PARASITE):**
```
Background Process (No User Intervention):
┌─────────────────────────────────────────────────────┐
│ PARASITE Autonomous Decision Engine                 │
├─────────────────────────────────────────────────────┤
│ Monitor: Chiller supply_temp < 8°C for 5 min        │
│ Analysis: Overshooting detected (88% confidence)    │
│ Decision: Lower setpoint to 9°C (safe action)       │
│ Safety: ✓ Within 4-12°C range                       │
│ Confidence: 88% > 85% threshold ✓                   │
│ Action: AUTO-EXECUTE                                │
└─────────────────────────────────────────────────────┘
           ↓
Execute: POST /api/niagara/bacnet/devices/5/points/AO/100/write
         {value: 9, priority: 8}
           ↓
Response: {success: true}
           ↓
Verify: COV subscription confirms setpoint = 9°C (5 sec)
           ↓
Log: Autonomous decision executed successfully
     Supply temp trend: 7°C → 11°C (goal achieved)
     Health impact: +2 (efficiency improved)
     Success tracked: +1 to accuracy metric
           ↓
Learning: Add to ML training data
         Decision pattern: "overshooting supply temp" → "raise setpoint"
         Outcome: "positive energy savings"
         Feedback: Model confidence increases

Timeline: <1 second (autonomous decision + execution)
Result: Continuous optimization, improved decision quality over time
```

### Example 2: Generator Start (Risky Action)

**Context:** Load shedding event detected (grid frequency dropping). PARASITE should start backup generator to support grid.

**Tier 1 (ADVISOR):**
```
PARASITE Recommendation:
  "Load shedding detected (grid freq 49.8Hz).
   Recommend starting backup generator to support grid
   and reduce facility load. Manual action required."

Technician: Manual generator start
Timeline: Hours (ops team coordination needed)
```

**Tier 2 (SUPERVISED):**
```
PARASITE Notification:
  "Load shedding support needed. Start generator? [APPROVE]"
  Confidence: 92%
  Duration: Duration of load shedding event (auto-stop)
  Safety: ✓ Runtime > 5min minimum

User: Clicks [APPROVE]
           ↓
PARASITE: Sends generator start command to Niagara
         Monitors: Generator status, load shedding duration
         Auto-stop: When frequency recovers
Timeline: Seconds
```

**Tier 3 (PARASITE):**
```
Tier 3 decision for generator start: NOT AUTO-EXECUTED
Reason: Equipment on/off is risky (fuel, noise, coordination)
         Requires user approval even in Tier 3

Notification: "Load shedding detected. Start generator? [APPROVE]"
User: Clicks [APPROVE] (same as Tier 2)
Result: Autonomous decision with user gate (hybrid model)
```

---

## Confidence Thresholds for Control Actions

**Key Concept:** Different actions require different confidence levels based on safety and impact.

| Action Type | Description | Tier 2 Threshold | Tier 3 Auto-Execute | Tier 3 Risky | Auto-Rollback Trigger |
|-------------|-------------|------------------|-------------------|---------------|-----------------------|
| **Setpoint ±1°C** | Small thermal adjustment | 70% | 85% | N/A | No change in 5 min |
| **Setpoint ±2°C** | Moderate thermal adjustment | 85% | 92% | N/A | No change in 5 min |
| **Damper 0-50%** | Damper position small change | 70% | 85% | N/A | No change in 5 min |
| **Fan speed** | Fan speed adjustment | 70% | 85% | N/A | No change in 5 min |
| **Lighting dim** | Lighting level adjustment | 60% | 75% | N/A | No change in 2 min |
| **Equipment on/off** | Start/stop equipment | 90% | 95%* | **✓ Requires approval** | Device didn't respond in 10 sec |
| **Load shedding** | Demand response action | 95% | 98%* | **✓ Requires approval** | Grid freq didn't improve in 2 min |
| **UPS mode** | UPS mode switching | 90% | 95%* | **✓ Requires approval** | Mode didn't change in 5 sec |

*Even in Tier 3, these risky actions require user approval due to high impact/energy consumption

**Threshold Rationale:**
- **Setpoint ±1°C:** Thermal mass protects against overshoot, safe range wide (16-28°C)
- **Setpoint ±2°C:** Larger change, requires higher confidence
- **Equipment on/off:** Risky (major energy, duration), always requires approval
- **Load shedding:** Grid coordination, always requires approval
- **Lighting:** Occupant comfort (low risk of harm), can be more aggressive

---

## Safety Constraints (Never Override)

**Critical:** These constraints NEVER override, even in Tier 3 autonomous mode. SafetyEngine enforces at write time.

### Temperature Constraints

| Equipment Type | Min Temp | Max Temp | Reason | SafetyEngine Rule |
|---|---|---|---|---|
| **Building comfort zone** | 16°C | 28°C | Building code + occupant comfort | TempRange(16-28) |
| **Chiller cooling_setpoint** | 4°C | 12°C | Freeze protection on chilled water | TempRange(4-12) |
| **AHU supply_temp** | 10°C | 25°C | Occupant comfort + freeze protection | TempRange(10-25) |
| **FCU zone_setpoint** | 16°C | 28°C | Occupant comfort | TempRange(16-28) |

### Equipment Operating Constraints

| Equipment | Constraint | Reason | SafetyEngine Rule |
|---|---|---|---|
| **Chiller compressor** | Min runtime 5 min | Prevent short-cycling (compressor damage) | RuntimeLimit(5min) |
| **AHU damper** | 0-100% range | Stuck damper = building uninhabitable | DamperRange(0-100) |
| **FCU fan speed** | 0-100% smooth ramp | Sudden changes = occupant discomfort | FanSpeedRamp(max=10%/min) |
| **VAV damper** | 0-100% position | Minimum airflow for IAQ | AirflowMin(20CFM) |
| **DALI lighting** | 10-90% brightness | Minimum visibility, maximum comfort | BrightnessRange(10-90) |
| **Generator** | Min 5 min runtime | Fuel efficiency, engine warm-up | RuntimeLimit(5min) |
| **UPS** | Only in eco/online mode | Safety modes only | UPSModeWhitelist(eco, online) |

### Priority Array Constraints

Niagara BACnet priority array resolution (lowest priority number wins):

| Priority | Owner | Authority |
|----------|-------|-----------|
| **1** | Safety system | Emergency stop, freeze protection (HIGHEST PRIORITY) |
| **2** | Building code | Min 16°C enforcement |
| **6** | Manual technician | Technician manual override (overrides PARASITE) |
| **8** | PARASITE | Autonomous control (manual operator level) |
| **14** | Scheduling | Standard occupancy setback |
| **16** | Default values | System defaults (LOWEST PRIORITY) |

**Implication:** If technician manually sets setpoint to 8°C (priority 6), PARASITE cannot override it (priority 8 < 6 means technician wins). PARASITE can only write at priority 8 or lower.

### Interlock Dependencies

Equipment cannot be controlled independently; some actions block others:

| Interlock | Rule | Reason |
|-----------|------|--------|
| **Pump → Chiller** | Cannot stop pump if chiller running | Freeze protection on chilled water lines |
| **Damper → AHU** | Cannot close damper if AHU is supplying | Ductwork pressurization |
| **Compressor → Pump** | Cannot stop compressor if system needs cooling | Cascade failure |
| **Generator → Load** | Cannot start generator without load | Overspeeding damage |
| **UPS → System Load** | Cannot switch modes during critical load | Power quality loss |

---

## Niagara BACnet Priority Mapping

**Context:** Niagara BACnet devices use a priority array (16 levels, 1-16). Lowest priority number wins in a conflict.

### PARASITE Priority Strategy

```
Priority 1-5:  RESERVED for safety/building code (never override)
Priority 6:    MANUAL TECHNICIAN (technician overrides PARASITE)
Priority 7:    RESERVED for future use
Priority 8:    PARASITE AUTONOMOUS CONTROL ← PARASITE writes here
Priority 9-13: RESERVED
Priority 14:   OCCUPANCY SCHEDULING (standard setback)
Priority 15-16: DEFAULTS (lowest priority)
```

**Example Resolution:**
```
Scenario 1: Normal operation (no technician override)
  Setpoint levels at different priorities:
    Priority 8 (PARASITE): 9°C
    Priority 14 (Schedule): 10°C
    Priority 16 (Default): 20°C
  Result: 9°C wins (lowest priority number)

Scenario 2: Technician manual override
  Setpoint levels at different priorities:
    Priority 6 (Technician): 8°C ← Technician logged in and changed it
    Priority 8 (PARASITE): 9°C
    Priority 14 (Schedule): 10°C
  Result: 8°C wins (technician always wins)
  Action: PARASITE recognizes override, switches to Tier 2 (supervised only)

Scenario 3: Safety constraint enforcement
  Priority 1 (Safety): 16°C (building code minimum) ← Always enforced
  Priority 6 (Technician): 15°C (technician tries to set too cold)
  Result: 16°C wins (safety cannot be overridden)
  Action: PARASITE write rejected, alert logged
```

---

## Rollback Mechanisms

### Tier 1: No Rollback (Read-Only)
- Tier 1 never writes to Niagara, so no rollback needed

### Tier 2: Manual Rollback + Timeout

**Explicit Rollback (User-Initiated):**
```
Scenario: User approved chiller setpoint change 30 minutes ago
         But wants to cancel it now

User action: Dashboard shows active control, click [REVERT]
             ↓
PARASITE: Restores original setpoint to what it was before approval
          Example: Revert 9°C back to 8°C
             ↓
Niagara: Write reversal executed immediately
             ↓
Audit log: "User reverted chiller control at [timestamp]"
```

**Automatic Timeout Rollback:**
```
Scenario: User approved chiller setpoint change 25 minutes ago
         But forgot to revert and is now offline

Timeout trigger: 30-minute timer elapsed
             ↓
PARASITE: Auto-reverts original setpoint
          Example: Revert 9°C back to 8°C automatically
             ↓
Niagara: Write reversal executed
             ↓
Audit log: "Timeout revert: User-approved control reverted after 30min"
Alert: "Chiller control reverted (timeout). Review and reapply if needed."
```

**Implementation Detail:**
- Each Tier 2 write stores: `original_value`, `approval_time`, `approved_by`
- Background job checks every minute: Is any Tier 2 control > 30 min old?
- If yes: Execute rollback, log revert event
- Alert ops if automatic rollback occurred (user should know)

### Tier 3: Automatic Rollback on Failure

**Failure Detection:**
```
PARASITE writes: cooling_setpoint = 9°C

Expected outcome: COV event → setpoint = 9°C within 5 seconds
Actual outcome: COV timeout (no change detected)

             ↓ FAILURE DETECTED

Auto-rollback trigger: No COV event in 5 seconds
             ↓
Action: Read current setpoint value
        If still = 8°C (original), write was never applied
             ↓
        Execute rollback: Write original value (8°C) again
             ↓
Audit log: "PARASITE write failed, auto-rollback executed"
Alert: "Chiller control write failed. Manual intervention may be needed."
```

**Root Cause Scenarios:**
1. **Device timeout:** Niagara device didn't respond → Write never reached device
2. **Write rejected:** SafetyEngine or device blocked write (e.g., safety rule violation)
3. **Device offline:** Device went offline during write → Write lost
4. **Network failure:** Network interrupted between PARASITE and Niagara

**Rollback Outcome:**
- Equipment stays at original value (safe)
- Audit logged: PARASITE detected failure, reverted automatically
- ML model: This decision marked as "failed", confidence decreases
- Alert: Ops notified, may need manual intervention
- Health impact: Equipment flagged for manual inspection

---

## Learning System for Tier 3

**Purpose:** Every autonomous decision improves the ML models for future decisions

### Decision-Outcome Tracking

**Every Tier 3 autonomous write generates:**
```
{
  "decision_id": "d5f8a2c1-4e9b-11ed-8b5d-001",
  "timestamp": "2026-02-11T14:30:00Z",
  "equipment_id": "S002-CHILLER-B1-001",
  "equipment_type": "CHILLER",
  "action": "lower_setpoint",
  "original_value": 8.0,
  "new_value": 7.0,
  "confidence": 0.88,
  "confidence_level": "HIGH",
  "decision_reason": "Supply temp overshooting, energy waste detected",
  "safety_checks": {
    "range_check": "PASS (within 4-12°C)",
    "interlock_check": "PASS (pump running)",
    "priority_check": "PASS (technician not override)"
  },
  "write_status": "SUCCESS",
  "cov_verification": {
    "expected": 7.0,
    "actual": 7.0,
    "verified_at": "2026-02-11T14:30:05Z",
    "verification_success": true
  },
  "outcome": {
    "duration_minutes": 10,
    "supply_temp_before": 7.0,
    "supply_temp_after": 11.0,
    "supply_temp_delta": 4.0,
    "energy_impact_kwh": -2.5,
    "energy_cost_saving": 50,
    "occupant_complaints": 0,
    "equipment_health_before": 85,
    "equipment_health_after": 87,
    "health_delta": 2,
    "success": true,
    "success_reason": "Setpoint change achieved desired effect"
  }
}
```

### Feedback Loop (Automatic)

**Every 10 minutes:**
1. Query Tier 3 decisions executed in last 10 minutes
2. For each decision: Pull outcome data (from COV subscriptions, sensors)
3. Calculate impact: Energy saved? Occupant complaints? Equipment improved?
4. Update decision record: Mark success/failure, impact
5. Queue for ML retraining

**Retraining Triggers:**
```
After every 100 autonomous decisions:
  1. Calculate accuracy: % of decisions with positive outcome
  2. Check success rate:
     - > 95%? Continue Tier 3
     - 90-95%? Log warning, stay in Tier 3 with monitoring
     - < 90%? Automatic fallback to Tier 2 (supervised mode)
  3. Retrain model with new data
     - Decision features (setpoint, load, temp) → Outcome (success/failure)
     - Train classifier: Can PARASITE predict if action will help?
     - Calculate new confidence thresholds for next 100 decisions
```

### Graceful Degradation Example

**Scenario:** PARASITE decision quality drops to 85% success rate

```
Day 1 of autonomous control:
  100 decisions executed
  92 successful, 8 failed → 92% success rate
  Action: Continue Tier 3

Day 2 of autonomous control:
  200 decisions total
  175 successful, 25 failed → 87.5% success rate
  Action: Continue Tier 3 with warning logs

Day 3 of autonomous control:
  300 decisions total
  255 successful, 45 failed → 85% success rate
  Warning: "Decision quality below 90%, monitoring closely"

Day 4 of autonomous control (Morning):
  400 decisions total
  330 successful, 70 failed → 82.5% success rate
  Action: AUTOMATIC FALLBACK TO TIER 2

  Dashboard alert:
  "PARASITE decision quality degraded below 85%.
   System reverted to Tier 2 (supervised mode).
   Pending actions will require user approval.
   Engineering team investigating root cause."
```

**Root Cause Analysis:**
- System discovered: New equipment type (VAV boxes) causing failures
- VAV model undertrained (R²=0.317 from Phase 67-03)
- PARASITE decisions for VAVs failing 60% of time
- Fallback protects equipment until VAV model improved

---

## Tier Transition Criteria

### Tier 1 → Tier 2 Transition

**Prerequisite:** System proven safe for weeks in Tier 1

**Criteria:**
- ✅ 100+ hours of safe Tier 1 operation (no incidents)
- ✅ Safety rules tested and working (SafetyEngine blocks unsafe writes)
- ✅ Niagara integration stable (no communication failures)
- ✅ COV subscriptions working (feedback verification working)
- ✅ Ops team trained (dashboard, approval process understood)
- ✅ Business approval (go/no-go decision from facilities leadership)

**Approval Process:**
1. Facilities manager reviews Tier 1 operation logs
2. Engineering signs off: "System ready for supervised control"
3. Ops team conducts approval workflow training
4. Pilot: Start Tier 2 with single equipment type (e.g., only CHILLER)
5. Monitor: 1-2 weeks of supervised control, 0 incidents
6. Expand: Gradually add more equipment types
7. Timeline: 2-4 weeks to full Tier 2 across all equipment

### Tier 2 → Tier 3 Transition

**Prerequisite:** Tier 2 proven reliable and accurate for 30+ days

**Criteria for Safe Actions (setpoint adjustments ±1-2°C):**
- ✅ 30+ consecutive days of Tier 2 operation
- ✅ 95%+ decision accuracy on test dataset
- ✅ 100+ approved actions executed (real user data)
- ✅ 0 safety violations (no unsafe setpoints written)
- ✅ 0 equipment damage incidents
- ✅ Occupant complaints < 1% of actions
- ✅ ML model confidence >= 85% for action type
- ✅ Engineering team validation: Model ready for autonomy
- ✅ Business approval: Go/no-go decision

**Criteria for Risky Actions (equipment on/off):**
- ✅ Additional 30+ days after safe actions deployed
- ✅ Equipment-specific model: R² >= 0.65
- ✅ 100+ examples of equipment on/off in training data
- ✅ 95%+ accuracy on holdout test set
- ✅ Failure mode analysis: What could go wrong? Mitigations?
- ✅ Business sign-off: Energy savings justify risk

**Approval Process:**
1. Review 30 days of Tier 2 metrics
2. Engineering team: Generate accuracy report
   - Historical decisions vs. actual outcomes
   - Failure analysis: Why did bad decisions happen?
   - Recommendations: Is system ready?
3. Team consensus: "Safe for Tier 3" or "Needs more work"
4. If approved:
   - Deploy Tier 3 for 1 equipment type (e.g., CHILLER only)
   - Continue monitoring: Success rate, incidents
   - After 2 weeks: If > 95% success, expand to more equipment
5. Timeline: 60-90 days to full Tier 3 across all equipment

### Fallback: Tier 3 → Tier 2 (Automatic)

**Trigger:** System detects decision quality degradation

**Criteria for Automatic Fallback:**
- ⚠️ Success rate drops below 90%
- 🔴 Success rate drops below 85% → Immediate fallback

**Fallback Process (Automatic, < 1 min):**
1. PARASITE detects: Success rate = 84.5% (below 85% threshold)
2. System action:
   - Stop executing Tier 3 decisions
   - New decisions go to Tier 2 (require approval)
   - Alert ops: "Decision quality issue detected"
3. Engineering investigation:
   - Review failed decisions: Pattern?
   - Check equipment status: Any offline?
   - Check ML models: Accuracy degraded?
   - Root cause: Why is system failing?
4. Resolution:
   - Fix root cause (retrain model, restart equipment, etc.)
   - Monitor 50 new decisions in Tier 2
   - If success rate recovers to 95%: Restore Tier 3
   - If not: Investigate further, may need to stay in Tier 2

---

## Architecture Decision Rationale

### Why Three Tiers?

**Single-tier (Tier 3 only) is too risky:**
- No operator oversight
- System failures can cascade
- Occupant impact without approval
- Regulatory/compliance concerns

**Two-tier (Tier 1 + Tier 2) is safer but limited:**
- Can't provide autonomous optimization
- Requires operator availability 24/7
- Misses time-critical decisions
- Slow response = less energy savings

**Three tiers (1 + 2 + 3) provides optimal safety vs. capability:**
- Tier 1: Prove system safe (read-only)
- Tier 2: Build operator trust (slow, supervised)
- Tier 3: Deliver efficiency gains (fast, autonomous)
- Graceful degradation: Falls back to lower tier if issues

### Why COV Feedback Verification?

**Question:** Why require COV feedback after every Niagara write?

**Answer:** Failure detection and auto-rollback

**Failure modes without verification:**
```
Scenario 1: Network interruption
  PARASITE: "Write setpoint to 9°C"
  Niagara: (network down, message never arrives)
  Equipment: Still at 8°C
  Without COV: PARASITE thinks success (no feedback loop)
  With COV: PARASITE detects no change, auto-rollbacks

Scenario 2: Device offline
  PARASITE: "Write setpoint to 9°C"
  Device: (offline for maintenance)
  Equipment: Can't receive command
  Without COV: PARASITE thinks success
  With COV: PARASITE detects no change, auto-rollbacks

Scenario 3: Priority conflict
  PARASITE: "Write setpoint to 9°C at priority 8"
  Technician: (overrides at priority 6, writes 8°C)
  Equipment: Conflicting writes, device takes priority 6
  Without COV: PARASITE thinks setpoint is 9°C (wrong)
  With COV: PARASITE reads actual value, sees 8°C, logs conflict
```

**Conclusion:** COV feedback is critical for safety. Every write must be verified.

### Why Confidence Thresholds?

**Question:** Why different confidence levels for different actions?

**Answer:** Risk-reward tradeoff

```
Setpoint ±1°C:
  Risk: Low (thermal mass protects, occupant comfort wide margin)
  Benefit: Medium (small energy savings)
  Decision: Auto-execute at 85% confidence

Equipment on/off:
  Risk: High (major energy change, occupant impact, fuel cost)
  Benefit: Medium (energy response, cost savings)
  Decision: Require approval even at 95% confidence

Rationale: Low-risk actions can be autonomous with modest confidence
          High-risk actions need high confidence + approval
```

### Why Graceful Degradation?

**Question:** Why fall back to Tier 2 if decision quality drops?

**Answer:** Protect against slow failures

```
Scenario: ML model gradually becomes less accurate
  Day 1: 95% success rate → Continue Tier 3
  Day 5: 92% success rate → Log warning, continue
  Day 10: 88% success rate → Fallback to Tier 2

Benefit: System catches issues before major failure
         Operators notified before things get bad
         Equipment protected by supervised control

Alternative (no graceful degradation):
  Day 1-9: System slowly failing (undetected)
  Day 10: Catastrophic failure (equipment damage, occupant impact)
```

---

## Summary

PARASITE's three-tier architecture balances safety, reliability, and efficiency:

1. **Tier 1 (ADVISOR):** Prove system safe with read-only recommendations
2. **Tier 2 (SUPERVISED):** Build operator trust with approval-based control
3. **Tier 3 (PARASITE):** Deliver efficiency with autonomous control + safeguards

**Key Safety Features:**
- ✅ SafetyEngine validates all writes (constraints enforced)
- ✅ COV feedback verifies success (auto-rollback on failure)
- ✅ Confidence thresholds control autonomy level
- ✅ Graceful degradation protects against model drift
- ✅ Audit trail enables investigation and learning

**Key Efficiency Features:**
- ✅ Sub-second response time (autonomous tier)
- ✅ Continuous learning (every outcome trains models)
- ✅ Multi-system optimization (coordinate HVAC + lighting + power)
- ✅ 24/7 availability (no operator bottleneck)

**Deployment Timeline:**
- Week 1-2: Tier 1 (read-only, safe)
- Week 2-4: Tier 2 (supervised, operational)
- Month 2+: Tier 3 (autonomous, optimized)

---

## Next Steps

This architecture document feeds into three downstream tasks:

1. **Task 2 (This Phase):** `parasite-niagara-data-flow.md` - Complete data flow diagram
2. **Task 3 (This Phase):** `68-NIAGARA-IMPLEMENTATION.md` - Implementation roadmap for phases 68-70
3. **Task 4 (This Phase):** `parasite-niagara-gaps-and-blockers.md` - Identified blockers to address

---

**Created:** 2026-02-11
**Phase:** 67-04 (PARASITE Niagara Architecture Design)
**Status:** ✅ Complete
