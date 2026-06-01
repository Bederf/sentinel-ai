---
title: "ISO 50001 Energy Management System (EnMS) Procedure"
type: "procedure"
status: "draft"
version: "0.1.0"
created: "2026-05-19"
updated: "2026-05-19"
author: "SENTINEL Compliance Team"
tags: ["iso-50001", "enms", "energy-management", "pdsa", "seu", "enpi", "gbcsa", "esg", "sustainability"]
domain: "compliance"
audience: "compliance, energy, facilities, engineering, management"
complexity: "high"
estimated_read_time: 25
---

# ISO 50001 Energy Management System (EnMS) Procedure

## 1. Purpose

This document defines the Energy Management System (EnMS) for site-002 (Sandton City Office Tower) in accordance with ISO 50001:2018. It establishes the energy review process, significant energy uses (SEUs), energy performance indicators (EnPIs), operational control procedures, management review cycle, and continuous improvement (PDCA) framework.

**Reference:** ISO 50001:2018 — Energy management systems — Requirements with guidance for use.
**Prerequisite:** This EnMS becomes mandatory if SENTINEL qualifies as a Large Energy User (LEU >400,000 kWh/month) or pursues Green Star certification. Currently it is voluntary but recommended for ESG reporting.
**Owner:** Energy Lead / Managing Director.
**Review period:** Annually (management review) + continuous monitoring.

---

## 2. Energy Management Boundary

### 2.1 Organizational Boundary

The EnMS covers the following facilities and operations:

| Site | Address | Building Type | Floor Area (m²) | Primary Energy Source |
|------|---------|--------------|-----------------|---------------------|
| site-002 | Sandton, Johannesburg | Commercial office | ~4,850 (estimated) | Eskom grid + solar PV + BESS |

Energy consumption within this boundary includes:
- All HVAC equipment (chillers, AHUs, FCUs, cooling towers)
- All lighting circuits
- BMS server and networking equipment
- Site bridge hardware (SIMBIOT adapter, WireGuard endpoint)
- Water pumping and treatment systems (if applicable)

### 2.2 Exclusions from Boundary

The following are excluded from the EnMS:
- Tenant electrical consumption beyond base building services (sub-metered separately)
- Emergency systems (emergency lighting, fire pumps — life safety critical)
- Security systems (access control, CCTV — not energy-managed)

---

## 3. Energy Review

### 3.1 Annual Energy Review Process

ISO 50001 requires a documented energy review annually. The energy review identifies:
- All energy sources and their consumption
- Significant Energy Uses (SEUs)
- Previous energy performance and patterns

**Schedule:** January of each year (aligned with DoE LEU reporting cycle if applicable)

**Energy review steps:**

1. **Data collection** — extract 12 months of energy data from SENTINEL:
   ```sql
   -- Monthly energy summary
   SELECT date_trunc('month', date) AS month,
          SUM(total_kwh) AS total_kwh,
          SUM(hvac_kwh) AS hvac_kwh,
          SUM(lighting_kwh) AS lighting_kwh,
          SUM(other_kwh) AS other_kwh
   FROM energy_consumption_history
   WHERE site_id = 'site-002'
     AND date >= '2025-01-01' AND date <= '2025-12-31'
   GROUP BY date_trunc('month', date)
   ORDER BY month;
   ```

2. **Baseline establishment** — define energy baseline (EnB) using 12-month rolling average:
   - Baseline year: **2025** (first full year of SENTINEL data)
   - Baseline energy intensity: ~48 kWh/m²/year (provisional)

3. **Performance trend analysis** — compare each month to baseline; identify anomalies:
   - High consumption months: investigate HVAC schedule changes, weather, occupancy
   - Low consumption months: validate solar generation data accuracy

4. **SEU identification** — rank energy-consuming systems by annual consumption:
   - Extract from `shadow_mode_polling.py` equipment aggregates: CHILLER-AGG, AHU aggregates, FCU zones
   - Calculate kWh per SEU per year

5. **Opportunity identification** — document energy savings opportunities ranked by:
   - Estimated kWh savings (per year)
   - Implementation cost
   - Payback period (months)

### 3.2 Significant Energy Uses (SEUs)

SEUs are the top energy-consuming systems that together represent ≥80% of total site consumption.

| SEU | Annual Consumption (kWh) | % of Total | Selection Rationale |
|-----|------------------------|------------|---------------------|
| **Chiller Plant** (2× chillers + pumps) | ~28,000 | ~50% | Largest single system; highest optimization potential |
| **AHUs** (AHU-001, 002, 003) | ~12,000 | ~21% | 3 large AHUs running 12+ hours/day |
| **Lighting Circuits** | ~5,600 | ~10% | LED retrofitted but still 10% of total |
| **BESS auxiliary** (inverter losses) | ~1,200 | ~2% | Fixed overhead; efficiency declining |
| **BMS server + networking** | ~900 | ~2% | ~90W continuous; small but consistent |

**SEU threshold:** Top 3 systems (chiller + AHU + lighting) = 81% of consumption → SEU scope.

### 3.3 Energy Performance Indicators (EnPIs)

Each SEU has a documented EnPI:

| SEU | EnPI | Formula | Measurement Method | Current Value (2025) |
|-----|------|---------|-------------------|---------------------|
| Chiller Plant | kW/ton refrigeration | `chiller_power_kW / chiller_cooling_tons` | BACnet read from Desigo CC | 0.68 kW/ton |
| Chiller Plant | Chiller efficiency (% COP) | `cooling_output_kW / chiller_power_kW` | BACnet read | COP = 5.2 |
| AHUs | kW/m³/s airflow | `AHU_power_kW / supply_airflow_m3s` | Modbus from AHU VSD | ~1.2 kW/m³/s |
| AHUs | Specific fan power (SFP) | `total_fan_kW / total_airflow_m3/s` | Derived from VSD | SFP = 1.8 |
| Lighting | W/m² installed | `total_lighting_watts / floor_area_m2` | As-built lighting schedule | ~8 W/m² |
| Lighting | Energy per workstation | `lighting_kwh / num_workstations` | Estimated 150 workstations | ~37 kWh/workstation/yr |
| BESS | Round-trip efficiency | `discharge_kwh / charge_kwh` | From `solar_bess` table | 87% |
| Site overall | Energy intensity (kWh/m²/yr) | `total_kwh / floor_area` | From `energy_consumption_history` | ~48 kWh/m²/yr |

**EnPI monitoring frequency:** Monthly via Supabase queries (see Section 6). Dashboard in Grafana (`SENTINEL Energy Overview` dashboard).

---

## 4. Operational Control Procedures

### 4.1 HVAC Scheduling

**Purpose:** Ensure HVAC systems operate only when needed, minimizing waste.

**Procedure:**
1. AHU occupancy schedule set in Desigo: 07:00-18:00 (Mon-Fri), 08:00-13:00 (Sat)
2. AHU pre-cooling starts 30 minutes before occupancy (06:30 on weekdays)
3. AHU shutdown at end of occupancy period (18:00 weekdays, 13:00 Saturday)
4. FCU setback during unoccupied periods: zone temperature setpoint 26°C
5. SENTINEL Tier 2 approval required for any schedule change >30 minutes
6. Shadow mode validation for 48 hours before schedule change goes live
7. Exception: if outdoor air temperature >32°C, extend AHU operation by 1 hour (no approval needed — safety override)

**Monitoring:** AHU runtime hours logged to Supabase `equipment_status` table. Alert if runtime exceeds expected by >15% in any week.

### 4.2 Chiller Efficiency Optimization

**Purpose:** Maintain chiller plant at optimal efficiency (<0.65 kW/ton at all times).

**Procedure:**
1. SENTINEL monitors chiller kW/ton in real-time via BACnet
2. If kW/ton > 0.65 for more than 2 hours → Tier 2 recommendation: investigate (clean filters, check condenser, adjust staging)
3. If kW/ton > 0.70 for more than 1 hour → Tier 2 alert + operator push notification: immediate action required
4. Solar pre-conditioning: if solar generation > HVAC demand, pre-cool building to reduce afternoon peak load
5. BESS discharge during peak (16:00-20:00) to reduce grid import and shift chiller load
6. Chiller sequencing: if 2 chillers running and combined load < 40%, recommend shutting down 1 chiller

**Monitoring:** Chiller efficiency (kW/ton) available in Grafana. Alert fires if >0.70 for 1h.

### 4.3 Lighting Control

**Purpose:** Ensure lighting operates only during occupied hours at minimum required level.

**Procedure:**
1. Lighting schedule in Desigo: 07:00-18:00 (Mon-Fri), 08:00-13:00 (Sat)
2. Daylight harvesting: photosensors on AHU-001 (lobby) dim artificial lighting when natural light sufficient
3. Occupancy override: no override without Tier 2 approval (security concern)
4. SENTINEL monitors lighting kWh via `lighting_energy` table. Alert if lighting consumption > expected by 20% for a full day (possible left-on condition)
5. Emergency lighting tested daily (IEC 62034) at 03:00 SAST; excluded from energy reporting

### 4.4 BESS Charge/Discharge Optimization

**Purpose:** Maximize solar self-consumption and minimize grid import during peak tariff hours.

**Procedure:**
1. BESS charge trigger: solar generation > (HVAC demand + 5kW buffer) → begin charging
2. BESS charge stop: SOC = 95% OR solar surplus drops below 2kW
3. BESS discharge trigger: 16:00-20:00 weekdays AND SOC > 25% → discharge to cover peak HVAC load
4. BESS discharge stop: SOC = 20% OR grid tariff hour ends OR grid emergency (frequency < 49Hz)
5. Emergency override: manual Tier 2 approval can force charge or discharge at any time

---

## 5. Management Review

### 5.1 Annual EnMS Management Review

ISO 50001 requires annual management review of EnMS performance. Schedule: **January** each year.

**Management review agenda:**

1. **EnMS performance vs targets** — review EnPI trends vs baseline:
   - Energy intensity: 48 kWh/m²/yr vs target 45 kWh/m²/yr
   - Chiller efficiency: 0.68 kW/ton vs target 0.62 kW/ton
   - Solar self-consumption: 25% vs target 35%

2. **SEU performance review** — each SEU: is EnPI improving or degrading?

3. **Energy savings achieved** — quantify actual savings vs previous year:
   - HVAC schedule optimization: ~1,800 kWh/month
   - BESS peak shaving: ~1,200 kWh/month
   - Chiller efficiency improvement: ~800 kWh/month

4. **Corrective actions from previous review** — were last year's action items completed?

5. **Opportunities for next year** — ranked list of energy efficiency projects

6. **Resource requirements** — budget and personnel for next year's EnMS

7. **EnMS changes** — any changes to scope, baseline, SEUs, or EnPIs?

8. **Legal compliance** — any new SA regulatory obligations (reviewed in South African Regulatory Compliance Register)?

### 5.2 Management Review Participants

| Role | Responsibility |
|------|---------------|
| Managing Director | Chair; approval of budget and targets |
| Energy Lead | Presenter; prepares EnPI report and savings analysis |
| Facilities Manager | Operational control evidence; SEU performance |
| AI Engineering Lead | SENTINEL optimization performance; Tier 2/3 impact |
| Compliance Lead | Regulatory compliance update |

### 5.3 Management Review Output

Outputs from the annual management review:
- Updated Energy Baseline (EnB) if significant change detected
- New or revised EnPI targets for next 12 months
- Energy efficiency project list with budget and owner
- Updated operational control procedures (if any changes)
- Updated EnMS documentation (this document and related)

---

## 6. Monitoring and Measurement

### 6.1 Monthly EnPI Monitoring Queries

Run these Supabase queries monthly and log results to `energy/monthly-enpi-<YYYY-MM>.md`:

```sql
-- Energy intensity (kWh/m²)
SELECT
  ROUND(SUM(total_kwh) / NULLIF(4850, 0), 2) AS energy_intensity_kwh_m2
FROM energy_consumption_history
WHERE site_id = 'site-002'
  AND date >= '2026-01-01' AND date < '2026-02-01';

-- Chiller efficiency (kW/ton) — from shadow_mode_polling equipment
-- Requires: chiller_power_kw FROM equipment_status WHERE equipment_id = 'CHILLER-AGG'
-- and chiller_cooling_tons FROM weather_api service
-- Calculate: chiller_power_kw / chiller_cooling_tons

-- Solar self-consumption rate
SELECT
  ROUND(SUM(discharge_kwh) / NULLIF(SUM(solar_yield_kwh), 0) * 100, 1) AS solar_self_consumption_pct
FROM solar_bess
WHERE site_id = 'site-002'
  AND reading_time >= '2026-01-01' AND reading_time < '2026-02-01';

-- BESS round-trip efficiency
SELECT
  ROUND(SUM(discharge_kwh) / NULLIF(SUM(charge_kwh), 0) * 100, 1) AS bess_rte_pct
FROM solar_bess
WHERE site_id = 'site-002'
  AND reading_time >= '2026-01-01' AND reading_time < '2026-02-01';
```

### 6.2 Grafana Dashboard

SENTINEL maintains a "SENTINEL Energy Overview" Grafana dashboard with the following panels:
- Monthly energy consumption vs baseline (bar chart)
- Energy intensity trend (line chart, kWh/m²/yr)
- Solar generation vs consumption (area chart)
- BESS charge/discharge efficiency (gauge)
- Chiller efficiency kW/ton (gauge with 0.65 threshold)
- HVAC vs lighting vs other breakdown (pie chart)
- Alert log: energy-related Prometheus alerts (table)

**Dashboard location:** Grafana > SENTINEL > Energy Overview (UID: sentinel-energy-overview)

---

## 7. PDCA Improvement Cycle

SENTINEL EnMS follows the Plan-Do-Check-Act cycle:

```
PLAN ───► DO ───► CHECK ───► ACT
  │         │         │         │
  ▼         ▼         ▼         ▼
Define    Implement  Monitor   Correct
targets   EnMS       vs        & improve
+ plans   controls   baseline  + update
                     + targets EnMS
```

### 7.1 Plan (Energy Planning)

- Establish energy baseline (EnB): 2025 = 48 kWh/m²/yr
- Define EnPIs for each SEU (see Section 3.3)
- Set energy efficiency targets: 2026 = 45 kWh/m²/yr (−6%)
- Identify opportunities ranked by savings potential

### 7.2 Do (Implementation)

- Implement operational controls (Section 4)
- SENTINEL Tier 2/3 optimization active
- Staff trained on energy awareness (annually)
- Maintenance scheduled per work order system

### 7.3 Check (Monitoring)

- Monthly EnPI monitoring (Section 6)
- Quarterly management review of EnMS
- Alert on EnPI deviation >10% from target
- Root cause analysis on any month exceeding baseline by 15%

### 7.4 Act (Improvement)

- Corrective actions for EnPI deviations (documented in incident file)
- Update operational control procedures if needed
- Update baseline if significant change (new equipment, retrofit)
- Report energy savings at annual management review

---

## 8. Energy Efficiency Opportunities — Action Register

| Opportunity | SEU Affected | Est. Annual Savings (kWh) | Est. Cost | Payback | Owner | Status |
|-------------|-------------|--------------------------|-----------|---------|-------|--------|
| Extend AHU pre-cooling by 30min (solar offset) | AHUs | 900 | R0 (config only) | immediate | AI Lead | Planned |
| Install VSD on AHU-003 secondary fan | AHUs | 600 | R8,000 | 14 months | Facilities | Investigation |
| Replace FCU 03-04 old fans with EC fans | FCU | 400 | R6,000 | 18 months | Facilities | Investigation |
| Optimize chiller staging (3→2 chillers at low load) | Chiller | 1,200 | R0 (config only) | immediate | AI Lead | Implemented 2025-11 |
| Increase BESS discharge window (15:30-20:00) | BESS | 600 | R0 (config only) | immediate | AI Lead | Implemented 2026-03 |
| **Total pipeline** | | **3,700 kWh/yr** | | | | |

---

## 9. Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-05-19 | Compliance Team | Initial ISO 50001 EnMS procedure |

### Approval

- **Energy Lead:** ___________________ Date: ___________
- **Facilities Manager:** ___________________ Date: ___________
- **Managing Director:** ___________________ Date: ___________
- **External Auditor (if ISO 50001 certified):** ___________________ Date: ___________

---

## 10. Related Documents

- [South African Regulatory Compliance Register](south-africa-regulatory-compliance-register.md)
- [Energy Balance Export Template](energy-balance-export-template.md)
- [Green Star BAS Evidence Package](green-star-bas-evidence-package.md)
- [Compliance Module](../../04-features/compliance-module.md)
- [Shadow Mode Polling Service](../../services/shadow_mode_polling.py)
- [AI Optimizer Service](../../services/ai_optimizer.py)

---

*This document is a controlled record under ISO 50001:2018. Review annually and update after any significant energy-related change.*
