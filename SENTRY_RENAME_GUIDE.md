# SENTRY Rename Guide

**Renaming Sentry → SENTRY System-Wide**

This guide walks through the complete, safe process of renaming all `sentry` references to `sentry` across the SENTINEL codebase.

---

## 📋 Overview

This is a **4-stage systematic rename** with built-in safety:

| Stage | Task | Duration | Risk |
|-------|------|----------|------|
| 1️⃣ | **Dry-run analysis** — preview all changes | 30 sec | ✅ None |
| 2️⃣ | **Review changes** — examine the log | 5 min | ✅ None |
| 3️⃣ | **Execute rename** — apply changes + backup | 1-2 min | ⚠️ Revertible |
| 4️⃣ | **Validation** — verify syntax + tests | 2-3 min | ⚠️ Can rollback |

**Key Safety Features:**
- ✅ Automatic backup before execution
- ✅ Dry-run mode to preview changes
- ✅ Syntax validation after rename
- ✅ One-command rollback if needed
- ✅ Git-safe (one clean commit)

---

## 🚀 Quick Start (TL;DR)

```bash
# Stage 1: See what will change
./scripts/rename_sentry_to_sentry.sh --dry-run

# Review output in .rename-log-*.txt

# Stage 2: Execute the rename
./scripts/rename_sentry_to_sentry.sh --execute

# Stage 3: Validate
python3 scripts/validate_sentry_rename.py

# Stage 4: Commit
git add -A
git commit -m "refactor(bot): Rename Sentry → SENTRY system-wide"
```

---

## 📖 Detailed Walkthrough

### Stage 1️⃣: Dry-Run Analysis

Preview everything that will change **without modifying files**.

```bash
cd /opt/bms-intelligence

./scripts/rename_sentry_to_sentry.sh --dry-run
```

**Output:**

```
[INFO] Starting DRY-RUN analysis...
[INFO] Output directory: .rename-log-2026-02-18-101234.txt

Files to be modified:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

backend/app/api/sentry_webhooks.py
  Line 34:
    - router = APIRouter(prefix="/api/sentry", tags=["sentry"])
    + router = APIRouter(prefix="/api/sentry", tags=["sentry"])

  Line 50:
    - x_sentry_secret: Optional[str] = Header(None),
    + x_sentry_secret: Optional[str] = Header(None),

backend/app/services/sentry_auth_service.py
  Line 15:
    - class SentryAuthService:
    + class SentryAuthService:

... (150+ more matches across 45 files)

Summary:
  Files to modify: 45
  Total matches:   156
```

**What gets renamed:**

| Pattern | Before | After | Count |
|---------|--------|-------|-------|
| Endpoints | `/api/sentry/` | `/api/sentry/` | 35 |
| Classes | `SentryAuthService` | `SentryAuthService` | 12 |
| Env Vars | `SENTRY_BOT_USERNAME` | `SENTRY_BOT_USERNAME` | 8 |
| Config Keys | `sentry_webhook_secret` | `sentry_webhook_secret` | 6 |
| Headers | `X-Sentry-Secret` | `X-Sentry-Secret` | 5 |
| Docs/Comments | `Sentry bot` | `Sentry bot` | 45+ |
| Other | Various function names, imports, etc. | ... | 50+ |

### Stage 2️⃣: Review the Changes

Open the generated log file to review what changed:

```bash
# Find the log file
ls -lh .rename-log-*.txt | tail -1

# View it
cat .rename-log-*.txt | less

# Or search for specific files
grep "backend/app/api/sentry_webhooks.py" .rename-log-*.txt
```

**What to look for:**
- ✅ Each change has "before" and "after" lines
- ✅ All patterns match the mapping table (see below)
- ✅ No accidental partial replacements (e.g., "sentry-integration" → "sentry-integration" not "sentryintegration")
- ✅ Comments and documentation properly renamed

### Stage 3️⃣: Execute the Rename

Actually apply all changes. **This will prompt for confirmation.**

```bash
./scripts/rename_sentry_to_sentry.sh --execute
```

**You'll see:**

```
[INFO] Starting RENAME execution...
[INFO] Backup directory: .rename-backup-1708266925

Continue with rename execution? (yes/no): yes

[INFO] Creating backup of all files...
[✓] Backup created at .rename-backup-1708266925

[INFO] Performing replacements...
[✓] backend/app/api/sentry_webhooks.py (8 replacements)
[✓] backend/app/services/sentry_auth_service.py (12 replacements)
[✓] backend/app/services/sentry_integration/alert_notifier.py (5 replacements)
... (42 more files)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[✓] Rename complete!
  Files modified: 45
  Total replacements: 156

[INFO] Verifying Python syntax...
[✓] All Python files have valid syntax

Rollback instructions:
  To rollback: rm -rf $PROJECT_ROOT && cp -r .rename-backup-1708266925 $PROJECT_ROOT
  Backup location: .rename-backup-1708266925
```

**Backup is automatically created** in `.rename-backup-*` directory. You can rollback at any time.

### Stage 4️⃣: Validate Completeness

Run the validation script to ensure **no sentry references remain** and everything is consistent:

```bash
python3 scripts/validate_sentry_rename.py
```

**Output:**

```
Collecting files...
Scanning 892 files for forbidden patterns...
  Checked 100 files...
  Checked 200 files...
  Checked 300 files...
  Checked 400 files...
  Checked 500 files...
  Checked 600 files...
  Checked 700 files...
  Checked 800 files...
  Checked 892 files...

Running validation checks...
[SUCCESS] Checking Python imports...
[SUCCESS] All 145 Python files have valid syntax

======================================================================
SENTRY Rename Validation Report
======================================================================

✓ Successes (5):
  ✓ All 145 Python files have valid syntax
  ✓ API endpoints properly use /api/sentry/ in sentry_webhooks.py
  ✓ Configuration keys use sentry_ prefix
  ✓ Documentation: 28/30 files reference SENTRY
  ✓ No forbidden patterns found

Summary:
  Files checked:     892/892
  Issues found:      0
  Warnings:          0
  Errors:            0
  Status:            PASS
```

---

## 📋 What Gets Renamed (Complete Mapping)

### Python Code

```python
# Classes
SentryAuthService          → SentryAuthService

# Function names
initialize_sentry_auth()    → initialize_sentry_auth()
get_sentry_auth_service()   → get_sentry_auth_service()
get_sentry_jwt_headers()    → get_sentry_jwt_headers()
notify_sentry()             → notify_sentry()

# Variables & imports
sentry_auth                 → sentry_auth
_sentry_auth_service        → _sentry_auth_service
from app.services.sentry_   → from app.services.sentry_

# Config keys
sentry_webhook_secret       → sentry_webhook_secret
sentry_bot_api_key          → sentry_bot_api_key
sentry_username             → sentry_username
sentry_password             → sentry_password
sentry_notifications        → sentry_notifications
```

### API Endpoints

```
/api/sentry/work-order/notify           → /api/sentry/work-order/notify
/api/sentry/work-order/response         → /api/sentry/work-order/response
/api/sentry/work-order/status/{code}    → /api/sentry/work-order/status/{code}
/api/sentry/ocr/process-service-sheet   → /api/sentry/ocr/process-service-sheet
/api/sentry-webhooks                    → /api/sentry-webhooks
```

### Environment Variables

```
SENTRY_WEBHOOK_SECRET      → SENTRY_WEBHOOK_SECRET
SENTRY_BOT_API_KEY          → SENTRY_BOT_API_KEY
SENTRY_BOT_USERNAME         → SENTRY_BOT_USERNAME
SENTRY_BOT_PASSWORD         → SENTRY_BOT_PASSWORD
```

### HTTP Headers

```
X-Sentry-Secret             → X-Sentry-Secret
X-Sentry-API-Key            → X-Sentry-API-Key
```

### Shared Secrets

```
sentry-bms-phase-41         → sentry-bms-phase-41
```

---

## 🔄 Rollback Procedure

If something goes wrong, **one command reverses everything:**

```bash
./scripts/rename_sentry_to_sentry.sh --rollback
```

**This:**
1. Finds the latest backup
2. Shows what will be restored
3. Prompts for confirmation
4. Restores from backup
5. Moves old backup to `.renamed.restored` for inspection

**Important:**
- Rollback requires the `.rename-backup-*` directory to exist
- Backups are created before execution (automatic)
- You can manually restore: `cp -r .rename-backup-* ./` if needed

---

## ⚠️ Troubleshooting

### Issue: Script says "No files found"

This means no sentry references exist in the codebase — **rename is already complete** or files don't exist.

**Check:**
```bash
grep -r "sentry\|sentry" /opt/bms-intelligence --include="*.py" | head -5
```

If nothing shows up, rename is done.

### Issue: Validation fails with "Pattern: /api/sentry/"

Some files still contain sentry references. **Find them:**

```bash
grep -rn "/api/sentry/" /opt/bms-intelligence --include="*.py" --include="*.ts"
```

**Fix manually or rollback and try again:**
```bash
./scripts/rename_sentry_to_sentry.sh --rollback
```

### Issue: Python syntax errors after rename

The rename script validates syntax, but if you find an error:

```bash
python3 -m py_compile backend/app/services/sentry_auth_service.py
```

**Most common cause:** A regex or special character in a string got partially replaced.

**Fix:** Edit the file manually or rollback:
```bash
./scripts/rename_sentry_to_sentry.sh --rollback
```

### Issue: Git merge conflicts

If you have uncommitted changes, the rename will modify them. **Before running:**

```bash
git status

# If dirty, commit or stash first
git commit -am "work in progress"
# OR
git stash
```

---

## 🧪 Testing After Rename

After completing the rename, **test the key systems:**

### 1. Import checks

```bash
# Test that services import correctly
python3 -c "from app.services.sentry_auth_service import SentryAuthService; print('✓ OK')"
python3 -c "from app.services.sentry_integration import alert_notifier; print('✓ OK')"
```

### 2. API endpoint checks

```bash
# Start backend
DEMO_MODE=true python -m uvicorn app.main:app --reload --port 9095 &

# Test endpoints (should return 200 or 401, not 404)
curl http://localhost:9095/api/sentry/work-order/pending -i
curl http://localhost:9095/api/sentry-webhooks/health -i

# Stop
kill %1
```

### 3. Configuration checks

```bash
# Verify settings.py has sentry_ keys
grep "sentry_" backend/app/config/settings.py | head -10

# Check .env
grep "SENTRY_" backend/.env 2>/dev/null || echo "(.env not committed)"
```

### 4. Run existing tests

```bash
cd backend
pytest tests/api/test_sentry_webhooks.py -v 2>&1 | head -50
# Should have test files named test_sentry_webhooks.py or similar if renamed
```

---

## 📝 Commit Message Template

After validation passes, **commit with this message:**

```bash
git add -A
git commit -m "refactor(bot): Rename Sentry → SENTRY system-wide

This commit renames all sentry/sentry references to sentry across the
entire codebase, including:

- Python class names (SentryAuthService → SentryAuthService)
- API endpoints (/api/sentry/ → /api/sentry/)
- Environment variables (SENTRY_* → SENTRY_*)
- Configuration keys and settings
- HTTP headers (X-Sentry-Secret → X-Sentry-Secret)
- Documentation and comments

No functional changes — purely a systematic renaming for clarity and
branding consistency. All tests and imports verified.

Tested with:
- Python syntax validation (145 files)
- Import verification
- API endpoint checks
- Configuration validation
- Documentation consistency

Files modified: 45
Total replacements: 156"
```

---

## 🔍 Files Modified (Full List)

**Backend API:**
- `backend/app/api/sentry_webhooks.py` → `sentry_webhooks.py` (optional)
- `backend/app/api/registrars/operations.py` (imports)
- `backend/app/api/registrars/safety_simulation.py` (imports)
- `backend/app/api/sensor_analysis.py` (imports)
- `backend/app/api/water.py` (function calls)
- `backend/app/api/alerts.py` (config keys)

**Backend Services:**
- `backend/app/services/sentry_auth_service.py` → class + functions renamed
- `backend/app/services/sentry_integration/` (directory) — 8 files
- `backend/app/services/equipment_alert_service.py`
- `backend/app/services/lifecycle_orchestrator.py`
- `backend/app/services/background_scheduler.py`
- `backend/app/services/water_alert_service.py`
- `backend/app/services/bms_simulation_service.py`
- `backend/app/services/hybrid_ai_service.py`

**Configuration & Startup:**
- `backend/app/config/settings.py` (keys)
- `backend/app/startup/events.py` (initialization)
- `backend/app/startup/middleware.py` (routes)
- `backend/app/main.py` (imports)

**Frontend:**
- `frontend/src/lib/simulationApi.ts` (one reference)

**Documentation:**
- `DEPLOY_SENTRY_FILES.md` → update file/directory paths
- `CLAUDE_INTEGRATION_GUIDE.md` → `/home/bederf/sentry/`
- `CLAUDE_UPDATE_DESK_SKILL.md` → `/home/bederf/sentry/`
- 25+ other .md files

**Tests & Scripts:**
- `backend/scripts/test_sentry_integration.sh` → `test_sentry_integration.sh` (optional)

---

## 📊 Rename Statistics

After running the script, you'll see:

```
Files to modify:     45
Total replacements:  156

Breakdown:
  - API endpoints:      35 matches (11 files)
  - Python classes:     12 matches (3 files)
  - Environment vars:    8 matches (2 files)
  - Config keys:         6 matches (1 file)
  - HTTP headers:        5 matches (2 files)
  - Function names:     18 matches (8 files)
  - Documentation:      45+ matches (30 files)
  - Other:              27 matches (8 files)
```

---

## 🎯 Next Steps After Rename

1. **Commit the changes** (see template above)
2. **Update directory names** (optional but recommended):
   ```bash
   # If Sentry directory exists on VM
   mv ~/.sentry ~/.sentry
   mv $SENTRY_HOME /home/bederf/.sentry
   ```
3. **Update documentation** referring to directory paths
4. **Push to remote:**
   ```bash
   git push origin main
   ```
5. **Deploy to staging** for integration testing
6. **Deploy to production** with the new naming

---

## 📞 Support

If you encounter issues:

1. **Check the log file:** `.rename-log-*.txt`
2. **Run validation:** `python3 scripts/validate_sentry_rename.py --strict`
3. **Review diffs:** `git diff --stat` to see all changed files
4. **Rollback if needed:** `./scripts/rename_sentry_to_sentry.sh --rollback`

---

**Last Updated:** 2026-02-18  
**Tested On:** Ubuntu 20.04 LTS, Python 3.10+, Bash 5.0+
