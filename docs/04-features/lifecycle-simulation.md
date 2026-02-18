---
title: "24-Hour Building Lifecycle Simulation"
type: "guide"
status: "approved"
version: "1.0.0"
created: "2026-02-05"
updated: "2026-02-05"
author: "Sentinel Development Team"
tags: ["simulation", "demo", "testing", "lifecycle"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
---

# 24-Hour Building Lifecycle Simulation

Simulates a complete 24-hour building day to test and demonstrate the full AI optimization, fault detection, alert, repair, and feedback cycle.

## Overview

The lifecycle simulation compresses 24 simulated hours into 2-24 real minutes, allowing rapid testing of:

- AI optimization recommendations
- Equipment health degradation
- Fault detection and alert generation
- Work order creation and technician dispatch
- Service feedback submission
- Health score restoration
- Alert resolution

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Lifecycle Orchestrator                        │
│  (backend/app/services/lifecycle_orchestrator.py)                │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐           │
│  │ Time Engine │   │  Scenario   │   │   Event     │           │
│  │ (compress)  │   │   Config    │   │   Logger    │           │
│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘           │
│         │                 │                 │                   │
│         └─────────────────┼─────────────────┘                   │
│                           │                                     │
│                    ┌──────▼──────┐                              │
│                    │ Hour Loop   │                              │
│                    │  Processor  │                              │
│                    └──────┬──────┘                              │
│                           │                                     │
│         ┌─────────────────┼─────────────────┐                   │
│         │                 │                 │                   │
│   ┌─────▼─────┐    ┌─────▼─────┐    ┌─────▼─────┐             │
│   │ Building  │    │   Fault   │    │  Repair   │             │
│   │  Events   │    │ Injection │    │ Scheduler │             │
│   └───────────┘    └───────────┘    └───────────┘             │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  AI Optimizer   │  │  Alert Service  │  │ Service Feedback│
│  (recommendations)│  │  (Clawd notify) │  │  (health update)│
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

## Thermal Simulation Engine Integration (Phase 5.5)

**NEW:** Zone temperatures now react realistically to occupancy, time of day, and HVAC response!

Each simulated hour, the **Thermal Simulation Engine** creates realistic sensor data:

### Daily Temperature Profile

**Example: Office Zone (Zone-001)** with realistic occupancy:
```
06:00  Night          0% occupancy     18.2°C
08:00  Arrival       60% occupancy     21.5°C  (+3.3°C warmup)
11:00  Peak          85% occupancy     23.8°C  (+2.3°C occupancy heat)
14:00  Peak + Solar  85% occupancy     24.2°C  (+0.4°C solar gain)
18:00  Evening       30% occupancy     22.1°C  (-2.1°C cooldown)
22:00  Setback        0% occupancy     19.5°C  (-2.6°C night mode)
```

### What This Enables

✅ **AI Recommendations** - "Zone at 24.2°C with 85% occupancy → reduce setpoint to 20°C"
✅ **ML Training** - 157,680 realistic sensor readings/year for occupancy patterns
✅ **Energy Accuracy** - Calculate actual wasted energy = (temp above setpoint) × hours × occupancy
✅ **Fault Detection** - Anomalies visible when zones can't reach setpoint

### Equipment Health Degradation (Future Maintenance Sims)

**Infrastructure ready** but DISABLED for baseline (Grant/Bederf):

To enable for maintenance/fault scenarios:
```python
# In lifecycle_orchestrator.py, line ~705:
consider_equipment_health=True  # Enable health degradation
```

Then degrade equipment:
```sql
UPDATE equipment SET health_score = 50 WHERE code = 'S002-CHILLER-B1-001';
```

Result: Chiller at 50% → Peak zone rises from 24.2°C to 25.8°C (can't cool)

**Learn more:** [`docs/04-features/thermal-simulation.md`](./thermal-simulation.md)

---

## API Endpoints

### Control Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/lifecycle/start` | POST | Start simulation with scenario |
| `/api/lifecycle/stop` | POST | Stop running simulation |
| `/api/lifecycle/pause` | POST | Pause simulation |
| `/api/lifecycle/resume` | POST | Resume paused simulation |
| `/api/lifecycle/status` | GET | Get current simulation status |

### Event Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/lifecycle/events` | GET | Get simulation events (filterable) |
| `/api/lifecycle/events/timeline` | GET | Events organized by hour |
| `/api/lifecycle/scenarios` | GET | List available scenarios |
| `/api/lifecycle/scenarios/{id}` | GET | Get scenario details |

### Manual Intervention

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/lifecycle/inject-fault` | POST | Manually inject a fault |
| `/api/lifecycle/trigger-repair/{code}` | POST | Force repair completion |

### Demo Shortcuts

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/lifecycle/demo/quick-cycle` | POST | 5-minute demo cycle |
| `/api/lifecycle/demo/ultra-fast` | POST | 2-minute demo cycle |

## Scenarios

### normal_day
- **Description:** Typical building operations
- **Fault Probability:** 10%
- **Auto-Repair:** No
- **Use Case:** Baseline demonstration

### fault_day (Default)
- **Description:** Guaranteed fault with auto-repair
- **Fault Hour:** 11:00 (simulated)
- **Repair Hour:** 14:00 (simulated)
- **Auto-Repair:** Yes
- **Use Case:** Full lifecycle demonstration

### chiller_failure
- **Description:** Chiller-specific fault scenario
- **Fault Equipment Type:** CHILLER
- **Fault Hour:** 10:00 (simulated)
- **Auto-Repair:** Yes
- **Use Case:** HVAC fault workflow demo

### multi_fault
- **Description:** Multiple equipment failures
- **Fault Probability:** 80%
- **Fault Equipment Types:** Various
- **Auto-Repair:** Yes (4-hour delay)
- **Use Case:** Stress testing, multiple alert handling

### maintenance_day
- **Description:** Scheduled maintenance day
- **Fault Probability:** 0%
- **Auto-Repair:** N/A
- **Use Case:** Maintenance workflow demonstration

## Time Compression

The `duration_minutes` parameter controls how real time maps to simulated time:

| Duration | Real Time per Hour | Total Duration | Use Case |
|----------|-------------------|----------------|----------|
| 24.0 | 1 minute | 24 minutes | Detailed demo |
| 12.0 | 30 seconds | 12 minutes | Standard demo |
| 5.0 | 12.5 seconds | 5 minutes | Quick demo |
| 2.0 | 5 seconds | 2 minutes | Ultra-fast testing |

## Hour-by-Hour Events

The simulation processes events based on simulated hour:

| Hour | Event Type | Description |
|------|------------|-------------|
| 6:00 | `building_wake` | Building systems start up |
| 7:00 | `occupancy_rise` | Occupancy begins increasing |
| 8:00-9:00 | `ai_optimization` | AI analyzes and recommends |
| 10:00-14:00 | `peak_load` | Peak occupancy and load |
| 11:00* | `fault_injection` | Fault occurs (fault_day scenario) |
| 14:00* | `repair_complete` | Auto-repair (fault_day scenario) |
| 17:00-18:00 | `occupancy_fall` | Occupancy decreases |
| 20:00-6:00 | `night_mode` | Building in standby |

*Scenario-dependent

## Usage Examples

### Start 5-Minute Demo

```bash
curl -X POST http://localhost:9095/api/lifecycle/demo/quick-cycle
```

### Start Custom Simulation

```bash
curl -X POST http://localhost:9095/api/lifecycle/start \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "fault_day",
    "duration_minutes": 10,
    "start_hour": 6
  }'
```

### Monitor Events

```bash
# Watch events in real-time
watch -n 5 'curl -s http://localhost:9095/api/lifecycle/events | jq ".events[-5:]"'
```

### Inject Fault Manually

```bash
curl -X POST "http://localhost:9095/api/lifecycle/inject-fault?fault_type=vibration"
```

### Check Status

```bash
curl http://localhost:9095/api/lifecycle/status | jq
```

**Response:**
```json
{
  "running": true,
  "paused": false,
  "scenario": "fault_day",
  "simulated_time": "2026-02-05T11:30:00",
  "simulated_hour": 11,
  "real_elapsed_seconds": 125.5,
  "events_count": 8,
  "active_faults": 1,
  "pending_repairs": 1,
  "recent_events": [...]
}
```

## Integration with Other Systems

### AI Optimizer
- Runs at 8:00 and 9:00 simulated time
- Generates optimization recommendations for the site
- Recommendations appear in dashboard

### Alert Service
- Fault injection creates alerts in Supabase
- Clawd notifications sent to FM team chat
- Alerts appear in dashboard bell icon

### Predictions
- Fault injection creates ML predictions
- Predictions appear in Risk Intelligence panel
- Probability and timeframe calculated from fault type

### Service Feedback
- After repair completion, service feedback is auto-submitted
- Health scores updated based on feedback
- Equipment status restored to normal

### Work Orders
- Faults create work orders automatically
- Technician assigned based on equipment type
- Work order status tracked through completion

## Creating New Demos

### Overview

You can create custom demo scenarios for different users, roles, or use cases. Each demo can have:
- **Auto-start on login** - Automatically trigger when a specific user logs in
- **Custom scenario** - Define fault timing, equipment types, and repair delays
- **Time compression** - Control demo speed (5 min, 24 min, etc.)
- **Response flags** - Backend signals frontend to auto-redirect to specific views

### Step 1: Create Demo Scenario

Scenarios are defined in `backend/app/services/lifecycle_orchestrator.py`:

```python
# In SCENARIOS dict, add new scenario:
SCENARIOS = {
    "your_demo_name": ScenarioConfig(
        name="Your Demo Name",
        description="Description of what this demo shows",
        fault_probability=1.0,  # 0.0 to 1.0 (1.0 = guaranteed)
        fault_hour=11,  # Simulated hour when fault occurs (0-23)
        fault_equipment_type="CHILLER",  # Equipment to fault (or None for random)
        auto_repair=True,  # Auto-repair after fault
        repair_delay_hours=3,  # How long before repair completes
        optimization_enabled=True,  # Run AI optimization
        clawd_notifications=True,  # Send Telegram alerts
    ),
}
```

### Step 2: Configure Auto-Start

Add auto-start logic in `backend/app/api/auth.py` in the `login` endpoint:

```python
# After successful login, check for demo users:
if email == "grant@wardew.co.za":
    try:
        orchestrator = get_lifecycle_orchestrator()
        orchestrator.reset()
        orchestrator.run_scenario(
            scenario_name="grant_hvac_dali_ai_7day",
            duration_minutes=7.0
        )

        # Return flags for frontend auto-redirect
        response["demo_auto_start"] = True
        response["demo_scenario"] = "grant_hvac_dali_ai_7day"
        response["demo_status"] = "running"
        response["demo_description"] = "HVAC + DALI + AI predictive control"
    except Exception as e:
        logger.error(f"Error auto-starting demo: {e}")
        response["demo_auto_start"] = False
        response["demo_error"] = str(e)
```

### Step 3: Configure Frontend Auto-Redirect

Update `frontend/src/App.tsx` in the `handleEmailEntrySuccess` callback:

```typescript
const handleEmailEntrySuccess = useCallback((user: AuthUser) => {
  setCurrentUser(user);

  // Auto-redirect to specific view if demo scenario starts
  if ((user as any).demo_auto_start === true) {
    console.log('Auto-starting demo:', (user as any).demo_scenario);
    toast.success(`Demo scenario started: ${(user as any).demo_scenario}`);

    // 500ms delay to allow user state to set
    setTimeout(() => {
      setCurrentView('digital-twin');  // or 'dashboard', 'optimization', etc.
    }, 500);
  }
}, []);
```

### Example: Grant's HVAC+DALI+AI Demo

Here's how Grant's 7-day demo is configured:

**Scenario Definition** (lifecycle_orchestrator.py):
```python
"grant_hvac_dali_ai_7day": ScenarioConfig(
    name="HVAC + DALI + AI (7-day)",
    description="Demonstrates predictive HVAC control with DALI lighting integration",
    fault_probability=0.0,  # No random faults - manual control
    fault_hour=None,  # Override with manual injection
    auto_repair=False,  # Manual repair demonstration
    optimization_enabled=True,  # Show AI recommendations
    clawd_notifications=True,  # Send FM team alerts
),
```

**Auto-Start Configuration** (auth.py):
```python
if email == "grant@wardew.co.za":
    orchestrator = get_lifecycle_orchestrator()
    orchestrator.reset()
    orchestrator.run_scenario(
        scenario_name="grant_hvac_dali_ai_7day",
        duration_minutes=7.0  # 7 real minutes = 24 simulated hours
    )
    response["demo_auto_start"] = True
    response["demo_scenario"] = "grant_hvac_dali_ai_7day"
    response["demo_status"] = "running"
    response["demo_description"] = "HVAC + DALI + Sentinel AI (7-day predictive control)"
```

**Frontend Redirect** (App.tsx):
```typescript
if ((user as any).demo_auto_start === true) {
  toast.success(`Demo scenario started: ${(user as any).demo_scenario}`);
  setTimeout(() => {
    setCurrentView('digital-twin');  // Show 3D visualization
  }, 500);
}
```

### Custom Demo Examples

#### Demo 1: Quick 5-Minute Chiller Failure

For a facilities manager who wants to see chiller fault workflow:

```python
"fm_chiller_fault_5min": ScenarioConfig(
    name="Chiller Failure - 5 Min",
    fault_probability=1.0,  # Guaranteed fault
    fault_hour=11,
    fault_equipment_type="CHILLER",
    auto_repair=False,  # Let FM manually trigger repair
    optimization_enabled=False,  # Keep focused on fault
),
```

**Login trigger** (auth.py):
```python
if email == "facilities-manager@bidvest.co.za":
    orchestrator.run_scenario("fm_chiller_fault_5min", duration_minutes=5.0)
    response["demo_auto_start"] = True
    response["demo_scenario"] = "fm_chiller_fault_5min"
    response["demo_view"] = "workflow"  # Go to work order dashboard
```

#### Demo 2: Multi-Site Portfolio Overview

For executives reviewing portfolio-wide optimization:

```python
"executive_portfolio_day": ScenarioConfig(
    name="Multi-Site Portfolio (24 hours)",
    fault_probability=0.05,  # Random low probability
    auto_repair=True,  # Auto-repair to show full lifecycle
    optimization_enabled=True,  # Show all AI recommendations
    clawd_notifications=True,
),
```

**Login trigger** (auth.py):
```python
if email in ["cto@bidvest.co.za", "sustainability@bidvest.co.za"]:
    orchestrator.run_scenario("executive_portfolio_day", duration_minutes=24.0)
    response["demo_auto_start"] = True
    response["demo_scenario"] = "executive_portfolio_day"
    response["demo_view"] = "sustainability"  # Show ESG/optimization impact
```

#### Demo 3: Stress Test - Multiple Faults

For testing team validating alert handling:

```python
"stress_multi_fault": ScenarioConfig(
    name="Stress Test - Multiple Faults",
    fault_probability=0.8,  # 80% chance per hour
    auto_repair=True,
    repair_delay_hours=1,  # Quick repairs
    optimization_enabled=True,
),
```

### Step 4: Test Your Demo

#### Local Testing
```bash
# Start backend
cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 9095

# Start frontend
cd frontend && npm run dev  # or npm run preview

# Test login in browser
# Navigate to http://localhost:9096
# Enter email: <your_demo_email>
# Watch auto-start and redirect
```

#### Watch Simulation Events
```bash
# Monitor in real-time
watch -n 2 'curl -s http://localhost:9095/api/lifecycle/events | jq ".events[-3:]"'

# Or check status
curl http://localhost:9095/api/lifecycle/status | jq
```

#### Check Systemd Logs
```bash
# View production logs
journalctl -u sentinel-backend -f | grep "demo\|scenario"
journalctl -u sentinel-frontend -f | grep "Demo\|redirect"
```

### Step 5: Deploy to Production

Once tested locally:

1. **Update auth.py** with your demo email/scenario logic
2. **Update lifecycle_orchestrator.py** with new scenario definition
3. **Test on staging** via `bms.aimthelaw.co.za`
4. **Systemd auto-restart** handles deployment:
   ```bash
   sudo systemctl restart sentinel-backend
   # Changes picked up on next login
   ```

### Best Practices

✅ **Do:**
- Use realistic scenario names (`grant_hvac_dali_7day` not `demo123`)
- Test locally first before production
- Document your scenario in a comment
- Use specific equipment types for focused demos
- Include scenario description for logging

❌ **Don't:**
- Hard-code user emails in multiple places (use environment variables for production)
- Set fault_probability > 1.0 or < 0.0
- Set repair_delay_hours < 0.5 (unrealistic)
- Auto-start multiple scenarios for same user (confusing)
- Change demo scenarios during active user session (restart needed)

### Testing Checklist

- [ ] Scenario runs without errors
- [ ] Auto-start triggered on login with correct email
- [ ] Frontend receives demo_auto_start flag
- [ ] Auto-redirect to correct view happens (500ms delay)
- [ ] Toast notification shows scenario name
- [ ] Simulation progresses through hours correctly
- [ ] Events visible in `/api/lifecycle/events`
- [ ] Faults generated at expected hour
- [ ] AI optimization runs if enabled
- [ ] Alerts/notifications sent if enabled
- [ ] Dashboard updates in real-time

## Files

| File | Purpose |
|------|---------|
| `services/lifecycle_orchestrator.py` | Core orchestrator with time engine, scenario definitions |
| `api/lifecycle_simulation.py` | REST API endpoints for simulation control |
| `api/auth.py` | Login logic with demo auto-start configuration |
| `frontend/src/App.tsx` | Frontend auto-redirect logic in handleEmailEntrySuccess |

## Related Documentation

- [Demo Simulation Control](./demo-simulation-control.md) - Simple trigger/reset endpoints
- [Asset Lifecycle State Machine](../05-integrations/asset-lifecycle-state-machine.md) - State definitions
- [Service Feedback System](./service-feedback-system.md) - Technician feedback
- [Health Scoring System](./health-scoring-system.md) - Health calculation
