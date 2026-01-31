---
title: "HVAC Systems Guide"
type: "guide"
status: "approved"
version: "1.0.0"
created: "2026-01-31"
updated: "2026-01-31"
author: "SENTINEL Development Team"
tags: ["hvac", "chiller", "ahu", "fcu", "vav", "technician", "operator"]
domain: "hvac"
audience: "operators"
complexity: "intermediate"
estimated_read_time: 20
---

# HVAC Systems Guide

Technical reference for HVAC equipment in SENTINEL-managed buildings. Written for technicians and operators.

## System Overview

SENTINEL manages **Central Chilled Water systems with VAV Reheat** - the most common commercial HVAC configuration in South African office buildings.

### Why This System Type?

| Factor | Reason |
|--------|--------|
| **Climate** | SA has mild winters - reheat sufficient, no boiler needed |
| **Efficiency** | Central chiller more efficient than distributed units |
| **Control** | VAV provides precise zone-by-zone airflow control |
| **Cost** | Lower operating cost than VRF for large buildings |

---

## Sandton Building HVAC Schematic

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        SANDTON HVAC SYSTEM                               │
│                    Central Chilled Water + VAV Reheat                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│    PLANT ROOM (Basement)                                                │
│    ════════════════════                                                 │
│                                                                          │
│    ┌────────────────────────┐      ┌─────────────────────┐             │
│    │   CHILLER (220 kW)     │      │   COOLING TOWER     │             │
│    │   011-stc-chiller-001  │◄────►│   (Heat Rejection)  │             │
│    │                        │      └─────────────────────┘             │
│    │   • chw_supply: 6°C    │                                          │
│    │   • chw_return: 12°C   │                                          │
│    │   • COP: 5.2           │                                          │
│    └───────────┬────────────┘                                          │
│                │                                                         │
│                │ Chilled Water Pipework (CHW)                           │
│                │ Supply: 6-7°C  Return: 11-13°C                         │
│                │                                                         │
│    ════════════╪════════════════════════════════════════════════════   │
│                │                                                         │
│    LEVEL 12    │    AHU-L12-01 (50 kW)                                  │
│    ═════════   │    ┌─────────────────────────────────────────┐        │
│                │    │  Outside    ┌──────┐   ┌──────┐  Supply │        │
│                └───►│  Air ──────►│Filter│──►│ Coil │──► Fan ─┼──►     │
│                     │  Damper     └──────┘   └──────┘         │        │
│                     │  (OA%)                  (CHW)           │        │
│                     └─────────────────────────────────────────┘        │
│                                        │                                │
│                     ┌──────────────────┼──────────────────┐            │
│                     │                  │                  │            │
│                     ▼                  ▼                  ▼            │
│              ┌────────────┐     ┌────────────┐                         │
│              │ VAV-L12-03A│     │ VAV-L12-04A│     Zone North/South   │
│              │ ┌────────┐ │     │ ┌────────┐ │                         │
│              │ │ Damper │ │     │ │ Damper │ │     Damper: 0-100%     │
│              │ │  75%   │ │     │ │  60%   │ │     Controls airflow   │
│              │ └────────┘ │     │ └────────┘ │                         │
│              │ ┌────────┐ │     │ ┌────────┐ │                         │
│              │ │ Reheat │ │     │ │ Reheat │ │     Reheat: 0-100%     │
│              │ │  0%    │ │     │ │  15%   │ │     For heating mode   │
│              │ └────────┘ │     │ └────────┘ │                         │
│              └─────┬──────┘     └─────┬──────┘                         │
│                    │                  │                                 │
│                    ▼                  ▼                                 │
│              ┌────────────┐     ┌────────────┐                         │
│              │ FCU-L12-03 │     │ FCU-L12-04 │     Fan Coil Units     │
│              │            │     │            │                         │
│              │ Temp: 22.5°│     │ Temp: 23°C │     Local temp control │
│              │ Set:  22°C │     │ Set:  22°C │                         │
│              │ Fan:  Auto │     │ Fan:  Med  │                         │
│              │ Valve: 45% │     │ Valve: 60% │     CHW valve position │
│              └─────┬──────┘     └─────┬──────┘                         │
│                    │                  │                                 │
│                    ▼                  ▼                                 │
│              ┌──────────────────────────────────────┐                  │
│              │           DIFFUSERS (Passive)        │                  │
│              │   ○  ○  ○  ○  ○  ○  ○  ○  ○  ○     │                  │
│              │   DIFF-N-1  DIFF-N-2  ...           │                  │
│              │   (Supply air outlets to space)      │                  │
│              └──────────────────────────────────────┘                  │
│                                                                          │
│    ════════════════════════════════════════════════════════════════    │
│                                                                          │
│    LEVEL 11    (Same pattern: AHU-L11 → VAV-L11-01A/02A → FCU-L11)     │
│    ═════════                                                            │
│              │                                                          │
│              └──► AHU-L11-01 ──► VAV-L11-01A ──► FCU-L11-01 ──► Zones  │
│                              └──► VAV-L11-02A ──► FCU-L11-02           │
│                                   (FAULT)         (FAULT)              │
│                                                                          │
│    ════════════════════════════════════════════════════════════════    │
│                                                                          │
│    LEVEL 10    (Same pattern: AHU-L10 → VAV-L10-01A → FCU-L10)         │
│    ═════════                                                            │
│              │                                                          │
│              └──► AHU-L10-01 ──► VAV-L10-01A ──► FCU-L10-01 ──► Zones  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Equipment Reference

### 1. Chiller

**Purpose:** Produces chilled water for the entire building.

| Point | Description | Typical Value | Alarm |
|-------|-------------|---------------|-------|
| `chw_supply_temp` | Water leaving chiller | 6-7°C | >8°C |
| `chw_return_temp` | Water returning to chiller | 11-13°C | >15°C |
| `compressor_status` | Compressor running | ON/OFF | - |
| `chiller_status` | Overall status | Running/Standby/Fault | Fault |
| `power_consumption` | Electrical load | 150-220 kW | - |

**Troubleshooting:**
| Symptom | Likely Cause | Action |
|---------|--------------|--------|
| High CHW supply temp | Low refrigerant, dirty condenser | Check pressures, clean condenser |
| Compressor short cycling | High head pressure | Check cooling tower, condenser fans |
| Chiller won't start | Safety lockout | Check fault codes on controller |

---

### 2. Air Handling Unit (AHU)

**Purpose:** Conditions and distributes primary air to each floor.

```
         Outside Air                              Supply Air
              │                                        │
              ▼                                        ▼
    ┌─────────────────────────────────────────────────────────┐
    │   ┌─────────┐   ┌────────┐   ┌────────┐   ┌────────┐   │
    │   │  OA     │   │        │   │  CHW   │   │ Supply │   │
    │   │ Damper  │──►│ Filter │──►│  Coil  │──►│  Fan   │──►│
    │   │  30%    │   │        │   │  60%   │   │  75%   │   │
    │   └─────────┘   └────────┘   └────────┘   └────────┘   │
    │                                                         │
    │   Return Air ◄──────────────────────────────────────────│
    └─────────────────────────────────────────────────────────┘
```

| Point | Description | Typical Value | Alarm |
|-------|-------------|---------------|-------|
| `supply_air_temp` | Air leaving AHU | 12-14°C | >18°C |
| `supply_air_setpoint` | Target supply temp | 13°C | - |
| `fan_status` | Supply fan running | ON/OFF | OFF during hours |
| `fan_speed` | Fan speed (VSD) | 0-100% | - |
| `chw_valve` | Cooling coil valve | 0-100% | - |
| `outside_air_damper` | Fresh air intake | 0-100% | - |
| `filter_dp` | Filter pressure drop | <250 Pa | >300 Pa (dirty) |

**Troubleshooting:**
| Symptom | Likely Cause | Action |
|---------|--------------|--------|
| High supply air temp | CHW valve stuck, low CHW flow | Check valve actuator, CHW pumps |
| Fan tripped | Overload, VSD fault | Check motor, reset VSD |
| Low airflow | Dirty filters, damper closed | Replace filters, check dampers |

---

### 3. Variable Air Volume (VAV) Box

**Purpose:** Controls airflow to each zone. Includes reheat for heating.

```
    Supply Air from AHU
           │
           ▼
    ┌─────────────────┐
    │  ┌───────────┐  │
    │  │  Damper   │  │  ◄── Modulates airflow (0-100%)
    │  │   75%     │  │
    │  └─────┬─────┘  │
    │        │        │
    │  ┌─────▼─────┐  │
    │  │  Reheat   │  │  ◄── Electric/HW coil for heating
    │  │   Coil    │  │
    │  │   0%      │  │
    │  └─────┬─────┘  │
    └────────┼────────┘
             │
             ▼
        To Zone (FCU/Diffusers)
```

| Point | Description | Typical Value | Alarm |
|-------|-------------|---------------|-------|
| `damper_position` | Airflow control | 0-100% | Stuck |
| `airflow_setpoint` | Target airflow | 200-500 L/s | - |
| `airflow_actual` | Measured airflow | 200-500 L/s | <50% setpoint |
| `reheat_valve` | Heating coil | 0-100% | - |

**Operating Modes:**
| Mode | Damper | Reheat | When |
|------|--------|--------|------|
| Cooling | 60-100% | 0% | Zone too warm |
| Deadband | Min (30%) | 0% | Zone at setpoint |
| Heating | Min (30%) | 20-100% | Zone too cold |

**Troubleshooting:**
| Symptom | Likely Cause | Action |
|---------|--------------|--------|
| Zone too cold | Damper stuck open, reheat failed | Check actuator, check reheat contactor |
| Zone too hot | Damper stuck closed, reheat stuck on | Check actuator, check reheat valve |
| No airflow | Damper closed, AHU off | Check damper, verify AHU running |

---

### 4. Fan Coil Unit (FCU)

**Purpose:** Local zone temperature control using chilled water.

```
    ┌─────────────────────────────────────┐
    │                                     │
    │   Room Air ──► ┌──────┐ ──► Fan ──► │ ──► Conditioned Air
    │                │ Coil │             │
    │                │ (CHW)│             │
    │                └──────┘             │
    │                                     │
    │   Temp Sensor: 22.5°C               │
    │   Setpoint:    22.0°C               │
    │   Fan:         Auto (Medium)        │
    │   Valve:       45%                  │
    │                                     │
    └─────────────────────────────────────┘
```

| Point | Description | Typical Value | Alarm |
|-------|-------------|---------------|-------|
| `room_temp` | Zone temperature | 20-25°C | <16°C or >28°C |
| `room_temp_setpoint` | Target temp | 22°C | - |
| `fan_speed` | Fan speed | Off/Low/Med/High/Auto | - |
| `valve_position` | CHW valve | 0-100% | Stuck |
| `fcu_status` | Unit status | Running/Off/Fault | Fault |

**Troubleshooting:**
| Symptom | Likely Cause | Action |
|---------|--------------|--------|
| No cooling | Valve stuck closed, no CHW | Check valve, verify CHW supply |
| Fan not running | Motor fault, contactor | Check motor, electrical |
| Noisy operation | Dirty fan, bearing wear | Clean fan, check bearings |
| Water leak | Condensate drain blocked | Clear drain pan, check drain line |

---

## Control Sequences

### Cooling Sequence

```
1. Zone temp rises above setpoint + deadband (e.g., 22.5°C > 22°C + 0.5)
2. FCU valve opens to provide local cooling
3. If FCU at 100% and still warm:
   - VAV damper opens to increase airflow
4. If still warm:
   - AHU increases fan speed
   - AHU CHW valve opens further
5. If still warm:
   - Chiller loads up
```

### Heating Sequence

```
1. Zone temp falls below setpoint - deadband (e.g., 21°C < 22°C - 0.5)
2. FCU valve closes (no cooling needed)
3. VAV damper goes to minimum position
4. VAV reheat valve opens (10%, 20%, 30%...)
5. If reheat at 100% and still cold:
   - Generate alarm (heating capacity exceeded)
```

### Morning Warm-Up (Winter)

```
1. 06:00 - Building start sequence
2. AHUs start with 100% return air (no outside air)
3. VAV reheat coils activate
4. FCUs run fans only (no cooling)
5. Once zones reach 20°C, normal sequence resumes
```

---

## Zone-to-Equipment Mapping (Sandton)

| Zone | FCU | VAV | AHU | Status |
|------|-----|-----|-----|--------|
| Zone-L12-N | FCU-L12-03 | VAV-L12-03A | AHU-L12-01 | Running |
| Zone-L12-S | FCU-L12-04 | VAV-L12-04A | AHU-L12-01 | Running |
| Zone-L11-N | FCU-L11-01 | VAV-L11-01A | AHU-L11-01 | Running |
| Zone-L11-S | FCU-L11-02 | VAV-L11-02A | AHU-L11-01 | **FAULT** |
| Zone-L10-N | FCU-L10-01 | VAV-L10-01A | AHU-L10-01 | Running |

---

## Common Alarms

| Alarm | Severity | Likely Cause | First Response |
|-------|----------|--------------|----------------|
| **Chiller Fault** | Critical | Various | Check chiller display for fault code |
| **AHU Fan Trip** | High | Overload, VSD fault | Check motor, reset VSD |
| **High Zone Temp** | Medium | HVAC undersized, fault | Check FCU, VAV, verify cooling |
| **Low Zone Temp** | Medium | Overcooling, reheat fault | Check VAV reheat, FCU valve |
| **Filter DP High** | Low | Dirty filters | Schedule filter replacement |
| **CHW Temp High** | High | Chiller issue | Check chiller operation |

---

## Efficiency Tips

### For Operators

1. **Don't override setpoints** - Let the system optimize
2. **Check filters monthly** - Dirty filters waste energy
3. **Report faults quickly** - Small issues become big problems
4. **Night setback** - Raise setpoints after hours (25-26°C)

### For Technicians

1. **Commission VAV boxes** - Ensure min/max airflow correct
2. **Balance airflow** - Measure and adjust for even distribution
3. **Check reheat** - Verify reheat only activates when needed
4. **Trend data** - Review trends to catch drift early

---

## Related Documentation

- [DALI-HVAC Integration](../07-integrations/dali-hvac-integration.md) - Comfort diagnosis
- [Safety Interlocks](../06-safety-compliance/safety-interlocks-engine.md) - Temperature limits
- [Device Control API](../03-api-reference/rest-api-endpoints.md) - API reference
