---
title: "Data Sheet: Equipment Telemetry"
type: "data-sheet"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
dataset_id: "ds-equipment-telemetry"
tags: ["ai-governance", "data-sheet", "telemetry", "bacnet", "modbus", "dali"]
domain: "compliance"
audience: ["developers", "data-scientists", "auditors"]
complexity: "intermediate"
---

# Data Sheet: Equipment Telemetry

## 1. Overview

| Field | Value |
|-------|-------|
| **Dataset Name** | Equipment Telemetry |
| **Dataset ID** | `ds-equipment-telemetry` |
| **Owner** | SENTINEL Development Team |
| **Status** | Active |
| **Primary Consumers** | All 6 active ML models (CHILLER, AHU, FCU, UPS, GENERATOR, DALI) |

## 2. Data Source

**Origin:** BACnet, Modbus, and DALI sensors via the SENTINEL device abstraction layer.

**Collection method:**
- Continuous polling at configurable intervals (default: 60 seconds)
- BACnet/IP for HVAC controllers (Siemens Desigo, CAREL)
- Modbus TCP/RTU for electrical equipment (UPS, generators)
- DALI-2 via Tridonic controllers for lighting
- Device abstraction layer normalizes all protocols into unified point model

**Sites covered:**

| Site | Equipment Count | Types | Notes |
|------|----------------|-------|-------|
| S002 | 26 | 12 | Office building, primary training site |
| S005 | 90 | 15 | Hospital, includes LIFT, JACE, COLD, MEDGAS |
| S012 | 19 | 7 | Office building |

## 3. Collection Period and Refresh

| Field | Value |
|-------|-------|
| **Collection Start** | 2026-02-06 (v9.0 ML deployment) |
| **Collection Mode** | Continuous real-time (live), hourly persistence (simulation) |
| **Poll Interval** | 60 seconds (configurable per device) |
| **Persistence** | Real-time to Supabase in live mode; hourly batch in simulation |
| **Simulation Data** | 365-day synthetic dataset per site using JHB climate model |
| **Historical Depth** | Training uses up to 3 years of data (some simulated) |

## 4. Data Quality Checks

**Quality service:** `DataQualityService` performs automated quality scoring (0-100).

| Check | Method | Threshold |
|-------|--------|-----------|
| **Sensor uptime** | Heartbeat monitoring per device | >95% for active model use |
| **Gap detection** | Missing data intervals identified and flagged | Gaps >15 min trigger interpolation |
| **Value range validation** | Min/max bounds per sensor type | Out-of-range values flagged as anomalies |
| **Quality scoring** | Composite score (0-100) per equipment per day | Score <60 triggers data quality alert |
| **Stale data detection** | Timestamp comparison against poll interval | Stale >5x interval triggers alert |

**Missing data policy:**
- Gaps <= 15 minutes: Linear interpolation
- Gaps 15-60 minutes: Forward-fill then interpolation
- Gaps > 60 minutes: Marked as missing, excluded from model training window
- Sensor defaults: Penalize model confidence when using default values (not actual readings)

## 5. Sensitive Fields

| Field | Sensitivity | Control |
|-------|------------|---------|
| Equipment telemetry (temperatures, pressures, currents) | **Not sensitive** | No PII, no restrictions |
| Equipment codes (e.g., S002-CHILLER-B1-001) | **Not sensitive** | Internal identifiers only |
| Site identifiers | **Low sensitivity** | Internal use; site names not exposed externally |
| GPS/location coordinates | **Not collected** | Building addresses known but not in telemetry dataset |

**PII assessment:** This dataset contains NO personally identifiable information. All data points describe equipment operating parameters. Occupancy data (where collected) is binary (zone occupied/unoccupied) and not identity-linked.

## 6. Known Bias and Skew

| Bias | Description | Mitigation |
|------|-------------|------------|
| **Simulation bias** | Training data from 365-day simulation may not capture real-world sensor noise, drift, and calibration issues | Monitor live vs. simulation prediction accuracy divergence; retrain with live data as it accumulates |
| **Site bias** | S002 is the primary training site; models may underperform on S005 (hospital) or S012 (different building profile) | Multi-site validation; site-specific confidence adjustments |
| **Seasonal bias** | JHB climate model captures SA seasons (Oct-Mar wet, Apr-Sep dry); models may not generalize to other climates | Document climate assumptions; require retraining for non-JHB deployments |
| **Equipment age bias** | New equipment dominates current dataset; degradation patterns may be underrepresented | Simulation includes accelerated degradation scenarios |
| **Southern hemisphere solar** | Sun in north sky in SA; north-facing zones receive max solar gain, south minimal | Solar gain models encode hemisphere; retraining required for northern hemisphere |
| **Altitude effects** | JHB at ~1,750m affects air density, condenser performance, boiling points | Altitude correction factors applied in preprocessing |

## 7. Retention and Lifecycle

| Policy | Value |
|--------|-------|
| **Raw data retention** | 365 days |
| **Aggregated daily metrics** | Indefinite (used for trend analysis) |
| **Model training snapshots** | Retained with model version (per model card deployment history) |
| **Deletion policy** | Raw data auto-purged after 365 days; aggregates retained |
| **Backup** | Supabase point-in-time recovery; JSON fallback files in `backend/app/data/` |

## 8. Lawful Basis and Regulatory

| Regulation | Basis | Notes |
|------------|-------|-------|
| **POPIA** | Legitimate interest | Equipment telemetry, no PII involved |
| **NIST AI RMF** | MS 2.5, MS 2.9 | Data sheet supports model documentation requirement |
| **ISO 42001** | A.6.2.6 | AI system data documentation |

## 9. Access Controls

| Role | Access Level |
|------|-------------|
| ML pipeline | Read (automated, for training and inference) |
| Data scientists | Read (for model development and validation) |
| Site operators | Read (via dashboards, filtered by site) |
| Auditors | Read (for compliance verification) |
| External parties | None (data never shared externally) |

---

*This data sheet follows the SENTINEL AI Governance Framework. For updates, contact the SENTINEL Development Team.*
