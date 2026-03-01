---
title: "Solar & BESS Optimisation Module"
type: "feature"
status: "implemented"
version: "2.0.0"
created: "2026-02-06"
updated: "2026-02-24"
author: "SENTINEL Development Team"
tags: ["solar", "pv", "bess", "battery", "arbitrage", "dispatch", "nrs-097", "maintenance", "financial"]
domain: "solar"
audience: "developers"
complexity: "advanced"
estimated_read_time: 20
phase: "34"
---

# Solar & BESS Optimisation Module

Full solar PV and battery energy storage optimisation — 9 feature modules covering ingestion, performance monitoring, grid compliance, dashboard, arbitrage, demand management, forecasting, generator coordination, health analytics, maintenance intelligence, financial reporting, and conversational queries.

**Demo Site:**  (3.875 MWp, 33 Huawei SUN2000 inverters, 2 MWh BESS, 500 kVA generator)

## Overview

Phase 34 delivers a complete solar energy management system across 3 waves:

| Wave | Plans | Features |
|------|-------|----------|
| Wave 1 (Foundation) | 34-01 to 34-04 | Data ingestion, performance monitoring, grid compliance, dashboard |
| Wave 2 (Optimisation) | 34-05 to 34-07 | Arbitrage/dispatch, demand management, forecasting, generator coordination |
| Wave 3 (Intelligence) | 34-08 to 34-09 | Health analytics/ML, maintenance scheduling, financial reporting, chat integration |

## Module Breakdown

### Module 1: Data Ingestion (34-01)

Multi-manufacturer connector framework with normalised readings.

- **Connectors:** Huawei SUN2000, Schneider Conext, SMA Sunny Tripower
- **Abstract base:** `SolarConnector` with `connect()`, `read_inverter()`, `read_bess()`, `read_meter()`
- **Simulated mode:** Each connector has a `Simulated*Connector` for demo with realistic register-level data
- **Normalised readings:** All connectors output `SolarReading` with type, value, unit, quality, timestamp

### Module 2: Performance Monitoring (34-02)

Performance Ratio (PR) calculation with inverter peer comparison and string-level anomaly detection.

- **PR calculation:** `actual_yield / (irradiance × capacity × hours)` for day/week/month periods
- **Inverter comparison:** Rankings by efficiency with deviation flags (>5% below median = underperformer)
- **String anomalies:** Detects underperformance, open circuit, short circuit, MPPT faults
- **Diagnostic reports:** Prioritised issues with severity, probable cause, recommended action, cost impact

### Module 3: Grid Compliance (34-03)

NRS 097-2-1 monitoring for South African SSEG (Small-Scale Embedded Generation) requirements.

| Parameter | Limits | Standard |
|-----------|--------|----------|
| Voltage | 207–253V (±10% of 230V) | NRS 097-2-1 Table 1 |
| Frequency | 49.0–51.0 Hz | NRS 097-2-1 §6.3 |
| THD | <5% | NRS 097-2-1 §6.4 |
| Power Factor | >0.95 | NRS 097-2-1 §6.5 |
| DC Injection | <0.5% rated | NRS 097-2-1 §6.6 |

- **Export limits:** Zero-export or capped export compliance
- **Certificate tracking:** NRS 097 certificate status and validity dates
- **SSEG reporting:** Full compliance report generation for municipal submission

### Module 4: Dashboard (34-04)

Seven frontend components for solar monitoring. Full-detail panels render in the **Solar & BESS** discipline tab (`SolarDashboard`). The building Overview tab shows a compact **SolarIntelligenceCard** (generation kW, self-consumption %, performance ratio).

| Component | Location | Purpose |
|-----------|----------|---------|
| `SolarIntelligenceCard` | Overview tab | Compact card: generation, self-consumption, PR, daily savings |
| `SolarOverviewPanel` | Solar & BESS tab | Generation gauge, daily yield, PR, savings ticker |
| `BESSStatusPanel` | Solar & BESS tab | SOC gauge (colour-coded), mode, power, SoH |
| `InverterStatusMatrix` | Solar & BESS tab | Traffic-light grid of all 33 inverters |
| `EnergyFlowDiagram` | Solar & BESS tab | Sankey-style energy flow (Solar → BESS → Building → Grid) |
| `SolarFinancialReport` | Solar & BESS tab | Stacked bar chart of monthly savings breakdown |
| `ForecastActualChart` | Solar & BESS tab | 48h forecast vs actual overlay with confidence band |

### Module 5: Energy Arbitrage & Dispatch (34-05)

Time-of-Use (TOU) optimised BESS dispatch scheduling.

- **City Power TOU:** Off-peak (R0.89/kWh), Standard (R1.47/kWh), Peak (R3.21/kWh)
- **Dispatch strategy:** Charge BESS during off-peak solar, discharge during peak tariff
- **24-hour schedule:** Half-hourly dispatch slots with mode, target SOC, expected savings
- **Savings tracking:** Daily arbitrage value = peak discharge × (peak rate - off-peak rate)

### Module 6: Demand Management (34-06)

Notified Maximum Demand (NMD) tracking and peak shaving.

- **NMD:** City Power R155.50/kVA/month demand charge
- **Peak shaving:** BESS discharge during demand peaks to reduce NMD ratchet
- **15-min profiles:** Demand profile with rolling average and peak markers
- **Self-consumption:** Target >95% self-consumption ratio, energy balance breakdown

### Module 7: Generation Forecasting & Generator Coordination (34-07)

Ensemble generation forecast with dispatch priority stack.

- **Forecast model:** 30% persistence + 30% clear-sky + 40% historical (72h horizon)
- **Confidence bands:** High/low bounds based on weather uncertainty
- **Accuracy metrics:** RMSE (kW, %), MAE, bias %
- **Dispatch priority:** Solar → BESS → Grid → Generator (generator as last resort)
- **Diesel avoidance:** Hours avoided, litres saved, ZAR value (R22/L diesel)
- **Load shedding:** Automatic BESS + generator coordination during Eskom events

### Module 8: Health Analytics & ML (34-08)

Inverter degradation tracking and BESS State-of-Health monitoring.

- **Degradation:** Annual degradation rate per inverter (%/year) from PR trend analysis
- **End-of-life prediction:** Estimated replacement date based on degradation curve
- **BESS SoH:** Rack-level health from cycle count, temperature, cell imbalance
- **Cycle history:** Monthly cycle data with depth-of-discharge averages
- **Warranty evidence:** Auto-generated evidence packages for warranty claims

### Module 9: Maintenance, Financial & Chat (34-09)

Condition-based maintenance scheduling, financial reporting, and conversational interface.

**Maintenance:**
- Panel cleaning: soiling loss estimate from PR decline
- Inverter service: runtime hours (>15,000h), fault count, thermal events
- BESS maintenance: cycle count milestones, cell imbalance trends
- Work order auto-generation via existing Sentry workflow

**Financial Reporting:**
- Monthly savings breakdown: arbitrage + demand charge + self-consumption + diesel avoidance
- ROI calculation vs SENTINEL licence fee
- Carbon offset: kWh × 0.95 kg/kWh (Eskom grid emission factor), diesel × 2.68 kg/L
- Demo data: 3 months retrospective (R80-150K/month for )

**Chat Integration:**
- 5 MCP tools: `get_solar_overview`, `get_bess_status`, `get_solar_savings`, `get_solar_forecast`, `get_solar_diagnostics`
- 4 chat tools registered in `chat_tools.py` for conversational queries via Sentry

## API Endpoints

48 endpoints on the `/api/solar` router. See [Solar API Reference](../03-api-reference/solar-api.md) for full documentation.

**Key endpoints:**
```bash
# Overview & Status
curl localhost:9095/api/solar/sites//overview
curl localhost:9095/api/solar/sites//bess

# Performance & Diagnostics
curl localhost:9095/api/solar/sites//performance
curl localhost:9095/api/solar/sites//diagnostics

# Dispatch & Savings
curl localhost:9095/api/solar/sites//dispatch/schedule
curl localhost:9095/api/solar/sites//arbitrage/savings

# Compliance
curl localhost:9095/api/solar/sites//compliance

# Financial
curl localhost:9095/api/solar/sites//financial/summary?period=ytd
curl localhost:9095/api/solar/sites//financial/carbon?period=month

# Maintenance
curl localhost:9095/api/solar/sites//maintenance/recommendations
```

## Implementation

### Backend Services (16 modules)

| Service | Purpose |
|---------|---------|
| `solar_ingestion_service.py` | Site registration, connector management |
| `solar_connector_base.py` | Abstract connector interface |
| `solar_connector_huawei.py` | Huawei SUN2000 Modbus TCP |
| `solar_connector_schneider.py` | Schneider Conext CL Modbus TCP |
| `solar_connector_sma.py` | SMA Sunny Tripower Modbus TCP |
| `solar_performance_service.py` | PR calculation, inverter comparison, diagnostics |
| `solar_compliance_service.py` | NRS 097-2-1 monitoring, SSEG reporting |
| `solar_arbitrage_engine.py` | TOU optimisation, dispatch scheduling |
| `solar_dispatch_service.py` | Dispatch execution, event logging |
| `solar_demand_service.py` | NMD tracking, peak shaving, demand profiles |
| `solar_selfconsumption_service.py` | Self-consumption ratio, energy balance |
| `solar_forecast_service.py` | Ensemble forecast model, accuracy metrics |
| `solar_generator_coordinator.py` | Dispatch priority stack, diesel avoidance |
| `solar_health_service.py` | Degradation tracking, BESS SoH, warranty evidence |
| `solar_maintenance_service.py` | Condition-based scheduling, work order generation |
| `solar_financial_service.py` | Monthly reports, ROI, carbon offsets |

### Frontend Components

| File | Location |
|------|----------|
| `SolarOverviewPanel.tsx` | `frontend/src/components/solar/` |
| `BESSStatusPanel.tsx` | `frontend/src/components/solar/` |
| `InverterStatusMatrix.tsx` | `frontend/src/components/solar/` |
| `EnergyFlowDiagram.tsx` | `frontend/src/components/solar/` |
| `SolarFinancialReport.tsx` | `frontend/src/components/solar/` |
| `ForecastActualChart.tsx` | `frontend/src/components/solar/` |
| `solarApi.ts` | `frontend/src/lib/` |

### API Router

- `backend/app/api/solar.py` — 48 endpoints across ingestion, performance, compliance, dispatch, demand, forecast, health, maintenance, and financial

## Business Value

| Metric | Value |
|--------|-------|
| Monthly savings () | R80-150K |
| Diesel avoidance | ~R22/L saved per litre |
| Carbon offset | 0.95 kg CO2/kWh solar |
| Manufacturer coverage | 3 (Huawei, Schneider, SMA) |
| Self-consumption target | >95% |
| Forecast horizon | 72 hours |
| Maintenance scheduling | 90-day rolling calendar |

## Module 10: MIP Dispatch Optimizer (v26.0)

Mathematical optimisation of BESS dispatch using Google OR-Tools CP-SAT integer programming solver. Replaces heuristic TOU rules with cost-minimising schedule.

### 15-Minute Load Forecast

GradientBoostingRegressor trained on 90 days of synthetic 15-min load profiles.

- **Features (8):** hour_of_day, day_of_week, month, is_weekend, ambient_temp_c, solar_generation_kw, prev_interval_demand_kw, prev_day_same_interval_kw
- **Output:** 96 intervals (24h) with confidence bands (widens with horizon)
- **Retraining:** Automatic via scheduler (15-min refresh), manual via `POST /retrain`
- **Service:** `load_forecast_service.py` (singleton, GBR, R² > 0.7)

### CP-SAT Dispatch Optimizer

96-slot optimal schedule minimising energy cost + demand charge + battery degradation.

**Decision variables (per 15-min interval):**
- `charge_kw[t]`, `discharge_kw[t]`, `soc_kwh[t]`, `grid_import_kw[t]`
- `is_charging[t]`, `is_discharging[t]` (binary, mutually exclusive)

**Objective:** MINIMIZE
```
sum(grid_import[t] × tariff[t] × 0.25)      # energy cost
+ peak_demand × R395.48/kVA/month ÷ 30       # demand charge
+ cycles × R15/cycle                          # battery degradation
```

**Constraints:**
| # | Constraint | Description |
|---|-----------|-------------|
| 1 | Energy balance | load = solar + grid + discharge − charge |
| 2 | SOC tracking | soc[t+1] = soc[t] + charge×eff×0.25 − discharge/eff×0.25 |
| 3 | SOC bounds | 40 kWh ≤ SOC ≤ 190 kWh (20-95% of 200 kWh) |
| 4 | Mutual exclusion | Cannot charge and discharge simultaneously |
| 5 | Power limits | ≤ 100 kW rated (LUNA2000-200KWH-2H1) |
| 6 | Export limit | ≤ 50 kW to grid (50% of rated) |
| 7 | NMD constraint | Peak demand ≤ 1820 kVA |
| 8 | Load shedding | Force ≥ 10 kW discharge during LS intervals |

**Fallback:** If solver times out (10s) or returns INFEASIBLE, falls back to rules-based dispatch (charge off-peak, discharge peak, respect LS).

**TOU Tariff Rates:**
| Band | Rate (R/kWh) | Hours (SAST) |
|------|-------------|--------------|
| Off-peak | 0.649 | 22:00-05:59 |
| Standard | 1.2457 | 06:00-06:59, 10:00-17:59, 20:00-21:59 |
| Peak | 3.7641 | 07:00-09:59, 18:00-19:59 |

### Modbus BESS Writer

Async Modbus TCP writer for Huawei LUNA2000 charge/discharge setpoints.

- **Registers:** 37001 (charge_power, i32, scale ×1000), 37003 (discharge_power, i32, scale ×1000)
- **AEGIS gate:** `aegis_bess_writer_enabled=False` (Phase 0) blocks ALL Modbus writes
- **Write protocol:** Validate constraints → AEGIS gate → Modbus TCP write → read-back verify → JSONL audit
- **Watchdog:** 5-min timeout sends idle (0 kW) if no command received
- **Demo mode:** When `modbus_bess_ip=""` or `DEMO_MODE=true`, logs commands without TCP
- **Service:** `modbus_bess_writer.py` (singleton, async)

### Integration Flow

```
Every 15 minutes (background scheduler):
  LoadForecastService.get_forecast()     → 96 × 15-min demand predictions
  SolarForecastService.get_forecast()    → 96 × 15-min solar predictions
  MIPDispatchOptimizer.optimize()        → 96-slot optimal schedule (cached)

Every 5 minutes (dispatch cycle):
  SolarDispatchService reads current interval from cached MIP schedule
  Falls back to arbitrage engine if MIP unavailable
  BESSDispatchEngine validates constraints
  ModbusBESSWriter executes (AEGIS gate decides: blocked or live)
  JSONL audit trail persisted
```

### New API Endpoints (v26.0)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/load-forecast/{site_id}` | 96-interval load forecast |
| GET | `/api/load-forecast/{site_id}/accuracy` | RMSE, MAE, R² metrics |
| POST | `/api/load-forecast/{site_id}/retrain` | Trigger model retraining |
| GET | `/api/dispatch-optimizer/{site_id}/schedule` | Current optimal schedule |
| GET | `/api/dispatch-optimizer/{site_id}/compare` | MIP vs rules side-by-side |
| POST | `/api/dispatch-optimizer/{site_id}/solve` | Trigger fresh optimisation |

### Backend Services (v26.0 additions)

| Service | Purpose |
|---------|---------|
| `load_forecast_service.py` | GBR 15-min load forecast (8 features, 90-day training) |
| `mip_dispatch_optimizer.py` | CP-SAT solver (96-slot schedule, 10s timeout, rules fallback) |
| `modbus_bess_writer.py` | Async Modbus TCP writer (AEGIS-gated, watchdog, audit) |

### Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `ortools` | ≥9.8.0 | Google OR-Tools CP-SAT solver |
| `pymodbus` | ≥3.6.0 | Modbus TCP client for LUNA2000 |

### Tests

112 tests across 3 test files:
- `test_load_forecast_service.py` — 40 tests (training, forecast, caching, edge cases)
- `test_mip_dispatch_optimizer.py` — 36 tests (solver, constraints, fallback, comparison)
- `test_modbus_bess_writer.py` — 36 tests (AEGIS gate, demo mode, registers, watchdog)

## Related Documentation

- [Solar API Reference](../03-api-reference/solar-api.md)
- [Energy Centre Integration](../07-integrations/energy-centre.md)
- [Load Shedding Optimization](10-load-shedding-optimization.md)
- [MCP Tools Reference](../03-api-reference/mcp-tools-reference.md)
