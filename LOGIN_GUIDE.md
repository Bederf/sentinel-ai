# Multi-User Access Testing - Login Guide

**Status:** DEMO_MODE disabled | Real authentication enabled | Module gating active

## System Ready ✅

- Backend running with JWT authentication
- Frontend running with module access control
- Two test users with different module grants
- All Phase 086-088 gating rules active

---

## How to Log In

### Via Web UI

1. **Open** http://localhost:9096

2. **You'll see login screen** (no password field, email-based auth)

3. **Enter email:**
   - `bederf@protonmail.com` - Solar Engineer (has SOLAR + CONTROL)
   - `grant@wardew.co.za` - Lighting Technician (has LIGHTING + CONTROL)

4. **Click "Login"** - You'll be automatically authenticated

---

## What Each User Sees

### Bederf (bederf@protonmail.com)
**Modules Granted:**
- ✅ control
- ✅ solar

**Dashboard Will Show:**
- HVAC controls (base module, free)
- Energy monitoring (base module, free)
- **Solar dashboard** with:
  - PV generation graphs
  - BESS state of charge
  - Energy arbitrage opportunities
  - Shows R300+/month savings potential
- Device control toggles
- **Locked:** Lighting controls (shows upgrade prompt "R200+/month savings")
- **Locked:** Work orders (shows upgrade prompt)

---

### Grant (grant@wardew.co.za)
**Modules Granted:**
- ✅ control
- ✅ lighting

**Dashboard Will Show:**
- HVAC controls (base module, free)
- Energy monitoring (base module, free)
- **Lighting dashboard** with:
  - DALI dimming controls
  - Occupancy-based automation
  - Daylight harvesting configuration
  - Shows R200+/month savings potential
- Device control toggles
- **Locked:** Solar controls (shows upgrade prompt "R300+/month savings")
- **Locked:** Work orders (shows upgrade prompt)

---

## What's Different Between Users?

| Feature | Bederf | Grant |
|---------|--------|-------|
| Device Controls | ✅ | ✅ |
| HVAC Panel | ✅ | ✅ |
| **Solar Dashboard** | ✅ | 🔒 (locked) |
| **Lighting Dashboard** | 🔒 (locked) | ✅ |
| Energy Comparison | ✅ | ✅ |
| Work Orders | 🔒 (locked) | 🔒 (locked) |
| Lifecycle Simulation | ✅ | ✅ |

---

## Testing Module Gating

### Try This as Bederf:
1. Click on locked "Lighting" feature
2. See blue overlay: "Lighting Module Not Activated"
3. See savings estimate: "R200+/month energy savings, 2-4% reduction"
4. Try "Request Activation" button (optional)

### Try This as Grant:
1. Look for Solar section
2. See it's locked/hidden (no prompt, just not visible)
3. Check settings to see locked modules
4. See "Solar Module" with "R300+/month savings potential"

---

## Backend API Testing (Advanced)

If you want to test API endpoints directly:

### Get JWT Token
```bash
# Email-based login (no password!)
curl -X POST "http://localhost:9095/api/auth/login?email=bederf@protonmail.com"

# Returns: {"access_token": "eyJhbGci...", "token_type": "bearer", ...}
```

### Test Module Access (Bederf can access SOLAR)
```bash
BEDERF_TOKEN=$(curl -s -X POST "http://localhost:9095/api/auth/login?email=bederf@protonmail.com" | jq -r .access_token)

curl -H "Authorization: Bearer $BEDERF_TOKEN" \
  http://localhost:9095/api/solar/generation/site-002
# Returns: 200 OK + solar data
```

### Test Module Access (Grant CANNOT access SOLAR)
```bash
GRANT_TOKEN=$(curl -s -X POST "http://localhost:9095/api/auth/login?email=grant@wardew.co.za" | jq -r .access_token)

curl -H "Authorization: Bearer $GRANT_TOKEN" \
  http://localhost:9095/api/solar/generation/site-002
# Returns: 403 Forbidden "User not granted module: solar"
```

---

## Key Features Being Tested

### 1. **Two-Layer Access Control**
- **Layer 1 (Site):** Which modules are installed
  - Both users see: control, solar, lighting active at site-002
- **Layer 2 (User):** Which modules user is granted
  - Bederf granted: control, solar
  - Grant granted: control, lighting

### 2. **Module Gating UI**
- Locked features show upgrade prompts with:
  - Feature name
  - Monthly savings estimate
  - Energy reduction percentage
  - "Request Activation" button

### 3. **Cascading Module Dependencies**
- CONTROL module is required for:
  - SOLAR (for dispatch control)
  - LIGHTING (for automation)
- Both Bederf and Grant have CONTROL → can use their respective features

### 4. **Role-Based Behavior**
- Both users are AUDITOR role
- They don't have approval authority
- They can request module access but can't approve
- Admin role would see approval dashboard

---

## Expected Experience

**When Bederf logs in:**
```
Dashboard
├── HVAC Controls       ✅ (enabled, base module)
├── Energy Monitoring   ✅ (enabled, base module)
├── Solar Dashboard     ✅ (enabled, has grant)
├── Lighting Controls   🔒 (locked, no grant)
└── Work Orders         🔒 (locked, not granted)
```

**When Grant logs in:**
```
Dashboard
├── HVAC Controls       ✅ (enabled, base module)
├── Energy Monitoring   ✅ (enabled, base module)
├── Lighting Dashboard  ✅ (enabled, has grant)
├── Solar Dashboard     🔒 (locked, no grant)
└── Work Orders         🔒 (locked, not granted)
```

---

## Grant Demo Simulation

Both users can run the Grant 365-day simulation:
- Same building (site-002)
- Same energy comparison results
- But DIFFERENT optimization recommendations based on modules:
  - **Bederf sees:** SOLAR arbitrage optimization (BESS charging/discharging)
  - **Grant sees:** DALI lighting optimization (occupancy-based dimming)
  - **Both see:** HVAC optimization (runs for everyone)

---

## Troubleshooting

**"Authentication required" error?**
- Make sure you're logged in (check browser console for token)
- Token might be expired (valid for 8 hours)
- Try logging in again

**"User not granted module" error?**
- This is correct behavior for gating!
- Try logging in as the other user to see the feature
- Or request module activation

**Feature showing but locked?**
- Frontend properly implemented gating overlay
- Click "Request Activation" to submit request
- Admin would approve in future UI

**Don't see the other user's differences?**
- Log out completely (not just navigate away)
- Clear browser cache/cookies
- Open new incognito window
- Then log in as different user

---

## Architecture Verification

This experience verifies Phase 086-088 implementation:
- ✅ **Site-level module activation** working
- ✅ **User-level module grants** working
- ✅ **Base modules** free for all users
- ✅ **Paid modules** require grants
- ✅ **Admin bypass** (test with admin@sentinel.bms if needed)
- ✅ **Frontend gating** showing locked features
- ✅ **Backend endpoint gating** returning 403 for unauthorized access
- ✅ **Module dependencies** (CONTROL required for SOLAR/LIGHTING)

---

## Next Steps

1. **Log in as both users** - see the difference
2. **Try accessing locked features** - see the gating UI
3. **Run Grant simulation** - see same results, different recommendations
4. **Check browser console** - see module access logs
5. **Test API endpoints** - verify 403 errors for denied access
6. **Request module activation** - see access request flow (admin approval needed)

---

**Ready to test?** Open http://localhost:9096 and log in!
