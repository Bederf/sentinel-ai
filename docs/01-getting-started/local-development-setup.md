---
title: "Local development environment setup"
type: "guide"
status: "approved"
version: "1.0.0"
created: "2026-02-18"
updated: "2026-02-18"
tags: ["setup", "development", "local-dev", "getting-started"]
related: ["TASK_1A_DEPENDABOT_STATUS.md"]
domain: "general"
audience: "developers"
complexity: "beginner"
estimated_read_time: 30
---

# Local development environment setup

Complete guide for setting up the SENTINEL BMS Intelligence Platform for local development, including verification steps and common troubleshooting.

## Quick start (5 minutes)

For experienced developers, here's the essentials:

```bash
# One-time setup
git clone <repo-url> && cd /opt/bms-intelligence

# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt && cp .env.example .env

# Frontend
cd ../frontend && npm install

# Start services (3 terminals)
./start-backend.sh    # Terminal 1
./start-frontend.sh   # Terminal 2
supabase start        # Terminal 3 (if using local Supabase)
```

**Ports:** Backend (9095), Frontend (9096), Supabase API (55321), DB (55322), Studio (55323)

## Prerequisites

- **Operating system**: macOS, Linux, or Windows (WSL2)
- **Python**: 3.11+ (`python3 --version`)
- **Node.js**: 18+ (`node --version`)
- **npm**: 9+ (`npm --version`)
- **Docker**: Required for local Supabase
- **Git**: For version control

### Verifying prerequisites

```bash
# Check versions
python3 --version    # Should be 3.11+
node --version       # Should be 18+
npm --version        # Should be 9+
docker --version     # Should be installed
git --version        # Should be installed
```

If any are missing, install them from:
- Python: https://www.python.org/downloads/
- Node.js: https://nodejs.org/ (includes npm)
- Docker: https://www.docker.com/products/docker-desktop
- Git: https://git-scm.com/

## Step 1: Clone repository

```bash
git clone <repository-url>
cd /opt/bms-intelligence
```

## Step 2: Backend setup

### Create virtual environment

```bash
cd backend

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate    # macOS/Linux
# OR
.\venv\Scripts\activate.bat  # Windows (cmd)
# OR
.\venv\Scripts\Activate.ps1  # Windows (PowerShell)

# Verify activation
which python  # Should show path to venv
```

### Install dependencies

```bash
# Within activated venv
pip install --upgrade pip
pip install -r requirements.txt

# Verify installation
python -c "import app; print('✓ Backend imports OK')"
```

### Configure environment

```bash
# Copy example configuration
cp .env.example .env

# Edit .env with your values
# Required fields:
# - JWT_SECRET_KEY: Generate with: openssl rand -hex 32
# - DEMO_MODE=true (for local development)
# - Optional: ANTHROPIC_API_KEY (for Claude API access)

# View configuration
cat .env | grep -v "^#" | grep -v "^$"
```

## Step 3: Frontend setup

```bash
cd ../frontend

# Install dependencies
npm install

# Verify installation
npm list react react-dom  # Should show versions

# Build to check for TypeScript errors
npm run build
```

## Step 4: Database setup (Supabase)

### Start local Supabase

```bash
# From project root
supabase start

# Wait for startup (30-60 seconds)
# Should see output like:
# API URL: http://localhost:55321
# Database URL: postgresql://postgres:postgres@localhost:55322/postgres
```

### Verify database

```bash
# Check Supabase status
supabase status

# Access Studio (web UI) at http://localhost:55323
# Username: supabase
# Password: (shown in start output)

# Or connect directly via psql
psql postgresql://postgres:postgres@localhost:55322/postgres

# List tables
\dt

# Exit
\q
```

## Step 5: Pre-commit hooks

```bash
# Install pre-commit framework
pip install pre-commit

# Install hooks from config
pre-commit install

# Run all hooks to verify setup
pre-commit run --all-files

# Should pass with output like:
# trim trailing whitespace...Passed
# fix end of files...Passed
# check yaml...Passed
# etc.
```

## Step 6: Verification checklist

Run these checks to verify everything is working:

```bash
# 1. Backend imports
cd backend && source venv/bin/activate
python -c "import app; print('✓ Backend imports OK')" || exit 1

# 2. Backend server startup
./start-backend.sh &
sleep 3
curl -s http://localhost:9095/health | jq . || echo "❌ Backend health check failed"
kill %1

# 3. Frontend dependencies
cd ../frontend
npm list react react-dom | head -3 || exit 1

# 4. Frontend build
npm run build 2>&1 | tail -5 || exit 1

# 5. Database
supabase status | grep "API URL" || echo "❌ Supabase not running"

# 6. Git hooks
git status  # Should not show hook errors

echo "✓ All checks passed - ready to develop!"
```

## Starting development

### Open three terminals

**Terminal 1: Backend**
```bash
cd /opt/bms-intelligence/backend
source venv/bin/activate
./start-backend.sh
# Should see: "Uvicorn running on http://0.0.0.0:9095"
```

**Terminal 2: Frontend**
```bash
cd /opt/bms-intelligence/frontend
npm run dev
# Should see: "Local: http://localhost:9096"
```

**Terminal 3: Database (if needed)**
```bash
supabase status
# Verify all services running
```

### Access the application

- **Application**: http://localhost:9096
- **API**: http://localhost:9095 (Swagger docs at /docs)
- **Database Studio**: http://localhost:55323
- **API Status**: http://localhost:9095/health

## Environment configuration

### Backend .env file

Key environment variables:

```bash
# Required
DEMO_MODE=true                  # Use demo data instead of live
JWT_SECRET_KEY=<random-hex>    # Generate: openssl rand -hex 32

# Optional
ANTHROPIC_API_KEY=sk-...       # For Claude API calls
SUPABASE_URL=http://localhost:55321
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...

# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:55322/postgres

# Logging
LOG_LEVEL=INFO
```

### Frontend .env.local file

```bash
# API endpoint
VITE_API_URL=http://localhost:9095

# Auth
VITE_AUTH_REDIRECT_URI=http://localhost:9096/auth/callback

# Optional
VITE_DEBUG=true
```

## Troubleshooting

### Port conflicts

**Check port availability:**
```bash
# Find what's using a port
lsof -i :9095    # Backend port
lsof -i :9096    # Frontend port
lsof -i :55321   # Supabase API

# On Windows
netstat -ano | findstr :9095
```

**Kill existing process:**
```bash
kill $(lsof -t -i :9095)      # macOS/Linux
taskkill /PID <pid> /F        # Windows
```

**Use different port:**
```bash
# Backend (change in start-backend.sh)
uvicorn app.main:app --reload --port 9097

# Frontend (change in start-frontend.sh)
npm run dev -- --port 9097
```

### Virtual environment issues

**Corrupted venv:**
```bash
cd backend
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Python version mismatch:**
```bash
# Check Python version
python3 --version

# If < 3.11, use explicit version
python3.11 -m venv venv
source venv/bin/activate
```

**Activation not working:**
```bash
# bash/zsh
source venv/bin/activate

# fish
source venv/bin/activate.fish

# Windows cmd
venv\Scripts\activate.bat

# Windows PowerShell
venv/Scripts/Activate.ps1
```

### Node modules cache issues

**Module not found errors:**
```bash
cd frontend

# Clean install
rm -rf node_modules package-lock.json
npm cache clean --force
npm install

# Rebuild
npm run build
```

**TypeScript compilation fails:**
```bash
# Clear TypeScript cache
rm -rf node_modules/.tsc*
rm -rf node_modules/.vite
rm -rf tsconfig.tsbuildinfo

# Restart TypeScript server
# VS Code: Cmd+Shift+P → "TypeScript: Restart TS Server"
# WebStorm: File → Invalidate Caches
```

### Supabase connection issues

**Cannot connect to localhost:55321:**
```bash
# Check if running
docker ps | grep supabase

# Start if stopped
supabase start

# Wait for initialization (30-60 seconds)
sleep 30
supabase status
```

**Connection refused from backend:**
```bash
# Verify backend .env
grep SUPABASE_URL backend/.env

# Test direct connection
curl -s http://localhost:55321/rest/v1/ | head -5

# If failed, enable JSON fallback
echo "USE_JSON_STORAGE=true" >> backend/.env
```

### Pre-commit hook failures

**Hardcoded API key detected:**
- Move sensitive values to `.env` file
- Update code to use `os.getenv("KEY_NAME")`
- Commit `.env` to `.gitignore` (not tracked)

**File too large (>1000 KB):**
```bash
# Find large files
find . -size +1000k -type f | grep -v node_modules | grep -v venv

# Either: Remove unnecessary files, use Git LFS, or move outside repo
```

**Pre-commit hook blocks legitimate changes:**
```bash
# Use only when necessary:
git commit --no-verify

# Then fix the issue and commit properly
```

## Restarting after git pull

When pulling new changes, dependencies may have updated:

```bash
# Backend
cd backend && source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm ci  # Clean install (stricter than npm install)

# Database
supabase db push  # Apply any new migrations
```

## Performance debugging

### Backend logs

```bash
# Real-time log watching
tail -f backend.log

# Filter by severity
grep ERROR backend.log
grep WARNING backend.log

# Find slow endpoints
grep "duration=" backend.log | sort -k2 -rn | head -10
```

### Frontend performance

```bash
# Open DevTools (F12)
# Network tab: Check request sizes and times
# React Query tab: View cache status and requests
# Console: Check for errors
```

### Database queries

```bash
# Connect to database
psql postgresql://postgres:postgres@localhost:55322/postgres

# Count records in tables
SELECT tablename, count(*) FROM information_schema.tables
  WHERE table_schema='public' GROUP BY tablename;

# Find slow queries
SELECT query, calls, mean_time FROM pg_stat_statements
  ORDER BY mean_time DESC LIMIT 10;
```

## Demo mode vs live mode

### Demo mode (development)

- `DEMO_MODE=true` in `.env`
- No API calls to external services
- Pre-seeded data from JSON files
- Faster development cycles
- No API key requirements

```bash
echo "DEMO_MODE=true" >> backend/.env
./start-backend.sh
```

### Live mode (production)

- `DEMO_MODE=false`
- Real API calls to Claude, Supabase, etc.
- Requires valid API keys
- Production data

```bash
echo "DEMO_MODE=false" >> backend/.env
# Set API keys in .env
./start-backend.sh
```

## Next steps

1. **Run first test**: `pytest tests/ -m unit -v`
2. **Start development**: Open http://localhost:9096
3. **Read API docs**: Visit http://localhost:9095/docs
4. **Check code style**: `pre-commit run --all-files`
5. **Review architecture**: See [System Overview](../02-architecture/system-overview.md)

## Getting help

When troubleshooting, gather this information:

```bash
# System info
uname -a
python3 --version
node --version
npm --version

# Service status
ps aux | grep -E "uvicorn|vite|supabase"

# Recent errors
tail -50 backend.log | grep ERROR

# Git state
git status
git log --oneline -5
```

Include this context when asking for help in issues or discussions.

## References

- **Main documentation**: See [CLAUDE.md](../../CLAUDE.md) hub
- **Architecture**: [System Overview](../02-architecture/system-overview.md)
- **API reference**: http://localhost:9095/docs (when backend running)
- **Testing guide**: [Testing patterns and markers](../testing/testing-guide.md) (when available)
- **Backend README**: `backend/README.md`
- **Frontend README**: `frontend/README.md`
