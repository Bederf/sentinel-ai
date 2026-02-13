# Debugging Guide

**Common debugging scenarios with solutions.**

**See CLAUDE.md for quick reference. This document covers detailed troubleshooting procedures.**

## API & Backend Issues

**"API calls are slow"**
1. Check Network tab (F12): Look for batch endpoints (`/api/devices/batch`)
2. Run React Query DevTools (F12 → "React Query" tab)
3. Verify `queryClient.ts` stale times: site summary/alerts (15-30s), predictions (60s), buildings (5m)
4. Check `frontend/src/lib/api/batchers.ts` for deduplication logic
5. Profile endpoint: `python -m cProfile -s cumtime -m pytest tests/api/test_devices.py::test_get_device -v`
6. Find slow endpoints: `grep "duration=" backend.log | sort -t= -k2 -rn | head -10`

**"API returns 403 Forbidden"**
1. Check auth headers: Network tab → API request → Headers → Authorization bearer token
2. Verify token format: `Authorization: Bearer eyJ...`
3. Check token expiry: Decode JWT and check `exp` claim
4. Verify user has required auth level:
   - ADMIN > OPERATOR > AUTHENTICATED > PUBLIC
   - Read-only operations should use AUTHENTICATED
   - Control operations require OPERATOR
5. Check `backend/app/startup/middleware.py` for auth configuration
6. Try with different user: May be permission issue

**"Endpoint returns 500 Internal Server Error"**
1. Check backend logs: `tail -f backend.log` or `docker logs bms-backend`
2. Look for Python exception traceback
3. Verify database connection: `SELECT 1` in studio.supabase.co
4. Check for circular imports: `python -c "from app.api import *"`
5. Add logging to endpoint and restart backend
6. Check `.env` variables are set correctly (SUPABASE_URL, API_KEY, etc.)

**"Database connection fails"**
1. Verify Supabase running: `supabase status`
2. Check ports: API should be 55321, DB should be 55322
3. Test connection: `psql postgresql://postgres:postgres@localhost:55322/postgres -c "SELECT 1"`
4. Check `.env` has SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
5. Set USE_JSON_STORAGE=true to force JSON fallback
6. Verify service role key starts with `eyJ` (JWT)

## Frontend & TypeScript Issues

**"TypeScript won't compile"**
1. Run `npm ci` (fresh install of exact versions)
2. Clear all caches: `rm -rf node_modules/.vite node_modules/.tsc*`
3. Restart IDE/TypeScript language server (Restart VS Code)
4. Verify `verbatimModuleSyntax: true` in `tsconfig.app.json`
5. Check all imports use barrel export: `from '@/lib/api'` not `from '@/lib/api/devices'`
6. Run `npm run build` to see full error messages

**"Module has no exported member 'X'"**
1. Verify export in source file: Check `frontend/src/lib/api/index.ts` has re-export
2. Run `npm ci` (cache issue)
3. Clear cache: `rm -rf node_modules/.vite node_modules/.tsc*`
4. Check barrel export: `frontend/src/lib/api/index.ts` should have `export * from './devices'`
5. Restart TypeScript language server

**"React Query data is stale"**
1. Check React Query DevTools (F12 → "React Query" tab)
2. See stale time for query: Should be 15-60s for dynamic data
3. See last updated time: If stale, may need to refetch
4. Trigger manual refetch: DevTools has "Refetch" button
5. Check hook stale time: `staleTime: 15 * 1000` in hook definition
6. Verify no global caching preventing updates

**"Component won't re-render after data update"**
1. Check React DevTools (F12 → "Components" tab)
2. Verify hook is being called: Should see query key in React Query tab
3. Check for stable dependency array issues: `useEffect` may not refetch
4. Verify data is actually changing: Add `console.log(data)` in component
5. Check React Query cache: May be using stale data from cache

## Database & Supabase Issues

**"Supabase connection fails"**
1. Check if Supabase local is running: `supabase status`
2. Verify ports are available: `lsof -i :55321` (API), `lsof -i :55322` (DB)
3. Kill port if needed: `kill -9 $(lsof -t -i :55321)`
4. Restart Supabase: `supabase stop && supabase start`
5. Check Docker running: `docker ps` should show postgres, api containers
6. Check `.env` has valid SUPABASE_URL: Should be `http://localhost:55321`

**"Predictions not appearing on dashboard"**
1. Verify alert exists → triggers equipment health_score persistence
   - Query: `SELECT code, health_score FROM equipment WHERE health_score IS NOT NULL`
   - Should have health_score = 30 (critical), 60 (warning), or 85 (normal)
2. Check health_score is persisted: Query at studio.supabase.co
3. Prediction engine runs every 5 minutes querying `equipment.health_score < 90`
4. If no health_score persisted, create alert to trigger persistence
5. Manually trigger prediction: `GET http://localhost:9095/api/predictions/site/S002?include_all=false`

**"Equipment health_score not updating"**
1. Create test alert: 
   ```bash
   curl -X POST "http://localhost:9095/api/alerts/supabase" \
     -H "Content-Type: application/json" \
     -d '{"equipment_code":"S002-CHILLER-B1-001","severity":"critical"}'
   ```
2. Check alert created: Query `SELECT * FROM alerts WHERE equipment_code = 'S002-CHILLER-B1-001'`
3. Verify trigger fired: `SELECT code, health_score FROM equipment WHERE code = 'S002-CHILLER-B1-001'`
4. If health_score not updated, check database trigger exists
5. Manually update: `UPDATE equipment SET health_score = 60 WHERE code = 'S002-CHILLER-B1-001'`

**"Query returns empty results"**
1. Verify table has data: `SELECT COUNT(*) FROM equipment`
2. Check column names: `SELECT column_name FROM information_schema.columns WHERE table_name='equipment'`
3. Verify WHERE clause: Try `SELECT * FROM equipment LIMIT 1`
4. Check for NULL values: May be filtering them out
5. Use studio.supabase.co to test query directly
6. Check RLS (Row Level Security) policies: May be filtering rows

**"Foreign key constraint violation"**
1. Verify referenced table/row exists: `SELECT * FROM equipment WHERE id = '...'`
2. Check foreign key definition: `SELECT * FROM pg_constraint WHERE table_name='work_orders'`
3. Verify correct column referenced: Should be `equipment(id)` not `equipment(equipment_id)`
4. Insert referenced row first before inserting dependent row
5. Check constraint is active: `SELECT constraint_name FROM information_schema.table_constraints WHERE table_name='work_orders'`

## Common Patterns & Solutions

### Timeout Issues (30s per test)

```bash
# Find slow tests
pytest tests/ --durations=10

# Mark long test as slow, run separately
@pytest.mark.slow
async def test_lifecycle_simulation():
    ...

# Run only fast tests
pytest -m "not slow" tests/
```

### Port Conflicts

```bash
# Check what's using port 9095
lsof -i :9095

# Kill process (if needed)
kill -9 $(lsof -t -i :9095)

# Start backend on different port
VITE_PORT=9090 ./start-backend.sh
```

### Virtual Environment Issues

```bash
# Reset venv completely
rm -rf backend/venv
python -m venv backend/venv
source backend/venv/bin/activate
pip install -r backend/requirements.txt

# Verify correct Python
which python  # Should show backend/venv/bin/python
```

### npm Cache Issues

```bash
# Clear all npm caches
npm cache clean --force
rm -rf frontend/node_modules frontend/package-lock.json

# Fresh install
npm install

# Or use clean install
npm ci
```

## Using GSD for Systematic Debugging

For complex issues, use GSD debug skill:
```bash
gsd:debug
# Follow systematic investigation steps
# Tests hypothesis about root cause
# Proposes targeted fixes
```

## Profiling & Performance Analysis

### Memory Profiling
```bash
pip install memory-profiler
python -m memory_profiler backend/app/api/devices.py
```

### CPU Profiling
```bash
python -m cProfile -s cumtime -m pytest tests/api/test_devices.py -v
```

### Query Performance
```bash
# Enable query logging in Supabase
# View execution plans
psql postgresql://postgres:postgres@localhost:55322/postgres
\d+ equipment  # Show indexes
EXPLAIN ANALYZE SELECT * FROM equipment WHERE code = '...';
```

## Log Analysis Tips

### Find Errors in Backend Logs
```bash
tail -f backend.log | grep -i "error\|exception\|traceback"
```

### Find Slow Endpoints
```bash
grep "duration=" backend.log | sort -t= -k2 -rn | head -10
```

### Find Authentication Failures
```bash
grep -i "auth\|401\|403" backend.log
```

### Real-time Log Monitoring
```bash
# Docker logs
docker logs -f bms-backend --tail 100

# Local development
tail -f backend.log
```

## Related Documents

- **Development Patterns:** `docs/DEVELOPMENT_PATTERNS.md` - Code patterns and constraints
- **Approval Workflow:** `docs/APPROVAL_WORKFLOW.md` - Approval system troubleshooting
- **Peak Demand:** `docs/PEAK_DEMAND_COORDINATION.md` - Demand coordination issues
- **Equipment Naming:** `docs/EQUIPMENT_NAMING.md` - Naming/identification issues
- **Local Setup:** `CLAUDE_LOCAL_SETUP.md` - Initial setup troubleshooting
