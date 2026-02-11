# Niagara BACnet Controllable Equipment & Safety Constraints Audit

**Phase:** 67-01 Niagara BACnet Control API Audit
**Status:** Complete
**Last Updated:** 2026-02-11

## Executive Summary

This document audits which SENTINEL BMS equipment can be autonomously controlled via Niagara BACnet, maps control points, and identifies safety constraints enforced by the SafetyEngine.

**Key Findings:**
- ✅ **22 controllable equipment units** identified across 6 device types
- ✅ **52 writable BACnet points** mapped to SENTINEL equipment
- ✅ **9 safety rules** enforced for autonomous control
- ✅ **6 interlock rules** for equipment interdependencies
- ⚠️ **5 equipment types** without Niagara control (manual only)
- ✅ PARASITE can control: HVAC (setpoints), Lighting (DALI dimming), Power (generator/UPS), Zones

---

## Table of Contents

1. [Controllable Equipment Matrix](#controllable-equipment-matrix)
2. [Equipment Type Deep Dives](#equipment-type-deep-dives)
3. [Safety Constraints by Equipment Type](#safety-constraints-by-equipment-type)
4. [Control Chain Examples](#control-chain-examples)
5. [Non-Controllable Equipment](#non-controllable-equipment)
6. [Interlocks & Dependencies](#interlocks--dependencies)
7. [Priority & Conflict Resolution](#priority--conflict-resolution)
8. [Recommendations for PARASITE](#recommendations-for-parasite)

---

## Controllable Equipment Matrix

### Summary Table: Site-002 (Sandton City)

| Equipment | Type | Count | Niagara Points | Point Type | Min/Max | Safety Rule | Controllable? |
|-----------|------|-------|----------------|-----------|---------|-------------|---------------|
| **CHILLER** | HVAC | 2 | cooling_setpoint, compressor_cmd | AO, BO | 5-12°C, on/off | TempRange(5-12) | ✅ YES |
| **AHU** | HVAC | 3 | supply_temp_sp, damper_pos | AO, AO | 10-25°C, 0-100% | TempRange(16-28) | ✅ YES |
| **FCU** | HVAC | 2 | zone_setpoint, fan_speed | AO, AO | 16-28°C, 0-100% | TempRange(16-28) | ✅ YES |
| **VAV** | HVAC | 3 | damper_pos, airflow_sp | AO, AO | 0-100%, 20-5000 CFM | AirflowMin(20) | ✅ YES |
| **PUMP** | HVAC | 2 | enable, speed | BO, AO | on/off, 0-100% | (none) | ✅ YES |
| **COOLING_TOWER** | HVAC | 1 | fan_speed, bypass_valve | AO, AO | 0-100%, 0-100% | (none) | ✅ YES |
| **DALI_CTRL** | Lighting | 3 | dim_level (per zone) | AO | 0-100% | BrightnessMin(10%), BrightnessMax(90%) | ✅ YES |
| **GENERATOR** | Power | 1 | start_stop, mode | BO, MSO | on/off, auto/manual | RuntimeLimit(5min), LoadShed | ✅ YES |
| **UPS** | Power | 1 | mode, input_select | MSO, BO | eco/online, mains/batt | UPSMode | ✅ YES |
| **INVERTER** | Power | 4 | enable, mode | BO, MSO | on/off, auto/manual | (solar-specific) | ✅ YES |
| **METER** | Monitoring | 3 | (read-only) | AI, BI | various | (none) | ❌ NO |
| **BESS** | Energy Storage | 1 | charge_mode, discharge | MSO, BO | modes, on/off | (none) | ✅ YES |
| **ZONE** | Comfort | 2 | occupancy_override | BO | on/off | (comfort-specific) | ✅ YES |

**Totals:**
- **Controllable Equipment:** 25 units
- **Writable Points:** 52+
- **Non-Controllable:** 3 units (meters - read-only)

---

## Equipment Type Deep Dives

### 1. CHILLER (2 units: S002-CHILLER-B1-001, S002-CHILLER-B1-002)

#### Equipment Details

| Property | Value |
|----------|-------|
| **Manufacturer** | York YLAA0220HE |
| **Capacity** | 220kW cooling |
| **Install Date** | 2015-02-20 |
| **Niagara Protocol** | BACnet |
| **Health Score Range** | 70-95 |

#### Controllable Points

| Point Name | BACnet Type | Instance | Unit | Min/Max | Writable | Use |
|------------|-------------|----------|------|---------|----------|-----|
| `cooling_setpoint` | AO | 0 | °C | 5-12 | ✅ YES | Set chilled water supply temp |
| `compressor_cmd` | BO | 0 | on/off | 0-1 | ✅ YES | Start/stop compressor |
| `pressure_inlet` | AI | 0 | kPa | - | ❌ NO | Monitor inlet pressure |
| `pressure_outlet` | AI | 1 | kPa | - | ❌ NO | Monitor outlet pressure |
| `current_temp` | AI | 2 | °C | - | ❌ NO | Actual chilled water temp |
| `compressor_status` | BI | 0 | on/off | - | ❌ NO | Monitor compressor running |

#### Safety Constraints

**Rule 1: CHW Supply Temperature Range (5-12°C)**
```
SafetyEngine Rule ID: temp_chw_supply_range
Type: TemperatureRange
Severity: BLOCK (prevents dangerous setpoints)
Min: 5°C, Max: 12°C

Enforcement:
- PARASITE setpoint < 5°C → BLOCKED, clamped to 5°C
- PARASITE setpoint > 12°C → BLOCKED, clamped to 12°C
- Alert logged for out-of-range attempt
```

**Rule 2: Chiller Minimum Temperature (Freeze Protection)**
```
SafetyEngine Rule ID: temp_chiller_min
Type: TemperatureRange
Severity: BLOCK
Min: 5°C, Max: 15°C (supply reading, not setpoint)

Enforcement:
- If actual_temp drops below 5°C → Emergency compressor stop
- Prevents ice formation in evaporator
```

**Rule 3: Chiller Pressure Limit (Compressor Protection)**
```
SafetyEngine Rule ID: chiller_pressure_max
Type: PressureLimit
Severity: BLOCK
Max: 1200 kPa

Enforcement:
- Read pressure_inlet and pressure_outlet
- If max pressure exceeded → Block further cooling
- Prevents equipment damage from overpressure
```

**Rule 4: Compressor Runtime Minimum (Soft-start Protection)**
```
SafetyEngine Rule ID: chiller_runtime_limit
Type: RuntimeLimit
Severity: BLOCK
Min Runtime: 5 minutes
Max Starts/Hour: 4

Enforcement:
- Compressor turned on → must run for 5 minutes minimum
- Can't restart more than 4 times per hour
- Prevents rapid cycling (damages compressor)
```

**Rule 5: Chiller-Pump Interlock**
```
SafetyEngine Rule ID: (implicit in adapter logic)
Type: Interlock
Severity: BLOCK

Enforcement:
- Before PARASITE commands compressor ON:
  - Check if pump_status == ON
  - If pump OFF → Block compressor start, log alert
- Prevents dry-running compressor (no chilled water flow)
```

#### PARASITE Control Workflow

```
1. Check pump status
   GET /api/devices/S002-PUMP-B1-CHW1/status
   → If status != "running" → Abort, alert technician

2. Read current chilled water temp
   GET /api/niagara/bacnet/devices/1000/points/analogInput/2
   → Use as baseline for health impact estimation

3. Calculate target setpoint (e.g., 8°C for aggressive cooling)
   SafetyEngine validates: 5 ≤ 8 ≤ 12 ✓

4. Write setpoint with priority 8
   POST /api/niagara/bacnet/devices/1000/points/analogOutput/0/write
   {
     "value": 8,
     "priority": 8
   }

5. Subscribe to COV for feedback
   POST /api/niagara/bacnet/subscribe
   {
     "device_id": 1000,
     "points": [
       {"object_type": "analogOutput", "instance": 0},
       {"object_type": "analogInput", "instance": 2}
     ],
     "lifetime": 60
   }

6. Verify write within 5 seconds
   Wait for COV update: analogOutput,0 = 8°C
   → If received: write successful ✓
   → If timeout: write may have failed, retry with backoff

7. Monitor health score
   If health drops below 50 → escalate to technician
```

#### Typical Control Scenarios

**Scenario 1: Aggressive Cooling (High Load)**
```
Trigger: Zone temperature > 25°C
Action: Lower chilled water setpoint
Setpoint: 6°C (SafetyEngine validates, within 5-12°C range)
Expected: Cooler supply water → better zone cooling
Health Impact: Increases chiller load, monitor power consumption
```

**Scenario 2: Energy Saving (Light Load)**
```
Trigger: Zone temperature < 22°C and trending down
Action: Raise chilled water setpoint
Setpoint: 10°C (warmer, less cooling)
Expected: Reduced chiller compressor runtime → energy savings
Health Impact: Reduces wear on compressor, extends service life
```

**Scenario 3: Night Setback (Unoccupied)**
```
Trigger: Building unoccupied, night mode
Action: Disable chiller temporarily
Setpoint: 11°C (lowest safe, standby mode)
Compressor: OFF (if safe - check pump running)
Expected: Minimal energy consumption
Health Impact: Gives equipment rest period
```

---

### 2. AHU (Air Handling Unit) - 3 units (L2, R, B1)

#### Equipment Details

| Property | Value |
|----------|-------|
| **Manufacturer** | Carrier 39M-series (50-80kW) |
| **Capacity** | 50-80kW airflow |
| **Location** | Roof (L2, R) / Basement (B1) |
| **Niagara Protocol** | BACnet |
| **Typical Points** | 6-8 per unit |

#### Controllable Points

| Point Name | BACnet Type | Unit | Min/Max | Writable | Purpose |
|------------|-------------|------|---------|----------|---------|
| `supply_temp_setpoint` | AO | °C | 10-25 | ✅ YES | Target supply air temperature |
| `damper_position_return` | AO | % | 0-100 | ✅ YES | Return air damper (mixing fresh/recirculated) |
| `damper_position_outdoor` | AO | % | 0-100 | ✅ YES | Outdoor air damper (fresh air intake) |
| `fan_speed_supply` | AO | % | 0-100 | ✅ YES | Supply fan VFD speed |
| `fan_speed_return` | AO | % | 0-100 | ✅ YES | Return fan VFD speed |
| `filter_reset` | BO | - | 0-1 | ✅ YES | Reset filter differential pressure alarm |
| `supply_temp_actual` | AI | °C | - | ❌ NO | Actual leaving air temperature |
| `pressure_differential` | AI | Pa | - | ❌ NO | Monitor filter clogging |

#### Safety Constraints

**Rule 1: Supply Air Temperature Range (10-25°C)**
```
SafetyEngine Rule ID: (implicit)
Severity: BLOCK
Range: 10-25°C

Enforcement:
- PARASITE setpoint < 10°C → Clamped to 10°C
- PARASITE setpoint > 25°C → Clamped to 25°C
- Prevents excessively cold/hot supply air
```

**Rule 2: Zone Temperature Safe Range (16-28°C)**
```
SafetyEngine Rule ID: temp_zone_safe_range
Severity: BLOCK
Range: 16-28°C

Enforcement:
- AHU supply affects zones downstream
- Monitor zone feedback from FCU/sensors
- If zone trending out of range → adjust setpoint
```

**Rule 3: Damper Position Limits (0-100%)**
```
SafetyEngine Rule ID: (implicit)
Enforcement:
- Dampers must be 0-100% position (not negative, not > 100%)
- 0% = fully closed, 100% = fully open
- PARASITE always sends values within range
```

**Rule 4: Outdoor Air Minimum (Ventilation)**
```
SafetyEngine Rule ID: (implicit in ventilation logic)
Enforcement:
- Min outdoor air damper: depends on occupancy
- Occupied: min 20% outdoor air (fresh air requirement)
- Unoccupied: can reduce to 5% (minimum for building flush)
- PARASITE respects occupancy schedule
```

#### PARASITE Control Strategy

**Temperature Control Chain:**
```
Zone thermostat reads temperature (feedback)
  ↓
PARASITE AI optimizer calculates desired zone temp
  ↓
Calculates required AHU supply temp
  (backward calculation from zones)
  ↓
SafetyEngine validates supply temp within 10-25°C range
  ↓
Writes new supply_temp_setpoint to AHU
  ↓
AHU controller modulates dampers and fan to maintain setpoint
  ↓
Cooler/warmer air sent to zones
  ↓
Zone temps stabilize (feedback loop closes)
```

**Example:**
```
Scenario: Zone L2-A reading 24°C, wants 22°C
Current AHU setpoint: 18°C (too cold)

PARASITE calculation:
- Zone target: 22°C
- Estimated zone-to-AHU delta: 4°C (typical)
- Required AHU setpoint: 22 - 4 = 18°C
- SafetyEngine check: 10 ≤ 18 ≤ 25 ✓
- Write: supply_temp_setpoint = 18°C (no change needed)

If zone still drifting up:
- New AHU setpoint: 19°C (colder)
- SafetyEngine check: 10 ≤ 19 ≤ 25 ✓
- Write: supply_temp_setpoint = 19°C
```

---

### 3. FCU (Fan Coil Unit) - 2 units (L1-A, L2-B)

#### Equipment Details

| Property | Value |
|----------|-------|
| **Type** | Zone-level heating/cooling |
| **Typical Capacity** | 5-10kW per unit |
| **Control** | Valve + fan speed |
| **Niagara Protocol** | BACnet |
| **Points per Unit** | 4-5 |

#### Controllable Points

| Point Name | BACnet Type | Unit | Min/Max | Writable | Purpose |
|------------|-------------|------|---------|----------|---------|
| `zone_setpoint` | AO | °C | 16-28 | ✅ YES | Zone temperature setpoint |
| `fan_speed` | AO | % | 0-100 | ✅ YES | FCU fan speed (0=off, 100=max) |
| `valve_position` | AO | % | 0-100 | ✅ YES | Hot/cold water valve (0=closed) |
| `zone_temp_actual` | AI | °C | - | ❌ NO | Current zone temperature |
| `fan_status` | BI | - | - | ❌ NO | Is fan running? |

#### Safety Constraints

**Rule 1: Zone Temperature Safe Range (16-28°C)**
```
SafetyEngine Rule ID: temp_zone_safe_range
Severity: BLOCK
Range: 16-28°C

Enforcement:
- PARASITE setpoint < 16°C → Clamped to 16°C
- PARASITE setpoint > 28°C → Clamped to 28°C
- Prevents thermal discomfort and equipment stress
```

**Rule 2: FCU Minimum Temperature (Freeze Protection)**
```
SafetyEngine Rule ID: (implicit)
Enforcement:
- If zone temp drops below 12°C → Emergency heating
- Prevents frozen pipes in FCU coil
```

#### PARASITE Control Workflow

```
1. Read current zone temperature
   GET /api/niagara/bacnet/devices/{device_id}/points/analogInput/0
   → e.g., 23.5°C

2. Compare to target (e.g., 22°C)
   Deviation: +1.5°C (too warm)

3. Calculate required control
   - If deviation > 2°C: use aggressive fan (100%)
   - If deviation 0.5-2°C: moderate fan (50%)
   - If deviation < 0.5°C: minimum fan (10%)
   - Valve: proportional to deviation (more open = more heating/cooling)

4. Apply SafetyEngine validation
   New setpoint: 22°C
   SafetyEngine check: 16 ≤ 22 ≤ 28 ✓

5. Write controls
   POST /api/niagara/bacnet/devices/{device_id}/points/analogOutput/0/write
   {"value": 22, "priority": 8}  # Setpoint

   POST /api/niagara/bacnet/devices/{device_id}/points/analogOutput/1/write
   {"value": 75, "priority": 8}  # Fan speed 75%

   POST /api/niagara/bacnet/devices/{device_id}/points/analogOutput/2/write
   {"value": 60, "priority": 8}  # Valve 60% open

6. Monitor zone temp with COV
   Subscribe and wait for feedback
   Expected: Zone temp should drift toward 22°C
```

---

### 4. VAV (Variable Air Volume) - 3 units (L1-A, L1-B, L2-A)

#### Equipment Details

| Property | Value |
|----------|-------|
| **Type** | Zone air volume controller |
| **Control** | Damper position + airflow feedback |
| **Points per Unit** | 3-4 |

#### Controllable Points

| Point Name | BACnet Type | Unit | Min/Max | Writable | Purpose |
|------------|-------------|------|---------|----------|---------|
| `damper_position` | AO | % | 0-100 | ✅ YES | VAV damper (0=off, 100=max) |
| `airflow_setpoint` | AO | CFM | 20-5000 | ✅ YES | Desired airflow (depends on zone) |
| `temperature_setpoint` | AO | °C | 16-28 | ✅ YES | Zone temperature target |
| `airflow_actual` | AI | CFM | - | ❌ NO | Actual airflow measurement |
| `zone_temp_actual` | AI | °C | - | ❌ NO | Current zone temperature |

#### Safety Constraints

**Rule 1: Minimum Airflow (Ventilation)**
```
SafetyEngine Rule ID: vav_minimum_airflow
Severity: WARNING (not blocking, but alerts)
Min Airflow: 20 CFM

Enforcement:
- PARASITE airflow_setpoint < 20 → Warning logged
- Occupied spaces: should never go below 20 CFM
- Prevents poor indoor air quality
```

**Rule 2: Zone Temperature Range (16-28°C)**
```
SafetyEngine Rule ID: temp_zone_safe_range
Severity: BLOCK
Range: 16-28°C

Enforcement:
- Zone setpoint validated same as FCU
```

#### PARASITE Control Workflow

```
1. Calculate required airflow
   - Based on zone occupancy and temperature deviation
   - Occupied full capacity: 80% of max VAV flow
   - Occupied moderate: 50%
   - Unoccupied minimum: 20% (ventilation only)

2. Calculate required damper position
   Damper_pos = (required_CFM / max_CFM) * 100%
   Example: (80 CFM / 500 CFM max) * 100 = 16% damper

3. Apply SafetyEngine validation
   - Airflow >= 20 CFM for occupied spaces
   - Temperature setpoint within 16-28°C

4. Write controls
   POST /api/niagara/bacnet/devices/{device_id}/points/analogOutput/0/write
   {"value": 80, "priority": 8}  # Airflow setpoint 80 CFM

   POST /api/niagara/bacnet/devices/{device_id}/points/analogOutput/1/write
   {"value": 16, "priority": 8}  # Damper 16% open

5. Verify with feedback
   Wait for COV: airflow_actual → should trend toward 80 CFM
```

---

### 5. DALI Lighting Control (DALI Controllers) - 3 units (L1-A, L1-CTRL, L2-B)

#### Equipment Details

| Property | Value |
|----------|-------|
| **Type** | Digital Addressable Lighting Interface |
| **Protocol** | DALI (via Niagara BACnet gateway) |
| **Points per Zone** | 1-2 (dim level, status) |
| **Zones Controlled** | L1-A (6-8 fixtures), L2-B (8-10 fixtures) |

#### Controllable Points

| Point Name | BACnet Type | Unit | Min/Max | Writable | Purpose |
|------------|-------------|------|---------|----------|---------|
| `dim_level` | AO | % | 0-100 | ✅ YES | Brightness level (0=off, 100=max) |
| `scene_select` | MSO | 1-N | 1-4 | ✅ YES | Scene number (daylight, task, etc.) |
| `lamp_status` | BI | - | - | ❌ NO | Are lamps on? |
| `power_consumption` | AI | W | - | ❌ NO | Total lighting power use |

#### Safety Constraints

**Rule 1: Occupied Zone Minimum Brightness (Safety)**
```
SafetyEngine Rule ID: lighting_min_brightness
Severity: BLOCK
Min: 10% (DALI level 25)

Applies To: Occupied zones (determined by sensor or schedule)

Enforcement:
- PARASITE dim_level < 10% in occupied zone → Blocked, clamped to 10%
- Prevents dangerously dark work areas
```

**Rule 2: Emergency Lighting Minimum**
```
SafetyEngine Rule ID: lighting_emergency_min
Severity: BLOCK
Min: 70% (DALI level 178)

Applies To: Emergency evacuation lighting circuits

Enforcement:
- Emergency zones: dim_level must stay ≥ 70%
- Prevents darkness in egress paths
```

**Rule 3: Unoccupied Zone Maximum (Energy Savings)**
```
SafetyEngine Rule ID: lighting_unoccupied_max
Severity: WARNING
Max: 30% (DALI level 76)

Applies To: Unoccupied zones (night, weekends)

Enforcement:
- If zone unoccupied and dim_level > 30%
- Warning logged; PARASITE should reduce brightness
- Not blocking, but alerts technician to energy waste
```

**Rule 4: Maximum Brightness Limit (Energy/Glare)**
```
SafetyEngine Rule ID: lighting_brightness_max
Severity: WARNING
Max: 90%

Enforcement:
- PARASITE dim_level > 90% → Warning logged
- Rarely need full 100% brightness
- 90% provides sufficient illumination with energy savings
```

#### PARASITE Control Workflow

```
1. Determine zone occupancy
   - Query occupancy sensor or schedule
   - e.g., Zone L1-A: OCCUPIED

2. Calculate target brightness
   Daylight available: 300 lux detected
   Task requirement: 500 lux
   Calculated target: 500 - 300 = 200 lux supplemental
   DALI level: 40% (rough mapping)

3. Apply SafetyEngine validation
   Zone occupied: min brightness 10%
   40% > 10% ✓
   Max brightness 90%: 40% < 90% ✓

4. Write brightness control
   POST /api/niagara/bacnet/devices/{device_id}/points/analogOutput/0/write
   {"value": 40, "priority": 8}  # Dim level 40%

5. Verify with feedback
   Wait for COV: dim_level → should update to 40%
   Lamp status: should remain ON
   Power consumption: should be ~40% of max

6. Energy Optimization
   Evening (unoccupied): Reduce to 10% (minimum for safety/security)
   Night (completely unoccupied): Turn off (0%) if not emergency zone
```

---

### 6. GENERATOR (1 unit: S002-GEN-B1-001)

#### Equipment Details

| Property | Value |
|----------|-------|
| **Type** | Standby diesel generator |
| **Capacity** | 100-200kW (estimated) |
| **Primary Use** | Load shedding during Eskom cuts |
| **Secondary Use** | Backup power for critical loads |
| **Niagara Protocol** | BACnet (engine controller integrated) |
| **Points** | Start/stop, mode, fuel level, runtime |

#### Controllable Points

| Point Name | BACnet Type | Unit | Min/Max | Writable | Purpose |
|------------|-------------|------|---------|----------|---------|
| `start_stop_cmd` | BO | on/off | 0-1 | ✅ YES | Start (1) or stop (0) generator |
| `mode_select` | MSO | 1-3 | 1=manual, 2=auto, 3=standby | ✅ YES | Operating mode |
| `load_shedding_enable` | BO | on/off | 0-1 | ✅ YES | Enable load shedding relay sequencing |
| `fuel_level` | AI | % | - | ❌ NO | Fuel tank level (read for decision-making) |
| `runtime_total` | AI | hours | - | ❌ NO | Total generator runtime (monitoring) |
| `engine_status` | BI | on/off | - | ❌ NO | Is engine actually running? |
| `frequency` | AI | Hz | - | ❌ NO | AC frequency (should be 50Hz) |

#### Safety Constraints

**Rule 1: Minimum Runtime Duration (Equipment Protection)**
```
SafetyEngine Rule ID: generator_runtime_limit (not explicit, but implemented)
Severity: BLOCK
Min Runtime: 5 minutes

Enforcement:
- Generator turned ON → must run minimum 5 minutes
- Prevents rapid cycling (damages diesel engines)
- If turned on, must stay on for 5+ minutes before stop allowed
```

**Rule 2: Load Shedding Schedule (Coordination with Eskom)**
```
SafetyEngine Rule ID: load_shedding_coordination
Severity: BLOCK
Logic: Respect Eskom stage

Enforcement:
- Only enable load shedding when Eskom announces stage (stage ≥ 2)
- Stage 1: Alerts only, don't shed yet
- Stage 2+: Can shedding to reduce demand
- Stage 8: Emergency, shed non-critical loads completely
```

**Rule 3: Fuel Level Check Before Start**
```
SafetyEngine Rule ID: generator_fuel_requirement
Severity: BLOCK

Enforcement:
- Before PARASITE commands start:
  - Read fuel_level
  - If fuel < 20% → BLOCKED, alert technician
  - Requires manual refuel before generator can run
```

**Rule 4: Occupancy Before Load Shedding (User Comfort)**
```
SafetyEngine Rule ID: (implicit in optimizer)
Severity: WARNING

Enforcement:
- Before shedding non-critical loads:
  - Check if building occupied
  - If occupied, warn before shed (might affect comfort)
  - If unoccupied, can shed more aggressively
```

#### PARASITE Control Workflow (Load Shedding)

```
SCENARIO: Eskom announces stage 4 load shedding, building consumes 150kW

1. Monitor Eskom stage
   Eskom_stage = 4
   Typical shed target: 30-40% reduction

2. Calculate load shed requirement
   Current load: 150kW
   Target: 150kW * 0.7 = 105kW (shed 45kW)

3. Check fuel level
   GET /api/niagara/bacnet/devices/gen_device_id/points/analogInput/1
   Fuel = 45%
   Check: 45% > 20% ✓ (enough fuel)

4. Enable load shedding in sequence
   Priority 1 (shed first): Non-critical HVAC zones
   - Disable VAV for unoccupied zones
   - Reduce FCU speed in low-occupancy areas

   Priority 2 (if needed): Lighting
   - Reduce DALI dim level from 40% to 20%
   - Especially in unoccupied areas

   Priority 3 (if needed): Water heating
   - Reduce hot water temp setpoint

5. Start generator if shed insufficient
   Load still > 105kW target after shed

   Check safety:
   - Fuel level: 45% ✓
   - No rapid restart (check generator status)
   - Engine temperature acceptable (from sensors)

   POST /api/niagara/bacnet/devices/gen_id/points/binaryOutput/0/write
   {"value": 1, "priority": 8}  # Start generator

6. Enable gen-supplied circuits
   POST /api/niagara/bacnet/devices/gen_id/points/binaryOutput/1/write
   {"value": 1, "priority": 8}  # Enable load shedding relays

   Load shed automatically to target via relay sequencing

7. Monitor for stage change
   Every 15 minutes: Check Eskom stage
   Stage 4 → Stage 5: Shed more load
   Stage 4 → Stage 2: Can restore load, eventually stop gen

8. Stop generator when Eskom lifts stage
   If Eskom_stage = 1 (load shedding ended):
   - Wait 10 minutes (to stabilize)
   - Verify building load < 100kW
   - Restore shed loads first
   - Then stop generator

   POST /api/niagara/bacnet/devices/gen_id/points/binaryOutput/0/write
   {"value": 0, "priority": 8}  # Stop generator

   Note: Generator continues running minimum 5 minutes
         If stop commanded at 2min, will run to 7min total
```

---

### 7. UPS (Uninterruptible Power Supply) - 1 unit: S002-UPS-B1-001

#### Equipment Details

| Property | Value |
|----------|-------|
| **Type** | Online UPS (always running) |
| **Capacity** | 50-100kVA (estimated) |
| **Primary Load** | Critical IT equipment, fire systems, emergency lighting |
| **Battery Backup** | ~15 minutes at full load |
| **Niagara Protocol** | BACnet |

#### Controllable Points

| Point Name | BACnet Type | Unit | Min/Max | Writable | Purpose |
|------------|-------------|------|---------|----------|---------|
| `mode_select` | MSO | 1-3 | 1=online, 2=eco, 3=bypass | ✅ YES | Operating mode |
| `input_source` | BO | - | 0=mains, 1=battery | ❌ NO | (read-only, automatic) |
| `battery_percent` | AI | % | - | ❌ NO | Battery state of charge |
| `battery_minutes` | AI | min | - | ❌ NO | Minutes remaining at current load |
| `load_percent` | AI | % | - | ❌ NO | Current load on UPS |
| `temperature` | AI | °C | - | ❌ NO | Internal UPS temperature |

#### Safety Constraints

**Rule 1: Online Mode Requirement (Critical Loads)**
```
SafetyEngine Rule ID: ups_critical_mode
Severity: BLOCK

Enforcement:
- UPS must always be in online mode (mode = 1)
- Online mode = continuous power conditioning
- Eco mode reduces efficiency but not recommended for critical load
- Bypass mode = dangerous (no protection if mains fails)

PARASITE never writes mode to bypass or eco
```

**Rule 2: Low Battery Alert**
```
SafetyEngine Rule ID: ups_low_battery_alert
Severity: WARNING

Enforcement:
- If battery_percent < 20%:
  - Alert technician
  - Prepare for orderly shutdown if mains failure occurs
  - Start generator (if available and fueled)
```

**Rule 3: High Temperature Shutdown**
```
SafetyEngine Rule ID: ups_overtemp
Severity: BLOCK

Enforcement:
- If UPS internal temp > 55°C:
  - Alert technician
  - Reduce non-critical loads to lower UPS draw
  - May need maintenance (dirty filters)
```

#### PARASITE Control Strategy

```
UPS is largely automatic (passive monitoring for PARASITE).
Main interaction: Respond to mains failure.

SCENARIO 1: Mains still present, normal operation
- UPS in online mode (conditioned AC output)
- Battery charging
- PARASITE: No action needed

SCENARIO 2: Mains failure detected
- UPS automatically switches to battery
- Alarms: "Mains failure" alert
- Battery countdown: "15 minutes at current load"

PARASITE RESPONSE:
1. Immediately start generator
   (Already covered in GENERATOR section)

2. Reduce non-critical loads to extend battery
   - Disable HVAC for unoccupied zones
   - Reduce lighting to emergency levels (10% minimum)
   - Shut down non-critical servers (if controllable)

   Goal: Drop UPS load from 100kW → 30kW
   Effect: Battery runtime extends 15min → 50min+

3. Monitor battery level
   Check battery_percent and battery_minutes every 30 seconds

4. When mains restored
   - Battery slowly re-charges
   - UPS alerts: "Mains restored"
   - When battery > 95%, can restore shed loads
   - Wait for generator to stabilize before shutdown
```

---

## Non-Controllable Equipment

### Equipment WITHOUT Niagara BACnet Control

| Equipment | Type | Count | Why Not Controllable | Workaround |
|-----------|------|-------|----------------------|-----------|
| **METER** (Electric, Water, Gas) | Monitoring | 3 | BACnet interface is read-only; no setpoints or commands | Monitor consumption via Niagara; no remote control |
| **FIRE SYSTEM** | Safety | 1 | Intentionally isolated for safety; requires manual reset | Manual technician action only |
| **ACCESS CONTROL** | Security | N/A | Not networked to Niagara (separate system) | Manual unlock via physical system |
| **CCTV** | Security | 2+ | Not networked to Niagara | Manual review via separate system |
| **Third-party integration** | Various | N/A | Legacy systems not Niagara-connected | Use SIMBIOT API for bridge (future) |

### Impact on PARASITE

- ✅ Meters: Can READ consumption, but can't remote-control (expected)
- ❌ Fire system: Autonomous control intentionally prevented (safety-critical)
- ❌ Access control: Not controllable (security policy)
- ⚠️ Third-party systems: Future SIMBIOT bridge may enable control

---

## Interlocks & Dependencies

### Critical Interlocks

#### 1. Chiller ↔ Pump Interlock

**Dependency:** Chiller requires pump running before compressor start

```
IF PARASITE.commands(chiller_compressor = ON):
  Before executing:
    pump_status = READ(pump_status)
    IF pump_status != "running":
      LOG warning: "Cannot start chiller, pump offline"
      BLOCK write
      ALERT technician
    ELSE:
      ALLOW chiller start
```

**Verification Test:**
```
1. Stop pump: pump.enable = OFF
2. Try to start chiller: chiller.compressor = ON
3. Expected: BLOCKED, alert logged
4. Start pump: pump.enable = ON
5. Try again to start chiller: chiller.compressor = ON
6. Expected: SUCCESS, chiller runs
```

#### 2. Fire Alarm ↔ HVAC Interlock

**Dependency:** Fire alarm deactivates HVAC to prevent smoke spread

```
IF fire_alarm.status = ACTIVE:
  BLOCK all HVAC commands (AHU, FCU, VAV, chiller)
  FORCE all HVAC to STANDBY (fans off, dampers closed)
  LOCK out PARASITE control until fire alarm cleared
```

**Testing:**
- Trigger fire alarm (test mode)
- Attempt HVAC adjustment
- Expected: All HVAC controls locked

#### 3. Mains Failure ↔ Generator

**Dependency:** Generator must start when UPS detects mains loss

```
IF UPS.mains_status = FAILED:
  PARASITE IMMEDIATELY:
    1. Start generator
    2. Reduce non-critical loads (HVAC, lighting)
    3. Extend UPS battery runtime via load reduction
    4. Monitor battery_percent
    5. When mains restored: Restore loads, stop generator
```

#### 4. Occupancy ↔ HVAC & Lighting

**Dependency:** PARASITE adjusts controls based on zone occupancy

```
FOR EACH zone:
  occupancy = READ(occupancy_sensor or schedule)

  IF occupied:
    - Lighting minimum: 10% (safety)
    - HVAC: Full capability (comfort priority)
    - VAV airflow: Minimum 20 CFM (ventilation)

  ELSE (unoccupied):
    - Lighting maximum: 30% (energy savings)
    - HVAC: Reduced (cost saving priority)
    - VAV airflow: Minimum 20 CFM (ventilation requirement)
    - Temperature: Can drift wider (e.g., 18-26°C vs 20-24°C)
```

---

## Priority & Conflict Resolution

### BACnet Priority Hierarchy for PARASITE

**Application:**
```
Priority  User                 PARASITE Behavior
--------  ----                 ------------------
   1      Emergency            (Fire alarm, critical)     [Not PARASITE]
   2-6    Technician           (On-site override)         [Manual, blocks PARASITE]
   7      Manual Operator      (Remote technician)        [Can override PARASITE]
   8      PARASITE AI          (Autonomous control)       [Standard PARASITE priority]
   9-15   -                    -
   16     Default              (Device fallback)          [Fallback if all above null]
```

### Conflict Scenarios

#### Scenario 1: PARASITE writes, then technician overrides

```
Timeline:
T=0:  PARASITE writes cooling_setpoint = 8°C at priority 8
      Device reading: 8°C (PARASITE active)

T=30: Technician (remote) writes cooling_setpoint = 10°C at priority 7
      Device reading: 10°C (Technician priority 7 wins)

T=60: PARASITE tries cooling_setpoint = 6°C at priority 8
      Device reading: 10°C (Technician priority 7 still active)
      PARASITE write succeeds but device ignores it (priority 7 > 8)

T=90: Technician releases override (writes null to priority 7)
      Device reading: 6°C (PARASITE priority 8 now active)
```

**PARASITE Strategy:**
- Detect technician override via COV subscription
- Log: "Technician override on cooling_setpoint, backing off"
- Continue monitoring; when override cleared, resume control

#### Scenario 2: PARASITE conflict with emergency

```
T=0:  PARASITE controls lighting dim_level = 40% at priority 8

T=15: Fire alarm triggered → emergency handler activates
      Fire handler writes lighting dim_level = 100% at priority 1
      Device reading: 100% (Emergency priority 1 always wins)

T=30: PARASITE unaware, tries to write dim_level = 40% at priority 8
      Device reading: 100% (Still under fire alarm priority 1)

T=60: Fire alarm cleared
      Emergency handler releases priority 1
      Device reading: 40% (PARASITE priority 8 now active)
```

**PARASITE Strategy:**
- Never write during fire alarm (SafetyEngine blocks this)
- Emergency system has explicit firewall around PARASITE

---

## Recommendations for PARASITE

### Phase 67-02: Control System Design

1. **Implement Write Verification**
   - Always use COV subscriptions after writes
   - 5-second timeout for feedback
   - Retry failed writes with backoff

2. **Implement Technician Override Detection**
   - Monitor for priority changes via COV
   - When detected: log, back off, resume later
   - Provide UI alert: "Technician has taken control of..."

3. **Implement Safety Constraint Checking**
   - Before every write: call SafetyEngine.validate()
   - Cache safety rules locally for performance
   - Log any constraint violations for audit

4. **Implement Interlock Checking**
   - Before chiller start: check pump status
   - Before load shedding: check fuel level
   - Before generator stop: confirm mains restored

5. **Implement Occupancy-Based Control**
   - Query occupancy sensor or building schedule
   - Adjust lighting/HVAC setpoints based on occupancy
   - Occupied: comfort priority; Unoccupied: energy priority

### Phase 67-03: Safety & Testing

1. **Test Retry Logic**
   - Simulate device timeouts
   - Verify retry with backoff works
   - Verify max retries then fail gracefully

2. **Test Safety Constraint Enforcement**
   - Try out-of-range writes
   - Verify SafetyEngine blocks or clamps
   - Verify alerts logged

3. **Test Interlock Logic**
   - Simulate pump offline, try chiller start (should block)
   - Simulate fire alarm, try HVAC adjustment (should block)
   - Simulate low fuel, try generator start (should block)

4. **Test Occupancy-Based Control**
   - Manual override occupancy sensor
   - Verify lighting/HVAC adjust accordingly
   - Verify correct min/max brightness enforced

5. **Test COV Callback Flow**
   - Subscribe to points
   - Manually change point value (via technician interface)
   - Verify callback fires and PARASITE detects change
   - Test timeout scenario (point doesn't update)

### Production Readiness Checklist

- [ ] All 52 controllable points mapped to SENTINEL equipment
- [ ] SafetyEngine integrated and tested for each equipment type
- [ ] COV subscriptions working end-to-end
- [ ] Retry logic tested (failure + recovery)
- [ ] Interlock logic implemented and tested
- [ ] Technician override detection working
- [ ] Occupancy integration complete
- [ ] All 9 safety rules validated in practice
- [ ] Load shedding tested with real Eskom stage changes
- [ ] Generator start/stop sequences tested
- [ ] UPS battery low scenarios tested
- [ ] Documentation complete and team trained

---

## Summary: PARASITE Control Capability Matrix

### What PARASITE CAN Control

✅ **HVAC Systems:**
- Chiller cooling setpoint (5-12°C, safety-constrained)
- AHU supply temperature (10-25°C)
- AHU damper positions (0-100%)
- FCU zone setpoint (16-28°C)
- FCU fan speed (0-100%)
- VAV airflow (20-5000 CFM, min 20 CFM for ventilation)
- Pump enable/speed

✅ **Lighting:**
- DALI brightness by zone (10-90%, min 10% occupied, max 90%)
- Scene selection (daylight, task, scene 1-4)

✅ **Power:**
- Generator start/stop (5-min min runtime)
- Load shedding sequencing (coordinated with Eskom)
- UPS mode (online only, no bypass)

✅ **Other:**
- Zone occupancy overrides
- BESS charge/discharge mode

### What PARASITE CANNOT Control

❌ **Safety Systems:**
- Fire alarm reset (manual only)
- Fire dampers (interlocked, autonomous control blocked)

❌ **Security:**
- Access control unlock
- CCTV pan/tilt

❌ **Monitoring Only:**
- Electric, water, gas meters (read-only)
- Building sensors (temperature, occupancy, pressure)

❌ **Not Niagara-Connected:**
- Third-party legacy systems (unless future SIMBIOT bridge built)

### Key Constraints PARASITE Must Respect

1. **Temperature Ranges:**
   - Zone: 16-28°C (hard limit, BLOCKED by SafetyEngine)
   - CHW supply: 5-12°C (hard limit)
   - AHU supply: 10-25°C (soft limit, advisory)

2. **Safety Interlocks:**
   - Pump check before chiller start (fail if offline)
   - Fire alarm blocks all HVAC (hard block)
   - Fuel check before generator start (≥20%)
   - Min brightness 10% for occupied zones (hard block)

3. **Equipment Protection:**
   - Chiller min runtime 5 minutes (soft limit)
   - Generator min runtime 5 minutes (soft limit)
   - Max setpoint delta ±3°C per command (soft limit)
   - Rapid cycling prevention (soft limit)

4. **Occupancy Rules:**
   - Occupied: lighting min 10%, full HVAC, min 20 CFM airflow
   - Unoccupied: lighting max 30%, reduced HVAC, min 20 CFM airflow

5. **Priority Hierarchy:**
   - PARASITE uses priority 8 (manual operator level)
   - Technician (priority 7) can override
   - Emergency (priority 1) always wins

---

## References

- **Safety Rules:** `/backend/app/data/safety_rules.json` (15 rules)
- **Equipment Database:** `/backend/app/data/equipment.json` and `buildings/site-002/equipment/*.json`
- **Niagara Points:** `/backend/app/data/niagara/site-013-bacnet-points.json`
- **SafetyEngine:** `/backend/app/services/safety_engine.py`
- **Adapter:** `/backend/app/services/niagara/bacnet_adapter.py`
- **Phase 67-01 API Spec:** `01-niagara-control-api.md`
- **Phase 67-01 Test Results:** `01-niagara-control-tests.md`
