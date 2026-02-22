# AEGIS BESS Discovery Prompt

> **Version:** 1.0 | **Created:** 2026-02-22
> **Purpose:** Gate between "monitoring" and "real control". No BESS automation without a completed discovery per site.
> **Usage:** Copy to `{site_id}.md`, complete per site, treat as AEGIS contract input.

---

## How to use this

1. Complete this per site
2. Store completed version as `docs/energy/aegis/{site_id}.md`
3. Treat it as AEGIS's contract input
4. Do not automate anything not written here

Once a completed version is submitted:
- Classify site risk
- Decide if AEGIS can write at all
- Define Tier rules for that site
- Draft the AEGIS agent spec
- Map safety boundaries

**This is the gate between "monitoring" and "real control".**

---

## 1. Site and ownership

| Field | Value |
|-------|-------|
| Site name and site_id | |
| Physical location | |
| Owner of PV and BESS | |
| Warranty provider and expiry date | |
| Who is allowed to approve control changes | |

---

## 2. System architecture

| Field | Value |
|-------|-------|
| Inverter brand and model | |
| Battery chemistry and manufacturer | |
| Total capacity kWh | |
| Max charge and discharge kW | |
| PCS type (AC-coupled / DC-coupled / hybrid) | |
| Is there a local controller or EMS | |

---

## 3. Grid and generator integration

| Field | Value |
|-------|-------|
| Grid tied / island capable / off-grid | |
| Export allowed yes/no | |
| Export limit (kW) | |
| NRS compliance status | |
| Generator present yes/no | |
| Generator make and ATS logic | |
| Priority order: Grid / BESS / Generator | |

---

## 4. Control interfaces

| Field | Value |
|-------|-------|
| Available APIs (REST / Modbus / BACnet / MQTT / vendor SDK) | |
| Read points list (SOC, power, temp, alarms) | |
| Write points list (charge rate, discharge enable, mode) | |
| Write latency typical and worst case | |
| Vendor cloud dependency yes/no | |

---

## 5. Operating rules (current reality)

| Field | Value |
|-------|-------|
| Min SOC allowed | |
| Max SOC allowed | |
| Reserve SOC for outage | |
| Max depth of discharge | |
| Allowed C-rate | |
| Cooling constraints | |
| Night charging allowed yes/no | |
| Weekend behaviour | |

---

## 6. Protection and safety

| Field | Value |
|-------|-------|
| Fire suppression present | |
| Thermal runaway detection | |
| Manual isolation location | |
| Emergency shutdown procedure | |
| Authority to override system | |
| Existing interlocks | |

---

## 7. Financial and contractual limits

| Field | Value |
|-------|-------|
| Feed-in tariff | |
| Peak tariff periods | |
| Demand charges | |
| Warranty cycle limits | |
| Penalty clauses for misuse | |
| SLA on uptime | |

---

## 8. Current operational use

Tick all that apply:

- [ ] Backup only
- [ ] Peak shaving
- [ ] Load shifting
- [ ] Tariff arbitrage
- [ ] PV smoothing
- [ ] Generator reduction

**Describe actual usage vs design intent:**

> (fill in)

---

## 9. Incident history

| Field | Value |
|-------|-------|
| Any shutdowns in last 12 months | |
| Any fire or overheating events | |
| Any inverter trips | |
| Any grid compliance violations | |
| Root causes and fixes | |

---

## 10. Data quality

| Field | Value |
|-------|-------|
| Telemetry update rate (seconds) | |
| Missing data frequency | |
| SOC accuracy confidence | |
| Time sync issues yes/no | |
| Manual data corrections used | |

---

## 11. Automation appetite

For each, mark: **Never** / **Advisory** / **Approval** / **Auto**

| Capability | Level |
|------------|-------|
| Charge scheduling | |
| Discharge for peak shaving | |
| Generator coordination | |
| Export control | |
| Emergency islanding | |
| SOC reserve management | |

---

## 12. Human roles

| Role | Person / Contact |
|------|-----------------|
| Who monitors daily | |
| Who approves Tier 2 | |
| Who can force manual mode | |
| Escalation contact after hours | |

---

## 13. Compliance

| Field | Value |
|-------|-------|
| Municipal approval status | |
| Grid code compliance | |
| Insurance conditions | |
| Audit requirements | |
| Reporting obligations | |

---

## 14. Success criteria

In one year, AEGIS is successful if:

1.
2.
3.

Examples: reduced diesel use, zero outages, payback met.

---

## 15. Red lines (non-negotiables)

List anything AEGIS must never do.

Examples:
- Never discharge below 30% SOC
- Never export during blackout
- Never override vendor safety lock

1.
2.
3.
