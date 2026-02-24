---
title: "Solar & BESS API Reference"
type: "reference"
status: "approved"
version: "2.0.0"
created: "2026-02-06"
updated: "2026-02-24"
author: "SENTINEL Development Team"
tags: ["api", "solar", "pv", "bess", "dispatch", "compliance", "financial", "maintenance"]
domain: "solar"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 15
---

# Solar & BESS API Reference

REST API endpoints for solar PV monitoring, BESS dispatch, grid compliance, financial reporting, and maintenance scheduling. Implemented in Phase 34 (Solar & BESS Optimisation Module).

**Base path:** `/api/solar`

**Demo site:** `` (3.875 MWp, 33 inverters, 2 MWh BESS)

## Ingestion & Overview (34-01)

### GET `/api/solar/sites`

List all registered solar sites.

**Response:**
```json
[
  {
    "site_id": "",
    "name": " Office Park",
    "capacity_kwp": 3875,
    "inverter_count": 33,
    "has_bess": true,
    "has_generator": true
  }
]
```

### GET `/api/solar/sites/{site_id}/overview`

Get site overview with current generation, BESS SOC, grid flow, and performance ratio.

**Response:**
```json
{
  "site_id": "",
  "generation_kw": 2847.3,
  "daily_yield_kwh": 14250.0,
  "bess_soc_pct": 72.5,
  "grid_import_kw": 0.0,
  "grid_export_kw": 340.0,
  "performance_ratio": 0.847,
  "savings_today_zar": 4250.00,
  "plants": [...]
}
```

### GET `/api/solar/sites/{site_id}/inverters`

Get all inverters with current readings.

### GET `/api/solar/sites/{site_id}/inverters/{inverter_id}`

Get single inverter detail with string-level data.

### GET `/api/solar/sites/{site_id}/bess`

Get BESS container status (SOC, mode, power, health, alarms).

**Response:**
```json
{
  "site_id": "",
  "soc_pct": 72.5,
  "soh_pct": 96.2,
  "mode": "discharging",
  "power_kw": -450.0,
  "temperature_c": 28.3,
  "cycle_count": 847,
  "alarms": []
}
```

### GET `/api/solar/sites/{site_id}/meter`

Get grid meter readings (import/export, voltage, frequency, PF, THD).

### GET `/api/solar/sites/{site_id}/readings`

Get normalised readings filtered by `reading_type` and `equipment_type`.

### GET `/api/solar/sites/{site_id}/connectors`

Get health status of all manufacturer connectors.

## Performance Monitoring (34-02)

### GET `/api/solar/sites/{site_id}/performance`

Get Performance Ratio metrics.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | string | `day` | `day`, `week`, or `month` |

**Response:**
```json
{
  "performance_ratio": 0.847,
  "rating": "good",
  "target": 0.80,
  "period": "day",
  "generation_kwh": 14250.0,
  "irradiance_kwh_m2": 5.8,
  "trend": "stable"
}
```

### GET `/api/solar/sites/{site_id}/performance/inverters`

Get inverter peer comparison table with rankings.

### GET `/api/solar/sites/{site_id}/performance/strings`

Get string-level detail with anomaly flags (underperform, open circuit, short, MPPT fault).

### GET `/api/solar/sites/{site_id}/diagnostics`

Get full diagnostic report with prioritised issues.

**Response:**
```json
{
  "site_id": "",
  "health_status": "good",
  "issue_count": 3,
  "total_cost_impact_zar": 12500.0,
  "issues": [
    {
      "severity": "high",
      "category": "underperformance",
      "equipment_id": "INV-H07",
      "description": "Inverter H07 operating 12% below peer median",
      "probable_cause": "MPPT tracking fault on string 3",
      "recommended_action": "Inspect string 3 connections, check MPPT controller",
      "cost_impact_zar": 8500.0,
      "confidence": 0.87
    }
  ]
}
```

## Grid Compliance (34-03)

### GET `/api/solar/sites/{site_id}/compliance`

Get overall NRS 097-2-1 compliance status.

### GET `/api/solar/sites/{site_id}/compliance/voltage`

Get voltage compliance detail with violation history.

### GET `/api/solar/sites/{site_id}/compliance/frequency`

Get frequency compliance detail with violation history.

### GET `/api/solar/sites/{site_id}/compliance/power-quality`

Get power quality compliance (THD, PF, DC injection).

### GET `/api/solar/sites/{site_id}/compliance/export`

Get export limit compliance status (zero-export vs export cap).

### GET `/api/solar/sites/{site_id}/compliance/certificates`

Get NRS 097 certificate status and validity.

### GET `/api/solar/sites/{site_id}/compliance/report`

Generate full compliance report for SSEG submission.

### GET `/api/solar/sites/{site_id}/compliance/events`

Get compliance event log.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hours` | int | `24` | Time range for events |

## Energy Arbitrage & Dispatch (34-05)

### GET `/api/solar/sites/{site_id}/dispatch/schedule`

Get 24-hour BESS dispatch schedule (TOU optimised).

**Response:**
```json
{
  "site_id": "",
  "schedule": [
    {
      "hour": 6,
      "slot": "06:00-06:30",
      "mode": "charge",
      "target_soc_pct": 95,
      "tariff_band": "off_peak",
      "rate_zar": 0.89,
      "expected_savings_zar": 0.0
    },
    {
      "hour": 18,
      "slot": "18:00-18:30",
      "mode": "discharge",
      "target_soc_pct": 20,
      "tariff_band": "peak",
      "rate_zar": 3.21,
      "expected_savings_zar": 1240.00
    }
  ]
}
```

### GET `/api/solar/sites/{site_id}/dispatch/status`

Get current dispatch state (mode, SOC, savings).

### GET `/api/solar/sites/{site_id}/dispatch/log`

Get dispatch event history.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hours` | int | `24` | Time range (1-168) |

### GET `/api/solar/sites/{site_id}/arbitrage/savings`

Get arbitrage savings calculation.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | string | `day` | `day`, `week`, or `month` |

### GET `/api/solar/sites/{site_id}/tariff/current`

Get current City Power TOU tariff band and rate.

## Demand Management (34-06)

### GET `/api/solar/sites/{site_id}/demand/status`

Get current demand status with NMD headroom.

### GET `/api/solar/sites/{site_id}/demand/profile`

Get 15-minute demand profile.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | string | `day` | `day` or `week` |

### GET `/api/solar/sites/{site_id}/demand/nmd`

Get NMD compliance status with ratchet history.

### GET `/api/solar/sites/{site_id}/demand/savings`

Get demand charge savings from BESS peak shaving.

## Self-Consumption (34-06)

### GET `/api/solar/sites/{site_id}/selfconsumption`

Get self-consumption and self-sufficiency ratios.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | string | `day` | `day`, `week`, or `month` |

### GET `/api/solar/sites/{site_id}/energy-balance`

Get complete energy balance breakdown with 15-min intervals.

## Generation Forecast (34-07)

### GET `/api/solar/sites/{site_id}/forecast`

Get 72-hour generation forecast with confidence bands.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hours` | int | `24` | Forecast horizon (1-168) |

**Response:**
```json
{
  "site_id": "",
  "generated_at": "2026-02-06T10:00:00Z",
  "hours": [
    {
      "hour": "2026-02-06T11:00:00Z",
      "generation_kw": 2450.0,
      "confidence_high_kw": 2800.0,
      "confidence_low_kw": 2100.0,
      "clear_sky_kw": 3100.0,
      "cloud_factor": 0.79
    }
  ],
  "accuracy_7d": {
    "rmse_kw": 180.0,
    "rmse_pct": 6.2,
    "mae_kw": 140.0,
    "bias_pct": -1.3
  }
}
```

### GET `/api/solar/sites/{site_id}/forecast/accuracy`

Get forecast vs actual accuracy metrics (RMSE, MAE, bias).

## Generator Coordination (34-07)

### GET `/api/solar/sites/{site_id}/generator/status`

Get dispatch priority stack and generator need assessment.

### GET `/api/solar/sites/{site_id}/generator/avoidance`

Get diesel avoidance savings (hours, litres, ZAR).

### GET `/api/solar/sites/{site_id}/generator/events`

Get generator event log.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | string | `day` | `day`, `week`, or `month` |

## Health Analytics (34-08)

### GET `/api/solar/sites/{site_id}/health`

Get fleet health overview (degradation rates, BESS SoH, alerts).

### GET `/api/solar/sites/{site_id}/health/inverters/{inverter_id}`

Get single inverter health with degradation rate.

### GET `/api/solar/sites/{site_id}/health/bess`

Get BESS State-of-Health with rack-level detail.

### GET `/api/solar/sites/{site_id}/health/bess/cycles`

Get monthly BESS cycle history.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `months` | int | `12` | History depth (1-24) |

### GET `/api/solar/sites/{site_id}/health/degradation`

Get fleet-wide degradation ranking (all inverters).

### POST `/api/solar/sites/{site_id}/health/warranty-evidence/{equipment_id}`

Generate warranty evidence package for equipment.

## Maintenance Scheduling (34-09)

### GET `/api/solar/sites/{site_id}/maintenance/schedule`

Get 90-day maintenance calendar (PPM + condition-based).

### GET `/api/solar/sites/{site_id}/maintenance/recommendations`

Get current maintenance recommendations with priority.

**Response:**
```json
{
  "recommendations": [
    {
      "type": "inverter_service",
      "equipment_id": "INV-H07",
      "priority": "soon",
      "reason": "Runtime 16,200 hours (threshold: 15,000h)",
      "estimated_cost_zar": 4500.0,
      "next_due_date": "2026-03-01"
    },
    {
      "type": "panel_cleaning",
      "equipment_id": "PLANT-A",
      "priority": "routine",
      "reason": "Soiling loss estimated at 3.2% from PR decline",
      "estimated_cost_zar": 8000.0,
      "next_due_date": "2026-03-15"
    }
  ]
}
```

### POST `/api/solar/sites/{site_id}/maintenance/generate-work-orders`

Create work orders from urgent/soon recommendations. Uses existing work order service with Sentry notification.

## Financial Reporting (34-09)

### GET `/api/solar/sites/{site_id}/financial/monthly`

Get monthly financial report.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `month` | int | current | Month (1-12) |
| `year` | int | current | Year (2024-2030) |

**Response:**
```json
{
  "site_id": "",
  "month": 1,
  "year": 2026,
  "savings": {
    "arbitrage_zar": 42000.0,
    "demand_charge_zar": 28000.0,
    "self_consumption_zar": 35000.0,
    "diesel_avoidance_zar": 18000.0,
    "total_zar": 123000.0
  },
  "generation_kwh": 485000.0,
  "carbon_offset_kg": 460750.0
}
```

### GET `/api/solar/sites/{site_id}/financial/summary`

Get YTD financial summary with ROI.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | string | `ytd` | `ytd` |

### GET `/api/solar/sites/{site_id}/financial/carbon`

Get carbon offset report.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | string | `month` | `month` or `ytd` |

**Carbon factors:**
- Grid electricity: 0.95 kg CO2/kWh (Eskom emission factor)
- Diesel: 2.68 kg CO2/L

## MCP Tools

5 solar tools registered in SIMBIOT MCP server:

| Tool | Description |
|------|-------------|
| `get_solar_overview` | Current generation, BESS SOC, grid flow, PR, savings |
| `get_bess_status` | SOC, mode, health, power, cycles, dispatch schedule |
| `get_solar_savings` | Financial summary (YTD/monthly savings breakdown, ROI) |
| `get_solar_forecast` | 24-72h generation forecast with confidence bands |
| `get_solar_diagnostics` | Top issues, underperformers, maintenance recommendations |

All tools accept `site_id` parameter (default: `""`).

## Chat Tools

4 solar tools registered for Claude chat interface:

| Tool | Trigger Examples |
|------|-----------------|
| `get_solar_overview` | "How much solar did we generate today?" |
| `get_solar_savings` | "How much have we saved this month?" |
| `get_solar_diagnostics` | "Which inverters are underperforming?" |
| `get_solar_forecast` | "What's tomorrow's generation forecast?" |

## Peak Demand Management Integration (Phase 081)

The Solar module integrates with the Peak Demand Management system to optimize BESS dispatch for both TOU arbitrage and NMD compliance.

### NMD-Aware BESS Dispatch

When NMD headroom drops below 15% (warning level), BESS discharge is prioritized for peak shaving over TOU arbitrage:

```
Priority Hierarchy:
1. NMD Breach Prevention (CRITICAL - prevents R77k+/month penalties)
2. TOU Arbitrage (IMPORTANT - captures daily savings)
3. Comfort Optimization (NICE_TO_HAVE - thermal inertia allows flexibility)
```

**Scenario:** Current demand 5,500 kW, NMD 6,000 kVA (91% utilization):
- BESS discharge recommended: 200 kW for 60 minutes
- Estimated cost savings: R31,100/month (demand charge reduction)
- Decision engine: Prefers BESS discharge over charging during peak tariff

### Coordinator Integration

The Demand-Aware Coordinator (`backend/app/services/demand_aware_coordinator.py`) runs every 5 minutes to:
1. Query current demand vs NMD from buildings table
2. Check which modules are active (Solar, HVAC, Energy, etc.)
3. Generate multi-module recommendations if headroom < 15%
4. Coordinate BESS discharge with HVAC setpoint adjustments
5. Calculate combined cost savings

**Typical Coordination:**
- If Solar + HVAC both active:
  - Solar: Discharge BESS 200 kW (saves R31,100/month on demand)
  - HVAC: Increase chilled water setpoint +2°C (saves 5 kW load)
  - Combined: 250 kW reduction, R38,875/month savings

### NMD Data Sources

NMD limit is extracted from municipal electricity bills and stored in `buildings.nmd_limit_kva`:

**Primary Source (Preferred):**
- Site manager uploads City Power bill PDF
- SIMBIOT extracts NMD from bill (e.g., "6,000 kVA")
- Value persisted to database
- Last upload tracked: `buildings.bill_last_uploaded_at`

**Fallback (No Bill Available):**
- S002: 6,000 kVA (default)
- site-005: 8,000 kVA (default)

**See also:** [Municipal Billing API](municipal-billing.md) - Bill ingestion and NMD extraction

### API Integration

**Peak Demand Status:**
```bash
GET /api/peak-demand/S002/status
```
Returns: Current demand, NMD headroom, available modules for shaving

**Recommendations:**
```bash
GET /api/peak-demand/S002/recommendations
```
Returns: Multi-module actions with Solar/HVAC/Energy coordinated changes

**See also:** [Peak Demand API](peak-demand-api.md) - Complete reference

### Dashboard Integration

Solar dashboard shows:
- **Current Headroom Gauge:** NMD headroom %, color-coded (green/yellow/red)
- **Peak Risk Alert:** "Peak demand approaching NMD limit at 18:30" (if forecasted)
- **Shaving Recommendation Panel:** If multi-module recommendation available
  - BESS discharge: 200 kW for 60 min
  - HVAC adjustment: +2°C setpoint
  - "Approve" button triggers Tier 2 approval workflow

---

## Load Forecast (v26.0)

15-minute building load forecast using GradientBoostingRegressor.

**Base path:** `/api/load-forecast`

### GET `/api/load-forecast/{site_id}`

Get 96-interval (24h) load forecast with confidence bands.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `intervals` | int | `96` | Number of 15-min intervals (1-192) |

**Response:**
```json
{
  "site_id": "site-002",
  "generated_at": "2026-02-24T10:00:00Z",
  "intervals": [
    {
      "timestamp": "2026-02-24T10:00",
      "demand_kw": 1650.3,
      "confidence_high_kw": 1815.3,
      "confidence_low_kw": 1485.3,
      "tariff_band": "standard",
      "is_peak": false
    }
  ],
  "peak_demand_kw": 1850.0,
  "avg_demand_kw": 1420.0,
  "total_energy_kwh": 34080.0,
  "accuracy": {
    "rmse_kw": 120.5,
    "mae_kw": 95.2,
    "r2_score": 0.82,
    "training_samples": 8640
  }
}
```

### GET `/api/load-forecast/{site_id}/accuracy`

Get model accuracy metrics (RMSE, MAE, R²).

### POST `/api/load-forecast/{site_id}/retrain`

Trigger model retraining on fresh synthetic data.

**Response:**
```json
{
  "status": "retrained",
  "site_id": "site-002",
  "accuracy": { "rmse_kw": 118.3, "mae_kw": 92.1, "r2_score": 0.84 }
}
```

## MIP Dispatch Optimizer (v26.0)

CP-SAT optimised BESS dispatch scheduling — minimises energy cost + demand charge + battery degradation.

**Base path:** `/api/dispatch-optimizer`

### GET `/api/dispatch-optimizer/{site_id}/schedule`

Get the current optimal 96-interval dispatch schedule. Returns cached MIP solution if available, otherwise triggers a fresh solve.

**Response:**
```json
{
  "site_id": "site-002",
  "solver_status": "optimal",
  "generated_at": "2026-02-24T10:00:00Z",
  "solve_time_ms": 2340.5,
  "total_cost_zar": 8450.20,
  "peak_grid_import_kw": 1620.0,
  "total_energy_kwh": 28500.0,
  "total_solar_kwh": 12400.0,
  "cycles": 1.25,
  "demand_charge_zar": 2135.50,
  "degradation_cost_zar": 18.75,
  "intervals": [
    {
      "timestamp": "2026-02-24T00:00",
      "charge_kw": 85.0,
      "discharge_kw": 0.0,
      "soc_kwh": 120.5,
      "grid_import_kw": 1585.0,
      "solar_kw": 0.0,
      "load_kw": 1500.0,
      "tariff_rate": 0.649,
      "tariff_band": "off_peak",
      "interval_cost_zar": 257.30
    }
  ]
}
```

**Solver status values:**
| Status | Meaning |
|--------|---------|
| `optimal` | CP-SAT found provably optimal solution |
| `feasible` | CP-SAT found a feasible (not proven optimal) solution within timeout |
| `rules_fallback` | Solver failed/infeasible — used rules-based heuristic |

### GET `/api/dispatch-optimizer/{site_id}/compare`

Compare MIP-optimised vs rules-based dispatch side by side.

**Response:**
```json
{
  "site_id": "site-002",
  "mip": { "...schedule..." },
  "rules": { "...schedule..." },
  "savings_zar": 1240.50,
  "savings_pct": 12.8,
  "mip_peak_kw": 1620.0,
  "rules_peak_kw": 1780.0
}
```

### POST `/api/dispatch-optimizer/{site_id}/solve`

Trigger a fresh MIP optimisation solve with current forecasts.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `initial_soc_kwh` | float | `100.0` | Initial BESS state of charge (0-200 kWh) |

### POST `/api/dispatch-optimizer/kill-switch`

Emergency stop for BESS hardware control. Executes 4 actions in sequence:

1. Send idle command to BESS (power → 0)
2. Close AEGIS write gate (runtime override)
3. Switch to simulation mode (runtime override)
4. Disconnect Modbus TCP connection

**Response:**
```json
{
  "status": "killed",
  "timestamp": "2026-02-24T14:30:00Z",
  "actions": [
    "idle_command_sent",
    "aegis_gate_closed",
    "mode_switched_to_simulation",
    "modbus_disconnected"
  ],
  "errors": [],
  "message": "BESS kill switch activated. All writes disabled. Mode: simulation."
}
```

**Notes:**
- Each action is independent — partial failures don't prevent other safety actions
- Idempotent: safe to call multiple times
- Always ends with gate CLOSED + mode SIMULATION
- Audit log records `who=operator_kill_switch`

---

## Related Documentation

- [Solar & BESS Module Feature Doc](../04-features/34-solar-bess-module.md)
- [Peak Demand Management API](peak-demand-api.md) - Full API reference (Phase 081)
- [Municipal Billing API](municipal-billing.md) - NMD bill extraction
- [MCP Tools Reference](mcp-tools-reference.md)
- [Energy Centre Integration](../07-integrations/energy-centre.md)
