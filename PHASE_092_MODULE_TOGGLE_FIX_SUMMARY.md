# Phase 092 - Module Toggle Fix Summary

**Date**: 2026-02-16  
**Status**: ✅ COMPLETE - Ready for deployment  
**Commit**: b5a2311

## Problem

Users reported: "the modules in the settings page is still not toggle off" - module toggles showed "offline icon" and didn't work, even after the auth level was lowered from ADMIN to OPERATOR in commit a48fb87.

## Root Causes Identified

### 1. **Deactivation Returns False on New Sites** (PRIMARY)
- `deactivate_module()` returned `False` when site config didn't exist
- Endpoint returned 404 "Module not found or not active"  
- Affected new sites with no previous module configuration
- **Fix**: Make deactivation idempotent - return `True` even if config/module not found

### 2. **Error Messages Not Shown to Users** (SECONDARY)
- API returned helpful error messages (e.g., "solar module requires control module to be active")
- Frontend threw generic "Failed to deactivate module" error
- Users couldn't understand why toggles failed
- **Fix**: Extract and display actual error detail from API response

## Changes Made

### Backend (module_registry_service.py)
```python
# Before:
def deactivate_module(self, site_id, module_type):
    if not config:
        return False  # ❌ Causes 404 error
    ...

# After:
def deactivate_module(self, site_id, module_type):
    if not config:
        return True  # ✅ Idempotent - no error
    ...
```

### Frontend (moduleRegistry.ts)
```typescript
// Before:
if (!response.ok) throw new Error('Failed to deactivate module');

// After:
if (!response.ok) {
  const errorData = await response.json();
  throw new Error(errorData.detail || `Failed to deactivate module (${response.status})`);
}
```

## Impact

| Scenario | Before | After |
|----------|--------|-------|
| Deactivate on new site | ❌ 404 error | ✅ Success (idempotent) |
| Activate SOLAR without CONTROL | ❌ "Failed to activate" | ✅ "solar module requires control module..." |
| Deactivate non-existent module | ❌ "Module not found" | ✅ Success (idempotent) |
| Module dependency error | ❌ Generic message | ✅ Clear error message |

## Deployment Steps

### 1. Pull Latest Code
```bash
git pull origin main
# Should see commit b5a2311
```

### 2. Rebuild Backend (if needed)
```bash
cd backend
python -m pip install -r requirements.txt  # If dependencies changed
# Backend will auto-reload if using --reload flag
```

### 3. Rebuild and Deploy Frontend
```bash
cd frontend
npm run build
# Copy dist/ to production web server or restart service
systemctl restart sentinel-frontend  # Or equivalent restart command
```

### 4. Restart Services
```bash
# Restart backend
systemctl restart sentinel-backend

# Verify services running
systemctl status sentinel-backend sentinel-frontend
```

### 5. Verify Fix Works

**Test 1: Basic Toggle**
1. Go to Settings → Feature Access
2. Find "Asset Workflow" module (should be toggleable)
3. Try to activate/deactivate
4. Should work without errors

**Test 2: Dependency Check**
1. Find "Building Controls" (CONTROL module)
2. Activate it first
3. Then try "Solar & BESS" (SOLAR module)
4. Should now work (requires CONTROL)

**Test 3: Error Messages**
1. Try to activate "Solar & BESS" WITHOUT "Building Controls" active
2. Should see clear error: "solar module requires control module to be active first"
3. Not just generic "Failed" message

**Test 4: Browser Console**
1. Open DevTools (F12) Network tab
2. Try toggle that fails (e.g., SOLAR without CONTROL)
3. Look for POST to `/api/modules/activate`
4. Should see error response with meaningful detail message

## Files Changed

### Backend
- `backend/app/services/module_registry_service.py` - Idempotent deactivation
- `backend/app/database/repositories/user_entitlements_repository.py` - (created)
- `backend/app/models/user_entitlements.py` - (created)

### Frontend  
- `frontend/src/lib/moduleRegistry.ts` - Better error extraction
- `frontend/src/components/Settings.tsx` - Error display (unchanged logic)

### QA
- `backend/tests/test_module_toggle_diagnostic.sh` - New diagnostic script
- `PHASE_090_MODULE_TOGGLE_DEBUG.md` - Debugging guide

## Verification Checklist

- [x] Code compiles without errors
- [x] TypeScript type checking passes
- [x] Frontend builds successfully (2,949 KB gzipped)
- [x] Git commit created with detailed message
- [x] Error handling graceful (JSON and non-JSON responses)
- [x] Idempotent behavior preserves cascade logic
- [ ] Deployed to production  ← NEXT STEP
- [ ] Tested on production site (site-002)
- [ ] User can toggle modules without "offline" error
- [ ] Error messages are clear and helpful

## Troubleshooting

### If toggles still don't work after deployment:

1. **Check Backend Restarted**
   ```bash
   ps aux | grep uvicorn | grep -v grep
   # Should show recent start time
   ```

2. **Verify Commit Deployed**
   ```bash
   # On production server
   cd /opt/bms-intelligence
   git log -1 --oneline | grep "Make deactivation idempotent"
   ```

3. **Check Browser Network**
   - F12 → Network tab
   - Try toggle
   - Look at `/api/modules/activate` response
   - What HTTP status? What error message?

4. **Run Diagnostic Script**
   ```bash
   bash backend/tests/test_module_toggle_diagnostic.sh
   # Shows what's happening with endpoints
   ```

5. **Check Module Dependencies**
   - Try activating CONTROL first
   - Then try SOLAR/LIGHTING
   - Should work better with dependencies met

## Additional Notes

### Why Auth Level Was Already Fixed

Commit a48fb87 already lowered auth from ADMIN to OPERATOR:
- Demo users automatically get OPERATOR role
- This was correct and necessary
- But still didn't fix deactivation on new sites (that's what this fix addresses)

### Idempotent Behavior

Making deactivation idempotent is safe because:
- Deactivating something already off = still off ✓
- No data loss
- Follows REST best practices
- Matches user expectations (toggling off twice = still off)

### Cascade Still Works

Cascade deactivation is preserved:
- Deactivate CONTROL → SOLAR and LIGHTING also deactivate ✓
- Only triggers if module actually deactivated (not if already off)
- All related cross-module links disabled correctly

## Next Phase

Once verified in production:
- Document module dependencies for users (SOLAR requires CONTROL, etc.)
- Consider auto-activating CONTROL when user tries to activate SOLAR
- Add visual indicators for dependencies in Settings UI
- Implement bulk toggle operations

## Questions?

See: `PHASE_090_MODULE_TOGGLE_DEBUG.md` for detailed diagnostic guide
