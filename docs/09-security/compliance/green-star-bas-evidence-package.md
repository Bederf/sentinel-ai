---
title: "Green Star BAS Evidence Package"
type: "evidence-package"
status: "draft"
version: "0.1.0"
created: "2026-05-19"
updated: "2026-05-19"
author: "SENTINEL Compliance Team"
tags: ["green-star", "edge", "gbcsa", "bas", "hvac", "energy", "esg", "certification", "commissioning"]
domain: "compliance"
audience: "compliance, energy, facilities, engineering, property"
complexity: "high"
estimated_read_time: 25
---

# Green Star Certification — BAS Evidence Package

## 1. Purpose

This document provides the Building Automation System (BAS) integration evidence required for Green Building Council of South Africa (GBCSA) Green Star certification submissions for site-002 (Sandton City Office Tower).

It documents: BAS architecture, control sequences, as-built HVAC performance data, commissioning evidence, and indoor environment quality trending.

**Reference:** GBCSA Green Star v2 Technical Manual; EDGE Certification standards.
**Owner:** AI Engineering Lead / Facilities Manager.
**Review period:** Annually; update after any BAS configuration change.

---

## 2. BAS Architecture Summary

### 2.1 SENTINEL BMS Integration

SENTINEL serves as the intelligence layer above the physical BMS (Siemens Desigo). It does not replace the BMS but augments it with AI optimization, monitoring, and approval workflows.

```
Siemens Desigo (Primary BMS — physical control)
    │
    │ BACnet/IP, BACnet MSTP, DALI-2, Niagara NAE
    ▼
SIMBIOT Universal Adapter (protocol translation layer — SBC on-site)
    │
    │ MQTT over WireGuard VPN
    ▼
SENTINEL BMS Intelligence (cloud intelligence — backend :9095)
    │
    ├── Tier 1: Advisory recommendations (no execution)
    ├── Tier 2: Operator-approved actions (email/Telegram approval)
    └── Tier 3: Auto-execute within safety boundaries (ML-gated, rollback capable)
    │
    ▼
Supabase (state, decisions, audit log)
Prometheus + Grafana (metrics, alerting)
```

### 2.2 Controlled Equipment Inventory

| Equipment | ID Code | Protocol | Controlled By | SENTINEL Control Level |
|-----------|---------|----------|---------------|----------------------|
| Chiller 1 | S002-CHILLER-B1-001 | BACnet | Desigo CC | Tier 2 (approval required) |
| Chiller 2 | S002-CHILLER-B1-002 | BACnet | Desigo CC | Tier 2 (approval required) |
| Cooling Tower | S002-CT-R-001 | BACnet | Desigo CC | Tier 2 (approval required) |
| AHU 001 (Floors 1-5) | S002-AHU-001 | BACnet | Desigo PXC | Tier 2 (approval required) |
| AHU 002 (Floors 6-10) | S002-AHU-002 | BACnet | Desigo PXC | Tier 2 (approval required) |
| AHU 003 (Floors 11-15) | S002-AHU-003 | BACnet | Desigo PXC | Tier 2 (approval required) |
| FCU Zone 1-8 | S002-FCU-01 to S002-FCU-08 | DALI-2 | Desigo TXM | Tier 3 (auto-execute) |
| Water Meter | S002-WATER-MTR-001 | Modbus | SIMBIOT | Monitoring only |
| BESS | S002-BESS-001 | REST API | Weather API | Tier 2 (charge/discharge) |
| Solar Inverter | S002-SOLAR-001 | REST API | Weather API | Monitoring only |
| CCURE Server | S002-CCURE-SVR | BACnet | CCURE | Monitoring only |
| Emergency Lighting | IEC 62034 | Relay | Desigo TXM | Monitoring only |

---

## 3. Control Sequences — As-Built Documentation

### 3.1 Chiller Plant Control Sequence

**Equipment:** S002-CHILLER-B1-001, S002-CHILLER-B1-002
**Control basis:** Return water temperature (CHW RT) + kW/ton efficiency optimization

```
Setpoint: CHW return temperature = 12°C (±0.5°C tolerance)
Setpoint: CHW flow = variable (VSD on primary pumps)
Setpoint: Chiller efficiency target = <0.65 kW/ton (Stage 1)
          or <0.60 kW/ton (Stage 2 optimization)

Sequence:
1. If CHW RT > 12°C + 0.5°C AND chiller kW/ton > 0.65 → Tier 2 recommendation
   Action: Increase setpoint differential (reduce load) OR add second chiller
2. If CHW RT > 13°C → Safety interlock: max 2 chillers online
3. If any chiller alarm active → Tier 2 alert; operator approval before reset
4. Daily optimization: AI evaluates efficiency curves; proposes schedule adjustment
5. BESS discharge during peak (16:00-20:00) to reduce grid import
6. Solar export when BESS full and solar generation > local demand
```

**Safety interlocks:**
- No chiller start if outdoor air temp < 5°C (cold weather protection)
- No more than 2 chillers running simultaneously (electrical protection)
- CHW RT never below 5°C (freezing protection)

**SENTINEL shadow mode validation:** All setpoint changes are simulated in shadow mode for 48h before operator approval.

### 3.2 AHU Control Sequence

**Equipment:** S002-AHU-001, S002-AHU-002, S002-AHU-003
**Control basis:** Zone CO₂ + temperature + occupancy schedule

```
Setpoint: Zone temperature = 22°C (heating) / 24°C (cooling)
Setpoint: Zone CO₂ < 1000 ppm (outdoor air boost trigger)
Setpoint: Occupied hours: 07:00-18:00 (Mon-Fri), 08:00-13:00 (Sat)

Sequence:
1. Occupancy schedule: AHU starts 30min before occupied period (pre-cooling)
2. Zone CO₂ > 1000 ppm → outdoor air damper opens to max (SANS 10400-X)
3. Zone temperature > 24°C → cooling valve opens; fan speeds up (VSD)
4. Zone temperature < 22°C → heating valve opens
5. Zone unoccupied + temperature within 20-26°C → economy mode (reduced outdoor air)
6. Tier 2 recommendation: change occupancy schedule ±30min (validated in shadow mode)
```

**SANS 10400-X compliance note:** Outdoor air rates are monitored to ensure minimum ventilation rates. CO₂ used as proxy for occupancy-driven ventilation requirement. The 1000 ppm trigger is above the 800 ppm advisory level and ensures adequate fresh air per SANS 10400-X Table X3.

### 3.3 FCU Zone Control Sequence

**Equipment:** S002-FCU-01 through S002-FCU-08
**Control basis:** Zone temperature + occupancy (Tier 3 auto-execute)

```
Setpoint: Zone temperature = 22-24°C (occupied), 26°C (unoccupied)
Setpoint: Fan speed = Auto (proportional to heating/cooling demand)

Sequence:
1. Zone temperature > 24°C → FCU fan speed increases (cooling mode)
2. Zone temperature < 22°C → FCU fan speed increases (heating mode)
3. Zone temperature 22-24°C → FCU in standby (Tier 3 auto-execute)
4. Occupancy override: FCU activates 15min before scheduled occupancy
5. Tier 3 auto-execute: setpoint adjustment within ±2°C of baseline (no approval needed)
   Safety boundary: never set below 20°C or above 28°C
6. Rollback: if post-execute efficiency drops >10%, Tier 3 action is rolled back
```

### 3.4 BESS Control Sequence

**Equipment:** S002-BESS-001
**Control basis:** Solar generation surplus + peak tariff avoidance

```
Setpoint: BESS charge when solar generation > local HVAC demand
Setpoint: BESS discharge from 16:00-20:00 (peak hours) OR grid emergency
Setpoint: Min state of charge = 20% (depth of discharge limit)

Sequence:
1. Solar yield > HVAC demand + 5kW surplus → BESS charge initiated
2. BESS full + solar surplus > 2kW → solar export to grid (Tier 2 alert)
3. Peak hours (16:00-20:00, weekdays): BESS discharges to reduce grid import
4. Grid emergency (frequency < 49Hz): BESS emergency discharge (automatic)
5. BESS round-trip efficiency target: >85% (alert if below 80%)
```

---

## 4. HVAC Commissioning Evidence

### 4.1 Control System Commissioning Records

| System | Commissioning Date | Commissioned By | Evidence |
|--------|------------------|-----------------|----------|
| Desigo CC configuration | 2024-11-15 | Siemens SA | BAS config export in vault |
| DALI-2 FCU integration | 2024-11-20 | Siemens SA | DALI commissioning report |
| SIMBIOT adapter installation | 2025-01-10 | SENTINEL Engineering | Site visit log |
| SENTINEL Tier 2/3 integration | 2025-02-01 | SENTINEL Engineering | Shadow mode validation report |
| BESS + Solar integration | 2025-04-10 | Solar installer | CoC + commissioning doc |
| Emergency lighting IEC 62034 | 2025-04-15 | SENTINEL Engineering | IEC test report |

**Commissioning evidence location:** `/home/bederf/sentinel-vault/site-002/commissioning/`

### 4.2 As-Built Setpoint Register

| Equipment | Parameter | Design Setpoint | As-Built Setpoint | Validation Date |
|-----------|-----------|-----------------|-----------------|-----------------|
| Chiller 1 | CHW return temp | 12°C | 12°C | 2025-02-01 |
| Chiller 1 | Min leaving temp | 6°C | 6°C | 2025-02-01 |
| Chiller 2 | CHW return temp | 12°C | 12°C | 2025-02-01 |
| AHU 001 | Heating setpoint | 22°C | 22°C | 2025-02-01 |
| AHU 001 | Cooling setpoint | 24°C | 24°C | 2025-02-01 |
| AHU 001 | Min outdoor air | 15% | 15% | 2025-02-01 |
| AHU 002 | Heating setpoint | 22°C | 22°C | 2025-02-01 |
| AHU 002 | Cooling setpoint | 24°C | 24°C | 2025-02-01 |
| AHU 003 | Heating setpoint | 22°C | 22°C | 2025-02-01 |
| AHU 003 | Cooling setpoint | 24°C | 24°C | 2025-02-01 |
| FCU 01-08 | Occupied temp | 22-24°C | 22-24°C | 2025-02-01 |
| FCU 01-08 | Unoccupied temp | 26°C | 26°C | 2025-02-01 |
| BESS | Min SOC | 20% | 20% | 2025-04-10 |
| BESS | Peak discharge start | 16:00 | 16:00 | 2025-04-10 |

---

## 5. Indoor Environment Quality — Data Trend

### 5.1 CO₂ Levels (SANS 10400-X Compliance Proxy)

SENTINEL monitors zone CO₂ as a proxy for occupancy-driven ventilation. Target: <800 ppm (advisory); alert: >1000 ppm.

| Month | Avg Zone CO₂ (ppm) | Max Recorded (ppm) | SANS Alert Trigger (>1000 ppm) |
|-------|-------------------|-------------------|-------------------------------|
| 2026-03 | 620 | 890 | 0 exceedances |
| 2026-04 | 640 | 920 | 0 exceedances |
| 2026-05 (partial) | 605 | 850 | 0 exceedances |

**Evidence:** Query `loki` for `{job="sentinel-decisions", site_id="site-002"}` filtered for `co2_level > 1000` — no events in 90-day window.

### 5.2 Zone Temperature Compliance

| Month | Avg Zone Temp (°C) | Below 18°C (cold) | Above 26°C (hot) |
|-------|-------------------|-------------------|-------------------|
| 2026-03 | 22.8 | 0 hours | 0 hours |
| 2026-04 | 22.5 | 0 hours | 0 hours |
| 2026-05 (partial) | 23.1 | 0 hours | 0 hours |

**Evidence:** Zone temperature logged to Loki via shadow_mode_polling every 15 minutes.

---

## 6. Energy Performance — Historical Data

### 6.1 Site-002 Energy Consumption (2026-04 to 2026-05)

| Month | Total kWh | HVAC kWh | Lighting kWh | Solar kWh | BESS Discharge kWh |
|-------|-----------|----------|-------------|-----------|-------------------|
| 2026-04 | 23,262 | ~13,957 | ~4,652 | 5,420 | 1,840 |
| 2026-05 (partial) | 23,625 | ~14,175 | ~4,725 | 5,880 | 1,920 |

### 6.2 Energy Intensity Metric

| Metric | Value | Target (Green Star) |
|--------|-------|-------------------|
| Energy intensity | ~48 kWh/m²/year (extrapolated) | < 75 kWh/m²/year for 4-star |
| Solar offset | ~25% of consumption | > 20% for Green Star innovation point |
| HVAC as % of total | ~60% | < 65% (target) |
| Lighting energy | ~20% of consumption | < 25% (LED target) |

### 6.3 Green Star Points — Energy Category

| Credit | Requirement | SENTINEL Evidence | Points |
|--------|-------------|-------------------|--------|
| Green Star 4-star minimum | Energy intensity < 75 kWh/m²/yr | On track (~48 kWh/m²) | — |
| Solar/wind renewable | > 20% of consumption from on-site solar | ~25% solar offset | 2 points |
| Outdoor air ventilation monitoring | CO₂ < 1000 ppm at all times | 0 exceedances, 90-day log | 1 point |
| BMS fault detection and optimisation | Automated fault detection + optimisation | SENTINEL Tier 2/3 shadow mode active | 2 points |
| HVAC controls | Occupancy-based setpoint adjustment | FCU occupancy schedule + CO₂ trigger | 1 point |
| **Estimated total** | | | **6 points** |

Green Star certification requires minimum points across multiple categories. Energy category alone typically needs 10+ points for a 4-star rating. The above represents energy-specific contributions only.

---

## 7. EDGE Certification Alignment

For EDGE (Excellence in Design for Greater Efficiencies) certification, the following as-built data is required:

| EDGE Parameter | SENTINEL Data | Status |
|---------------|--------------|--------|
| As-built energy consumption (kWh/m²/yr) | `energy_consumption_history.total_kwh / floor_area` | Available |
| HVAC system type | Variable refrigerant flow / central chilled water | Documented above |
| Lighting power density (W/m²) | `lighting_energy_kwh / hours / floor_area` | Available |
| On-site renewable energy (%) | `solar_yield_kwh / total_consumption_kwh` | Available (~25%) |
| Energy modeling baseline | SANS 961 (SANS 10400-X energy compliance) | Not yet modeled |

**Gap:** EDGE requires a formal energy model comparison (as-designed vs as-built). SENTINEL has as-built data but no formal energy model baseline. If pursuing EDGE, a SANS 961 energy model must be created using DesignBuilder or equivalent.

---

## 8. Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-05-19 | Compliance Team | Initial Green Star BAS evidence package |

### Approval

- **AI Engineering Lead:** ___________________ Date: ___________
- **Facilities Manager:** ___________________ Date: ___________
- **GBCSA Registered Professional:** ___________________ Date: ___________

---

## 9. Related Documents

- [South African Regulatory Compliance Register](south-africa-regulatory-compliance-register.md)
- [Energy Benchmark Calculation](../../04-features/energy-chart-benchmark-calculation.md)
- [Compliance Module](../../04-features/compliance-module.md)
- [SIMBIOT Universal Adapter Architecture](../../05-integrations/simbiot-universal-adapter-pattern.md)
- [Shadow Mode Polling Service](../../services/shadow_mode_polling.py)

---

*This document is a controlled record for Green Star / EDGE certification. Update after any BAS configuration change.*