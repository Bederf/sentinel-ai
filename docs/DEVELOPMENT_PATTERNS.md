# Development Patterns & Essential Constraints

**See CLAUDE.md for quick reference. This document covers detailed pattern explanations.**

## Async Functions (Critical)

**No blocking IO in async functions.** Use `httpx` with `await` for all HTTP calls (never `requests`).

```python
# ❌ WRONG - blocks event loop
async def get_data():
    import requests
    response = requests.get("...")  # BLOCKS!

# ✅ CORRECT
async def get_data():
    async with httpx.AsyncClient() as client:
        response = await client.get("...")  # Async!
```

**Why?** FastAPI runs on async event loop. Blocking calls freeze the entire server for all requests.

## TypeScript/React

### Type-Only Imports (verbatimModuleSyntax enforced)

Strict separation required:
```typescript
// ✅ CORRECT: Separate type and value imports
import { devicesApi, authorizedFetch } from '@/lib/api'
import type { Device, Site } from '@/lib/api'

// ❌ WRONG: Mixing types and values
import { devicesApi, type Device } from '@/lib/api'
```

**Why?** `verbatimModuleSyntax: true` in tsconfig enforces this. Prevents accidental runtime imports of type-only code.

### Path Alias Convention

Always use `@/` prefix:
```typescript
// ✅ CORRECT
import { devicesApi } from '@/lib/api'
import { Dashboard } from '@/components/Dashboard'

// ❌ WRONG
import { devicesApi } from '../lib/api'
import { Dashboard } from '../../components/Dashboard'
```

### Prediction Severity Enum

Use consistent severity levels:
```typescript
// ✅ CORRECT - use these exact strings
type Severity = "critical" | "warning" | "healthy"

// ❌ WRONG - don't use high/medium/low
type Severity = "high" | "medium" | "low"  // WRONG!
```

### Side Effects in useEffect

Never initialize state with side effects:
```typescript
// ❌ WRONG - effect runs during render
const [data, setData] = useState(() => {
  fetchData();  // Blocks render
  return null;
});

// ✅ CORRECT - effect runs after render
useEffect(() => {
  const load = async () => {
    const result = await fetchData();
    setData(result);
  };
  load();
}, []);
```

### React Query Hook Usage

Never bypass custom hooks:
```typescript
// ❌ WRONG - direct API call
function MyComponent() {
  const [data, setData] = useState(null);
  useEffect(() => {
    devicesApi.getAll().then(setData);  // No caching!
  }, []);
}

// ✅ CORRECT - uses React Query hook
function MyComponent() {
  const { data } = useDevices();  // Automatic caching, deduplication
}
```

## Database (Supabase)

### Foreign Key References

Equipment table structure:
```sql
-- ✅ CORRECT
ALTER TABLE work_orders ADD CONSTRAINT fk_equipment 
  FOREIGN KEY (equipment_id) REFERENCES equipment(id);

-- ❌ WRONG
ALTER TABLE work_orders ADD CONSTRAINT fk_equipment 
  FOREIGN KEY (equipment_id) REFERENCES equipment(equipment_id);
```

**Why?** Equipment uses UUID `id` as primary key, not `equipment_id`.

### TEXT[] Arrays

Use PostgreSQL syntax, not JSON:
```sql
-- ✅ CORRECT
INSERT INTO equipment (tags) VALUES (ARRAY['hvac', 'critical']);

-- ❌ WRONG
INSERT INTO equipment (tags) VALUES ('["hvac","critical"]'::TEXT[]);
```

### PL/pgSQL Blocks

Use `$$` delimiter:
```sql
-- ✅ CORRECT
CREATE FUNCTION update_health() RETURNS void AS $$
BEGIN
  UPDATE equipment SET health_score = 85;
END
$$ LANGUAGE plpgsql;

-- ❌ WRONG
CREATE FUNCTION update_health() RETURNS void AS \$\$
BEGIN
  UPDATE equipment SET health_score = 85;
END
\$\$;
```

## Python Gotchas

### dict.get() with None Values

Use `or` for defaults when Supabase fields can be explicitly None:
```python
# ✅ CORRECT - handles explicit None
data = supabase_record.get("field") or "default_value"
# If field=None, use "default_value"
# If field="", use ""

# ❌ WRONG - default ignored when field=None
data = supabase_record.get("field", "default_value")
# If field=None, uses None (not the default!)
```

### DeviceManager Initialization

Always initialize before use in tests:
```python
# ✅ CORRECT
from backend.app.services.device_manager import ensure_device_manager_initialized

@pytest.mark.asyncio
async def test_device_control():
    await ensure_device_manager_initialized()
    device = device_manager.get_device("S002-DALI-101")

# ❌ WRONG - device_manager may be uninitialized
async def test_device_control():
    device = device_manager.get_device("S002-DALI-101")  # May fail!
```

### Circular Dependencies

No circular imports between routers:
```python
# ✅ CORRECT - use dependency injection
from backend.app.services import device_service

async def get_device(equipment_id: str):
    return await device_service.get_device(equipment_id)

# ❌ WRONG - circular import risk
from backend.app.api import other_router  # May import this router!
```

## API Organization

### Registrar Pattern

```python
# backend/app/startup/routes.py
def register_core_routers(app):
    """Core domain routers"""
    from app.api import auth, settings, sites, health
    app.include_router(auth.router)
    app.include_router(settings.router)
    app.include_router(sites.router)
    app.include_router(health.router)

# ✅ CORRECT: More specific routes first
def register_building_routers(app):
    app.include_router(sites_aggregation.router)  # /api/sites/summary/* (specific)
    app.include_router(sites.router)              # /api/sites/* (general)

# ❌ WRONG: General route would shadow specific ones
def register_building_routers(app):
    app.include_router(sites.router)              # Matches /api/sites/*
    app.include_router(sites_aggregation.router)  # Never reached!
```

**Why?** FastAPI matches routes in registration order. Specific routes must come first.

## Repository Pattern

### Supabase with JSON Fallback

```python
# ✅ CORRECT - uses repository fallback
equipment = await equipment_repo.get_by_code("S002-CHILLER-B1-001")
# Uses Supabase if available, falls back to JSON

# ❌ WRONG - bypasses fallback
data = await supabase.table("equipment").select("*")
# Fails if Supabase unavailable
```

### Repository Initialization

All repositories auto-initialize:
```python
# ✅ CORRECT - auto-initialize on first call
equipment = await equipment_repo.get_by_code("S002-CHILLER-B1-001")

# ❌ WRONG - don't manually initialize
await equipment_repo.initialize()  # Not needed!
```

## Testing Patterns

### Async Test Structure

```python
# ✅ CORRECT
import pytest

@pytest.mark.asyncio
async def test_approval_workflow():
    # Arrange
    mock_device_manager = AsyncMock()
    mock_device_manager.set_value.return_value = {"success": True}
    
    # Act
    result = await approval_service.execute_approval(...)
    
    # Assert
    assert result.success is True

# ❌ WRONG - missing pytest.mark.asyncio
async def test_approval_workflow():  # Will timeout/fail!
    result = await approval_service.execute_approval(...)
```

### Mock Objects

```python
# ✅ CORRECT - use AsyncMock for async functions
from unittest.mock import AsyncMock

mock_repo = AsyncMock()
mock_repo.get_by_id.return_value = {"id": "123", "name": "Test"}

# ❌ WRONG - MagicMock doesn't handle async
mock_repo = MagicMock()  # Won't work with await!
```

## Performance Patterns

### React Query Stale Times

```typescript
// ✅ CORRECT - appropriate stale times
const { data: demand } = useQuery({
  queryKey: ['demand-status'],
  queryFn: () => peakDemandApi.getStatus(),
  staleTime: 15 * 1000,  // 15s - demand changes frequently
});

const { data: buildings } = useQuery({
  queryKey: ['buildings'],
  queryFn: () => sitesApi.getBuildings(),
  staleTime: 5 * 60 * 1000,  // 5m - rarely changes
});

// ❌ WRONG - stale times too long/short
const { data: demand } = useQuery({
  queryKey: ['demand-status'],
  queryFn: () => peakDemandApi.getStatus(),
  staleTime: 60 * 1000,  // Too long! Will miss updates
});
```

### Batch Aggregators

```typescript
// ✅ CORRECT - batches multiple calls
const devices = await devicesApi.batch(['device1', 'device2', 'device3']);
// Makes 1 HTTP request instead of 3

// ❌ WRONG - individual calls
const d1 = await devicesApi.get('device1');
const d2 = await devicesApi.get('device2');
const d3 = await devicesApi.get('device3');  // 3 HTTP requests!
```

## File Size Constraints

- **Backend files:** Max 500 lines (ESLint: max-lines)
- **Frontend functions:** Max 50 lines (ESLint: max-lines-per-function)
- **CLAUDE.md:** Max 40k characters (split into docs/)

**Why?** Prevents cognitive overload, easier to test, faster refactoring.

## Code Organization Rules

### Backend

- New routers go in `api/{domain}.py`
- Register in appropriate registrar (`api/registrars/{registrar}.py`)
- Business logic in `services/`, never in API handlers
- All async functions use `httpx` + `await`
- Repositories follow fallback pattern: Supabase → JSON

### Frontend

- Data fetching through custom hooks only
- Component-specific styling (no global CSS)
- Type definitions imported from `lib/api`
- 3D components use React Three Fiber, in `components/3d/`

## Common Patterns - Security

### Don't Skip Approval Workflow

```python
# ❌ WRONG - bypasses approval and safety checks
await device_manager.set_value(equipment_id, point, value)

# ✅ CORRECT - routes through safety validation
result = await approval_service.execute_approval(
    recommendation_id="rec-123",
    approved_by="operator@site",
    approval_notes="Peak demand response"
)
```

### Always Validate at Boundaries

```python
# ✅ CORRECT - validate user input
@app.post("/api/device/set")
async def set_device(request: SetDeviceRequest):
    # Pydantic validates request automatically
    return await device_service.set_value(request.equipment_id, request.value)

# ❌ WRONG - trust untrusted input
@app.post("/api/device/set")
async def set_device(data: dict):
    return await device_service.set_value(data['equipment_id'], data['value'])
```
