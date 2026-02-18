# CLAUDE_LOCAL_SETUP.md

Comprehensive guide for local development setup, verification, and troubleshooting for the SENTINEL BMS Intelligence Platform.

**TL;DR:** See "Quick Verification Checklist" below. For specific issues, jump to the relevant section.

---

## Quick Verification Checklist

Run these commands in order after initial setup:

```bash
# 1. Backend imports
cd backend && source venv/bin/activate
python -c "import app; print('✓ Backend imports OK')" || exit 1

# 2. Backend server
./start-backend.sh &
sleep 3
curl -s http://localhost:9095/health | head -3 || echo "Backend health check failed"

# 3. Frontend deps
cd ../frontend
npm list react react-dom | head -3 || exit 1

# 4. Frontend build
npm run build 2>&1 | tail -5 || exit 1

# 5. Database (local Supabase)
supabase status | grep "API URL"

# 6. Pre-commit hooks
pre-commit run --all-files 2>&1 | tail -5

echo "✓ All checks passed - ready to develop!"
```

---

## Environment Setup

### One-Time Setup

```bash
# Clone and enter repo
git clone <repo-url> && cd /opt/bms-intelligence

# Backend setup
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: Update JWT_SECRET_KEY (openssl rand -hex 32) and API keys

# Frontend setup
cd ../frontend
npm install  # First time only

# Pre-commit hooks (one-time)
pip install pre-commit
pre-commit install
pre-commit run --all-files  # Validate setup

# Start services
./start-backend.sh  # Terminal 1
./start-frontend.sh  # Terminal 2
```

### Restarting Development

```bash
# Short-lived development session
./start-backend.sh  # Terminal 1
./start-frontend.sh  # Terminal 2

# After git pull (dependencies may have changed)
cd backend && source venv/bin/activate && pip install -r requirements.txt
cd ../frontend && npm ci  # Clean install, not npm install
```

---

## Port Conflicts & Resolution

### Checking Port Availability

```bash
# Find what's using a port
lsof -i :9095  # Backend port
lsof -i :9096  # Frontend port
lsof -i :55321  # Supabase API
lsof -i :55322  # Supabase DB

# On Windows (or no lsof)
netstat -tulpn 2>/dev/null | grep LISTEN
```

### Resolving Conflicts

**If port 9095 (Backend) is in use:**
```bash
# Kill existing process
kill $(lsof -t -i :9095)

# Or use different port (then update VITE_API_URL in frontend .env)
cd backend && uvicorn app.main:app --reload --port 9097
```

**If port 9096 (Frontend) is in use:**
```bash
# Kill existing process
kill $(lsof -t -i :9096)

# Or use different port (update in start-frontend.sh)
cd frontend && npm run dev -- --port 9097
```

**If Supabase ports (55321, 55322, 55323) are in use:**
```bash
# Stop local Supabase
supabase stop

# Wait 10 seconds for cleanup
sleep 10

# Start again
supabase start
```

---

## Virtual Environment Issues

### Backend Virtual Environment

**Corrupted venv:**
```bash
cd backend
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
touch venv/.deps_installed
```

**Python version mismatch (requires 3.11+):**
```bash
python3 --version  # Should be 3.11+
which python3.11  # Check if available

# If using Python 3.10 or 3.9:
python3.11 -m venv backend/venv
source backend/venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
```

**Activation issues on different shells:**
```bash
# bash/zsh
source backend/venv/bin/activate

# fish
source backend/venv/bin/activate.fish

# Windows (cmd)
backend\venv\Scripts\activate.bat

# Windows (PowerShell)
backend/venv/Scripts/Activate.ps1
```

**After activation, verify:**
```bash
which python  # Should show /path/to/backend/venv/bin/python
python -c "import sys; print(sys.prefix)"  # Should show venv path
```

---

## Node Modules & TypeScript Cache Issues

### Symptom: "Module has no exported member 'X'" despite export existing

**Clean Cache + Fresh Install:**
```bash
cd frontend

# Remove all cache directories
rm -rf node_modules/.vite
rm -rf node_modules/.tsc*
rm -rf .next
rm -rf .turbo

# Full clean install
rm -rf node_modules package-lock.json
npm cache clean --force
npm install

# Restart IDE/TypeScript server
# In VS Code: Cmd+Shift+P → "TypeScript: Restart TS server"
# In WebStorm: File → Invalidate Caches
```

### Symptom: "Cannot find module '@/lib/api'" after editing tsconfig.json

```bash
cd frontend

# Verify tsconfig.app.json has path aliases
cat tsconfig.app.json | grep -A5 '"paths"'
# Should show: "@/*": ["./src/*"]

# Clear TypeScript build cache
rm -rf tsconfig.tsbuildinfo

# Rebuild
npm run build
```

### Symptom: TypeScript compiles but IDE shows red squiggles

```bash
# IDE cache issue - restart TypeScript server

# VS Code
cmd/ctrl + shift + p → "TypeScript: Restart TS server"

# WebStorm / IntelliJ
File → Invalidate Caches → Restart

# Vim / Neovim (restart language server)
# Most LS plugins: :LspRestart
```

### Clearing npm Cache

```bash
# View current cache location
npm cache verify

# Force clear
npm cache clean --force

# Verify
npm cache ls | wc -l  # Should be 0 or near 0
```

---

## Pre-commit Hook Failures

### Understanding Hook Blocks

Pre-commit hooks block commits for security and code quality. Not all blocks are errors.

```bash
# See which hooks ran
pre-commit run --all-files -v

# Run specific hook to debug
pre-commit run detect-secrets --all-files -v
pre-commit run check-hardcoded-secrets --all-files -v
```

### Common Hook Failures

**"Hardcoded API key detected"**
```bash
# False positive? Check what was flagged
grep -r "sk-ant-\|sk-\|eyJhbGciOi" backend/app frontend/src --include="*.py" --include="*.ts"

# Legitimate issue - Move to .env:
# In code: Use os.getenv("ANTHROPIC_API_KEY")
# In .env: ANTHROPIC_API_KEY=sk-...
```

**"detect-secrets baseline outdated"**
```bash
# Update baseline (review additions first!)
detect-secrets scan --baseline .secrets.baseline

# Or: git add .secrets.baseline
pre-commit run --all-files
```

**"File too large"** (>1000 KB)
```bash
# Find oversized files
find . -size +1000k -type f | grep -v node_modules | grep -v venv

# If necessary, commit separately or split:
# Option 1: Use Git LFS for large files
# Option 2: Move to outside repo, reference in README
```

**"Invalid safety rules JSON"**
```bash
# Validate JSON structure
python3 -c "import json; json.load(open('backend/app/data/safety_rules.json'))"

# Check required fields
python3 << 'EOF'
import json
with open('backend/app/data/safety_rules.json') as f:
    rules = json.load(f)
for rule in rules:
    assert 'rule_id' in rule, f'Missing rule_id in {rule}'
    assert 'severity' in rule, f'Missing severity in {rule}'
    assert rule['severity'] in ['WARNING', 'BLOCK', 'ALARM']
print(f"✓ Validated {len(rules)} rules")
EOF
```

**Override if intentional** (use sparingly):
```bash
git commit --no-verify  # Dangerous! Use only for config/docs
```

---

## Database & Supabase

### Local Supabase Status

```bash
# Check if running
supabase status

# Expected output:
# API URL: http://localhost:55321
# Database URL: postgresql://postgres:postgres@localhost:55322/postgres
# Studio URL: http://localhost:55323
```

### Connection Problems

**"Cannot connect to localhost:55321"**
```bash
# Verify Supabase is running
docker ps | grep supabase  # Check for containers

# If not running:
supabase start

# Wait for startup (can take 30-60 seconds)
sleep 10
supabase status
```

**"ECONNREFUSED" from backend**
```bash
# Check backend .env
cat backend/.env | grep SUPABASE_URL
# Should be: SUPABASE_URL=http://localhost:55321

# Test connection directly
curl -s http://localhost:55321/rest/v1/ | head -5

# If failed, fallback to JSON storage
echo "USE_JSON_STORAGE=true" >> backend/.env
./start-backend.sh
```

### Database Access

```bash
# View data in Supabase Studio
# Open http://localhost:55323 in browser
# Username: supabase
# Password: (from supabase start output)

# Direct database queries
psql postgresql://postgres:postgres@localhost:55322/postgres

# Useful queries
\dt  # List tables
\d equipment  # Show equipment table structure
SELECT count(*) FROM equipment;  # Count records
```

### Schema Verification

```bash
# After migrations, verify tables exist
supabase db list

# Check specific migration status
supabase migration list

# View pending migrations
supabase db pull  # Pulls remote schema for comparison

# Compare with git
git diff supabase/migrations/
```

### Rollback Changes

```bash
# If schema migration went wrong:
supabase db reset  # WARNING: Deletes all local data

# Safer: Backup first
pg_dump postgresql://postgres:postgres@localhost:55322/postgres > backup.sql

# Then reset
supabase db reset

# Restore from backup if needed
psql postgresql://postgres:postgres@localhost:55322/postgres < backup.sql
```

---

## Health Score & Alert Debugging

### Verify Health Score System

```bash
# 1. Create a test alert (triggers health_score persistence)
curl -X POST "http://localhost:9095/api/alerts/supabase" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(cat backend/.env | grep JWT_SECRET_KEY | cut -d= -f2)" \
  -d '{
    "equipment_code": "S002-CHILLER-B1-001",
    "severity": "critical",
    "message": "Test alert for health score"
  }'

# 2. Verify health_score was persisted
psql postgresql://postgres:postgres@localhost:55322/postgres -c \
  "SELECT code, health_score FROM equipment WHERE code='S002-CHILLER-B1-001';"

# Expected output: health_score should be 30 (critical)
```

**Health Score Lifecycle:**
```
Create CRITICAL alert → health_score = 30
Create WARNING alert → health_score = 60
Acknowledge alert (if no active alerts) → health_score = 85 (reset)
```

### Predictions Not Appearing

```bash
# Check if prediction job is running
grep "Prediction generation" backend.log

# Check equipment health thresholds
python backend/scripts/check_health_thresholds.py

# Manually generate predictions
curl "http://localhost:9095/api/predictions/site/S002?include_all=false" \
  -H "Authorization: Bearer <token>"

# Force recalculation
python << 'EOF'
import asyncio
from app.api.alerts import recalculate_equipment_health_score

asyncio.run(recalculate_equipment_health_score('S002-CHILLER-B1-001'))
EOF
```

---

## Performance Profiling & Debugging

### Backend Performance

**Find slow endpoints:**
```bash
# Check logs for duration field
tail -100 backend.log | grep "duration="

# Extract and sort by duration
grep "duration=" backend.log | \
  sed 's/.*duration=//' | \
  sed 's/[^0-9.]*$//' | \
  sort -rn | head -10
```

**Profile specific endpoint:**
```bash
# Test with profiling enabled
python -m cProfile -s cumtime -m pytest \
  tests/api/test_devices.py::test_get_device_batch -v

# Output will show cumulative time per function
```

**Memory profiling:**
```bash
# Install profiler
pip install memory-profiler

# Decorate function with @profile, then run:
python -m memory_profiler backend/app/api/devices.py
```

**Backend logs:**
```bash
# Real-time log watching
tail -f backend.log

# Filter by severity
grep ERROR backend.log
grep WARNING backend.log

# Count errors
grep ERROR backend.log | wc -l
```

### Frontend Performance

**Bundle analysis:**
```bash
cd frontend

# Build with analysis
npm run build -- --analyze  # Some bundlers support this

# Or use vite plugin
# See vite.config.ts for rollup analyzer setup
```

**React Query DevTools:**
```bash
# Open browser DevTools (F12)
# Click "React Query" tab (bottom left)
# View:
# - Query cache status (fresh/stale)
# - Request/response data
# - Query timing
# - Batch window detection
```

**Network tab debugging:**
```bash
# Open DevTools (F12) → Network tab
# Look for:
# - Batch endpoints: /api/devices/batch
# - Request deduplication (same query twice should = 1 request)
# - Response times >500ms (check for optimization)

# Check request headers
# Should include: Authorization: Bearer <token>
```

---

## Ollama & AI Services

### Verify Ollama

```bash
# Check if running on default port
curl -s http://localhost:11434/api/models | head -20

# If not found, start Ollama
ollama serve  # In separate terminal

# Load default model
ollama pull mistral  # Or your configured model
```

### Demo Mode vs Production

```bash
# Check current mode
grep DEMO_MODE backend/.env

# Demo mode (local development)
DEMO_MODE=true  # No Claude API calls, pre-seeded responses

# Production (real API)
DEMO_MODE=false
ANTHROPIC_API_KEY=sk-...  # Must be set
```

---

## Supabase-Specific Issues

### Migrations Not Applying

```bash
# Check migration status
supabase migration list

# Apply pending migrations
supabase db push

# See what changed
git diff supabase/migrations/

# If migration fails, debug SQL
psql postgresql://postgres:postgres@localhost:55322/postgres \
  < supabase/migrations/[migration-number]_[name].sql
```

### Schema Mismatch

```bash
# Local schema differs from remote?
supabase db pull --remote

# Review differences
git diff supabase/migrations/

# If correct, commit changes
git add supabase/migrations/
git commit -m "sync: update schema from remote"
```

### Data Not Syncing

```bash
# Check fallback status
grep "JSON_STORAGE_FALLBACK" backend.log

# If using JSON storage instead of Supabase:
echo "USE_JSON_STORAGE=false" >> backend/.env
# Then restart backend: ./start-backend.sh
```

---

## Common Issue Checklist

| Issue | Likely Cause | First Check |
|-------|-------------|-------------|
| "Cannot connect to backend" | Backend not running | `./start-backend.sh` |
| "Module not found" errors | npm cache stale | `npm ci && npm run build` |
| "Port already in use" | Previous session lingering | `lsof -i :9095` & `kill <PID>` |
| "Supabase connection refused" | Local Supabase not running | `supabase start` |
| "Health score not updating" | Alert not created properly | Check alert endpoint response |
| "TypeScript compilation fails" | Cache issue | `rm -rf node_modules/.tsc*` |
| "Pre-commit hook blocks commit" | Legitimate issue or false positive | `pre-commit run --all-files -v` |
| "Predictions not appearing" | Health score < 90 not persisted | Create test alert first |

---

## Getting Help

**Before asking for help, collect context:**

```bash
# System info
uname -a
python3 --version
node --version
npm --version

# Service status
ps aux | grep -E "uvicorn|vite|supabase"

# Recent logs (last 50 lines of errors)
tail -50 backend.log | grep ERROR

# Git state
git status
git log --oneline -5

# Environment
cat backend/.env | grep -v "=sk-" | head -20
```

**Share this info when asking for help:**
1. System info (see above)
2. Exact error message (full stack trace if available)
3. Steps to reproduce
4. What you've already tried
5. Related git commits

---

## Resources

- **Main docs:** See `CLAUDE.md` for architecture and patterns
- **Advanced patterns:** See `CLAUDE_ADVANCED_PATTERNS.md`
- **API reference:** http://localhost:9095/docs (Swagger UI)
- **React Query guide:** `frontend/README.md`
- **Backend README:** `backend/README_MCP_INTEGRATION.md`
- **Project memory:** `/home/bederf/.claude/projects/-opt-bms-intelligence/memory/MEMORY.md`
