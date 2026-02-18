# CLAUDE_WORKFLOWS.md

Complete end-to-end workflows and feature descriptions.

## Workflow 1: Equipment Fault → Resolution

**Timeline:** ~2 hours from fault detection to full recovery

### Stage 1: Fault Detection

```
Equipment sensor detects fault (e.g., temperature out of range)
    ↓
PostgreSQL trigger evaluates: Is health_score < 50?
    ↓
Health score updated based on sensor deviation magnitude
    ↓
If health < 50% → Equipment enters WARNING state
```

**Example:** CHILLER discharge temp rising → sensor reading 35°C (vs 28°C setpoint) → health drops 100% → 45%

### Stage 2: Alert & Work Order Creation

```
PostgreSQL trigger: equipment_alert_trigger fires
    ↓
Alert created: severity calculated from equipment type + fault magnitude
    ↓
Work order auto-created (code: WO-SIM, status: pending)
    ↓
Technician assignment: equipment type → specialty
    ├─ CHILLER, AHU, FCU, VAV → hvac specialty
    ├─ GEN, UPS, MTR, DB → electrical specialty
    ├─ DALI, LUM → dali specialty
    ├─ FIRE → fire specialty
    └─ API: GET /api/work-orders/technician-for-equipment/{code}
```

### Stage 3: Notification (Telegram Auto-Trigger)

```
Service record created (status='notified')
    ↓
Background job wakes every 30 seconds
    ↓
Processes all pending service records
    ↓
Sentry bot sends Telegram: Equipment code, issue, diagnostics
    ↓
Technician receives notification on phone
```

**Example:** "⚠️ CHILLER Alert | S002-CHILLER-B1-001 | Filter diff high | John Smith assigned | Reply when done"

### Stage 4: Service Completion

```
Technician arrives on-site
    ↓
Performs repair/maintenance (filter replacement, sensor calibration)
    ↓
Submits service feedback via Sentry bot
    ├─ Templates loaded from ml_data_templates.json
    ├─ Questions: What action? Result? Impact?
    └─ Submits health impact score: positive/neutral/negative/critical
```

### Stage 5: Health Restoration & Alert Resolution

```
Backend receives feedback submission
    ↓
Health score updated: new_health = old_health + impact
    ├─ +2 for positive (fix successful)
    ├─ +0 for neutral (service done, no change)
    ├─ -3 for negative (service made worse)
    └─ -5 for critical (equipment now unsafe)
    ↓
If new_health ≥ 80% → Alert auto-resolved
    ↓
Dashboard updates real-time (SSE): equipment status green ✅
```

### Files Involved

- **Alert creation:** `backend/app/api/alerts.py`, triggers in `supabase/migrations/`
- **Work order:** `backend/app/api/work_orders.py`, `work_order_repository.py`
- **Notification:** `backend/app/api/clawd_webhooks.py`, `background_scheduler.py` (30s job)
- **Feedback:** `backend/app/api/service_feedback.py`, `feedback_collection_service.py`

### Example Timeline (fault_day simulation)

```
11:00 AM - Fault injected: Health 100% → 45%
11:00 AM - Alert created (<1 second)
11:00 AM - Work order created & assigned (<1 second)
11:00 AM - Service record status='notified'
11:00 AM - Background job processes (next 30s tick)
11:01 AM - Telegram sent to technician
13:00 PM - Technician repairs (2 hours elapsed)
13:00 PM - Feedback submitted: "replaced filter, recalibrated" (impact: +2)
13:00 PM - Health updated: 45% + 2 = 85% (restored)
13:00 PM - Alert auto-resolved
Dashboard - Equipment shows green ✅
```

---

## Workflow 2: Device Control Approval (Tier 2)

**Summary:** AI recommendation → Operator review → Safety validation → Device write → COV feedback

### Stage 1: AI Generates Recommendation

```
Background job (10-minute interval) analyzes equipment
    ↓
Queries: equipment with health_score < 90
    ↓
Creates maintenance recommendation
    ├─ Description: "Cool building 5°C lower"
    ├─ Target value: 18°C (vs current 22°C)
    ├─ Reason: "Anticipatory pre-cooling for peak demand"
    └─ Status: PENDING
```

### Stage 2: Operator Reviews & Approves

```
Frontend displays in "Pending Approvals" list
    ↓
Operator clicks recommendation
    ↓
Reviews:
  ├─ Current: 22°C
  ├─ Target: 18°C
  ├─ Reason: Pre-cooling
  ├─ Safety: ✅ Safe
    ↓
Operator clicks "Approve"
```

### Stage 3: Backend Validates (Defense-in-Depth)

```
Safety rules re-evaluated:
  ├─ Temperature range: 16-28°C (default)
  ├─ Pressure limits
  ├─ Interlocks (can't cool if already at limit)
  ├─ Runtime limits (max 12h continuous)
    ↓
If validation FAILS → Status: REJECTED, reason logged
If validation PASSES → Proceed to device write
```

### Stage 4: Device Write & COV Feedback

```
Original value saved (for rollback): 22°C
    ↓
Write command sent to device via device_manager
    ↓
Device receives command
    ↓
COV (Change of Value) feedback returned: "Now at 18°C"
    ↓
Comparison:
  ├─ If COV matches target (18°C ≈ 18°C) → Status: EXECUTED ✅
  ├─ If COV mismatches (returned 20°C, not 18°C) → ERROR, allow rollback
  └─ Execution stored: {original: 22°C, target: 18°C, actual: 18°C}
```

### Stage 5: Rollback (If Needed)

```
Operator sees mismatch or wants to undo
    ↓
Clicks "Rollback" button
    ↓
Backend restores original: 22°C
    ↓
Status: ROLLED_BACK
    ↓
Audit entry created: who, when, why
```

### Files

- **API:** `backend/app/api/approvals.py` (GET, POST, PUT, DELETE endpoints)
- **Logic:** `backend/app/services/approval_service.py`, `safety_interlocks.py`
- **Frontend:** `frontend/src/components/Recommendations/ApprovalDialog.tsx`, `RecommendationsList.tsx`

### Key Status States

```
PENDING    → Awaiting operator approval
APPROVED   → Operator approved, awaiting execution
EXECUTED   → Successfully written to device
REJECTED   → Operator rejected
ROLLED_BACK → Operator rolled back after execution
ERROR      → Device write failed (COV mismatch)
```

---

## Workflow 3: Module System (Feature Activation)

**Purpose:** Admin can enable/disable features per building without code changes

### 16 Available Modules

```
Energy (amber)          → Solar + energy management
HVAC (blue)             → Heating/cooling control
Security (purple)       → Access control, CCTV
Lighting (yellow)       → DALI control
Water (blue)            → Consumption monitoring
Fire (red)              → Safety systems
Sustainability (emerald) → ESG metrics, carbon tracking
Contracts (orange)      → Maintenance contracts
ML (cyan)               → ML model deployment
Notifications (rose)    → Alerts, escalations
Integrations (sky)      → APIs, webhooks
Control (slate)         → Device control
Assets (indigo)         → Asset register
SIMBIOT (teal)          → External connectors
Access (green)          → Door locks
```

### API Workflow

```bash
# List all modules
GET /api/modules/available
# Returns: [
#   {name: "hvac", enabled: true, health: 95},
#   {name: "energy", enabled: false, integrations: ["hvac", "notifications"]}
# ]

# Activate module
POST /api/modules/activate
# Body: {site_id: "site-002", module_type: "energy"}
# Response: {activated: true, dependencies: ["ml", "notifications"]}

# Check integrations
GET /api/modules/site/{site_id}/integration
# Returns: {
#   active: ["hvac", "energy", "notifications"],
#   potential: {energy: ["peak_shaving"], hvac: ["occupancy_control"]}
# }
```

### Example: Activating Energy Module

```
1. Admin opens ModuleSelector in dashboard
2. Clicks toggle for "Energy" module
3. POST /api/modules/activate {site_id: "site-002", module_type: "energy"}
4. Backend enables:
   - Energy dashboard
   - Solar API access
   - Peak demand coordination
5. Frontend shows:
   - Energy tab in tabbed view
   - Consumption graphs
   - Solar generation chart
   - Peak demand alerts
6. AI optimizer now includes energy recommendations
7. Notifications can send peak demand alerts
```

### Files

- **API:** `backend/app/api/modules.py` (8 endpoints)
- **Frontend:** `frontend/src/components/modules/ModuleSelector.tsx`, `ModularDashboard.tsx`
- **Hooks:** `frontend/src/hooks/useModuleContext()` (state management)

---

## Workflow 4: Lifecycle Simulation (24-Hour or Annual)

**Purpose:** Test features without waiting for real faults or time to pass

### Quick Cycle (5 minutes, realistic timing)

```bash
curl -X POST http://localhost:9095/api/lifecycle/demo/quick-cycle \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "site_id": "site-002",
    "scenario": "fault_day",
    "compression_factor": 240
  }'

# Simulates 24 hours in 5 real minutes
# 6 AM → 6 PM = 12 hours
# Each real second ≈ 48 simulated seconds (240x compression)
```

### Available Scenarios

- `normal_day` - Equipment operates normally (baseline)
- `fault_day` - Single fault at hour 11 (tests alert → repair)
- `chiller_failure` - Critical chiller failure (escalation)
- `multi_fault` - Multiple cascading failures (prioritization)
- `maintenance_day` - Planned maintenance (feedback loop)

### Timeline Inside Simulation (fault_day)

```
Hour 0:  06:00 AM - Building wakes up
Hour 3:  09:00 AM - Occupancy 30%
Hour 5:  11:00 AM - Peak demand begins (80%)
Hour 6:  12:00 PM - Peak load (95%), 32°C ambient
         ← FAULT INJECTED HERE
         ← Alert created (<1s)
         ← Work order assigned (<1s)
Hour 8:  14:00 PM - Repair begins
Hour 9:  15:00 PM - Repair completes, feedback submitted
         ← Health restored (45% → 85%)
         ← Alert resolved
Hour 24: 06:00 AM - Next day (simulation ends)
```

### What Gets Tested

✅ AI optimization decisions (pre-cooling, load shedding)
✅ Fault detection (sensor thresholds)
✅ Alert generation (timing, severity)
✅ Work order lifecycle (creation, assignment, completion)
✅ Service feedback (health score updates)
✅ Dashboard updates (real-time SSE)
✅ Background job notifications (Telegram)

### Output

- **Location:** `backend/app/data/simulation_logs/sim_{timestamp}_{id}_*.json`
- **Contains:** Hourly summaries, fault events, alert timestamps, assignments, feedback

---

## Data Flow: Alert → Resolution

```
1. Sensor detects fault
   ↓
2. PostgreSQL trigger updates health_score
   ↓
3. Trigger creates alert (severity calculated)
   ↓
4. Trigger creates work order (WO-SIM code)
   ↓
5. Technician lookup by equipment type → specialty
   ↓
6. Service record created (status='notified')
   ↓
7. Background job (30s) processes pending notifications
   ↓
8. Sentry bot sends Telegram
   ↓
9. Technician replies "done" or submits feedback
   ↓
10. Service record status → 'data_collection'
   ↓
11. Technician feedback endpoint updates health
   ↓
12. If health ≥ 80%: Alert status → 'resolved'
   ↓
13. Dashboard updates (SSE broadcast)
   ↓
14. Equipment shows green ✅
```

---

See related docs:
- `CLAUDE_ARCHITECTURE.md` - System design
- `CLAUDE_DATABASE.md` - Data schema
- `CLAUDE_INTEGRATION.md` - Telegram, SIMBIOT, MCP
