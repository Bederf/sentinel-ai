---
title: "Manufacturer FLC Integration Guides"
type: "integration-guide"
status: "active"
version: "1.0.0"
created: "2026-02-10"
updated: "2026-02-10"
author: "SENTINEL Development Team"
tags: ["flc", "fuzzy-logic", "integration", "manufacturers", "bms", "hvac"]
domain: "bms"
audience: ["developers", "integrators", "technicians"]
complexity: "intermediate"
estimated_read_time: 45
---

# Manufacturer FLC Integration Guides

Detailed integration specifications for Fuzzy Logic Controller brands commonly deployed in South African commercial buildings.

## Siemens Desigo Fuzzy Logic Controllers

### Product Line
- **S7-200 Smart FLC**: Compact PLCs with built-in FLC module
- **LOGO! 8 with FLC**: Micro automation controller
- **MICROMASTER 440/420 FLC**: Inverter-embedded fuzzy logic
- **KTP mobile panels**: HMI with FLC visualization

### Communication Protocols
| Protocol | Support | Port | Notes |
|----------|---------|------|-------|
| BACnet/IP | Native | 47808 | Full point discovery |
| BACnet MSTP | Native | — | Via serial gateway |
| Modbus TCP | Native | 502 | Legacy support |
| OPC-UA | Optional | 4840 | Premium licensing |
| Profinet | Native | — | Industrial only |

### Key Data Points Available
```
Control Algorithm Detection:
- Output frequency/variance ratio (FLC = low)
- P, I, D term weights (PID: visible, FLC: hidden)
- Membership function count (BACnet object count)
- Fuzzy rule fire rate (can infer from COV speed)

Equipment Parameters:
- Setpoint (chiller: 6-7°C, AHU: 22-26°C)
- Output % (valve/damper position)
- Sensor readings (temperature, pressure, humidity)
- Alarm status and codes
```

### Siemens FLC Detection Heuristic
**Trend Pattern Analysis:**
- Smooth supply/return differential (±0.2°C): FLC likely
- Sharp step changes (>0.5°C/min): PID likely
- Adaptive response to load: FLC characteristic
- Periodic overshoot: PID characteristic

### Integration Checklist
- [ ] BACnet/IP enabled in Siemens controller config
- [ ] SENTINEL IP address whitelisted in controller
- [ ] COV (Change of Value) subscriptions configured
- [ ] Historical data logging enabled for trend analysis
- [ ] Fault/alarm reporting active in BACnet
- [ ] Point naming mapped to SENTINEL taxonomy

### Known Issues
- **S7-200 Smart**: Older firmware (pre-2020) may not support COV. Upgrade to latest FW.
- **LOGO! 8**: Limited BACnet objects. Ensure all control points are exported.
- **Commissioning**: Siemens engineers may restrict point write access. Negotiate read-only initially.

**Support Contact:** Siemens HVAC Technical Support: +27-11-627-2900

---

## Schneider Electric Unity Pro / Square D FLC

### Product Line
- **Unity Pro**: Premium PLC with embedded FLC library
- **Square D PowerLogic**: Energy monitoring with FLC control
- **Modicon M241 / M251**: Compact controllers
- **EcoStruxure Building Operation**: Cloud-based FLC orchestration

### Communication Protocols
| Protocol | Support | Port | Notes |
|----------|---------|------|-------|
| BACnet/IP | Via gateway | — | Modbus first priority |
| Modbus TCP | Native | 502 | Primary protocol |
| Modbus RTU | Native | — | Serial only |
| OPC-UA | Optional | 4840 | Premium feature |
| EtherNet/IP | Native | 2222 | Industrial variant |

### Schneider FLC Characteristics
- **Fuzzy module library**: Available in Unity Pro V12+
- **Rule base tuning**: Via web HMI (hard to extract remotely)
- **Adaptive parameters**: Learning enabled by default
- **Energy optimization mode**: Reduces output variance

### Integration Checklist
- [ ] Modbus TCP gateway configured on Unity Pro
- [ ] SENTINEL client whitelisted in controller security
- [ ] Register mapping documented (FLC output = register 40XXX)
- [ ] Coil polling interval set to <5 second
- [ ] Modbus timeout: 2 seconds (account for network latency)
- [ ] Backup: Historical data export configured

### Data Point Mapping
```
Chiller Control Example (Schneider):
Temperature setpoint:     40101  (Holding Register)
Current temperature:       30001  (Input Register)
Valve output %:            40102  (Holding Register)
System mode (Heat/Cool):   00102  (Coil)
Alarm flags:              00201-00210 (Coils)
```

**Support Contact:** Schneider Electric South Africa: +27-11-317-5000

---

## Honeywell Niagara / Total Connect FLC

### Product Line
- **N-Ware / N-Thinx**: Proprietary FLC in Niagara
- **DCLX**: DDC controller with embedded FLC
- **WLAN FLC**: Wireless fuzzy logic for retrofit
- **Total Connect**: Cloud-native FLC orchestration

### Communication Protocols
| Protocol | Support | Port | Notes |
|----------|---------|------|-------|
| BACnet/IP | Via Niagara | 47808 | Recommended path |
| Modbus TCP | Via gateway | 502 | Alternative |
| Honeywell Proprietary | Native | 5007 | Requires special licensing |
| OPC-UA | Optional | 4840 | Enterprise only |

### Honeywell FLC Specifics
- **Fuzzy algorithm**: Proprietary; not visible in point data
- **Trend detection**: Built into T-stat logic
- **Remote tuning**: Via Total Connect cloud only
- **Migration path**: Cloud → Local not supported; requires hardware replacement

### Integration Path
1. **Preferred**: Connect via Niagara Framework (if already deployed)
2. **Alternative**: Use Modbus gateway to DCLX controller
3. **Cloud option**: Total Connect API (requires premium licensing)

### Data Point Mapping (DCLX)
```
Chiller:
Supply Temp setpoint:    DP 1 (CTL_SETP_CHW)
Current chiller temp:    DP 2 (TEMP_CHW_SUP)
Valve command %:         DP 3 (CMD_CHW_VALVE)
Status:                  DP 10 (STATUS_CHILLER)
```

**Support Contact:** Honeywell South Africa: +27-21-975-3000

---

## Johnson Controls Metasys / FLC

### Product Line
- **VAV Controllers**: FLC for zone damper control
- **Chiller Optimizer**: Setpoint FLC logic
- **Sequence Manager**: Multi-loop FLC
- **Metasys Native**: Proprietary BACnet flavor

### Communication Protocols
| Protocol | Support | Port | Notes |
|----------|---------|------|-------|
| BACnet/IP | Native (extended) | 47808 | Metasys flavor |
| Modbus TCP | Via gateway | 502 | Third-party devices |
| Johnson Proprietary | Native | 2048 | Metasys only |
| OPC-UA | Limited | 4840 | Read-only for most |

### JCI FLC Detection
- **Sequence Manager firmware**: Check version in commissioning data
- **Tuning parameters**: Visible in Metasys Explorer (if access granted)
- **Optimization mode**: "Adaptive Control" or "Fuzzy Gain Schedule"
- **Response time**: FLC typically <2 minute response; PID = 3-5 minutes

### Integration Strategy
- SENTINEL reads from Metasys BACnet (as if JCI is the local controller)
- Do NOT write directly; route through Metasys workflow automation
- FLC tuning requires Metasys expert approval

**Support Contact:** JCI South Africa: +27-10-593-3900

---

## Mitsubishi Electric / Toshiba VRF FLC

### Product Line
- **GHP / GHR / GHE**: VRF heat pump units (distributed FLC)
- **CMS controller**: Centralized fuzzy logic
- **Lossnay Energy Recovery**: Fuzzy damper control
- **SmartFlex**: Cloud integration layer

### Communication Protocols
| Protocol | Support | Port | Notes |
|----------|---------|------|-------|
| BACnet/IP | Via CoolAutomation | 47808 | Gateway required |
| Modbus TCP | Via CoolAutomation | 502 | Recommended |
| Proprietary M-NET | Native | 9010 | Requires gateway |
| OPC-UA | Optional | 4840 | SmartFlex only |

### Mitsubishi FLC Notes
- **Distributed control**: Each outdoor unit has local FLC
- **Setpoint optimization**: FLC adjusts capacity (0-100%)
- **Zone balancing**: Fuzzy logic for multi-zone pressure control
- **Cold start detection**: Prevents compressor short-cycling via FLC

### Integration (No Direct BACnet/Modbus)
**Solution:** CoolAutomation gateway required (see "Protocol Gateways" section)

```
Mitsubishi VRF System
    │
    ├─ Outdoor Unit 1 (FLC embedded)
    ├─ Outdoor Unit 2 (FLC embedded)
    └─ Indoor Units (20-40 zones)
              │
              CoolAutomation Gateway (bridges M-NET → Modbus/BACnet)
              │
              SENTINEL
```

**Support Contact:** Mitsubishi Electric South Africa: +27-11-900-1000

---

## CAREL / Refrigeration Equipment FLC

### Product Line
- **pCO compact**: Chiller/boiler controller with FLC
- **pCOPRO**: Advanced FLC for chillers, heat pumps
- **MDi**: Modular device interface (gateway-ready)
- **WebServer**: Remote monitoring + FLC tuning

### Communication Protocols
| Protocol | Support | Port | Notes |
|----------|---------|------|-------|
| BACnet/IP | Native (optional) | 47808 | Additional licensing |
| Modbus TCP | Native | 502 | Standard on all units |
| OPC-UA | Optional | 4840 | Enterprise licensure |
| Proprietary LAN | Native | 5000 | For local commissioning only |

### CAREL FLC Features
- **Superheat control**: FLC for compressor efficiency
- **Capacity modulation**: Fuzzy logic for part-load optimization
- **Thermal storage**: FLC for load shifting (cold storage mode)
- **Energy savings**: Up to 20% vs traditional PID in part-load

### Integration via Modbus (Recommended)
```
CAREL pCO Controller
    │
    ├─ Coil supply temp (register 30001)
    ├─ Superheat setpoint (register 40101)
    ├─ Capacity output % (register 40102)
    ├─ Alarms (register 40200)
    └─ Status flags (register 40300)
              │
              Modbus TCP (SENTINEL client polls)
```

### Known Commissioning Issues
- **Modbus timeout**: CAREL is slow; set timeout to 3 seconds
- **Register write protection**: Setpoint writes may be locked; use "advanced unlock" in WebServer
- **Firmware updates**: Always backup configuration before update; FLC rules may reset

**Support Contact:** CAREL South Africa: +27-11-804-3611

---

## Data Point Naming Convention for Clawd Bot

When Clawd Bot recommends an FLC or discusses controller tuning, reference these standard point names:

```
Chiller FLC:
  chw_supply_temp_sp     - Chilled water supply setpoint
  chw_supply_temp_actual - Measured supply temperature
  chw_valve_output_pct   - Percentage valve opening (0-100%)
  chw_return_temp        - Return water temperature
  compressor_output_pct  - Compressor capacity (FLC output)

AHU / FCU FLC:
  sat_setpoint           - Supply air temperature setpoint
  sat_actual             - Measured supply air temperature
  damper_position_pct    - Damper opening (0-100%)
  mixed_air_temp         - Temperature after mixing
  reheat_valve_pct       - Reheat valve opening
  ahu_status_mode        - Heating/Cooling mode

Zone VAV:
  space_temp_setpoint    - Zone temperature setpoint
  space_temp_actual      - Measured room temperature
  vav_damper_pct         - Damper opening (0-100%)
  zone_occupancy         - Occupied/Unoccupied

Generic FLC Signal Detection:
  control_output         - 0-100% for any FLC output
  setpoint               - Target value (any equipment)
  sensor_value           - Current measurement
  error_signal           - Setpoint - Actual (trend this for FLC vs PID)
  control_mode           - Auto/Manual/Override
```

---

## Integration Flowchart for Clawd Bot

```
Client equipment identified
    │
    ├─ Is it Tridium Niagara? → Yes: Use Niagara Integration Guide
    │
    ├─ Is it BACnet/Modbus native? → Yes: Direct connection + FLC trend analysis
    │
    ├─ Is it Mitsubishi/Daikin/LG VRF? → Yes: Recommend CoolAutomation gateway
    │
    ├─ Is it proprietary protocol? → Yes: Recommend IntesisBox gateway
    │
    └─ Unknown / Unsupported → Request equipment model + serial number
                              → Search Fault Code Database
                              → Recommend CoolAutomation (universal gateway)
```

---

## Next Steps for SENTINEL Integration

1. **Discovery Phase** (SIMBIOT scan): Detect what controller types exist
2. **Protocol Assessment**: Identify native BACnet/Modbus vs gateway-dependent
3. **FLC Detection**: Analyze trend data for control algorithm type
4. **Recommendation**: Suggest integration path + any gateway requirements
5. **Implementation**: Deploy gateway (if needed) + map points to SENTINEL taxonomy
6. **Validation**: Verify FLC data points are visible in Clawd Bot recommendations

---

## References

- [Device Abstraction Layer](../02-architecture/device-abstraction-layer.md)
- [BACnet Integration Deep Dive](./bacnet-integration.md)
- [Fault Code Database](../04-features/18-fault-code-database.md)
- [Tridium Niagara Integration](./tridium-niagara-integration.md)
