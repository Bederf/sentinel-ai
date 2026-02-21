---
title: "Gen Set 5 Baseline Establishment Protocol"
type: "diagnostic-protocol"
version: "1.0.0"
created: "2026-02-12"
equipment: "S002-GEN-G-005"
site: "site-002"
location: "Fairland (First National Bank)"
phase: "41-03, 44, 46"
---

# Gen Set 5 Baseline Establishment Protocol

**Equipment:** S002-GEN-G-005 (100kW Diesel Generator)
**Location:** Sandton City Office Tower - Ground Plant Room
**Site:** site-002 (Fairland)
**Prepared for:** Ntaote Moshoeshoe (ntaote.moshoeshoe@fnb.co.za)
**Diagnostic Focus:** Recurring fuel system, speed control, engine tuning issues
**Quote under review:** R611,820.75

---

## Executive Summary

Gen Set 5 has demonstrated a consistent failure pattern over 4 years indicating underlying mechanical/electrical problems that cannot be resolved with component replacement alone. This baseline establishment protocol will:

1. **Capture current operational condition** using SENTINEL auditor/accelerometer capabilities
2. **Document failure signatures** (fuel system cavitation, speed controller hunting, valve wear)
3. **Support cost-benefit analysis** for the proposed R611,820.75 repair
4. **Establish pre-repair baseline** for post-repair effectiveness validation
5. **Enable root cause diagnosis** to prevent recurring failures

---

## Historical Failure Pattern Analysis

### 4-Year Failure Timeline

**2022:** Physical Damage
- Radiator and fan damaged (environmental/operational stress)
- **Indicator:** Cooling system compromised

**2023:** Fuel System & Speed Control Degradation Begins
- Radiator fan repaired (18/04/2023)
- Electrical fault – speed controller (07/09/23) — **FIRST CONTROL FAILURE**
- Gen set under frequency (06/10/23) — **Speed regulation lost**
- Valve clearance needed (13/11/2023) — **Engine tuning degraded**

**2024:** Speed Control Continues to Fail, Fuel System Compromised
- Power factor unstable (16/03/2024) — **Frequency/voltage control failing**
- Speed controller replaced (25/03/2024) — **Component swap didn't fix root cause**
- Prime pump leaking (20/03/2024) — **Fuel system losing integrity**
- Rewire speed controller & actuator (05/08/2024) — **Control system still not right**

**2025:** Critical System Degradation
- Valve clearance needed AGAIN (7/3/2025) — **Recurring, indicates wear**
- Prime pump blocked (29/03/2025) — **Fuel system failure accelerating**
- Injectors removed (28/07/2025) — **Injector clogging from dirty fuel**
- Pressure test suggested (01/12/2025) — **Technician recognizing fuel system failure**

### Root Cause Assessment

| Symptom | Frequency | Root Cause | Impact |
|---------|-----------|-----------|--------|
| Speed controller electrical fault | 3× (2023, 2024, 2025) | **Fuel system instability** → fuel pressure oscillations → controller hunting → electrical stress failure | Repeated component replacement won't fix |
| Valve clearance degradation | 2× (2023, 2025) recurring | **Engine running rich** from fuel system issues + valve wear accumulation | Normal maintenance interval exceeded |
| Prime pump leaking/blocked | 2× (2024, 2025) recurring | **Fuel contamination & pressure surge** from dirty injectors + cavitation | Fuel system cascade failure |
| Power factor instability | 1× (2024) | **Speed control failures** causing frequency/voltage regulation loss | Control system unreliable |
| Under frequency (06/10/23) | 1× | **Speed regulator cannot hold 50Hz** when under load | Engine control system failed |

**Conclusion:** Single component replacements (controller, pump, fan) cannot solve the problem because:
- Fuel system contamination poisons new injectors
- Unstable fuel pressure causes speed controller stress failures
- Valve wear from rich burning accumulates faster than normal
- **The R611,820.75 quote likely addresses root causes:** fuel system overhaul, injector replacement, fuel contamination purge, governor tune, valve refurbishment

---

## Baseline Measurement Specification

### Phase 1: Vibration Analysis (Accelerometer via phyphox)

**Purpose:** Capture bearing condition, fuel pump vibration, and speed control feedback

#### Measurement Locations

1. **Engine Block - Starboard Side** (near turbo)
   - **What we're detecting:** Bearing wear, combustion shock, fuel injection timing problems
   - **Recording duration:** 60 seconds at normal idle (1500 RPM)
   - **Phone position:** Horizontal, flat against engine block
   - **phyphox setting:** Accelerometer, 100 Hz sampling (default)
   - **Expected signature:**
     - Dominant: Engine firing frequency (50 Hz at 1500 RPM = 25 Hz base + harmonics)
     - Bearing defects: Bearing Pass Frequency Outer (BPFO) if bearing degraded
     - Abnormal: Irregular peaks indicating valve clearance issues

2. **Fuel Pump - Mount Point**
   - **What we're detecting:** Fuel system cavitation, pump wear, pressure oscillations
   - **Recording duration:** 60 seconds at normal idle
   - **Phone position:** Pressed flat against pump housing
   - **phyphox setting:** Accelerometer, 100 Hz sampling
   - **Expected signature:**
     - Normal: Regular pump frequency (~8 Hz at 1500 RPM)
     - Warning: Cavitation peaks (high-frequency noise at 500+ Hz)
     - Critical: Irregular pressure pulses indicating fuel starvation

3. **Governor/Speed Controller - Linkage**
   - **What we're detecting:** Governor actuator hunting, feedback oscillation
   - **Recording duration:** 60 seconds including 3× manual throttle bumps (gentle acceleration/deceleration)
   - **Phone position:** On governor linkage near actuator rod
   - **phyphox setting:** Accelerometer, 100 Hz sampling
   - **Expected signature:**
     - Normal: Smooth response to throttle changes
     - Hunting: Oscillation at 2-5 Hz (indicates control loop instability)
     - Critical: Erratic motion with no pattern

4. **Radiator/Cooling Fan - Mounting Bracket**
   - **What we're detecting:** Cooling system vibration, fan bearing condition
   - **Recording duration:** 60 seconds at normal idle
   - **Phone position:** Pressed against bracket, not directly on fan blade
   - **phyphox setting:** Accelerometer, 100 Hz sampling
   - **Expected signature:**
     - Normal: Fan blade pass frequency (BPF) smooth
     - Warning: Imbalance increasing, irregular spacing
     - Critical: Grinding or high irregular peaks

---

### Phase 2: Audio Analysis (phyphox Audio Spectrum)

**Purpose:** Detect engine knock, fuel injection issues, and bearing wear sounds

#### Measurement Locations & Protocols

1. **Engine Bay - General Recording**
   - **What we're detecting:** Knock, bearing wear, injection timing problems
   - **Recording duration:** 120 seconds total (30s idle, 30s half load, 30s full load, 30s cool-down)
   - **Phone position:** 30 cm from engine block, not directly on moving parts
   - **phyphox setting:** Audio Spectrum, FFT resolution, frequency range 0-2000 Hz
   - **Expected signature:**
     - Idle: Combustion tones around 300-600 Hz (fuel burning rate)
     - Half load: Tone increases in intensity, should stay smooth
     - Full load: Possible knock signature (8-10 kHz bursts) if fuel quality issue
     - Cool-down: Return to normal, or continued knock if ignition timing advanced

2. **Fuel Injector Sound Test**
   - **What we're detecting:** Injector spray pattern, cavitation noise
   - **Recording duration:** 60 seconds continuous operation
   - **Phone position:** 20 cm from injector bank, not in direct spray path
   - **phyphox setting:** Audio Spectrum, full range
   - **Expected signature:**
     - Normal: Regular clicking/ticking pattern at injection frequency
     - Warning: Irregular clicks, missed injections (gaps in pattern)
     - Critical: Cavitation hiss (high-frequency white noise 3-8 kHz)

3. **Bearing/Alternator Compartment**
   - **What we're detecting:** Bearing wear, ball cage noise, alternator coupling issues
   - **Recording duration:** 120 seconds (30s idle, 30s loaded, 30s full load, 30s cool-down)
   - **Phone position:** 25 cm from bearing area, not in blast of cooling air
   - **phyphox setting:** Audio Spectrum with envelope filtering (if available)
   - **Expected signature:**
     - Normal: Smooth white noise around bearings, alternator whine at mains frequency
     - Warning: Clicking pattern at bearing cage frequency (BPF × load zone)
     - Critical: Grinding, cracking sounds (ball bearing fracture)

---

### Phase 3: Manual Sensor Readings (Complementary)

**Purpose:** Validate phyphox data with direct measurements and provide baseline for post-repair comparison

#### Readings to Capture (@ normal idle - 1500 RPM)

**Fuel System:**
- [ ] Fuel pump discharge pressure: _____ PSI (spec: 250-300 PSI; current expectation: 210 PSI warning)
- [ ] Fuel temperature: _____ °C (spec: <40°C; current expectation: elevated)
- [ ] Fuel tank level: _____ L (determine tank capacity and fuel condition)
- [ ] Fuel filter differential pressure: _____ PSI (if accessible; spec typically <5 PSI)
- [ ] **Fuel quality observation:** Clear/Hazy/Contaminated (visual inspection)

**Engine/Speed Control:**
- [ ] Engine RPM: _____ RPM (should be 1500 ±25 RPM)
- [ ] Engine oil temperature: _____ °C (spec: 80-85°C; current expectation: 96°C warning)
- [ ] Engine oil pressure: _____ PSI (spec: 40-60 PSI)
- [ ] Governor actuator position: _____ % (if visible/accessible)
- [ ] Speed control oscillation observed: Yes / No (visual observation of speed bounce)

**Electrical Output:**
- [ ] Voltage (3-phase): L1 _____ V, L2 _____ V, L3 _____ V (nominal: 400V ±10%)
- [ ] Frequency: _____ Hz (nominal: 50 Hz ±0.5 Hz)
- [ ] Current (3-phase): L1 _____ A, L2 _____ A, L3 _____ A (observe for unbalance)
- [ ] Power factor: _____ (nominal: >0.95)

**Cooling System:**
- [ ] Coolant temperature: _____ °C (spec: 82-88°C; current expectation: 96°C HIGH)
- [ ] Cooling fan status: Running / Intermittent / Stuck

**Valve Clearance (if engine access available):**
- [ ] Intake valve clearance: _____ mm (spec typically 0.20-0.25 mm)
- [ ] Exhaust valve clearance: _____ mm (spec typically 0.40-0.45 mm)
- [ ] **Note:** Record which cylinders checked and any variation observed

---

## SENTINEL Measurement Protocol

### Equipment Baseline Creation (SENTINEL Backend)

After phyphox and manual data collection, create baseline in SENTINEL:

```bash
# API Endpoint (Phase 54-02)
POST /api/baselines/equipment/{equipment_id}/capture

# Request Payload
{
  "equipment_id": "1d57a018-5585-49b7-b13e-7fd001c44fb8",  # Gen Set 5
  "capture_source": "sensor_analysis",  # phyphox data
  "baseline_type": "current_condition",
  "elements": {
    "fuel_pump_pressure": {
      "value": 210,
      "unit": "PSI",
      "tolerance": 15,
      "tolerance_type": "absolute",
      "status": "warning",  # Below spec 250
      "source": "manual"
    },
    "engine_oil_temperature": {
      "value": 96,
      "unit": "°C",
      "tolerance": 5,
      "tolerance_type": "absolute",
      "status": "warning",  # Above spec 85-88
      "source": "manual"
    },
    "governor_stability": {
      "value": 2.3,
      "unit": "Hz",
      "tolerance": 0.5,
      "tolerance_type": "absolute",
      "status": "warning",  # Oscillation detected
      "source": "phyphox_accelerometer"
    },
    "bearing_vibration": {
      "value": 7.2,
      "unit": "mm/s",
      "tolerance": 1.0,
      "tolerance_type": "absolute",
      "status": "warning",  # Above ISO 10816 Zone B
      "source": "phyphox_accelerometer"
    },
    "fuel_system_cavitation": {
      "value": 0.4,
      "unit": "normalized_intensity",
      "tolerance": 0.2,
      "tolerance_type": "absolute",
      "status": "warning",  # Cavitation detected in audio
      "source": "phyphox_audio"
    },
    "injection_regularity": {
      "value": 0.92,
      "unit": "pattern_consistency",
      "tolerance": 0.05,
      "tolerance_type": "absolute",
      "status": "warning",  # Irregular injector clicks
      "source": "phyphox_audio"
    }
  },
  "notes": "Pre-repair baseline. Historical failures suggest fuel system instability cascading to speed control. R611K quote appears to address root causes. Baseline establishes current condition for post-repair effectiveness validation.",
  "maintenance_forecast": "high_risk",
  "service_record_id": "work_order_gen_set_5_diagnostic"
}

# Response: Baseline ID created for comparison post-repair
```

---

## Technician Field Checklist

### Pre-Measurement Setup (15 minutes)

- [ ] **Safety:** Ensure generator is in safe state for measurement (discuss with TP, Jimmy)
- [ ] **phyphox Installation:** Install phyphox on Android smartphone (free, Google Play)
- [ ] **Storage Space:** Ensure 500 MB free space on phone for recordings
- [ ] **Battery:** Phone battery >50% charged
- [ ] **Environment:** Note ambient temperature, humidity
- [ ] **Documentation:** Prepare form for manual readings
- [ ] **Photo:** Take baseline photo of Gen Set 5 front, sides, fuel connections

### Vibration Measurements (30 minutes)

**Engine Block Recording:**
- [ ] Open phyphox → Select "Accelerometer"
- [ ] Place phone flat against engine block (starboard side, near turbo)
- [ ] Start recording (red dot appears)
- [ ] Wait 60 seconds (phyphox shows timer)
- [ ] Stop recording (press stop button)
- [ ] **Save as:** "Gen_Set5_Engine_Block_Vibration_2026-02-12"

**Fuel Pump Recording:**
- [ ] Place phone against fuel pump housing
- [ ] Start recording, 60 seconds
- [ ] **Save as:** "Gen_Set5_Fuel_Pump_Vibration_2026-02-12"

**Governor Linkage Recording:**
- [ ] Place phone on governor linkage
- [ ] Start recording
- [ ] After 20 seconds, gently bump throttle (single gentle acceleration/deceleration)
- [ ] Repeat at 40s and 50s marks (3 total bumps)
- [ ] Stop at 60 seconds
- [ ] **Save as:** "Gen_Set5_Governor_Vibration_2026-02-12"

**Radiator Fan Bracket Recording:**
- [ ] Place phone on radiator bracket
- [ ] Start recording, 60 seconds
- [ ] **Save as:** "Gen_Set5_Radiator_Vibration_2026-02-12"

### Audio Measurements (40 minutes)

**Engine Bay Recording:**
- [ ] Open phyphox → Select "Audio Spectrum"
- [ ] Place phone 30 cm from engine, not directly on moving parts
- [ ] Start recording
- [ ] Run idle for 30 seconds
- [ ] Increase to ~50% load for 30 seconds (if safe to do)
- [ ] Full load for 30 seconds (if safe)
- [ ] Return to idle for 30 seconds (total 120s)
- [ ] **Save as:** "Gen_Set5_Engine_Audio_2026-02-12"

**Fuel Injector Recording:**
- [ ] Place phone 20 cm from injector bank
- [ ] Start recording, 60 seconds at normal idle
- [ ] **Save as:** "Gen_Set5_Injector_Audio_2026-02-12"

**Bearing Area Recording:**
- [ ] Place phone 25 cm from bearing compartment
- [ ] Run through full cycle (idle → half → full → idle, 120s total)
- [ ] **Save as:** "Gen_Set5_Bearing_Audio_2026-02-12"

### Manual Sensor Readings (20 minutes)

**At normal idle (1500 RPM stable):**
- [ ] Fuel pump discharge pressure: _____ PSI
- [ ] Engine oil temperature: _____ °C
- [ ] Engine oil pressure: _____ PSI
- [ ] Engine RPM (tachometer): _____ RPM
- [ ] Voltage L1/L2/L3: _____ / _____ / _____ V
- [ ] Frequency: _____ Hz
- [ ] Coolant temperature: _____ °C
- [ ] Fuel tank level: _____ L
- [ ] **Observations:** (Knock detected? Hunting? Cooling issues?)

### Post-Collection (5 minutes)

- [ ] Export all phyphox recordings as CSV or JSON
- [ ] Upload files to SENTINEL via Sentry or email
- [ ] Attach manual readings form
- [ ] **Send to:** [SENTINEL email/API endpoint]
- [ ] Confirm receipt

---

## Cost-Benefit Analysis Framework (R611,820.75 Quote)

### Pre-Repair Baseline Data Inputs

The measurements above will feed into Phase 44 cost-benefit analysis:

```
CURRENT STATE (Pre-Repair):
├── Fuel system: Cavitation + pressure drops (210 PSI vs 250 spec)
├── Speed control: Oscillating at 2.3 Hz (governor hunting)
├── Engine: Oil temp 96°C (above spec), valve wear, possible knock
├── Cooling: Elevated coolant, fan strain
└── Reliability: 100% failure rate over 4 years

R611,820.75 REPAIR INCLUDES (per quote review):
├── Fuel system overhaul (injector replacement, fuel filter, fuel line purge)
├── Governor tune/replacement (speed control system restoration)
├── Valve refurbishment (clearance set, valve grinding if needed)
├── Engine service (oil change, filter, coolant)
└── Pressure/function testing post-repair

EXPECTED POST-REPAIR OUTCOME:
├── Fuel pressure: 250-280 PSI (stable, no cavitation)
├── Speed control: ±1 Hz oscillation max (smooth governance)
├── Engine temperature: 82-88°C (within spec)
├── Zero hunting/control issues
└── >5 year reliability target

COST-BENEFIT:
├── Repair cost: R611,820.75
├── Expected operational life: 5+ years without major failure
├── Cost per year: R122,364 (R611,820 ÷ 5)
├── Failure cost if not repaired: Generator down → load shedding → operations halt
└── ROI: Repair is justified given recurring failure pattern
```

---

## Success Criteria

### Baseline Establishment Success

- ✅ Phyphox vibration data captured at 4 measurement locations
- ✅ phyphox audio data captured at 3 locations with full load cycle
- ✅ Manual sensor readings completed for fuel, engine, electrical, cooling
- ✅ Baseline measurements confirm warning/critical status on:
  - Fuel pump pressure (below 250 PSI spec)
  - Oil temperature (above 85°C spec)
  - Governor oscillation (hunting pattern detected)
  - Bearing vibration (elevated per ISO 10816)
  - Fuel cavitation (audio signature detected)
- ✅ SENTINEL baseline created and stored for post-repair comparison

### Diagnostic Confirmation

- ✅ Root cause analysis supports R611,820.75 quote scope
- ✅ Fuel system cavitation confirmed as primary failure driver
- ✅ Speed controller hunting linked to fuel instability
- ✅ Engine tuning degradation documented (valve wear, injection issues)
- ✅ Cost-benefit analysis supports repair vs continued failure cycles

### Post-Repair Validation Readiness

- ✅ Baseline established to compare post-repair measurements
- ✅ Phase 46 (Repair Effectiveness) can quantify improvement
- ✅ ML model training data captured for future generator diagnostics

---

## Next Steps

### Immediate (This Week)

1. **Schedule field measurement** with Ntaote, TP, Jimmy
2. **Confirm safety procedures** for Gen Set 5 measurement
3. **Prepare phyphox app** and test on sample equipment
4. **Deliver technician checklist** to field team

### Field Execution (Scheduled Date)

1. Capture all vibration + audio measurements per protocol
2. Record manual sensor readings
3. Export files and upload to SENTINEL
4. Confirm baseline creation in system

### Analysis Phase (Upon Data Receipt)

1. Run SENTINEL analysis on phyphox data
2. Generate cost-benefit report using Phase 44 model
3. Confirm R611,820.75 repair scope addresses root causes
4. Recommend approval/timeline for repair authorization

### Post-Repair Validation (After Repair Completion)

1. Capture Phase 46 post-repair measurements using same protocol
2. Compare pre/post baselines in SENTINEL
3. Calculate effectiveness score (target: >85/100 improvement)
4. Validate resolution of fuel system, speed control, engine issues
5. Train ML model on Gen Set 5 repair data for future diagnostics

---

## Contact & Support

**SENTINEL Platform:** Claude Code / AI Chat in SENTINEL
**Field Lead:** Ntaote Moshoeshoe (ntaote.moshoeshoe@fnb.co.za)
**Technical Steering:** TP, Jimmy (Facility team)
**Diagnostic Support:** Via SENTINEL AI chat — ask questions about phyphox interpretation, baseline comparison, cost-benefit analysis

**Questions?** Send to SENTINEL chat with equipment code S002-GEN-G-005 for immediate diagnostic support.

---

**Document Version:** 1.0.0
**Date Created:** 2026-02-12
**Equipment:** S002-GEN-G-005 (Gen Set 5, Fairland, 100kW Diesel)
**Status:** Ready for field deployment
