# AEGIS BESS Discovery — Site-002

> **Version:** 1.0 | **Completed:** 2026-02-22
> **Status:** Populated from codebase config + equipment files. Fields marked **[CONFIRM]** need ops/vendor sign-off before AEGIS writes are enabled.
> **Source files:** `site-002_config.json`, `energy_centre.json`, `building.json`, `bess_dispatch_engine.py`, `solar_arbitrage_engine.py`, `solar_generator_coordinator.py`, `compliance_rules.json`, `city_power_2025_26.json`

---

## 1. Site and ownership

| Field | Value |
|-------|-------|
| Site name and site_id | Sandton City Office Tower / `site-002` |
| Physical location | Sandton City Complex, 83 Rivonia Road, Sandton, JHB (-26.13, 27.97) |
| Owner of PV and BESS | **[CONFIRM]** Site-002 Operations (ORG-SITE-002) — contract holder. Confirm asset owner vs lease |
| Warranty provider and expiry date | **[CONFIRM]** Huawei (LUNA2000 + SUN2000). Inverter cert: Intertek CN-PVES-250406, Oct 2025. Battery warranty expiry not on file |
| Who is allowed to approve control changes | **[CONFIRM]** Current config: `control_tier: human_in_loop`. Tier 2 approvals required. James Wilson (Facilities Manager) listed as escalation. Confirm who signs off Tier 3 |

---

## 2. System architecture

| Field | Value |
|-------|-------|
| Inverter brand and model | Huawei SUN2000-100KTL-M2 (4 units, 100 kVA each, 400 kVA total) |
| Battery chemistry and manufacturer | Huawei LUNA2000-200KWH-2H1, LFP (Lithium Iron Phosphate), 2 racks |
| Total capacity kWh | 200 kWh usable |
| Max charge and discharge kW | 100 kW (0.5C rate) |
| PCS type | AC-coupled (Modbus TCP, inverters at 10.1.1.101–104:502) |
| Is there a local controller or EMS | Siemens Desigo CC (BACnet/IP) is the BMS. No dedicated BESS EMS — SENTINEL acts as EMS via Modbus TCP to LUNA2000 |

### PV array

| Field | Value |
|-------|-------|
| Plant ID | `sandton-roof` |
| Total PV capacity | 297 kWp (540 panels x 550W JA Solar JAM72S30-550/MR) |
| Orientation / tilt | 0° North-facing / 15° tilt |
| MPPT configuration | 10 MPPT per inverter, 1 string per MPPT, 14 panels per string |
| Commissioning date | 2025-09-01 |
| Typical peak output | ~288 kW (94% of nameplate at midday) |
| Daily generation | ~1,535 kWh (summer) |

---

## 3. Grid and generator integration

| Field | Value |
|-------|-------|
| Grid tied / island capable / off-grid | Grid-tied with bidirectional metering. ATS present (Socomec ATyS 4000A 4-pole) for generator failover |
| Export allowed | Yes |
| Export limit (kW) | 297 kW max (= PV capacity). BESS export capped at 50 kW (50% Prated, NRS 097 limit in dispatch engine) |
| NRS compliance status | NRS 097-2-1:2024 Edition 3 compliant. SSEG Category B (100 kW to 1 MW). All 4 inverters certified |
| Generator present | Yes — 2x 500 kVA Caterpillar diesel gensets (1,000 kVA total, N+1 redundancy). DeepSea DSE8610 MKII controllers |
| Generator make and ATS logic | Caterpillar + Socomec ATyS ATS. Mechanical interlock, 85 ms transfer time. Last transfer: 2026-01-28 06:15 UTC (mains fail). Transfer count: 892 |
| Priority order | 1. Solar (primary) 2. BESS (secondary) 3. Grid (tertiary) 4. Generator (last resort — only when BESS SOC < 20% AND load shedding active AND solar insufficient) |

### Electrical infrastructure

| Component | Specification |
|-----------|--------------|
| MV incomer | 11 kV, supply point GT-SAN-0042, 630A rated, 250 MVA fault level |
| Transformers | 2x 2,000 kVA (Dyn11, 11 kV/400V). TX-1 Essential 79% loaded, TX-2 Non-Essential 56% loaded |
| Main switchboard | 400V, 4,000A rated, 50 kA fault rating, 2 bus sections coupled |
| NMD (Notified Maximum Demand) | 1,820 kVA |
| Historical peak demand | 1,820 kW (2025-12-15 14:30 UTC) — recorded on main meter |
| Total building load (avg) | 1,450 kW / 1,543 kVA at PF 0.94 |
| PFC bank | 600 kvar total (12 x 50 kvar steps), 8 active = 400 kvar. Target PF 0.95 |

---

## 4. Control interfaces

| Field | Value |
|-------|-------|
| Available APIs | **Modbus TCP** (BESS + PV inverters at 10.1.1.101–104:502), **BACnet/IP** (BMS via Desigo CC), **DALI-2** (lighting via Tridonic Scenecom). REST API via SENTINEL backend |
| Read points (BESS) | SOC (%), pack_voltage (V), pack_current (A), pack_temperature (C), power_kw, mode, alarm_status, rack_1_temp, rack_2_temp, daily_charge_kwh, daily_discharge_kwh, total_cycles |
| Read points (PV) | ac_power_kw, dc_power_kw, efficiency_pct, inverter_temp_c, daily_energy_kwh, total_energy_kwh, mppt_voltages, alarm_status |
| Read points (Grid) | voltage_l1/l2/l3, current_l1/l2/l3, power_kw, power_kva, pf, frequency_hz, thd_v_pct, thd_i_pct, kwh_import, kwh_export, max_demand_kw |
| Write points (BESS) | charge_rate_kw, discharge_rate_kw, mode (peak_shaving/load_shifting/grid_export/backup), enable/disable, soc_target_pct |
| Write points (PV) | active_power_limit_pct, reactive_power_setpoint, enable/disable |
| Write latency | **[CONFIRM]** Modbus TCP typical: <100 ms. Worst case not measured. ATS transfer: 85 ms measured |
| Vendor cloud dependency | **[CONFIRM]** Huawei FusionSolar cloud available but not required. Local Modbus TCP is primary control path. Confirm if cloud has override authority |

---

## 5. Operating rules (current reality)

| Field | Value |
|-------|-------|
| Min SOC allowed | 20% (emergency reserve — `SOC_MIN_PCT` in dispatch engine). Absolute floor: 10% (`BESS_MIN_SOC_PCT` in arbitrage engine, cell protection) |
| Max SOC allowed | 95% (`SOC_MAX_PCT` — prevents overcharge) |
| Reserve SOC for outage | 80% (`SOC_LS_RESERVE_PCT` — pre-charge target before load shedding window) |
| Max depth of discharge | 75% usable (95% - 20% = 150 kWh usable from 200 kWh) |
| Allowed C-rate | 0.5C (100 kW / 200 kWh). Ramp: 10 kW/min normal, 5 kW/min during load shedding |
| Cooling constraints | Charge blocked below 12C or above 40C. Discharge blocked below 12C or above 44C. Throttling begins 5C before charge max (35-40C range, linear reduction). Current pack temp: 28.5C |
| Night charging allowed | Yes — off-peak TOU charging (22:00-06:00 summer, same winter) is the primary arbitrage strategy |
| Weekend behaviour | **[CONFIRM]** No weekend-specific rules in dispatch engine. Same TOU schedule applies. Confirm if building occupancy changes dispatch priority |

### Dispatch decision tree (implemented)

| Priority | Condition | Action |
|----------|-----------|--------|
| 1 | Load shedding active | Discharge to sustain critical loads (unless SOC <= 10%, then IDLE for generator) |
| 2 | SOC critically low (< 12%) | Emergency charge at 100 kW to 20% |
| 3 | Off-peak tariff period | Charge at 100 kW to 95% (cloudy forecast: full rate; sunny: 60% rate to 70% SOC) |
| 4 | Peak tariff period | Discharge at min(100 kW, building_load) unless SOC <= 10% |
| 5 | Standard tariff period | Absorb excess solar if > 50 kW and SOC < 95%, else IDLE |

### Load shedding stage adjustments

| Stages | Action |
|--------|--------|
| 0-3 | Continue normal arbitrage |
| 4-5 | Reduce discharge to 50% of requested |
| 6-8 | Stop discharge, prepare emergency support |

---

## 6. Protection and safety

| Field | Value |
|-------|-------|
| Fire suppression present | **[CONFIRM]** Fire alarm interlock exists in safety engine (disables HVAC on alarm). BESS container fire suppression not confirmed in codebase |
| Thermal runaway detection | LFP chemistry (lower thermal runaway risk than NMC). Per-rack temperature monitoring via Modbus. Charge blocked >40C, discharge blocked >44C |
| Manual isolation location | **[CONFIRM]** Energy centre in Basement Level 2 (S002-EC-B1-001). ATS manual override available. Confirm BESS isolator location |
| Emergency shutdown procedure | **[CONFIRM]** ATS has mechanical + electrical interlocks. Fire alarm interlock triggers HVAC shutdown. Kill switch architecture defined in write-policy doc (global / per-site / per-equipment). Confirm physical E-stop location |
| Authority to override system | **[CONFIRM]** Current: OPERATOR or ADMIN role via SENTINEL. `write_device_point` tool requires `ModuleType.CONTROL` + `SentinelRole.OPERATOR` minimum. Confirm who holds ADMIN role |
| Existing interlocks | Fire alarm -> HVAC disable (block severity). Chiller min runtime 5 min / max 4 starts per hour. Grid frequency > 50.3 Hz -> discharge power reduction. Voltage/frequency NRS 097 disconnect limits. ATS mechanical interlock prevents parallel source |

### NRS 097-2-1 protection limits

| Parameter | Disconnect | Reconnect delay |
|-----------|-----------|-----------------|
| Voltage low | 195.5V | 60 seconds |
| Voltage high | 264.5V | 60 seconds |
| Frequency low | 47.5 Hz | 60 seconds |
| Frequency high | 52.0 Hz | 60 seconds |
| Anti-islanding | IEC 62116, 2.0 second detection | N/A |
| Max THD | 5.0% | N/A |
| Max DC injection | 0.5% | N/A |
| Min power factor | 0.95 | N/A |

---

## 7. Financial and contractual limits

| Field | Value |
|-------|-------|
| Feed-in tariff (SSEG) | 78.5 c/kWh (City Power Johannesburg) |
| Peak tariff periods | Summer (Sep-May): 07:00-10:00, 18:00-20:00. Winter (Jun-Aug): 06:00-09:00, 17:00-19:00 |
| Demand charges | R395.48 /kVA/month (same summer and winter) |
| Warranty cycle limits | **[CONFIRM]** LFP chemistry rated >6,000 cycles at 75% DoD. Huawei LUNA2000 warranty terms not on file. Confirm cycle limit and calendar life |
| Penalty clauses for misuse | **[CONFIRM]** Not on file. Confirm if warranty voids on >95% SOC, <10% SOC, or >0.5C sustained |
| SLA on uptime | **[CONFIRM]** Maintenance contract: Full Maintenance, R285,000/month, 2024-01-01 to 2026-12-31. Confirm BESS availability SLA |

### Full tariff schedule (City Power LPU-TOU 2025/26)

| Period | Summer (c/kWh) | Winter (c/kWh) |
|--------|----------------|----------------|
| Peak | 295.39 | 827.09 |
| Standard | 222.39 | 289.11 |
| Off-Peak | 170.95 | 188.05 |
| Network (flat) | 6.00 | 6.00 |
| Reactive surcharge | 42.43 c/kvarh | 42.43 c/kvarh |
| Service charge | R11,658.08/month | R11,658.08/month |

### Financial opportunity

| Lever | Annual estimate |
|-------|----------------|
| Demand charge shaving (100 kW = ~55 kVA at PF 0.94) | ~R261K (55 kVA x R395.48 x 12) |
| TOU arbitrage (peak vs off-peak spread) | ~R32K (conservative, summer only) |
| Winter arbitrage (827 vs 188 c/kWh spread) | ~R46K (winter months, higher spread) |
| SSEG export income | ~R14K (limited excess solar after self-consumption) |
| Generator diesel avoidance | Up to R2M (from R2.5M to <R500K target) |
| **Total opportunity** | **~R2.35M/year** (diesel avoidance dominates) |

---

## 8. Current operational use

- [ ] Backup only
- [x] Peak shaving
- [x] Load shifting
- [x] Tariff arbitrage
- [ ] PV smoothing
- [x] Generator reduction

**Actual usage vs design intent:**

> Design intent: 4-mode operation (peak shaving, load shifting, grid export, backup). All four modes are licensed in config (`operating_modes` in `site-002_config.json`). Actual usage as implemented: primarily TOU arbitrage (charge off-peak, discharge peak) with load shedding reserve management. Peak shaving is active but limited by 100 kW rated power vs 1,450 kW average building load (~7% shaving capacity). Generator reduction is the primary financial driver — BESS sustains critical load during Eskom load shedding stages 1-5, avoiding diesel genset starts. PV smoothing is not implemented as a distinct mode. Grid export is enabled but secondary to self-consumption.

---

## 9. Incident history

| Field | Value |
|-------|-------|
| Any shutdowns in last 12 months | **[CONFIRM]** ATS has recorded 892 transfers total. Last transfer 2026-01-28 for mains failure. No BESS-specific shutdown records in codebase |
| Any fire or overheating events | **[CONFIRM]** No records in codebase. Pack temperature currently 28.5C (well within limits) |
| Any inverter trips | **[CONFIRM]** All 4 inverters show status: online, health: 93%. No trip records in mock data |
| Any grid compliance violations | **[CONFIRM]** NRS 097 compliant. THD voltage 2.1% (limit 5.0%), THD current 8.5%. No violation records |
| Root causes and fixes | **[CONFIRM]** No incident records available in codebase. Request maintenance log from FM team |

---

## 10. Data quality

| Field | Value |
|-------|-------|
| Telemetry update rate (seconds) | **[CONFIRM]** Modbus TCP polling rate not explicitly configured. BACnet scan interval typically 15-60 seconds. Confirm BESS telemetry interval |
| Missing data frequency | Simulation mode: 0% missing (synthetic). Live: **[CONFIRM]** — quality gate metric `freshness_minutes` tracks this. Pass threshold: < 1440 min (simulation), < 60 min (shadow_live), < 15 min (live_control) |
| SOC accuracy confidence | **[CONFIRM]** Huawei LUNA2000 reports SOC via Modbus. LFP SOC estimation accuracy typically +/-3%. No independent verification configured |
| Time sync issues | **[CONFIRM]** SCADA network on 10.1.50.0/24 VLAN 50. NTP source not documented. Confirm time sync between BESS, inverters, and SENTINEL |
| Manual data corrections used | Yes — simulation mode uses JSON fallback data (`mock_device_state.json`). No manual corrections to live telemetry |

---

## 11. Automation appetite

| Capability | Level |
|------------|-------|
| Charge scheduling | **Approval** — TOU-based charge scheduling during off-peak. Currently Tier 2 (human approval) |
| Discharge for peak shaving | **Approval** — Tier 2 approval required. Config: `control_tier: human_in_loop` |
| Generator coordination | **Advisory** — BESS-first strategy implemented. Generator start only at SOC < 20%. Gen start/stop stays manual |
| Export control | **Approval** — Export enabled but capped at 50 kW (BESS) / 297 kW (PV). Tier 2 approval for changes |
| Emergency islanding | **Never** — ATS is mechanical (Socomec ATyS). AEGIS must not interfere with ATS operation |
| SOC reserve management | **Approval** — Pre-LS charging to 80% is automated in dispatch logic. SOC floor changes require Tier 2 |

**[CONFIRM]** These levels are inferred from `control_tier: human_in_loop` and existing dispatch logic. Confirm with ops team which capabilities can move to Auto (Tier 3) after shadow_live validation period.

---

## 12. Human roles

| Role | Person / Contact |
|------|-----------------|
| Who monitors daily | **[CONFIRM]** FM Team. SENTINEL dashboard provides real-time monitoring. Confirm named individual |
| Who approves Tier 2 | **[CONFIRM]** James Wilson (Facilities Manager, +27721234571). Confirm backup approver |
| Who can force manual mode | **[CONFIRM]** Anyone with OPERATOR or ADMIN role in SENTINEL. Physical: whoever has access to Basement Level 2 energy centre |
| Escalation contact after hours | Emergency: +27 11 350 4000. Technician roster: John Smith (Electrical, +27721234567), David Chen (Controls, +27721234570) |

### Full technician roster

| Name | Specialty | WhatsApp | Status |
|------|-----------|----------|--------|
| John Smith | Electrical | +27721234567 | Active |
| Mike Johnson | HVAC | +27721234568 | Active |
| Sarah Lee | Plumbing | +27721234569 | Active |
| David Chen | Controls | +27721234570 | Active |
| James Wilson | Facilities Mgr | +27721234571 | Active |

---

## 13. Compliance

| Field | Value |
|-------|-------|
| Municipal approval status | **[CONFIRM]** City Power Johannesburg SSEG Category B registration. Confirm approval reference number |
| Grid code compliance | NRS 097-2-1:2024 Edition 3 compliant. Inverter certificates: Intertek CN-PVES-250406 (Oct 2025). Anti-islanding per IEC 62116 |
| Insurance conditions | **[CONFIRM]** Not on file. Confirm if insurer requires specific BESS operating constraints or fire suppression |
| Audit requirements | PARASITE decision audit trail: every dispatch decision logged to `parasite_decisions` with 21-field schema (mode, gate status, enforcement, safety result, COV verification). Monthly SSEG reporting enabled in compliance config |
| Reporting obligations | Monthly export reporting to City Power (enabled). Quality gate evaluations logged. **[CONFIRM]** Confirm municipal reporting frequency and format |

---

## 14. Success criteria

In one year, AEGIS is successful if:

1. Diesel generator runtime reduced by 80% (from ~R2.5M/year to <R500K/year fuel cost)
2. Zero BESS safety incidents (no thermal events, no NRS 097 violations, no unplanned shutdowns)
3. Demand charge reduced by at least R250K/year through peak shaving

**[CONFIRM]** These are derived from config targets. Confirm with client what their actual success metrics are.

---

## 15. Red lines (non-negotiables)

Based on implemented safety boundaries and dispatch constraints:

1. Never discharge below 20% SOC (10% absolute floor for cell protection)
2. Never charge or discharge outside temperature envelope (12-40C charge, 12-44C discharge)
3. Never export more than 50 kW from BESS to grid (NRS 097 distribution limit)
4. Never interfere with ATS mechanical transfer operation
5. Never override NRS 097 voltage/frequency disconnect protection
6. Never bypass the quality gate — if gate returns FAIL in live_control, all writes are blocked
7. Never operate BESS during grid frequency > 50.3 Hz without power reduction
8. Never exceed 10 kW/min ramp rate (5 kW/min during load shedding stages 4+)
9. Never start generator unless BESS SOC < 20% AND load shedding active AND solar insufficient
10. **[CONFIRM]** Never void Huawei warranty — confirm specific warranty terms (cycle limits, DoD limits, operating temperature range)

---

## Appendix: Constraint summary table

| Category | Parameter | Min | Max | Unit | Source |
|----------|-----------|-----|-----|------|--------|
| SOC | Operating | 20% | 95% | % | `bess_dispatch_engine.py` |
| SOC | Absolute floor | 10% | — | % | `solar_arbitrage_engine.py` |
| SOC | LS reserve target | 80% | — | % | `bess_dispatch_engine.py` |
| Temperature | Charge | 12 | 40 | C | `bess_dispatch_engine.py` |
| Temperature | Discharge | 12 | 44 | C | `bess_dispatch_engine.py` |
| Power | Rated | — | 100 | kW | `site-002_config.json` |
| Ramp rate | Normal | — | 10 | %Prated/min | `bess_dispatch_engine.py` |
| Ramp rate | Load shedding | — | 5 | %Prated/min | `bess_dispatch_engine.py` |
| Grid frequency | Normal range | 49.0 | 51.0 | Hz | `compliance_rules.json` |
| Grid frequency | Discharge reduction trigger | — | 50.3 | Hz | `bess_dispatch_engine.py` |
| Export | BESS to grid | — | 50 | kW | `bess_dispatch_engine.py` |
| Export | PV to grid | — | 297 | kW | `site-002_config.json` |
| Capacity | Total | — | 200 | kWh | `site-002_config.json` |
| Efficiency | Round-trip | — | 90 | % | `solar_arbitrage_engine.py` |

---

## [CONFIRM] items checklist

Items that must be verified with ops team / energy vendor before AEGIS can move beyond Advisory mode:

- [ ] Asset ownership (PV + BESS): owner vs lease arrangement
- [ ] Huawei warranty terms: expiry date, cycle limits, DoD limits, temperature range
- [ ] Who signs off Tier 3 (auto-execute) authority
- [ ] Vendor cloud (FusionSolar) override authority — can cloud override local Modbus commands?
- [ ] Write latency: measured Modbus TCP round-trip to BESS
- [ ] Weekend dispatch rules: same as weekday or reduced?
- [ ] BESS container fire suppression: present or not?
- [ ] Physical E-stop and BESS isolator location
- [ ] Who holds ADMIN role in SENTINEL
- [ ] BESS telemetry polling interval (seconds)
- [ ] NTP time sync between BESS, inverters, and SENTINEL
- [ ] SOC accuracy verification method
- [ ] Named daily monitor (not just "FM Team")
- [ ] Backup Tier 2 approver (if James Wilson unavailable)
- [ ] City Power SSEG approval reference number
- [ ] Insurance conditions affecting BESS operation
- [ ] Municipal reporting frequency and format
- [ ] Client's actual success criteria (confirm or replace defaults)
- [ ] Huawei warranty void conditions (specific to installed unit)
