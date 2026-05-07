---
title: "SIMBIOT BMS Integration Onboarding Checklist"
type: "spec"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# SIMBIOT BMS Integration Onboarding Checklist

**Document Type**: Implementation Guide + Sales Collateral  
**Audience**: BMS Consultants, Facility Managers, SENTINEL Account Managers  
**Purpose**: Clarify what SIMBIOT autodetects vs. what requires consultant input

## Executive Summary

SENTINEL's SIMBIOT device abstraction layer autodetects **~60% of BMS integration requirements** via BACnet/Modbus discovery. The remaining 40% requires one-time consultant inputs—no ongoing exports needed.

**The Pitch:** "Your BMS consultant provides network access + a couple of seed CSVs, and SIMBIOT handles the rest."

---

## Site-002 deterministic stage gates

Site-002 onboarding uses a deterministic policy to drive stage progression:

`commissioning -> shadow_live -> advisory -> supervised -> automatic`

The policy evaluates every 5 minutes and automatically writes stage transitions to Supabase when `dry_run: false`. A manual phase advance via the UI is **blocked** when the current stage's entry gates have not passed — the operator sees a toast explaining which specific gates failed.

See [`109C-site-002-mode-policy-dry-run.md`](../04-features/109C-site-002-mode-policy-dry-run.md) for the full threshold table.

### Promotion and demotion criteria

| Transition | Minimum dwell | Promotion criteria | Demotion criteria |
|-----------|---|---|---|
| `commissioning -> shadow_live` | 0h | all commissioning gates pass, truth check submitted, consecutive pass days >= 2 | n/a |
| `shadow_live -> advisory` | 12h | freshness <= 2h, match coverage >= 95%, error rate <= 1%, no file/manual sources, quality gate pass/warn, consecutive pass days >= 2 | demote to `shadow_live` after 2h sustained violation of shadow exit thresholds |
| `advisory -> supervised` | 24h | freshness <= 1h, match coverage >= 97%, error rate <= 1%, no file/manual sources, conflicts 24h = 0, quality gate pass/warn, consecutive pass days >= 2 | demote to `shadow_live` after 2h sustained violation of advisory exit thresholds |
| `supervised -> automatic` | 24h | freshness <= 0.5h, match coverage >= 98%, error rate <= 0.5%, no file/manual sources, conflicts 24h = 0, quality gate pass only, consecutive pass days >= 2 | demote to `shadow_live` after 1h sustained violation of supervised exit thresholds |

Note: BMS active alarms do **not** block SENTINEL policy gates — only data quality metrics (freshness, match coverage, error rate, provenance, quality gate status) gate progression.

### Automatic stage fail-closed

When in `automatic`, any fail of freshness, coverage, provenance, conflict, or quality-gate thresholds triggers immediate dry-run outcome:

- Decision: `would_fail_closed_demote`
- Target stage: `supervised`
- Write action: `stop_writes`

### Anti-flap rule

After any demotion, promotion is blocked for 24 hours (`repromotion_stability_hours = 24`).

---

## Site-002 guided inspection policy (major equipment only)

Guided inspection generation is intentionally scoped to major plant first. This reduces onboarding risk and avoids over-instrumenting low-impact endpoints.

### Tier policy

| Tier | Included in full guided inspection | Rule |
|---|---|---|
| Tier A | Yes | `type` in `CHILLER, CHWP, CWP, CT, BOILER, AHU, GEN, UPS, ATS, MSB, INCOMER` |
| Tier B | Conditional | `type` in `FCU, VAV, DALI_CONTROLLER, METER` and (`health_score <= 70` or `>= 2` warning/critical transitions in 30 days) |
| Tier C | No | All other endpoints/sensors/luminaires/low-impact assets |

### Overrides

- Force include: life-safety assets, backup power chain, whole-floor comfort assets, or any `criticality=high` asset.
- Force exclude: telemetry-only/virtual/software-only points and single endpoint sensors/luminaires.

### Site-002 default Tier A prefixes

- `S002-CHILLER-`, `S002-CHWP-`, `S002-CWP-`, `S002-CT-`, `S002-BOILER-`
- `S002-AHU-`, `S002-GEN-`, `S002-UPS-`, `S002-ATS-`, `S002-MSB-`, `S002-INCOMER-`

### Onboarding acceptance criteria for this policy

- 100% of Tier A assets are present in Supabase equipment inventory.
- Tier A assets have discovered technical identity populated: `manufacturer` and `model`.
- Tier A work orders generate guided inspection instructions and technician evidence prompts.
- Tier B/C assets do not block commissioning if guided inspection metadata is incomplete.

---

## Scorecard: Automation vs. Consultant Input

| Category | Item | Auto-Detected | Consultant Input | Effort | Notes |
|----------|------|---|---|---|---|
| **Point List** | Equipment points (temps, valves, fans) | ✅ | — | 0 min | BACnet discovery finds all points |
| | BACnet object types (AI, AO, BI, BO, AV, BV, etc.) | ✅ | — | 0 min | Encoded in BACnet metadata |
| | Point instance numbers | ✅ | — | 0 min | BACnet protocol |
| | Point descriptions (BACnet Description property) | ✅ | — | 0 min | Configured in BMS |
| | Point units (°C, PSI, V, etc.) | ✅ | — | 0 min | BACnet Units property |
| | Point naming convention | ⚡ Inferred | Optional: official doc | 5-10 min | AI pattern matching used if doc provided |
| **Controllers** | Controller discovery (Who-Is/I-Am) | ✅ | — | 0 min | BACnet protocol discovery |
| | Device Instance IDs | ✅ | — | 0 min | BACnet Device object |
| | IP addresses (BACnet/IP) or MSTP addresses | ✅ | — | 0 min | BACnet addressing |
| | Model name & vendor | ✅ | — | 0 min | Device Manufacturer/Model properties |
| | Floor/area served | ❌ | **Required** | 10-30 min | Not exposed via BACnet (must be inferred by location or manually mapped) |
| | Redundancy info (active/standby) | ⚡ | Optional | 5-10 min | Can be inferred from point health, or provided by consultant |
| **Historical Data** | Alarm history (past 7-14 days) | ❌ | **CSV Export** | 30 min | SIMBIOT can't reach back in time to Desigo CC SQL database |
| | Trend data (past 3-5 days) | ❌ | **CSV Export** | 30 min | Needed for ML model seed data |
| | Trend data (ongoing) | ✅ | — | 0 min | BACnet COV + polling collects going forward |
| | Alarm history (ongoing) | ✅ | — | 0 min | BACnet alarm/event objects subscribed |
| **System Info** | Desigo CC version | ❌ | **Screenshot/email** | 5 min | Not exposed via BACnet |
| | BMS server IP address | ❌ | **Provided during setup** | 5 min | Required to configure connection |
| | BMS network subnet (CIDR) | ❌ | **Provided during setup** | 5 min | Required for BACnet discovery configuration |
| | Active Directory credentials (if required) | ⚡ | Optional | 2 min | Only if Desigo CC requires domain auth |
| | BACnet gateway IP (if not same as BMS server) | ⚡ | Optional | 5 min | Required if BACnet on separate network |

---

## By Phase: What Happens When

### Phase 1: Pre-Onboarding (CONSULTANT)
**Effort:** ~1.5 hours (mostly documentation)

**Checklist:**
- [ ] **Network Access**
  - [ ] Provide BMS server IP address
  - [ ] Provide network subnet (e.g., 192.168.1.0/24)
  - [ ] Provide BACnet gateway IP (if separate)
  - [ ] Whitelist SENTINEL appliance IP on firewall
  - [ ] Confirm BACnet/IP is enabled on BMS (vs MSTP-only)
  - [ ] Confirm BACnet Who-Is/I-Am discovery is enabled

- [ ] **Documentation**
  - [ ] Point naming convention (e.g., "HVAC_ChillerSupplyTemp_L1")
  - [ ] Equipment naming scheme (e.g., "CH-001", "AHU-L1", "FCU-L2-A")
  - [ ] Controller naming (e.g., "PXC4_L2_West", "MSTP_Controller_B1")
  - [ ] Floor mapping (which controllers serve which floors)
  - [ ] System architecture diagram (optional but helpful)

- [ ] **Credentials** (if needed)
  - [ ] BACnet user/password (if password-protected)
  - [ ] Active Directory credentials (if domain-authenticated)
  - [ ] Desigo CC screenshot showing version number

- [ ] **Historical Data Exports** (optional, improves ML)
  - [ ] Alarm history CSV: Past 7-14 days of alarms (fields: timestamp, equipment, alarm type, severity, cleared_at)
  - [ ] Trend data CSV: Past 3-5 days of key points (fields: timestamp, point_name, value, unit)
  - [ ] File format: CSV, Excel, or JSON accepted

---

### Phase 2: BMS Connection Wizard (SIMBIOT AUTODETECTS)
**Effort:** ~45 minutes (fully automated)

**What Happens:**
1. **Network Configuration** (5 min)
   - SIMBIOT connects to BMS server IP
   - Validates network connectivity
   - Authenticates if required (AD/BACnet credentials)

2. **Discovery** (15 min) — ✅ FULLY AUTO
   - [ ] **Controllers Found:**
     - Device Instance IDs auto-detected
     - IP addresses auto-detected
     - Model names auto-detected
     - Vendor names auto-detected
     - Device count: **X controllers discovered**

   - [ ] **Points Found:**
     - BACnet object count: **Y total points**
     - By type: **Z AI (analogs)**, **W BI (binaries)**, **V AV (values)**, etc.
     - Descriptions: auto-extracted from Description property
     - Units: auto-extracted from Units property
     - Status: **X online**, **Y offline**, **Z unreachable**

3. **AI Classification** (15 min) — ✅ AUTO + CONSULTANT ASSIST
   - [ ] Points automatically mapped to SENTINEL equipment types:
     - **HVAC:** AHU, FCU, VAV, Chiller, Boiler, Pump, Split, CRAC, Cooling Tower, Cold Room, KEF
     - **Electrical:** Generator, UPS, ATS, MSB, Distribution Board, Meter, Transformer, PFC
     - **Lighting:** DALI, Luminaire
     - **Fire/Safety:** Fire Panel
     - **Security:** Access Control, CCTV
     - **Transport:** Lift/Elevator
     - **Medical:** Medical Gas System (MEDGAS)
     - **Controllers:** JACE, PXC, BMS

   - [ ] Vendor-agnostic classification (3-tier approach):
     - [ ] **Tier 1 — Metadata:** Uses equipment JSON metadata (`equipment_type`, `equipment_id`) when available — 100% high confidence, works for any BMS vendor
     - [ ] **Tier 2 — ID extraction:** Extracts type code from equipment ID segments (e.g., `COLD`, `LIFT`, `JACE`) using KNOWN_TYPE_CODES lookup
     - [ ] **Tier 3 — Regex fallback:** Pattern matching against point names for raw BACnet points without metadata

   - [ ] Floor/zone extraction from equipment IDs (vendor-agnostic):
     - [ ] Finds floor codes (L3, B1, G, R) anywhere in hyphen/dot-separated IDs
     - [ ] Works for Niagara (`site-005-UMH-AHU-L3-ICU`), Desigo, Schneider, etc.

   - [ ] Equipment instances created (e.g., "S005-AHU-L3-ICU")
     - Naming uses SENTINEL v2.0 format: `S###-TYPE-FLOOR-ZONE`
     - **Count:** X equipment instances created

4. **Verification** (10 min) — CONSULTANT REVIEWS
   - [ ] Consultant reviews discovered equipment list
   - [ ] Confirms floor assignments are correct
   - [ ] Identifies any missed equipment or misclassifications
   - [ ] Approves or corrects mappings

**Output:** Building + equipment records created, ready for live monitoring

---

### Phase 3: Optional Historical Data Ingestion (CONSULTANT + SIMBIOT)
**Effort:** ~30 minutes (recommended for ML accuracy)

**If consultant provided CSV exports:**

1. Alarm History CSV
   - [ ] Upload 7-14 day alarm export
   - [ ] SIMBIOT imports to time-series database
   - [ ] ML models use for anomaly baseline tuning

2. Trend Data CSV
   - [ ] Upload 3-5 day equipment trend export
   - [ ] SIMBIOT seeds initial LSTM models
   - [ ] Improves ML prediction accuracy from day 1

**If CSVs not available:**
- ✅ SIMBIOT still works fine (collects data going forward)
- ⚠️ ML predictions less accurate first 1-2 weeks (normal behavior)
- Data collection starts immediately

---

## Detailed Input Requirements

### 1. Network Access (CONSULTANT PROVIDES)

| Parameter | Example | Why Needed | Format |
|-----------|---------|-----------|--------|
| BMS Server IP | 192.168.1.100 | Initial connection | Single IPv4 address |
| Network Subnet | 192.168.1.0/24 | BACnet discovery scope | CIDR notation |
| BACnet Gateway IP | 192.168.1.150 | If BACnet on separate network | Single IPv4 address or "same as BMS" |
| Firewall Rule | Port 47808 (UDP) | BACnet/IP communication | Port number |
| Authentication Type | "None", "AD", or "BACnet" | Connection setup | Single option |
| Credentials (if needed) | user / password | AD or BACnet authentication | Text credentials |
| Desigo CC Version | V5.0.0 build 254 | Compatibility checking | Screenshot or text |

**Effort:** Consultant knows this info, ~5 minutes to provide

**Validation:**
- [ ] BMS server responds to ping
- [ ] BACnet port 47808 reachable
- [ ] Who-Is/I-Am discovery works
- [ ] At least 1 controller found

---

### 2. Equipment Naming Convention (CONSULTANT PROVIDES - OPTIONAL)

If provided, improves point classification accuracy by 10-20%.

**Example Convention 1: Siemens Desigo**
```
[SYSTEM]_[PARAMETER]_[QUALIFIER]
Examples:
  HVAC_ChillerWaterTemp_Supply
  HVAC_AHU_Fan_Speed_Percent
  ELEC_Generator_Runtime_Hours
  LIGHTING_Zone_1_Level_Percent
```

**Example Convention 2: Pneumatic (Legacy)**
```
[FLOOR][SYSTEM][UNIT]_[POINT]
Examples:
  L1CHW_SUPPLY_T    = Level 1, Chilled Water, Supply Temperature
  L2AH_COOL_CMD     = Level 2, Air Handler, Cooling Command
  B1GEN_RPM         = Basement 1, Generator, RPM
```

**Example Convention 3: Free-Form**
```
Any pattern works; AI pattern-matches to SENTINEL taxonomy
  supply_temp_l1, ahu_fan_l2, chiller_runtime_b1, etc.
```

**Effort:** ~5 minutes to paste into wizard (optional)

**Impact without it:**
- ✅ Still works; AI classifies based on data type
- ⚠️ May misclassify ambiguous points (~10-20% error rate)
- Solution: Consultant corrects misclassifications in verification step

---

### 3. Floor/Area Mapping (CONSULTANT PROVIDES)

**Critical for:** Equipment placement in Digital Twin, technician routing, geographic alerts

| Controller | Floors Served | Areas Covered |
|-----------|---|---|
| PXC4_L2_West | L2, L3 | West Wing (offices) + Center core |
| PXC4_B1 | B1 | Plant room (HVAC, power) |
| MSTP_Controller_1 | L1 | East Wing + lobby |

**Format:** Simple table or mapping document

**Effort:** ~10 minutes (consultant copies from system architecture doc)

**Validation:**
- [ ] Every controller has explicit floor assignment
- [ ] No gaps (all floors covered)
- [ ] No overlaps (each floor served by clear controller)

---

### 4. Historical Data (CONSULTANT PROVIDES - OPTIONAL)

**Only needed if ML accuracy is critical from day 1** (e.g., load shedding optimization, chiller predictive maintenance)

#### Alarm History CSV
```csv
timestamp,equipment_id,alarm_type,severity,description,cleared_at
2026-01-30 08:15:00,CH-001,HighPressure,CRITICAL,Discharge pressure > 350 PSI,2026-01-30 08:45:00
2026-01-30 09:20:00,AHU-L1,FanFault,WARNING,Fan motor current high,2026-01-30 09:22:00
2026-01-30 14:30:00,GEN-B1,LowFuel,WARNING,Fuel level < 25%,
```

**Fields Required:**
- timestamp (ISO format)
- equipment_id (matches BMS naming)
- alarm_type (e.g., HighPressure, FanFault, LowFuel)
- severity (CRITICAL, WARNING, INFORMATIONAL)
- cleared_at (or NULL if still active)

**Duration:** 7-14 days preferred (minimum 2 days useful)
**File Size:** ~500 rows typical
**Effort:** ~20 minutes for consultant to export from Desigo CC history view

#### Trend Data CSV
```csv
timestamp,point_name,value,unit
2026-01-30 00:00:00,HVAC_ChillerSupply_Temp,6.2,°C
2026-01-30 00:05:00,HVAC_ChillerSupply_Temp,6.1,°C
2026-01-30 00:10:00,HVAC_ChillerSupply_Temp,6.3,°C
2026-01-30 00:00:00,ELEC_UPS_Load,0.45,%
2026-01-30 00:05:00,ELEC_UPS_Load,0.46,%
```

**Fields Required:**
- timestamp (ISO format)
- point_name (matches BMS naming)
- value (numeric)
- unit (°C, %, PSI, kW, etc.)

**Duration:** 3-5 days (minimum 1 day useful)
**Data Points:** One reading per 5 minutes typical
**File Size:** ~50k rows typical
**Effort:** ~20 minutes for consultant to export from Desigo CC trend archive

**Impact without historical data:**
- ✅ System still works perfectly (collects data going forward)
- ⚠️ ML predictions less confident first 1-2 weeks
- Why: Models need baseline data to detect anomalies

---

## Consultant Responsibilities Matrix

### Pre-Onboarding (Week 1)

| Task | Owner | Time | Deliverable |
|------|-------|------|-------------|
| Provide network access | **Consultant** | 5 min | IP, subnet, credentials |
| Document equipment naming | Consultant (optional) | 5 min | Naming convention doc |
| Map equipment to floors | **Consultant** | 15 min | Controller-to-floor table |
| Export historical alarms | Consultant (optional) | 20 min | 7-14 day CSV |
| Export historical trends | Consultant (optional) | 20 min | 3-5 day CSV |
| | | **~1.5 hours total** | |

### Onboarding Day (Week 2)

| Task | Owner | Time | Deliverable |
|------|-------|------|-------------|
| Run BMS Connection Wizard | **SIMBIOT** | 45 min | Equipment discovery + mapping |
| Verify discovered equipment | **Consultant** | 15 min | Sign-off on equipment list |
| Ingest historical data (optional) | **SIMBIOT** | 15 min | ML model seeding |
| | | **~1.5 hours total** | |

### Post-Onboarding

| Task | Owner | Time | Notes |
|------|-------|------|-------|
| Collect new alarm/trend data | **SIMBIOT** | Continuous | Automatic going forward |
| Monitor equipment health | **SIMBIOT** | Continuous | No consultant input needed |
| Optimize equipment settings | **Facility Manager** | Ongoing | Based on SIMBIOT recommendations |

---

## Acceptance Criteria: Successful Onboarding

### ✅ Completion Checklist

- [ ] Network connectivity verified (BMS server responds)
- [ ] BACnet discovery completes without errors
- [ ] **X controllers** found and device IDs captured
- [ ] **Y points** discovered and classified (HVAC, electrical, etc.)
- [ ] **Z equipment instances** created in SENTINEL format (S###-TYPE-FLOOR-ZONE)
- [ ] Floor assignments verified (each controller has explicit floor map)
- [ ] Equipment list reviewed and approved by consultant
- [ ] Historical data imported (if CSVs provided)
- [ ] Dashboard shows live data from all points
- [ ] First alarms received and logged
- [ ] Mobile app shows building + equipment + real-time status
- [ ] Facility manager can see equipment on map/digital twin
- [ ] First AI recommendation generated (target: within 24 hours)

---

## FAQ: Consultant Questions

### Q1: "Do I need to manually create equipment records?"
**A:** No. SIMBIOT's BACnet discovery automatically creates equipment records from discovered points. Your job is to verify they're correct (30% of discovery process) and provide optional metadata (floor mapping).

### Q2: "What if BMS uses non-standard point naming?"
**A:** SIMBIOT uses a 3-tier vendor-agnostic classifier: (1) equipment metadata from JSON files (100% accuracy), (2) type code extraction from equipment IDs, (3) regex pattern matching as fallback. Works for Niagara, Desigo, Schneider, Honeywell, and any vendor. No code changes needed per client — if a new equipment type appears, it's a one-line addition to the type lookup table.

### Q3: "How often do I need to export data?"
**A:** Only during onboarding (one-time). Going forward, SIMBIOT collects data automatically via BACnet COV (change-of-value) and polling. No ongoing exports needed.

### Q4: "Can SIMBIOT pull historical data from Desigo CC?"
**A:** No, SIMBIOT can't reach back into the SQL database. That's why a one-time CSV export is helpful (but optional). SIMBIOT collects all data going forward automatically.

### Q5: "What if equipment is offline/unreachable?"
**A:** SIMBIOT still creates records but marks as offline. Once the equipment comes online, SIMBIOT starts collecting data immediately (no re-setup needed).

### Q6: "Do I need to configure BACnet parameters?"
**A:** No. SIMBIOT auto-detects BACnet settings (instance numbers, object types, units, etc.) from the BMS. Your BMS already has these configured.

### Q7: "Can I use this with a Modbus-only BMS?"
**A:** Yes (with caveats). If no BACnet gateway exists, SIMBIOT requires manual equipment list + Modbus register mapping (more consultant effort). BACnet is strongly recommended.

### Q8: "What's the typical success rate?"
**A:** ~95% of points discovered correctly. When equipment JSON metadata is available (simulation or pre-configured sites), 100% classification at high confidence. For raw BACnet discovery, ~85-95% classified automatically — consultant verification catches the remainder in ~15 minutes.

---

## Success Metrics

**After Successful Onboarding, Consultant Can Verify:**

1. **Equipment Discovery Accuracy**
   - [ ] 95%+ of BMS points detected by SIMBIOT
   - [ ] 100% classified at high confidence (when equipment metadata available)
   - [ ] 85-95% classified automatically for raw BACnet discovery
   - [ ] 0% needs review (metadata path) or <15% requiring manual correction (regex path)

2. **Data Collection**
   - [ ] All discovered points receiving live data (no nulls)
   - [ ] Data quality: <1% missing/invalid readings
   - [ ] Update frequency: ≥ 60% of expected for COV + polling

3. **ML Readiness**
   - [ ] Baseline models trained within 24 hours
   - [ ] First anomaly detected and alerted
   - [ ] First optimization recommendation generated

4. **User Experience**
   - [ ] Dashboard loads in < 5 seconds
   - [ ] Equipment status updates < 10 seconds after BMS change
   - [ ] Facility manager can navigate to any equipment detail page
   - [ ] Digital twin renders correctly (if 3D floor plan provided)

---

## Pitch to Clients

### For Facility Managers:
"SENTINEL autodetects 95% of your BMS equipment via the BACnet gateway. Your consultant just needs to verify floor assignments—about 30 minutes of work. Then SENTINEL collects data automatically. No more manual exports ever."

### For BMS Consultants:
"You get to focus on optimization recommendations while SIMBIOT handles the tedious equipment discovery. One 90-minute wizard run, one verification pass, and you're done. All future data collection is automatic."

### For CIOs (Data Security):
"No continuous data exports leave your building. SIMBIOT connects directly to your BMS (via BACnet) and collects data in real-time. Historical seed data is optional and stays on your network. Perfect for security-first facilities."

---

## Checklist Template: Print & Use

```
SENTINEL SIMBIOT Onboarding Checklist
Building: ________________    Date: ________________
Consultant: ________________ Account Manager: ________________

PRE-ONBOARDING (Week 1)
[ ] Network access provided (IP, subnet, credentials)
[ ] Equipment naming convention documented (optional)
[ ] Floor/controller mapping documented
[ ] Historical alarm CSV exported (optional: 7-14 days)
[ ] Historical trend CSV exported (optional: 3-5 days)

ONBOARDING DAY (Week 2)
[ ] BMS Connection Wizard started
[ ] Controllers discovered: ______ found
[ ] Points discovered: ______ total
[ ] Equipment instances created: ______ instances
[ ] Floor assignments verified
[ ] Equipment list approved by consultant

POST-ONBOARDING
[ ] Dashboard showing live data
[ ] First alarms received
[ ] Digital twin rendering (if 3D floor plan provided)
[ ] First AI recommendation generated
[ ] Facility manager trained on mobile app

SIGN-OFF
Consultant: ________________    Date: ________________
Account Manager: ________________    Date: ________________
```

---

## Related Documentation

- **SIMBIOT Integration Guide**: `docs/05-integrations/README.md`
- **BACnet Discovery Deep Dive**: `docs/05-integrations/bacnet-object-reference.md`
- **Troubleshooting**: `docs/05-integrations/simbiot-troubleshooting.md`
- **Equipment Naming v2.0**: `../02-architecture/NAMING_CONVENTIONS.md`
- **Digital Twin Feature**: `docs/04-features/DIGITAL_TWIN_REAL_DATA_INTEGRATION.md`
- **Deterministic Stage Policy (Site-002)**: `../04-features/109C-site-002-mode-policy-dry-run.md`

---

**Document Version:** 1.2
**Last Updated:** 2026-02-23
**Audience:** BMS Consultants, Facility Managers, Sales Team
**Status:** Ready for Production Use
