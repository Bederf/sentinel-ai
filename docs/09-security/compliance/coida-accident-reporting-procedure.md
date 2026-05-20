---
title: "COIDA Accident Reporting Procedure"
type: "procedure"
status: "active"
version: "0.1.0"
created: "2026-05-19"
updated: "2026-05-19"
author: "SENTINEL Compliance Team"
tags: ["coida", "accident-reporting", "ohs", "south-africa", "legal", "doel", "compensation"]
domain: "compliance"
audience: "compliance, facilities, management, engineering"
complexity: "high"
estimated_read_time: 15
---

# COIDA Accident Reporting Procedure

## 1. Purpose and Legal Basis

This procedure defines how SENTINEL handles workplace accidents and compensation claims under the Compensation for Occupational Injuries and Diseases Act 130/1943 (COIDA), as amended.

COIDA requires employers to report accidents resulting in death, injury, or disease to the Department of Employment and Labour (DoEL) within **7 days** of the accident. Failure to report is a criminal offence under s49 of the Act.

**Reference:** COIDA Act 130/1943, Sections 8, 10, 22, 24, 38, 43, 49.
**Review period:** Annually or after any incident.
**Owner:** Facilities Manager / Managing Director.

> **Legal disclaimer:** This procedure is for internal governance use only. It does not constitute legal advice. COIDA claims are handled by the Compensation Fund. Consult qualified legal counsel for actual claims.

---

## 2. Scope

This procedure applies to:
- Accidents involving SENTINEL personnel, contractors, or visitors on SENTINEL-operated sites
- Accidents involving BMS equipment that may be relevant to a COIDA claim (e.g., HVAC-related injury, electrical fault, lift malfunction)
- Near-miss incidents that could have resulted in injury (must be documented for due diligence)

**Out of scope:**
- Personal health conditions not caused by work (not COIDA)
- Motor vehicle accidents on public roads (ROiA, not COIDA)
- Mining accidents (Mines and Works Act, not COIDA)

---

## 3. What Must Be Reported

### 3.1 Mandatory Reporting Triggers

| Scenario | Report to DoEL? | Report to SAPS? |
|---------|----------------|-----------------|
| Death resulting from workplace accident | ✅ Yes — immediately | ✅ Yes |
| Injury requiring medical treatment (beyond first aid) | ✅ Yes — within 7 days | ❌ No (unless crime suspected) |
| Occupational disease (e.g., heat exhaustion, repetitive strain) | ✅ Yes — within 7 days of diagnosis | ❌ No |
| Near-miss with potential serious injury | ❌ No legal requirement | ❌ No |
| Minor first-aid-only injury (no medical treatment) | ❌ No | ❌ No |

### 3.2 BMS-Related Scenarios Requiring COIDA Assessment

The following SENTINEL events may trigger COIDA obligations — assess each against the table above:

| Event | COIDA Relevance | Action |
|-------|----------------|--------|
| Technician injured by moving HVAC equipment (FCU, chiller) | Likely — work-related injury | Assess and report if medical treatment required |
| Electrical shock from faulty equipment (electrical CoC lapse) | Likely — work-related injury + electrical fault | Assess and report; also check SANS 10142-1 compliance |
| Lift entrapment of employee | Likely — occupational injury + lift safety | Report within 7 days; also check lift safety regs |
| Legionella exposure (cooling tower contamination) | Possible — occupational disease | Assess if diagnosis linked to workplace exposure |
| Heat exhaustion (HVAC failure in server room) | Possible — occupational health | Assess if work environment caused condition |
| Fall on wet floor (cleaning crew — BMS not HVAC cause) | Not COIDA (facilities management, not SENTINEL) | Document; forward to building management |

---

## 4. Internal Escalation Chain

```
ACCIDENT DETECTED
       │
       ▼
Site Manager / First Responder
       │
       ▼
Collect BMS evidence (if applicable) — within 2 hours
       │
       ▼
Facilities Manager (escalate within 4 hours of accident)
       │
       ├─ Fatality or serious injury → Managing Director immediately
       │   → DoEL report within 7 days
       │   → SAPS if applicable
       │
       └─ Other injury requiring medical treatment → DoEL report within 7 days
           → Compensation claim lodged with Compensation Fund
           → Near-miss logged in SENTINEL
```

**Compensation claim contact:**
- DoEL online portal: https://onlinecomp.co.lef.gov.za/
- Compensation Fund call centre: 0860 100 250
- Registration of employer (if not yet registered): Form W2/COIDA

---

## 5. BMS Evidence Collection

When a BMS-related accident occurs, the following BMS data must be preserved as evidence:

### 5.1 What to Collect

| Evidence Type | Source | How to Extract | Retention |
|---------------|--------|----------------|-----------|
| Equipment status at time of accident | Shadow mode polling data | `SELECT * FROM equipment_status WHERE site_id = 'site-002' AND timestamp BETWEEN '<accident_date> 00:00:00' AND '<accident_date> 23:59:59'` | 7 years |
| Alarm and event log for affected zone | Loki | `scripts/export-loki-range.sh "<accident_datetime-2h>" "<accident_datetime+2h>" coida-evidence.json` | 7 years |
| Maintenance work orders for affected equipment | Supabase `work_orders` table | `SELECT * FROM work_orders WHERE equipment_id = '<equip_id>' AND completed_at IS NOT NULL ORDER BY completed_at DESC LIMIT 10` | 7 years |
| Electrical CoC record (if electrical incident) | Supabase `compliance_records` table | `SELECT * FROM compliance_records WHERE site_id = 'site-002' AND compliance_type = 'electrical_coc' AND expiry_date > '<accident_date>'` | 7 years |
| Legionella risk assessment (if water-related) | Supabase `legionella_risk_assessment` table | `SELECT * FROM legionella_risk_assessment WHERE site_id = 'site-002' ORDER BY assessment_date DESC LIMIT 1` | 7 years |
| HVAC schedule / setpoint history | Shadow mode polling | Point history from site bridge historian | 7 years |
| Alert notification log (who was notified, when) | Supabase `parasite_decisions` table | `SELECT * FROM parasite_decisions WHERE site_id = 'site-002' AND created_at BETWEEN '<accident_date> 00:00:00' AND '<accident_date> 23:59:59'` | 7 years |

### 5.2 Chain of Custody

BMS evidence must be preserved with clear chain of custody:

1. **Extract** — run the queries/scripts above immediately, save to `incidents/<YYYY-MM-DD>-coida/<>` in the vault
2. **Hash** — compute SHA-256 hash of each export file and record in incident file:
   ```bash
   sha256sum incidents/<YYYY-MM-DD>-coida/equipment_status_20260519.json
   # SHA256: a3f5b8c9d2e1... (record this)
   ```
3. **Seal** — copy to separate immutable storage (USB drive, not connected to internet; or encrypted cloud storage with no delete permissions)
4. **Log** — enter in incident register: file name, hash, extracted by, extracted at, stored at

> **Do not modify exported files.** Any modification destroys evidentiary value. If corrections are needed, create a new annotated version and keep both.

---

## 6. 7-Day Reporting Timeline

```
Day 0 — Accident occurs
  │
  ▼
Day 0-1 — Initial response (first aid, medical treatment, scene safety)
  │
  ▼
Day 0-2 — BMS evidence collected and sealed
  │
  ▼
Day 1-3 — Assess whether DoEL report required
  │
  ▼
Day 3-6 — Prepare WCL 2/4 form (Report of Accident form)
  │
  ▼
Day 7 — Submit to DoEL via online portal OR submit to nearest DoEL office
  │
  ▼
Day 7+ — File in incident register; notify Compensation Fund if claim expected
```

**WCL 2/4 Form (Report of Accident / Occupational Disease):**
Obtainable from: https://www.labour.gov.za/ — search "WCL 2/4"
Or from: nearest DoEL office or Labour Centre.

Required information for the form:
- Employer registration number (with Compensation Fund)
- Employee details (name, ID, occupation, department)
- Date and time of accident
- Place of accident (building, zone, equipment)
- Description of how accident occurred
- Nature of injury (medical diagnosis if available)
- Medical treatment given
- Witnesses (if any)
- Employer investigation findings (attach BMS evidence)

---

## 7. DoEL Report Exemptions and Considerations

**Near-miss documentation (not a reportable event but tracked):**
- Create entry in SENTINEL incident register: `incidents/<YYYY-MM-DD>-near-miss.md` in vault
- Include: description of near-miss, equipment involved, root cause, corrective action
- This demonstrates due diligence for future COIDA claims

**When DoEL might not accept a claim:**
- Accident occurred while employee was under influence of alcohol/drugs
- Employee was committing a criminal act at the time
- Accident was wholly due to employee disregarding written safety instructions
- Disease was not occupational (must be linked to work exposure)

**SENTINEL's due diligence defence:**
- If equipment was maintained per schedule (work orders in Supabase) and BMS data shows no anomalies before accident, this supports the defence that SENTINEL took reasonable steps
- Conversely, if BMS showed faults and maintenance was overdue, this weakens the due diligence defence

---

## 8. Compensation Fund Claim Process

If an employee is injured and medical treatment was required:

1. **WCL 2/4 submitted within 7 days** (report accident only — not yet claiming)
2. **WCL 1 (First Medical Report)** — completed by treating doctor, submitted to Compensation Fund
3. **WCL 3 (Progress Medical Report)** — if further treatment needed
4. **WCL 4 (Invoice for Medical Expenses)** — medical service providers claim directly from Compensation Fund

**Medical aid providers** must be registered with Compensation Fund to claim. Employee cannot be billed directly for compensable injuries.

---

## 9. Near-Miss Register

For any near-miss event (no actual injury but potential for serious harm), document in `incidents/<YYYY-MM-DD>-near-miss.md`:

```markdown
# Near-Miss Incident — <YYYY-MM-DD>

**Reported by:** <name>
**Date/Time:** <datetime>
**Location:** <building, zone, equipment>
**Description:** <what nearly happened>

**Root Cause:** <why did it nearly happen>
**Immediate Action:** <what was done immediately>
**Corrective Action:** <what must be done to prevent recurrence>
**Owner:** <who is responsible for corrective action>
**Due Date:** <date>
**BMS Evidence:** <links to exported data>

**Status:** Open / Closed
**Closed by:** <name> Date: <date>
```

---

## 10. Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-05-19 | Compliance Team | Initial COIDA accident reporting procedure |

### Approval

- **Facilities Manager:** ___________________ Date: ___________
- **Information Security Officer:** ___________________ Date: ___________
- **Managing Director:** ___________________ Date: ___________

---

## 11. Related Documents

- [South African Regulatory Compliance Register](south-africa-regulatory-compliance-register.md)
- [Compliance Module](../../04-features/compliance-module.md)
- [Compliance API Reference](../../03-api-reference/compliance-api.md)
- [Electrical Certificate of Compliance (SANS 10142-1)](../../04-features/compliance-module.md) — relevant for electrical accidents
- [Lift Safety Compliance](../../04-features/compliance-module.md) — relevant for lift incidents

---

*This document is a controlled record under COIDA s49. Unauthorized modification is prohibited.*