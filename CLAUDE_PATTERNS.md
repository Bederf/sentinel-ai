# CLAUDE_PATTERNS.md

Essential code patterns, constraints, and best practices.

## Critical Constraints (Enforce These)

### 1. Async Functions: NO Blocking IO

**WRONG - Blocks event loop, crashes under load:**
```python
async def fetch_data():
    import requests
    response = requests.get("https://...")  # ❌ BLOCKS
    return response.json()
```

**CORRECT - Non-blocking:**
```python
async def fetch_data():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://...")  # ✅ ASYNC
        return response.json()
```

**Rule:** If function is `async`, ALL I/O must be `await httpx` or similar. Never use `requests`, `sqlite3`, `open()`, etc. inside async functions.

### 2. React Imports: Type-Only Separated

**WRONG - Violates verbatimModuleSyntax:**
```typescript
// ❌ DON'T DO THIS
import { devicesApi, type Device } from '@/lib/api'
```

**CORRECT - Type imports separated:**
```typescript
// ✅ DO THIS
import { devicesApi } from '@/lib/api'
import type { Device } from '@/lib/api'
```

**Why:** `tsconfig.json` has `verbatimModuleSyntax: true`. Mixing runtime and type imports breaks tree-shaking.

### 3. Device Control: Always Through SafetyEngine

**WRONG - Bypasses safety:**
```python
# ❌ DON'T DO THIS
await device_manager.write_property(device_id, property, value)
```

**CORRECT - Safety-validated:**
```python
# ✅ DO THIS
from app.services.approval_service import ApprovalService
result = await ApprovalService.execute_approval(recommendation_id)
# Behind the scenes: SafetyEngine validates, then device_manager writes
```

**Flow:** ApprovalService → SafetyEngine → DeviceManager

### 4. Supabase: Always Use Repositories

**WRONG - Bypasses fallback:**
```python
# ❌ DON'T DO THIS
data = await supabase.table("equipment").select("*").execute()
```

**CORRECT - Uses fallback automatically:**
```python
# ✅ DO THIS
from app.database.repositories.equipment_repository import EquipmentRepository
repo = EquipmentRepository()
equipment = await repo.list()
# Automatically falls back to JSON if Supabase down
```

**Why:** Repositories handle fallback to JSON files automatically. Direct queries don't.

### 5. React Query: No Direct Fetching in Components

**WRONG - Fetching in component:**
```typescript
// ❌ DON'T DO THIS
function MyComponent() {
  const [data, setData] = useState(null)
  useEffect(() => {
    devicesApi.getDevices().then(setData)
  }, [])
  return <div>{data}</div>
}
```

**CORRECT - Use custom hook:**
```typescript
// ✅ DO THIS
function MyComponent() {
  const { data } = useDevices()  // Custom hook with React Query
  return <div>{data}</div>
}

// Hook:
export function useDevices() {
  return useQuery({
    queryKey: ['devices'],
    queryFn: devicesApi.getDevices,
    staleTime: 30_000,
  })
}
```

**Why:** React Query handles caching, deduplication, and stale times.

## Python Patterns

### Dict.get() Gotcha: Explicit None

```python
# When Supabase field is explicitly None:
value = data.get("field") or "default"  # ✅ CORRECT
value = data.get("field", "default")    # ❌ WRONG (None doesn't use default)

# Example:
user = {"name": None, "age": 25}
name = user.get("name") or "Unknown"    # Returns "Unknown" ✅
name = user.get("name", "Unknown")      # Returns None ❌
```

### Pydantic v2: @field_validator

```python
# ❌ WRONG - v1 syntax
from pydantic import validator

class Device(BaseModel):
    name: str
    @validator('name')
    def name_not_empty(cls, v):
        if not v:
            raise ValueError('Name required')
        return v

# ✅ CORRECT - v2 syntax
from pydantic import field_validator

class Device(BaseModel):
    name: str
    @field_validator('name')
    @classmethod
    def name_not_empty(cls, v):
        if not v:
            raise ValueError('Name required')
        return v
```

### Circular Imports: Use Dependency Injection

**WRONG - Circular import:**
```python
# api/routers/devices.py
from api.routers import alerts  # ❌ Circular if alerts imports devices

# alerts.py
from api.routers import devices  # ❌ Circular!
```

**CORRECT - Inject dependency:**
```python
# api/routers/devices.py
async def control_device(device_id: str, alert_service = Depends(get_alert_service)):
    # Use injected service, no import needed
    await alert_service.create_alert(device_id)

# In registrars/
def register_building_routers(app: FastAPI):
    app.include_router(devices.router)
    app.include_router(alerts.router)
    # No circular imports
```

### Async Context Managers

```python
# ✅ CORRECT - Resource cleanup guaranteed
async with httpx.AsyncClient() as client:
    response = await client.get("https://...")
# Client closed automatically

# ❌ WRONG - Resource leak if exception occurs
client = httpx.AsyncClient()
response = await client.get("https://...")
await client.aclose()  # Never reached if exception
```

## TypeScript Patterns

### Custom React Query Hook Pattern

```typescript
// frontend/src/hooks/useDeviceSafetyStatus.ts

export function useDeviceSafetyStatus(deviceId: string) {
  return useQuery({
    queryKey: ['device-safety', deviceId],
    queryFn: () => devicesApi.getSafetyStatus(deviceId),
    staleTime: 15_000,      // Refetch after 15s
    gcTime: 5 * 60_000,     // Keep in memory 5m after last use
    retry: 2,               // Retry failed requests 2x
    enabled: !!deviceId,    // Disable if no ID
  })
}

// In component:
const { data, isLoading, error } = useDeviceSafetyStatus('device-123')
```

### Type-Safe API Client

```typescript
// frontend/src/lib/api/devices.ts

export const devicesApi = {
  getSafetyStatus: (deviceId: string) =>
    client.get<SafetyStatus>(`/api/devices/${deviceId}/safety-status`),

  batchSafetyStatus: (ids: string[]) =>
    client.post<SafetyStatus[]>('/api/devices/batch/safety-status', { ids }),
}

// ✅ Type-safe when imported:
import { devicesApi } from '@/lib/api'
const status = await devicesApi.getSafetyStatus('...')  // Type: SafetyStatus
```

### Barrel Export Pattern

```typescript
// frontend/src/lib/api/index.ts

export * from './devices'
export * from './alerts'
export * from './approvals'
export type * from './models'

// Import from barrel everywhere:
import { devicesApi, alertsApi } from '@/lib/api'
import type { Device, Alert } from '@/lib/api'
```

### useEffect Dependencies

```typescript
// ❌ WRONG - Missing dependency, stale closure
function MyComponent({ deviceId }) {
  useEffect(() => {
    fetchData(deviceId)  // deviceId not in deps
  }, [])  // ❌ Will use old deviceId if prop changes
}

// ✅ CORRECT
function MyComponent({ deviceId }) {
  useEffect(() => {
    fetchData(deviceId)
  }, [deviceId])  // ✅ Refetch if deviceId changes
}
```

## Equipment Naming (Two-Tier System)

### Tier 1: Zone Equipment (Offices)

```
Pattern: {site}-{type}-{zone_id}
Example: S002-VAV-101
Meaning: Site S002 | VAV unit | Zone 101 (Level 1, Zone B)

Zone Numbering:
  001-099 = Level 0 (Ground floor)
  100-199 = Level 1
  200-299 = Level 2

Types: VAV, FCU, DALI, LUM, SPLIT
```

### Tier 2: Plant Equipment (Infrastructure)

```
Pattern: {site}-{type}-{location}-{sequence}
Example: S002-CHILLER-B1-001
Meaning: Site S002 | CHILLER | Basement 1 | Unit 001

Locations: B1, R (Roof), G (Ground), L1-L9 (multi-floor)

Types: CHILLER, AHU, GEN, UPS, PUMP, MTR, CT, TX
```

### Equipment Type → Technician Specialty

```
HVAC:       CHILLER, AHU, FCU, VAV, SPLIT, CT, CRAC, PUMP
DALI:       DALI, LUM
Electrical: GEN, TX, UPS, ATS, MSB, MTR, PFC, FDR, MV, DB
Fire:       FIRE
Security:   ACC, CCTV
```

## Health Score Lifecycle

```
Initial State: 100 (brand new)

Factors That Lower:
  - Fault detected: -5 to -50 (magnitude-based)
  - Age: Slow degradation
  - Service failure: -3
  - Safety violations: -1 each

Factors That Raise:
  - Successful service: +2 (positive feedback)
  - Neutral service: +0
  - Bad service: -3
  - Critical failure: -5
  - Preventive maintenance: +3

Thresholds:
  80-100: Healthy (green)
  50-79:  Warning (yellow) ← Creates work order
  0-49:   Critical (red)   ← Escalates
```

## Error Handling Patterns

### Backend: Raise HTTPException

```python
# ✅ CORRECT - Returns proper HTTP response
from fastapi import HTTPException

if not device:
    raise HTTPException(status_code=404, detail="Device not found")

if not authorized:
    raise HTTPException(status_code=403, detail="Access denied")
```

### Frontend: Handle in Hook

```typescript
// ✅ CORRECT - Error handled in custom hook
export function useDevices() {
  const { data, error, isLoading } = useQuery({...})

  // Caller gets error automatically
  return { data, error, isLoading }
}

// In component:
const { data, error } = useDevices()
if (error) return <div>Error: {error.message}</div>
```

## Testing Patterns

### Backend: Async Test

```python
# ✅ CORRECT - pytest handles async automatically
@pytest.mark.asyncio
async def test_get_devices():
    from app.services.device_service import DeviceService
    service = DeviceService()

    devices = await service.list()
    assert len(devices) > 0
```

### Frontend: Component Test

```typescript
// ✅ CORRECT - Test utilities auto-wrap with providers
import { render, screen } from '@testing-library/react'
import { MyComponent } from '../MyComponent'

it('renders device name', async () => {
  render(<MyComponent deviceId="123" />)
  await screen.findByText(/device name/i)
})
```

## Common Gotchas

| Issue | Solution |
|-------|----------|
| "Module not found" (Python) | Check import path; use `from app.services...` not `from services...` |
| TypeScript circular imports | Use dependency injection or reorganize modules |
| React Query not caching | Check `staleTime` is set; verify `gcTime` (default 5m) |
| Device control fails silently | Check SafetyEngine rules; inspect audit log |
| Health score not updating | Verify feedback submission reached service; check status='data_collection' |
| Batch aggregation not working | Ensure all hooks mount within 50ms window; check Network tab |
| Async test timeout | Mark test with `@pytest.mark.slow` if >5 seconds |

---

See `CLAUDE_QUICK_START.md` for common commands and troubleshooting.
