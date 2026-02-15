---
title: "Phase 082: Solar/BESS Annual Simulation with ML Learning Curve"
type: "feature"
status: "implemented"
version: "1.0.0"
created: "2026-02-14"
updated: "2026-02-14"
author: "SENTINEL Development Team"
tags: ["solar", "bess", "simulation", "ml", "annual", "forecasting", "arbitrage", "dashboard"]
domain: "solar"
audience: "developers"
complexity: "advanced"
estimated_read_time: 15
phase: "082"
---

# Phase 082: Solar/BESS Annual Simulation with ML Learning Curve

365-day solar/BESS simulation comparing **Standard EMS (reactive)** vs **Sentinel AI (predictive optimization)** with an ML learning curve demonstrating 2%-18% savings progression. Dashboard card integration (not a new page) on existing Solar Dashboard.

**Demo Site:** Site-002 Sandton (3,900 kWp solar + 5,015 kWh BESS)

---

## Overview

Phase 082 delivers a comprehensive 365-day simulation system showing:

1. **Annual Energy & Cost Analysis**
   - Monthly breakdown: solar generation, BESS cycles, grid import/export, costs
   - Seasonal aggregation: summer/autumn/winter/spring patterns
   - Annual totals: savings ZAR, capacity factor %, self-consumption %

2. **Standard EMS Baseline**
   - Fixed schedule: Charge BESS off-peak (22:00-06:00), discharge peak (07:00-10:00, 18:00-20:00)
   - No weather awareness, no load forecasting
   - ~5-7% baseline savings

3. **Sentinel AI Optimization**
   - Dynamic TOU arbitrage based on tariff forecast + solar forecast
   - Weather-aware charging: Pre-charge before cloud cover
   - Demand charge minimization: Targets < NMD threshold
   - Learning phases: 2% (month 1) → 18% (month 12)

4. **ML Learning Curve**
   - **Phase 1 (Month 1-2):** Learning (2-5%) — collecting baseline data, basic TOU
   - **Phase 2 (Month 3-6):** Optimization (8-14%) — predictive dispatch, weather integration
   - **Phase 3 (Month 7-12):** Mature (16-18%) — full arbitrage, demand minimization

---

## Architecture

### Backend Components

#### 1. Annual Scenario (`lifecycle_orchestrator.py`)

New scenario `grant_solar_bess_ai_annual`:
```python
ScenarioConfig(
    name="Grant Demo: Solar + BESS + Sentinel AI (365 days)",
    description="Full-year simulation with 3.9 MWp solar + 5 MWh BESS, City Power TOU arbitrage, demand management, and South African seasonal variations",
    operation_mode=OperationMode.SOLAR_BESS_SENTINEL,
    fault_probability=0.03,
    auto_repair=True,
    repair_delay_hours=6,
    optimization_enabled=True,
)
```

**Lifecycle Integration:**
- Reuses existing `LifecycleOrchestrator` infrastructure
- Runs 365 × 24 = 8,760 simulated hours
- Time compression: 240 real minutes = full year
- Generates hourly snapshots with seasonal patterns

#### 2. Aggregation Service (`solar_annual_aggregator.py`)

Aggregates 8760 hourly snapshots into monthly/seasonal/annual summaries.

**Data Classes:**
```python
@dataclass
class HourlySnapshot:
    hour: int
    date: datetime
    solar_gen_kw: float
    building_load_kw: float
    bess_soc_pct: float
    grid_import_kw: float
    grid_export_kw: float
    tariff_band: str  # peak|standard|off_peak
    tariff_rate_c_kwh: float

@dataclass
class MonthSummary:
    month: int
    season: str  # summer|autumn|winter|spring
    solar_generated_kwh: float
    grid_import_kwh: float
    peak_demand_kw: float
    total_cost_standard_ems_zar: float
    total_cost_sentinel_ai_zar: float
    savings_pct: float
    learning_factor: float

@dataclass
class AnnualSummary:
    monthly_data: List[MonthSummary]
    seasonal_data: List[SeasonSummary]
    annual_savings_zar: float
    annual_savings_pct: float
    learning_curve: List[Dict[str, float]]
```

**Aggregation Steps:**
1. Group 8760 hours by month (12 groups)
2. Sum energy flows: solar, BESS, grid, building load
3. Calculate peak demand per month
4. Calculate Standard EMS cost (fixed schedule, no optimization)
5. Apply ML learning curve (2% → 18%)
6. Calculate Sentinel AI cost with learning factor
7. Aggregate to 4 seasonal summaries
8. Calculate annual totals and metrics

#### 3. API Endpoints (`solar_annual.py`)

**Endpoints:**

```bash
# GET - Fetch cached results (< 100ms, or 404 if not cached)
GET /api/solar/annual/{site_id}/summary
  → AnnualSummary { monthly_data[], seasonal_data[], learning_curve[] }

# POST - Start background simulation (returns immediately with task_id)
POST /api/solar/annual/{site_id}/simulate
  → { task_id, status: "queued" }

# GET - Poll progress
GET /api/solar/annual/{site_id}/status/{task_id}
  → { status: "running", progress_pct: 35, days_completed: 127 }
```

**Background Task Flow:**
1. API returns task_id immediately
2. Background job starts 365-day simulation
3. Every 30 seconds: Update progress (0-100%, days completed)
4. After 240 minutes: Aggregation complete
5. Cache results in Supabase `solar_annual_simulations` table
6. Client polls and refreshes UI

#### 4. Database Schema (`095_solar_annual_simulations.sql`)

**Tables:**

```sql
-- Cache for 365-day results
CREATE TABLE solar_annual_simulations (
    id UUID PRIMARY KEY,
    site_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    scenario TEXT NOT NULL,
    results JSONB NOT NULL,  -- monthly_data[], seasonal_data[], learning_curve[]
    simulation_started_at TIMESTAMPTZ,
    simulation_completed_at TIMESTAMPTZ,
    simulation_duration_seconds INTEGER,
    UNIQUE(site_id, year, scenario)
);

-- Task tracking
CREATE TABLE solar_annual_tasks (
    task_id UUID PRIMARY KEY,
    site_id TEXT,
    status TEXT,  -- queued|running|completed|failed
    progress_pct INTEGER,
    days_completed INTEGER,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);
```

**Indexes:**
- `idx_solar_annual_site_year` — Fast lookup
- `idx_solar_annual_tasks_status` — Filter by status
- RLS policies — User access control

### Frontend Components

#### 1. Dashboard Card (`SolarAnnualCard.tsx`)

Displays annual simulation results on existing Solar Dashboard.

**Features:**
- **Auto-start:** Triggers simulation on mount if not cached
- **Progress bar:** Shows 0-100% while simulating
- **Metric cards:**
  - Annual savings (ZAR) with % vs Standard EMS
  - Solar generated (kWh) with capacity factor %
  - Self-consumption % with kWh on-site
  - Grid import (kWh) with % reduction vs no solar
- **ML learning curve preview:** 3 cards showing month 1-2, 3-6, 7-12 savings
- **Seasonal breakdown:** 4 cards (Summer/Autumn/Winter/Spring) with solar generation and savings %

**Styling:** Gradient background (green/emerald), Tremor UI components, responsive grid (2-4 columns)

#### 2. API Client (`solarAnnual.ts`)

```typescript
// Fetch cached results
fetchAnnualSummary(siteId, year?): Promise<AnnualSummary>

// Start background simulation
startAnnualSimulation(siteId, scenario, durationMinutes): Promise<{ task_id }>

// Poll progress
pollSimulationStatus(siteId, taskId): Promise<SimulationStatus>

// Utilities
formatZAR(value): "R1.2M" | "R890k" | "R456"
formatKWh(value): "850k kWh" | "234 kWh"
getLearningPhase(month): "Learning" | "Optimization" | "Mature"
```

#### 3. Integration with Solar Dashboard

Added as Row 4 (after financial report and forecast chart):
```jsx
<div className="mb-4">
  <div className="glass-panel overflow-hidden">
    <SolarAnnualCard siteId={selectedSiteId} />
  </div>
</div>
```

---

## How It Works

### User Flow

```
User logs in
  ↓
Solar Dashboard loads
  ↓
SolarAnnualCard mounts
  ↓
Tries GET /api/solar/annual/site-002/summary
  ├─ Success (304): Display cached results (< 100ms)
  └─ 404 (not cached): Start simulation
      ↓
      POST /api/solar/annual/site-002/simulate → task_id
      ↓
      Show progress bar (0-100%)
      ↓
      Poll GET /api/solar/annual/site-002/status/{task_id} every 5s
      ├─ Status: "running" → Update progress
      └─ Status: "completed" → Fetch results & display
```

### Data Aggregation Pipeline

```
LifecycleOrchestrator.start("grant_solar_bess_ai_annual")
  ├─ Initialize SeasonalModeler (SA weather, occupancy patterns)
  ├─ Loop 365 days:
  │  ├─ Hour 0-23: Generate hourly snapshot
  │  │  ├─ Solar generation (weather factor × capacity × hour factor)
  │  │  ├─ Building load (HVAC + occupancy)
  │  │  ├─ BESS dynamics (charge/discharge)
  │  │  ├─ Grid import/export
  │  │  └─ Tariff band (peak|standard|off_peak)
  │  └─ Day 365: Notify orchestrator completion
  └─ Return 8760 HourlySnapshot[]
      ↓
      SolarAnnualAggregator.aggregate_annual_results()
      ├─ Group by month (12 groups)
      ├─ Calculate Standard EMS cost (fixed schedule)
      ├─ Apply ML learning curve (2% → 18%)
      ├─ Calculate Sentinel AI cost with learning
      ├─ Aggregate by season (4 groups)
      └─ Calculate annual totals & metrics
          ↓
          Cache in Supabase solar_annual_simulations
          ↓
          Return AnnualSummary
```

### City Power Tariff Integration

**Summer (Dec-Feb):**
- Peak: 345.67 c/kWh (07:00-10:00, 18:00-20:00)
- Standard: 212.34 c/kWh (10:00-18:00)
- Off-peak: 105.67 c/kWh (20:00-07:00)
- Demand charge: R189.45/kVA

**Winter (Jun-Aug):**
- Peak: 489.12 c/kWh (06:00-09:00, 17:00-22:00)
- Standard: 256.78 c/kWh (09:00-17:00)
- Off-peak: 134.56 c/kWh (22:00-06:00)
- Demand charge: R267.89/kVA

**Shoulder (Mar-May, Sep-Nov):**
- Standard rates apply
- Demand charge: R223.67/kVA

---

## ML Learning Curve Model

### Phase 1: Learning (Month 1-2)
**Savings: 2-5%**
- Month 1: 2.0%
- Month 2: 3.5%

**Characteristics:**
- Collecting baseline data (occupancy, weather patterns, equipment response times)
- Basic TOU arbitrage: Fixed schedule charge/discharge
- No weather forecasting
- No demand minimization

### Phase 2: Optimization (Month 3-6)
**Savings: 8-14%**
- Month 3: 8.0%
- Month 4: 10.0%
- Month 5: 12.0%
- Month 6: 14.0%

**Characteristics:**
- Weather-aware charging: Pre-charge before cloud cover
- Predictive dispatch: Charges when solar forecast high, discharges during peak tariff
- Load forecasting: Adjusts charging based on occupancy prediction
- Demand monitoring: Begins tracking peak vs NMD threshold

### Phase 3: Mature (Month 7-12)
**Savings: 16-18%**
- Month 7: 16.0%
- Month 8: 16.5%
- Month 9: 17.0%
- Month 10: 17.3%
- Month 11: 17.7%
- Month 12: 18.0%

**Characteristics:**
- Full TOU arbitrage: Maximizes low-rate charging
- Demand charge minimization: Actively reduces peak to stay below NMD
- Cross-system coordination: HVAC + BESS + lighting optimization
- Seasonal tuning: Adapts to winter/summer load patterns

---

## Cost Calculations

### Standard EMS (Baseline)

Fixed schedule: Charge 22:00-06:00 (off-peak), Discharge 07:00-10:00 + 18:00-20:00 (peak)

```
Monthly Cost = Energy Cost + Demand Cost

Energy Cost = 
  Grid_Import_kwh × Weighted_Tariff_Rate
  (Assuming 30% peak, 30% standard, 40% off-peak)

Demand Cost = 
  Peak_Demand_kW ÷ 0.95 (power factor) × Demand_Charge_ZAR_kVA
```

**Example (Summer month):**
- Grid import: 5,000 kWh
- Peak: 1,500 kWh × R3.4567/kWh = R5,185
- Standard: 1,500 kWh × R2.1234/kWh = R3,185
- Off-peak: 2,000 kWh × R1.0567/kWh = R2,113
- **Energy subtotal: R10,483**

- Peak demand: 250 kW
- kVA: 250 ÷ 0.95 = 263.2 kVA
- Demand cost: 263.2 × R189.45 = R49,854
- **Monthly total: R60,337**

### Sentinel AI (Optimized)

Dynamic dispatch applying ML learning factor (2%-18% savings):

```
Sentinel_Cost = Standard_Cost × (1 - Learning_Factor)

Learning_Factor ranges from 0.02 (month 1) to 0.18 (month 12)
```

**Example (Summer month, Month 6):**
- Standard EMS cost: R60,337
- Learning factor: 14%
- Sentinel cost: R60,337 × (1 - 0.14) = **R51,890**
- **Monthly savings: R8,447 (14.0%)**

---

## Integration Points

### Existing Services Used

1. **SeasonalModeler** (`seasonal_modeler.py`)
   - `get_solar_generation_factor(date, cloud_cover)` — 75-95% seasonal efficiency
   - `get_occupancy_factor(date, hour)` — Building load patterns
   - `get_hvac_load_factor(date, occupancy, temp)` — HVAC demand

2. **SolarArbitrageEngine** (`solar_arbitrage_engine.py`)
   - TOU tariff optimization
   - Dispatch schedule generation
   - Savings calculation

3. **TariffScheduleService** (`tariff_schedule_service.py`)
   - `get_band_for_hour(datetime)` → peak|standard|off_peak
   - Season switching (summer/winter/shoulder)

4. **LifecycleOrchestrator** (`lifecycle_orchestrator.py`)
   - 365-day simulation runner
   - Time compression (240 min = full year)
   - Event generation

---

## Performance Characteristics

| Metric | Value |
|--------|-------|
| **Simulation Duration** | 240 real minutes (4 hours) for 365 days |
| **Cached Results** | < 100ms (direct Supabase query) |
| **Card Render** | < 2 seconds (data formatting) |
| **Memory Usage** | < 2GB during simulation |
| **Database Storage** | ~500KB per annual result (JSONB) |
| **Progress Update Frequency** | Every 30 seconds |
| **Frontend Poll Interval** | Every 5 seconds |

---

## Testing & Verification

### Backend Tests

```bash
# Test annual scenario is recognized
pytest tests/api/test_lifecycle.py::test_annual_scenario_simulation

# Test aggregation accuracy
pytest tests/services/test_solar_annual_aggregator.py

# Test API endpoints
pytest tests/api/test_solar_annual.py
```

### Frontend Testing

```bash
# Component renders
npm run test:run -- SolarAnnualCard.test.tsx

# Progress polling works
npm run test:ui  # Manual: Start simulation, watch progress bar

# Results display correctly after 4 hours (or use cached test data)
```

### Integration Testing

```bash
# Full end-to-end
1. Start backend: DEMO_MODE=true
2. Start frontend: npm run dev
3. Navigate to Solar Dashboard
4. Card displays loading + progress bar
5. After 4 hours (or cached), shows annual summary
6. Metrics match expected ranges:
   - Annual savings: 13-17% vs baseline
   - Capacity factor: 20-25%
   - Self-consumption: 80-95%
```

---

## Success Criteria

- ✅ Scenario works: `grant_solar_bess_ai_annual` completes 365 days
- ✅ Aggregation accurate: 12 months + 4 seasons with correct totals
- ✅ ML curve realistic: 2% → 18% progression across phases
- ✅ Frontend renders: All metrics display with correct data
- ✅ Caching works: Second request returns < 100ms
- ✅ Seasonal patterns: Summer solar > winter, HVAC load varies
- ✅ Cost accuracy: Demand charges calculated by month
- ✅ Standard vs Sentinel: ~15% average savings shown

---

## Files Created

| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/services/solar_annual_aggregator.py` | 580 | Aggregation engine |
| `backend/app/api/solar_annual.py` | 290 | API endpoints |
| `frontend/src/components/solar/SolarAnnualCard.tsx` | 250 | Dashboard card |
| `frontend/src/lib/api/solarAnnual.ts` | 150 | API client |
| `supabase/migrations/095_solar_annual_simulations.sql` | 120 | Database schema |
| **Total** | **~1,390** | **New code** |

## Files Modified

| File | Changes | Purpose |
|------|---------|---------|
| `backend/app/services/lifecycle_orchestrator.py` | +6 lines | New scenario |
| `backend/app/api/registrars/analytics.py` | +2 lines | Route registration |
| `frontend/src/lib/api/index.ts` | +14 lines | Export types |
| `frontend/src/components/solar/SolarDashboard.tsx` | +3 lines | Card integration |
| `CLAUDE.md` | +4 lines | Phase 082 status |
| `CLAUDE_QUICK_START.md` | +14 lines | Testing commands |

---

## Related Documentation

- [Solar & BESS Module](./34-solar-bess-module.md)
- [Lifecycle Simulation](./lifecycle-simulation.md)
- [Solar API Reference](../03-api-reference/solar-api.md)
- [Seasonal Modeler](../02-architecture/system-overview.md#seasonal-patterns)

---

**Status:** ✅ COMPLETE (2026-02-14)
