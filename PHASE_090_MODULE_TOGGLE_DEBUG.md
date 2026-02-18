# Phase 090 - Module Toggle Debugging Guide

**Status**: Auth fix applied (commit a48fb87), but toggles still not working  
**Last Updated**: 2026-02-16

## Problem Statement

Users report that module toggles in Settings page show "offline icon" and don't work, even after lowering auth level from ADMIN to OPERATOR (commit a48fb87).

```
User Report: "when i want to toggle a module the offline icon comes on and the toggles dont work"
Expected: Toggling modules on/off should work
Actual: Toggles appear to fail silently or show offline status
```

## Fix Applied (Commit a48fb87)

Changed authentication level on module toggle endpoints from ADMIN to OPERATOR:

**File**: `backend/app/api/modules.py`
- **Line 178**: POST `/api/modules/activate` - changed to `AuthLevel.OPERATOR`
- **Line 208**: POST `/api/modules/site/{site_id}/deactivate/{module_type}` - changed to `AuthLevel.OPERATOR`

### Why This Should Work

1. **Demo Mode**: In DEMO_MODE (active on localhost/127.0.0.1), all demo users get `SentinelRole.OPERATOR` automatically
   - Line 680 in `backend/app/middleware/auth_middleware.py`: `role=SentinelRole.OPERATOR`

2. **Production Auth**: Non-demo users need valid JWT tokens with OPERATOR or higher role

3. **No Additional Checks**: Module toggle endpoints don't check entitlements or permissions beyond auth level

## Possible Root Causes (Priority Order)

### 1. **Production Backend Not Running New Code** (HIGHEST PROBABILITY)

If production backend hasn't been restarted after deploying commit a48fb87, it's still running old code.

**Check**:
```bash
# On production server
ps aux | grep "uvicorn.*modules"
# Or check service status
systemctl status sentinel-backend

# Check if running code includes OPERATOR in modules.py
curl https://bms.aimthelaw.co.za/api/health
```

**Fix**:
```bash
# Restart backend service
systemctl restart sentinel-backend

# Verify it's running the new code by checking if auth works
# Make a test request and check response headers
```

### 2. **Module Dependency Constraints** (HIGH PROBABILITY)

Some modules require other modules to be active:
- **SOLAR** requires **CONTROL** to be active first
- **LIGHTING** requires **CONTROL** to be active first

If user tries to activate these without CONTROL active, activation fails with:
```
403 Forbidden: "solar module requires control module to be active first"
```

**Check**:
```bash
# In Settings, try activating "Building Controls" (CONTROL module) first
# Then try "Solar & BESS" (SOLAR module)
# Or check browser console for error messages
```

**Frontend Error Handling**:
If error is thrown from `deactivateModule()` or `activateModule()` in ModuleContext.tsx, it calls `onError?.(message)` - check if error toast is displayed.

### 3. **Site Not Initialized** (MEDIUM PROBABILITY)

If site doesn't have any module config yet, `deactivate_module()` returns `False` because:
- Line 286 in `module_registry_service.py`: `if not config: return False`
- This triggers 404: "Module not found or not active"

**Fix**:
Change deactivate to be idempotent - return True even if module not found:
```python
def deactivate_module(self, site_id: str, module_type: ModuleType) -> bool:
    """Deactivate a module for a site (idempotent)."""
    if module_type in NON_DEACTIVATABLE_MODULES:
        raise ValueError(...)

    config = self._site_configs.get(site_id)
    if not config:
        return True  # Changed: return True if not found (idempotent)
    ...
```

### 4. **CORS or Network Issues** (MEDIUM PROBABILITY)

Frontend making request to `https://bms.aimthelaw.co.za/api/modules/activate`

**Check Caddy Configuration**: Verify `/api/*` is correctly routed to backend:
```
# In Caddyfile
reverse_proxy /api/* localhost:9095 {
    header_up Origin {http.request.header.Origin}
}
```

**Browser Network Debug**:
1. Open DevTools (F12)
2. Go to Network tab
3. Try to toggle a module
4. Check the request to `/api/modules/activate`:
   - Is it sent? (Method, URL, headers)
   - What response code? (200, 401, 403, 404, 500, etc.)
   - What error message?

### 5. **Frontend State Cache** (LOW PROBABILITY)

Frontend might be caching active modules list incorrectly.

**Check**:
- Refresh page, try toggle again
- Check localStorage: `localStorage.getItem("sentinel_module_recommendations_*")`

## Diagnostic Steps

Run these in order to identify the issue:

### Step 1: Verify Backend Code Has Fix

```bash
# SSH to production server
ssh user@bms.aimthelaw.co.za

# Check if running code has OPERATOR
grep "AuthLevel.OPERATOR" /path/to/app/api/modules.py

# If not found, backend is running old code - restart it
```

### Step 2: Check Backend Service Status

```bash
# Check service status
systemctl status sentinel-backend

# If not active, restart
systemctl restart sentinel-backend

# Watch logs
tail -f /var/log/sentinel-backend.log | grep -i "module\|auth"
```

### Step 3: Test Endpoint Directly with curl

```bash
# Test activate endpoint (will fail without valid token, but check error)
curl -v -X POST https://bms.aimthelaw.co.za/api/modules/activate \
  -H "Content-Type: application/json" \
  -d '{"site_id":"site-002","site_name":"Sandton","module_type":"assets"}'

# Expected: 401 Unauthorized (no token) or success if DEMO_MODE
# If 403, check the detail message - might be dependency or permission
# If 404, site config doesn't exist
# If 500, there's a server error
```

### Step 4: Debug in Browser

1. Open https://bms.aimthelaw.co.za in browser
2. Open DevTools (F12)
3. Go to Network tab
4. Try to toggle a module in Settings
5. Look for POST request to `/api/modules/activate` or `/api/modules/site/*/deactivate/*`
6. Check:
   - Response Status Code
   - Response Body (error message)
   - Request Headers (Authorization token)
   - CORS headers in Response

### Step 5: Check Module Dependencies

In Settings page, try this sequence:
1. Find "Building Controls" (CONTROL module) toggle
2. Try to activate it (should work if auth is OK)
3. Then try "Solar & BESS" (SOLAR module) - should now work
4. Or "Occupancy" (LIGHTING module) - should now work

If step 1 fails, auth is broken. If step 2 fails, dependency check is working correctly.

## Required Verification Checklist

Before declaring issue resolved:

- [ ] Backend service is running and has commit a48fb87
- [ ] Module activation works (try "Building Controls" first, then "Asset Workflow")
- [ ] Module deactivation works (toggle activated modules off)
- [ ] Dependency checking works (try activating SOLAR without CONTROL - should fail with clear message)
- [ ] Error messages are displayed in UI (check Settings page for toast notifications)
- [ ] Refresh page and verify toggle states persist

## Recommended Fix Priority

If debugging confirms the issue:

1. **Immediate**: Restart production backend if it's running old code
2. **Short-term**: Make deactivate idempotent (return True if not found)
3. **Medium-term**: Improve error messaging in Settings to show why toggle failed
4. **Long-term**: Initialize default module config for new sites

## Files to Monitor

- `/opt/bms-intelligence/backend/app/api/modules.py` - Endpoint implementations
- `/opt/bms-intelligence/backend/app/services/module_registry_service.py` - Module logic
- `/opt/bms-intelligence/frontend/src/contexts/ModuleContext.tsx` - Frontend state
- `/opt/bms-intelligence/frontend/src/components/Settings.tsx` - UI
- `/opt/bms-intelligence/Caddyfile` - Reverse proxy configuration

## Next Steps

1. Run diagnostic steps in order
2. Identify which root cause applies
3. Apply targeted fix
4. Test toggle functionality
5. Verify with browser DevTools Network tab
