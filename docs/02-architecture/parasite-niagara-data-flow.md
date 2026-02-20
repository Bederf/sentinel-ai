# PARASITE Niagara Data Flow: Complete Decision-to-Control Pipeline

**Phase:** 67-04 (PARASITE Architecture Design)
**Objective:** Design complete data flow from Niagara sensor → PARASITE decision → write → feedback
**Date:** 2026-02-11
**Status:** ✅ Complete

---

## Executive Summary

This document specifies the complete data flow for PARASITE autonomous control, from real-time sensor data collection through decision-making to Niagara equipment writes and feedback verification. The pipeline has 6 distinct stages:

1. **Input Stage:** Real-time data collection from Niagara BACnet devices via COV subscriptions
2. **Decision Stage:** ML predictions + AI optimization + safety validation
3. **Action Stage:** Niagara BACnet write execution with priority handling
4. **Monitoring Stage:** Real-time feedback verification via COV subscriptions
5. **Feedback Loop:** Outcome measurement and health score updates
6. **Learning Stage:** ML model retraining and decision quality assessment

**Key Characteristics:**
- **Real-time:** Event-driven updates (COV) + periodic polling (every 5 min)
- **Safe:** All writes validated through SafetyEngine before execution
- **Verified:** COV feedback confirms write success or triggers auto-rollback
- **Auditable:** Complete decision trail with timestamps and reasoning
- **Learning:** Every outcome feeds back to ML models for continuous improvement

---

## Table of Contents

1. [Data Flow Diagram](#data-flow-diagram)
2. [Stage 1: Input (Niagara Data Collection)](#stage-1-input-niagara-data-collection)
3. [Stage 2: Decision (PARASITE Analysis)](#stage-2-decision-parasite-analysis)
4. [Stage 3: Action (Niagara Write)](#stage-3-action-niagara-write)
5. [Stage 4: Monitoring (Feedback Verification)](#stage-4-monitoring-feedback-verification)
6. [Stage 5: Feedback Loop (Learning)](#stage-5-feedback-loop-learning)
7. [Stage 6: Audit Trail & History](#stage-6-audit-trail--history)
8. [Data Flow Examples](#data-flow-examples)
9. [Error Handling & Recovery](#error-handling--recovery)

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                    NIAGARA BACNET DEVICES                           │
│  (CHILLER, AHU, FCU, VAV, DALI, Generator, UPS, etc.)              │
└─────────────────────────────────────────────────────────────────────┘
         ↑                                        ↑
         │                                        │
    Reads data via               Writes control commands to
    COV subscriptions            points via BACnet priority array
         │                                        │
         ↓                                        ↓
┌─────────────────────────────────────────────────────────────────────┐
│                  STAGE 1: INPUT (Data Collection)                    │
├─────────────────────────────────────────────────────────────────────┤
│  COV Subscriptions:                                                 │
│    - cooling_setpoint, supply_air_temp, return_air_temp            │
│    - compressor_amps, fan_speed, damper_position                   │
│    - equipment_status, occupancy, energy_meters                    │
│                                                                     │
│  Update Triggers:                                                   │
│    - Event-driven: Value change (subscription callback)            │
│    - Periodic: Every 5 minutes (stale data detection)              │
│                                                                     │
│  Data Validation:                                                   │
│    - Range checks: Is value within expected range?                 │
│    - Spike detection: Did value change > expected? (sensor error)  │
│    - Missing value handling: Null/NaN → Use last known good        │
│    - Timeout detection: No update in 5 min? Mark stale             │
└─────────────────────────────────────────────────────────────────────┘
         │
         │ Validated sensor data + historical context
         ↓
┌─────────────────────────────────────────────────────────────────────┐
│              STAGE 2: DECISION (PARASITE Analysis)                   │
├─────────────────────────────────────────────────────────────────────┤
│  A. Current State Analysis:                                         │
│     - Query: What is chiller supply_temp, setpoint, load?          │
│     - Trend: Is it increasing? Stable? Decreasing?                 │
│     - Health: Equipment health_score from database                 │
│     - Context: Occupancy, weather, time-of-day                     │
│                                                                     │
│  B. ML Prediction:                                                  │
│     - Model: LSTM + Autoencoder (trained on historical data)       │
│     - Input: Current state + recent trend data                     │
│     - Output: Probability of failure, recommended action           │
│     - Confidence: % confidence in prediction (0-100%)              │
│                                                                     │
│  C. AI Optimizer Recommendation:                                    │
│     - Algorithm: Multi-objective optimization (energy + comfort)    │
│     - Input: Current state + occupancy profile + ML confidence     │
│     - Output: Specific control action (setpoint, damper, etc.)     │
│     - Reason: Why this action? What's the expected benefit?        │
│                                                                     │
│  D. Safety Validation:                                              │
│     - SafetyEngine checks: Is action within safety constraints?    │
│     - Temperature range: [16°C - 28°C] for comfort zones?          │
│     - Equipment limits: Chiller [4°C - 12°C]?                     │
│     - Interlocks: Can chiller run without pump?                    │
│     - Decision: BLOCK (unsafe) or ALLOW (safe)                     │
│                                                                     │
│  E. Confidence Assessment:                                          │
│     - Threshold check: Confidence > 85% (Tier 3) or 70% (Tier 2)? │
│     - Decision: Auto-execute, require approval, or skip            │
│     - Risk assessment: High-confidence safe actions execute        │
│                        Low-confidence risky actions require approval│
└─────────────────────────────────────────────────────────────────────┘
         │
         │ Decision to execute control action
         ↓
┌─────────────────────────────────────────────────────────────────────┐
│              STAGE 3: ACTION (Niagara Write)                         │
├─────────────────────────────────────────────────────────────────────┤
│  Write Execution:                                                   │
│    POST /api/niagara/bacnet/devices/5/points/AnalogOutput/100/write│
│    Payload:                                                         │
│      {                                                              │
│        "value": 7,              // New setpoint value              │
│        "priority": 8            // PARASITE autonomy level         │
│      }                                                              │
│                                                                     │
│  Timeout: 5 seconds for write acknowledgment                       │
│                                                                     │
│  Response Handling:                                                 │
│    ✓ SUCCESS: {success: true, device_id: 5, value: 7}             │
│    ✗ FAILURE: {success: false, error: "device offline"}           │
│    ✗ TIMEOUT: No response → Assume failure, rollback              │
│                                                                     │
│  Priority Array Resolution:                                         │
│    Niagara applies lowest priority number principle:                │
│    - Priority 1 (Safety): Always wins                              │
│    - Priority 6 (Technician): Overrides PARASITE                   │
│    - Priority 8 (PARASITE): Our autonomous control                 │
│    - Priority 14 (Schedule): Baseline occupancy setback            │
│    Result: If technician logged in, their value wins               │
└─────────────────────────────────────────────────────────────────────┘
         │
         │ Write sent to device
         ↓
┌─────────────────────────────────────────────────────────────────────┐
│          STAGE 4: MONITORING (Feedback Verification)                 │
├─────────────────────────────────────────────────────────────────────┤
│  Immediate Verification (0-30 seconds):                             │
│    - COV Subscription: Monitor cooling_setpoint changes            │
│    - Expected: Point changes from 8°C to 7°C                       │
│    - Detect: COV event shows actual change on device              │
│    - Confirm: Read current value, verify = 7°C                     │
│    - Timeline: 5-30 seconds for confirmation                       │
│                                                                     │
│  Success Cases:                                                     │
│    ✓ COV event received: setpoint = 7°C (write confirmed)          │
│    ✓ Device responds: Setpoint changed as requested                │
│    ✓ Priority conflict resolved: Value at priority 8 was applied   │
│                                                                     │
│  Failure Cases:                                                     │
│    ✗ No COV event: No change detected after 5 sec                  │
│    ✗ Actual != Expected: setpoint is 8°C (write didn't apply)     │
│    ✗ Timeout: Device offline, COV event never arrives              │
│    ✗ Priority conflict: Technician override detected               │
│                                                                     │
│  Auto-Rollback on Failure:                                          │
│    If verification fails:                                           │
│      1. Read current value (double-check it's really failed)      │
│      2. Execute rollback write: POST /write with value=8°C         │
│      3. Verify rollback: Confirm setpoint = 8°C                   │
│      4. Log failure: Decision failed, equipment protected          │
│      5. Alert: Ops notified of control issue                       │
└─────────────────────────────────────────────────────────────────────┘
         │
         │ Outcome data + verification status
         ↓
┌─────────────────────────────────────────────────────────────────────┐
│           STAGE 5: FEEDBACK LOOP (Learning)                         │
├─────────────────────────────────────────────────────────────────────┤
│  Outcome Measurement (next 10 minutes):                             │
│    - Monitor: supply_air_temp trend after setpoint change         │
│    - Expected: Gradual stabilization toward new setpoint          │
│    - Actual: supply_temp increased from 7°C toward 9°C            │
│    - Measure: Energy consumption reduced? Occupants happy?         │
│                                                                     │
│  Health Score Update:                                               │
│    - Before: equipment.health_score = 85                           │
│    - Decision impact: Setpoint adjustment (predicted +2 health)   │
│    - Outcome impact: Energy savings observed (+1 health)           │
│    - After: equipment.health_score = 88                            │
│                                                                     │
│  Decision Outcome Recording:                                        │
│    {                                                                │
│      "decision_id": "d5f8a2c1-4e9b-11ed",                         │
│      "outcome": {                                                   │
│        "write_success": true,                                      │
│        "write_verified": true,                                     │
│        "supply_temp_before": 7.0,                                  │
│        "supply_temp_after": 11.0,                                  │
│        "supply_temp_delta": +4.0,                                  │
│        "energy_kwh_saved": 2.5,                                    │
│        "cost_saved": $50,                                          │
│        "occupant_complaints": 0,                                   │
│        "health_delta": +2,                                         │
│        "success": true                                             │
│      }                                                              │
│    }                                                                │
│                                                                     │
│  ML Training Queue:                                                 │
│    - Add decision/outcome to retraining queue                      │
│    - Queue size: Every 100 decisions → Trigger retraining         │
│    - Features: (equipment_state, action) → (outcome, success)     │
│    - Retrain models: Improve predictions for next 100 decisions   │
│    - Confidence update: Model learns its accuracy range            │
└─────────────────────────────────────────────────────────────────────┘
         │
         │ Decision + outcome logged
         ↓
┌─────────────────────────────────────────────────────────────────────┐
│          STAGE 6: AUDIT TRAIL & HISTORY                             │
├─────────────────────────────────────────────────────────────────────┤
│  Complete Decision Record:                                          │
│    {                                                                │
│      "timestamp": "2026-02-11T14:30:00Z",                         │
│      "equipment_id": "S002-CHILLER-B1-001",                       │
│      "equipment_type": "CHILLER",                                  │
│      "tier": 3,                                                    │
│      "action": "lower_setpoint",                                  │
│      "from": 8.0,                                                  │
│      "to": 7.0,                                                    │
│      "unit": "°C",                                                 │
│      "confidence": 0.88,                                           │
│      "reason": "Supply temp overshooting",                         │
│      "safety_checks": {                                            │
│        "range_ok": true,                                           │
│        "interlock_ok": true,                                       │
│        "priority_ok": true                                         │
│      },                                                             │
│      "write_status": "success",                                    │
│      "cov_verified": true,                                         │
│      "cov_response_time_sec": 5,                                   │
│      "outcome": {                                                   │
│        "success": true,                                            │
│        "supply_temp_delta": +4.0,                                  │
│        "energy_saved_kwh": 2.5,                                    │
│        "health_delta": +2                                          │
│      },                                                             │
│      "searchable_by": [                                            │
│        "equipment", "date", "action", "outcome", "success_rate"    │
│      ]                                                              │
│    }                                                                │
│                                                                     │
│  Dashboard Displays:                                                │
│    - "PARASITE executed 45 control actions this week"             │
│    - "Success rate: 94% (improved from 91% last week)"            │
│    - "Energy savings: $250 from autonomous optimization"           │
│    - "Recent decision: Lowered chiller setpoint (success)"        │
│    - Audit timeline: See all decisions chronologically             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Stage 1: Input (Niagara Data Collection)

### COV Subscription Endpoints

**Endpoint:** `POST /api/niagara/bacnet/subscribe`

**Purpose:** Establish real-time change-of-value subscriptions for equipment points

**Subscription Points Per Equipment Type:**

| Equipment | Points Subscribed | Update Trigger | Min Interval |
|-----------|-------------------|----------------|--------------|
| **CHILLER** | cooling_setpoint, supply_temp, return_temp, compressor_amps, compressor_status | Value change OR timeout | 5 min |
| **AHU** | supply_temp_sp, damper_pos, supply_fan_speed, filter_status | Value change OR timeout | 5 min |
| **FCU** | zone_setpoint, supply_temp, fan_speed, valve_position | Value change OR timeout | 5 min |
| **VAV** | damper_pos, airflow_sp, zone_temp, occupancy | Value change OR timeout | 5 min |
| **DALI** | dim_level (per zone), scene, occupancy_sensor | Value change OR timeout | 5 min |
| **GENERATOR** | status, fuel_level, load_percent, runtime_hours | Value change OR timeout | 5 min |
| **UPS** | mode, battery_voltage, input_select, load_percent | Value change OR timeout | 5 min |
| **METER** | energy_kwh, power_kw, power_factor, frequency | Periodic | 5 min |

### Data Quality Pipeline

**Step 1: Data Reception (Real-Time)**
```
BACnet COV event received:
  Point: cooling_setpoint
  Device: S002-CHILLER-B1-001
  Old value: 8.0°C
  New value: 7.0°C
  Timestamp: 2026-02-11T14:30:05Z
  Source: BACnet COV subscription
```

**Step 2: Range Validation**
```
Expected range for cooling_setpoint: [4°C, 12°C]
Actual value: 7.0°C
Validation: ✓ PASS (within range)
```

**Step 3: Spike Detection**
```
Last value: 8.0°C
New value: 7.0°C
Delta: -1.0°C
Expected max change: ±3°C per 5 min
Validation: ✓ PASS (normal change rate)
```

**Step 4: Missing Value Handling**
```
Scenario: supply_temp = NULL in dataset
Fallback: Use last known good value (7.0°C)
Mark as: "stale" (no recent update)
Age: 5 minutes since last valid reading
Decision: Use value but note staleness in analysis
```

**Step 5: Timeout Detection**
```
Point: compressor_status
Last update: 12:25:00 (5 minutes ago)
Current time: 12:30:00
Age: 5 minutes
Status: STALE (no recent update)
Action: Alert ops, may indicate device offline
```

### Data Storage (Memory + Cache)

```
PARASITE Memory:
{
  "S002-CHILLER-B1-001": {
    "cooling_setpoint": {
      "value": 8.0,
      "unit": "°C",
      "timestamp": "2026-02-11T14:30:00Z",
      "age_seconds": 5,
      "stale": false,
      "data_quality": "GOOD"
    },
    "supply_temp": {
      "value": 7.0,
      "unit": "°C",
      "timestamp": "2026-02-11T14:29:55Z",
      "age_seconds": 10,
      "stale": false,
      "data_quality": "GOOD"
    },
    "compressor_status": {
      "value": "on",
      "timestamp": "2026-02-11T14:25:00Z",
      "age_seconds": 300,
      "stale": true,
      "data_quality": "STALE"
    }
  }
}
```

---

## Stage 2: Decision (PARASITE Analysis)

### 2.1 Current State Query

**Input Data:**
```
Equipment: S002-CHILLER-B1-001
Current state (from PARASITE Memory):
  - cooling_setpoint: 8.0°C
  - supply_temp: 7.0°C (COLD - below setpoint)
  - return_temp: 4.0°C
  - compressor_amps: 45A (running hard)
  - compressor_status: on
  - equipment_health: 85 (good)

Trend analysis (last 30 min):
  - supply_temp: 9°C → 8°C → 7°C (decreasing)
  - compressor_amps: 40A → 42A → 45A (increasing, working harder)
  - Trend direction: DETERIORATING (overcooling)
```

### 2.2 ML Prediction

**Model:** LSTM (Long Short-Term Memory) trained on chiller historical data

**Input Features:**
```
[supply_temp, setpoint, compressor_amps, return_temp,
 occupancy, time_of_day, outside_temp, recent_trend]
```

**Prediction Output:**
```
Equipment: S002-CHILLER-B1-001
Model: LSTM_CHILLER_v3.pkl
Prediction: "Chiller overshooting (supply temp below setpoint)"
Probability: 88%
Confidence: HIGH
Recommended action: Raise setpoint (increase target temp)
Expected benefit: Reduce energy waste, stabilize system
```

### 2.3 AI Optimizer Recommendation

**Algorithm:** Multi-objective optimization (energy minimization + comfort maximization)

**Input:**
```
Current state:
  - cooling_setpoint: 8°C
  - supply_temp: 7°C (cold)
  - occupancy: 80% (building occupied)
  - outdoor_temp: 32°C (hot)

Profiles applied:
  - profile: "COMFORT" (occupants present)
  - optimization_level: "BALANCED" (energy + comfort)

Constraints:
  - Min comfort temp: 16°C
  - Max comfort temp: 28°C
  - Setpoint range: 4-12°C
```

**Optimization Output:**
```
Current setpoint: 8.0°C (too cold, wasting energy)
Optimal setpoint: 9.0°C (achieves comfort with less overcooling)
Change: +1.0°C

Reasoning:
  1. Supply temp (7°C) is below setpoint (8°C) — overcooling
  2. Raising setpoint to 9°C reduces overcooling margin
  3. Building will stay comfortable (warmth range 16-28°C protected)
  4. Compressor will run less hard (45A → ~40A expected)
  5. Energy savings: ~$50/day

Confidence: 88% (model is confident this action will help)
Expected outcome: Supply temp stabilizes at 9°C, comfort maintained
```

### 2.4 Safety Validation

**SafetyEngine Checks:**

1. **Temperature Range Check**
   ```
   Rule: TempRange(4-12°C) for chiller cooling_setpoint
   Proposed value: 9°C
   Min: 4°C, Max: 12°C
   Validation: 4 <= 9 <= 12? ✓ YES (PASS)
   ```

2. **Interlock Check**
   ```
   Rule: Chiller requires pump running
   Current state: pump = ON
   Validation: Pump running? ✓ YES (PASS)
   Decision: Safe to control chiller
   ```

3. **Equipment Status Check**
   ```
   Rule: Equipment must be online to control
   Current state: equipment_status = NORMAL
   Validation: Equipment ready? ✓ YES (PASS)
   ```

4. **Priority Check**
   ```
   Rule: Technician override (priority 6) wins over PARASITE (priority 8)
   Current state: technician_logged_in = FALSE
   Validation: No override? ✓ YES (PASS)
   Decision: PARASITE can write at priority 8
   ```

**Safety Decision:** ✅ **ALLOW** (all checks pass)

### 2.5 Confidence Assessment

**Tier Determination:**

```
Decision: Raise chiller setpoint from 8°C to 9°C
Action type: Setpoint adjustment ±1°C (SAFE)
Confidence: 88%
Tier threshold for auto-execute: 85%
Validation: 88% > 85%? ✓ YES

Tier Decision: 🟢 TIER 3 AUTO-EXECUTE
             (autonomous control, no approval needed)
```

**Alternative Scenarios:**

```
Scenario A: Same decision, lower confidence
  Confidence: 72%
  Tier threshold: 85%
  Decision: 72% < 85%? ✗ NO
  Action: TIER 2 (require user approval)

Scenario B: Equipment on/off (risky action)
  Confidence: 92%
  Tier threshold for safe actions: 85% (passes)
  But action type: RISKY (equipment start)
  Tier 3 policy: Risky actions always require approval
  Action: TIER 2 (require user approval despite high confidence)

Scenario C: Low confidence + safe action
  Confidence: 60%
  Tier threshold: 70% (for Tier 2 recommendation)
  Decision: 60% < 70%? ✗ NO
  Action: SKIP (don't even recommend, too uncertain)
```

---

## Stage 3: Action (Niagara Write)

### Write Endpoint Details

**Endpoint:** `POST /api/niagara/bacnet/devices/{device_id}/points/{object_type}/{instance}/write`

**Example Request:**
```
POST /api/niagara/bacnet/devices/5/points/AnalogOutput/100/write
Content-Type: application/json

{
  "value": 9.0,
  "priority": 8
}
```

**Request Fields:**
```
device_id = 5              (BACnet device instance number for CHILLER)
object_type = AnalogOutput (BACnet object type for setpoint)
instance = 100             (Point instance number on device)
value = 9.0               (New setpoint value in °C)
priority = 8              (BACnet priority: 1=safety, 6=tech, 8=PARASITE, 14=sched, 16=default)
```

### Write Execution Process

**Step 1: Request Validation**
```
Validate request parameters:
  - device_id 5 exists? ✓ YES (CHILLER online)
  - point exists? ✓ YES (cooling_setpoint is instance 100)
  - value in range [4, 12]? ✓ YES (9.0 is valid)
  - priority 1-16? ✓ YES (8 is valid)
```

**Step 2: BACnet Write Execution**
```
Action: Send BACnet WriteProperty service request
Target: Device 5, AnalogOutput instance 100
Value: 9.0
Priority: 8 (manual operator priority)
Timeout: 5 seconds for device acknowledgment
```

**Step 3: Response Handling**

✅ **Success Response:**
```
HTTP 200 OK
{
  "success": true,
  "device_id": 5,
  "device_name": "S002-CHILLER-B1-001",
  "object_type": "AnalogOutput",
  "instance": 100,
  "point_name": "cooling_setpoint",
  "value_written": 9.0,
  "unit": "°C",
  "priority": 8,
  "timestamp": "2026-02-11T14:30:05Z"
}
```

❌ **Failure Response (Device Offline):**
```
HTTP 500 Internal Server Error
{
  "success": false,
  "error": "device_offline",
  "message": "Device 5 (S002-CHILLER-B1-001) did not respond",
  "timestamp": "2026-02-11T14:30:10Z"
}
Action: Trigger auto-rollback, alert ops
```

❌ **Failure Response (Priority Conflict):**
```
HTTP 400 Bad Request
{
  "success": false,
  "error": "priority_conflict",
  "message": "Priority 6 (technician) has precedence over priority 8",
  "current_value": 8.0,
  "attempted_value": 9.0,
  "winning_priority": 6,
  "timestamp": "2026-02-11T14:30:10Z"
}
Action: Log conflict, don't rollback (technician override is legitimate)
```

---

## Stage 4: Monitoring (Feedback Verification)

### Immediate Verification (5-30 seconds)

**Process:**

1. **Monitor COV Subscription**
   ```
   Waiting for COV event on: cooling_setpoint
   Expected: cooling_setpoint → 9.0°C
   Timeout: 5 seconds
   ```

2. **COV Event Received**
   ```
   ✓ COV Event: cooling_setpoint changed to 9.0°C
   ✓ Timestamp: 2026-02-11T14:30:05Z (immediately after write)
   ✓ Status: VERIFIED
   ```

3. **Read Confirmation**
   ```
   POST /api/niagara/bacnet/devices/5/points/AnalogOutput/100/read

   Response: {
     "device_id": 5,
     "point_name": "cooling_setpoint",
     "value": 9.0,
     "unit": "°C",
     "timestamp": "2026-02-11T14:30:05Z"
   }

   Verification: Actual = Expected? 9.0 = 9.0? ✓ YES
   Status: VERIFIED
   ```

### Failure Cases

**Case 1: No COV Event (Device Offline)**
```
Write executed: cooling_setpoint = 9.0°C (HTTP 200)
Wait for COV: 5-second timeout
Result: No COV event received
Status: FAILURE (device might be offline or unresponsive)

Auto-rollback:
  1. Read current value: cooling_setpoint = 8.0°C (write didn't apply)
  2. Write original value: 8.0°C (restore)
  3. Log: "Device offline, write failed, auto-rollback executed"
  4. Alert: Ops notified of control failure
```

**Case 2: Actual != Expected (Priority Conflict)**
```
Write executed: cooling_setpoint = 9.0°C (HTTP 200)
Wait for COV: cooling_setpoint changed to 8.0°C (not 9.0°C!)
Status: FAILURE (technician override - priority 6 wins)

Decision:
  1. Read actual value: cooling_setpoint = 8.0°C
  2. Detect conflict: Expected 9, actual 8
  3. Log: "Priority 6 override detected, PARASITE write ignored"
  4. Alert: "Technician logged in, manual control active"
  5. No rollback: Technician override is legitimate
```

**Case 3: Timeout (Device Slow)**
```
Write executed: cooling_setpoint = 9.0°C (HTTP 200)
Wait for COV: 5-second timeout expires
No COV event received yet (device slow)

Decision:
  1. Retry read: cooling_setpoint = ?
  2. If = 9.0°C: Success (delayed COV) → Log as success
  3. If ≠ 9.0°C: Failure → Auto-rollback
```

---

## Stage 5: Feedback Loop (Learning)

### Outcome Measurement (10 minutes)

**Timeline:**
```
T+0:00   Decision made, write executed
T+0:05   Verify: COV confirms setpoint = 9.0°C ✓
T+0:30   Impact: Supply temp responds to new setpoint
T+5:00   Measurement: Monitor supply temp trend
T+10:00  Assessment: Calculate total impact, update health score
```

**Measurement Process:**

1. **Collect Impact Data**
   ```
   Before action (T+0):
     - supply_temp: 7.0°C
     - compressor_amps: 45A
     - occupant_comfort: Normal
     - energy_rate: 5kW

   After action (T+10:00):
     - supply_temp: 11.0°C (increased toward new setpoint)
     - compressor_amps: 38A (reduced, working less hard)
     - occupant_comfort: Still normal
     - energy_rate: 4.2kW (reduced consumption)
   ```

2. **Calculate Deltas**
   ```
   supply_temp_delta: 11.0 - 7.0 = +4.0°C ✓
   compressor_amps_delta: 38 - 45 = -7A ✓
   energy_delta: 4.2 - 5.0 = -0.8kW ✓
   occupant_complaints: 0 ✓
   ```

3. **Health Score Impact**
   ```
   Base health: 85
   Decision impact: +2 (setpoint adjustment within safe range)
   Outcome impact: +1 (energy savings verified)
   Complaint impact: 0 (no occupant issues)
   New health: 85 + 2 + 1 + 0 = 88
   ```

### ML Training Data Generation

**Decision-Outcome Record:**
```json
{
  "decision_id": "d5f8a2c1-4e9b-11ed-8b5d-001",
  "equipment_type": "CHILLER",
  "decision_features": {
    "supply_temp": 7.0,
    "cooling_setpoint": 8.0,
    "compressor_amps": 45,
    "occupancy": 80,
    "time_of_day": 14,
    "outside_temp": 32,
    "recent_trend": "decreasing"
  },
  "action": {
    "type": "setpoint_adjustment",
    "from": 8.0,
    "to": 9.0,
    "confidence": 0.88
  },
  "outcome": {
    "write_success": true,
    "write_verified": true,
    "duration_minutes": 10,
    "supply_temp_after": 11.0,
    "supply_temp_delta": 4.0,
    "compressor_amps_after": 38,
    "compressor_amps_delta": -7,
    "energy_kwh": 0.8,
    "energy_saved": true,
    "occupant_complaints": 0,
    "health_before": 85,
    "health_after": 88,
    "success": true,
    "success_score": 1.0
  }
}
```

### Retraining Trigger

**After every 100 decisions:**
```
Decisions executed: 100
Add all 100 decision/outcome pairs to training dataset
Retrain LSTM model: LSTM_CHILLER_v4.pkl
Validation: Test on holdout dataset (20% of training data)
Metrics: R², accuracy, precision, recall, F1 score
Update: If accuracy > previous version, deploy new model
Confidence: Recalibrate thresholds based on new accuracy
```

---

## Stage 6: Audit Trail & History

### Complete Decision Record

**Database Record:**
```json
{
  "id": "aud_5f8a2c1-4e9b-11ed",
  "timestamp": "2026-02-11T14:30:00Z",
  "equipment_id": "S002-CHILLER-B1-001",
  "equipment_type": "CHILLER",
  "equipment_health_before": 85,
  "tier": 3,
  "action": "lower_setpoint",
  "from_value": 8.0,
  "to_value": 9.0,
  "unit": "°C",
  "confidence": 0.88,
  "confidence_level": "HIGH",
  "decision_reason": "Chiller overshooting (supply temp 7°C < setpoint 8°C), wasting energy",
  "safety_checks": {
    "range_check": "PASS (9.0 in [4, 12])",
    "interlock_check": "PASS (pump running)",
    "priority_check": "PASS (no technician override)",
    "equipment_status_check": "PASS (equipment online)"
  },
  "write_execution": {
    "endpoint": "POST /api/niagara/bacnet/devices/5/points/AnalogOutput/100/write",
    "request_payload": {"value": 9.0, "priority": 8},
    "http_status": 200,
    "success": true,
    "timestamp": "2026-02-11T14:30:05Z"
  },
  "cov_verification": {
    "expected": 9.0,
    "actual": 9.0,
    "event_received": true,
    "verified_timestamp": "2026-02-11T14:30:05Z",
    "verification_success": true,
    "verification_time_seconds": 5
  },
  "outcome_measurement": {
    "duration_minutes": 10,
    "supply_temp_before": 7.0,
    "supply_temp_after": 11.0,
    "supply_temp_delta": 4.0,
    "compressor_amps_before": 45,
    "compressor_amps_after": 38,
    "compressor_amps_delta": -7,
    "energy_saved_kwh": 0.8,
    "cost_saved_usd": 50,
    "occupant_complaints": 0,
    "comfort_maintained": true,
    "equipment_health_after": 88,
    "health_delta": 3
  },
  "ml_feedback": {
    "decision_queued_for_retraining": true,
    "retraining_priority": "normal",
    "confidence_feedback": "prediction_correct",
    "outcome_success": true
  },
  "audit_trail": "All decisions logged, searchable by equipment/date/action/outcome"
}
```

### Dashboard Displays

**Summary:**
```
PARASITE Autonomous Control (Last 7 Days)
───────────────────────────────────────────
Total decisions: 287
Success rate: 94.3% (271 successful, 16 failed)
Auto-rollbacks: 5 (due to device failures)
Occupant complaints: 0
Energy saved: $1,250 (over 7 days)
Cost saved: $1,250 total, $178/day average

Equipment Performance:
  CHILLER:    92 decisions, 94% success
  AHU:        85 decisions, 95% success
  FCU:        56 decisions, 92% success
  VAV:        45 decisions, 88% success (being retrained)
  DALI:       9 decisions, 100% success
```

**Time Series:**
```
PARASITE Decision Quality (Last 30 Days)

Success Rate Trend:
  Week 1: 89% (system learning)
  Week 2: 91%
  Week 3: 93%
  Week 4: 94% ← Current week

Trend: IMPROVING (confidence thresholds working)
```

**Equipment-Specific:**
```
S002-CHILLER-B1-001 Recent Actions:
───────────────────────────────────
Time           Action              Status      Impact
14:30 2/11     Lower setpoint      ✓ Success   +$2 savings
13:45 2/11     Fan speed adjust    ✓ Success   +$1 savings
12:20 2/11     Damper position     ✓ Success   +$1.50 savings
[More history...]
```

---

## Data Flow Examples

### Example 1: Setpoint Adjustment (Happy Path)

**T+0:00 - Decision Triggered**
```
Input: Chiller supply_temp = 7°C, setpoint = 8°C
ML prediction: "Overshooting (88% confidence)"
AI Optimizer: "Raise to 9°C"
SafetyEngine: ✓ ALLOW (in range)
Tier assessment: 88% > 85% threshold → TIER 3 auto-execute
```

**T+0:05 - Write Executed**
```
POST /api/niagara/bacnet/devices/5/points/AnalogOutput/100/write
Body: {value: 9, priority: 8}
Response: HTTP 200 OK {success: true}
```

**T+0:10 - Verification**
```
COV event: cooling_setpoint = 9.0°C ✓
Read confirmation: Current value = 9.0°C ✓
Status: VERIFIED
```

**T+0:30 to T+10:00 - Outcome Monitoring**
```
Supply temp trend: 7°C → 9°C → 11°C (stabilizing)
Compressor load: 45A → 38A (improving)
Energy: 5kW → 4.2kW (reducing)
Occupant comfort: Normal
```

**T+10:00 - Learning**
```
Outcome: SUCCESS (setpoint change achieved goal)
Health delta: +3 (decision + outcome both positive)
ML training: Add this decision/outcome to retraining dataset
Decision quality: +1 to success counter (287/304 = 94.3%)
```

### Example 2: Priority Override Detection

**T+0:00 - Decision Triggered**
```
Input: AHU supply_temp too high
Decision: Lower damper position from 75% to 60%
Confidence: 82%
Tier: TIER 3 auto-execute
```

**T+0:05 - Write Executed**
```
POST /api/niagara/bacnet/devices/3/points/AnalogOutput/50/write
Body: {value: 60, priority: 8}
Response: HTTP 200 OK {success: true}
```

**T+0:10 - Verification Shows Conflict**
```
Expected: damper_pos = 60%
Actual: damper_pos = 75%
Status: CONFLICT DETECTED

COV event shows: Priority 6 (technician) wrote 75% after PARASITE wrote 60%
Action: Log conflict, acknowledge technician override
No rollback: Technician control is legitimate
Alert: "Technician logged in, manual control active on AHU"
```

**T+10:00 - Learning Impact**
```
Outcome: INCONCLUSIVE (technician override)
Decision marked: "Suppressed by manual override"
ML training: This decision NOT added to success/failure metric
Health delta: 0 (no impact, technician in control)
Dashboard note: "AHU had technician override, PARASITE control suspended"
```

---

## Error Handling & Recovery

### Network Failure

**Scenario:** Network between PARASITE and Niagara goes down

```
T+0:05 Decision: Write setpoint = 9°C
       Network down - write times out

T+0:10 Timeout: No response from device
       Status: FAILURE

T+0:15 Recovery attempt: Retry write (exponential backoff)
       Network up - write succeeds

T+0:20 Verification: COV confirms value written
       Status: SUCCESS (delayed, but recovered)

T+10:00 Outcome: Delayed action completed, learning proceeds
```

### Device Offline

**Scenario:** Chiller offline for maintenance

```
T+0:05 Decision: Write setpoint = 9°C
       Device offline - write returns {success: false, error: device_offline}

T+0:06 Auto-rollback: No action needed (device already offline)
       Status: SKIPPED (safe - offline device can't hurt anyone)

T+0:10 Alert: "S002-CHILLER-B1-001 offline, control skipped"
       Ops notified that equipment is unavailable

T+10:00 Outcome: Decision marked "skipped"
        Not added to success/failure metrics
        Learning: Skip this decision (can't measure outcome)
```

### Cascade Failure (One Bad Decision Triggers Another)

**Scenario:** PARASITE makes bad decision, triggers safety system

```
T+0:05 Decision: Lower chiller setpoint to 3°C (TOO COLD!)
       SafetyEngine check: 3°C < 4°C minimum → BLOCKED
       Write never sent

Status: PREVENTED (safety system caught dangerous decision)
Alert: "PARASITE decision blocked by SafetyEngine: setpoint too low"
ML impact: Decision logged as BLOCKED, confidence decreased for future
```

### Partial Verification Failure

**Scenario:** Write succeeds, but COV doesn't confirm

```
T+0:05 Decision: Write damper_pos = 75%
       Write succeeds: HTTP 200

T+0:10 Verification: Wait for COV 5-second timeout
       No COV event received (slow device)

T+0:12 Read confirmation: Query device directly
       Actual value: damper_pos = 75% (write DID work!)
       Status: SUCCESS (delayed COV, but verified by read)

T+10:00 Outcome: Decision marked successful (verified by read)
        ML training: Include this outcome
```

---

## Summary

The six-stage PARASITE data flow provides:

1. **Real-time data collection** via COV subscriptions
2. **Intelligent decision-making** combining ML + AI + safety
3. **Safe execution** with SafetyEngine validation
4. **Verification** via COV feedback and auto-rollback
5. **Continuous learning** from every outcome
6. **Complete audit trail** for transparency and investigation

**Key Characteristics:**
- ✅ **Event-driven:** COV subscriptions trigger updates immediately
- ✅ **Verified:** Every write confirmed before moving on
- ✅ **Safe:** SafetyEngine prevents dangerous decisions
- ✅ **Learning:** Every outcome improves future decisions
- ✅ **Auditable:** Complete decision history logged
- ✅ **Recoverable:** Failures trigger auto-rollback
- ✅ **Graceful degradation:** System falls back to lower tiers if quality drops

This architecture enables safe autonomous control while maintaining human oversight through approval gates and continuous monitoring.

---

**Created:** 2026-02-11
**Phase:** 67-04 (PARASITE Niagara Architecture Design)
**Status:** ✅ Complete
