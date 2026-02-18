---
title: "Protocol Gateway Specifications"
type: "integration-guide"
status: "active"
version: "1.0.0"
created: "2026-02-10"
updated: "2026-02-10"
author: "SENTINEL Development Team"
tags: ["gateways", "integration", "protocol-conversion", "bacnet", "modbus", "proprietary"]
domain: "bms"
audience: ["integrators", "technicians", "developers"]
complexity: "advanced"
estimated_read_time: 40
---

# Protocol Gateway Specifications

Complete specifications for protocol conversion gateways used when native BACnet/Modbus integration is not available. Covers Tridium JACE, CoolAutomation CoolMaster, and IntesisBox.

---

## 1. Tridium Niagara JACE (Universal Gateway)

### Product Options
| Model | Processing | Memory | Network | Best For |
|-------|-----------|--------|---------|----------|
| JACE 8000 | Intel i7, multi-core | 8GB RAM | Dual Ethernet | Large sites (100+ devices) |
| JACE 7000 | ARM Cortex, dual-core | 2GB RAM | Single Ethernet | Medium sites (30-50 devices) |
| JACE 6X | ARM Cortex, single-core | 512MB RAM | Single Ethernet | Small sites (<20 devices) |
| JACE GO | Embedded, low-power | 256MB RAM | Single Ethernet | Retrofit / Budget |

### Protocol Support Matrix
| Protocol | Support | Latency | Stability | Notes |
|----------|---------|---------|-----------|-------|
| BACnet IP | Native | <100ms | Excellent | Full device discovery |
| BACnet MSTP | Native | <50ms | Excellent | Serial/RS-485 required |
| Modbus TCP | Native | <100ms | Excellent | Poll-based, no COV |
| Modbus RTU | Native | <200ms | Good | Serial, reliable |
| LonWorks | Native | <150ms | Good | Neuron card required |
| KNX | Native | <100ms | Good | IP or RF variant |
| DALI | Optional module | <500ms | Good | Via DALI controller |
| Proprietary M-NET | Via plugin | <200ms | Fair | Mitsubishi VRF |
| Honeywell XNEt | Via plugin | <150ms | Fair | Legacy support |
| SNMP | Native | <1000ms | Fair | Network devices only |

### Network Architecture
```
JACE Network Configuration:
┌──────────────────────────────────────────────┐
│         Niagara Supervisor (Cloud)           │
│    (Central management + analytics)          │
└────────────────┬─────────────────────────────┘
                 │ HTTPS (secure)
        ┌────────┴────────┐
        │                 │
    ┌───▼────┐        ┌──▼────┐
    │JACE 8000│        │JACE 8000
    │(Bldg A) │        │(Bldg B)
    └────┬────┘        └──┬─────┘
         │                │
    ┌────┴───────┐   ┌────┴────────┐
    │            │   │             │
  BACnet      Modbus BACnet      KNX
  Devices    Devices Devices     Devices
```

### Data Point Import into SENTINEL
1. **Network Scan**: SENTINEL queries JACE via BACnet/IP
2. **Point Discovery**: JACE returns all exported points from sub-devices
3. **Point Classification**: AI classifier maps to SENTINEL equipment taxonomy
4. **Continuous Monitoring**: COV subscriptions for real-time updates

### Commissioning Steps
- **Phase 1 (2-3 days)**: Install JACE, network configuration
- **Phase 2 (2-5 days)**: Commission sub-devices (BACnet, Modbus, etc.)
- **Phase 3 (1-2 days)**: Point mapping and naming conventions
- **Phase 4 (1 day)**: SENTINEL integration testing

### Recommended Settings for SENTINEL Integration
```
JACE BACnet Configuration:
  Device ID: 8000-8999 (avoid conflicts with field devices)
  Supported Services: Device Communication, File Transfer
  Network Number: 0 (for BACnet IP)
  Port: 47808
  Max APDU Size: 1024 bytes (conservative for stability)
  COV Subscribe: Enabled for all analog points
  COV Timeout: 60 seconds
  Poll Interval: 30 seconds (for COV-unsupported devices)

Modbus Configuration (if used):
  Port: 502 (standard Modbus TCP)
  Poll Rate: 2 seconds per device
  Timeout: 3 seconds
  Retry Count: 2
  Register Map: Pre-configured for each sub-protocol
```

### Licensing
- **Base system**: ~$15,000-25,000 per JACE (hardware + OS license)
- **Module licenses**: ~$2,000-5,000 per sub-protocol (LonWorks, DALI, etc.)
- **Supervisor cloud**: $5,000-10,000/year SaaS licensing
- **Total 3-year cost**: ~$30,000-50,000 per site

### Pros
- Supports virtually ALL building protocols
- Best-in-class stability and uptime (99.9%)
- Tridium support available globally
- Can serve multiple platforms simultaneously (BMS, EMS, Security)

### Cons
- High capital cost (not suitable for small sites)
- Requires Niagara training for configuration
- Long commissioning timeline (4-5 weeks typical)
- Overkill for single-protocol sites

---

## 2. CoolAutomation CoolMaster Series

### Product Options
| Model | Processing | Capacity | Protocols | Best For |
|-------|-----------|----------|-----------|----------|
| CoolMaster Pro | Multi-core ARM | 100+ units | BACnet, Modbus, M-NET | Large VRF/chiller sites |
| CoolMaster | Dual-core ARM | 50 units | BACnet, Modbus | Medium sites |
| CoolMaster Lite | Single-core ARM | 20 units | Modbus | Small retrofit sites |
| CoolMaster USB | USB dongle | 5 units | Modbus (serial) | Budget HVAC-only |

### Specialization: HVAC/Refrigeration
**Primary use:** Converting proprietary HVAC manufacturer protocols to standard BACnet/Modbus
- Mitsubishi M-NET → BACnet/Modbus
- Daikin S21 → BACnet/Modbus
- LG NASA → BACnet/Modbus
- Samsung HVAC → BACnet/Modbus
- CAREL pCO → Enhanced Modbus mapping
- Carrier AquaEdge → Modbus

### Architecture Example: Mitsubishi VRF Integration
```
Mitsubishi VRF System
┌────────────────────────────────────────┐
│ Outdoor Units (3x)                     │
│ + 25 Indoor Cassettes/Wall Units       │
│ (Each with embedded fuzzy logic)       │
└────────────┬─────────────────────────┘
             │
        M-NET Cable (proprietary)
             │
        ┌────▼────────────┐
        │ CoolMaster Pro  │
        │ (Gateway)       │
        └────┬──────┬─────┘
             │      │
          BACnet  Modbus
             │      │
          SENTINEL ◄─────┘
```

### Data Points Exposed (Example: Mitsubishi)
```
Per Outdoor Unit (in BACnet):
  ou_cap_set_point      - Capacity setpoint (0-100%)
  ou_actual_capacity    - Measured capacity
  ou_comp_outlet_temp   - Compressor outlet temperature
  ou_high_pressure      - High side refrigerant pressure
  ou_low_pressure       - Low side refrigerant pressure
  ou_alarm_code         - Current fault code
  ou_operating_mode     - Heating/Cooling/Auto

Per Zone (in BACnet):
  zone_setpoint_heat    - Heating setpoint (°C)
  zone_setpoint_cool    - Cooling setpoint (°C)
  zone_actual_temp      - Room temperature
  zone_filter_dirty     - Maintenance flag
  zone_mode             - Heating/Cooling/Off
  zone_fan_speed        - 0-100%
```

### Installation & Commissioning
1. **Physical**: Install CoolMaster on LAN near HVAC controller
2. **Wiring**: Connect to proprietary protocol (M-NET cable, RS-232, etc.)
3. **Configuration**: Upload CoolMaster profile for your equipment (manufacturer/model)
4. **Testing**: Verify data points appear in BACnet/Modbus
5. **SENTINEL Integration**: Scan network, verify point discovery

**Timeline**: 2-5 days (faster than Tridium JACE)

### Recommended Settings for SENTINEL
```
CoolMaster BACnet Configuration:
  Device ID: 8100-8199 (avoid main JACE range)
  Scan Rate: 30 seconds
  COV Subscribe: Yes (enabled by default)
  Historical Logging: 7 days (optional upgrade)

Data Point Mapping (for Clawd Bot):
  Map outdoor unit capacity to SENTINEL "compressor_output_pct"
  Map zone setpoint to SENTINEL "space_temp_setpoint"
  Map zone actual temp to SENTINEL "space_temp_actual"
  Map defrost/alarm flags to SENTINEL "equipment_status"
```

### Pricing
- **Hardware**: $5,000-12,000 per gateway
- **Software license**: One-time, included
- **Manufacturer profile**: Already included (Mitsubishi, Daikin, LG, etc.)
- **Support**: $2,000/year optional SLA

### Pros
- Specialist HVAC/refrigeration focus
- Pre-configured profiles for common manufacturers
- Faster deployment than JACE (2-5 days vs 4-5 weeks)
- Lower cost than Tridium
- Excellent for VRF systems (common in SA)

### Cons
- HVAC-only (cannot bridge non-HVAC protocols)
- Limited to 50-100 devices (smaller than JACE)
- Vendor lock-in (only works with their profiles)
- No cloud management interface

### When to Recommend
- **VRF/Split systems dominate**: Daikin, Mitsubishi, LG
- **Chiller-based systems**: CAREL, Carrier with proprietary controls
- **Timeline pressure**: Need rapid deployment
- **Budget constraints**: Can't justify $30K+ for Tridium JACE

---

## 3. IntesisBox (Protocol-Specific Bridges)

### Product Family
IntesisBox manufactures dozens of specific protocol converters. For SENTINEL context, key ones are:

| Gateway | Converts | To | Best For |
|---------|----------|-----|----------|
| IntesisBox KNX-BA | KNX | BACnet | EU buildings with KNX |
| IntesisBox MOD-LonIp | LonWorks | Modbus/BACnet | Legacy DDC sites |
| IntesisBox GW-HVAC | HVAC Proprietary | BACnet/Modbus | HVAC-only retrofit |
| IntesisBox AC-IF-MODBUS | Daikin VRV | Modbus | Daikin-heavy sites |
| IntesisBox REF-AEI | Carrier AquaEdge | Modbus | Carrier chiller sites |

### Architecture: Single-Protocol Bridge
```
Legacy KNX Lighting System
┌──────────────────────────────────┐
│  KNX Devices (120 points)        │
│  - Lighting scenes                │
│  - Dimmer levels                  │
│  - Occupancy sensors              │
└──────────────┬────────────────────┘
               │
         KNX Serial Cable
               │
        ┌──────▼───────────┐
        │ IntesisBox       │
        │ KNX-BA Bridge    │
        └──────┬───────────┘
               │
            BACnet/IP
               │
            SENTINEL
         (Can now see
        lighting levels
        in optimization)
```

### Supported Conversions (South Africa Focus)
```
Common SA Building Protocols:

1. LonWorks (legacy DDC systems)
   IntesisBox MOD-LonIp: LonWorks → Modbus
   Estimated sites: 15-20% of older commercial buildings

2. KNX (small commercial, retail)
   IntesisBox KNX-BA: KNX → BACnet
   Estimated sites: 10-15% of retail/hospitality

3. Proprietary HVAC
   IntesisBox GW-HVAC: Multiple HVAC protocols → BACnet
   Estimated sites: 5-10% (mainly Daikin, Carrier)

4. DALI Lighting (new builds)
   Tridium JACE DALI module: DALI → BACnet (preferred)
   IntesisBox DALI-Modbus: DALI → Modbus (fallback)
```

### Installation
1. **Mount**: Wall-mounted unit near controller
2. **Network**: Connect to Ethernet (BACnet/Modbus output)
3. **Serial**: Connect to proprietary protocol (KNX, LonWorks, etc.)
4. **Power**: 24VDC or 110-240VAC (varies by model)
5. **Configuration**: Web-based interface, pre-configured for common devices

### Configuration Example: LonWorks Bridge
```
IntesisBox MOD-LonIp Setup:

1. Serial Configuration:
   - Port: /dev/ttyUSB0 (Linux) or COM3 (Windows)
   - Baud: 78.125 kbps (LonWorks standard)
   - Auto-detection: LonWorks node address

2. Modbus Server:
   - Listen on: 0.0.0.0:502 (all interfaces)
   - Unit ID: 1
   - Point mapping: LonWorks variables → Modbus registers
     - Building chilled water temp → Register 30001
     - AHU discharge temp → Register 30002
     - VAV zone temp → Register 30100-30130 (array)

3. SENTINEL Client:
   - Connect to IntesisBox via Modbus TCP
   - Poll interval: 5 seconds
   - Timeout: 2 seconds
```

### Pricing (Per Gateway)
- **Hardware**: $2,000-8,000 depending on protocol
- **Software**: Included (one-time license)
- **Support**: Community forum (free) or SLA ($1,000/year)

### Pros
- Very affordable for single-protocol bridges
- Plug-and-play: minimal configuration
- Compact form factor
- 10+ years manufacturer support history

### Cons
- Limited to pre-defined protocol pairs
- Cannot handle multiple protocols (unlike JACE)
- Smaller capacity (10-50 points typically)
- Less robust than enterprise gateways (uptime: 98-99%)

### When to Recommend
- **Single-protocol retrofit**: KNX lighting, LonWorks DDC
- **Budget extremely constrained**: <$10K total gateway cost
- **Small device count**: <50 points to bridge
- **Zero maintenance expectations**: Install and forget

---

## Gateway Selection Flowchart

```
Equipment protocol known?
    │
    ├─ Yes: BACnet or Modbus native?
    │       └─ Yes: No gateway needed → Direct SENTINEL connection
    │       └─ No: Which proprietary?
    │              ├─ Mitsubishi/Daikin/LG VRF? → CoolMaster
    │              ├─ CAREL chiller? → CoolMaster
    │              ├─ Carrier AquaEdge? → IntesisBox REF-AEI
    │              ├─ LonWorks DDC? → IntesisBox MOD-LonIp
    │              ├─ KNX system? → IntesisBox KNX-BA
    │              └─ Multi-protocol site? → Tridium JACE
    │
    └─ No: Unknown
           ├─ Site >100 devices or multi-protocol? → JACE
           ├─ HVAC-dominant site? → CoolMaster
           └─ Single building with <50 points? → IntesisBox

Budget considerations:
    ├─ <$5K: IntesisBox (single protocol only)
    ├─ $5-15K: CoolMaster (HVAC-specialized)
    └─ >$20K: Tridium JACE (enterprise, multi-protocol)
```

---

## Integration with SENTINEL

### Data Point Import Process
```
1. Gateway deployed on LAN
2. Devices configured and bridge verified
3. Gateway exposes BACnet/Modbus to SENTINEL
4. SIMBIOT discovery scans gateway (as if gateway = controller)
5. SENTINEL imports all points from gateway
6. Clawd Bot analyzes trend data to detect control algorithm type
7. Recommendations generated based on equipment type
```

### Clawd Bot Integration Template
When a client has a proprietary protocol:

```
Clawd Bot Response:
"I detected your [Mitsubishi VRF / CAREL chiller / KNX lighting]
system on the network. These use a proprietary protocol that SENTINEL
doesn't directly support. I recommend a [CoolMaster / IntesisBox]
gateway to bridge the gap.

Expected cost: $[X]-[Y]k
Deployment time: [N] days
Ongoing maintenance: Minimal (gateway is passive)

Would you like me to provide a specific quote, or schedule a
site survey first?"
```

---

## References

- Tridium Niagara Integration: `/docs/07-integrations/tridium-niagara-integration.md`
- Manufacturer Guides: `/docs/07-integrations/manufacturer-integration-guides.md`
- Device Abstraction Layer: `/docs/02-architecture/device-abstraction-layer.md`
