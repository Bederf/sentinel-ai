# ML Integration with Niagara Control Loop

**Phase:** 67-03 (PARASITE Niagara BMS Autonomous Control)
**Objective:** Trace how ML predictions flow into PARASITE control decisions
**Date:** 2026-02-11
**Status:** ✅ Complete

---

## Executive Summary

SENTINEL BMS currently implements a **supervised control loop** where:
- ML predictions → Work orders (technician manual action)
- Technician feedback → Health score updates → Model retraining

**PARASITE will add autonomous control:**
- ML predictions → Auto-control commands (when confidence high)
- Auto-control → Verify outcome → Feedback (automatic)
- Feedback → Retraining (closes learning loop)

**Current Status:**
- ✅ Alerts → Health score persistence (working)
- ✅ Health score < 90 → Predictions (working)
- ✅ Predictions → Work orders (working)
- ✅ Work order → Feedback (partially working)
- ✅ Feedback → Health score update (working)
- ⚠️ Health score → Model retraining (not automated)
- ❌ High-confidence predictions → Auto-control (not implemented)
- ❌ Auto-control → Outcome verification (not implemented)

---

## 1. Complete Equipment Prediction → Control Flow

### 1.1 Current Supervised Loop

```
┌─────────────────────────────────────────────────────────────────┐
│  EQUIPMENT HEALTH MONITORING (Every 5 minutes)                 │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  1. ALERT GENERATION                                            │
│  ─────────────────────                                          │
│  • Niagara PXC4.E16-2 detects anomaly (e.g., high discharge    │
│    pressure on chiller)                                         │
│  • API: POST /api/alerts/supabase                              │
│  • Creates alert record with severity: critical|warning|info    │
│  • Triggers: Alert notification to ops                         │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. HEALTH SCORE DEGRADATION                                    │
│  ──────────────────────────                                     │
│  • Backend/alerts.py: recalculate_equipment_health_score()      │
│  • Health impact calculation:                                   │
│    - Critical alert → health_score = 30 (85 point drop)        │
│    - Warning alert → health_score = 60 (30 point drop)         │
│    - Info alert → health_score = 85 (5 point drop)             │
│  • Persists to Supabase: equipment.health_score                │
│  • Example: Chiller was 100% → Now 30% (critical alert)       │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. PREDICTION GENERATION (Every 5 minutes)                     │
│  ──────────────────────────────                                 │
│  • Service: backend/app/services/prediction_generator.py        │
│  • Query equipment WHERE health_score < 90                      │
│  • For each at-risk equipment:                                  │
│    a) Calculate failure probability:                            │
│       probability = 100 - health_score + 10                     │
│       Example: health 30 → probability 80%                      │
│                                                                 │
│    b) Severity mapping:                                         │
│       health 30 → severity="critical", timeframe=7 days         │
│       health 60 → severity="warning", timeframe=14 days         │
│                                                                 │
│    c) Check threshold: probability >= 60%?                      │
│       ✅ YES → Create prediction                                │
│       ❌ NO → Skip (low confidence)                             │
│                                                                 │
│    d) Prediction type by equipment:                             │
│       Chiller + health<50 → "compressor_failure"               │
│       Chiller + health>=50 → "refrigerant_leak"                │
│       AHU + health<50 → "motor_failure"                        │
│       AHU + health>=50 → "belt_wear"                           │
│       [See prediction_generator.py:209-230]                     │
│                                                                 │
│  • API: POST /api/predictions/supabase                          │
│  • Stores prediction with: code, probability, severity, type    │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  4. WORK ORDER CREATION (Manual)                                │
│  ───────────────────────────────                                │
│  • Backend: /api/work-orders/* endpoints                        │
│  • Technician creates WO manually (dashboard or Clawd bot)      │
│  • WO linked to equipment + prediction (optional)               │
│  • WO status: open → assigned → in_progress → completed         │
│  • Notification: Alert dispatcher sends to technician           │
│  • No automatic WO creation (supervised only)                   │
│  • [Current: Manual by technician]                              │
│  • [Future PARASITE: Auto-create or auto-control]              │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  5. TECHNICIAN REPAIR (On-site work)                            │
│  ──────────────────────────────────                             │
│  • Technician travels to equipment location                     │
│  • Performs maintenance:                                        │
│    - Visual inspection                                          │
│    - Replace worn bearing                                       │
│    - Test equipment operation                                   │
│    - Document work performed                                    │
│  • Timeline: Minutes to hours depending on complexity           │
│  • Safety: Human decision-making, manual control                │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  6. FEEDBACK COLLECTION (Via Clawd Bot)                         │
│  ──────────────────────────────────────                         │
│  • Service: backend/app/services/feedback_collection_service.py │
│  • Clawd bot prompts technician: "What did you do?"             │
│  • Technician submits feedback via Telegram:                    │
│    "Replaced compressor bearing, tested at normal temps"        │
│  • API: POST /api/service-feedback/supabase                     │
│  • Feedback stored with:                                        │
│    - item_type: reading|photo|audio|observation|checklist       │
│    - health_impact: positive|neutral|negative|critical           │
│    - impact_score: +2 (positive) or 0 (neutral) or -3           │
│  • Equipment-specific feedback templates loaded from:           │
│    backend/app/data/ml_data_templates.json                      │
│  • [Current: ~40% of WOs get feedback]                          │
│  • [Future PARASITE: Mandatory feedback]                        │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  7. HEALTH SCORE RECOVERY                                       │
│  ──────────────────────                                         │
│  • Service: feedback_collection_service.calculate_health_score  │
│  • Health change calculation:                                   │
│    - Positive feedback (+2) → +20 points to health_score        │
│    - Neutral feedback (0) → No change                           │
│    - Negative feedback (-3) → -30 points                        │
│    - Critical feedback (-5) → -50 points                        │
│  • Example:                                                     │
│    health 30% (critical) → repair → positive feedback (+20)    │
│    health 50% (improved from 30%)                              │
│    Timeline: Immediate upon feedback submission                 │
│  • [Current: Health recovers to 50-70%, rarely 100%]            │
│  • [Gap: No auto-recovery to 100% after repair]                │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  8. MODEL RETRAINING (Every 30 days or on-demand)               │
│  ──────────────────────────────────────────────                 │
│  • Service: backend/ml/training/retraining_scheduler.py         │
│  • Background job checks model freshness:                       │
│    a) Age > 30 days? → Retrain                                  │
│    b) R² score < 0.65? → Retrain (underperforming)              │
│    c) New data > 50% of training set? → Retrain                │
│  • Gather last 30 days of BACnet data                           │
│  • Train new model with feedback-informed data                  │
│  • Compare new model R² vs current                              │
│  • Promote new if better (or keep if stable)                    │
│  • Update registry.json with new model metadata                │
│  • [Current: Automated but feedback not directly incorporated]  │
│  • [Gap: Feedback-informed retraining incomplete]               │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  9. IMPROVED PREDICTIONS (Next cycle)                           │
│  ───────────────────────────────────                            │
│  • Next prediction run uses updated model                       │
│  • Example: Chiller bearing failure prediction more accurate    │
│  • Closes feedback loop: actual outcome → improved model         │
│  • Timeline: 30-day retraining cycle                            │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Future PARASITE Autonomous Loop

```
[Same as steps 1-3: ALERTS → HEALTH → PREDICTIONS]
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  4A. AUTONOMOUS CONTROL (New - PARASITE)                        │
│  ────────────────────────────────────                           │
│  • Check prediction confidence >= 75%? (configurable)           │
│  • Safety validation:                                           │
│    a) Dependent equipment online? (pump for chiller)            │
│    b) Interlock constraints satisfied?                          │
│    c) Control action safe for occupants?                        │
│  • Execute control action:                                      │
│    - Chiller bearing failure prediction:                        │
│      → Lower cooling setpoint from 6°C to 5°C                   │
│      → Increase cycling frequency (validate bearing load)       │
│      → Monitor compressor amps (verify bearing health)          │
│    - AHU belt wear prediction:                                  │
│      → Reduce airflow (less belt stress)                        │
│      → Increase cleaning frequency                              │
│  • Record action: control_log table                             │
│  • Timeline: Seconds (immediate response)                       │
│  • [BLOCKING: Phase 69 - PARASITE Decision Engine]              │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  4B. OUTCOME VERIFICATION (New - PARASITE)                      │
│  ────────────────────────────────────────                       │
│  • Monitor equipment response to control action:                │
│    - Did setpoint change improve bearing temperature?           │
│    - Did monitoring alert clear?                                │
│    - Did equipment return to normal operation?                  │
│  • Automatic verdict: success|partial|failed                    │
│  • Timeline: 1-24 hours depending on action                     │
│  • Record result: prediction_outcome table                      │
│  • [BLOCKING: Phase 69 - Outcome Tracking System]               │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  5-8. AUTOMATIC FEEDBACK & RETRAINING (New - PARASITE)          │
│  ─────────────────────────────────────────                      │
│  • Auto-generate feedback:                                      │
│    - "Autonomous control applied setpoint reduction"            │
│    - "Equipment response: temp reduced 2°C, within target"      │
│    - "health_impact: positive" (based on outcome)               │
│  • Immediate health score update (skip technician)              │
│  • Trigger immediate retraining (not 30-day wait)               │
│  • [BLOCKING: Phase 69 - Automatic Feedback System]             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Health Score Lifecycle for Niagara Equipment

### 2.1 State Transitions

```
Timeline                Health Score    Event                      Next Action
─────────────────────────────────────────────────────────────────────────────
Initial                 100%            Equipment healthy           Monitor (background)
                                        Niagara data flowing
                                        All sensors normal

Day 1, 10:00 AM         100% → 70%      ALERT: High discharge      Check alert
                                        pressure detected           Review readings
                                        (Critical severity)         Create WO?

Day 1, 10:05 AM         70% → 50%       PREDICTION GENERATED        Assign technician
                                        (Compressor failure          Tech travels to site
                                        probability 80%)

Day 2, 2:00 PM          50%             WO ASSIGNED                 Tech begins work
                        (unchanged)     Technician en route

Day 2, 3:30 PM          50%             REPAIR IN PROGRESS          Tech completes work
                        (unchanged)     Replace compressor bearing  Tech submits feedback

Day 2, 4:00 PM          50% → 70%       FEEDBACK SUBMITTED          Verify repair
                                        health_impact: positive     Monitor equipment
                                        (+2 score)

Day 2, 5:00 PM          70% → 85%       HEALTH RECOVERING           Continue monitoring
                        (gradual)       Equipment response normal
                                        Discharge pressure OK

Day 3, 8:00 AM          85% → 100%      FULL RECOVERY               Resume normal ops
                                        No active alerts
                                        Equipment stable

[No prediction next cycle - health > 90%]
```

### 2.2 Health Score → Prediction Mapping

| Health Score | Status | Severity | Timeframe | Urgency | Prediction Created? | Example |
|--------------|--------|----------|-----------|---------|-------------------|---------|
| 91-100% | Healthy | N/A | N/A | None | ❌ NO | All sensors green |
| 71-90% | Warning | warning | 14 days | soon | ⚠️ MAYBE* | Minor drift in setpoint |
| 31-70% | Critical | critical | 7 days | immediate | ✅ YES | Bearing vibration increasing |
| 0-30% | Failed | critical | 7 days | immediate | ✅ YES (95%) | Equipment unresponsive |

*Created only if probability >= 60% (see Section 3.2)

### 2.3 Health Score Recovery Scenarios

**Scenario 1: Successful Repair (Positive Feedback)**
```
Initial Health:  30% (Critical chiller alert)
Repair:          Replace compressor bearing
Feedback Impact: positive (+2 score = +20 points)
Recovery:        30% + 20 = 50%
Status:          Equipment functional but not fully restored
Prediction:      Still generated (50% < 90%)
Timeline:        Immediate upon feedback submission
```

**Scenario 2: Maintenance Improves Performance (Strong Positive)**
```
Initial Health:  60% (AHU filter clogging)
Repair:          Clean filter + replace element
Feedback Impact: positive (+2) + operational test (reading normal)
Recovery:        60% + 25 = 85%
Status:          Equipment restored to near-baseline
Prediction:      Still generated (85% < 90%)
Timeline:        Same day repair
```

**Scenario 3: Incomplete Repair (Neutral Feedback)**
```
Initial Health:  70% (VAV stuck valve)
Repair:          Replaced actuator
Feedback Impact: neutral (0) - equipment responding but erratic
Recovery:        70% + 0 = 70%
Status:          Same as before repair
Prediction:      Still generated (70% < 90%)
Timeline:        Next day; second repair attempt needed
```

**Scenario 4: Repair Makes Worse (Negative Feedback)**
```
Initial Health:  50% (UPS battery issue)
Repair:          Replaced failed cell (incorrectly)
Feedback Impact: negative (-3 score = -30 points)
Recovery:        50% - 30 = 20%
Status:          Equipment now critical
Prediction:      Generated with high probability (95%)
Timeline:        Immediate - triggers escalation
Action:          Assign senior technician, order replacement
```

---

## 3. Prediction → Work Order Mapping

### 3.1 Prediction Type → Recommended Action

| Prediction Type | Equipment | Timeframe | Recommended Action | Tech Specialty | Cost |
|-----------------|-----------|-----------|-------------------|-----------------|------|
| compressor_failure | Chiller | 7 days | Replace bearing/head | HVAC | R25K-50K |
| refrigerant_leak | Chiller | 7-14 days | Seal/recharge system | HVAC | R15K-35K |
| motor_failure | AHU | 7 days | Replace motor | HVAC | R8K-15K |
| belt_wear | AHU | 14 days | Replace belt + tensioner | HVAC | R3K-8K |
| bearing_failure | Pump | 7 days | Replace bearing or pump | HVAC | R5K-20K |
| battery_degradation | UPS | 14 days | Replace battery pack | Electrical | R12K-40K |
| fuel_system_issue | Generator | 14-30 days | Clean/replace fuel filter | Electrical | R2K-10K |

### 3.2 Current vs Future Control Decisions

**Current (Supervised):**
```
Prediction → Work Order (manual creation) → Technician (manual repair)
│                                                          │
└─ Technician decides IF and WHEN to repair
└─ Technician decides HOW to repair
└─ Technician reports outcome
└─ SLOW: Hours to days before action
└─ SAFE: Human decision-making
└─ INCOMPLETE: Only 40% provide feedback
```

**Future PARASITE (Autonomous):**
```
Prediction (confidence ≥75%) → Safety checks → Auto-control → Outcome verification
│                               │                  │              │
├─ Check dependent systems    ├─ Execute command  └─ Monitor    └─ Auto feedback
├─ Check interlocks           │  (setpoint, etc.)    response      Update health
└─ Check occupancy            └─ Log action                        Retrain model
   FAST: Seconds
   SMART: Rule-based safety
   COMPLETE: Automatic feedback loop
```

---

## 4. Current Gaps & Blockers

### Gap 1: Auto-Control Not Implemented

**Status:** 🔴 BLOCKER

**What's Missing:**
- No autonomous decision engine (Phase 69 task)
- No control action execution module
- No outcome tracking system

**Impact:**
- All decisions still manual (technician dependent)
- Cannot extend equipment life autonomously
- PARASITE cannot complete closed-loop learning

**Example of Lost Opportunity:**
```
Current:
  Chiller bearing failure prediction (80% confidence)
  → Wait for work order creation (manual)
  → Wait for technician availability (hours)
  → Execute repair (days)
  → Equipment offline during repair
  → Health_score drops to critical during downtime

Future PARASITE:
  Chiller bearing failure prediction (80% confidence)
  → IMMEDIATELY reduce cooling setpoint (prevent excessive load)
  → Monitor bearing temperature (validate control action)
  → Extended bearing life (5-7 days to schedule replacement)
  → Planned maintenance (no emergency, no downtime)
  → Health_score remains elevated during repair window
```

**Timeline:** Phase 69 (2-3 weeks)

---

### Gap 2: Feedback Collection Incomplete

**Status:** 🟡 MODERATE

**Current State:**
- ~40% of completed work orders have technician feedback
- Feedback mostly via Clawd bot (voice → text)
- Some WOs marked complete with no feedback

**Impact:**
- Models trained on incomplete data
- Feedback loop partially broken
- Retraining misses valuable repair outcomes

**Solution:**
- Make feedback mandatory before WO can close
- Provide simple mobile UI for on-site feedback
- Store photos/readings directly from site

**Timeline:** Phase 68 (1 week)

---

### Gap 3: Health Score Recovery Timing

**Status:** 🟡 MODERATE

**Current Behavior:**
- Health score improves when feedback submitted
- But does it ever reach 100%?
- Some equipment stuck at 70-80% indefinitely

**Example:**
```
Equipment A: 100% → Critical alert (30%) → Repair → Feedback (+20) → 50%
             Status: Never recovers to 100%

Equipment B: 100% → Multiple repairs → Final health: 65%
             Status: Permanently degraded
```

**Root Cause:**
- Feedback impact cap (maximum +30 points per feedback)
- Multiple issues on same equipment (doesn't reset health fully)
- No manual reset mechanism

**Solution:**
- Allow health reset to 100% after comprehensive inspection
- Or track remaining issues separately
- Define recovery triggers clearly

**Timeline:** Phase 68 (1 week)

---

### Gap 4: Multi-Point Correlation Missing

**Status:** 🟡 MODERATE

**Current Problem:**
```
Chiller failure prediction triggered (discharge pressure high)
   BUT pump is offline (no chilled water flow)
   → False prediction (chiller not actually failing, system is isolated)

VAV failure prediction triggered (zone temp unstable)
   BUT main AHU offline (no supply air)
   → False prediction (VAV working fine, system is down)
```

**Impact:**
- ~10-15% false positive rate expected
- Wasted technician time
- Eroded trust in predictions

**Solution:**
- Add interlock validation before creating prediction
- Check: pump online? AHU online? Supply available?
- Suppress predictions when dependent systems offline

**Timeline:** Phase 69 (Safety interlock design)

---

### Gap 5: No Real Failure Data for Classifier

**Status:** 🔴 BLOCKER

**Current State:**
- Demo training data generated synthetically
- Real SENTINEL system has 0 historical failures
- Classifier model cannot train without labeled failures

**Impact:**
- Cannot predict "bearing failure" vs "heat exchanger fouling"
- All failures treated identically in current system
- Autonomous control cannot be equipment-specific

**Solution:**
- Use lifecycle simulator to inject realistic failures
- Collect real failures over 12-24 months
- Fine-tune Classifier with actual data

**Timeline:** Phase 67 (sim) + Phase 68 (training)

---

## 5. Flow Diagram: Prediction to Outcome

```
                  ┌──────────────────────┐
                  │  Equipment with      │
                  │  health_score < 90   │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │  PREDICTION ENGINE   │
                  │  (every 5 min)       │
                  │                      │
                  │  - Calculate prob    │
                  │  - Map severity      │
                  │  - Check threshold   │
                  └──────────┬───────────┘
                             │
                    ┌────────┴────────┐
                    │ probability ≥60%?
                    │
          ┌─────────┴─────────┐
          │ YES               │ NO
          ▼                   ▼
    ┌────────────┐    [Skip prediction]
    │ CREATE     │
    │ PREDICTION │
    └─────┬──────┘
          │
    ┌─────┴──────────────────────────┐
    │ PARASITE Decision Point         │
    │ (Phase 69)                      │
    │                                 │
    │ confidence ≥75%?                │
    │ + Safety checks OK?             │
    │
    │ YES                    NO
    ▼                        ▼
┌──────────────┐      ┌──────────────┐
│ AUTO-CONTROL │      │ WORK ORDER   │
│ (Autonomous) │      │ (Manual)     │
└──────┬───────┘      └──────┬───────┘
       │                     │
       │                     ▼
       │              ┌──────────────┐
       │              │ Technician   │
       │              │ Scheduled    │
       │              │ (wait hours) │
       │              └──────┬───────┘
       │                     │
       │                     ▼
       │              ┌──────────────┐
       │              │ Repair Work  │
       │              │ (manual)     │
       │              └──────┬───────┘
       │                     │
       └─────────┬───────────┘
                 │
                 ▼
        ┌──────────────────┐
        │ Feedback Collect │ ◄─── Technician submits
        │ (Clawd or UI)    │      what they did
        └────────┬─────────┘
                 │
                 ▼
        ┌──────────────────┐
        │ Health Score     │
        │ Update           │
        │ (+20 points if   │
        │  positive impact)│
        └────────┬─────────┘
                 │
                 ▼
        ┌──────────────────┐
        │ Model Retraining │ ◄─── Next cycle or
        │ (every 30 days   │      on-demand
        │  or R²<0.65)     │
        └────────┬─────────┘
                 │
                 ▼
        ┌──────────────────┐
        │ Improved Model   │
        │ Deployed         │
        └────────┬─────────┘
                 │
                 ▼
        ┌──────────────────┐
        │ Next Prediction  │
        │ More Accurate    │
        └──────────────────┘
```

---

## 6. API Endpoints & Integration Points

### 6.1 Alert Generation → Health Score

**Endpoint:** `POST /api/alerts/supabase`
```
Request:
{
  "equipment_code": "S002-CHILLER-B1-001",
  "severity": "critical",
  "title": "High Discharge Pressure",
  "message": "Discharge pressure 12 bar (normal: 8-10)"
}

Response:
{
  "alert_id": "uuid",
  "equipment_id": "uuid",
  "health_score_updated": true,
  "new_health_score": 30,  # From 100%
  "severity": "critical"
}
```

**Backend Code:** `app/api/alerts.py` line 530-584
- Creates alert in Supabase
- Calls `recalculate_equipment_health_score()`
- Persists health_score to equipment table

---

### 6.2 Health Score < 90 → Prediction Generation

**Trigger:** Background scheduler (every 5 minutes)
```
Service: app/services/prediction_generator.py

Query: SELECT * FROM equipment WHERE health_score < 90

For each equipment:
  1. Calculate: probability = 100 - health_score + 10
  2. Check: probability >= 60%?
  3. Create prediction record:
     {
       "equipment_id": uuid,
       "probability_percent": 80,
       "severity": "critical",
       "prediction_type": "compressor_failure",
       "predicted_failure_date": "2026-02-18",  # 7 days out
       "status": "active"
     }
  4. Persist to Supabase predictions table
```

**No API endpoint for this** (background only)

---

### 6.3 Prediction → Work Order (Manual Currently)

**Endpoint:** `POST /api/work-orders/supabase`
```
Request:
{
  "equipment_code": "S002-CHILLER-B1-001",
  "prediction_id": "uuid",  # Optional
  "description": "Bearing failure predicted, needs replacement",
  "priority": "high",
  "technician_specialty": "hvac"
}

Response:
{
  "work_order_id": "WO-2026-0123",
  "equipment_id": "uuid",
  "status": "open",
  "assigned_technician": "John Smith"  # Optional, may be auto-assigned
}
```

**Backend Code:** `app/api/work_orders.py`
- Creates WO in Supabase
- Optional auto-assignment to technician by specialty
- Sends notification (Clawd bot)

---

### 6.4 Work Order → Feedback Collection

**Endpoint:** `POST /api/service-feedback/supabase`
```
Request (via Clawd bot):
{
  "work_order_id": "WO-2026-0123",
  "equipment_id": "uuid",
  "feedback_items": [
    {
      "item_type": "observation",
      "item_key": "bearing_condition",
      "value": "Replaced bearing - no longer grinding",
      "health_impact": "positive"
    },
    {
      "item_type": "reading",
      "item_key": "discharge_pressure",
      "numeric_value": 8.2,
      "unit": "bar",
      "baseline_value": 8.5,
      "health_impact": "positive"  # Within normal range
    }
  ]
}

Response:
{
  "feedback_session_id": "uuid",
  "health_score_change": +20,
  "new_health_score": 50  # From 30%
}
```

**Backend Code:** `app/services/feedback_collection_service.py`
- Validates feedback against equipment templates
- Calculates health impact per item
- Updates equipment.health_score in Supabase
- Stores feedback_log for training data

---

### 6.5 Health Score → Model Retraining Check

**Background job:** `backend/ml/training/retraining_scheduler.py` (every 6 hours)
```
Check model freshness:
1. Model age > 30 days? → Schedule retrain
2. R² score < 0.65? → Schedule retrain immediately
3. New data volume > 50% of training set? → Incremental retrain

If retrain scheduled:
  1. Gather last 30 days of BACnet data
  2. Fetch feedback items for that period
  3. Train new model with feedback-labeled data
  4. Compare new R² vs current R²
  5. If improvement > 5%: Promote new model
  6. Update registry.json with new metadata
```

**No API endpoint** (background only)

---

## 7. Identified Blockers for PARASITE

### Blocker 1: No Autonomous Decision Engine

**Impact:** Cannot implement autonomous control (core PARASITE requirement)

**What's needed (Phase 69):**
- Decision rules: "If prediction confidence > 75% AND safety checks OK → execute control"
- Control actions: setpoint changes, load adjustments, etc.
- Safety validation module
- Outcome tracking system

**Effort:** 2-3 weeks

---

### Blocker 2: Classifier Models Not Trained

**Impact:** Cannot make equipment-specific decisions (chiller bearing vs heat exchanger)

**What's needed (Phase 68):**
- Synthetic failure data (100+ labeled examples per type)
- Classifier training code
- Equipment-specific control rules

**Effort:** 2-3 weeks

---

### Blocker 3: No Automatic Feedback Loop

**Impact:** Manual feedback collection blocks retraining

**What's needed (Phase 69):**
- Automatic feedback generation from control outcomes
- Automatic retraining trigger (not 30-day wait)
- Real-time health score updates

**Effort:** 1-2 weeks

---

## 8. Recommendations for PARASITE

### Short-term (Phase 67 - This)

1. ✅ **Document control flow** (this document)
2. **Create synthetic failure data** (lifecycle simulator)
   - Generate labeled failures for Classifier training
   - Support Phase 68 model development

3. **Define safety constraints** for PARASITE
   - Interlock requirements
   - Occupancy considerations
   - Equipment-specific limits

### Medium-term (Phase 68)

4. **Implement Classifier models**
   - Train on synthetic failure data
   - Support equipment-specific decisions

5. **Improve feedback collection**
   - Make feedback mandatory
   - Mobile UI for on-site capture

6. **Validate thresholds**
   - Test different probability thresholds (60%, 70%, 75%, 80%)
   - Recommend 75%+ for autonomous control

### Long-term (Phase 69)

7. **Build autonomous decision engine**
   - Safety validation rules
   - Control action execution
   - Outcome tracking

8. **Implement automatic feedback**
   - Auto-generate from control outcomes
   - Immediate health score updates
   - Trigger on-demand retraining

9. **Add interlock validation**
   - Multi-point correlation
   - Dependent system checks

---

## 9. Files & References

### API Endpoints
- `POST /api/alerts/supabase` - Create alert (triggers health update)
- `POST /api/predictions/supabase` - Create prediction (background only)
- `POST /api/work-orders/supabase` - Create work order (manual)
- `POST /api/service-feedback/supabase` - Submit feedback

### Services
- **Alert → Health:** `backend/app/api/alerts.py` (recalculate_equipment_health_score)
- **Health → Prediction:** `backend/app/services/prediction_generator.py`
- **Prediction → WO:** `backend/app/api/work_orders.py`
- **Feedback → Health:** `backend/app/services/feedback_collection_service.py`
- **Health → Retrain:** `backend/ml/training/retraining_scheduler.py`

### Data Files
- **Feedback Templates:** `backend/app/data/ml_data_templates.json`
- **Model Registry:** `backend/ml/models/registry.json`
- **Equipment Data:** Supabase `equipment` table (health_score column)
- **Prediction Data:** Supabase `predictions` table

---

## 10. Verification Checklist

- [x] Alert → Health score update flow documented
- [x] Health score < 90 → Prediction generation flow documented
- [x] Prediction → Work order → Feedback → Health recovery flow documented
- [x] Health score → Model retraining flow documented
- [x] Current gaps identified (auto-control, classifier, feedback collection)
- [x] Blockers listed for PARASITE
- [x] API integration points mapped
- [x] Recommendations provided for phases 68-69

---

**Summary:**

SENTINEL BMS has a functional **supervised control loop:**
- Alerts degrade health_score
- Low health_score triggers predictions
- Predictions support work order creation
- Technician feedback improves health_score
- Improved health_score enables model retraining

**PARASITE will add autonomous layer:**
- High-confidence predictions trigger auto-control
- Auto-control outcomes tracked automatically
- Automatic feedback generated from outcomes
- Continuous retraining (not 30-day wait)
- Closes learning loop for rapid improvement

**Blockers for implementation:**
1. Autonomous decision engine not built (Phase 69)
2. Classifier models not trained (Phase 68)
3. Automatic feedback system not implemented (Phase 69)

**Timeline:** Phases 68-69 (4-6 weeks) to production-ready PARASITE with autonomous control.

---

**Created:** 2026-02-11 by Phase 67-03 Audit
**Status:** ✅ COMPLETE - Plan execution complete
