# Grant Simulation Test Guide (DEMO_MODE)

## Goal
Verify that the Grant simulation produces **correct energy numbers** (positive, not inverted) when DEMO_MODE is enabled. This separates two problems:
1. Is the simulation logic correct? ← We're testing this
2. Is the auth middleware blocking the POST? ← We'll debug separately

## Prerequisites

**Terminal 1 (Backend)** - Start with DEMO_MODE enabled:
```bash
cd backend
source venv/bin/activate
DEMO_MODE=true python -m uvicorn app.main:app --reload --port 9095
```

**Terminal 2 (Test)** - Run the test script:
```bash
chmod +x TEST_GRANT_SIMULATION.sh
./TEST_GRANT_SIMULATION.sh
```

## What the Test Does

| Step | What | Expected | Issue if Fails |
|------|------|----------|---|
| 1 | Health check | 200 OK | Backend not running |
| 2 | Get initial energy data | 3 scenarios (baseline, dali, sentinel) | Energy endpoint broken |
| 3 | Check module status | See active modules | Module registry broken |
| 4 | Start Grant simulation | Returns task_id | Simulation POST fails (might hang) |
| 5 | Monitor progress | 0% → 100% | Simulation hangs or doesn't run |
| 6 | Get final energy data | Updated numbers | Data didn't refresh |
| 7 | Compare before/after | Numbers should change | Simulation didn't actually run |
| 8 | Check for inverted numbers | All positive | Calculation logic inverted |
| 9 | Lifecycle status | Shows simulation complete | Status endpoint broken |

## Expected Results if Simulation is Working Correctly

### Step 2: Initial Energy Comparison
```json
{
  "baseline": {
    "actual": { "total_kwh": 1000, "hvac_kwh": 600, ... },
    "dali": { "total_kwh": 950, ... },
    "sentinel": { "total_kwh": 700, ... }
  }
}
```
- **All positive numbers** ✓
- **sentinel < dali < actual** (descending savings) ✓
- **No negative values** ✓

### Step 4: Start Simulation
```json
{
  "task_id": "abc123...",
  "status": "queued",
  "scenario": "grant_hvac_dali_ai_annual"
}
```
- **Returns immediately** (doesn't hang) ✓
- **Has task_id** ✓

### Step 5: Monitor Progress
```
[0:00] Status: queued      Progress:   0%
[0:05] Status: running     Progress:  15%
[0:10] Status: running     Progress:  32%
[0:15] Status: running     Progress:  52%
[0:20] Status: running     Progress:  78%
[0:25] Status: complete    Progress: 100%
```
- **Status progresses: queued → running → complete** ✓
- **Takes ~4 minutes for 365-day simulation** ✓
- **Progress increases smoothly** ✓

### Step 6: Final Energy Data
```json
{
  "baseline": {
    "actual": { "total_kwh": 1000, "hvac_kwh": 600, ... },
    "dali": { "total_kwh": 950, ... },
    "sentinel": { "total_kwh": 700, ... }
  }
}
```
- **All positive numbers** ✓
- **Same structure as initial** ✓

### Step 8: Energy Numbers Check
```
✓ HVAC energy is positive: 600.00 kWh
✓ Total energy is positive: 1000.00 kWh
```
- **No negative signs** ✓
- **Not inverted** ✓

## Troubleshooting

### Issue: "Backend NOT running"
**Solution:** Start backend in Terminal 1 with DEMO_MODE:
```bash
cd backend && source venv/bin/activate
DEMO_MODE=true python -m uvicorn app.main:app --reload --port 9095
```

### Issue: TEST 2 returns 404 (Energy endpoint not found)
**Cause:** Router not registered
**Solution:** Verify `backend/app/api/registrars/building.py` has:
```python
from app.api import energy
app.include_router(energy.router, prefix="/api", tags=["energy"])
```

### Issue: TEST 4 hangs (POST never returns)
**Cause:** Auth middleware blocking without DEMO_MODE
**Expected in production:** This is why we're testing with DEMO_MODE first
**Action:** Verify DEMO_MODE=true is set before starting backend

### Issue: TEST 5 shows 0% progress forever
**Cause:** Simulation never started or background job stuck
**Action:** Check backend logs for errors in `lifecycle_orchestrator`

### Issue: TEST 8 shows NEGATIVE numbers
**Cause:** Simulation logic has inversion bug
**Action:** Check `energy_rules_engine.py` or `simulator_service.py` for sign errors

### Issue: Numbers unchanged between initial and final
**Cause:** Simulation ran but data not persisted
**Action:** Check if background job wrote to database/cache

## After This Test

### If All Tests Pass ✓
Great news! The simulation logic is correct. Numbers are positive and reasonable.
**Next step:** Debug why auth middleware blocks POST in production (without DEMO_MODE).

### If Tests Fail ✗
Need to fix simulation logic or data generation.
Check:
1. `backend/app/services/simulator_service.py` - Data generation
2. `backend/app/services/energy_rules_engine.py` - Energy calculation
3. `backend/app/services/lifecycle_orchestrator.py` - Simulation orchestration

## Quick Reference: curl Commands

```bash
# Health check
curl http://localhost:9095/health

# Get energy comparison
curl "http://localhost:9095/api/energy/comparison?site_id=site-002&days=30"

# Check modules
curl "http://localhost:9095/api/modules/status/site-002"

# Start simulation
curl -X POST http://localhost:9095/api/lifecycle/start \
  -H "Content-Type: application/json" \
  -d '{"scenario": "grant_hvac_dali_ai_annual"}'

# Check simulation status
curl "http://localhost:9095/api/lifecycle/status/site-002"
```

## Test Duration

- **TEST 1-3:** ~5 seconds
- **TEST 4:** ~1 second
- **TEST 5:** ~4 minutes (monitoring simulation)
- **TEST 6-9:** ~10 seconds

**Total:** ~4-5 minutes

---

**Debug Mode:** If you need more detailed output:
```bash
DEMO_MODE=true python -m uvicorn app.main:app --reload --port 9095 --log-level debug
```

Check logs for:
- `Simulation queued`
- `Simulation running`
- `Hour X/8760`
- `Simulation complete`
