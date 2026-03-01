---
title: "Load Shedding Optimization"
type: "feature"
status: "implemented"
version: "1.0.0"
created: "2026-02-03"
updated: "2026-02-03"
author: "SENTINEL Development Team"
tags: ["load-shedding", "eskom", "optimization", "hvac", "thermal", "south-africa"]
domain: "energy"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
phase: "10"
---

# Load Shedding Optimization

South African load shedding optimization with thermal runway visualization, pre-cooling strategies, and generator coordination.

## Overview

Phase 10 implements SENTINEL's unique South African value proposition:
- **Plan 10-01**: Backend thermal model and EskomSePush simulation
- **Plan 10-02**: Frontend optimization panel with thermal runway chart
- **Plan 10-03**: Full integration with dashboard

## The "Wow" Moment

SENTINEL's thermal runway visualization shows how pre-cooling extends comfort during outages:

```
Temperature (°C)
    28 ┤                                    ╱ Without Pre-cooling
       │                                  ╱   (52 min to breach)
    26 ┤                               ╱
       │                            ╱
    24 ┤                         ╱
       │─────────────────────╱─────── Comfort Limit (24°C)
    22 ┤                   ╱     ╲
       │                ╱          ╲ With Pre-cooling
    20 ┤─────────────╱               ╲ (108 min to breach)
       │           ╱                   ╲
    18 ┤        ╱                        ╲
       │─────────────────────────────────────────────────────
       0      30      60      90     120     150 minutes
              │                       │
         Pre-cooling             Outage Ends
          Starts
```

**Result:** 56 minutes of additional comfort time (107% improvement)

## API Endpoints

### Eskom Status

```bash
# Get current load shedding status
GET /api/optimization/eskom-status

Response:
{
  "current_stage": 4,
  "next_stages": [
    {"stage": 4, "start_time": "16:00", "end_time": "18:30"},
    {"stage": 2, "start_time": "20:00", "end_time": "22:30"}
  ],
  "area_schedules": {
    "gateway-theatre": {
      "next_outage": "16:00",
      "duration_minutes": 150,
      "stage": 4
    }
  },
  "last_updated": "2026-02-03T14:00:00Z"
}
```

### Site-Specific Schedule

```bash
GET /api/optimization/eskom-status/gateway-theatre

Response:
{
  "site_id": "gateway-theatre",
  "site_name": "Gateway Theatre",
  "schedule": {
    "next_outage": "16:00",
    "duration_minutes": 150,
    "stage": 4,
    "area": "Centurion Block 15"
  }
}
```

### Thermal Runway Calculation

```bash
POST /api/optimization/thermal-runway
Content-Type: application/json

{
  "site_id": "gateway-theatre",
  "current_temp": 22.0,
  "comfort_limit": 24.0,
  "outage_duration_minutes": 150,
  "include_precooling": true
}

Response:
{
  "without_precooling": {
    "time_to_breach_minutes": 52,
    "final_temp": 27.3,
    "comfort_maintained": false
  },
  "with_precooling": {
    "time_to_breach_minutes": 108,
    "final_temp": 24.8,
    "comfort_maintained": true,
    "precooling_schedule": [
      {"time": "14:00", "action": "Lower setpoint to 18°C"},
      {"time": "14:30", "action": "Start additional AHU"},
      {"time": "15:45", "action": "Pre-charge thermal mass"}
    ]
  },
  "improvement": {
    "minutes_gained": 56,
    "percent_improvement": 107
  },
  "thermal_curve": {
    "labels": ["0", "30", "60", "90", "120", "150"],
    "without_precooling": [22, 23.2, 24.5, 25.8, 26.5, 27.3],
    "with_precooling": [18, 19.5, 21.0, 22.5, 24.0, 24.8]
  }
}
```

### Zone-Aware Analysis (Phase 10.1)

```bash
POST /api/optimization/analyze-load-shedding
Content-Type: application/json

{
  "site_id": "site-002",
  "load_shedding_stage": 4
}

Response:
{
  "stage": 4,
  "zones_affected": 12,
  "zones_maintained": 3,
  "priority_zones": [
    {"zone": "Server Room L2-A", "priority": 1, "action": "Maintain cooling"},
    {"zone": "Executive Suite L3-B", "priority": 2, "action": "Reduce to 24°C"}
  ],
  "savings_kwh": 45.2,
  "comfort_impact": "minimal"
}
```

## Thermal Model

### Building Parameters

| Parameter | Description | Demo Value |
|-----------|-------------|------------|
| `thermal_mass` | Heat storage capacity | 0.8 |
| `insulation_factor` | Heat retention | 0.6 |
| `internal_heat_gain` | Equipment/people load | 0.5 kW/m² |

### Temperature Calculation

```python
def calculate_temperature(
    current_temp: float,
    outside_temp: float,
    building_params: dict,
    time_minutes: int
) -> float:
    """
    Simplified thermal model for demo.

    ΔT = (T_outside - T_inside) × heat_transfer + internal_gain
    """
    heat_transfer = (1 - building_params["insulation_factor"]) / 60
    internal_gain = building_params["internal_heat_gain"] * 0.1

    delta_t = (outside_temp - current_temp) * heat_transfer + internal_gain
    return current_temp + (delta_t * time_minutes)
```

## Pre-Cooling Strategy

### Timeline

| Time | Action | Energy Impact |
|------|--------|---------------|
| T-120 min | Lower setpoint to 18°C | +15% cooling |
| T-90 min | Start additional AHUs | +10% cooling |
| T-30 min | Pre-charge thermal mass | +5% cooling |
| T-15 min | Stage generator | Standby |
| T-0 | Outage begins | Cooling stops |
| T+108 min | Comfort limit reached | vs 52 min without |

### Energy Trade-off

| Metric | Without Pre-cooling | With Pre-cooling |
|--------|---------------------|------------------|
| Pre-outage energy | 0 kWh | +18 kWh |
| Comfort duration | 52 min | 108 min |
| Generator runtime | 98 min | 42 min |
| Generator fuel | 45 liters | 19 liters |
| **Net savings** | - | **26 liters fuel** |

## Demo Scenarios

Three pre-configured scenarios in `optimization_scenarios.json`:

### 1. Gateway Theatre (Hero Demo)
- Stage 4, 150-minute outage
- 56-minute comfort extension
- 26 liters fuel saved
- R850 cost savings

### 2. Sandton City
- Stage 2, 120-minute outage
- 54-minute comfort extension
- Medium complexity

### 3. Centurion Mall
- Stage 3, 150-minute outage
- Multiple chillers
- Generator coordination

## Zone Priority System (Phase 10.1)

### Zone Types

| Zone Type | Priority | Description |
|-----------|----------|-------------|
| `server_room` | P1 | Critical - Never reduce cooling |
| `executive` | P2 | Important - 50% setpoint change |
| `banking_hall` | P2 | Customer-facing - Maintain comfort |
| `open_office` | P3 | Standard - Normal optimization |
| `meeting_room` | P4 | Flexible - Wider setpoint range |
| `lobby` | P5 | Lowest - Maximum flexibility |

### Load Shedding Stages

| Stage | Zones Maintained |
|-------|------------------|
| 1 | P1, P2, P3, P4 |
| 2 | P1, P2, P3 |
| 3 | P1, P2 |
| 4 | P1 only |

## Implementation

**Services:**
- `backend/app/services/thermal_model.py` - Thermal calculations
- `backend/app/services/ai_optimizer.py` - Optimization recommendations

**API:**
- `backend/app/api/optimization.py` - Optimization endpoints

**Data:**
- `backend/app/data/optimization_scenarios.json` - Demo scenarios

**Frontend:**
- `frontend/src/components/intelligence/EnergyIntelligenceCard.tsx` - Overview tab compact card
- `frontend/src/components/OptimizationPanel.tsx` - Main panel
- `frontend/src/components/ThermalRunwayChart.tsx` - Visualization
- `frontend/src/components/PrecoolingSchedule.tsx` - Timeline
- `frontend/src/pages/OptimizationPage.tsx` - Full page view (3 tabs: Load Shedding, Profile, Validation)

## Business Value

| Metric | Value |
|--------|-------|
| Energy savings | 8-12% on cooling costs |
| Comfort extension | 45+ minutes during outages |
| Generator fuel reduction | 15-25% |
| Estimated monthly savings | R15,000-R25,000 per building |

## ML Integration (Phase 132)

Load shedding optimization benefits from the ML Context Injection pipeline:

- **LSTM forecasts** provide predicted temperature trajectories, improving thermal runway accuracy
- **Anomaly scores** flag equipment that may underperform during load shedding (e.g., degraded chiller)
- **Fault classifications** help the AI Optimizer avoid recommending pre-cooling via equipment with active faults

See [ML Data Architecture](../02-architecture/ML-DATA-ARCHITECTURE.md) and [ML Context Injection](../08-ai-ml/ai-recommendation-system.md#ml-context-injection-phase-132) for details.

## Related Documentation

- [Device Control & Safety](06-device-control-safety.md)
- [Autonomous Decision Engine](09-autonomous-decisions.md)
- [AI Recommendation System](../08-ai-ml/ai-recommendation-system.md)
- [ML Data Architecture](../02-architecture/ML-DATA-ARCHITECTURE.md)
- [South Africa Context](../14-south-africa-context/load-shedding-optimization.md)
