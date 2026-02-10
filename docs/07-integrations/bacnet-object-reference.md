---
title: "BACnet Object Type Reference & SENTINEL Taxonomy Mapping"
type: "technical-reference"
status: "active"
version: "1.0.0"
created: "2026-02-10"
updated: "2026-02-10"
author: "SENTINEL Development Team"
tags: ["bacnet", "object-types", "taxonomy", "data-points", "mapping"]
domain: "bms"
audience: ["developers", "integrators"]
complexity: "advanced"
estimated_read_time: 35
---

# BACnet Object Type Reference & SENTINEL Taxonomy Mapping

Complete mapping of BACnet standard object types to SENTINEL equipment taxonomy. Used by Clawd Bot to classify discovered points and determine which equipment types can be monitored.

---

## BACnet Object Types (ISO 16663-6)

### Standard Object Classes

| BACnet Object Type | Purpose | SENTINEL Mapping |
|-------------------|---------|-----------------|
| ANALOG_INPUT | Real-time sensor value (read-only) | Sensor data points |
| ANALOG_OUTPUT | Setpoint or command (read-write) | Control output signals |
| ANALOG_VALUE | Computed/intermediate value | Derived metrics |
| BINARY_INPUT | On/Off sensor (read-only) | Status flags |
| BINARY_OUTPUT | On/Off command (read-write) | Binary control (pump on/off) |
| BINARY_VALUE | Computed binary state | Equipment status states |
| MULTI_STATE_INPUT | 1-to-N state (read-only) | Mode indicators (Heat/Cool/Off) |
| MULTI_STATE_OUTPUT | 1-to-N command (read-write) | Mode selection |
| MULTI_STATE_VALUE | Computed state | Inferred equipment state |

---

## SENTINEL Equipment Taxonomy & Required Point Types

### HVAC Equipment Class: Chiller (S00X-CHILLER-B1-001)

**Required BACnet Objects:**

```
Monitoring Points (ANALOG_INPUT):
├─ chw_supply_temperature
│  Object Type: ANALOG_INPUT
│  Units: °C (degreesCelsius)
│  Range: -5 to +30°C (typical)
│  Purpose: FLC detection (smooth curves = FLC, oscillation = PID)
│  Update Rate: COV or 30 seconds
│
├─ chw_return_temperature
│  Object Type: ANALOG_INPUT
│  Units: °C
│  Range: 8 to +35°C
│  Purpose: Calculate delta-T for efficiency assessment
│
├─ compressor_outlet_pressure
│  Object Type: ANALOG_INPUT
│  Units: kPa (kilopascals)
│  Range: 200-400 kPa (medium pressure)
│  Purpose: Detect compressor health degradation
│
├─ condenser_outlet_pressure
│  Object Type: ANALOG_INPUT
│  Units: kPa
│  Range: 800-1200 kPa (high pressure)
│  Purpose: Cooling tower fouling detection
│
├─ chiller_power_consumption
│  Object Type: ANALOG_INPUT
│  Units: kW (kilowatts)
│  Range: 0-220 kW (for 220kW unit)
│  Purpose: Energy efficiency scoring, anomaly detection
│
└─ condenser_fan_status
   Object Type: BINARY_INPUT
   Range: 0 (off) / 1 (on)
   Purpose: Detect fan failure

Control Points (ANALOG_OUTPUT / MULTI_STATE_OUTPUT):
├─ chw_setpoint_command
│  Object Type: ANALOG_OUTPUT
│  Units: °C
│  Range: 4-12°C (typical commissioning range)
│  Purpose: Remote setpoint adjustment via SENTINEL recommendations
│  Access: Read-write with safety validation
│
├─ cooling_mode
│  Object Type: MULTI_STATE_OUTPUT
│  States: 1=Off, 2=Cool, 3=Auto
│  Purpose: Enable SENTINEL to manage chiller startup/shutdown
│
└─ compressor_command_percent
   Object Type: ANALOG_OUTPUT
   Units: % (0-100%)
   Range: 0-100%
   Purpose: Direct capacity modulation (if allowed by safety rules)

Status Points (BINARY_INPUT):
├─ alarm_high_pressure
│  High-side pressure exceeded
│
├─ alarm_low_pressure
│  Low-side pressure too low
│
├─ alarm_motor_overload
│  Compressor overload protection
│
├─ alarm_freeze_protection
│  Supply temperature dropping below threshold
│
└─ alarm_communication_fault
   Loss of control signal
```

**SENTINEL Point Naming:**
```
In SENTINEL database (after import):
{
  equipment_id: "S002-CHILLER-B1-001",
  equipment_type: "chiller",
  points: {
    "chw_supply_temp_sp": { object_type: "ANALOG_OUTPUT", ... },
    "chw_supply_temp_actual": { object_type: "ANALOG_INPUT", ... },
    "chw_return_temp": { object_type: "ANALOG_INPUT", ... },
    "compressor_output_pct": { object_type: "ANALOG_OUTPUT", ... },
    "chiller_power_kw": { object_type: "ANALOG_INPUT", ... },
    "chiller_status": { object_type: "MULTI_STATE_INPUT", ... }
  }
}
```

---

### HVAC Equipment Class: AHU (S00X-AHU-L1-001)

**Required BACnet Objects:**

```
Monitoring Points:
├─ supply_air_temperature (SAT)
│  Object Type: ANALOG_INPUT
│  Units: °C
│  Range: 12-35°C
│  FLC Indicator: Smooth approach to setpoint = FLC
│
├─ return_air_temperature (RAT)
│  Object Type: ANALOG_INPUT
│  Units: °C
│  Range: 16-28°C (typical office)
│
├─ mixed_air_temperature (MAT)
│  Object Type: ANALOG_INPUT
│  Units: °C
│  Purpose: Detect OA damper position from temperature delta
│
├─ supply_air_humidity
│  Object Type: ANALOG_INPUT
│  Units: % RH (relative humidity)
│  Range: 20-80%
│  Purpose: Dehumidification assessment
│
├─ outdoor_air_temperature
│  Object Type: ANALOG_INPUT
│  Units: °C
│  Purpose: Weather correlation for predictive control
│
├─ supply_fan_speed_percent
│  Object Type: ANALOG_INPUT
│  Units: % (0-100%)
│  Purpose: Energy consumption analysis
│
└─ supply_fan_pressure_differential
   Object Type: ANALOG_INPUT
   Units: Pa (pascals)
   Purpose: Filter fouling detection (pressure rise over time)

Control Points:
├─ sat_setpoint_command
│  Object Type: ANALOG_OUTPUT
│  Units: °C
│  Range: 12-35°C (commissioning dependent)
│
├─ supply_fan_speed_command
│  Object Type: ANALOG_OUTPUT
│  Units: %
│  Purpose: Demand-controlled ventilation (DCV)
│
├─ outside_air_damper_percent
│  Object Type: ANALOG_OUTPUT
│  Units: % (0-100%)
│  Purpose: Economizer control, fresh air management
│
└─ heating_mode
   Object Type: MULTI_STATE_OUTPUT
   States: 1=Off, 2=Cool, 3=Heating, 4=Auto
```

---

### HVAC Equipment Class: FCU / VAV (S00X-FCU-L2-A)

**Required BACnet Objects:**

```
Zone Monitoring:
├─ zone_space_temperature
│  Object Type: ANALOG_INPUT
│  Units: °C
│  Purpose: Occupant comfort assessment
│
├─ zone_setpoint_cool
│  Object Type: ANALOG_OUTPUT
│  Units: °C
│  Range: 22-28°C
│
├─ zone_setpoint_heat
│  Object Type: ANALOG_OUTPUT
│  Units: °C
│  Range: 16-22°C
│
├─ zone_occupancy_status
│  Object Type: BINARY_INPUT
│  States: 0=Vacant, 1=Occupied
│  Purpose: Operational cost allocation
│
├─ damper_position_feedback
│  Object Type: ANALOG_INPUT
│  Units: % (0-100%)
│  Purpose: Control quality verification
│
└─ reheat_valve_position
   Object Type: ANALOG_INPUT or ANALOG_OUTPUT
   Units: %
   Purpose: Heating mode operation

Control Points:
├─ damper_position_command
│  Object Type: ANALOG_OUTPUT
│  Units: %
│  Purpose: VAV damper control
│
└─ reheat_valve_command
   Object Type: ANALOG_OUTPUT
   Units: %
   Purpose: Zone heating control
```

---

## Fuzzy Logic Controller (FLC) Detection via BACnet

### FLC Signature Points

When analyzing BACnet trend data, look for these object patterns:

```
Signature 1: Control Output Variance
├─ For PID Controller:
│  Variance(supply_temp) = HIGH (oscillating)
│  d²T/dt² = HIGH (sharp changes)
│  Setpoint overshoot = >1.5°C regular
│
└─ For FLC Controller:
   Variance(supply_temp) = LOW (smooth)
   d²T/dt² = LOW (gradual)
   Setpoint overshoot = <0.5°C rare

Signature 2: Damper/Valve Movement Pattern
├─ PID:
│  valve_position changes = DISCRETE STEPS
│  movement frequency = 2-10 minute cycles
│  acceleration = SHARP
│
└─ FLC:
   valve_position changes = CONTINUOUS CURVE
   movement frequency = VARIABLE (adaptive)
   acceleration = SMOOTH

Signature 3: Response to Load Change
├─ Load step input (e.g., door opening):
│  PID: Fast overshoot (±2°C), then oscillates, 5-min settle time
│
└─ FLC: Gradual correction (±0.2°C), 2-min settle time
```

### Clawd Bot Analysis Algorithm
```python
# Pseudocode for Clawd Bot FLC detection

def detect_controller_type(trend_data):
    """
    Analyze 48+ hours of trend data to infer control algorithm.
    
    Returns: "PID", "FLC", or "Unknown"
    """
    
    # Calculate variance of setpoint error over time
    error = setpoint - actual_value
    variance = std_dev(error)
    
    # Count number of setpoint overshoots >1°C
    overshoots_large = count(error > 1.0)
    
    # Measure average correction response time
    response_times = []
    for load_change in detected_step_changes():
        correction_time = time_to_settle_within_0_5C()
        response_times.append(correction_time)
    
    avg_response = mean(response_times)
    
    # Score for FLC likelihood
    flc_score = 0
    
    if variance < 0.3:        # Low variance
        flc_score += 40
    
    if overshoots_large < 2:  # Few large overshoots
        flc_score += 30
    
    if avg_response < 180:    # Fast response (3 min)
        flc_score += 30
    
    # Decision
    if flc_score > 80:
        return "FLC"
    elif flc_score > 40:
        return "Likely FLC (recommendation: confirm with technician)"
    else:
        return "PID (candidate for FLC upgrade)"
```

---

## BACnet Property Mapping

### Standard Properties

Every BACnet object should expose these properties:

```
Object Identifier:    Unique reference (e.g., analogInput:1)
Object Name:          Human-readable (e.g., "chw_supply_temp")
Present Value:        Current reading or command
Units:                Engineering units (°C, %, kW)
Description:          Technical purpose
Status Flags:         Bit field (in_alarm, fault, out_of_service, overridden)
Priority Array:       0-16 levels for control precedence
```

### SENTINEL Required Properties

For Clawd Bot to generate accurate recommendations:

```
sensor_accuracy:      ±0.5°C (for temperature points)
update_frequency:     Event-driven (COV) or max 30 seconds
calibration_date:     Last calibration (ISO 8601)
maintenance_due:      Predicted maintenance interval
expected_range:       Min/max normal operating values
alarm_threshold:      High/low limits for alerts
```

---

## Modbus Equivalent Mapping (For Gateway Devices)

When a device uses Modbus instead of BACnet, SENTINEL uses this register mapping:

```
BACnet ANALOG_INPUT (sensor)
  → Modbus INPUT_REGISTER (3xxxx)
  Example: chw_supply_temp = Register 30001

BACnet ANALOG_OUTPUT (control)
  → Modbus HOLDING_REGISTER (4xxxx)
  Example: chw_setpoint = Register 40101

BACnet BINARY_INPUT (status)
  → Modbus DISCRETE_INPUT (1xxxx)
  Example: pump_running = Bit 10001

BACnet BINARY_OUTPUT (control)
  → Modbus COIL (0xxxx)
  Example: chiller_enable = Bit 00101
```

---

## Data Point Naming Convention

### Standard SENTINEL Point Names

```
Temperature Points:
  {equipment}_{location}_temp_sp      = Setpoint
  {equipment}_{location}_temp_actual  = Current value
  Examples: chw_supply_temp_sp, sat_actual, zone_temp_actual

Percentage Points:
  {equipment}_{location}_percent      = 0-100% value
  Examples: damper_percent, valve_percent, fan_speed_percent

Pressure Points:
  {equipment}_{location}_pressure     = kPa or bar
  Examples: compressor_outlet_pressure, filter_pressure_delta

Power Points:
  {equipment}_power_kw                = kilowatts
  Examples: chiller_power_kw, ahu_fan_power_kw

Status Points:
  {equipment}_status                  = Text state
  {equipment}_mode                    = Operating mode
  Examples: chiller_status, ahu_mode

Alarm Points:
  alarm_{equipment}_{type}            = Yes/No
  Examples: alarm_chiller_high_pressure, alarm_ahu_filter_clogged
```

---

## Discovery Workflow in SENTINEL

```
BACnet Discovery Flow:
┌──────────────────────────────────────────┐
│ SIMBIOT Network Scan                     │
│ (Identifies all BACnet devices)          │
└──────────────┬───────────────────────────┘
               │
        ┌──────▼──────┐
        │ Per Device: │
        │ ReadDeviceObject
        └──────┬──────┘
               │
        ┌──────▼─────────────────────────┐
        │ GetPropertyValues for each:     │
        │ - OBJECT_IDENTIFIER             │
        │ - OBJECT_NAME                   │
        │ - OBJECT_TYPE                   │
        │ - PRESENT_VALUE (current)       │
        │ - UNITS                         │
        │ - PROPERTY_LIST                 │
        └──────┬─────────────────────────┘
               │
        ┌──────▼──────────────────────────┐
        │ AI Classification               │
        │ Match against SENTINEL taxonomy │
        │ (chiller, ahu, fcu, etc.)       │
        └──────┬──────────────────────────┘
               │
        ┌──────▼─────────────────────────┐
        │ Store in SENTINEL database:     │
        │ {equipment_id, type,            │
        │  points: [{name, type, units}]} │
        └──────────────────────────────────┘

Result: Equipment points ready for Clawd Bot analysis
```

---

## Common Integration Issues & Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| "Object not found" on COV subscribe | Device doesn't support COV | Fall back to 30-second polling |
| Missing units in ANALOG_INPUT | Misconfigured BACnet device | Add unit mapping in SENTINEL config |
| Setpoint writes rejected | Safety interlocks active | Route through SENTINEL safety engine |
| Very slow polling (>5 min/cycle) | Network congestion or gateway bottleneck | Reduce number of subscribed points or increase APDU size |
| Sudden data gaps (points disappear) | Device communication timeout | Implement watchdog timer + alert |

---

## References

- BACnet Standards: ASHRAE 135-2020 (https://www.ashrae.org/)
- SENTINEL Device Abstraction: `/docs/02-architecture/device-abstraction-layer.md`
- Manufacturer Integration Guides: `/docs/07-integrations/manufacturer-integration-guides.md`
- Protocol Gateways: `/docs/07-integrations/protocol-gateways.md`
