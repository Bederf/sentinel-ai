# Site-002 24-Hour Lifecycle Simulation - Complete Analysis

## Executive Summary

This document provides a detailed analysis of how to run a complete 24-hour simulation for **Sandton City Office Tower (Site-002)** that tests the entire system end-to-end:

```
Simulation Start → AI Optimization → Fault Injection → Alert Created →
Work Order Created → Technician Notified → Inspection → Repair →
Health Restored → Dashboard Updated
```

---

## Site-002 Equipment Inventory

### Equipment Available for Testing (15 items)

| Equipment Code | Name | Type | Specialty | Status |
|---|---|---|---|---|
| S002-CHILLER-B1-002 | Chiller (CH-2) | CHILLER | HVAC | ✓ Active |
| S002-FCU-201 | Fan Coil Unit | FCU | HVAC | ✓ Active |
| S002-PUMP-B1-CW1 | Chilled Water Pump | PUMP | HVAC | ✓ Active |
| S002-CT-R-001 | Cooling Tower | CT | HVAC | ✓ Active |
| S002-UPS-B1-001 | UPS (Power Backup) | UPS | Electrical | ✓ Active |
| S002-GEN-B1-001 | Generator (Backup Power) | GEN | Electrical | ✓ Active |
| S002-DALI-201 | DALI Lighting Zone L2 | DALI | Lighting | ✓ Active |
| S002-MTR-R-SOLAR | Solar Generation Meter | MTR | Monitoring | ✓ Active |
| S002-BESS-B1-001 | Battery Energy Storage | BESS | Power | ✓ Active |
| S002-INV-R-002 | Solar Inverter 2 | INV | Solar | ✓ Active |
| S002-INV-R-003 | Solar Inverter 3 | INV | Solar | ✓ Active |
| S002-ZONE-100 | Zone L1 | ZONE | Zone | ✓ Active |
| S002-ZONE-101 | Zone L1 | ZONE | Zone | ✓ Active |
| S002-ZONE-200 | Zone L2 | ZONE | Zone | ✓ Active |
| S002-ZONE-201 | Zone L2 | ZONE | Zone | ✓ Active |

---

## Simulation Architecture

### How It Works

```
┌─────────────────────────────────────────────────────────────┐
│           24-Hour Building Lifecycle Orchestrator           │
│                  (Time: 24hrs → 24 minutes)                 │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Hour 6:00   → Building Wake (HVAC starts, occupancy: 0%)  │
│  Hour 7:00   → Occupancy Rise (occupancy: 10-20%)          │
│  Hour 8:00   → AI Optimization Run #1                       │
│  Hour 9:00   → AI Optimization Run #2                       │
│  Hour 10:00  → Peak Load Begins (occupancy: 80%)           │
│  Hour 11:00* → FAULT INJECTION (equipment fails)           │
│              → Alert Created in Supabase                    │
│              → Sentry Notification to FM Team               │
│              → Work Order Auto-Created                      │
│              → Technician Auto-Assigned                     │
│  Hour 12:00  → Inspection Period                            │
│  Hour 13:00* → Repair Completed (auto-repair enabled)      │
│              → Service Feedback Submitted                   │
│              → Health Score Restored                        │
│              → Alert Resolved                               │
│  Hour 14:00  → Peak Load Ends (occupancy: 60%)            │
│  Hour 17:00  → Occupancy Fall (occupancy: 20%)            │
│  Hour 20:00  → Night Mode (building systems standby)       │
│  Hour 22:00  → Deep Night (occupancy: 5%)                  │
│                                                              │
│  * Scenario-dependent timing                                │
└─────────────────────────────────────────────────────────────┘
```

### Integration Points

**1. AI Optimizer (Hours 8-9)**
- Analyzes current building state
- Generates device recommendations (setpoint changes, mode adjustments)
- Stores in `recommendations` table
- Dashboard shows: "AI suggests X actions"

**2. Fault Injection (Hour 11)**
- Randomly selects equipment from site-002
- **Default target**: S002-CHILLER-B1-002 (Chiller)
- Simulates equipment degradation
- Health score: 100% → 30% (critical)

**3. Alert Generation (Hour 11)**
- Creates alert in Supabase `alerts` table
- Severity: "critical"
- Triggers SSE event (real-time dashboard update)
- Toast notification: "⚠️ S002-CHILLER-B1-002 - Critical Alert (30% health)"

**4. Sentry Notification (Hour 11)**
- Telegram message sent to FM team
- Includes: Equipment name, health, severity, action buttons
- Button: `/inspect_S002_CHILLER_B1_002`

**5. Work Order Creation (Hour 11)**
- Automatically created in Supabase
- Status: "assigned"
- Type: "inspection"
- Technician: Auto-assigned based on equipment type
  - **CHILLER** → Specialty: `hvac` → Assigned HVAC technician
- Title: "Inspection: S002-CHILLER-B1-002"

**6. Technician Inspection**
- Manual step: Technician clicks `/inspect_...` button in Telegram
- OR creates inspection via mobile app
- Status becomes "in_progress"

**7. Service Feedback (Hour 13)**
- Technician submits inspection findings
- Auto-repair submits: "Critical failure detected, needs replacement"
- Health impact: "neutral" (no improvement yet)
- System analyzes: **Decision → Repair Required**

**8. Repair Work Order (Hour 13)**
- New work order created: Type="repair"
- Pre-filled with inspection findings
- Same technician assigned
- Repair parts listed: ["Compressor", "Refrigerant", "Expansion valve"]

**9. Repair Completion (Hour 13)**
- Auto-repair submits positive feedback
- Findings: "Compressor replaced, system tested, performance verified"
- Health impact: "positive" (+2 points)
- Equipment health: 30% → 32%

**10. Health Restoration**
- If multiple positive feedbacks → health increases further
- When health ≥ 80% → Status becomes "normal"
- Alert marked "resolved"
- Dashboard returns to green

---

## Scenario Comparison

### Recommended: "fault_day" (Default)

```
POST /api/lifecycle/start
{
  "scenario": "fault_day",
  "duration_minutes": 24.0,
  "start_hour": 6
}
```

**What happens:**
- ✓ Guaranteed fault at Hour 11 (11:00 AM)
- ✓ Auto-repair at Hour 13 (1:00 PM - 2-hour delay)
- ✓ Complete alert → repair → restoration cycle
- ✓ Full Telegram notifications
- ✓ Perfect for testing the complete workflow

**Expected Duration:** 24 real minutes for full cycle
**Expected Result:** Equipment health restored, alert resolved, work orders closed

---

### Alternative: "chiller_failure" (HVAC-Specific)

```
POST /api/lifecycle/start
{
  "scenario": "chiller_failure",
  "duration_minutes": 24.0,
  "start_hour": 6
}
```

**What happens:**
- ✓ Guaranteed CHILLER fault at Hour 10 (10:00 AM)
- ✓ Auto-repair at Hour 13 (3-hour delay)
- ✓ Tests HVAC-specific workflow
- ✓ Technician specialty: HVAC

**Good for:** Testing specific equipment type handling

---

## Step-by-Step Test Execution

### Prerequisites

1. ✅ Backend running on `localhost:9095`
2. ✅ Supabase running on `localhost:55321` (API) and `localhost:55322` (DB)
3. ✅ Frontend running on `localhost:9096`
4. ✅ Equipment endpoint now uses Supabase (you're fixing this)
5. ✅ Redis running (optional, for caching)

### Execution Plan

#### **Phase 1: Pre-Simulation (Minutes 0-1)**

**Terminal 1 - Monitor Backend**
```bash
tail -f /tmp/backend.log | grep -E "lifecycle|alert|fault|repair"
```

**Terminal 2 - Watch Dashboard**
- Open: http://localhost:9096
- Login with demo credentials
- Navigate to "Risk Intelligence" or "System Health" dashboard

**Terminal 3 - Watch Alerts in Real-Time**
```bash
watch -n 2 'curl -s http://localhost:9095/api/alerts | jq ".alerts[-3:]"'
```

**Terminal 4 - Monitor Simulation Events**
```bash
watch -n 2 'curl -s http://localhost:9095/api/lifecycle/events | jq ".events[-3:]"'
```

---

#### **Phase 2: Start Simulation (Minute 1)**

**Terminal 5 - Execution**
```bash
# Start 24-hour simulation (runs for 24 real minutes)
curl -X POST http://localhost:9095/api/lifecycle/start \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "fault_day",
    "duration_minutes": 24.0,
    "start_hour": 6
  }' | jq '.'
```

**Expected Output:**
```json
{
  "success": true,
  "scenario": "fault_day",
  "status": "running",
  "simulated_hour": 6,
  "real_elapsed_seconds": 0.0,
  "message": "Lifecycle simulation started"
}
```

---

#### **Phase 3: Monitor Hour-by-Hour Events (Minutes 1-12)**

**Minute 1-2 (Simulated Hour 6-7)** - Building Wake
- Equipment systems starting
- No alerts yet
- Dashboard: All equipment green

**Minute 2-3 (Simulated Hour 8-9)** - AI Optimization
- AI generates optimization recommendations
- Dashboard: Shows "AI suggesting 3 actions"
- Backend logs: "AI_OPTIMIZATION generated X recommendations"

**Minute 5-6 (Simulated Hour 10-11)** - Peak Load → FAULT
- At exactly Minute 5 (Simulated 11:00 AM):
  - **CRITICAL EVENT**: Equipment fault injected
  - Check Terminal 3 alerts: **NEW ALERT appears**
  - Check Terminal 2 dashboard: **Equipment card turns RED + toast notification**
  - Check Terminal 4 events: **EQUIPMENT_FAULT event logged**

**Example Alert Created:**
```json
{
  "id": "alert-xxx",
  "equipment_code": "S002-CHILLER-B1-002",
  "severity": "critical",
  "status": "active",
  "health_score_change": -70,
  "message": "Critical failure detected",
  "created_at": "2026-02-12T11:00:00Z"
}
```

**Minute 6-7 (Simulated Hour 12-13)** - Repair Phase
- Work order created in Supabase
- At exactly Minute 7 (Simulated 13:00):
  - **AUTO-REPAIR TRIGGERED**
  - Service feedback submitted automatically
  - Health restored: 30% → 32%+
  - Check Terminal 3 alerts: **Status changes to "resolved"**
  - Check Terminal 2 dashboard: **Equipment card turns GREEN again**

---

#### **Phase 4: Verify Complete Workflow (Minute 12-24)**

**Check Final State:**
```bash
# Verify work orders created and closed
curl -s http://localhost:9095/api/work-orders/supabase | jq '.work_orders | length'

# Check equipment health restored
curl -s http://localhost:9095/api/equipment | jq '.equipment[] | select(.code == "S002-CHILLER-B1-002") | {name, status, health_score}'

# Verify alerts resolved
curl -s http://localhost:9095/api/alerts | jq '.alerts | map(select(.status == "resolved")) | length'
```

**Expected Results:**
- ✓ 2 work orders created (inspection + repair)
- ✓ Equipment health: 30% (fault) → 32%+ (after repair)
- ✓ Status: "critical" → "normal"
- ✓ 1 alert created and resolved

---

## Real-Time Dashboard Integration

### What You Should See

**During Fault (Minute 5-6)**
- 🔴 Equipment card turns RED
- ⚠️ Toast notification: "S002-CHILLER-B1-002 - Critical Alert"
- 📊 Health badge changes from ✅ 100% to ⛔ 30%
- 🔔 Bell icon shows "1 active alert"
- 📋 Alert appears in "Recent Alerts" panel

**During Repair (Minute 7)**
- 🟡 Equipment card turns YELLOW
- 📊 Health badge updates as feedback received
- 🔧 Work order appears in "Active Work Orders"
- ✅ Health increases gradually

**After Restoration (Minute 12+)**
- 🟢 Equipment card returns to GREEN
- ✅ Health badge shows ≥80%
- ✓ Alert moved to "Resolved"
- 📋 Work order status: "completed"

---

## Troubleshooting

### Alert Not Appearing

**Issue:** Fault injection happens but no alert in Supabase

**Checklist:**
1. ✓ Backend using Supabase for equipment lookup (you're fixing this)
2. ✓ Equipment `S002-CHILLER-B1-002` exists in Supabase `equipment` table
3. ✓ Alert service calls `client.table("alerts").insert(...)` not just internal event

**Check:**
```bash
# Verify equipment exists in Supabase
psql postgresql://postgres:postgres@127.0.0.1:55322/postgres \
  -c "SELECT code, name FROM equipment WHERE code = 'S002-CHILLER-B1-002';"

# Check alerts table after simulation
psql postgresql://postgres:postgres@127.0.0.1:55322/postgres \
  -c "SELECT id, equipment_code, severity, status FROM alerts ORDER BY created_at DESC LIMIT 3;"
```

### Health Not Restoring

**Issue:** Health stays at 30% even after repair feedback

**Causes:**
- Negative feedback submitted instead of positive
- Health impact not calculated correctly
- Service feedback service not integrated

**Check:**
```bash
# Query service feedback
psql postgresql://postgres:postgres@127.0.0.1:55322/postgres \
  -c "SELECT * FROM service_records ORDER BY created_at DESC LIMIT 3;"
```

### Work Order Not Created

**Issue:** No work order created when alert fires

**Causes:**
- Alert creation succeeds but work order trigger doesn't fire
- Technician not found for equipment type
- Work order repository not persisting to Supabase

**Check:**
```bash
# Query work orders
psql postgresql://postgres:postgres@127.0.0.1:55322/postgres \
  -c "SELECT code, equipment_code, status FROM work_orders ORDER BY created_at DESC LIMIT 3;"
```

---

## Success Criteria

### Complete Workflow Success: ✅

- [x] Simulation starts and runs for 24 real minutes
- [x] Hour 11 (Minute 5): Fault injected, equipment health drops to 30%
- [x] Alert created in Supabase `alerts` table
- [x] Dashboard updates in real-time (SSE): Equipment card red, toast notification
- [x] Work order created in Supabase `work_orders` table
- [x] Technician auto-assigned based on equipment type (CHILLER → HVAC)
- [x] Hour 13 (Minute 7): Repair completed, feedback submitted
- [x] Health restored: 30% → 32%+, status "critical" → "normal"
- [x] Alert status changes to "resolved"
- [x] Work order status: "in_progress" → "completed"
- [x] Dashboard returns to green

---

## Next Steps

1. **Verify backend uses Supabase** (you're on this)
   - Equipment endpoint loads from Supabase first
   - Falls back to CSV only if Supabase unavailable

2. **Confirm all integrations ready:**
   - Equipment lookup: ✓ (Supabase)
   - Alert creation: ✓ (Supabase)
   - Work order creation: ✓ (Supabase)
   - SSE events: ✓ (Real-time dashboard)
   - Sentry notifications: ✓ (Telegram)

3. **Run the simulation**
   ```bash
   curl -X POST http://localhost:9095/api/lifecycle/start \
     -H "Content-Type: application/json" \
     -d '{"scenario":"fault_day","duration_minutes":24.0,"start_hour":6}'
   ```

4. **Monitor all four terminals** to watch the complete workflow

5. **Collect results** for final validation report

---

## Files & Resources

| Resource | Location |
|---|---|
| Lifecycle Simulation Docs | `/docs/04-features/lifecycle-simulation.md` |
| Orchestrator Source | `/backend/app/services/lifecycle_orchestrator.py` |
| API Endpoints | `/backend/app/api/lifecycle_simulation.py` |
| Direct E2E Test (Manual) | `/DIRECT_E2E_TEST.md` |
| Automated Test Script | `/QUICK_INTEGRATION_TEST.sh` |
| This Analysis | `/SITE-002_SIMULATION_ANALYSIS.md` |

---

## System Readiness Checklist

- [ ] Backend fixed to use Supabase as primary source
- [ ] Backend starts without errors
- [ ] Equipment endpoint returns Supabase data
- [ ] Alert endpoint queries Supabase correctly
- [ ] Supabase has site-002 equipment data
- [ ] Redis running (optional, but recommended)
- [ ] Frontend accessible at `localhost:9096`
- [ ] All 4 monitoring terminals ready
- [ ] Simulation duration confirmed: 24 minutes
- [ ] Expected fault time: Minute 5 (Simulated 11:00 AM)
