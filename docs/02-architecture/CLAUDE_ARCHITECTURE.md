---
title: "CLAUDE_ARCHITECTURE.md - System Design & Architecture"
type: "architecture"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# CLAUDE_ARCHITECTURE.md - System Design & Architecture

Complete system architecture for SENTINEL BMS Intelligence Platform.

---

## 🎯 Project Overview

**SENTINEL BMS Intelligence Platform** — AI-powered building management system combining predictive maintenance, conversational AI, and device control.

- **Backend:** FastAPI + Python 3.11 | Supabase (PostgreSQL) | TensorFlow | Claude API + Ollama
- **Frontend:** React + TypeScript (Vite) | Sentinel design system + Tailwind (no Tremor)
- **Scale:** 70+ API endpoints, 31 MCP tools, 3 buildings, 542+ equipment
- **Multi-Protocol:** BACnet, Modbus, DALI, OPC-UA, Telegram
- **Automation:** PostgreSQL triggers + APScheduler + Sentry webhook integration

---

## 🏗️ Backend Architecture

### Application Structure
```
backend/app/
├── api/                 # 70+ routers organized by domain
│   ├── registrars/      # 4 registrars that organize routes
│   └── {domain}.py      # Individual route files
├── services/            # 30+ business logic services
├── database/            # Repositories + data access
├── ml/                  # ML models, predictions, inference
├── mcp/                 # SIMBIOT MCP Server (31 tools)
└── startup/             # Routes, jobs, middleware, events
```

### 4-Registrar Pattern

All routes registered via 4 specialized registrars:

```python
# backend/app/startup/events.py
register_core_routers(app)         # Auth, health, sites (public)
register_building_routers(app)     # Equipment, HVAC, lighting, zones
register_operations_routers(app)   # Work orders, alerts, approvals, integrations
register_analytics_routers(app)    # Chat, ML, optimization, simulations
```

**Key Principle:** Each registrar imports only its own routers. No circular dependencies.

### Request Flow
```
Client Request
  → Middleware (CORS, auth check)
  → 4-Registrar Router (core|building|operations|analytics)
  → API Handler (async function)
  → Service Layer (business logic)
  → Repository Layer (data access)
  → Supabase/Cache/Fallback
  → Response
```

### Data Access Pattern (Repositories)

All database access uses **Repository Pattern** for consistency:

```python
# backend/app/database/repositories/{table}_repository.py
class EquipmentRepository:
    def __init__(self, db=None):
        self.db = db or Supabase.instance().client

    async def get_by_code(self, code: str) -> Optional[Equipment]:
        # Tries cache first, then Supabase, then JSON fallback
        ...

# Usage in services:
equipment_repo = EquipmentRepository()
equipment = await equipment_repo.get_by_code("S002-VAV-101")
```

**Benefits:**
- Redis caching layer
- JSON fallback (when Supabase is down)
- Consistent error handling
- Easy mocking in tests

---

## 🖥️ Frontend Architecture

### Component Structure
```
frontend/src/
├── lib/api/            # Modular API clients (barrel export: index.ts)
├── components/         # React components by feature
├── hooks/              # React Query data fetching only
└── __tests__/          # Test files (80% coverage required)
```

### Standard Component Pattern

```typescript
// frontend/src/components/Feature/MyComponent.tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { MyData } from '@/lib/api'  // Type-only import on own line
import { myApi } from '@/lib/api'        // Runtime import separate

interface Props {
  id: string
  onUpdate?: (data: MyData) => void
}

export function MyComponent({ id, onUpdate }: Props) {
  // 1. State
  const [isLoading, setIsLoading] = useState(false)

  // 2. Data fetching (useQuery hook only)
  const { data, isLoading: queryLoading } = useQuery({
    queryKey: ['myFeature', id],
    queryFn: () => myApi.get(id),
  })

  // 3. Effects
  // Side effects depending on props/state go here

  // 4. Event handlers
  const handleUpdate = async () => {
    try {
      const result = await myApi.update(id, data)
      onUpdate?.(result)
    } catch (error) {
      console.error('Update failed:', error)
    }
  }

  // 5. Render
  return (...)
}
```

**Key Rules:**
- Data fetching: Use `useQuery`/`useMutation` hooks only
- Never call `fetch()` or API methods directly in components
- Type-only imports must be on separate line (verbatimModuleSyntax)
- Files mirror folder structure: `src/components/Feature/MyComponent.tsx`
- Tests alongside: `src/components/Feature/__tests__/MyComponent.test.tsx`

---

## 🗄️ MCP Tools (SIMBIOT Integration)

**Location:** `backend/app/mcp/tools/` (31 tools across 5 categories)

### Tool Categories
- **core/** - Device discovery, health checks, telemetry
- **operations/** - Work orders, alerts, approvals
- **commercial/** - Billing, contracts, vendors
- **solar/** - PV system monitoring, performance
- **onboarding/** - System initialization, setup

### Adding a New Tool
1. Create `backend/app/mcp/tools/{category}/my_tool.py`
2. Implement tool class with `execute()` method
3. Register in `backend/app/mcp/tools/registry.py` → `TOOLS` dict
4. Tool auto-discovered by SIMBIOT server on startup

### Tool Invocation
```
User asks → Claude API calls MCP tool → Tool executes → Result returned to AI
```

All tools are async-first for performance.

---

## 🔐 Safety & Approval Workflow

### Tier 2 Supervised Control
```
AI Recommendation
  ↓
User Approval Required
  ↓
Safety Validation (temperature limits, interlocks)
  ↓
Device Control (write to Supabase)
  ↓
COV Feedback (read back to confirm)
  ↓
Execution Result (stored for rollback)
```

### Safety Engine
- Defense-in-depth: Pre-execution + runtime validation
- Temperature limits: 16-28°C for HVAC
- Interlocks: Cannot cool below 5°C
- Priority arrays: Emergency modes override normal limits
- Rollback: Original value stored, can restore on failure

---

## 📊 Database Schema

### Key Tables
- **equipment** - Device registry (542 items)
- **buildings** - Building registry (3 sites)
- **alerts** - Auto-generated when health < 50%
- **work_orders** - Auto-created when alert generated
- **technicians** - Technician registry with specialties
- **service_records** - Service feedback for ML training
- **ml_models** - ML model registry with R² scores

### Foreign Keys
- Equipment references building via `building_id`
- Work orders reference equipment via `equipment_id`
- Service records reference work orders via `work_order_id`
- All use UUID primary keys

### JSON Fallback
- If Supabase down: Repositories fall back to JSON files
- Files in `backend/app/data/{table}.json`
- Automatically synced with Supabase
- Must be manually updated if using fallback

---

## 🔄 Automation Pipelines

### Equipment Warning Workflow
```
Equipment health < 50%
  ↓ (PostgreSQL trigger - instant)
Alert created + severity calculated
  ↓ (PostgreSQL trigger - instant)
Work order auto-created
  ↓ (PostgreSQL trigger - instant)
Service record created
  ↓ (Background job every 30s)
Technician assigned by specialty
  ↓ (Sentry bot webhook)
Telegram notification sent
  ↓ (Technician replies)
Service feedback submitted
  ↓ (Automated)
Health restored + alert resolved
```

### Background Jobs (APScheduler)
- Run in `backend/app/services/background_scheduler.py`
- Initialized in `backend/app/startup/events.py`
- Process notifications, update health, cascade alerts
- 30-second default interval, configurable

---

## 🎯 Redis Caching

**Service:** `backend/app/services/cache_service.py`

**TTL Presets:**
- STATIC (600s) - Buildings, users, reference data
- SEMI_STATIC (300s) - Equipment, technicians
- DYNAMIC (60s) - Alerts, work orders
- REALTIME (15s) - Equipment health, live data

**Cached Repositories:**
- BuildingRepository
- EquipmentRepository
- AlertRepository

**Invalidation:**
Use `CacheInvalidation` class for write operations to automatically clear related keys.

---

## 🧠 ML & Prediction System

### Model Registry
- Database-driven: `ml_models` table
- Equipment types: CHILLER, AHU, FCU, VAV, UPS, GEN, DALI
- Models include: LSTM, Autoencoder, Classifier, Survival Analysis
- R² scores: 0.30-0.61 depending on type

### Prediction Flow
```
Equipment telemetry
  → ML inference
  → Health score calculated
  → Thresholds checked
  → Alert/WO triggered if health < 50%
```

### Health Impact Scoring
- Positive feedback: +2 to health
- Neutral feedback: 0
- Negative feedback: -3
- Critical failure: -5

---

## 🌞 Solar/BESS Annual Simulation

**Files:**
- `backend/app/services/solar_annual_aggregator.py` - Aggregation engine
- `backend/app/api/solar_annual.py` - API endpoints
- `frontend/src/components/solar/SolarAnnualCard.tsx` - Dashboard card

**How It Works:**
```
User: POST /api/solar/annual/simulate
  ↓
Background task starts (8,760 hourly snapshots)
  ↓
Frontend polls progress every 5 seconds
  ↓
After 240 real minutes: Complete
  ↓
Results cached in Supabase
  ↓
GET /api/solar/annual/summary returns instant results
```

**ML Learning Curve:**
- Phase 1 (Month 1-2): 2% → 5% savings
- Phase 2 (Month 3-6): 8% → 14% savings
- Phase 3 (Month 7-12): 16% → 18% savings

---

See also: `CLAUDE_PATTERNS.md`, `CLAUDE_DATABASE.md`, `CLAUDE_INTEGRATION.md`
