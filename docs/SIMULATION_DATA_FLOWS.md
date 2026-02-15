# Simulation Data Flows — Solar & DALI Architecture

## Overview

Two simulation engines already generate building data that we should build on:

1. **Solar Annual Simulation** ✅ Complete 365-day profile (hourly)
2. **Lifecycle Orchestrator** ✅ 24-hour to 365-day events + recommendations
3. **DALI System** ✅ Real-time occupancy + daylight sensors

---

## ☀️ SOLAR ANNUAL SIMULATION

### Output Structure

**HourlySnapshot** (8,760 items):
```python
{
  "hour": 0-8759,
  "solar_gen_kw": 0-500,        # Varies by season
  "building_load_kw": 200-800,  # HVAC + lights + equipment
  "bess_soc_pct": 0-100,        # Battery charge state
  "bess_charge_kw": 0-100,
  "bess_discharge_kw": 0-100,
  "grid_import_kw": 0-500,      # Imported from grid
  "grid_export_kw": 0-500,      # Exported to grid
  "tariff_band": "peak|standard|off_peak",
}
```

### Actual vs Optimized Comparison

```
Two Baselines per Month:

1. total_cost_standard_ems_zar
   = TOU energy charges + peak demand charge
   = Assuming reactive control (no optimization)
   = FIXED for each month (same weather, different tariff)

2. total_cost_sentinel_ai_zar  
   = Same calculation BUT consumption reduced by learning_factor
   = Month 1: 2% savings
   = Month 6: 14% savings
   = Month 12: 18% savings
```

**Learning Curve (3 Phases):**
- Phase 1 (Month 1-2): 2% → 5% (Basic TOU arbitrage)
- Phase 2 (Month 3-6): 8% → 14% (Predictive dispatch)
- Phase 3 (Month 7-12): 16% → 18% (Full optimization)

### Time Resolution
**Hourly** — 8,760 data points = 365 days × 24 hours

### Annual Output Example
```
total_solar_kwh: 5,881,253
total_grid_import_kwh: 3,200,000
total_self_consumption_kwh: 2,900,000
total_cost_standard_ems_zar: R3,050,000
total_cost_sentinel_ai_zar: R2,645,000  (13% savings)
annual_savings_zar: R405,000
```

---

## 💡 DALI SYSTEM (Lighting + Occupancy)

### Output Structure

**Real-time sensor data (not a simulation):**
```python
{
  "sensor_id": "S002-DALI-L2-01-sen-001",
  "zone_id": "Zone-101",
  "occupancy": true/false,       # PIR detects movement
  "lux_level": 0-1000,           # Daylight ambient
  "daylight_setpoint": 500,      # Target lux for harvesting
  "luminaires": [                # Lights in zone
    {
      "luminaire_id": "...",
      "power_w": 15,
      "brightness_pct": 100
    }
  ]
}
```

### Potential Optimization Rules

```
If occupancy=false for 15+ min → brightness = 0 (off)
If lux > 500 → brightness = 30% (daylight harvest)
If lux > 200 → brightness = 60%
After 18:00 → only respond to motion (no continuous operation)

Estimated Savings: 40-50% of lighting energy
```

### Time Resolution
**Real-time** — Sensor polls every 1-2 seconds

### Integration with HVAC
**Occupancy context for HVAC:**
- DALI PIR sensors show zone occupancy %
- HVAC rules use this for zone temperature setpoints
- Example: "Zone occupancy 15% → can reduce AHU flow to 40%"

---

## 🎯 LIFECYCLE ORCHESTRATOR (Events + Recommendations)

### Output Structure

**LifecycleEvent per simulated hour:**
```python
{
  "timestamp": "2025-02-15T10:00:00",
  "simulated_hour": 10,
  "event_type": "AI_OPTIMIZATION",
  "equipment_id": "S002-CHILLER-B1-001",
  "description": "Adjust chiller setpoint",
  "details": {
    "action": "Adjust chiller setpoint",
    "current_setpoint": 6.5,
    "recommended_setpoint": 5.0,
    "energy_savings_kwh": 8.5,
    "confidence_score": 0.87
  }
}
```

### Available Scenarios

**For base package comparison:**
- `grant_hvac_only_7day` — AC baseline (always on)
- `grant_hvac_dali_7day` — Basic occupancy control
- `grant_hvac_dali_ai_7day` — AI optimization
- `grant_hvac_dali_ai_annual` — Full year with seasonal faults

### Recommendation Types

**HVAC Optimization:**
```
- Chiller staging: Load balance across units
- Setpoint pre-cooling: Start cooling early for peak
- Occupancy-based: Adjust zones by PIR occupancy %
- Peak-shaving: Shift loads off peak tariff
```

**DALI Optimization:**
```
- Daylight harvesting: Dim based on lux level
- Occupancy-based: Off when no motion for 15+ min
- Time-based: Off after hours unless motion
```

---

## 🔗 How To Build Energy Comparison Card

### Data Flow

```
ACTUAL CONSUMPTION (from simulation or real BMS):
  solar_annual_simulations.building_load_kwh per hour
  × actual occupancy (from DALI PIR)
  × actual solar generation (affects BESS dispatch)
  = Baseline: 245 kWh/day

OPTIMIZED CONSUMPTION (rules engine):
  building_load (baseline) 
  - HVAC optimization rules:
    × Chiller staging bonus (-%5)
    × Setpoint reduction -%3)
    × Occupancy scheduling (-%2)
  - DALI optimization rules:
    × Daylight harvesting (-%4)
    × Occupancy-based scheduling (-%3)
  = Optimized: 213 kWh/day

DELTA = 245 - 213 = 32 kWh
Savings = 32 kWh × R5/kWh = R160
```

### Implementation

1. **Extract Rules from Orchestrator**
   - Move `_generate_hvac_recommendation()` logic → RulesEngine service
   - Move `_generate_dali_recommendation()` logic → RulesEngine service
   - Both already calculate energy_savings_kwh + confidence

2. **Create API Endpoint**
   ```
   GET /api/energy/optimised-consumption?site_id=site-002&date=2025-02-15
   
   Returns:
   {
       "actual_kwh": 245,
       "optimised_kwh": 213,
       "delta_kwh": 32,
       "delta_rand": 160,
       "by_system": {
           "hvac": {"delta": 35},
           "lighting": {"delta": 7},
           "other": {"delta": -10}
       },
       "rules_applied": ["chiller_staging", "pre_cooling", "occupancy_schedule"],
       "confidence": 0.78,
       "method": "rules-based"  // Later: "ml-refined"
   }
   ```

3. **Rules Engine Operates on:**
   - Building state (zone temps, occupancy, daylight)
   - Scenario type (emergency, comfort-focused, efficiency-focused)
   - Time of day + day of week
   - Outdoor weather (from SeasonalModeler)
   - Equipment capacity and setpoint limits

4. **Frontend Card Shows:**
   - Actual vs Sentinel headline (R160 daily savings)
   - By-system breakdown (HVAC, lighting, other)
   - Which rules were applied (transparency)
   - Confidence score (builds trust over time)

---

## ✨ Why This Approach Works

### Reuses What's Working
- **Solar simulation hourly structure** → Already proven
- **Orchestrator recommendation logic** → Already validates against equipment
- **DALI sensor data** → Already streaming real occupancy
- **Learning curve pattern** → Already shows ML progression

### Single Source of Truth
- Rules engine source: Orchestrator (same logic as lifecycle simulation)
- Building state source: Current BMS readings (or simulation playback)
- Occupancy source: DALI PIR sensors (real-time or simulated)
- Result: Consistent recommendations whether in simulation or live

### Scales from Demo to Production
- **Month 1**: Rules-based estimation (rules-based confidence ~0.75)
- **Month 3**: ML model refines parameters (confidence ~0.82)
- **Month 6**: Highly accurate to building (confidence ~0.92)
- **Same API endpoint** returns progressively refined estimates

---

## What's Already There vs What Needs Building

✅ **Already Built:**
- Solar hourly simulation (building_load_kw as baseline)
- DALI sensor integration (occupancy + daylight)
- Lifecycle orchestrator recommendations (HVAC + lighting rules)
- Learning curve pattern (2% → 18% over 12 months)

⚠️ **Needs Implementation:**
- Rules engine service (extract from orchestrator)
- API endpoint for daily optimization comparison
- Frontend energy comparison card
- ML model integration (for later refinement)

---

See Also: `CLAUDE_ARCHITECTURE.md` (system design), `CLAUDE_EQUIPMENT_TYPES.md` (equipment naming)
