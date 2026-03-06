# SENTINEL — Technical Forum Briefing

**Prepared:** 2 March 2026 | **For:** Technical Operations Meeting

---

## What is SENTINEL?

**S**mart **EN**vironment & **T**elemetry **IN**telligence for **E**fficient **L**iving

An AI layer that sits on top of your existing BMS (Siemens Desigo, Tridonic DALI-2, Niagara) to shift facility management from **reactive** to **predictive**.

---

## How SENTINEL Addresses Your Agenda

| Agenda Item | Current State | With SENTINEL |
|---|---|---|
| **3a. Job Cards & Repeating Faults** | Manual tracking, faults repeat without pattern detection | AI detects recurring faults (Random Forest classifier), auto-generates WOs, tracks response times live |
| **3c. Critical Alarms (BACS)** | Alarms trigger reactive response | LSTM forecasting predicts faults 24-72h ahead; health scores trend equipment performance over time |
| **3f. High-Risk Interventions** | Ad-hoc oversight | Tiered autonomy (recommend → supervised → automatic), step-up PIN auth, full audit trail |
| **3g. Complex Technical Issues** | Meeting-dependent resolution | AI cross-correlates HVAC + lighting + occupancy + energy data; Telegram bot for async collaboration |
| **4a. Critical Equipment List** | Static spreadsheet | Live equipment registry with AI-scored criticality: health, anomaly score, fault count, remaining useful life |
| **4b. Maintenance Frequency** | Standard intervals, no compliance tracking | Configurable per-type intervals (30d generators → 365d lighting), auto-escalation when overdue |
| **4c. Operating Standards & SOPs** | Documents in shared drives | Uploaded to SENTINEL with trust-level tagging; AI chat retrieves relevant SOPs contextually |

---

## Key Capabilities

**Predictive Maintenance**
- 20 trained ML models (LSTM forecasting, Autoencoder anomaly detection, Random Forest fault classification)
- 5-component health scoring: sensor data, anomaly score, fault history, maintenance recency, operating hours

**Automated Workflows**
- Equipment health drops below 50% → Alert → Work Order → Technician notified via Telegram/WhatsApp
- Inspection checklists for 7 equipment types, guided step-by-step via mobile

**Cross-System Intelligence**
- HVAC + Lighting + Solar/BESS + Fire + Security + Water in one view
- Occupancy-driven optimisation: empty zones get relaxed setpoints and dimmed lighting automatically

**Technician Tools**
- Telegram bot: `/info_` for equipment status, `/inspect_` for guided inspections, `done #WO-XXXX` to complete
- No app install — browser-based dashboard works on iPads, phones, media walls

---

## Projected Value

| Metric | Target |
|---|---|
| Unplanned downtime reduction | 40% |
| Maintenance cost savings | 25% |
| Energy optimisation | 15-25% through cross-system coordination |
| Mean time to detect faults | Hours → Minutes (automated) |

---

## Current Status

- **Live at:** Sandton City Office Tower (site-002)
- **Monitoring:** 83 equipment items, 28 occupancy sensors, 135 luminaires
- **Active:** HVAC intelligence, Solar/BESS dispatch, occupancy-driven control
- **Building:** Energy optimisation, water baseline, fire compliance tracking

---

## Next Steps

1. Enable energy optimisation analysis for site-002
2. Seed DALI lighting controller data for full lighting intelligence
3. Configure WhatsApp integration for technician notifications
4. Onboard additional sites as needed

---

*SENTINEL is equipment-agnostic, protocol-agnostic, and runs entirely on-premises. No cloud dependency for operations.*
