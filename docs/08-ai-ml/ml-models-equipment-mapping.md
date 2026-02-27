---
title: "SENTINEL ML Model Specifications & Equipment Type Mapping"
type: "technical-reference"
status: "active"
version: "2.1.0"
created: "2026-02-10"
updated: "2026-02-27"
author: "SENTINEL Development Team"
tags: ["ml", "lstm", "autoencoder", "models", "equipment-type", "predictions", "registry", "database-driven"]
domain: "ai-ml"
audience: ["developers", "data-scientists", "operations", "devops"]
complexity: "advanced"
estimated_read_time: 40
changes: "Phase 68-03: Database-driven ML registry, async infrastructure, multi-site support, 23 equipment types"
---

# SENTINEL ML Model Specifications & Equipment Type Mapping

Complete specifications for SENTINEL's ML models and equipment type mapping system. Used by the ML inference engine to determine which predictive models apply to discovered equipment and generate equipment-specific health scores and maintenance recommendations.

> **Phase 132 (2026-02-27):** ML model outputs are now injected into Claude's optimisation prompt via `_gather_ml_context()` in `ai_optimizer.py`. This bridges trained models to the AI Recommendation Engine. See [AI Recommendation System — ML Context Injection](./ai-recommendation-system.md#ml-context-injection-phase-132) and [ML Data Architecture](../02-architecture/ML-DATA-ARCHITECTURE.md).

## Database-Driven ML Registry (Phase 68-03)

**Architecture:** Supabase-driven configuration replaces hardcoded models, enabling multi-site support and graceful degradation.

### Registry Overview

| Component | Location | Purpose |
|-----------|----------|---------|
| **ml_models** | Supabase table | Trained model versions (LSTM, autoencoder), paths, performance metrics (R²) |
| **model_thresholds** | Supabase table | Confidence thresholds per equipment type (Tier 2: advisory, Tier 3: auto-execute) |
| **model_registry_db.py** | Backend service | Async database-driven registry with caching (1-hour TTL) |
| **NiagaraMLInference** | Backend service | Async inference engine that queries Supabase for models/thresholds |

### Multi-Site Equipment Coverage (Current)

| Site | Items | Types | ML Coverage | Rules Fallback | Notes |
|------|-------|-------|-------------|----------------|-------|
| **S002** | 26 | 12 | 21% (6 items) | 79% | Office building |
| **S005** | 90 | 15 | 56% (50 items) | 44% | Hospital with LIFT, JACE, COLD, MEDGAS |
| **S012** | 19 | 7 | 79% (15 items) | 21% | Office building |
| **TOTAL** | 135 | 23 | 48% (65 items) | 52% | Multi-site production |

### Active ML Models (Tier 2 Recommendations)

| Equipment Type | Instances | R² Score | Tier 2 | Tier 3 | Status |
|---|---|---|---|---|---|
| **CHILLER** | 4 | 0.6065 | 0.70 | 0.85 | ✅ Active |
| **AHU** | 30 | 0.4915 | 0.70 | 0.85 | ✅ Active |
| **FCU** | 8 | 0.4236 | 0.70 | 0.85 | ✅ Active |
| **UPS** | 4 | 0.4144 | 0.70 | 0.85 | ✅ Active |
| **GENERATOR** | 14 | 0.3710 | 0.85 | 0.95 | ✅ Active (elevated) |
| **DALI** | 4 | N/A | 0.70 | 0.85 | ✅ Placeholder |

### Disabled Equipment Types (Rules Fallback)

Equipment without trained ML models uses graceful degradation: `threshold=1.0` (impossible to meet) → disables recommendations but doesn't break system.

- **Hospital-specific** (Site 005): LIFT (12), JACE (10), COLD (3), MEDGAS (1), BOILER (2), KEF (2), MSB (3), DB (2)
- **General-purpose**: PUMP (5), METER (6), BESS (1), CT (9), SPLIT (4), INV (4), FIRE (4), ACC, CCTV, VAV (3)

### Graceful Degradation Strategy

```
Equipment without ML model:
  1. threshold = 1.0 (impossible to meet)
  2. Recommendations automatically DISABLED
  3. System falls back to rule-based predictions
  4. No errors, no data loss
  5. Ready for upgrade when model trained

When model trained:
  1. Add to ml_models table
  2. Update threshold to normal (0.70/0.85)
  3. Recommendations automatically ENABLED
  4. Live within minutes (cache expires)
```

---

## Model Architecture Overview

SENTINEL uses a dual-model approach for each equipment type:

### 1. LSTM (Long Short-Term Memory) Model
**Purpose:** Predictive maintenance - detect degradation trends early

- **Architecture:** Bidirectional LSTM, 128 units per layer, 2 layers
- **Input:** 30-day rolling window of key performance indicators
- **Output:** Remaining Useful Life (RUL) prediction, 0-365 days
- **Training data:** 3+ years of equipment telemetry + failure records
- **Retraining:** Monthly (automatic via MLOps pipeline)

### 2. Autoencoder Model
**Purpose:** Anomaly detection - identify abnormal operating patterns

- **Architecture:** Symmetric encoder-decoder, 64→32→16→32→64 units
- **Input:** Current performance metrics (normalized)
- **Output:** Reconstruction error score, 0-1 scale
- **Threshold:** 0.3 = normal, 0.3-0.6 = warning, >0.6 = critical anomaly
- **Retraining:** Weekly (automatic)

---

## Equipment Type 1: Chiller (HVAC)

### Installed Instances
- Siemens Desigo centrifugal chillers (primary)
- CAREL refrigeration controllers
- Carrier AquaEdge
- Daikin magnetic bearing chillers

### Key Performance Indicators (KPIs)

```
Input Time Series (normalized 0-1):
  ├─ chw_supply_temp           (°C, setpoint variance)
  ├─ chw_return_temp           (°C, delta-T efficiency)
  ├─ compressor_outlet_pressure (kPa, efficiency indicator)
  ├─ compressor_power_draw     (kW, power consumption)
  ├─ cooling_load_percent      (%, estimated via delta-T)
  ├─ condenser_fan_speed       (%, adaptive cooling)
  ├─ superheat_actual          (K, refrigerant efficiency)
  ├─ condenser_pressure        (kPa, fouling indicator)
  ├─ motor_vibration           (mm/s, bearing condition)
  └─ oil_return_temp           (°C, lubrication condition)

Prediction Horizon: 30-90 days
```

### LSTM Model Specifications

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Input window** | 30 days @ 15-min intervals | Balance: enough history, not too stale |
| **Output horizon** | 60-90 days | Time for technician to schedule maintenance |
| **Training data** | 3 years (1,095 days) | Captures seasonal variations + 2 complete failures |
| **Batch size** | 32 samples | Memory efficiency on edge devices |
| **Learning rate** | 0.001 (Adam optimizer) | Stable convergence |
| **Validation split** | 20% | Prevent overfitting |
| **Early stopping** | Patience=5 epochs | Stop if val loss not improving |
| **Performance** | MAE = 8.3 days, RMSE = 12.1 days | Typical prediction error: ±12 days |

### Autoencoder Model Specifications

| Parameter | Value |
|-----------|-------|
| **Encoder layers** | 64 → 32 → 16 |
| **Bottleneck** | 16 units |
| **Decoder layers** | 16 → 32 → 64 |
| **Activation** | ReLU (hidden), Linear (output) |
| **Anomaly threshold** | Reconstruction error > 0.3 |
| **Training data** | 2 years of normal operation |
| **Sensitivity** | 0.89 (true positive rate) |
| **Specificity** | 0.92 (true negative rate) |

### Chiller Health Score Calculation

```
Health Score = 0-100 (100 = new, 0 = failed)

Components:
  1. Age Factor (15% weight):
     health_age = 100 - (equipment_age_years / expected_life_years) × 100
     expected_life = 20 years for centrifugal

  2. Performance Degradation (30% weight):
     COP_baseline = 5.2 (typical for this model at full load)
     COP_current = measured efficiency
     health_perf = (COP_current / COP_baseline) × 100
     Capped at 100 to handle anomalies

  3. RUL Prediction (35% weight):
     if RUL_days > 1000: health_rul = 100
     if RUL_days > 365: health_rul = 90
     if RUL_days > 90: health_rul = 70
     if RUL_days > 30: health_rul = 40
     if RUL_days <= 30: health_rul = 10

  4. Anomaly Score (20% weight):
     if reconstruction_error < 0.3: health_anom = 100
     if reconstruction_error < 0.6: health_anom = 50
     if reconstruction_error >= 0.6: health_anom = 10

  Final Score:
    health_score = (health_age × 0.15) + (health_perf × 0.30)
                 + (health_rul × 0.35) + (health_anom × 0.20)
```

### Maintenance Recommendations Trigger

```
When health_score <= 60 AND RUL_days <= 90:
  Priority: HIGH
  Recommendation: "Schedule major maintenance within 60 days"
  Action: Generate work order for bearing/seal inspection

When RUL_days <= 30:
  Priority: CRITICAL
  Recommendation: "Equipment failure likely within 30 days; arrange emergency maintenance"
  Action: Alert facility manager immediately

When reconstruction_error > 0.6:
  Priority: CRITICAL
  Recommendation: "Anomaly detected; possible sensor malfunction or bearing failure"
  Action: Request on-site technical assessment
```

---

## Equipment Type 2: AHU (Air Handling Unit)

### Installed Instances
- Supply air handling units (50-200 kW)
- Return air processing units
- Mixed air control via AHU

### Key Performance Indicators

```
Input Time Series:
  ├─ supply_air_temperature    (°C, control accuracy)
  ├─ return_air_temperature    (°C, building ambient)
  ├─ mixed_air_temperature     (°C, damper control)
  ├─ supply_fan_speed_percent  (%, energy consumption)
  ├─ supply_fan_pressure_delta (Pa, filter fouling)
  ├─ outdoor_air_percent       (%, economizer position)
  ├─ supply_humidity           (%, dehumidification)
  ├─ motor_current             (Amps, bearing friction)
  ├─ filter_pressure_drop      (Pa, replacement countdown)
  └─ belt_tension              (N, wear indicator, optional)

Prediction Horizon: 14-30 days (faster failure modes than chiller)
```

### LSTM Model Specifications

| Parameter | Value |
|-----------|-------|
| **Input window** | 14 days @ 15-min intervals |
| **Output horizon** | 14-30 days |
| **Training data** | 2 years (730 days) |
| **Performance** | MAE = 2.4 days, RMSE = 4.1 days |
| **Primary failure mode** | Filter clogging, motor bearing degradation |

### Autoencoder Model Specifications

| Parameter | Value |
|-----------|-------|
| **Bottleneck** | 8 units (smaller than chiller) |
| **Anomaly threshold** | Reconstruction error > 0.4 |
| **False positive rate** | 5-8% (higher sensitivity) |
| **Training data** | 18 months of normal operation |

### AHU Health Score Calculation

```
health_score components (different weighting from chiller):
  1. Age Factor (10% weight): Same as chiller (20-year life)
  2. Filter Fouling (25% weight):
     filter_health = 100 - (pressure_drop_percent / max_pressure) × 100
     When pressure drop > 80%: health_filter = 20 (replacement imminent)
  3. Motor Bearing (25% weight):
     vibration_health = 100 - sqrt(measured_vibration / alarm_threshold) × 100
  4. RUL Prediction (25% weight): Similar algorithm to chiller
  5. Anomaly Score (15% weight): Similar to chiller

Final Score: Weighted average of 5 components
```

### Filter Replacement Prediction

AHU includes **filter replacement scheduling**:
```
When pressure_drop > 60 Pa:
  Priority: MEDIUM
  Recommendation: "Schedule filter replacement within 7 days"
  Est. savings: Prevents fan motor overload in 2-3 weeks

When pressure_drop > 80 Pa:
  Priority: HIGH
  Recommendation: "Filter replacement urgent; replace within 24 hours"
  Est. risk: Motor overload, energy consumption +30%
```

---

## Equipment Type 3: FCU / VAV (Zone Control)

### Installed Instances
- VAV boxes (perimeter + core zones)
- FCU units (4-pipe fan coil)
- Hydronic zone controllers

### Key Performance Indicators

```
Input Time Series:
  ├─ zone_temp_setpoint        (°C, comfort target)
  ├─ zone_temp_actual          (°C, measured)
  ├─ damper_position_feedback  (%, actuator health)
  ├─ airflow_measured          (CFM, or inferred from damper)
  ├─ reheat_valve_position     (%, heating mode)
  ├─ zone_occupancy            (binary, load indicator)
  └─ actuator_response_time    (sec, mechanical wear)

Prediction Horizon: 7-14 days (zone equipment fails quickly when it fails)
```

### LSTM Model Specifications

| Parameter | Value |
|-----------|-------|
| **Input window** | 7 days @ 15-min intervals |
| **Output horizon** | 7-14 days |
| **Training data** | 1.5 years (aggregated across 100+ zones) |
| **Performance** | MAE = 1.2 days, RMSE = 2.3 days |
| **Primary failure modes** | Actuator stiffness, damper mechanism jam |

### Autoencoder Model Specifications

| Parameter | Value |
|-----------|-------|
| **Bottleneck** | 6 units (smallest for simple equipment) |
| **Anomaly threshold** | Reconstruction error > 0.35 |
| **Training data** | 1 year of zone data (all buildings) |

### VAV Health Score Calculation

```
health_score components:
  1. Age Factor (8% weight): 15-year typical life
  2. Actuator Response (35% weight):
     response_time_baseline = 90 seconds (spec)
     health_actuator = 100 - min((response_time - 90) / 90, 1.0) × 100
     If response_time > 180 sec: health = 20 (replacement soon)
  3. Damper Stiction (30% weight):
     stiction = difference between measured and commanded position
     When stiction > 15%: health = 50 (erratic control)
     When stiction > 25%: health = 10 (failure imminent)
  4. Temperature Control Quality (15% weight):
     deviation_from_setpoint_history
     High variance → indicates damper issues
  5. RUL Prediction (12% weight):
     Based on stiction trend + response time trend

Final Score: Weighted average
```

### Maintenance Recommendations

```
When stiction increases >5% over 7 days:
  Priority: MEDIUM
  Recommendation: "Actuator showing wear; plan replacement within 4-6 weeks"

When response_time > 180 seconds:
  Priority: HIGH
  Recommendation: "Actuator unresponsive; replace within 1 week"

When stiction > 25% AND temperature_deviation > 2°C:
  Priority: CRITICAL
  Recommendation: "Zone control failing; emergency replacement required"
  Action: Generate work order immediately
```

---

## Equipment Type 4: Pump (Central Station)

### Installed Instances
- Chilled water supply pumps
- Chilled water return pumps
- Condenser water pumps

### Key Performance Indicators

```
Input Time Series:
  ├─ pump_flow_rate            (m³/hr, hydraulic performance)
  ├─ pump_discharge_pressure   (bar, resistance increase)
  ├─ pump_motor_current        (Amps, bearing friction, cavitation)
  ├─ pump_vibration            (mm/s, bearing condition)
  ├─ pump_inlet_pressure       (bar, cavitation indicator)
  ├─ motor_temperature         (°C, winding health)
  └─ seal_leakage              (ml/hr, mechanical seal wear)

Prediction Horizon: 14-30 days
```

### LSTM Model Specifications

| Parameter | Value |
|-----------|-------|
| **Input window** | 21 days @ 15-min intervals |
| **Output horizon** | 21-60 days |
| **Training data** | 2.5 years |
| **Performance** | MAE = 4.1 days, RMSE = 6.7 days |
| **Primary failure mode** | Bearing wear, seal degradation, impeller erosion |

### Autoencoder Model Specifications

| Parameter | Value |
|-----------|-------|
| **Bottleneck** | 12 units |
| **Anomaly threshold** | 0.32 |
| **Cavitation detection** | Vibration spike + pressure drop simultaneous |

### Pump Health Score Calculation

```
health_score components:
  1. Bearing Condition (40% weight):
     vibration_alarm_threshold = 7.1 mm/s (ISO 20816)
     health_bearing = 100 - (vibration_actual / 7.1) × 100
     When vibration > 7.1 mm/s: health = 0 (failed)

  2. Seal Condition (25% weight):
     seal_age = months since last replacement (typically 24 mo)
     leakage_rate_trend = increasing? degrading?
     health_seal = 100 - (seal_age / 24) × 100
     Trend analysis: if leakage increasing, reduce by 20%

  3. Motor Condition (20% weight):
     current_above_rated = indicates friction increase
     temp_rise = winding temperature rise above baseline
     health_motor = 100 - (temp_rise / max_allowable) × 100

  4. Efficiency (15% weight):
     flow_vs_curve = compare current to pump curve
     Degradation indicates impeller erosion

Final Score: Weighted average
```

### Maintenance Triggers

```
When vibration trend increasing:
  Priority: MEDIUM → HIGH (depending on rate)
  Recommendation: "Bearing wear detected; plan replacement within 6-8 weeks"

When leakage exceeds 5 ml/hr:
  Priority: MEDIUM
  Recommendation: "Mechanical seal degrading; replacement within 4-8 weeks"

When cavitation pattern detected (pressure drop + current spike):
  Priority: HIGH
  Recommendation: "Cavitation occurring; check inlet pressure, filter, suction line"
  Note: Can cause rapid impeller erosion if not addressed
```

---

## Equipment Type 5: Valve (Modulating Control)

### Installed Instances
- Chilled water control valves
- Reheat water valves
- Condenser water bypass valves

### Key Performance Indicators

```
Input Time Series:
  ├─ valve_command_percent     (%, what was requested)
  ├─ valve_position_feedback   (%, where it actually is)
  ├─ pressure_drop_across_valve (bar, flow control)
  ├─ flow_through_valve        (m³/hr, calculated or measured)
  └─ actuator_current          (Amps, motor load)

Prediction Horizon: 7-21 days
```

### LSTM Model Specifications

| Parameter | Value |
|-----------|-------|
| **Input window** | 7 days @ 15-min intervals |
| **Training data** | 1.5 years |
| **Performance** | MAE = 0.8 days, RMSE = 1.6 days |
| **Primary failure mode** | Stiction (sticking-slip), cartridge wear, seat erosion |

### Autoencoder Model Specifications

| Parameter | Value |
|-----------|-------|
| **Bottleneck** | 5 units (simple equipment) |
| **Anomaly threshold** | 0.3 |

### Valve Health Score Calculation

```
health_score components:
  1. Stiction Detection (50% weight):
     stiction = |command - feedback| when command changes
     Expected stiction: <2% on new valve
     health_stiction = 100 - min(stiction / 10, 1.0) × 100
     When stiction > 10%: health = 20 (failure soon)

  2. Response Time (30% weight):
     response_time = time for valve to reach 95% of new position
     Typical: 30-60 seconds
     health_response = similar to VAV actuator calculation

  3. Leakage (20% weight):
     shutoff_leakage = flow when valve commanded 0%
     If leakage detected: health = 40 (cartridge needs replacement)

Final Score: Weighted average
```

---

## Equipment Type 6: Cooling Tower

### Installed Instances
- Open loop evaporative cooling towers
- Closed circuit coolers (dry/wet hybrid)

### Key Performance Indicators

```
Input Time Series:
  ├─ cooling_tower_outlet_temp (°C, effective cooling)
  ├─ entering_water_temp       (°C, load)
  ├─ outdoor_wet_bulb          (°C, environmental limit)
  ├─ fan_speed_percent         (%, energy + air delivery)
  ├─ fan_vibration             (mm/s, blade condition)
  ├─ fouling_index             (scaled 0-1, water quality)
  └─ pump_bypass_flow          (%, cooling capacity)

Prediction Horizon: 30-60 days
```

### LSTM Model Specifications

| Parameter | Value |
|-----------|-------|
| **Input window** | 30 days @ hourly intervals (less frequent than central equipment) |
| **Training data** | 3 years |
| **Performance** | MAE = 5.8 days, RMSE = 9.2 days |
| **Primary failure mode** | Fouling, blade erosion, bearing failure |

### Autoencoder Model Specifications

| Parameter | Value |
|-----------|-------|
| **Bottleneck** | 8 units |
| **Anomaly threshold** | 0.35 |

### Cooling Tower Health Score Calculation

```
health_score components:
  1. Fouling Level (40% weight):
     fouling_index = measured vs theoretical cooling capacity
     health_fouling = 100 - (fouling_index × 100)
     Clean tower: fouling = 0%, health = 100
     Fouled tower: fouling = 20-40%, health = 60-80
     Severely fouled: fouling > 50%, health < 50

  2. Fan Condition (30% weight):
     vibration + blade erosion patterns
     Similar to pump bearing assessment

  3. Age & Maintenance (20% weight):
     Water treatment history
     Last chemical cleaning date

  4. Seasonal Efficiency (10% weight):
     Compare to wet-bulb envelope

Final Score: Weighted average
```

### Maintenance Triggers

```
When fouling_index > 0.15:
  Priority: MEDIUM
  Recommendation: "Chemical cleaning recommended within 2-4 weeks"
  Est. benefit: 10-15% energy recovery, improved chiller performance

When fouling_index > 0.25:
  Priority: HIGH
  Recommendation: "Chemical cleaning urgent; chiller performance degraded"
  Note: Can force chiller into less efficient part-load zone
```

---

## Equipment Type 7: Generator (Backup Power)

### Installed Instances
- Diesel backup generators
- Generator automatic transfer switches

### Key Performance Indicators

```
Input Time Series:
  ├─ runtime_total_hours       (cumulative, maintenance schedule)
  ├─ load_profile              (%, utilization)
  ├─ fuel_consumption_rate     (liters/hour, engine efficiency)
  ├─ coolant_temperature       (°C, engine stress)
  ├─ exhaust_temperature       (°C, combustion quality)
  ├─ oil_pressure              (bar, lubrication health)
  └─ transfer_switch_operations (count, mechanical wear)

Prediction Horizon: 60-180 days (generators have long degradation curves)
```

### LSTM Model Specifications

| Parameter | Value |
|-----------|-------|
| **Input window** | 60 days @ daily intervals (low-frequency equipment) |
| **Training data** | 3+ years |
| **Performance** | MAE = 12.3 days, RMSE = 18.7 days |
| **Primary failure mode** | Fuel system degradation, valve carbon buildup |

### Autoencoder Model Specifications

| Parameter | Value |
|-----------|-------|
| **Bottleneck** | 10 units |
| **Anomaly threshold** | 0.38 |
| **Periodic operation**: Generators operate infrequently; models trained on both steady and transient states

### Generator Health Score Calculation

```
health_score components:
  1. Maintenance Schedule Adherence (35% weight):
     runtime_hours vs recommended service intervals (500 hr = service)
     health_maintenance = 100 if compliant, degrades if overdue

  2. Fuel System (25% weight):
     fuel_contamination_indicator (based on consumption efficiency)
     Recent fuel top-up vs tank age (old fuel = gums)
     health_fuel = 100 - (fuel_degradation_score × 100)

  3. Engine Condition (25% weight):
     oil_pressure_trend (declining pressure = bearing wear)
     exhaust_temp_trend (rising temp = valve carbon, combustion issues)
     health_engine = 100 - sqrt(oil_pressure_drop + exhaust_temp_rise)

  4. Transfer Switch (15% weight):
     operation_count / expected_lifetime_ops
     health_switch = 100 - (ops / lifetime) × 100

Final Score: Weighted average (typically 70-90 for inactive units)
```

### Maintenance Triggers

```
When runtime_hours > service_interval + 50 hours:
  Priority: MEDIUM
  Recommendation: "Scheduled maintenance overdue; plan service within 2 weeks"
  Note: Impacts emergency readiness if failure occurs

When fuel_degradation detected:
  Priority: MEDIUM
  Recommendation: "Fuel system maintenance (drain, filter, fuel conditioner)"

When oil_pressure declining trend:
  Priority: HIGH
  Recommendation: "Bearing wear detected; plan major overhaul within 4-8 weeks"
```

---

## Sentry Bot Integration: Model Selection Algorithm

When Sentry Bot discovers new equipment, it selects appropriate models:

```python
def select_models_for_equipment(equipment_type, manufacturer, model):
    """
    Determine which LSTM and Autoencoder models to use for discovered equipment.

    Returns: (lstm_model_id, autoencoder_model_id, health_score_algo)
    """

    model_mapping = {
        'chiller': ('lstm-chiller-v2.1', 'ae-chiller-v1.3', 'health_chiller'),
        'ahu': ('lstm-ahu-v2.0', 'ae-ahu-v1.2', 'health_ahu'),
        'fcu': ('lstm-fcu-v1.9', 'ae-fcu-v1.1', 'health_fcu'),
        'vav': ('lstm-fcu-v1.9', 'ae-fcu-v1.1', 'health_fcu'),  # Same as FCU
        'pump': ('lstm-pump-v2.2', 'ae-pump-v1.4', 'health_pump'),
        'valve': ('lstm-valve-v1.8', 'ae-valve-v1.0', 'health_valve'),
        'cooling_tower': ('lstm-cwtower-v1.7', 'ae-cwtower-v1.2', 'health_cwtower'),
        'generator': ('lstm-gen-v1.6', 'ae-gen-v1.1', 'health_generator'),
    }

    return model_mapping.get(equipment_type, None)
```

---

## Performance Summary Table

```
Equipment Type | LSTM MAE | LSTM RMSE | AE Sensitivity | AE Specificity | Primary Failure
───────────────┼──────────┼───────────┼────────────────┼────────────────┼─────────────────
Chiller        | 8.3 days | 12.1 days | 89%            | 92%            | Bearing wear
AHU            | 2.4 days | 4.1 days  | 91%            | 94%            | Filter clogging
FCU/VAV        | 1.2 days | 2.3 days  | 87%            | 89%            | Actuator stiction
Pump           | 4.1 days | 6.7 days  | 88%            | 91%            | Seal degradation
Valve          | 0.8 days | 1.6 days  | 85%            | 88%            | Cartridge wear
Cooling Tower  | 5.8 days | 9.2 days  | 86%            | 90%            | Fouling
Generator      | 12.3 days| 18.7 days | 82%            | 87%            | Fuel degradation
```

---

## Continuous Improvement

Models are retrained automatically:
- **LSTM**: Monthly (capture seasonal patterns, new failure modes)
- **Autoencoder**: Weekly (adapt to equipment aging)
- **Health scores**: Recalculated daily (real-time updates)

Training data sources:
- Customer telemetry (aggregated, anonymized)
- Maintenance records (failure annotations)
- Weather data (external factors)
- Control system logs (actuator movements)

---

## References

- [Device Abstraction Layer](../02-architecture/device-abstraction-layer.md)
- [Hybrid AI Routing](./hybrid-ai-routing.md)
- [ML Equipment Support](../02-architecture/ml-equipment-support.md)
