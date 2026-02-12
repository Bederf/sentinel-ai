# Normal Day Simulation - Pure AI Optimization

## Objective

Run a 24-hour building simulation with:
- ✅ Normal operations (no faults, no emergencies)
- ✅ AI optimization enabled (generating device recommendations)
- ✅ Auto-fix enabled (automatically applying recommendations)
- ✅ Watch what the AI does to optimize building performance

---

## The Scenario: "normal_day"

```json
{
  "scenario": "normal_day",
  "duration_minutes": 12.0,
  "start_hour": 6
}
```

**What happens:**
- Typical day: 6am building wake → peak load → 6pm close
- Only 10% chance of minor fault (usually none)
- **NO critical alerts**
- **NO emergency repairs**
- **FOCUS: AI recommendations and optimizations**

**Duration:** 12 real minutes (24 hours simulated)

---

## Setup: 4 Monitoring Terminals

### Terminal 1: Backend Logs
```bash
tail -f /tmp/backend.log | grep -i "optimization\|recommendation\|setpoint\|mode"
```
**Watch for:** AI decisions, device changes, optimization actions

### Terminal 2: Lifecycle Events
```bash
watch -n 3 'curl -s http://localhost:9095/api/lifecycle/events | jq ".events[-5:]"'
```
**Watch for:** AI_OPTIMIZATION events at hours 8 and 9

### Terminal 3: AI Recommendations
```bash
watch -n 3 'curl -s http://localhost:9095/api/recommendations/site/S002 | jq ".recommendations[0:3]"'
```
**Watch for:** Equipment control recommendations, confidence scores, expected impact

### Terminal 4: Dashboard
```
Open: http://localhost:9096
Navigate: Dashboard → Risk Intelligence panel
```
**Watch for:**
- Green status for all equipment (no faults)
- "AI Recommendations" section shows suggested actions
- Equipment health scores stable

---

## Execution

### Step 1: Start Simulation
```bash
curl -X POST http://localhost:9095/api/lifecycle/start \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "normal_day",
    "duration_minutes": 12.0,
    "start_hour": 6
  }' | jq '.'
```

**Expected response:**
```json
{
  "success": true,
  "scenario": "normal_day",
  "status": "running",
  "simulated_hour": 6,
  "real_elapsed_seconds": 0.0,
  "message": "Lifecycle simulation started - normal day scenario"
}
```

### Step 2: Monitor Hour-by-Hour

**Minute 0-1 (Hour 6:00)** - Building Wake
- Systems start
- Occupancy: 0%
- HVAC: standby mode
- Lighting: minimal

**Minute 1-2 (Hour 7:00)** - Occupancy Rise
- People arriving
- Occupancy: 10-20%
- Heating/cooling begins
- Lighting increases

**Minute 2-3 (Hour 8:00)** - **AI OPTIMIZATION RUN #1** 🤖
- AI analyzes building state
- Makes recommendations:
  - HVAC setpoint adjustments
  - Lighting level optimization
  - Power management changes
- **Check Terminal 3:** New recommendations appear

**Minute 2.5-3.5 (Hour 8:30-9:00)** - **AUTO-FIX EXECUTION** ⚡
- AI recommendations being applied
- Device commands sent:
  - VAV setpoint → 22°C (from 20°C)
  - Chiller mode → efficiency (from comfort)
  - Lighting dimmed → 80% (from 100%)
  - UPS mode → eco (from full power)

**Minute 3-4 (Hour 9:00)** - **AI OPTIMIZATION RUN #2** 🤖
- Second optimization pass
- Fine-tuning recommendations
- Expected impact calculated

**Minute 4-5 (Hour 10:00-12:00)** - Peak Load
- Occupancy: 90%
- All systems running optimally
- Recommendations: Fine-tuning only
- No issues detected

**Minute 5-8 (Hour 13:00-18:00)** - Stable Operations
- Occupancy decreasing
- AI reducing energy usage
- Lights dimming
- HVAC backing off

**Minute 8-12 (Hour 18:00-22:00)** - Shutdown
- Building closing
- Systems powering down
- Final optimization pass
- Night mode engaged

### Step 3: Check Results

**After simulation completes, run these queries:**

#### What recommendations were made?
```bash
curl -s http://localhost:9095/api/recommendations/site/S002?status=approved | jq '.recommendations | length'
```

#### What was the energy impact?
```bash
curl -s http://localhost:9095/api/optimization/impact/site/S002 | jq '{
  energy_savings_kwh: .energy_savings,
  cost_savings_usd: .cost_savings,
  comfort_score: .comfort_score
}'
```

#### Equipment status after optimization?
```bash
curl -s http://localhost:9095/api/equipment?site_id=S002 | jq '.equipment[] | {
  name,
  health_score,
  status,
  current_mode: .operating_data.mode
}' | head -20
```

#### All lifecycle events that occurred?
```bash
curl -s http://localhost:9095/api/lifecycle/events | jq '{
  total_events: (.events | length),
  event_types: (.events | map(.event_type) | unique),
  optimization_events: (.events | map(select(.event_type == "ai_optimization")) | length)
}'
```

---

## What to Expect

### AI Recommendation Types

**HVAC Optimization:**
- Setpoint: 20°C → 22°C (save cooling cost)
- Mode: Comfort → Efficiency
- Impact: 10-15% energy savings
- Equipment: S002-CHILLER-B1-002, S002-FCU-201, S002-PUMP-B1-CW1

**Lighting Optimization:**
- Level: 100% → 80% (during peak daylight)
- Scene: Performance → Energy saving
- Impact: 5-10% energy savings
- Equipment: S002-DALI-201

**Power Management:**
- UPS: Full power → Eco mode (off-peak)
- Generator: Standby (unless load shedding)
- Inverters: Maximize solar usage
- Impact: 15-20% energy savings
- Equipment: S002-UPS-B1-001, S002-GEN-B1-001, S002-INV-R-*

**Multi-System Coordination:**
- Chiller reduced → Temperature rises slightly → Lighting reduced → Comfort maintained at lower energy
- Expected comfort score: 85-90 out of 100 (vs 100 before optimization)
- Expected energy savings: 20-30% vs baseline

---

## Expected Outputs

### Terminal 1 (Logs)
```
INFO: AI_OPTIMIZATION started at simulated hour 8
INFO: Analyzing HVAC system - 5 devices
INFO: Generating recommendation: S002-CHILLER-B1-002 setpoint 20°C → 22°C
INFO: Confidence: 0.92 (high confidence in savings)
INFO: Recommendation executed via autofix
INFO: S002-CHILLER-B1-002 setpoint changed to 22°C
INFO: Equipment health maintained at 92%
```

### Terminal 2 (Events)
```
{
  "event_type": "ai_optimization",
  "simulated_hour": 8,
  "description": "AI analyzed 5 HVAC devices, 3 lighting zones, 4 power systems",
  "details": {
    "recommendations_made": 12,
    "recommendations_executed": 12,
    "expected_energy_savings_kwh": 45.2,
    "expected_cost_savings_usd": 22.50
  }
}
```

### Terminal 3 (Recommendations)
```json
{
  "recommendations": [
    {
      "equipment_id": "S002-CHILLER-B1-002",
      "control_point": "setpoint",
      "current_value": 20.0,
      "recommended_value": 22.0,
      "reasoning": "Peak demand pricing window - reduce cooling to eco mode",
      "confidence": 0.92,
      "expected_impact": {
        "energy_saving_kwh": 12.3,
        "cost_saving_usd": 5.67,
        "comfort_impact": "minimal - within occupant satisfaction threshold"
      },
      "status": "executed",
      "executed_at": "2026-02-12T08:15:30Z"
    },
    {
      "equipment_id": "S002-DALI-201",
      "control_point": "brightness",
      "current_value": 100,
      "recommended_value": 80,
      "reasoning": "Daylight available, reduce artificial lighting to 80%",
      "confidence": 0.88,
      "expected_impact": {
        "energy_saving_kwh": 8.5,
        "cost_saving_usd": 3.20
      },
      "status": "executed"
    }
  ]
}
```

### Terminal 4 (Dashboard)
- All equipment cards: **GREEN** (no issues)
- No red alerts or warnings
- Health scores: 88-96% (stable)
- "AI Recommendations" panel shows 12 suggestions applied
- Energy impact widget: "↓ 25% energy usage vs baseline"
- Cost savings: "$45.80 estimated savings today"

---

## Success Criteria

### ✅ Normal Day Simulation Success

- [x] Simulation runs for 12 real minutes (24 simulated hours)
- [x] No faults injected (buildings runs smoothly)
- [x] No critical alerts (all green)
- [x] AI generates recommendations at hours 8 and 9
- [x] Recommendations include: HVAC, Lighting, Power systems
- [x] Auto-fix executes all recommendations
- [x] Device values change: setpoints, brightness, modes
- [x] Equipment health maintained throughout
- [x] Energy/cost savings calculated and displayed
- [x] Dashboard shows pure optimization (no emergency handling)

---

## If Nothing Happens (Troubleshooting)

### No Recommendations Appearing

**Check:**
```bash
# Are recommendations being generated?
curl -s http://localhost:9095/api/recommendations/site/S002 | jq '.recommendations | length'

# Is optimization enabled?
curl -s http://localhost:9095/api/lifecycle/status | jq '.scenario.optimization_enabled'
```

### Devices Not Changing

**Check:**
```bash
# Are device writes being executed?
tail -100 /tmp/backend.log | grep "setpoint\|brightness\|mode"

# Check recommendation status
curl -s http://localhost:9095/api/recommendations/site/S002 | jq '.recommendations[0] | {status, executed_at}'
```

### AI Not Running

**Check:**
```bash
# Verify orchestrator sees the optimization_enabled flag
curl -s http://localhost:9095/api/lifecycle/status | jq '.'

# Check for optimization events
curl -s http://localhost:9095/api/lifecycle/events | jq '.events[] | select(.event_type == "ai_optimization")'
```

---

## Key Insights to Watch

1. **AI Strategy:** What does it prioritize?
   - Energy savings first?
   - Comfort first?
   - Balanced?

2. **Recommendation Confidence:** High or low?
   - 0.9+ = High confidence (usually applied)
   - 0.7-0.9 = Medium confidence
   - <0.7 = Low confidence (skipped)

3. **Real-World Impact:**
   - Energy savings realistic?
   - Comfort maintained?
   - Any system conflicts?

4. **Device Responsiveness:**
   - Do setpoint changes stick?
   - Are modes actually changing?
   - Any device errors?

---

## Files & Resources

| Item | Location |
|---|---|
| This Guide | `/RUN_NORMAL_DAY_SIMULATION.md` |
| Lifecycle Docs | `/docs/04-features/lifecycle-simulation.md` |
| AI Optimizer | `/backend/app/services/ai_optimizer.py` |
| Orchestrator | `/backend/app/services/lifecycle_orchestrator.py` |
