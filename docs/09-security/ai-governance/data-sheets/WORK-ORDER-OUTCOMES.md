---
title: "Data Sheet: Work Order Outcomes"
type: "data-sheet"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
dataset_id: "ds-work-order-outcomes"
tags: ["ai-governance", "data-sheet", "work-orders", "ml-feedback", "technician"]
domain: "compliance"
audience: ["developers", "data-scientists", "auditors"]
complexity: "intermediate"
---

# Data Sheet: Work Order Outcomes

## 1. Overview

| Field | Value |
|-------|-------|
| **Dataset Name** | Work Order Outcomes |
| **Dataset ID** | `ds-work-order-outcomes` |
| **Owner** | SENTINEL Development Team |
| **Status** | Active |
| **Primary Consumers** | ML feedback loop, QualityGateEvaluator, training readiness assessment |

## 2. Data Source

**Origin:** Work order system integrated with technician feedback and ML prediction outcomes.

**Collection method:**
- Event-driven: Data captured at each work order lifecycle stage
- Work order creation: Automated (health < 50% triggers PostgreSQL trigger) or manual
- Assignment: Technician assigned by equipment type -> specialty mapping
- Completion: Technician marks complete with outcome notes
- Feedback: Structured feedback on prediction accuracy (was the AI correct?)

**Data flow:**
1. ML model predicts equipment issue -> recommendation generated
2. Work order created (WO-SIM prefix for auto-generated)
3. Technician assigned and notified (Telegram/WhatsApp)
4. Technician performs work, records outcome
5. ML feedback service validates outcome against prediction
6. Feedback used in model retraining pipeline

## 3. Collection Period and Refresh

| Field | Value |
|-------|-------|
| **Collection Start** | 2026-02-06 (v9.0 ML deployment) |
| **Collection Mode** | Event-driven (not continuous polling) |
| **Events Captured** | WO creation, assignment, status changes, completion, feedback |
| **Feedback Latency** | Typically 1-72 hours after work order completion |
| **Refresh** | Real-time event capture; ML feedback batch processing every 30 seconds |

## 4. Data Quality Checks

**Quality service:** `MLFeedbackService` validates outcomes against predictions.

| Check | Method | Threshold |
|-------|--------|-----------|
| **Feedback completeness** | Required fields validation on WO completion | All mandatory fields filled |
| **Outcome-prediction alignment** | Compare actual failure mode to predicted failure mode | Tracked as ML accuracy metric |
| **Feedback timeliness** | Time from WO completion to feedback submission | Label lag p95 < configurable threshold |
| **Feedback capture rate** | Percentage of completed WOs with ML feedback | Target: >85% in live mode |
| **Duplicate detection** | WO ID uniqueness check | Reject duplicate submissions |

**Missing data policy:**
- Work orders without feedback: Flagged as incomplete, excluded from ML training until feedback received
- Partial feedback: Accepted but confidence-weighted (less weight in retraining)
- Late feedback (>7 days): Accepted with reduced weight

**Quality gate integration:**
- `feedback_capture_rate_7d_pct`: 7-day rolling feedback capture rate
- `label_lag_p95_hours`: 95th percentile feedback latency
- Training readiness thresholds: live (0.85/180/5), shadow (0.75/120/3), sim (0.50/30/1)

## 5. Sensitive Fields

| Field | Sensitivity | Control |
|-------|------------|---------|
| **Technician names** | **POPIA protected** | Encrypted at rest (Phase 081), access restricted to operations team |
| **Technician phone numbers** | **POPIA protected** | Encrypted at rest, used only for notification delivery |
| **Work order notes** | **Low sensitivity** | May contain equipment-specific details; no PII expected |
| **Equipment codes** | **Not sensitive** | Internal identifiers |
| **Prediction outcomes** | **Not sensitive** | ML accuracy data |
| **Feedback ratings** | **Not sensitive** | Structured numeric/categorical feedback |

**PII handling:**
- Technician personal data encrypted at rest (AES-256, Phase 081 security remediation)
- Personal data not included in ML training datasets
- Technician identity anonymized in aggregated ML feedback metrics
- Access to PII restricted to operations team and system administrators
- Retention per POPIA data privacy policy

## 6. Known Bias and Skew

| Bias | Description | Mitigation |
|------|-------------|------------|
| **Technician experience bias** | Feedback quality varies by technician experience level; junior technicians may misclassify outcomes | Weight feedback by technician seniority; flag outlier feedback for review |
| **Confirmation bias** | Technicians may confirm AI prediction even when uncertain | Include "unsure" option in feedback form; track confirmation rate per technician |
| **Selection bias** | Only completed work orders have feedback; abandoned or deferred WOs lack outcome data | Track WO completion rate; model for missing-not-at-random |
| **Equipment type skew** | Some equipment types generate more WOs (e.g., FCU/VAV zone issues) than others (e.g., generators) | Weight by equipment type in aggregated metrics |
| **Severity skew** | Critical issues more likely to receive prompt, detailed feedback; routine maintenance may have sparse feedback | Monitor feedback completeness by severity tier |

## 7. Retention and Lifecycle

| Policy | Value |
|--------|-------|
| **Work order records** | Per data privacy policy (minimum 3 years for operational records) |
| **ML feedback records** | Retained with associated model version |
| **Technician PII** | Per POPIA: retained only while employment relationship active + 1 year |
| **Aggregated metrics** | Indefinite (anonymized, no PII) |
| **Deletion policy** | PII deleted on request or employment termination + retention period |

## 8. Lawful Basis and Regulatory

| Regulation | Basis | Notes |
|------------|-------|-------|
| **POPIA** | Contractual obligation | Technician data collected as part of employment/service contract |
| **POPIA** | Legitimate interest | Work order operational data for building management |
| **NIST AI RMF** | MS 2.5, MS 2.9 | Data sheet supports model documentation |
| **ISO 42001** | A.6.2.6 | AI system data documentation |

## 9. Access Controls

| Role | Access Level |
|------|-------------|
| ML pipeline | Read (anonymized feedback, no PII) |
| Operations team | Read/Write (full access including technician PII) |
| Data scientists | Read (anonymized, for feedback analysis) |
| Auditors | Read (for compliance verification, PII access logged) |
| External parties | None (data never shared externally) |

---

*This data sheet follows the SENTINEL AI Governance Framework. For updates, contact the SENTINEL Development Team.*
