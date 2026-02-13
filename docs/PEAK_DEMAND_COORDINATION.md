# Peak Demand Management & Multi-Module Coordination

**Purpose:** Coordinate multi-module peak demand shaving across Solar, HVAC, Energy, and Load Deferral modules. Prevents NMD (Network Moment Demand) breaches while optimizing cost savings through TOU arbitrage and demand response.

**See CLAUDE.md for quick reference. This document covers full technical details.**

## Architecture Overview

- **Module-Agnostic Coordinator:** `backend/app/services/demand_aware_coordinator.py` discovers active modules at runtime, no hardcoding
- **AI Optimizer Integration:** Uses Claude for multi-system reasoning with peak demand context
- **Tier 2 Approval:** Multi-module changes routed through approval workflow with safety validation
- **Real-Time Dashboard:** Solar tab with demand curve, headroom gauge, BESS state, cost tracking
- **Graceful Degradation:** Works with any module combination (solar alone, hvac+solar, etc.)

## REST API Endpoints (Module-Agnostic)

All read-only, discover modules at runtime:

```python
# GET /api/peak-demand/{site_id}/status
# Returns current demand vs NMD limit, headroom %, alert level, active modules
Response: {
  "current_demand_kw": 5500,
  "nmd_limit_kva": 6000,
  "headroom_kw": 500,
  "headroom_percent": 8.3,
  "headroom_level": "critical",  # normal | warning | critical | emergency
  "active_modules": ["solar", "hvac"],
  "available_reductions": {
    "solar": {"max_reduction_kw": 200, "method": "bess_discharge"},
    "hvac": {"max_reduction_kw": 50, "method": "setpoint_increase"}
  }
}

# GET /api/peak-demand/{site_id}/forecast-24h
# Returns hourly demand predictions for next 24 hours with NMD trend
Response: {
  "forecast_intervals": [
    {"hour": 0, "demand_kw": 3200, "headroom_percent": 46.7, "trend": "stable"},
    {"hour": 1, "demand_kw": 3100, "headroom_percent": 48.3, "trend": "falling"},
    ...
  ]
}

# GET /api/peak-demand/{site_id}/recommendations
# Returns multi-module recommendations coordinated by AI optimizer
Response: {
  "multi_module_recommendations": [
    {
      "id": "rec-001",
      "urgency": "critical",
      "modules_involved": ["solar", "hvac"],
      "module_actions": [
        {"module": "solar", "action": "bess_discharge_200kw", "duration_min": 60, "reduction_kw": 200, "estimated_savings_r": 31100},
        {"module": "hvac", "action": "setpoint_increase_2c", "reduction_kw": 50, "comfort_impact": "minor"}
      ],
      "estimated_reduction_kw": 250,
      "estimated_savings_r": 38875,
      "reasoning": "NMD headroom critical (8.3%), BESS available, HVAC can support adjustment"
    }
  ]
}

# POST /api/peak-demand/{site_id}/approve-recommendation
# Executes multi-module recommendation with atomic all-or-nothing semantics
Request: {"recommendation_id": "rec-001", "approved_by": "operator@site"}
Response: {"status": "executing", "module_actions_executing": 2}
```

## Headroom Urgency Levels

- **Normal** (>80%): Routine operations, TOU arbitrage enabled (if solar active)
- **Warning** (15-80%): Begin monitoring, optional load reduction if needed
- **Critical** (<15%): Immediate shaving required, all modules activate, potential load deferral
- **Emergency** (<5%): Emergency measures, hard load shedding as last resort

## Coordinator Flow (Runs Every 5 Minutes)

1. **Query current state:** Get demand_kw, nmd_limit_kva from solar_demand_service
2. **Module discovery:** Query module registry for active modules at site (no hardcoding)
3. **Collect options:** Call each module's `generate_optimization_options()` method:
   - Solar: "BESS discharge 100/150/200 kW" with SOC/tariff constraints
   - HVAC: "Setpoint +1°C / +2°C" with comfort bounds
   - Energy: "Pump deferral 30 min" with load preservation
   - Load Deferral: "Non-critical load shed 50kW" with occupancy limits
4. **Route to AI:** Build unified prompt with available options + demand context
5. **Get recommendation:** AI returns best combination with cost-benefit analysis
6. **Store & notify:** Save recommendation to database, display on dashboard

## Multi-Module Recommendation Format

Stored in database:
```python
{
    "recommendation_id": "rec-001",
    "site_id": "S002",
    "modules_involved": ["solar", "hvac"],  # Which modules contribute
    "urgency": "critical",  # Based on headroom level
    "module_actions": [
        {
            "module": "solar",
            "action": "bess_discharge_200kw",
            "duration_min": 60,
            "estimated_reduction_kw": 200,
            "estimated_savings_r": 31100
        },
        {
            "module": "hvac",
            "action": "setpoint_increase_2c",
            "estimated_reduction_kw": 50,
            "comfort_impact": "minor"
        }
    ],
    "total_reduction_kw": 250,
    "total_savings_r": 38875,
    "requires_approval": true,
    "created_at": "2026-02-12T14:30:00Z"
}
```

## Frontend Integration (React Query)

Module-specific stale times:
```typescript
// Hook: usePeakDemandStatus(siteId)
// Stale time: 15s (demand changes frequently)
// Returns: current_demand_kw, headroom_percent, active_modules, available_reductions

// Hook: usePeakDemandForecast(siteId)
// Stale time: 60s (model runs infrequently, 15-min coordinator cycle)
// Returns: 24-hour hourly forecast with trend

// Hook: usePeakDemandRecommendations(siteId)
// Stale time: 30s (coordinator runs every 5 min)
// Returns: Multi-module recommendations with module_actions array

// Component: SolarDashboard.tsx
// - Demand curve chart (Tremor LineChart, last 24h with NMD overlay)
// - NMD headroom gauge (Tremor Gauge, color zones: green/yellow/red)
// - BESS state card (SOC %, discharge available, charge schedule)
// - Active module options (dynamic: show only if module_active)
// - Cost savings tracker (BESS arbitrage value, demand charge savings)
// - Recommendation card (if pending multi-module actions)

// Component: ApprovalDialog.tsx enhancements for multi-module
// - Multi-module support: Added "modules_involved" field to Recommendation type
// - Tab switching: Auto-select "modules" tab when module_actions array exists
// - Module grouping: Actions displayed grouped by module with per-module impact
// - Approve button label: "Approve All Changes" for multi-module recommendations
// - Progress display: Each module's action status as execution proceeds
```

## Module-Agnostic Design Pattern

The coordinator doesn't hardcode modules—it discovers them at runtime:

```python
# ✅ CORRECT: Coordinator doesn't hardcode modules
active_modules = await module_registry.get_active_modules(site_id)
for module_name in active_modules:
    module = await module_registry.get_module(module_name)
    options = await module.generate_optimization_options(demand_context)
    collected_options[module_name] = options

# ❌ WRONG: Hardcoding assumes solar always active
solar_actions = await solar_module.get_discharge_options()  # What if solar not active?

# Scaling benefit: Adding new modules (water management, transport, waste) requires
# no changes to coordinator - just implement generate_optimization_options() interface
```

## Related Files

- **Backend Services:** `backend/app/services/demand_aware_coordinator.py`, `solar_demand_service.py`, `solar_arbitrage_engine.py`, `bess_dispatch_engine.py`, `ai_optimizer.py`
- **Backend API:** `backend/app/api/peak_demand.py`, `backend/app/api/modules.py`
- **Backend Jobs:** `background_scheduler.py` (add_demand_aware_coordination_job every 5 min)
- **Frontend API:** `frontend/src/lib/api/peakDemand.ts` with PeakDemandAPI client
- **Frontend Hooks:** `frontend/src/hooks/usePeakDemand.ts` with 4 custom hooks
- **Frontend Components:** `frontend/src/components/modules/SolarDashboard.tsx`, `ModularDashboard.tsx`, `ApprovalDialog.tsx`

## Common Patterns

```typescript
// ✅ CORRECT: Use React Query hooks with appropriate stale times
const { data: demand } = usePeakDemandStatus(siteId);  // 15s stale
const { data: forecast } = usePeakDemandForecast(siteId);  // 60s stale

// ✅ CORRECT: Check which modules are active before rendering
if (demand?.active_modules.includes("solar")) {
  return <SolarDashboard />;
}

// ✅ CORRECT: Multi-module approval with atomic execution
POST /api/peak-demand/approve-recommendation
# All module_actions execute together or none at all

// ❌ WRONG: Assuming Solar always has demand data
const bess_power = demand.solar.bess_discharge;  # May not exist if solar not active

// ❌ WRONG: Bypassing coordinator for single-module changes
POST /api/solar/discharge  # Prevents coordination across modules
```

## Graceful Degradation

- **If coordinator unavailable:** Manual Solar control still works via individual module APIs
- **If AI optimizer unavailable:** Coordinator uses rule-based defaults (fixed reduction targets)
- **If BESS unavailable:** Coordinator skips solar actions, offers HVAC-only shaving
- **If HVAC unavailable:** Coordinator offers solar-only peak shaving (no load increases)
- **If no modules active:** Peak demand monitoring still works, no recommendations generated

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No recommendations generated | Verify coordinator job running every 5 min in logs, check `add_demand_aware_coordination_job()` in startup events |
| Demand curve not updating | Check Redis cache TTL (should be 15s for status endpoint), verify `usePeakDemandStatus` hook is called |
| Multi-module tab not showing | Recommendation must have `modules_involved` array with 2+ modules, check ApprovalDialog receives `module_actions` field |
| Approval fails with "missing modules" | Ensure all active modules implement `generate_optimization_options()` interface, check module registry initialization |
| BESS discharge doesn't execute | Verify Solar module active, check BESS SOC >20%, verify bess_dispatch_engine safety constraints pass |
| Cost savings always zero | Check TOU tariff schedule loaded, verify solar_arbitrage_engine initialized with tariff data |
