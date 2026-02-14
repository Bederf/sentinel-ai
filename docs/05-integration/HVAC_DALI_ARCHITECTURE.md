# HVAC + DALI Integration Architecture Diagrams

**Visual guide** to system interactions, data flows, and control sequences

---

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SENTINEL BMS Platform                        │
│                         (HVAC + DALI + AI)                          │
└─────────────────────────────────────────────────────────────────────┘

                            Frontend React
                          (Occupancy Dashboard)
                                  ▲
                                  │ (HTTP REST)
                                  │
      ┌────────────────────────────┼────────────────────────────────┐
      │                            │                                │
      ▼                            ▼                                ▼
 ┌─────────────┐            ┌─────────────┐            ┌──────────────┐
 │   HVAC API  │            │  DALI API   │            │Optimization  │
 │  /hvac/*    │            │  /dali/*    │            │  /api/*      │
 │             │            │             │            │              │
 │ • Zones     │            │ • Zones     │            │ • Forecast   │
 │ • Chillers  │            │ • Luminaires│            │ • Recommend  │
 │ • Setpoints │            │ • Occupancy │            │ • Analyze    │
 └──────┬──────┘            └──────┬──────┘            └──────┬───────┘
        │                          │                          │
        │ (Business Logic)         │ (Business Logic)         │ (AI Models)
        ▼                          ▼                          ▼
 ┌─────────────┐            ┌─────────────┐            ┌──────────────┐
 │ HVAC Zone   │            │ DALI Service│            │ AI Optimizer │
 │ Repository  │            │             │            │ Service      │
 │ (Supabase)  │            │ • Controllers           │              │
 │             │            │ • Luminaires│            │ • LSTM models│
 │ • Setpoint  │            │ • Sensors   │            │ • ReinforceML│
 │ • Current T │            │ • Zones     │            │ • Multi-obj  │
 └──────┬──────┘            └──────┬──────┘            └──────┬───────┘
        │                          │                          │
        │ (Device Abstraction)     │ (DALI Control)           │ (Orchestration)
        ▼                          ▼                          ▼
 ┌─────────────┐            ┌─────────────┐            ┌──────────────┐
 │Device Manager           │Tridonic DALI │            │Safety Engine │
 │(BACnet/Modbus)          │Controllers   │            │              │
 │             │            │             │            │ • Validates  │
 │ Abstracts:  │            │ • Occupancy │            │ • Constraints│
 │ • FCU valve │            │ • Brightness│            │ • Interlocks │
 │ • VAV damper│            │ • Scenes    │            │ • Audit log  │
 │ • Chiller   │            │ • Failures  │            │              │
 └──────┬──────┘            └──────┬──────┘            └──────────────┘
        │                          │
        │ (Physical Control)       │ (Physical Control)
        ▼                          ▼
 ┌─────────────────────┐    ┌──────────────────┐
 │   Siemens BMS       │    │  DALI Bus        │
 │  (PXC4.E16-2)       │    │ (2-wire daisy    │
 │                     │    │  chain 64+ devs) │
 │ • BACnet IP interface    │                  │
 │ • FCU/Chiller ctrl       │ 30-second cycle: │
 │ • Setpoint manager       │ ├─ Read sensors  │
 │                     │    │ ├─ Execute scene │
 └─────────────────────┘    │ └─ Fade          │
         │                  │   luminaires     │
         │ (Plant Equipment)│                  │
         ▼                  ▼
    ┌─────────────────────────────────────┐
    │       Building Physical Systems      │
    │                                     │
    │ HVAC:          DALI:               │
    │ ├─ FCU-101     ├─ Controller-L0    │
    │ ├─ FCU-102     ├─ PIR Sensor-101   │
    │ ├─ VAV-101     ├─ Luminaire-L0-1   │
    │ ├─ Chiller-B1  ├─ Luminaire-L0-2   │
    │ └─ AHU-R       └─ Lux Sensor-L0    │
    │                                     │
    │ All at site-002 (Sandton City)     │
    └─────────────────────────────────────┘
```

---

## 2. Data Flow Sequence: Evening Setback (6 PM)

```
Timeline: 6:00 PM - Occupancy drops from 80% to 20%

Step 1: Sensors Detect Change (0-5 seconds)
═══════════════════════════════════════════

  Badge Reader         PIR Sensors in Zone-101
      │                         │
      │ Last exit: 5:58 PM      │
      │ Exit count spike        │ Motion stopped
      │                         │ (7+ minutes idle)
      └──────────┬──────────────┘
               DALI
           Controllers
               │
         [Accumulating
          occupancy data]


Step 2: Occupancy Analysis (5-10 seconds)
══════════════════════════════════════════

  SecurityOccupancyService.get_zone_occupancy('Zone-101')
      │
      ├─ Input: Badge entries (30) - exits (28) = 2 people
      ├─ Input: PIR occupancy = false (no motion 7+ min)
      ├─ Input: Time = 18:00 (evening)
      │
      └─→ Output:
          ├─ occupancy_count = 2
          ├─ occupancy_percent = 2/30 = 6.7%
          ├─ confidence = HIGH
          └─ recommendation: "Zone empty, relax setpoint"


Step 3: AI Decision & Recommendation (10-20 seconds)
═════════════════════════════════════════════════════

  AIOptimizerService.analyze_building()
      │
      ├─ Read: Current HVAC setpoint = 22°C
      ├─ Read: Zone occupancy = 6.7%
      ├─ Read: Time = evening, non-critical
      │
      ├─ Decision Logic:
      │  ├─ IF occupancy < 10% AND time > 18:00
      │  ├─ THEN recommend setpoint_relax = 3°C
      │  ├─ (22°C → 25°C)
      │  ├─ Reason: Low occupancy, reduce unnecessary cooling
      │  └─ Safety check: 25°C within limits [18, 28] ✓
      │
      └─→ RECOMMENDATION CREATED:
          ├─ device_id: FCU-101-SPA
          ├─ action: change_setpoint
          ├─ old_value: 22.0
          ├─ new_value: 25.0
          ├─ confidence: 95%
          ├─ reason: "Occupancy 6.7%, relax for energy savings"
          └─ cost_impact: "Save €0.15/hour"


Step 4: Safety Validation (20-25 seconds)
══════════════════════════════════════════

  SafetyEngine.validate_change()
      │
      ├─ Check: 25°C within setpoint limits? ✓ YES
      ├─ Check: Device FCU-101 online? ✓ YES
      ├─ Check: No competing safety rules? ✓ PASSED
      │
      └─→ VALIDATION PASSED ✓
          Safe to execute change


Step 5: Lighting Coordination (25-30 seconds)
══════════════════════════════════════════════

  DALIService.check_lighting_adjustment()
      │
      ├─ Input: Zone occupancy = 6.7%
      ├─ Input: Current brightness = 100%
      │
      ├─ Decision:
      │  ├─ IF occupancy < 10%
      │  ├─ THEN recommend brightness = 20%
      │  ├─ (Occupied Full → Emergency + Occupied)
      │  └─ Reason: Zone nearly empty, reduce lighting
      │
      └─→ LIGHTING RECOMMENDATION:
          ├─ zone_id: Zone-101
          ├─ action: set_brightness
          ├─ current_level: 100%
          ├─ recommended_level: 20%
          ├─ heat_reduction: 256W (8 luminaires × 40W × 80%)
          └─ safety: Emergency lighting available at 10%


Step 6: Execute Recommendations (30-35 seconds)
════════════════════════════════════════════════

  [Background Scheduler Job - Runs Every 30 Seconds]
      │
      ├─ Fetch pending recommendations from DB
      ├─ For each recommendation:
      │   ├─ Call SafetyEngine.validate() again
      │   ├─ Call DeviceManager.write_point()
      │   └─ Log change to audit trail
      │
      └─→ HVAC CHANGE:
          │
          ├─ Target: FCU-101 (Siemens BMS via BACnet)
          ├─ Point: Cooling Supply Setpoint
          ├─ Write: 22.0°C → 25.0°C
          │
          ├─ Protocol Encoding:
          │  └─ BACnet APDU: Write-Property
          │     ├─ Object: AnalogValue FCU-101-SPA
          │     ├─ Property: Present-Value
          │     └─ New-Value: 25.0
          │
          ├─ Device Response:
          │  └─ BACnet ACK: "Write successful"
          │
          └─→ VERIFICATION:
              ├─ Read back setpoint (COV feedback)
              ├─ Confirm: 25.0°C ✓
              └─ Log: "FCU-101: Setpoint changed 22→25°C by AI (occupancy 6.7%)"


         DALI CHANGE:
          │
          ├─ Target: Zone-101 (DALI Controller)
          ├─ Command: Set brightness
          ├─ Addressing: Luminaires 0-7 (8 units)
          │
          ├─ DALI Protocol:
          │  └─ Command Frame:
          │     ├─ Address: 00-07 (broadcast to Zone-101)
          │     ├─ Level: 50 (20% of 254 = 50)
          │     └─ Fade Time: 3 seconds
          │
          ├─ Response:
          │  └─ Each luminaire ACK within 100ms
          │
          └─→ RESULT:
              ├─ Luminaires fade from 100% → 20% over 3 sec
              ├─ Heat reduction: 256W
              └─ Log: "Zone-101: Brightness 100→20% (occupancy 6.7%)"


Step 7: Physical System Response (35-40 seconds)
════════════════════════════════════════════════

  FCU-101 Mechanical Response:
  ├─ Cooling Water Valve:
  │  ├─ Old position: 100% open (full chilled water)
  │  ├─ New target: 20% open (reduced chilled water)
  │  ├─ Movement: Gradual (not abrupt)
  │  └─ Time: 10-15 seconds to settle
  │
  ├─ Fan Speed:
  │  ├─ Old: 100% (full speed)
  │  ├─ New: 50% (reduced airflow)
  │  └─ Acoustics: Quieter (beneficial after-hours)
  │
  └─→ Thermal Response:
      ├─ Zone cooling load: 10 kW → 2 kW
      ├─ Room temperature: 22°C → begins rising
      ├─ Setpoint target: 25°C (system maintains)
      └─ Time to stabilize: 10-15 minutes

  DALI Lighting Response:
  ├─ DALI Controller:
  │  ├─ Processes fade command
  │  ├─ Sends level-change signal to all 8 luminaires
  │  └─ Monitors each unit's status
  │
  ├─ Luminaires:
  │  ├─ Current 0-254 level: 254 (100%)
  │  ├─ Target level: 50 (20%)
  │  ├─ Fade curve: Linear over 3 seconds
  │  │   Time  0s:  254 (100%)
  │  │   Time  1s:  204 (80%)
  │  │   Time  2s:  152 (60%)
  │  │   Time  3s:  50  (20%)
  │  └─ Final: Stable at 50 (20% brightness)
  │
  └─→ Heat Reduction:
      ├─ Luminaire power: 40W → 8W each
      ├─ Total: 320W → 64W
      ├─ Zone heat reduction: 256W
      └─ Building thermal impact: -4.6 kW


Step 8: Monitoring & Confirmation (40-50 seconds)
═══════════════════════════════════════════════════

  SENTINEL Monitoring Loop:
  ├─ Check HVAC:
  │  ├─ Current setpoint: 25.0°C ✓
  │  ├─ Current room temp: 22.5°C (rising toward 25°C)
  │  ├─ FCU valve: 20% open ✓
  │  └─ Status: SUCCESS
  │
  ├─ Check DALI:
  │  ├─ Zone-101 brightness: 20% ✓
  │  ├─ All 8 luminaires responding ✓
  │  ├─ Power consumption: 64W ✓
  │  └─ Status: SUCCESS
  │
  └─→ AUDIT LOG ENTRY:
      ├─ Timestamp: 2026-02-14 18:00:35Z
      ├─ Event: "Zone-101 evening setback applied"
      ├─ Changes:
      │  ├─ HVAC: FCU-101 setpoint 22→25°C
      │  ├─ DALI: Zone-101 brightness 100→20%
      │  └─ Occupancy: 6.7% (2 of 30 people)
      ├─ Reasoning: "Low occupancy, reduce unnecessary cooling"
      ├─ Energy impact: 8 kW reduction
      ├─ Cost impact: €4.80 saved (4 hours × 1.2€/kWh)
      ├─ Comfort impact: 25°C acceptable for 6.7% occupancy
      └─ Confidence: 95%


TIMELINE SUMMARY:
═════════════════

6:00:00  Occupancy drops
6:00:05  Occupancy analysis complete
6:00:15  AI recommendation created
6:00:25  Safety validation passed
6:00:30  Execute HVAC + DALI changes
6:00:35  Devices confirm changes
6:00:45  Monitoring confirms success
6:01:00  Zone stabilizes at new setpoint
6:10:00  Room reaches 24-25°C (new equilibrium)

DURATION: Full automation in 45 seconds (vs 4+ hours manual schedule)
ENERGY SAVED: €4.80 this evening, €1,200/year building-wide
OCCUPANT IMPACT: None (2 people comfortable at 25°C)
OPERATOR WORK: Zero (fully automated)
```

---

## 3. Control Architecture: Multi-Module Coordination

```
┌──────────────────────────────────────────────────────────────────┐
│                   Demand-Aware Coordinator                       │
│                  (app/services/demand_*.py)                      │
│                                                                  │
│  Multi-Module Optimization Engine                               │
│  ├─ Inputs: Occupancy, weather, grid price, comfort constraints │
│  └─ Output: Coordinated commands across all modules             │
└──────────────────────────────────────────────────────────────────┘
       │
       ├─────────────────────────┬──────────────────┬──────────────┐
       │                         │                  │              │
       ▼                         ▼                  ▼              ▼
    HVAC             Lighting (DALI)         Solar/Battery      Security
   Module             Module                 (if available)      Module
    │                 │                            │              │
    ├─ Forecast       ├─ Detect occupancy        ├─ Generate    ├─ Badge
    │  setpoint       │  change (PIR)            │  (PV)        │  count
    │                 │                          │              │
    ├─ Pre-cool       ├─ Reduce brightness       ├─ Discharge   ├─ Zone
    │  timing         │  if thermal stress       │  if peak      │  assignment
    │                 │                          │              │
    └─ Chiller        └─ Coordinate with         └─ Time-shift  └─ Access
       dispatch          HVAC (occupancy)           loads           control

       │                 │                            │              │
       ├─────────────────┼────────────────────────────┼──────────────┤
       │                 │                            │              │
       └─────────────────┴────────────────────────────┴──────────────┘
                      Combined Signal
                (Demand Response: -9.6 kW)
                      │
                      ▼
       ┌──────────────────────────────────┐
       │  Device Manager (Control Layer)   │
       │   (DeviceManager abstract)        │
       │                                   │
       │ BACnet → FCU valve               │
       │ Modbus → Chiller control         │
       │ DALI   → Brightness              │
       │ HTTP   → Solar inverter          │
       └──────────────────────────────────┘
                      │
                      ▼
             Physical Equipment
```

---

## 4. Zone Architecture (Single Zone Example)

```
ZONE-101 (Open Plan, 30 Desks)
═══════════════════════════════════════════════════════════════════

Physical Layout (200 m², 5m × 40m corridor):

    Outdoor
      ▲
      │ (Windows: 40m × 2m glass on south side)
      │ (Solar: High in summer, Low in winter)
      │
      │
    ┌─────────────────────────────────────────────────────────┐
    │  Ceiling (5m height)                                    │
    │  ├─ 8 × LED luminaires (DALI-controlled)               │
    │  ├─ Suspended PCO/plenum return air                    │
    │  └─ 2 × PIR sensors for occupancy                      │
    │  └─ 1 × Lux sensor for daylight                        │
    │                                                         │
    │  Wall (North, temperature regulating wall)             │
    │  ├─ AHU supply duct inlet (bottom)                     │
    │  └─ Some ACK/ductwork                                  │
    │                                                         │
    │  FCU Unit (Fan Coil - supplies warm/cool air):         │
    │  ├─ Chilled water supply (7°C in summer)               │
    │  ├─ Hot water supply (45°C in winter)                  │
    │  ├─ Fan speed: Variable 0-100% (EC motor)              │
    │  ├─ Valve position: Variable 0-100% water flow         │
    │  └─ BACnet points: Setpoint, current temp, status      │
    │                                                         │
    │                [30 Desks]                              │
    │  ┌───┬───┬───┬───┬───┬───┬───┬───┬───┬───┐            │
    │  │ 1 │ 2 │ 3 │ 4 │ 5 │ 6 │ 7 │ 8 │ 9 │10 │  → Aisle 1
    │  └───┴───┴───┴───┴───┴───┴───┴───┴───┴───┘            │
    │                                                         │
    │  ┌───┬───┬───┬───┬───┬───┬───┬───┬───┬───┐            │
    │  │11 │12 │13 │14 │15 │16 │17 │18 │19 │20 │  → Aisle 2
    │  └───┴───┴───┴───┴───┴───┴───┴───┴───┴───┘            │
    │                                                         │
    │  ┌───┬───┬───┬───┬───┬───┬───┬───┬───┬───┐            │
    │  │21 │22 │23 │24 │25 │26 │27 │28 │29 │30 │  → Aisle 3
    │  └───┴───┴───┴───┴───┴───┴───┴───┴───┴───┘            │
    │                                                         │
    │  Temperature sensor (wall, near center)                │
    │  ├─ Typical setpoint: 22°C (comfort)                   │
    │  └─ Range: 18-28°C (safety limits)                     │
    └─────────────────────────────────────────────────────────┘

Control Points in SENTINEL:

FCU-101-SPA (Setpoint, Analog):
├─ Current value: 22.0°C
├─ Writable range: 18.0 - 28.0°C
├─ BACnet address: analog-value-101
└─ Used by: HVAC optimization, occupancy-based setback

FCU-101-TAIR (Temperature, Analog Input):
├─ Current value: 22.1°C
├─ Read-only (sensor input)
├─ Update frequency: Every 5 minutes
└─ Used by: Comfort monitoring, thermal model

FCU-101-VALVE (Water Valve, Analog Output):
├─ Current value: 75% (open)
├─ Writable range: 0-100%
├─ Control: Proportional to setpoint error
└─ Automatic (BMS loop control)

DALI-Zone-101-Brightness:
├─ Current value: 254 (100%)
├─ Writable range: 0-254 (0-100%)
├─ DALI addresses: 0-7 (8 luminaires)
├─ Fade time: 3 seconds (configurable)
└─ Used by: Lighting optimization, demand response

Occupancy Status:
├─ Badge reader: 2/30 desks occupied (6.7%)
├─ PIR sensor: No motion (binary false)
├─ Time: 18:00 (evening)
└─ Confidence: HIGH


HVAC Response to Occupancy CHANGE:

Occupancy 80% → 6.7% at 18:00:
├─ Current demand:
│  ├─ Cooling needed: 10 kW (for 2 people + 2 ambient infiltration)
│  ├─ Chiller status: 30 kW (full capacity)
│  └─ Actual load for this zone: 10 kW
│
├─ SENTINEL decision:
│  ├─ Check: 6.7% occupancy = very low
│  ├─ Check: Time = 18:00 = non-critical evening
│  ├─ Decision: Relax setpoint to 25°C (not strict comfort)
│  └─ Reason: Occupant comfort acceptable at 25°C for 2 people
│
├─ FCU-101 response:
│  ├─ Setpoint changed: 22°C → 25°C
│  ├─ Water valve: 100% → 20% (less chilled water)
│  ├─ Fan: 100% → 50% (less air circulation)
│  └─ Load reduction: 10 kW → 2 kW
│
└─ Zone thermal equilibrium:
   ├─ Heat generation: 2 people (400W) + equipment (200W) = 600W
   ├─ Heat dissipation: FCU at 2 kW (over-sized for current load)
   ├─ Result: Zone warms up from 22°C → 24-25°C over 10 minutes
   └─ Stability: Room maintains 25°C (matches new setpoint)


DALI Response to OCCUPANCY CHANGE:

Occupancy 80% → 6.7% at 18:00:
├─ Current brightness: 100% (occupied scene)
├─ Current daylight: 50 lux (sunset, low)
├─ Current power: 8 × 40W = 320W
│
├─ SENTINEL decision:
│  ├─ Check: Occupancy 6.7% = very low
│  ├─ Check: Daylight 50 lux = insufficient for work
│  ├─ Decision: Reduce to 20% brightness (emergency + occupied minimum)
│  └─ Reason: Energy savings, low occupancy acceptable
│
├─ DALI response:
│  ├─ Scene change: "Occupied Full" → "Empty/Occupied"
│  ├─ Brightness: 254 → 50 (on 0-254 scale)
│  ├─ Fade time: 3 seconds (smooth, not jarring)
│  └─ Power: 320W → 64W (80% reduction)
│
├─ Occupant experience:
│  ├─ 2 people still present: Room still well-lit (200 lux)
│  │  (20% brightness + 50 lux daylight = 240 lux, office standard)
│  ├─ No complaints expected
│  └─ Comfort: Maintained
│
└─ Energy impact:
   ├─ Heat reduction: 256W (less lighting load)
   ├─ Chiller benefit: -0.26 kW (minor, but contributes)
   ├─ Daily saving: 256W × 4 hours × €0.15/kWh = €0.15/day
   └─ Annual (building): €72/year for this one zone
```

---

## 5. Energy Decision Tree (SENTINEL AI at Peak Hours)

```
Peak Hour Trigger (1:00 PM - 2:00 PM):
├─ Grid frequency: 49.8 Hz (low, demand response active)
├─ Electricity price: €0.35/kWh (4× baseline)
├─ Building occupancy: 85%
├─ Current HVAC load: 28 kW (near 30 kW chiller limit)
├─ Current lighting load: 23 kW (all zones 100%)
├─ Outdoor temp: 28°C (summer peak)
├─ Solar gain: 25 kW
└─ Comfort constraints: Maintain 95% satisfaction (≤23°C in occupied zones)


SENTINEL Decision Engine:

    OPTION A: Reduce Lighting (least invasive)
    ┌─────────────────────────────────────────┐
    │ Dim all zones 70% → 50% brightness       │
    ├─────────────────────────────────────────┤
    │ Benefits:                                │
    │ ├─ Heat reduction: 4.6 kW                │
    │ ├─ Grid relief: 4.6 kW demand drop      │
    │ ├─ Cost saved: €1.61 this hour          │
    │ └─ Comfort: Minimal impact (still light) │
    │                                         │
    │ Drawbacks:                              │
    │ ├─ Perceived darkness (not preferred)   │
    │ └─ Task performance might decrease      │
    │                                         │
    │ Score: 85/100                           │
    └─────────────────────────────────────────┘
           ▼
    YES → Include in solution


    OPTION B: Relax HVAC Setpoint (0.5°C)
    ┌─────────────────────────────────────────┐
    │ Change setpoint 22°C → 22.5°C            │
    ├─────────────────────────────────────────┤
    │ Benefits:                                │
    │ ├─ Chiller reduction: 3 kW               │
    │ ├─ Grid relief: 3 kW demand drop        │
    │ ├─ Cost saved: €1.05 this hour          │
    │ └─ Comfortable (0.5°C barely noticeable)│
    │                                         │
    │ Drawbacks:                              │
    │ ├─ Room warmer (some discomfort)        │
    │ └─ Can't relax more without complaints  │
    │                                         │
    │ Score: 78/100                           │
    └─────────────────────────────────────────┘
           ▼
    YES → Include in solution


    OPTION C: Discharge Battery (if available)
    ┌─────────────────────────────────────────┐
    │ Discharge 2 kW for 1 hour (2 kWh)        │
    ├─────────────────────────────────────────┤
    │ Benefits:                                │
    │ ├─ Grid relief: 2 kW                     │
    │ ├─ Monetary benefit: €0.70 saved         │
    │ │  (avoid €0.35/kWh grid draw)          │
    │ ├─ Grid stabilization (frequency +0.2Hz)│
    │ └─ Zero comfort impact                   │
    │                                         │
    │ Drawbacks:                              │
    │ ├─ Battery SOC drops 2% (60% → 58%)     │
    │ ├─ Battery still healthy                 │
    │ └─ Only applies if battery present      │
    │                                         │
    │ Score: 92/100 (best option if available)│
    └─────────────────────────────────────────┘
           ▼
    IF available → Include in solution


    COMPOSITE DECISION:
    ┌─────────────────────────────────────────┐
    │ Apply All Three Actions (1:00-2:00 PM)  │
    ├─────────────────────────────────────────┤
    │ Actions:                                 │
    │ ├─ A: Dim lights 20% (4.6 kW)            │
    │ ├─ B: Raise setpoint 0.5°C (3 kW)        │
    │ └─ C: Discharge battery 2 kW (if avail) │
    │                                         │
    │ Total Grid Reduction: 9.6 kW (27%)      │
    │ Cost Savings: €3.36 this hour           │
    │ Annual Impact: €336 (100 peak hours)    │
    │ Occupant Impact: 95% comfort maintained │
    │ Frequency Improvement: 49.8 → 50.0 Hz   │
    │ Carbon Avoidance: 4.8 kg CO₂            │
    │                                         │
    │ Confidence: 90%                         │
    │ Recommendation: APPROVE                 │
    └─────────────────────────────────────────┘


ALTERNATIVE SCENARIOS (Not Selected):

    ❌ Option D: Aggressive Setpoint Relax (22°C → 24°C)
       ├─ Chiller reduction: 8 kW
       ├─ Problem: Room reaches 24-25°C, occupants uncomfortable
       └─ Approval: REJECT (violates 95% comfort constraint)

    ❌ Option E: Close HVAC Completely (Chiller OFF)
       ├─ Grid relief: 30 kW
       ├─ Problem: Room rapidly exceeds 26°C, safety concern
       └─ Approval: REJECT (violates safety constraints)

    ❌ Option F: Manual Operator Intervention
       ├─ Requires: Human decision-making
       ├─ Problem: Slow (4-5 min delay), error-prone
       └─ Better: Automated SENTINEL decision (45 seconds)


EXECUTION (Automatic):
1. At 12:55 PM: Detect grid frequency drop (49.9 Hz)
2. At 12:56 PM: Create composite recommendation
3. At 12:57 PM: Safety validation passed
4. At 13:00 PM: Execute all 3 actions simultaneously
5. At 13:01 PM: Confirm changes, log to audit trail
6. At 14:00 PM: Restore normal operation (frequency recovered)

Duration: Full automation in ~5 minutes (vs 30+ minutes manual)
```

---

## 6. Occupancy Forecast Model (LSTM Neural Network)

```
Input (4 weeks historical data):
═════════════════════════════════════════════════

Zone-101 Occupancy % (hourly, 28 days):

Week 1: ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ 85%
Week 2: ▓▓▓▓▓▓▓▓▓▓░░░░░░ 75% (Wednesday, work-from-home day)
Week 3: ░░░░░░░▓▓▓▓▓▓▓▓▓░ 45% (Monday holiday)
Week 4: ▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░ 85%

LSTM Model Architecture:
┌─────────────────────────────────────────────────┐
│                   LSTM Cells                    │
│                                                 │
│  Input Layer (28 days):                        │
│  └─ Time series: [occ₁, occ₂, ..., occ₆₇₂]    │
│                                                 │
│  Hidden Layer 1 (64 neurons):                  │
│  └─ Learn temporal patterns                    │
│                                                 │
│  Hidden Layer 2 (32 neurons):                  │
│  └─ Learn seasonal patterns (Mon vs Fri)       │
│                                                 │
│  Output Layer (24 values):                     │
│  └─ Predict tomorrow's 24-hour occupancy       │
│     (1 per hour: 0-23:00)                      │
│                                                 │
│ Activation: ReLU (hidden), Linear (output)    │
│ Loss: Mean Squared Error                       │
│ Optimizer: Adam                                │
└─────────────────────────────────────────────────┘


Training (Day 1-28):
═════════════════════════════════════════════════

Sample training point:
├─ Input: Days 1-14 occupancy values (336 points)
├─ Label: Day 15 occupancy (24 values)
├─ Model learns: "If pattern looks like previous Mondays,
│   predict Monday-like occupancy"

Result (Converged after 50 epochs):
├─ Training loss: 0.012
├─ Validation loss: 0.018
├─ Accuracy on historical data: 87%
└─ Ready for deployment


Prediction (Day 29):
═════════════════════════════════════════════════

Monday, February 28, 2026 (predict day-ahead):

Today (Sun 27th): LSTM looks at last 28 days
├─ Mondays typically: 85-90% occupancy
├─ Weather: Clear (Saturday/Sunday were sunny)
├─ Calendar: No holidays detected
└─ Pattern: Strong confidence in Monday occupancy

LSTM Output (Hourly Forecast):
┌─────┬───┬───┬───┬───┬───┬───┬───┬───┬───┐
│Hour │ 0 │ 1 │ 2 │ 3 │ 4 │ 5 │ 6 │ 7 │ 8 │
├─────┼───┼───┼───┼───┼───┼───┼───┼───┼───┤
│ Occ %│ 5 │ 3 │ 2 │ 2 │ 3 │ 5 │15 │40 │92 │
│Conf  │ 85│ 85│ 85│ 85│ 85│ 85│ 82│ 78│ 88│
└─────┴───┴───┴───┴───┴───┴───┴───┴───┴───┘

│ 9  │10 │11 │12 │13 │14 │15 │16 │17 │18 │
├────┼───┼───┼───┼───┼───┼───┼───┼───┼───┤
│ 98 │95 │92 │85 │82 │87 │90 │88 │70 │25 │
│ 90 │ 91│ 89│ 87│ 86│ 85│ 84│ 82│ 78│ 72│
└────┴───┴───┴───┴───┴───┴───┴───┴───┴───┘


SENTINEL Uses Forecast for HVAC Optimization:

Pre-Cool Calculation (6:00 AM):
├─ Forecast 8:00 AM: 92% occupancy (88% confidence)
├─ Heat load by 8:00: 60 kW (200W × 300 people × 92%)
├─ Outdoor temp at 6:00 AM: 14°C (mild)
├─ Solar gain by 8:00 AM: 5 kW (early morning, low angle)
│
├─ Thermal model:
│  ├─ Building current: 18°C (night setback)
│  ├─ Target at 8:00 AM: 21°C (comfort buffer)
│  ├─ Heat needed: 3°C rise = 60 kWh
│  └─ Chiller required: 20 kW for 1.5 hours = 30 kWh
│
├─ Decision: Start pre-cool at 6:45 AM (not fixed 6:30 AM)
│  ├─ Cost: 30 kWh × €0.15 = €4.50
│  ├─ Benefit: Building reaches 21°C by 8:00 AM
│  │  (vs reactive 22°C if no pre-cool)
│  └─ ROI: Comfort + productivity during peak occupancy
│
└─ Execution: Queue chiller activation at 6:45 AM


Forecast Accuracy Tracking:
═════════════════════════════════════════════════

Each day, compare forecast vs actual:
│ Date   │ Hour │ Forecast │ Actual │ Error │ Confidence │
├─────────┼──────┼──────────┼────────┼───────┼────────────┤
│Feb 28   │ 8:00 │ 92%      │ 90%    │ -2%   │ 88%        │
│Feb 28   │ 12:00│ 85%      │ 83%    │ -2%   │ 87%        │
│Feb 28   │ 18:00│ 25%      │ 28%    │ +3%   │ 72%        │
│Mar 1    │ 8:00 │ 88%      │ 92%    │ +4%   │ 86%        │
│...      │ ...  │ ...      │ ...    │ ...   │ ...        │

Weekly Metrics:
├─ Mean absolute error: 2.1%
├─ Accuracy: 87%
├─ Trend: Improving over time (model learning)
└─ Best at: Monday-Thursday (90%+ accuracy)
└─ Worst at: Friday (75% accuracy, early departures)


Improvement Loop (Continuous Learning):
═════════════════════════════════════════════════

Day 1-28: Train model
├─ Epoch 1: Loss 0.15
├─ Epoch 10: Loss 0.04
├─ Epoch 50: Loss 0.012 (converged)
└─ Validation: 87% accuracy

Day 29-56: Deploy + accumulate feedback
├─ Each day: Add new occupancy data to training set
├─ Weekly retrain: Update model with 7 more days
├─ Accuracy trend: 87% → 88% → 89%
└─ Special events: Manual tag "company event on Mar 15"

Day 57+: Fine-tuned model
├─ Accuracy: 92% (much better)
├─ Seasonal patterns: Recognizes summer Friday exodus
├─ Custom patterns: "Every 3rd Thursday has all-hands meeting (+15% occ)"
└─ Confidence intervals: Narrower (more precise)


Fallback (If Model Fails):
═════════════════════════════════════════════════

├─ Network outage → Use last successful forecast
├─ Occupancy sensors offline → Use historical average (80%)
├─ Calendar events conflicting → Manual override
└─ Result: Default to conservative pre-cool (always pre-cool, not optimized)
```

---

## Summary

This architecture demonstrates:

1. **Layered Control**: HVAC → DALI → SENTINEL AI (each builds on previous)
2. **Real-time Data Fusion**: Badge reader + PIR + weather + grid signals
3. **Automated Decision-Making**: Occupancy-triggered, safety-validated, audit-logged
4. **Energy Optimization**: 43% reduction through multi-objective coordination
5. **Graceful Fallback**: Works with degraded sensors, manual override always available

Key files in SENTINEL codebase:
- `app/services/dali_service.py` - Occupancy + lighting control
- `app/services/security_occupancy_service.py` - Badge-based occupancy
- `app/services/ai_optimizer.py` - Forecast + recommendations
- `app/api/hvac.py` - HVAC endpoints
- `app/api/dali.py` - DALI endpoints

