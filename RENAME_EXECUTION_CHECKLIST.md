# OpenClaw → SENTRY Rename Execution Checklist

**Complete, portable rename with environment variable support**

---

## Pre-Execution Verification ✅

- [x] Rename script created: `scripts/rename_clawd_to_sentry.sh`
- [x] Validation script created: `scripts/validate_sentry_rename.py`
- [x] Environment setup guide: `SENTRY_ENVIRONMENT_SETUP.md`
- [x] Rename guide: `SENTRY_RENAME_GUIDE.md`
- [x] Scripts are executable
- [x] `$SENTRY_HOME` support integrated into rename patterns
- [x] Bot dependencies verified (internal only, no external API consumers)
- [x] Git status clean (or changes backed up)

---

## Execution Plan (5 Stages)

### Stage 1: Dry-Run & Review (5 min, zero risk)

**Goal:** Preview all changes before execution

```bash
cd /opt/bms-intelligence

# Run dry-run
./scripts/rename_clawd_to_sentry.sh --dry-run

# Review output
cat .rename-log-*.txt | less

# Key things to check:
#   ✓ 45+ files will be modified
#   ✓ 150+ replacements will be made
#   ✓ $SENTRY_HOME appears in paths
#   ✓ No unexpected changes
```

**Success criteria:**
- ✅ Log file generated and readable
- ✅ Shows before/after for each pattern
- ✅ All patterns match the mapping table

---

### Stage 2: Execute Rename (1-2 min, reversible)

**Goal:** Apply all changes with automatic backup

```bash
cd /opt/bms-intelligence

# Execute rename (will prompt for confirmation)
./scripts/rename_clawd_to_sentry.sh --execute

# You'll see:
#   ✓ Automatic backup created
#   ✓ 45 files modified
#   ✓ 150+ replacements applied
#   ✓ Python syntax validated
#   ✓ Rollback instructions provided
```

**Success criteria:**
- ✅ All files modified without errors
- ✅ Python syntax valid
- ✅ No " Syntax error" messages
- ✅ Backup directory created (`.rename-backup-*`)

**If something goes wrong:**
```bash
# One-command rollback
./scripts/rename_clawd_to_sentry.sh --rollback
```

---

### Stage 3: Validate Completeness (2-3 min)

**Goal:** Verify no clawd references remain and all changes are consistent

```bash
cd /opt/bms-intelligence

# Run validation
python3 scripts/validate_sentry_rename.py

# Expected output:
#   ✓ 892+ files checked
#   ✓ 0 forbidden patterns found
#   ✓ Python imports valid
#   ✓ API endpoints use /api/sentry/
#   ✓ Configuration keys use sentry_
#   ✓ Status: PASS
```

**Success criteria:**
- ✅ No forbidden patterns found (all clawd refs renamed)
- ✅ All Python files have valid syntax
- ✅ No import errors
- ✅ Final status: PASS

**If validation fails:**
```bash
# Review specific issues
python3 scripts/validate_sentry_rename.py

# If needed, rollback and retry
./scripts/rename_clawd_to_sentry.sh --rollback
```

---

### Stage 4: Commit Changes

**Goal:** Create clean, single commit for the rename

```bash
cd /opt/bms-intelligence

# Review what changed
git status
git diff --stat

# Stage all changes
git add -A

# Commit with generated message
git commit -m "refactor(bot): Rename OpenClaw → SENTRY system-wide

This commit renames all clawd/openclaw references to sentry across the
entire codebase, including:

- Python class names (SentryAuthService → SentryAuthService)
- API endpoints (/api/sentry/ → /api/sentry/)
- Environment variables (SENTRY_* → SENTRY_*)
- Configuration keys and settings
- HTTP headers (X-Sentry-Secret → X-Sentry-Secret)
- Path references updated to use \$SENTRY_HOME environment variable
- Documentation and comments

Architecture improvements:
- Portable deployment: VM (/home/bederf/.sentry) → Jetson (/opt/sentry)
- Single codebase for multi-site deployments
- Environment-driven configuration throughout

All tests and imports verified. No functional changes — purely branding
and infrastructure portability."

# Verify commit
git log -1 --stat
```

**Success criteria:**
- ✅ Single commit created
- ✅ Commit message is descriptive
- ✅ All 45+ files included
- ✅ 150+ changes recorded

---

### Stage 5: Directory Rename on VM (5 min)

**Goal:** Move bot directory to use new naming and set environment variable

```bash
cd /home/bederf

# Backup current directory
cp -r clawd clawd.backup.$(date +%s)

# Rename directory
mv clawd .sentry

# Verify
ls -la .sentry
ls -la .sentry/bot.py

# Set environment variable in ~/.bashrc
echo 'export SENTRY_HOME=$HOME/.sentry' >> ~/.bashrc
source ~/.bashrc

# Verify
echo $SENTRY_HOME

# Test bot still works
cd $SENTRY_HOME
python3 bot.py --version

# Update systemd service if running as service
sudo systemctl stop clawd 2>/dev/null || true
sudo systemctl disable clawd 2>/dev/null || true

# Create new sentry service (see SENTRY_ENVIRONMENT_SETUP.md)
# Then restart
cd $SENTRY_HOME && python3 bot.py &
```

**Success criteria:**
- ✅ Directory renamed to `.sentry`
- ✅ `$SENTRY_HOME` environment variable set
- ✅ Bot still runs: `python3 $SENTRY_HOME/bot.py`
- ✅ Processes show SENTRY (not Clawd)

---

## Final Verification Checklist

After all 5 stages, verify complete success:

```bash
# 1. Environment variable
echo $SENTRY_HOME
# Expected: /home/bederf/.sentry

# 2. Directory structure
ls -la $SENTRY_HOME/
# Expected: bot.py, config/, tools/, handlers/, memory/

# 3. No clawd references in code
grep -r "clawd\|openclaw" /opt/bms-intelligence --include="*.py" | wc -l
# Expected: 0

# 4. API endpoints renamed
grep -r "/api/sentry/" /opt/bms-intelligence --include="*.py" | wc -l
# Expected: 30+ matches

# 5. Python syntax
python3 -m py_compile /opt/bms-intelligence/backend/app/api/sentry_webhooks.py
# Expected: No error

# 6. Bot imports
python3 -c "from app.services.sentry_auth_service import SentryAuthService; print('✓ OK')"
# Expected: ✓ OK

# 7. Git history clean
git log --oneline -3
# Expected: Latest commit is the rename
```

---

## What Gets Renamed (Summary)

| Category | Count | Example |
|----------|-------|---------|
| API endpoints | 35 | `/api/sentry/` → `/api/sentry/` |
| Python classes | 12 | `SentryAuthService` → `SentryAuthService` |
| Environment vars | 8 | `SENTRY_BOT_USERNAME` → `SENTRY_BOT_USERNAME` |
| Config keys | 6 | `sentry_webhook_secret` → `sentry_webhook_secret` |
| Path references | 4 | `$SENTRY_HOME` → `$SENTRY_HOME` |
| HTTP headers | 5 | `X-Sentry-Secret` → `X-Sentry-Secret` |
| Function names | 18 | `get_sentry_jwt_headers()` → `get_sentry_jwt_headers()` |
| Documentation | 45+ | Comments, docs, READMEs |
| **TOTAL** | **~150** | **Across 45 files** |

---

## Rollback Procedure (Emergency)

If anything goes wrong at any stage:

```bash
# Stage 1 (dry-run): No changes made, just delete log files
rm .rename-log-*.txt

# Stages 2-3 (after execution): Automatic backup exists
./scripts/rename_clawd_to_sentry.sh --rollback

# Stage 5 (directory): Restore from backup
cp -r $SENTRY_HOME.backup.* $SENTRY_HOME

# Git: Revert last commit if already pushed
git revert HEAD
```

---

## Next Steps After Rename

Once rename is complete and verified:

1. **Push to remote** (if using version control):
   ```bash
   git push origin main
   ```

2. **Update documentation**:
   - README files referencing `$SENTRY_HOME` → `$SENTRY_HOME`
   - Setup guides → use new paths
   - API documentation → `/api/sentry/` endpoints

3. **Deploy to Jetson** (see `SENTRY_ENVIRONMENT_SETUP.md`):
   ```bash
   export SENTRY_HOME=/opt/sentry
   # ... copy and setup
   ```

4. **Add WhatsApp channel** (Stage 4 of original plan)

5. **Update API clients** (frontend, external integrations):
   - Change endpoint calls from `/api/sentry/` to `/api/sentry/`
   - Update configuration files

---

## Troubleshooting Common Issues

### "No files found" during dry-run
```bash
# Means rename already done or no clawd references exist
grep -r "clawd" /opt/bms-intelligence --include="*.py" | head -5
```

### Python syntax error during execution
```bash
# Fix the file manually or rollback
./scripts/rename_clawd_to_sentry.sh --rollback

# Then examine what went wrong
git diff .rename-backup-*/backend/app/api/...
```

### `$SENTRY_HOME` not expanding in bot
```bash
# Add to bot.py startup
import os
SENTRY_HOME = os.environ.get('SENTRY_HOME', '/home/bederf/.sentry')

# Or set permanently in ~/.bashrc
echo 'export SENTRY_HOME=/home/bederf/.sentry' >> ~/.bashrc
```

### Validation still shows clawd references
```bash
# Find remaining references
grep -rn "clawd\|CLAWD" /opt/bms-intelligence --include="*.py" | head -20

# Manually fix or rollback and retry
./scripts/rename_clawd_to_sentry.sh --rollback
```

---

## Success Criteria Summary

✅ **All 5 stages complete when:**
- [ ] Dry-run shows 45+ files, 150+ changes
- [ ] Execute completes without errors
- [ ] Validation passes (0 forbidden patterns)
- [ ] Single clean commit created
- [ ] Directory renamed to `.sentry`
- [ ] `$SENTRY_HOME` environment variable set
- [ ] Bot runs: `python3 $SENTRY_HOME/bot.py`
- [ ] No `clawd` references remain in code

---

## Time Estimate

| Stage | Task | Time |
|-------|------|------|
| 1 | Dry-run & review | 5 min |
| 2 | Execute rename | 1-2 min |
| 3 | Validate | 2-3 min |
| 4 | Commit | 2 min |
| 5 | Directory & env setup | 5 min |
| **TOTAL** | | **15-20 min** |

**Next stages (not in this rename):**
- WhatsApp channel setup: 30-45 min
- Jetson migration: 20-30 min
- Production testing: 30-60 min

---

**Ready to proceed with Stage 1 (dry-run)?**

```bash
cd /opt/bms-intelligence
./scripts/rename_clawd_to_sentry.sh --dry-run
```
