---
title: "Demo Auto-Start System"
type: "reference"
status: "active"
version: "1.0.0"
created: "2026-02-14"
updated: "2026-02-14"
author: "Development Team"
tags: ["demo", "login", "auto-start", "client-specific"]
related: ["01-getting-started/demo-guide.md"]
domain: "demonstrations"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 15
---

# Demo Auto-Start System

## Overview

The Demo Auto-Start System automatically launches client-specific demonstrations when users log in. This enables seamless, personalized demo experiences without manual setup.

**How it works:**
1. User logs in with their email
2. Backend checks if email matches a demo user
3. Login response includes `demo_auto_start: true` flag
4. Frontend receives flag and auto-triggers appropriate simulation
5. Demo runs in background while user views dashboard

## Demo Consistency: Reproducible Yet Realistic

All demos are **reproducible but realistic** - energy results are identical every time, with realistic day-to-day occupancy variation:

**How it works:**
- ✅ No random faults injected (`fault_probability=0.0`)
- ✅ **Realistic occupancy variation by day-of-week** (seeded randomness)
- ✅ Deterministic AI recommendations (same sequence each run)
- ✅ **Energy results guaranteed identical** (variation averages to same totals)

**Occupancy Patterns (7-day week):**
```
Monday:    60% × 1.0  = ~54-66% (full office)
Tuesday:   60% × 0.95 = ~51-62% (hybrid work)
Wednesday: 60% × 0.90 = ~49-59% (some WFH)
Thursday:  60% × 0.88 = ~48-58% (more WFH)
Friday:    60% × 0.80 = ~43-53% (early departures)
Saturday:  30% (baseline only)
Sunday:    20% (minimal - servers + emergency)
```

**Energy Results (Guaranteed Identical):**
```
Grant runs Tuesday: Method 1 = 88.2 kWh | Method 2 = 42.0 kWh | Method 3 = 38.0 kWh
Grant runs Friday:  Method 1 = 88.2 kWh | Method 2 = 42.0 kWh | Method 3 = 38.0 kWh ✓ IDENTICAL
Next month:         Method 1 = 88.2 kWh | Method 2 = 42.0 kWh | Method 3 = 38.0 kWh ✓ IDENTICAL
```

**Why identical energy despite varying occupancy?**
- Same scenario name → same random seed (reproducible)
- Different daily occupancies average out to same weekly total
- AI recommendations follow same pattern (deterministic)
- Result: Realistic but professional demos perfect for clients ✨

---

## Current Demos

### 1. Grant's Three-Method Comparison
**Client Email:** `grant@grantdemo.co.za`

**Demo Type:** `three-method-comparison`

**Scenarios:**
- Method 1: HVAC ONLY (Baseline - 88.2 kWh/7 days)
- Method 2: HVAC + DALI (Reactive - 42.0 kWh/7 days, 52% savings)
- Method 3: HVAC + DALI + SENTINEL AI (Predictive - 38.0 kWh/7 days, 57% savings)

**Endpoints:**
```
POST /api/lifecycle/demo/method-1-hvac-only
POST /api/lifecycle/demo/method-2-hvac-dali
POST /api/lifecycle/demo/method-3-hvac-dali-sentinel
```

**Duration:** 15 minutes (simulates 7 days)

**Data Queried:**
- `GET /api/lifecycle/status` - Current simulated time
- `GET /api/lifecycle/energy-summary` - Energy accumulation
- `GET /api/lifecycle/events` - Simulation events

---

### 2. Solar/BESS Client Comparison
**Client Email:** `bederf@protonmail.com`

**Demo Type:** `solar-bess-comparison`

**Scenarios:**
- Baseline: Simple reactive control (~R1,750-2,450/week savings)
- Sentinel AI: TOU arbitrage + demand management (~R5,950-8,400/week savings)

**Endpoints:**
```
POST /api/lifecycle/demo/solar-bess-baseline
POST /api/lifecycle/demo/solar-bess-sentinel
```

**Duration:** 15 minutes (simulates 7 days)

**Financial Metrics:**
- Daily savings: R250-350 (baseline) vs R850-1,200 (AI optimized)
- AI benefit: +R4,200-5,950/week vs baseline

---

## Architecture

### Login Flow

```
User Login (email)
    ↓
Backend: Check _DEMO_USERS dict
    ↓
    ├─ If grant@grantdemo.co.za
    │  ├─ Call orchestrator.reset() ← Fresh state
    │  └─ Add demo_auto_start: true
    │     └─ demo_type: "three-method-comparison"
    │
    ├─ If bederf@protonmail.com
    │  ├─ Call orchestrator.reset() ← Fresh state
    │  └─ Add demo_auto_start: true
    │     └─ demo_type: "solar-bess-comparison"
    │
    └─ Otherwise → No demo_auto_start flag
    ↓
Return LoginResponse with demo_auto_start flag
    ↓
Frontend: Receives response
    ↓
If demo_auto_start === true:
    └─ POST /api/lifecycle/demo/{scenario}
       └─ Simulation starts in background (fresh state)
```

### Demo State Management

**Key Behavior: Demos Reset on Every Login**

Each time a demo user logs in, the orchestrator is reset to a clean state:

```python
# In auth.py login endpoints:
if email == "grant@grantdemo.co.za":
    orchestrator = get_lifecycle_orchestrator()
    orchestrator.reset()  # Clears all previous simulation state
    response["demo_auto_start"] = True
    # ...
```

**What gets reset:**
- ✅ Previous simulation stopped
- ✅ Events history cleared
- ✅ Active faults removed
- ✅ Pending repairs removed
- ✅ Simulated time reset to midnight
- ✅ Ready for fresh demo

**Why this matters:**
- Grant logs in at 2pm → Demo starts fresh ✓
- Grant logs out and back in at 3pm → Demo restarts from beginning ✓
- No residual state from previous session
- Consistent, professional demo experience every time

### Login Response Example (Grant)

```json
{
  "access_token": "eyJ0eXAi...",
  "refresh_token": "eyJ0eXAi...",
  "token_type": "bearer",
  "user": {
    "id": "grant-demo",
    "email": "grant@grantdemo.co.za",
    "full_name": "Grant",
    "role": "operator"
  },
  "expires_at": "2026-02-14T17:30:00",
  "mfa_required": false,
  "mfa_enrolled": false,
  "mfa_challenge_pending": false,
  "session_id": "sess-abc123",
  "demo_auto_start": true,
  "demo_type": "three-method-comparison",
  "demo_description": "HVAC Only vs HVAC+DALI vs HVAC+DALI+Sentinel AI"
}
```

---

## Adding a New Demo

### Step 1: Define Login Trigger (Backend)

**File:** `backend/app/api/auth.py`

Add email to both login endpoints:

```python
# In login_with_email() function (line ~347)
if email == "new-client@example.com":
    response["demo_auto_start"] = True
    response["demo_type"] = "my-new-demo"
    response["demo_description"] = "Description of what the demo shows"

# In complete_mfa_login() function (line ~520)
if email == "new-client@example.com":
    response["demo_auto_start"] = True
    response["demo_type"] = "my-new-demo"
    response["demo_description"] = "Description of what the demo shows"
```

**Required fields in response:**
- `demo_auto_start: true` - Enables auto-start
- `demo_type: string` - Machine-readable demo identifier (used by frontend)
- `demo_description: string` - Human-readable description

---

### Step 2: Create Demo Endpoints (Backend)

**File:** `backend/app/api/lifecycle_simulation.py`

Add endpoint decorator and handler:

```python
@router.post("/demo/my-new-demo")
async def run_my_new_demo():
    """
    My New Demo: Brief Description

    Realistic scenario with:
    - Key feature 1
    - Key feature 2
    - Key feature 3

    Expected result: Metric showing benefit
    """
    orchestrator = get_lifecycle_orchestrator()

    if orchestrator.running:
        await orchestrator.stop()

    # Start simulation with your scenario
    result = await orchestrator.start(
        scenario="my_new_demo_scenario",
        duration_minutes=15.0,  # 7 days in 15 minutes
        start_hour=6
    )

    return {
        **result,
        "demo_type": "my-new-demo",
        "description": "Human-readable description",
        "demo_info": {
            "duration_minutes": 15,
            "scenario_used": "my_new_demo_scenario",
            "key_metric_1": "value",
            "key_metric_2": "value",
            "watch_events_at": "/api/lifecycle/events",
            "financial_summary_endpoint": "/api/lifecycle/my-summary"
        }
    }
```

**Critical points:**
- Use `duration_minutes=15.0` for 7-day simulations (5.4 sec per hour)
- Use `start_hour=6` for building start time
- Remove any `await asyncio.sleep()` calls (breaks HTTP response)
- Return `demo_info` dict with relevant metrics
- Always include `watch_events_at` for real-time monitoring

---

### Step 3: Define Scenario (Backend)

**File:** `backend/app/services/lifecycle_orchestrator.py`

Add scenario to SCENARIOS dict (around line ~1000):

```python
SCENARIOS = {
    # ... existing scenarios ...

    "my_new_demo_scenario": ScenarioConfig(
        name="My New Demo",
        description="Description of what happens in this scenario",
        fault_probability=0.0,  # 0 = no faults, 0.3 = 30% chance
        fault_hour=None,  # Random if None, specific hour if set
        fault_equipment_type=None,  # Specific type if set
        auto_repair=True,
        repair_delay_hours=2,
        optimization_enabled=True,
        sentry_notifications=False,
        operation_mode=OperationMode.HVAC_DALI_SENTINEL  # Pick appropriate mode
    ),
}
```

**Scenario configuration options:**
- `name`: Display name for logs
- `description`: What happens during scenario
- `fault_probability`: 0.0-1.0 (0 = no faults, 0.3 = 30% random)
- `fault_hour`: Hour to inject fault (None = random)
- `fault_equipment_type`: Equipment type to fault (None = random)
- `auto_repair`: Auto-complete repair after delay
- `repair_delay_hours`: Hours after fault before auto-repair
- `optimization_enabled`: Enable AI optimization recommendations
- `sentry_notifications`: Send Telegram notifications
- `operation_mode`: HVAC_ONLY, HVAC_DALI, HVAC_DALI_SENTINEL, SOLAR_BESS_BASELINE, SOLAR_BESS_SENTINEL

---

### Step 4: Frontend Auto-Start Logic

**File:** `frontend/src/components/App.tsx` or login handler

Check for demo_auto_start flag:

```typescript
// After successful login
const response = await apiClient.login(email);

if (response.demo_auto_start) {
  // Auto-start the demo
  const demoType = response.demo_type; // "my-new-demo"

  // Map demo type to endpoint
  const endpointMap = {
    "three-method-comparison": [
      "/api/lifecycle/demo/method-1-hvac-only",
      "/api/lifecycle/demo/method-2-hvac-dali",
      "/api/lifecycle/demo/method-3-hvac-dali-sentinel"
    ],
    "solar-bess-comparison": [
      "/api/lifecycle/demo/solar-bess-baseline",
      "/api/lifecycle/demo/solar-bess-sentinel"
    ],
    "my-new-demo": [
      "/api/lifecycle/demo/my-new-demo"
    ]
  };

  // Trigger all endpoints for this demo
  const endpoints = endpointMap[demoType] || [];
  for (const endpoint of endpoints) {
    await fetch(endpoint, { method: "POST" });
  }

  // Optional: Show toast notification
  showToast(`Auto-starting: ${response.demo_description}`);
}
```

---

## Testing Your New Demo

### 1. Backend Verification

```bash
# Verify syntax
python3 -m py_compile backend/app/api/auth.py
python3 -m py_compile backend/app/api/lifecycle_simulation.py
python3 -m py_compile backend/app/services/lifecycle_orchestrator.py

# Should output: ✓ (no errors)
```

### 2. Manual Login Test

```bash
# Terminal 1: Start backend
./start-backend.sh

# Terminal 2: Test login endpoint
curl -s -X POST "http://localhost:9095/api/auth/login?email=new-client@example.com" \
  | jq '.demo_auto_start, .demo_type'

# Should output:
# true
# "my-new-demo"
```

### 3. Manual Demo Endpoint Test

```bash
# Start demo
curl -s -X POST "http://localhost:9095/api/lifecycle/demo/my-new-demo" | jq '.success'

# Should output: true

# Check status after 5 seconds
curl -s http://localhost:9095/api/lifecycle/status | jq '.simulated_hour, .progress_percent'

# Should show progressing time
```

### 4. Frontend Integration Test

1. Clear browser cache
2. Navigate to login page
3. Enter new demo email
4. Verify auto-start happens (check Network tab for demo endpoint calls)
5. Verify dashboard shows simulation progress

---

## Monitoring Active Demos

### Check Current Simulation Status
```bash
# Get real-time status
curl http://localhost:9095/api/lifecycle/status | jq '.'

# Expected output:
{
  "running": true,
  "scenario": "My New Demo",
  "simulated_hour": 12,
  "progress_percent": 50,
  "events_count": 25
}
```

### View Simulation Events
```bash
# Get all events
curl 'http://localhost:9095/api/lifecycle/events?limit=100' | jq '.events[] | {hour: .hour, type: .event_type, description: .description}'

# Filter by event type
curl 'http://localhost:9095/api/lifecycle/events?event_type=ai_optimization' | jq '.events | length'
```

### Get Energy/Financial Summary
```bash
# Energy data
curl http://localhost:9095/api/lifecycle/energy-summary | jq '.energy_data'

# Solar/BESS financial data
curl http://localhost:9095/api/lifecycle/solar-bess-comparison | jq '.financial_analysis'
```

---

## Troubleshooting

### Demo Not Auto-Starting

**Checklist:**
1. ✅ Email added to both `login_with_email()` and `complete_mfa_login()` in auth.py
2. ✅ `demo_auto_start: true` in response dict
3. ✅ Backend restarted after code changes
4. ✅ Browser cache cleared before test

**Debug:**
```bash
# Check login response
curl -s -X POST "http://localhost:9095/api/auth/login?email=test@example.com" | jq '.'

# Should contain:
# "demo_auto_start": true
# "demo_type": "..."
```

### Demo Endpoint Returns 500 Error

**Common causes:**
1. Scenario name doesn't exist in SCENARIOS dict → Check spelling
2. Blocking sleep in endpoint → Remove `await asyncio.sleep()`
3. Invalid OperationMode enum → Use exact enum value

**Debug:**
```bash
# Check backend logs
tail -f backend.log | grep ERROR

# Test endpoint directly
curl -v -X POST "http://localhost:9095/api/lifecycle/demo/my-new-demo"
```

### Simulation Doesn't Progress

**Common causes:**
1. Site filtering wrong → All equipment filtered out
2. Scenario has no equipment defined → Query returns empty list

**Debug:**
```bash
# Check if equipment exists for site
curl 'http://localhost:9095/api/sites/site-002/equipment' | jq '.equipment | length'

# Should return > 0

# Check scenario equipment loading in logs
tail -f backend.log | grep equipment
```

---

## Best Practices

### 1. Equipment Filtering
Always use `building_id="site-002"` when querying equipment in simulations:
```python
# ✅ CORRECT
equipment_list = self.equipment_repo.get_all(building_id="site-002")

# ❌ WRONG - loads from all sites
equipment_list = self.equipment_repo.get_all()
```

### 2. No Blocking Calls
Never use blocking sleep in demo endpoints:
```python
# ❌ WRONG - blocks HTTP response for 15 minutes
await asyncio.sleep(15 * 60 + 2)

# ✅ CORRECT - return immediately, orchestrator runs in background
return { **result, "demo_info": {...} }
```

### 3. Consistent Duration
Use 15 minutes for 7-day simulations (5.4 seconds per simulated hour):
```python
# ✅ Standard duration
duration_minutes=15.0
# = 7 days * 24 hours / 15 real minutes
# = 5.4 seconds per hour
```

### 4. Meaningful Metrics
Include relevant metrics in demo_info:
```python
# For HVAC demos:
"expected_energy_kwh": 88.2,
"savings_vs_baseline_percent": 57,

# For Solar/BESS demos:
"expected_daily_savings_r": "R850-1200",
"ai_benefit_vs_baseline_annual_r": "R220000-310000"
```

### 5. Documentation Comments
Document what each demo shows:
```python
"""
My Demo: Feature Description

Realistic scenario with:
- Occupancy patterns (Mon-Fri vs Sat-Sun)
- AI optimization enabled
- Energy consumption and cost impact

Expected result: X% savings vs baseline
"""
```

---

## Checklist: Adding a New Demo

- [ ] Add email to `backend/app/api/auth.py` - `login_with_email()` function
- [ ] Add email to `backend/app/api/auth.py` - `complete_mfa_login()` function
- [ ] Create demo endpoint in `backend/app/api/lifecycle_simulation.py`
- [ ] Create scenario in `backend/app/services/lifecycle_orchestrator.py` SCENARIOS dict
- [ ] Verify Python syntax: `python3 -m py_compile` (all 3 files)
- [ ] Test login endpoint returns demo_auto_start=true
- [ ] Test demo endpoint returns success=true
- [ ] Test simulation progresses: Check events after 5 seconds
- [ ] Update frontend demo endpoint mapping
- [ ] Clear browser cache and test end-to-end
- [ ] Test with real user email
- [ ] Document in this file (DEMO-AUTO-START-SYSTEM.md)

---

## Future Expansion Ideas

1. **Regional Demos**: Different scenarios per geographic region
2. **Industry Demos**: Hospital (site-003), retail, office, industrial
3. **Feature Demos**: Highlight specific capabilities (3D viz, chat, MFA, etc.)
4. **Performance Demos**: Compare optimization strategies (HVAC vs Solar vs Water)
5. **Customizable Demos**: Admin-configurable scenarios per client

---

## Related Documentation

- **Demo Guide:** [docs/01-getting-started/demo-guide.md](demo-guide.md)
- **Lifecycle Simulation:** [docs/04-features/demo-simulation-control.md](demo-simulation-control.md)
- **API Reference:** [docs/03-api-reference/lifecycle-simulation.md](lifecycle-simulation.md)
- **CLAUDE.md:** Quick reference for development workflows

---

**Last Updated:** 2026-02-14
**Maintainers:** Development Team
**Status:** Active - Ready for new demo additions
