# Plan 67-02: AI Optimizer & Niagara Integration Audit

## Document 1: AI-Niagara Control Mapping

**Date:** 2026-02-11
**Phase:** 67 (PARASITE AI Automation System)
**Status:** Complete Mapping Documented

---

## 1. AI Optimizer Equipment Categorization

### Overview
The AI Optimizer (`backend/app/services/ai_optimizer.py`) categorizes ALL site equipment by `DeviceType` to support site-specific optimization. Different buildings have different equipment combinations, so the system must dynamically handle varied equipment inventories.

### Equipment Categories & Niagara Mapping

#### **HVAC Equipment** (DeviceType: `hvac`)
Supports variable equipment combinations per site:

| Equipment Type | Niagara Protocol | BACnet Object Type | Control Points | Optimization Profile |
|---|---|---|---|---|
| **Chiller** | BACnet/IP | AnalogOutput | `chw_supply_temp_setpoint` (AO) | SWEAT_ASSETS: Lower to 7°C<br>COMFORT: Maintain 8°C stable<br>COST: Raise to 9°C off-peak |
| **AHU (Air Handling Unit)** | BACnet/IP | AnalogOutput | `damper_position` (AO)<br>`supply_air_temp_setpoint` (AO) | SWEAT_ASSETS: Max damper 90%<br>COMFORT: Proportional 50-70%<br>COST: Min 30% unoccupied |
| **FCU (Fan Coil Unit)** | BACnet/IP | AnalogOutput<br>BinaryOutput | `zone_cooling_setpoint` (AO)<br>Fan speed (BO) | SWEAT_ASSETS: Lower to 22°C<br>COMFORT: Maintain 23-24°C<br>COST: Raise to 25°C off-peak |
| **VAV (Variable Air Volume)** | BACnet/IP | AnalogOutput | `zone_cooling_setpoint` (AO)<br>`box_damper_position` (AO) | SWEAT_ASSETS: Maximize load<br>COMFORT: Stable setpoint<br>COST: Reduce VAV openings |
| **Zone Controller** | BACnet/IP | AnalogOutput | `zone_cooling_setpoint` (AO)<br>`humidity_setpoint` (AO) | All profiles: Zone-aware adjustments based on type |

**Key Feature:** AI Optimizer applies `_get_zone_type()` and `_should_skip_zone_optimization()` to skip critical zones (e.g., Server Room, ICU) from certain optimizations.

---

#### **Lighting Equipment** (DeviceType: `lighting`)

| Equipment Type | Niagara Integration | Control Points | Optimization Profile |
|---|---|---|---|
| **DALI-2 Luminaires** | DALI Bridge → BACnet/IP | `brightness` (AO, 0-100%) | SWEAT_ASSETS: 100% utilization<br>COMFORT: Occupancy-responsive<br>COST: Dim to 30% @ < 50% occupancy |
| **Tridonic Controllers** | Direct BACnet/IP | `zone_brightness` (AO) | COST: Aggressive dimming off-peak<br>COMFORT: Lux level maintains 300-500 |

**Integration Note:** DALI zones can be queried via `dali_service.get_all_zones()` to get occupancy-driven recommendations.

---

#### **Power Equipment** (DeviceType: `power`)

| Equipment Type | Niagara Integration | Control Points | Optimization Profile |
|---|---|---|---|
| **Generator (Diesel)** | BACnet/IP | `load_shed_relay` (BO)<br>`start_inhibit` (BO) | SWEAT_ASSETS: Never standby<br>COST: Off until load shedding stage detected<br>Safety: Cannot force start during peak |
| **UPS (Uninterruptible Power Supply)** | BACnet/IP | `mode_select` (MSMV)<br>`battery_soc` (AI) | COST: Eco mode off-peak<br>COMFORT: Normal mode peak hours<br>Safety: Never reduce battery reserve |
| **ATS (Automatic Transfer Switch)** | BACnet/IP | `transfer_control` (BO) | Read-only monitoring<br>No recommendations (critical safety) |
| **Load Shedding Relay** | BACnet/IP | `shed_relay_enable` (BO) | Driven by Eskom stage detection<br>Requires occupancy check before activation |

---

#### **Solar & BESS Equipment** (DeviceType: `solar` / `bess`)

| Equipment Type | Niagara Integration | Control Points | Optimization Profile |
|---|---|---|---|
| **Solar Inverter** | BACnet/IP | `ac_power` (AI - read-only)<br>`mppt_mode` (MSMV) | COST: Track PV generation for AC load<br>Monitor efficiency, no direct setpoint control |
| **Battery Energy Storage** | BACnet/IP | `soc_setpoint` (AO)<br>`charge_mode` (MSMV) | COST: Charge off-peak, discharge peak<br>SWEAT_ASSETS: Maximize charge cycles |
| **Energy Meter** | BACnet/IP | `active_power` (AI)<br>`cumulative_energy` (AI) | Read-only (monitoring only)<br>No recommendations |

---

#### **Security & Fire Safety** (DeviceType: `security` / `fire_safety`)

| Equipment Type | Niagara Integration | Notes |
|---|---|---|
| **Access Control Readers** | BACnet/IP (if networked) | Monitoring only, no optimization |
| **CCTV Cameras** | Network (non-BACnet) | Monitoring only |
| **Fire Alarm Panel** | BACnet/IP (if monitored) | Read-only, no control |

---

### Equipment Availability Per Site
Different sites have different equipment:

**Site-002 (Sandton City - Demo Site):**
- HVAC: Chiller, AHUs (3), FCUs (60+), Zone Controllers
- Lighting: DALI-2 with 16+ zones, Tridonic controllers
- Power: Generator, UPS, ATS, Load shedding relays
- Solar: 50 kW PV inverter + meter (new Phase 34)
- BESS: 100 kWh battery + BMS (planned Phase 34)
- Security: Access control (networked)
- Fire: BMS monitoring only

**Site-001 (Gateway Theatre):**
- HVAC: Chiller, AHUs (2), FCUs (minimal)
- Lighting: Standard (non-DALI)
- Power: Generator, UPS only
- No solar/BESS

**System Flexibility:** The `_categorize_equipment()` method dynamically groups by DeviceType, so if a site has no solar equipment, solar recommendations are simply not generated.

---

## 2. Optimization Profile Rules

Each profile is stored in `backend/app/data/optimization_profiles.json` and loaded by `ProfileService`.

### **Profile 1: SWEAT_ASSETS** (Maximize Equipment Utilization)

**Target Metric:** Equipment ramp rate (% of rated capacity)

**Decision Criteria:**
- Maximize chiller run time and load factor
- Increase ventilation for fresh air quality
- Full lighting brightness for visual comfort
- Generator always available (no standby penalties)

**Niagara Recommendations:**

| Equipment | Current → Recommended | Rationale | Niagara Write |
|---|---|---|---|
| Chiller | 8°C → 7°C | Lower setpoint = higher cooling load | `POST /api/niagara/bacnet/devices/5/points/AnalogOutput/100/write` value=7, priority=8 |
| AHU Damper | 50% → 90% | Increase fresh air intake | `POST /api/niagara/bacnet/devices/6/points/AnalogOutput/50/write` value=90, priority=8 |
| FCU Setpoint | 24°C → 22°C | Aggressive cooling | `POST /api/niagara/bacnet/devices/7/points/AnalogOutput/20/write` value=22, priority=8 |
| DALI Brightness | 70% → 100% | Maximum light output | `POST /api/niagara/bacnet/devices/8/points/AnalogOutput/15/write` value=100, priority=8 |
| Generator | Standby → Ready | Always available for load | Not directly controlled (status relay only) |

**Safety Constraints:**
- Chiller minimum: 4°C (freeze protection)
- AHU max damper: 100%
- FCU minimum: 20°C (occupant discomfort)
- Lighting: No occupancy check (maximize visibility)

---

### **Profile 2: COMFORT** (Minimize Discomfort/Temperature Variance)

**Target Metric:** Indoor temperature variance (std dev)

**Decision Criteria:**
- Maintain stable setpoints (no aggressive changes)
- Proportional control based on actual load
- Occupancy-responsive lighting (visual comfort only)
- UPS in normal mode (not eco)

**Niagara Recommendations:**

| Equipment | Current → Recommended | Rationale | Niagara Write |
|---|---|---|---|
| Chiller | 7°C → 8°C | Stable, moderate cooling | `POST /api/niagara/bacnet/devices/5/points/AnalogOutput/100/write` value=8, priority=8 |
| AHU Damper | 30% → 60% | Proportional fresh air | `POST /api/niagara/bacnet/devices/6/points/AnalogOutput/50/write` value=60, priority=8 |
| FCU Setpoint | 22°C → 23.5°C | Comfort band 22-25°C | `POST /api/niagara/bacnet/devices/7/points/AnalogOutput/20/write` value=23.5, priority=8 |
| DALI Brightness | Occupancy-responsive | Lux level 300-500 (office) | `POST /api/niagara/bacnet/devices/8/points/AnalogOutput/15/write` value=(occupancy %), priority=8 |
| UPS | Eco → Normal | Better power quality | `POST /api/niagara/bacnet/devices/10/points/MultiStateOutput/30/write` value="normal", priority=8 |

**Safety Constraints:**
- Chiller range: 6-9°C (comfort band)
- FCU range: 22-25°C (occupant preference)
- Damper max: 100%, min: 20%

---

### **Profile 3: COST** (Minimize Operational Costs)

**Target Metric:** Energy cost (R/hour based on tariff)

**Decision Criteria:**
- Raise chiller setpoint during off-peak (cheaper electricity)
- Reduce ventilation when building unoccupied
- Aggressive lighting dimming (30% minimum)
- Load shedding optimization
- UPS eco mode off-peak

**Niagara Recommendations:**

| Equipment | Current → Recommended | Condition | Niagara Write |
|---|---|---|---|
| Chiller | 8°C → 9°C | Off-peak (21:00-06:00) | `POST /api/niagara/bacnet/devices/5/points/AnalogOutput/100/write` value=9, priority=8 |
| Chiller | 8°C → 7°C | Peak (06:00-21:00) | `POST /api/niagara/bacnet/devices/5/points/AnalogOutput/100/write` value=7, priority=8 |
| AHU Damper | 60% → 30% | Unoccupied (< 10% zones) | `POST /api/niagara/bacnet/devices/6/points/AnalogOutput/50/write` value=30, priority=8 |
| DALI Brightness | 100% → 30% | Unoccupied zones | `POST /api/niagara/bacnet/devices/8/points/AnalogOutput/15/write` value=30, priority=8 |
| UPS Mode | Normal → Eco | Off-peak hours | `POST /api/niagara/bacnet/devices/10/points/MultiStateOutput/30/write` value="eco", priority=8 |
| Load Shed Relay | Off → On | Eskom stage > 2 | `POST /api/niagara/bacnet/devices/11/points/BinaryOutput/40/write` value=1, priority=8 |

**Time-of-Use Awareness:**
- Peak rates (R/kWh high): 06:00-21:00 → Aggressive cooling (lower setpoint)
- Off-peak (R/kWh low): 21:00-06:00 → Relaxed setpoint, pre-cooling at night
- Critical hours (R/kWh extreme): 17:00-20:00 → Load shedding triggers

**Safety Constraints:**
- Chiller: Not below 6°C (freeze risk increases cost)
- Lighting: Not below 30% (safety hazard)
- Load shedding: Requires occupancy check first (don't shed if occupied)

---

## 3. Recommendation → Niagara Write Mapping

### Complete Data Flow

```
1. AI Optimizer analyzes building
   ├─ Input: current_conditions, weather_forecast, energy_prices
   ├─ Categorizes equipment: equipment_inventory["hvac"], ["lighting"], ["power"]
   ├─ Selects profile: sweat_assets | comfort | cost
   └─ Generates recommendations → list of Dict

2. Recommendation Structure:
   {
       "equipment_id": "S002-CHILLER-B1-001",
       "equipment_name": "Chiller B1",
       "point_name": "chw_supply_temp_setpoint",
       "current_value": 8.0,
       "recommended_value": 7.0,
       "unit": "°C",
       "reason": "Lower setpoint for higher cooling load",
       "confidence": 0.92,
       "profile": "sweat_assets"
   }

3. Dashboard displays recommendation
   └─ User clicks "Approve"

4. Approval creates EITHER:
   Option A (current): Work order → technician executes manually
   Option B (planned): Direct Niagara write → PARASITE auto-executes

5. If Option B (auto-execute):
   ├─ Safety validation → passes 85%+ confidence
   ├─ Find device adapter → device_abstraction.get_adapter("S002-CHILLER-B1-001")
   ├─ Adapter resolves Niagara metadata:
   │   ├─ bacnet_device_id: 5 (from device metadata)
   │   └─ point metadata:
   │       ├─ bacnet_object_type: "analogOutput"
   │       └─ bacnet_instance: 100
   ├─ Write point → NiagaraBACnetAdapter._protocol_write()
   │   └─ client.write_point(device_id=5, object_type="analogOutput", instance=100, value=7, priority=8)
   └─ Log to audit trail with result

```

### Exact Niagara Write API Mapping

For each recommendation, the mapping is:

| Recommendation Field | Niagara Write Parameter | Example |
|---|---|---|
| `equipment_id` | Used to find device adapter | "S002-CHILLER-B1-001" |
| Device metadata `bacnet_device_id` | `device_id` param | 5 |
| Point metadata `bacnet_object_type` | `object_type` param | "analogOutput" |
| Point metadata `bacnet_instance` | `instance` param | 100 |
| `recommended_value` | `value` param | 7.0 |
| (implicit) Priority | `priority` param | 8 (PARASITE operator level) |

**API Endpoint (Backend):**
```
POST /api/recommendations/{rec_id}/approve
{
    "auto_execute": true,
    "executed_by": "system"
}
```

**Internal Flow:**
```python
# backend/app/api/recommendations.py
recommendation = get_recommendation(rec_id)
device = device_manager.get_device(recommendation["equipment_id"])
adapter = device_manager.get_adapter(device.id)
success = await adapter.write_value(
    point_name=recommendation["point_name"],
    value=recommendation["recommended_value"],
    priority=8,
    user="parasite"
)
```

**Niagara BACnet Write (lowest level):**
```python
# backend/app/services/niagara/bacnet_client.py
await client.write_point(
    device_id=5,
    object_type="analogOutput",
    instance=100,
    value=7,
    priority=8
)
```

---

## 4. Confidence Scoring

Each recommendation includes a confidence score (0-100%) that indicates how likely the change will improve the target metric.

### Inputs to Confidence Calculation
```python
# backend/app/services/ai_optimizer.py
confidence = 0.7  # base for rule-based

# Factors that increase confidence:
+ recent_historical_data_available        (+0.05)
+ similar_weather_pattern_before          (+0.08)
+ stable_equipment_performance            (+0.05)
+ high_occupancy_consistency              (+0.05)

# Factors that decrease confidence:
- sensor_data_unreliable                  (-0.10)
- first_time_seeing_pattern               (-0.15)
- equipment_just_serviced                 (-0.05)
- low_occupancy_variability               (-0.10)
```

### Confidence Thresholds for Autonomy

| Confidence Range | Current Behavior | Recommended PARASITE Behavior |
|---|---|---|
| **90-100%** | Display "High Confidence" | AUTO-EXECUTE (no approval) |
| **80-89%** | Display "Confident" | Require operator confirmation (1-click) |
| **70-79%** | Display "Moderate" | Require technician review (full form) |
| **<70%** | Display "Low" | Information only, no automation |

**Example Scores:**
- "Lower chiller to 7°C": 92% (good historical data, similar weather)
- "Increase AHU damper to 75%": 78% (moderate occupancy variance)
- "Dim DALI to 30%": 65% (first time seeing this pattern)

---

## 5. Equipment Coverage Assessment

### Controllable Equipment by Site

| Equipment Category | Controllable? | Writable Points | Coverage | Notes |
|---|---|---|---|---|
| **HVAC** | ✅ YES | Setpoint (AO) | 100% | Zone controllers, chillers, AHUs all writable |
| **Lighting** | ✅ YES | Brightness (AO) | 100% if DALI-2 | DALI zones queryable, brightness 0-100 |
| **Power** | ⚠️ PARTIAL | Load shed (BO), UPS mode (MSMV) | ~50% | Generator start/stop controlled by safety rules |
| **Solar** | ❌ NO | MPPT (read-only) | 0% | Inverters optimize autonomously, no setpoint control |
| **BESS** | ⚠️ PARTIAL | SOC target, charge mode | ~50% | Battery safety requires careful control |
| **Security** | ❌ NO | Status (read-only) | 0% | Monitoring only |
| **Fire** | ❌ NO | Alarms (read-only) | 0% | Monitoring only |

### Non-Controllable Equipment (Monitoring Only)

1. **Meters** (`meter` type) - energy consumption tracking
2. **Inverters** (solar) - MPP tracking automatic
3. **Sensors** - temperature, humidity, CO2 (inputs only)
4. **Alarms** - fire, intrusion (status indicators only)
5. **Power meters** - kW, kWh measurement only

### Coverage by Equipment Type

| Niagara Equipment ID | Equipment Type | Controllable | AI Optimization | Notes |
|---|---|---|---|---|
| S002-CHILLER-B1-001 | Chiller | ✅ | ✅ | Setpoint optimization (7-9°C range) |
| S002-AHU-L1-001 | AHU | ✅ | ✅ | Damper position optimization (30-90%) |
| S002-AHU-L2-001 | AHU | ✅ | ✅ | Damper position optimization |
| S002-FCU-L1-A | FCU | ✅ | ✅ | Zone cooling setpoint (22-25°C) |
| S002-FCU-L1-B through Z | FCU | ✅ | ✅ | Zone-aware optimization |
| S002-DALI-L1 | DALI Zone | ✅ | ✅ | Brightness 0-100%, occupancy-responsive |
| S002-DALI-L2 | DALI Zone | ✅ | ✅ | Brightness 0-100%, occupancy-responsive |
| S002-GEN-B1 | Generator | ⚠️ | ⚠️ | Load shedding only, safety-gated |
| S002-UPS-B1 | UPS | ⚠️ | ✅ | Mode (eco/normal), battery protected |
| S002-ATS-B1 | ATS | ❌ | ❌ | Monitoring only (critical safety) |
| S002-SOLAR-ROOF | Solar Inverter | ❌ | ❌ | MPPT autonomous, can monitor generation |
| S002-BESS-B1 | Battery | ⚠️ | ⚠️ | SOC target (Phase 34) |
| S002-MTR-MAIN | Energy Meter | ❌ | ❌ | Monitoring only |

---

## 6. Multi-Equipment Coordination

### Coordinated Optimization Examples

**Scenario 1: Cool Building at Night (COST Profile)**
```
Trigger: Off-peak hours (21:00-23:00) detected
Action: Coordinated sequence
  1. Lower chiller setpoint 8°C → 6°C (aggressive cooling)
  2. Increase AHU damper 30% → 70% (draw cooler outside air)
  3. Reduce lighting 100% → 20% (nighttime occupancy minimal)
  4. Dim DALI zones to 20% (security lighting only)

Effect: Pre-cool building overnight
  - Chiller runtime: 60 min
  - Energy cost: +200 R (chiller runs harder)
  - Next day peak cooling: -300 R (building already cool)
  - Net savings: -100 R

Timing: Sequential writes over 5 minutes
  - T+0s: Chiller setpoint write
  - T+30s: AHU damper write (allow 30s settling time)
  - T+60s: Lighting writes
```

**Scenario 2: Emergency Load Shedding (COST Profile)**
```
Trigger: Eskom stage 4 (400 MW deficit)
Action: Coordinated sequence
  1. Raise chiller setpoint 7°C → 8.5°C (reduce compressor load)
  2. Reduce AHU damper 60% → 40% (reduce motor load)
  3. Enable load shedding relay (if occupancy > 10%)
  4. Switch UPS to eco mode (reduce charging load)

Effect: Reduce site peak demand by ~150 kW
  - Comfort impact: Minimal (only 1.5°C increase)
  - Duration: 2 hours (typical stage 4)

Timing: Immediate writes (all within 30 seconds)
```

**Scenario 3: Multi-Zone Occupancy Optimization (COST Profile)**
```
Trigger: Occupancy drops to 20% (evening clearing)
Action: Zone-aware sequence
  1. For each occupied zone:
     - Keep FCU setpoint 23°C (occupied)
  2. For each unoccupied zone:
     - Raise FCU setpoint 24°C (reduce cooling)
  3. Reduce AHU damper for unoccupied zones (30%)
  4. Dim DALI lighting in unoccupied zones (5%)

Effect: Save energy in empty zones without affecting occupied zones

Timing: Parallel writes (all zones within 60 seconds)
```

### Rollback & Error Handling

If a write fails:
1. **Safety first:** Check if failure is due to device offline or permission
2. **Log the failure:** Audit trail records what failed
3. **Partial rollback:** Don't revert previous writes (already executed)
4. **Alert operator:** Dashboard shows "Write failed for equipment X"
5. **Fallback:** Switch to manual technician work order

**Example:**
```
Sequence: Chiller (✅) → AHU (✅) → FCU Zone 1 (❌)
Result: Chiller and AHU changes persist
        FCU Zone 1 change fails
        Alert: "Failed to update FCU-L1-A setpoint"
Next:   Operator approves manual work order for FCU only
```

---

## 7. Safety Gates Before Niagara Write

### Pre-Write Validation Checklist

```python
async def _validate_before_niagara_write(recommendation):

    # Gate 1: Safety Engine validation
    if not safety_engine.validate(
        equipment_id=recommendation["equipment_id"],
        point_name=recommendation["point_name"],
        new_value=recommendation["recommended_value"],
        priority=8
    ):
        return False, "Safety rules block this change"

    # Gate 2: Confidence threshold
    if recommendation["confidence"] < 0.85:
        return False, "Confidence too low for auto-execute"

    # Gate 3: Device online check
    device = device_manager.get_device(recommendation["equipment_id"])
    if device.status != DeviceStatus.ONLINE:
        return False, f"Device offline ({device.status})"

    # Gate 4: Occupancy check (for load shedding only)
    if recommendation["point_name"] == "load_shed_relay":
        occupancy = get_building_occupancy()
        if occupancy > 50:  # Don't shed if occupied
            return False, "Building occupied, cannot shed"

    # Gate 5: Priority array conflict
    # Check if higher priority (1-7) is already holding value
    current_priority = get_current_priority(device.id, point_name)
    if current_priority < 8:
        return False, "Higher priority already controlling point"

    return True, "All safety gates passed"
```

### Safety Rule Examples (from `safety_rules.json`)

```json
{
    "rules": [
        {
            "name": "Chiller Temperature Range",
            "equipment_type": "chiller",
            "parameter": "chw_supply_temp_setpoint",
            "min_value": 4.0,
            "max_value": 12.0,
            "severity": "BLOCK"
        },
        {
            "name": "Occupancy-Based Load Shedding",
            "equipment_type": "generator",
            "parameter": "load_shed_relay",
            "condition": "occupancy_percent < 10",
            "severity": "BLOCK",
            "message": "Cannot shed with occupants present"
        },
        {
            "name": "UPS Battery Reserve",
            "equipment_type": "ups",
            "parameter": "battery_soc_setpoint",
            "min_value": 30,
            "severity": "BLOCK",
            "message": "Must maintain minimum 30% battery reserve"
        }
    ]
}
```

---

## Summary: Data Flow from AI to Niagara

```
┌─────────────────────────────────────┐
│ AI Optimizer                        │
│ - Analyzes building conditions      │
│ - Selects optimization profile      │
│ - Generates recommendations         │
│ - Scores confidence (0-100%)        │
└──────────────┬──────────────────────┘
               │
               ├─► Recommendation stored in Supabase
               │   {equipment_id, point_name,
               │    current_value, recommended_value,
               │    confidence, reason, profile}
               │
               └─► Dashboard displays for user review
                   └─► User clicks "Approve"
                       │
                       ├─ Option A (Current): Create work order
                       │                      → Technician executes manually
                       │
                       └─ Option B (Planned): Approval triggers auto-execution
                          │
                          ├─ Safety validation
                          ├─ Confidence check (>= 85%)
                          ├─ Device online check
                          ├─ Occupancy check (if load shedding)
                          ├─ Priority array check
                          │
                          └─ NiagaraBACnetAdapter.write_value()
                             │
                             └─ BACnetClient.write_point(
                                 device_id=X,
                                 object_type="analogOutput",
                                 instance=Y,
                                 value=recommended_value,
                                 priority=8
                             )
                                │
                                └─ Niagara JACE/Supervisor
                                   └─ BACnet/IP write to device
                                      └─ Equipment responds + COV feedback
                                         │
                                         └─ Audit trail logged
                                            - Who approved
                                            - What changed
                                            - Result (success/fail)
```

---

## Deliverables Checklist

- [x] AI Optimizer equipment categorization (DeviceType mapping)
- [x] Three optimization profiles (SWEAT_ASSETS, COMFORT, COST) documented
- [x] Recommendation → Niagara write mapping table with examples
- [x] Confidence scoring inputs and autonomy thresholds
- [x] Equipment coverage assessment (controllable vs. read-only)
- [x] Multi-equipment coordination scenarios
- [x] Pre-write safety gates and validation checklist
- [x] Complete data flow from AI recommendation to Niagara BACnet write

---

**Next Step:** Task 2 will validate these mappings by running optimization tests and examining recommendation quality.
