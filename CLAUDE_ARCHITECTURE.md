# CLAUDE_ARCHITECTURE.md

Detailed architecture, design patterns, and system organization.

## Backend Architecture

### Monorepo Structure

```
/opt/bms-intelligence/
├── backend/                    # FastAPI application
│   ├── app/                    # Main package (import as: from app.*)
│   │   ├── main.py             # FastAPI entry point
│   │   ├── startup/            # Routes registration & lifecycle
│   │   │   ├── events.py        # Startup: background jobs, MCP init
│   │   │   ├── routes.py        # 4-registrar pattern
│   │   │   └── middleware.py    # CORS, auth, logging
│   │   ├── api/                 # 70+ routers by domain
│   │   │   ├── registrars/      # 4 registrars organize routers
│   │   │   │   ├── core.py      # Auth, health, sites, cache
│   │   │   │   ├── building.py  # Equipment, devices, zones
│   │   │   │   ├── operations.py # Work orders, alerts, integrations
│   │   │   │   └── analytics.py # Chat, ML, optimization, MCP
│   │   │   ├── {domain}.py      # Individual routers
│   │   │   └── dependencies/    # Shared dependencies
│   │   ├── services/            # Business logic (30+ services)
│   │   │   ├── ai_optimizer.py           # AI recommendations
│   │   │   ├── approval_service.py       # Tier 2 device control
│   │   │   ├── device_abstraction.py     # Protocol-agnostic control
│   │   │   ├── safety_interlocks.py      # Safety validation
│   │   │   ├── background_scheduler.py   # APScheduler jobs
│   │   │   ├── lifecycle_orchestrator.py # 24-hour simulation
│   │   │   ├── feedback_collection_service.py  # Service feedback
│   │   │   ├── prediction_generator.py   # Health score ML
│   │   │   └── ...                       # 20+ other services
│   │   ├── database/
│   │   │   ├── repositories/   # Supabase + JSON fallback (25+ repos)
│   │   │   └── models.py       # Pydantic models
│   │   ├── ml/                 # Machine Learning
│   │   │   ├── models/
│   │   │   │   ├── model_registry_db.py      # Database-driven registry
│   │   │   │   ├── niagara_ml_inference.py   # LSTM/Autoencoder
│   │   │   │   └── ml_data_templates.json    # Equipment-specific templates
│   │   │   └── prediction_generator.py
│   │   ├── mcp/                # SIMBIOT MCP Server
│   │   │   └── simbiot_server.py  # 31+ tools via stdio protocol
│   │   ├── config/
│   │   │   └── settings.py     # Environment config (Pydantic)
│   │   └── data/
│   │       └── safety_rules.json  # Safety engine rules
│   ├── tests/                  # pytest tests (separate from E2E)
│   ├── requirements.txt        # Python dependencies
│   └── pytest.ini              # Test config (30s timeout, async_mode=auto)
├── frontend/                   # React/Vite application
│   ├── src/
│   │   ├── App.tsx             # View routing
│   │   ├── lib/api/            # Modular API clients (barrel export)
│   │   │   ├── index.ts        # Barrel export (import from here)
│   │   │   ├── devices.ts      # Device API client
│   │   │   ├── alerts.ts       # Alert API client
│   │   │   ├── approvals.ts    # Approval workflow API
│   │   │   ├── batchers.ts     # Batch aggregation (50ms window)
│   │   │   └── ...             # One per domain
│   │   ├── lib/queryClient.ts  # React Query config
│   │   ├── components/         # React components
│   │   │   ├── Dashboard/      # Main UI
│   │   │   ├── Recommendations/ # Approval workflow UI
│   │   │   ├── modules/        # Module system UI
│   │   │   ├── digital-twin/   # 3D visualization
│   │   │   └── ...             # Feature-specific components
│   │   ├── hooks/              # React Query custom hooks
│   │   │   ├── useDeviceSafetyStatus.ts
│   │   │   ├── useAlerts.ts
│   │   │   └── ...             # Data fetching only, no business logic
│   │   ├── __tests__/          # Test files (not in spec pattern)
│   │   └── test-utils/         # Shared test setup
│   ├── vitest.config.ts        # 80% coverage thresholds
│   ├── package.json
│   └── tsconfig.json           # verbatimModuleSyntax: true
├── supabase/
│   └── migrations/             # SQL migrations
├── simbiot_concept/            # Standalone Python package
│   └── pyproject.toml          # Can be installed: pip install -e
├── tests/                      # E2E tests (Playwright)
└── docs/                       # Documentation
    ├── 02-architecture/
    └── 05-integration/
```

### 4-Registrar Organization Pattern

Routes are organized by **domain registrars** to prevent circular imports and enforce dependency order:

```python
# backend/app/startup/routes.py
def register_routers(app: FastAPI):
    # Order matters: specific before general
    register_core_routers(app)           # Auth, health, sites
    register_building_routers(app)       # Equipment, devices
    register_operations_routers(app)     # Work orders, alerts
    register_analytics_routers(app)      # Chat, ML, predictions

# backend/app/api/registrars/core.py
def register_core_routers(app: FastAPI):
    from app.api import auth, health, sites, cache
    app.include_router(auth.router)
    app.include_router(health.router)
    # ... etc
```

**Why this pattern?**
- ✅ Prevents circular imports between routers
- ✅ Enforces clear dependency hierarchy
- ✅ Makes it obvious where new endpoints belong
- ✅ Reduces router coupling

## Frontend Architecture

### API Client Pattern (Barrel Export)

All API clients are exported from a single barrel (`lib/api/index.ts`):

```typescript
// frontend/src/lib/api/index.ts (barrel export)
export * from './devices'
export * from './alerts'
export * from './approvals'
export type * from './models'  // Types only

// In components:
import { devicesApi, alertsApi } from '@/lib/api'
import type { Device, Alert } from '@/lib/api'
```

**Benefits:**
- ✅ Single import source (no scattered imports)
- ✅ Easy to see all available API methods
- ✅ Type-safe across frontend
- ✅ Simple to refactor API endpoints

### React Query Integration

**All data fetching via custom hooks (never direct in components):**

```typescript
// frontend/src/hooks/useDeviceSafetyStatus.ts
export function useDeviceSafetyStatus(deviceId: string) {
  return useQuery({
    queryKey: ['device-safety', deviceId],
    queryFn: () => devicesApi.getSafetyStatus(deviceId),
    staleTime: 15_000,    // Refetch after 15s
    gcTime: 5 * 60_000,   // Cache for 5 min after last use
  })
}

// In component:
function MyComponent() {
  const { data, isLoading } = useDeviceSafetyStatus('device-123')
  // ... render data
}
```

**Stale Times by Data Type:**

| Data | Stale Time | Reason |
|------|-----------|--------|
| Alerts | 15s | High priority, catch issues quickly |
| Device readings | 15s | Sensor values change frequently |
| Site summary | 30s | Relatively stable |
| Predictions | 60s | ML runs infrequently |
| Buildings | 5m | Rarely changes during session |

### Batch Aggregation (50ms Window)

Multiple React Query hook calls within 50ms window automatically batch:

```typescript
// Component 1 mounts at 0ms
const { data: safety1 } = useDeviceSafetyStatus('device-001')

// Component 2 mounts at 20ms (within 50ms window)
const { data: safety2 } = useDeviceSafetyStatus('device-002')

// Result: 1 batch API call to /api/devices/batch/safety-status
// (not 2 separate calls)

// Component 3 mounts at 60ms (outside window)
const { data: safety3 } = useDeviceSafetyStatus('device-003')
// Result: separate batch API call (new 50ms window)
```

## Design Patterns

### 1. Device Abstraction Layer

Protocol-agnostic device control (BACnet, Modbus, DALI, mock):

```python
# backend/app/services/device_abstraction.py
device_manager = DeviceManager()  # Singleton

# Control any device regardless of protocol
await device_manager.write_property(
    device_id="S002-VAV-101",
    property_name="setpoint",
    value=22.5,
)

# Device manager handles:
# - Protocol detection (BACnet? Modbus? DALI?)
# - Connection pooling
# - Error handling & retries
# - COV (Change of Value) feedback
```

### 2. Safety System (Defense-in-Depth)

All device control routed through SafetyEngine:

```python
# backend/app/services/safety_interlocks.py

# Rule types: TemperatureRange, PressureLimit, Interlock, RuntimeLimit
# Severity levels: WARNING (allow), BLOCK (prevent), ALARM (critical)

safety_engine.validate_control(
    device_id="S002-CHILLER-B1-001",
    target_value=5.0,  # Try to set to 5°C
    control_type="chiller_setpoint"
)
# Returns: ✓ ALLOWED or ✗ BLOCKED with reason
```

### 3. Approval Workflow (Tier 2)

**AI Recommendation → Operator Review → Safety Validation → Device Write**

```
1. AI generates recommendation (health_score < 90 equipment)
2. Dashboard displays in "Pending Approvals"
3. Operator reviews + clicks "Approve"
4. Backend re-validates safety rules
5. Device receives write command
6. COV feedback returned ("Now at 18°C")
7. Comparison: target vs actual
8. Status: EXECUTED or ERROR
9. Rollback available if needed
```

See: `CLAUDE_WORKFLOWS.md` → Device Control Approval section

### 4. Background Jobs (APScheduler)

Periodic tasks run in background:

```python
# backend/app/services/background_scheduler.py
scheduler = BackgroundScheduler()

# Example: Process Telegram notifications every 30 seconds
scheduler.add_job(
    func=process_pending_notifications,
    trigger=IntervalTrigger(seconds=30),
    id='sentry_notifications',
    replace_existing=True
)

# Initialized in backend/app/startup/events.py
# Jobs survive service restarts (stored in Supabase)
```

**Active Jobs:**
- Telegram notification processing (30s interval)
- AI recommendations generation (10-min interval)
- Demo data generation (testing only)

### 5. Database Repositories (Supabase + Fallback)

```python
# backend/app/database/repositories/equipment_repository.py

class EquipmentRepository:
    async def get_by_code(self, code: str):
        # First tries Supabase
        # If fails, falls back to JSON files
        # Transparent to caller
        pass

# Always use repositories, never direct Supabase queries:
# ✅ equipment = await repo.get_by_code("S002-VAV-101")
# ❌ data = await supabase.table("equipment").select("*")
```

### 6. ML Model Registry (Database-Driven)

Models defined in Supabase `ml_models` table, not Python:

```python
# backend/app/ml/models/model_registry_db.py

registry = await MLModelRegistry.get_instance()

# Query models by equipment type
models = await registry.get_models_for_type("AHU")
# Returns: [AHU_LSTM (R²=0.49), AHU_Autoencoder (R²=0.42)]

# Threshold-based fallback for types without ML
threshold = await registry.get_confidence_threshold("VAV")
# Returns: 1.0 if no model (use rules-only)
```

**Why database-driven?**
- ✅ Update models without redeploying
- ✅ Retrain without code changes
- ✅ Equipment types auto-extracted from codes
- ✅ Multi-site support (S002, site-003, site-012)

## Data Flow Example: Equipment Fault → Resolution

```
Equipment Sensor Detects Fault
    ↓
Health Score Updated (<50% = warning)
    ↓
PostgreSQL trigger: Alert Created
    ↓
PostgreSQL trigger: Work Order Created
    ↓
Technician Assignment: Type → Specialty
    ↓
Service Record: Status='notified'
    ↓
Background Job (30s interval)
    ↓
Sentry Bot Sends Telegram to Technician
    ↓
Technician On-Site → Repairs Equipment
    ↓
Technician Submits Feedback via Sentry
    ↓
Health Score Updated: +2 (positive), 0 (neutral), -3 (negative), -5 (critical)
    ↓
Alert Auto-Resolved (if health ≥ 80%)
    ↓
Dashboard Updates Real-Time (SSE)
```

## Service Layer Architecture

```
API Routers (70+)
    ↓
Services (30+) ← Business Logic
    ↓                ↓
Repositories    Safety Engine
(25+)           Device Manager
    ↓
Supabase + JSON Fallback
```

**Never put business logic in routers.** Always delegate to services.

```python
# ✅ CORRECT: Router delegates to service
@router.post("/devices/{device_id}/control")
async def control_device(device_id: str, value: float):
    result = await device_service.control(device_id, value)
    return result

# ❌ WRONG: Business logic in router
@router.post("/devices/{device_id}/control")
async def control_device(device_id: str, value: float):
    device = await supabase.table("equipment").select("*").eq("id", device_id)
    # ... more logic here ...
```

## Key Files by Concept

| Concept | Files |
|---------|-------|
| **Health Score Lifecycle** | `prediction_generator.py`, `alerts.py`, `feedback_collection_service.py` |
| **Device Control** | `device_abstraction.py`, `approval_service.py`, `safety_interlocks.py` |
| **Alerts & Notifications** | `alerts.py`, `sentry_webhooks.py`, `background_scheduler.py` |
| **Work Orders** | `work_orders.py`, `feedback_collection_service.py`, `technician_repository.py` |
| **React Query Caching** | `lib/queryClient.ts`, `lib/api/batchers.ts` |
| **Batch Optimization** | `lib/api/batchers.ts`, each `lib/api/{domain}.ts` |

See `CLAUDE.md` → "Key Files by Task" for more.
