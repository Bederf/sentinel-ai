---
title: "Gen Set 5 Quick Start — Phase 41-03 to 46 Implementation"
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

# Gen Set 5 Quick Start — Phase 41-03 to 46 Implementation

**Goal:** Before approving the R611,820.75 quote, capture phyphox diagnostic data to confirm/challenge the repair scope and validate cost-benefit.

**Timeline:** 30-minute assessment during Ntaote's onsite visit

---

## Phase 41-03 Execution Checklist (Vibration & Audio Analysis)

### 👤 Who & When
- **Technician:** Ntaote Moshoeshoe (or TP/Jimmy from facilities team)
- **Duration:** 30 minutes total (measurement + phyphox capture)
- **During:** Gen Set 5 operational visit (onsite assessment)
- **Deliverable:** 4 vibration recordings + 3 audio recordings + manual sensor data

### 📱 Equipment Required
- [ ] Android smartphone with phyphox app installed (free from Google Play)
- [ ] 500 MB free storage on phone
- [ ] Battery >50%
- [ ] Pen/paper for manual readings
- [ ] Temperature gun (if available for supplementary coolant temp check)

### 🎯 Specific Measurements (30-Min Protocol)

**Vibration (phyphox Accelerometer):**
1. **Engine Block:** 60s recording @ normal idle
   - **Detects:** Bearing condition, fuel injection timing issues, valve wear
   - **File:** Gen_Set5_Engine_Block_Vibration_[DATE]
   - ⏱️ 2 minutes

2. **Fuel Pump Mount:** 60s recording @ normal idle
   - **Detects:** Cavitation (high-freq noise 500+ Hz), pressure oscillations
   - **File:** Gen_Set5_Fuel_Pump_Vibration_[DATE]
   - ⏱️ 2 minutes

3. **Governor Linkage:** 60s with 3 gentle throttle bumps
   - **Detects:** Governor hunting (2-5 Hz oscillation = speed controller instability)
   - **File:** Gen_Set5_Governor_Vibration_[DATE]
   - ⏱️ 2 minutes

4. **Radiator Bracket:** 60s recording
   - **Detects:** Cooling fan bearing condition (previous failure 2022)
   - **File:** Gen_Set5_Radiator_Vibration_[DATE]
   - ⏱️ 2 minutes

**Audio (phyphox Audio Spectrum):**
5. **Engine Bay (Full Cycle):** 120s total (30s idle → 30s 50% load → 30s full load → 30s cool-down)
   - **Detects:** Engine knock (8-10 kHz bursts if fuel quality issue), combustion irregularities
   - **File:** Gen_Set5_Engine_Audio_2026-02-12
   - ⏱️ 5 minutes

6. **Fuel Injector Bank:** 60s @ idle
   - **Detects:** Injector spray pattern, missed clicks (injection failures), cavitation hiss
   - **File:** Gen_Set5_Injector_Audio_2026-02-12
   - ⏱️ 2 minutes

7. **Bearing Area:** 120s full cycle
   - **Detects:** Bearing cage noise, ball fracture signatures
   - **File:** Gen_Set5_Bearing_Audio_2026-02-12
   - ⏱️ 5 minutes

**Manual Readings (Validation):** ⏱️ 5 minutes
- [ ] Fuel pump pressure: _____ PSI (spec: 250-300; expect 210 warning)
- [ ] Oil temperature: _____ °C (spec: 85°C; expect 96° high)
- [ ] RPM: _____ (spec: 1500 ±25)
- [ ] Voltage & frequency: _____ V, _____ Hz
- [ ] Coolant temp: _____ °C
- [ ] Observations: ____________

**Total Time:** 30 minutes ✓

---

## Phase 44 Execution (Cost-Benefit Analysis)

### 📊 Inputs from Phase 41-03 Data

SENTINEL will analyze phyphox output to populate:

| System | Phase 41-03 Finding | Impact on Cost-Benefit |
|--------|-------------------|----------------------|
| **Fuel System** | Cavitation detected in pump audio? | If YES → injector contamination confirmed → R611K scope justified |
| **Speed Control** | Governor hunting (2-5 Hz oscillation)? | If YES → fuel instability cascading to controller → systemic repair needed |
| **Engine** | Oil temp 96°C + knock detected? | Indicates degraded combustion + thermal stress → overhaul justified |
| **Bearing Wear** | Elevated baseline vibration (7.2 mm/s)? | RUL estimate → justifies preemptive repair vs future failure |

### 💰 Quote Validation Framework

```
DIESEL ELECTRIC QUOTE: R611,820.75 includes:
├── Fuel system overhaul (injector replacement, fuel line purge)
├── Governor tune/replacement (speed control restoration)
├── Valve refurbishment (clearance, grinding if needed)
├── Engine service (oil, filters, coolant)
└── Pressure testing + validation

SENTINEL ANALYSIS WILL CONFIRM:
├── ✅ Is fuel cavitation the PRIMARY failure driver? (audio analysis)
├── ✅ Is speed control oscillation caused by fuel instability? (vibration analysis)
├── ✅ Are injectors actually contaminated? (indirect: knock + cavitation signatures)
├── ✅ Is engine wear significant enough to justify valve refurbishment? (combustion analysis)

OUTCOME:
├── If 4/4 confirmed → R611K repair justified, proceed with authorization
├── If 2-3 confirmed → Partial repair recommended, negotiate scope reduction
├── If <2 confirmed → Possible misdiagnosis, request alternative analysis
```

### 🎯 RUL Estimation per Subsystem

Phase 44 will calculate:
- **Fuel injection system:** RUL _____ months (degradation model)
- **Speed controller:** RUL _____ months
- **Engine cooling:** RUL _____ months
- **Bearing/drivetrain:** RUL _____ months
- **Overall equipment:** RUL _____ months → Critical if <12 months

**Decision Point:** If overall RUL <6 months → Repair approval urgent

---

## Phase 46 Execution (Post-Repair Validation)

### 📈 Timeline

**After repair completion by Diesel Electric:**
- [ ] Schedule Phase 46 measurement (same protocol as Phase 41-03)
- [ ] Capture identical 7 recordings + manual readings
- [ ] SENTINEL compares pre-repair vs post-repair baselines

### ✔️ Success Metrics

| Measurement | Pre-Repair | Post-Repair Target | Status |
|-------------|-----------|------------------|--------|
| Fuel pump pressure | 210 PSI (warning) | 250-280 PSI | Cavitation eliminated? |
| Oil temperature | 96°C (high) | 82-88°C (normal) | Combustion improved? |
| Governor oscillation | 2.3 Hz (hunting) | <0.5 Hz (stable) | Speed control restored? |
| Bearing vibration | 7.2 mm/s (warn) | <3.0 mm/s (normal) | Mechanical wear stopped? |
| Injector audio pattern | Irregular clicks | Regular, consistent | Injectors cleaned? |
| Cavitation signature | Present | Absent | Fuel system purged? |

### 💯 Effectiveness Score

**SENTINEL calculates:** Improvement % = [(Pre baseline - Post baseline) / Pre baseline] × 100

- **Target:** >85% improvement across all subsystems
- **Acceptable:** 70-85% improvement (partial restoration)
- **Failure:** <70% improvement (repair did not address root causes)

**If <70%:** Request warranty service from Diesel Electric to complete repair

---

## Implementation Timeline

### Week 1 (Feb 12-16)
- [ ] **MON-TUE:** Prepare phyphox app, confirm technician availability
- [ ] **WED:** Ntaote schedules onsite visit to Gen Set 5
- [ ] **FRI:** Baseline field assessment (Phase 41-03) — 30 minutes

### Week 2 (Feb 19-23)
- [ ] **MON-TUE:** Upload phyphox data to SENTINEL, manual readings documented
- [ ] **WED-FRI:** Phase 44 cost-benefit analysis → Report to Ntaote + TP + Jimmy

### Decision Point
- **If approved:** Proceed with Diesel Electric repair (R611,820.75)
- **If challenged:** Request cost reduction or alternative scope from Diesel Electric
- **If rejected:** Escalate to facilities leadership for final decision

### Post-Repair (Weeks 4-6)
- [ ] Diesel Electric completes repair
- [ ] Schedule Phase 46 measurement (identical protocol)
- [ ] SENTINEL validates effectiveness
- [ ] Archive baseline data for future diagnostics

---

## Key Questions for Ntaote's Team

**Before Phase 41-03 Field Visit:**
1. What is the exact scope of the R611K repair? (Ask for Diesel Electric's detailed work order)
2. Are there any known fuel quality issues at this site?
3. Has the governor/speed controller linkage been inspected for mechanical wear?
4. What was the date of the last fuel filter replacement?

**After Phase 41-03 Analysis:**
1. Does SENTINEL confirm fuel cavitation as the primary failure driver?
2. If YES → R611K repair justified, proceed with authorization
3. If NO → What alternative issues did SENTINEL identify?

**Post-Repair:**
1. Did Diesel Electric provide a warranty on the repair?
2. What is the recommended service interval post-repair?
3. Should Gen Set 5 be placed on monthly condition monitoring with phyphox?

---

## Success Criteria

✅ Phase 41-03 Complete: Phyphox baseline captured, manual readings recorded
✅ Phase 44 Complete: Cost-benefit analysis confirms repair scope
✅ Phase 46 Ready: Post-repair validation protocol established for effectiveness tracking
✅ R611K Decision: Data-driven recommendation provided to Ntaote + TP + Jimmy
✅ Long-Term Resolution: Gen Set 5 diagnostic baseline established for future monitoring

---

## SENTINEL Support

**Questions or issues during implementation?**
- Ask SENTINEL AI chat: "Help me interpret Gen Set 5 phyphox data"
- Reference this doc: gen-set-5-quick-start-checklist.md
- Equipment code: S002-GEN-G-005

**To upload phyphox files:**
- Via Sentry: Send CSV/JSON exports directly
- Via email: Send to SENTINEL data ingestion endpoint
- Via frontend: Use equipment detail page → Upload baseline files

---

**Ready to proceed? Contact Ntaote to schedule the 30-minute Phase 41-03 field visit.**

Equipment: **S002-GEN-G-005** (Gen Set 5 - 100kW Diesel)
Location: **Sandton City Ground Plant Room**
Date Prepared: **2026-02-12**
