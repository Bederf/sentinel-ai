# CLAUDE Quick Start

**Quick reference for daily development commands.** See `CLAUDE.md` for comprehensive documentation.

## One-Time Setup

```bash
# Backend
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt && cp .env.example .env

# Frontend
cd frontend && npm install

# Supabase (local, includes migrations)
supabase start
```

## Start Services (Open 3 terminals)

```bash
# Terminal 1: Backend (http://localhost:9095)
./start-backend.sh

# Terminal 2: Frontend (http://localhost:9096)
./start-frontend.sh

# Terminal 3: Monitor logs (optional)
tail -f backend.log
```

**Verify:**
- Backend: `curl http://localhost:9095/health`
- Frontend: `http://localhost:9096`
- API docs: `http://localhost:9095/docs`

## Daily Commands

### Run Tests

```bash
# Backend - all required tests before commit
pytest -m security tests/api/ -v        # REQUIRED before commit
pytest -m unit tests/                   # Unit tests (fast)
pytest tests/api/test_devices.py -v    # Single file
pytest tests/api/test_devices.py::test_name -v  # Single test
pytest tests/ --durations=10            # Find slow tests

# Frontend - enforces 80% coverage
npm run test:run                        # Single run (CI mode)
npm run test:watch                      # Watch mode
npm run test:ui                         # Interactive UI (recommended)
npm run test:coverage                   # Coverage report
```

### Linting & Building

```bash
# Backend
ruff check backend/ --select E,F        # Lint check
ruff format backend/                    # Auto-format

# Frontend
npm run lint                            # ESLint check
npm run build                           # TypeScript compile + bundle
tsc --noEmit                            # Type check only (faster)
```

### Database

```bash
# Apply migrations to local Supabase
supabase db push

# Sync local schema to repo
supabase db pull

# Reset local Supabase (caution: loses data)
supabase db reset

# View local database (opens Studio at http://localhost:54323)
supabase status
```

### Common Workflows

```bash
# Test lifecycle simulation (24 hours in 5 minutes)
curl -X POST http://localhost:9095/api/lifecycle/demo/quick-cycle \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"site_id": "site-002", "scenario": "fault_day"}'

# Check MFA status
curl http://localhost:9095/api/mfa/status \
  -H "Authorization: Bearer $TOKEN"

# Create alert for testing
curl -X POST http://localhost:9095/api/alerts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"equipment_id": "uuid", "severity": 75}'

# Flush Redis cache (if enabled)
curl -X POST http://localhost:9095/api/cache/flush \
  -H "Authorization: Bearer $TOKEN"
```

## Pre-Commit Checklist

```bash
# Run ALL of these before pushing:

# 1. Backend security tests (REQUIRED)
pytest -m security tests/api/ -v

# 2. Backend linting
ruff check backend/ --select E,F
pytest tests/ --durations=10  # Check for >30s timeouts

# 3. Frontend linting & tests
npm run lint
npm run test:run              # Must pass 80% coverage
npm run build                 # Must compile without errors

# 4. Commit with conventional format
git commit -m "type(scope): description"
# Types: fix|feat|refactor|test|docs|perf
# Example: git commit -m "fix(alerts): prevent duplicate notifications"
```

## Troubleshooting

| Problem | Quick Fix |
|---------|-----------|
| Backend won't start | Check port 9095: `lsof -i :9095` \| Kill: `kill -9 <pid>` |
| Frontend build fails | `npm ci && rm -rf node_modules/.vite && npm run build` |
| Type errors in TypeScript | `tsc --noEmit` (faster than full build) |
| Supabase connection fails | `supabase status` → check API/DB running on 55321/55322 |
| Redis not caching | Verify `REDIS_ENABLED=true` in `.env` and `redis-cli ping` returns PONG |
| "Module not found" | `npm ci` + clear `.vite` cache + restart IDE |
| Tests timeout | Check if test has `@pytest.mark.slow` (>5 seconds) |
| Circular import errors | Check `backend/app/api/registrars/` router registration order |
| Device control fails | Verify `DEMO_MODE=true` in `.env` (enables mock devices) |

## Development Workflow Examples

### Add a New API Endpoint

```bash
# 1. Create endpoint in backend/app/api/{domain}.py
# 2. Register in backend/app/api/registrars/{registrar}.py
# 3. Test: pytest tests/api/test_{domain}.py::test_name -v
# 4. Add frontend client in frontend/src/lib/api/{domain}.ts
# 5. Export from barrel: frontend/src/lib/api/index.ts
# 6. Use in component via React Query hook
# 7. Test component & coverage: npm run test:ui
```

### Deploy Database Change

```bash
# 1. Create migration: touch supabase/migrations/$(date +%s)_description.sql
# 2. Write SQL: CREATE TABLE... or ALTER TABLE...
# 3. Apply locally: supabase db push
# 4. Verify schema: supabase db pull
# 5. Create repo class: backend/app/database/repositories/{table}_repository.py
# 6. Add endpoint using new repository
# 7. Test: pytest tests/api/test_{domain}.py -v
```

### Fix TypeScript Compilation Error

```bash
# 1. Check errors: npm run build
# 2. Type check only: tsc --noEmit
# 3. If cache issue: rm -rf node_modules/.tsc* node_modules/.vite
# 4. Reinstall: npm ci
# 5. Retry: tsc --noEmit
```

## Project Structure Quick Reference

```
backend/
  ├── app/api/              # 70+ routers (organized by domain)
  ├── app/services/         # Business logic (30+ services)
  ├── app/database/         # Repositories + Supabase fallback
  ├── app/ml/               # ML models, predictions
  ├── tests/                # pytest tests
  └── requirements.txt      # Python dependencies

frontend/
  ├── src/lib/api/          # API clients (barrel export in index.ts)
  ├── src/components/       # React components
  ├── src/hooks/            # Custom hooks (React Query only)
  ├── src/__tests__/        # Test files
  └── package.json          # npm dependencies

supabase/
  └── migrations/           # SQL migrations (applied via db push)

docs/
  ├── 02-architecture/      # System design docs
  └── 05-integration/       # Integration guides (Clawd, SIMBIOT, etc.)
```

## Session Memory

Project-specific knowledge from past sessions is auto-loaded:
- **Location:** `/home/bederf/.claude/projects/-opt-bms-intelligence/memory/MEMORY.md`
- **Contains:** Phase status, equipment registry, lessons learned, architecture decisions
- **Use:** Refer to when working on related phases or equipment modifications

## Service Ports

| Service | Port | Use |
|---------|------|-----|
| Backend | 9095 | API endpoint |
| Frontend | 9096 | Web UI |
| Supabase API | 55321 | Database REST API |
| Supabase DB | 55322 | PostgreSQL |
| Redis | 6379 | Query caching (optional) |
| Ollama | 11434 | LLM inference (optional) |

## Configuration

**Backend `.env`:**
```bash
DEMO_MODE=true                    # Skip auth, use mock data (fastest for local dev)
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
USE_JSON_STORAGE=false            # True = force JSON fallback (Supabase down)
REDIS_ENABLED=true                # Query caching
JWT_SECRET_KEY=<32-char hex>      # Generate: openssl rand -hex 32
```

**Frontend `.env.development`:**
```bash
VITE_API_URL=http://localhost:9095
```

## Links

- **API Docs (Swagger):** `http://localhost:9095/docs`
- **Comprehensive Guide:** `CLAUDE.md`
- **Architecture Details:** `docs/02-architecture/`
- **Integration Guides:** `docs/05-integration/`
- **Test Documentation:** `docs/PHASE_68_TESTING_COMPLETE.md`
- **Approval Workflow:** `docs/APPROVAL_WORKFLOW.md`
- **Equipment Naming:** `docs/EQUIPMENT_NAMING.md`

---

**Pro Tip:** Bookmark `http://localhost:9095/docs` for live API testing during development.
