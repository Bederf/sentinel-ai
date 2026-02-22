# Multi-User Module Access Testing Guide

**Status:** DEMO_MODE disabled | Real authentication enabled | Phase 086-088 module gating active

## Test Users

### User 1: Bederf (Solar Engineer)
```
Email: bederf@protonmail.com
Password: (configured in auth system)
Site: site-002 (Bederf building)

Granted Modules:
✅ control    - Device control & approval workflows
✅ solar      - Solar generation, BESS dispatch, grid management

Locked Modules (will show upgrade prompts):
🔒 lighting   - DALI lighting automation
🔒 maintenance - Work order management
🔒 sustainability - Carbon tracking
```

**What Bederf Sees:**
- HVAC controls (base module, free)
- Energy monitoring (base module, free)
- **Solar dashboard** with:
  - PV generation graphs
  - BESS state of charge
  - Grid pricing & dispatch decisions
  - Energy arbitrage opportunities (R/month savings shown)
- Device control toggles and setpoints
- Locked features show: "R300+/month savings - Request Activation"

---

### User 2: Grant (Lighting Technician)
```
Email: grant@grantdemo.co.za
Password: (configured in auth system)
Site: site-002 (Grant building - same as demo simulation)

Granted Modules:
✅ control   - Device control & approval workflows
✅ lighting  - DALI lighting automation

Locked Modules (will show upgrade prompts):
🔒 solar          - Solar controls hidden
🔒 maintenance    - Work order management
🔒 sustainability - Carbon tracking
```

**What Grant Sees:**
- HVAC controls (base module, free)
- Energy monitoring (base module, free)
- **Lighting dashboard** with:
  - DALI dimming controls
  - Occupancy-based automation
  - Daylight harvesting rules
  - Energy savings metrics (2-4% typical)
- Device control toggles and setpoints
- Solar panel is hidden/locked
- Locked features show: "R200+/month savings - Request Activation"

---

## 2-Layer Access Control Verification

### Layer 1: Site-Level Module Activation
Both users access same site (site-002) but:
- Site has CONTROL, SOLAR, LIGHTING modules installed
- Backend allows these modules to run
- Individual users only see modules they're granted

### Layer 2: User-Level Grants
```sql
-- Bederf's grants
SELECT * FROM user_module_access
WHERE user_email = 'bederf@protonmail.com';
-- Result: control, solar

-- Grant's grants
SELECT * FROM user_module_access
WHERE user_email = 'grant@grantdemo.co.za';
-- Result: control, lighting
```

---

## Testing Scenarios

### Scenario 1: Access Control on Dashboard
1. Log in as **Bederf**
   - ✅ Solar controls visible
   - 🔒 Lighting controls hidden (upgrade prompt)

2. Log in as **Grant**
   - 🔒 Solar controls hidden (upgrade prompt)
   - ✅ Lighting controls visible

### Scenario 2: Module Dependencies
- If CONTROL module deactivated at site level:
  - SOLAR module auto-disabled (cascade)
  - LIGHTING module auto-disabled (cascade)
  - Both users lose access
  - Explanation shown: "Control module required for device automation"

### Scenario 3: Upgrade Request Workflow
1. User clicks "Request Activation" on locked feature
2. Request submitted to `access_requests` table
3. Admin reviews and approves
4. User gets access without re-login
5. Feature immediately becomes available

### Scenario 4: Grant Simulation Results
- Both users see Grant demo (365-day annual simulation)
- Same energy numbers (baseline → DALI → SENTINEL AI)
- But only Bederf sees solar arbitrage optimization
- Only Grant sees DALI lighting optimization

---

## Expected API Behavior

### Bederf calling `/api/solar/generation`
```
Status: 200 OK
Data: Solar generation metrics, BESS state
```

### Bederf calling `/api/lighting/zones`
```
Status: 403 Forbidden
Message: "User not granted module: lighting"
```

### Grant calling `/api/solar/generation`
```
Status: 403 Forbidden
Message: "User not granted module: solar"
```

### Grant calling `/api/lighting/zones`
```
Status: 200 OK
Data: Lighting zone controls, occupancy data
```

---

## Frontend Module Gating Examples

### ChillerControlPanel (when CONTROL locked)
```
[TOGGLE] Chiller On/Off
         ↓
         [LOCKED OVERLAY]
         "Control Module Required"
         "R200+/month energy savings"
         [Request Activation] [Learn More]
```

### SolarDashboard (when SOLAR locked)
```
[HIDDEN] Solar controls don't render at all
         BUT in settings page shows:
         "Solar Module Not Active"
         "R300+/month savings potential"
         [Request Activation]
```

---

## How to Test

### Via Web UI (http://localhost:9096)
```
1. Log in as bederf@protonmail.com
   - Should see solar controls
   - Should see locked lighting with upgrade prompt

2. Log out

3. Log in as grant@grantdemo.co.za
   - Should see lighting controls
   - Should see locked solar with upgrade prompt

4. Try requesting activation on locked features
   - Check access_requests table
```

### Via API
```bash
# As Bederf (needs JWT token)
curl -H "Authorization: Bearer $JWT_TOKEN" \
  http://localhost:9095/api/solar/generation/site-002

# As Grant (needs JWT token)
curl -H "Authorization: Bearer $JWT_TOKEN" \
  http://localhost:9095/api/lighting/zones/site-002
```

---

## Architecture Summary

**Backend Filtering:**
- `has_module_access()` checks both layers before returning data
- 17 gated routers enforce access control at endpoint level
- Returns 403 Forbidden if access denied

**Frontend Gating:**
- `useModuleAccess()` hook checks module status
- `LockedFeatureOverlay` component wraps locked features
- Shows upgrade prompts with savings data

**Database Layer:**
- `solar_annual_tasks` table stores simulation results
- Both users see same task (site-level data)
- But optimize differently based on granted modules
- Frontend computes different "potential savings" per user

---

## Known Limitations

- Auth system uses JWT tokens (configure in auth service)
- Module requests require admin approval (no auto-approval)
- Cascade deactivation shows no warning UI (silent backend)
- Users can't see which modules other users have

---

**Test Status:** Ready for user testing
**Last Updated:** 2026-02-16
